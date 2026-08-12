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

from config import (
    ANALYSIS_MODEL,
    CLASSIFICATION_MAX_TOKENS,
    CLASSIFICATION_SAMPLE_CHARS,
    CLASSIFICATION_THINKING,
    EFFORT,
    LIGHTWEIGHT_MODEL,
    MAX_TOKENS_PER_CHUNK,
    THINKING_CONFIG,
    TRUNCATION_RETRY_MAX_TOKENS,
)
from models.schemas import (
    AnalysisRun,
    AnalyzedChunk,
    ChunkAnalysis,
    ChunkFailure,
    ChunkFailureReason,
    Confidence,
    DocumentChunk,
    DocumentTypeGuess,
)
from prompts.analysis import (
    ANALYSIS_SYSTEM_PROMPT,
    DOCUMENT_TYPE_SYSTEM_PROMPT,
    build_chunk_prompt,
    build_classification_prompt,
)

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


def _is_truncated_json(exc: ValidationError) -> bool:
    """True when the payload was not parseable as JSON at all.

    Distinguished from a schema violation (wrong enum, missing field) by pydantic's
    typed error code rather than by matching on message text, which changes between
    pydantic releases.

    Under structured outputs the model cannot emit ungrammatical JSON, so this
    condition means the response was cut off mid-token — i.e. the token budget ran
    out. Confirmed live: a 4000-token chunk request produced
    "EOF while parsing a string at line 1 column 4892" with type=json_invalid.
    """
    try:
        return any(err.get("type") == "json_invalid" for err in exc.errors())
    except Exception:  # noqa: BLE001 - never let error inspection mask the failure
        return False


def interpret_response(
    response: _ParsedResponse,
    chunk_index: int,
    *,
    max_tokens: int = MAX_TOKENS_PER_CHUNK,
) -> AnalyzedChunk | ChunkFailure:
    """Map an API response onto a success or a typed failure.

    Pure and synchronous by design — this is the branch most likely to harbour a
    bug, so it is testable without network access.

    `stop_reason` is checked BEFORE `parsed_output`: a refusal or a truncation
    bypasses the structured-output guarantee, so the parsed field may be missing or
    non-conforming even though the request itself succeeded.

    `max_tokens` is passed in rather than read from config so the diagnostics name
    the budget that was actually used — which differs on a retry.
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
        # the budget is too low for the thinking config — do not treat it as random
        # model noise.
        logger.error(
            "chunk %s hit the token ceiling (max_tokens=%s, thinking=%s) — "
            "output truncated; review the per-chunk budget",
            chunk_index,
            max_tokens,
            THINKING_CONFIG,
        )
        return ChunkFailure(
            chunk_index=chunk_index,
            reason=ChunkFailureReason.TRUNCATED,
            user_message="This section was too long to analyze in one pass.",
            detail=f"stop_reason=max_tokens at max_tokens={max_tokens}",
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


async def _attempt_chunk(
    client: AsyncAnthropic,
    chunk: DocumentChunk,
    *,
    max_tokens: int,
    document_type_hint: str | None,
) -> AnalyzedChunk | ChunkFailure:
    """One analysis attempt at a given budget. Never raises.

    Split out from analyze_chunk so a truncated attempt can be retried at a larger
    budget without duplicating the request or the error handling.

    The SDK already retries 429 and 5xx with exponential backoff (max_retries
    defaults to 2), so there is no hand-rolled transport retry here. By the time a
    RateLimitError surfaces, those retries are spent.
    """
    try:
        response = await client.messages.parse(
            model=ANALYSIS_MODEL,
            max_tokens=max_tokens,
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
        # The SDK validates the response while constructing it, so a truncated
        # payload raises here and `stop_reason` never reaches interpret_response.
        # Structured outputs constrains the grammar, so syntactically invalid JSON
        # means generation was cut off mid-token — a budget failure, not a
        # malformed-output one. CLAUDE.md requires the two be logged separately;
        # collapsing them would hide a systematic budget problem as random noise.
        if _is_truncated_json(exc):
            logger.error(
                "chunk %s returned unparseable JSON consistent with truncation "
                "(max_tokens=%s, thinking=%s) — review the per-chunk budget",
                chunk.index,
                max_tokens,
                THINKING_CONFIG,
            )
            return ChunkFailure(
                chunk_index=chunk.index,
                reason=ChunkFailureReason.TRUNCATED,
                user_message="This section was too long to analyze in one pass.",
                detail=f"json_invalid during response validation at "
                f"max_tokens={max_tokens}: {exc}",
            )
        logger.warning("chunk %s failed schema validation: %s", chunk.index, exc)
        return ChunkFailure(
            chunk_index=chunk.index,
            reason=ChunkFailureReason.INVALID_OUTPUT,
            user_message="This section could not be analyzed.",
            detail=f"ValidationError: {exc}",
        )

    return interpret_response(response, chunk.index, max_tokens=max_tokens)


async def analyze_chunk(
    client: AsyncAnthropic,
    chunk: DocumentChunk,
    *,
    document_type_hint: str | None = None,
    retry_on_truncation: bool = True,
) -> AnalyzedChunk | ChunkFailure:
    """Analyze one chunk, retrying once at a larger budget if it truncates.

    Never raises — every failure becomes a ChunkFailure.

    Truncation is the one failure worth retrying: it is a property of this request's
    budget, not of the document or the service, so the same call at a higher ceiling
    has a real chance of succeeding. The other failure kinds are not retried here —
    rate limits and 5xx have already exhausted the SDK's own backoff, a refusal will
    refuse again, and a schema violation will violate again. Retrying those would
    just double the cost of a certain failure.

    The retry runs at most once. A chunk that truncates twice is reported as a
    skipped section, which the UI already discloses, rather than escalated into an
    unbounded spend.
    """
    outcome = await _attempt_chunk(
        client,
        chunk,
        max_tokens=MAX_TOKENS_PER_CHUNK,
        document_type_hint=document_type_hint,
    )

    truncated = (
        isinstance(outcome, ChunkFailure)
        and outcome.reason is ChunkFailureReason.TRUNCATED
    )
    if not (truncated and retry_on_truncation):
        return outcome

    logger.warning(
        "chunk %s truncated at max_tokens=%s — retrying once at %s",
        chunk.index,
        MAX_TOKENS_PER_CHUNK,
        TRUNCATION_RETRY_MAX_TOKENS,
    )
    retried = await _attempt_chunk(
        client,
        chunk,
        max_tokens=TRUNCATION_RETRY_MAX_TOKENS,
        document_type_hint=document_type_hint,
    )

    if isinstance(retried, AnalyzedChunk):
        logger.info(
            "chunk %s recovered on retry at max_tokens=%s",
            chunk.index,
            TRUNCATION_RETRY_MAX_TOKENS,
        )
        return retried

    # Keep the retry's reason and user-facing message — it may have failed for a
    # different reason the second time — but record that a retry happened, so a
    # persistent truncation is distinguishable in the logs from a one-shot one.
    logger.error(
        "chunk %s failed again after the truncation retry (reason=%s)",
        chunk.index,
        retried.reason.value,
    )
    return retried.model_copy(
        update={
            "detail": f"after truncation retry at "
            f"max_tokens={TRUNCATION_RETRY_MAX_TOKENS}: {retried.detail}"
        }
    )


def _classification_sample(chunks: list[DocumentChunk]) -> str:
    """Opening text of the document, up to the sample budget.

    Drawn across leading chunks rather than from chunk 0 alone, so a thin cover
    page does not become the entire sample.
    """
    parts: list[str] = []
    used = 0
    for chunk in chunks:
        remaining = CLASSIFICATION_SAMPLE_CHARS - used
        if remaining <= 0:
            break
        parts.append(chunk.text[:remaining])
        used += min(len(chunk.text), remaining)
    return "\n\n".join(parts)


async def classify_document_type(
    client: AsyncAnthropic,
    chunks: list[DocumentChunk],
    *,
    model: str = LIGHTWEIGHT_MODEL,
) -> str | None:
    """Best-effort document-type classification for the analysis hint.

    Returns None rather than raising, always. This is an optimisation: without a
    hint the analysis still runs, so a classification failure must never fail the
    document. Every exit that is not a confident answer returns None.

    The request shape differs from the analysis call: thinking is disabled rather
    than adaptive, and no `effort` is sent. Both are model constraints on Haiku 4.5,
    verified against the live API — see config.py.
    """
    if not chunks:
        return None

    sample = _classification_sample(chunks)
    if not sample.strip():
        return None

    try:
        response = await client.messages.parse(
            model=model,
            max_tokens=CLASSIFICATION_MAX_TOKENS,
            system=DOCUMENT_TYPE_SYSTEM_PROMPT,
            thinking=CLASSIFICATION_THINKING,
            output_format=DocumentTypeGuess,
            messages=[{"role": "user", "content": build_classification_prompt(sample)}],
        )
    except (
        anthropic.RateLimitError,
        anthropic.APIConnectionError,
        anthropic.APIStatusError,
        ValidationError,
    ) as exc:
        logger.warning(
            "document-type classification failed (%s); continuing without a hint: %s",
            type(exc).__name__,
            exc,
        )
        return None

    if response.stop_reason not in (None, "end_turn", "stop_sequence"):
        logger.info(
            "document-type classification did not finish cleanly (stop_reason=%s); "
            "continuing without a hint",
            response.stop_reason,
        )
        return None

    guess = response.parsed_output
    if guess is None:
        logger.info("document-type classification returned no parsed output")
        return None

    if guess.confidence is Confidence.LOW or not guess.document_type.strip():
        # A weak guess is applied to EVERY chunk, so it correlates errors across
        # the whole run. No hint is better than a bad one.
        logger.info(
            "document-type classification too weak to use (confidence=%s, type=%r)",
            guess.confidence.value,
            guess.document_type,
        )
        return None

    logger.info(
        "document classified as %r (confidence=%s)",
        guess.document_type,
        guess.confidence.value,
    )
    return guess.document_type.strip()


async def analyze_document(
    chunks: list[DocumentChunk],
    *,
    client: AsyncAnthropic,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    on_progress: Callable[[int, int], None] | None = None,
    document_type_hint: str | None = None,
    classify: bool = True,
    retry_on_truncation: bool = True,
) -> AnalysisRun:
    """Analyze every chunk and collect both successes and failures.

    `on_progress(completed, total)` fires as each chunk settles, giving the UI the
    determinate count it needs for "Analyzing 4 of 11 sections" rather than an
    opaque spinner. Completion order is not document order — the count is
    meaningful, the index is not.

    A cheap classification pre-pass runs first so every chunk knows what kind of
    document it is judging missing clauses against. It is awaited before the fan-out
    because the hint has to reach all chunks; it costs one small Haiku call rather
    than serialising an expensive Sonnet one. Pass `document_type_hint` to supply the
    answer directly, or `classify=False` to skip it.
    """
    if not chunks:
        return AnalysisRun(analyzed=[], failures=[])

    hint = document_type_hint
    if hint is None and classify:
        hint = await classify_document_type(client, chunks)

    semaphore = asyncio.Semaphore(max_concurrency)
    completed = 0
    total = len(chunks)
    lock = asyncio.Lock()

    async def run_one(chunk: DocumentChunk) -> AnalyzedChunk | ChunkFailure:
        nonlocal completed
        async with semaphore:
            outcome = await analyze_chunk(
                client,
                chunk,
                document_type_hint=hint,
                retry_on_truncation=retry_on_truncation,
            )
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
