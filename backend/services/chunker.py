"""Token-aware chunking of parsed documents.

Chunks are 3000 tokens with 200 tokens of overlap (CLAUDE.md). The overlap exists
so a clause split across a boundary is still seen whole by at least one chunk.

Design: text is broken into paragraph SEGMENTS, each tagged with the page it came
from, and segments are then packed into chunks. Working in segments rather than
raw character offsets means page attribution falls out of the packing for free —
a chunk's pages are simply the pages of its segments — and boundaries land
between paragraphs instead of mid-word.

Token counting is pluggable. The default is a deliberately conservative local
estimate; `make_api_token_counter` swaps in exact counts from the API when the
extra round trips are worth it.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Callable

from config import ANALYSIS_MODEL, CHUNK_TOKENS, OVERLAP_TOKENS
from models.schemas import DocumentChunk, ParsedDocument

logger = logging.getLogger(__name__)

TokenCounter = Callable[[str], int]

# Re-exported under the historical names so call sites read naturally; the values
# are owned by config.py (per CLAUDE.md).
DEFAULT_CHUNK_TOKENS = CHUNK_TOKENS
DEFAULT_OVERLAP_TOKENS = OVERLAP_TOKENS

# Deliberately LOW. Anthropic tokenizers average roughly 3.5-4 characters per
# token on English prose; legal text runs denser because of citations, numbers and
# capitalised defined terms. Dividing by the low end over-estimates the token
# count, which yields slightly smaller chunks — the safe direction to be wrong,
# since under-estimating would silently push requests past the budget.
CHARS_PER_TOKEN = 3.5

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.;:!?])\s+")

# Inline page boundary, written into the chunk text the model reads.
#
# Without this the model is told which pages a chunk spans but is shown text with
# no boundaries in it, so the only way to pick a page is to guess from position.
# Measured on a 6-page lease: 11 of 13 citations were wrong, every one of them
# inside the permitted range and therefore undetectable by range checking. The
# analyzer's out-of-range sanitiser cannot help here — a wrong-but-plausible page
# is exactly what it cannot see, and a citation that looks verified and is not is
# the failure docs/ui-patterns.md is built around.
_PAGE_MARKER = "[page {n}]"


def _marked(page_number: int, text: str) -> str:
    return f"{_PAGE_MARKER.format(n=page_number)}\n\n{text}"


def estimate_tokens(text: str) -> int:
    """Conservative local token estimate. No network call."""
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN) + 1)


def make_api_token_counter(client, model: str = ANALYSIS_MODEL) -> TokenCounter:
    """Exact token counts via the API's count_tokens endpoint.

    Counting is not billed, but it is a network round trip per call, so this is
    opt-in. Use it to calibrate CHARS_PER_TOKEN against real documents, or when a
    document sits close enough to the budget that estimate error matters.
    """

    def count(text: str) -> int:
        if not text:
            return 0
        response = client.messages.count_tokens(
            model=model, messages=[{"role": "user", "content": text}]
        )
        return response.input_tokens

    return count


@dataclass(frozen=True)
class _Segment:
    """A paragraph-sized unit of text and the page it came from."""

    page_number: int
    text: str
    tokens: int


def _split_oversized(text: str, limit: int, counter: TokenCounter) -> list[str]:
    """Break a single paragraph that exceeds `limit` into pieces that do not.

    Falls back progressively: sentences, then words, then a hard character slice.
    The final fallback guarantees termination — without it a single unbroken
    token-dense string (a base64 blob, a table with no spaces) would loop forever.
    """
    if counter(text) <= limit:
        return [text]

    pieces: list[str] = []
    for unit in _split_units(text):
        if counter(unit) <= limit:
            pieces.append(unit)
            continue
        pieces.extend(_hard_slice(unit, limit, counter))

    merged = _remerge(pieces, limit, counter)
    return [p for p in merged if p.strip()]


def _hard_slice(text: str, limit: int, counter: TokenCounter) -> list[str]:
    """Slice text into pieces that each measure <= `limit` tokens.

    The character estimate only seeds the slice width; every piece is then
    verified with the actual counter and shrunk until it fits. Deriving the width
    from CHARS_PER_TOKEN alone is off by one at the boundary (a slice of exactly
    limit*3.5 chars measures limit+1 tokens), and is wrong by an unknown margin
    for an injected counter. Measuring closes both gaps.

    Shrinking bottoms out at one character, so forward progress is guaranteed
    regardless of what the counter reports.
    """
    pieces: list[str] = []
    start = 0
    width = max(1, int(limit * CHARS_PER_TOKEN))

    while start < len(text):
        size = width
        piece = text[start : start + size]
        while size > 1 and counter(piece) > limit:
            size = max(1, int(size * 0.8))
            piece = text[start : start + size]
        pieces.append(piece)
        start += len(piece)

    return pieces


def _split_units(text: str) -> list[str]:
    """Sentences where possible, else words."""
    sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
    if len(sentences) > 1:
        return sentences
    return text.split(" ")


def _remerge(pieces: list[str], limit: int, counter: TokenCounter) -> list[str]:
    """Recombine over-split fragments so we do not emit one chunk per sentence."""
    merged: list[str] = []
    buffer = ""
    for piece in pieces:
        candidate = f"{buffer} {piece}".strip() if buffer else piece
        if buffer and counter(candidate) > limit:
            merged.append(buffer)
            buffer = piece
        else:
            buffer = candidate
    if buffer:
        merged.append(buffer)
    return merged


def _marker_cost(counter: TokenCounter) -> int:
    """Token cost of one page marker, measured rather than assumed.

    Measured with a wide page number so the estimate cannot be low for long
    documents, and against the injected counter so it is right for the API
    tokenizer too.
    """
    return counter(_PAGE_MARKER.format(n=9999) + "\n\n")


def _build_segments(
    document: ParsedDocument, limit: int, counter: TokenCounter
) -> list[_Segment]:
    """Flatten pages into page-tagged paragraph segments.

    Pages with no text contribute nothing, which is what keeps them out of a
    chunk's `page_numbers` and therefore out of the model's citable set.

    Every segment's token count includes a page marker, even though `_to_chunk`
    only emits one where the page actually changes. That over-counts by a few
    tokens per paragraph, which is the safe direction to be wrong: the packing
    loop's budget arithmetic stays valid no matter which segments end up carrying
    a marker, and no chunk can exceed max_tokens because markers were added after
    it was measured.
    """
    marker = _marker_cost(counter)
    piece_limit = max(1, limit - marker)

    segments: list[_Segment] = []
    for page in document.pages:
        if not page.text.strip():
            continue
        for para in _PARAGRAPH_BREAK.split(page.text):
            para = para.strip()
            if not para:
                continue
            for piece in _split_oversized(para, piece_limit, counter):
                segments.append(
                    _Segment(
                        page_number=page.page_number,
                        text=piece,
                        tokens=counter(_marked(page.page_number, piece)),
                    )
                )
    return segments


def _overlap_tail(segments: list[_Segment], budget: int) -> list[_Segment]:
    """Trailing segments of a chunk that fit within the overlap budget.

    Capped at len-1 so a chunk can never be reproduced in full as the next
    chunk's prefix.
    """
    if budget <= 0 or len(segments) < 2:
        return []
    tail: list[_Segment] = []
    total = 0
    for seg in reversed(segments[1:]):
        if total + seg.tokens > budget:
            break
        tail.insert(0, seg)
        total += seg.tokens
    return tail


def chunk_document(
    document: ParsedDocument,
    *,
    max_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    token_counter: TokenCounter | None = None,
) -> list[DocumentChunk]:
    """Split a parsed document into overlapping, page-attributed chunks.

    Synchronous and CPU-bound. Call `chunk_document_async` from a route.
    """
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens cannot be negative")
    if overlap_tokens >= max_tokens:
        # Otherwise the overlap alone fills a chunk and no new text is ever
        # consumed — the classic non-terminating chunker.
        raise ValueError(
            f"overlap_tokens ({overlap_tokens}) must be less than "
            f"max_tokens ({max_tokens})"
        )

    counter = token_counter or estimate_tokens

    # Segments are capped at max_tokens - overlap_tokens so that carried overlap
    # plus one fresh segment can never exceed max_tokens. This invariant is what
    # lets the packing loop below add a segment unconditionally when a chunk is
    # still empty, without risking an over-budget chunk.
    segment_limit = max_tokens - overlap_tokens
    segments = _build_segments(document, segment_limit, counter)

    if not segments:
        logger.warning("%s produced no chunkable text", document.filename)
        return []

    chunks: list[DocumentChunk] = []
    carry: list[_Segment] = []
    i = 0

    while i < len(segments):
        current = list(carry)
        total = sum(s.tokens for s in current)
        added_new = 0

        while i < len(segments):
            seg = segments[i]
            if added_new > 0 and total + seg.tokens > max_tokens:
                break
            current.append(seg)
            total += seg.tokens
            added_new += 1
            i += 1
            if total >= max_tokens:
                break

        chunks.append(_to_chunk(len(chunks), current, total))
        carry = _overlap_tail(current, overlap_tokens)

    logger.info(
        "%s: %s pages -> %s chunks (max_tokens=%s, overlap=%s)",
        document.filename,
        document.page_count,
        len(chunks),
        max_tokens,
        overlap_tokens,
    )
    return chunks


def _to_chunk(index: int, segments: list[_Segment], tokens: int) -> DocumentChunk:
    """Assemble a chunk, marking each page boundary in the text itself.

    A marker is emitted whenever the page changes, including for the first
    segment — a chunk usually starts mid-page because of the carried overlap, so
    "the page has not changed yet" is not a safe assumption at the top.

    Every page in `page_numbers` therefore appears as a marker in `text`, and no
    other page does. That equivalence is what makes the citation checkable: the
    model is reading the same page attribution the parser produced, not inferring
    one from position.
    """
    pages = sorted({s.page_number for s in segments})

    parts: list[str] = []
    current_page: int | None = None
    for segment in segments:
        if segment.page_number != current_page:
            parts.append(_PAGE_MARKER.format(n=segment.page_number))
            current_page = segment.page_number
        parts.append(segment.text)

    return DocumentChunk(
        index=index,
        text="\n\n".join(parts),
        page_numbers=pages,
        token_estimate=tokens,
    )


async def chunk_document_async(
    document: ParsedDocument,
    *,
    max_tokens: int = DEFAULT_CHUNK_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
    token_counter: TokenCounter | None = None,
) -> list[DocumentChunk]:
    """Async entry point — offloads the CPU-bound split off the event loop."""
    return await asyncio.to_thread(
        chunk_document,
        document,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
        token_counter=token_counter,
    )
