"""Claude API calls and analysis orchestration.

Contract notes, all of which trace back to rules in CLAUDE.md:
  - Structured outputs via `output_format=ChunkAnalysis` — the Pydantic model is the
    only definition of the output shape.
  - `thinking` is set EXPLICITLY. Never rely on the model default: it varies by model
    and changed between Sonnet 4.6 and Sonnet 5.
  - `max_tokens` is one ceiling over thinking tokens AND response text together.
  - No `temperature` / `top_p` / `top_k` — a non-default value returns 400 on
    Sonnet 5. Behavior is steered through the system prompt instead.
  - A chunk that fails is REPORTED, never silently dropped.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Protocol

import anthropic
from anthropic import AsyncAnthropic
from pydantic import ValidationError

from config import ANALYSIS_MODEL, EFFORT, MAX_TOKENS_PER_CHUNK, THINKING_CONFIG
from models.schemas import (
    AnalysisRun,
    AnalyzedChunk,
    ChunkAnalysis,
    ChunkFailure,
    ChunkFailureReason,
    DocumentChunk,
)
from prompts.analysis import ANALYSIS_SYSTEM_PROMPT, build_chunk_prompt

logger = logging.getLogger(__name__)

# Bounded so a long document does not open one connection per chunk. Raise only
# against measured rate-limit headroom.
DEFAULT_MAX_CONCURRENCY = 4


class _ParsedResponse(Protocol):
    """The subset of the SDK response this module reads.

    Declared so `interpret_response` can be unit-tested with a stub instead of a
    live API call.
    """

    stop_reason: str | None
    parsed_output: ChunkAnalysis | None


def interpret_response(
    response: _ParsedResponse, chunk_index: int
) -> AnalyzedChunk | ChunkFailure:
    """Map an API response onto a success or a typed failure.

    Pure and synchronous by design — this is the branch most likely to harbour a
    bug, so it is testable without network access.

    `stop_reason` is checked BEFORE `parsed_output`: a refusal or a truncation
    bypasses the structured-output guarantee, so the parsed field may be missing or
    non-conforming even though the request itself succeeded.
    """
    stop_reason = response.stop_reason

    if stop_reason == "refusal":
        logger.warning("chunk %s refused by safety classifiers", chunk_index)
        return ChunkFailure(
            chunk_index=chunk_index,
            reason=ChunkFailureReason.REFUSED,
            user_message="This section could not be analyzed.",
            detail="stop_reason=refusal",
        )

    if stop_reason == "max_tokens":
        # Budget failure, NOT a malformed-JSON failure. If this fires repeatedly,
        # MAX_TOKENS_PER_CHUNK is too low for the thinking config — do not treat it
        # as random model noise.
        logger.error(
            "chunk %s hit the token ceiling (max_tokens=%s, thinking=%s) — "
            "output truncated; review the per-chunk budget",
            chunk_index,
            MAX_TOKENS_PER_CHUNK,
            THINKING_CONFIG,
        )
        return ChunkFailure(
            chunk_index=chunk_index,
            reason=ChunkFailureReason.TRUNCATED,
            user_message="This section was too long to analyze in one pass.",
            detail=f"stop_reason=max_tokens at max_tokens={MAX_TOKENS_PER_CHUNK}",
        )

    parsed = response.parsed_output
    if parsed is None:
        logger.warning(
            "chunk %s returned no parsed output (stop_reason=%s)", chunk_index, stop_reason
        )
        return ChunkFailure(
            chunk_index=chunk_index,
            reason=ChunkFailureReason.INVALID_OUTPUT,
            user_message="This section could not be analyzed.",
            detail=f"parsed_output was None with stop_reason={stop_reason}",
        )

    return AnalyzedChunk(chunk_index=chunk_index, analysis=parsed)


async def analyze_chunk(
    client: AsyncAnthropic,
    chunk: DocumentChunk,
    *,
    document_type_hint: str | None = None,
) -> AnalyzedChunk | ChunkFailure:
    """Analyze one chunk. Never raises — every failure becomes a ChunkFailure.

    The SDK already retries 429 and 5xx with exponential backoff (max_retries
    defaults to 2), so there is no hand-rolled retry loop here. By the time a
    RateLimitError surfaces, the retries are spent.
    """
    try:
        response = await client.messages.parse(
            model=ANALYSIS_MODEL,
            max_tokens=MAX_TOKENS_PER_CHUNK,
            system=ANALYSIS_SYSTEM_PROMPT,
            thinking=THINKING_CONFIG,
            # Merges with the format the SDK derives from output_format rather than
            # replacing it (anthropic/resources/messages/messages.py).
            output_config={"effort": EFFORT},
            output_format=ChunkAnalysis,
            messages=[
                {
                    "role": "user",
                    "content": build_chunk_prompt(
                        chunk, document_type_hint=document_type_hint
                    ),
                }
            ],
        )
    except anthropic.RateLimitError as exc:
        logger.warning("chunk %s rate limited after SDK retries: %s", chunk.index, exc)
        return ChunkFailure(
            chunk_index=chunk.index,
            reason=ChunkFailureReason.RATE_LIMITED,
            user_message="The analysis service is busy. Try again in a moment.",
            detail=f"RateLimitError: {exc}",
        )
    except anthropic.APIConnectionError as exc:
        logger.warning("chunk %s connection error: %s", chunk.index, exc)
        return ChunkFailure(
            chunk_index=chunk.index,
            reason=ChunkFailureReason.CONNECTION_ERROR,
            user_message="Could not reach the analysis service. Check your connection.",
            detail=f"APIConnectionError: {exc}",
        )
    except anthropic.APIStatusError as exc:
        # Covers 400/401/403/404/5xx. The status and body go to the log; the user
        # gets plain language, never a raw API error body.
        logger.error("chunk %s API error %s: %s", chunk.index, exc.status_code, exc)
        return ChunkFailure(
            chunk_index=chunk.index,
            reason=ChunkFailureReason.API_ERROR,
            user_message="This section could not be analyzed.",
            detail=f"APIStatusError {exc.status_code}: {exc}",
        )
    except ValidationError as exc:
        # Structured outputs makes this rare, but client-side validation of any
        # constraint the API cannot enforce still runs here.
        logger.warning("chunk %s failed client-side validation: %s", chunk.index, exc)
        return ChunkFailure(
            chunk_index=chunk.index,
            reason=ChunkFailureReason.INVALID_OUTPUT,
            user_message="This section could not be analyzed.",
            detail=f"ValidationError: {exc}",
        )

    return interpret_response(response, chunk.index)


async def analyze_document(
    chunks: list[DocumentChunk],
    *,
    client: AsyncAnthropic,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    on_progress: Callable[[int, int], None] | None = None,
) -> AnalysisRun:
    """Analyze every chunk and collect both successes and failures.

    `on_progress(completed, total)` fires as each chunk settles, giving the UI the
    determinate count it needs for "Analyzing 4 of 11 sections" rather than an
    opaque spinner. Completion order is not document order — the count is
    meaningful, the index is not.
    """
    if not chunks:
        return AnalysisRun(analyzed=[], failures=[])

    semaphore = asyncio.Semaphore(max_concurrency)
    completed = 0
    total = len(chunks)
    lock = asyncio.Lock()

    async def run_one(chunk: DocumentChunk) -> AnalyzedChunk | ChunkFailure:
        nonlocal completed
        async with semaphore:
            outcome = await analyze_chunk(client, chunk)
        async with lock:
            completed += 1
            current = completed
        if on_progress is not None:
            on_progress(current, total)
        return outcome

    outcomes = await asyncio.gather(*(run_one(chunk) for chunk in chunks))

    analyzed = [o for o in outcomes if isinstance(o, AnalyzedChunk)]
    failures = [o for o in outcomes if isinstance(o, ChunkFailure)]

    # Restore document order — gather returns in submission order, but be explicit
    # so downstream position-based sorting cannot silently depend on it.
    analyzed.sort(key=lambda a: a.chunk_index)
    failures.sort(key=lambda f: f.chunk_index)

    if failures:
        logger.warning("%s of %s chunks could not be analyzed", len(failures), total)

    return AnalysisRun(analyzed=analyzed, failures=failures)
