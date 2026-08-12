"""Upload and analysis endpoints.

Shape of the flow, and why:

    POST /api/documents/analyze   multipart PDF
        -> read (size-capped), parse, chunk   [synchronous, inside the request]
        -> 202 with a job id and the document metadata
    GET  /api/documents/analyze/{job_id}
        -> progress while running, the full result once COMPLETE

Parsing happens inside the POST rather than in the background on purpose. It is
the step that fails for reasons the user can act on — not a PDF, password
protected, scanned with no text layer — and those deserve an immediate 400 with a
specific message, not a job that has to be polled before it can report that the
file was never usable. It also means the 202 already carries the filename and page
count that docs/ui-patterns.md wants shown before analysis begins.

Analysis runs in the background because it is the slow, chunked, expensive part,
and because progress is only meaningful if someone can read it while it happens.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from config import (
    MAX_CHUNKS_PER_DOCUMENT,
    MAX_UPLOAD_BYTES,
)
from models.schemas import (
    AnalysisResult,
    AnalysisRun,
    DocumentChunk,
    DocumentMeta,
    JobState,
    JobStatus,
    ParsedDocument,
    SectionAnalysis,
    SkippedSection,
)
from services.analyzer import analyze_document
from services.chunker import chunk_document_async
from services.jobs import AnalysisJob
from services.parser import ParserError, parse_pdf

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# Read the upload in blocks so a hostile or accidental 2 GB file is refused after
# one block rather than after it is fully in memory. Content-Length is not trusted
# for this: the client writes it.
_READ_BLOCK = 1024 * 1024


def _safe_filename(raw: str | None) -> str:
    """Strip any path component from a client-supplied filename.

    Nothing here writes to disk, so this is not a traversal fix — it is to keep
    directory noise out of a value that is stored, logged, and rendered back to
    the user.
    """
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (name or "document.pdf")[:255]


async def _read_upload(file: UploadFile) -> bytes:
    blocks: list[bytes] = []
    total = 0
    while True:
        block = await file.read(_READ_BLOCK)
        if not block:
            break
        total += len(block)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"That file is larger than the "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit. Upload a smaller PDF, "
                f"or split it into sections.",
            )
        blocks.append(block)
    return b"".join(blocks)


def _require_client(request: Request):
    """The Anthropic client, or a 503 explaining that it was never configured.

    Separate from the parse path so a missing key does not masquerade as a bad
    upload. This is a server misconfiguration and says so.
    """
    client = getattr(request.app.state, "claude_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document analysis is not configured on this server "
            "(no API key). Text extraction is unaffected.",
        )
    return client


def _build_result(
    parsed: ParsedDocument,
    chunks: list[DocumentChunk],
    run: AnalysisRun,
    document: DocumentMeta,
) -> AnalysisResult:
    """Convert pipeline output into the wire payload.

    The one place `ChunkFailure` becomes `SkippedSection`, which is the point at
    which `detail` — raw API error bodies, validation tracebacks — is dropped.
    Keep it that way: if a second conversion path appears, so does a second chance
    to leak diagnostics into a browser.
    """
    pages_by_index = {chunk.index: chunk.page_numbers for chunk in chunks}

    return AnalysisResult(
        document=document,
        document_type_hint=run.document_type_hint,
        pages=parsed.pages,
        sections=[
            SectionAnalysis(
                chunk_index=a.chunk_index,
                pages=pages_by_index.get(a.chunk_index, []),
                analysis=a.analysis,
            )
            for a in run.analyzed
        ],
        skipped=[
            SkippedSection(
                chunk_index=f.chunk_index,
                reason=f.reason,
                message=f.user_message,
                pages=pages_by_index.get(f.chunk_index, []),
            )
            for f in run.failures
        ],
    )


async def _run_analysis(
    request: Request,
    job: AnalysisJob,
    parsed: ParsedDocument,
    chunks: list[DocumentChunk],
) -> None:
    """Background driver for one job. Never raises — it has no caller to raise to.

    An exception escaping here would be swallowed by the task and leave the job
    stuck on ANALYZING forever, which the frontend cannot distinguish from a slow
    document. Every exit sets a terminal status.
    """
    app = request.app
    client = app.state.claude_client
    try:
        async with app.state.analysis_semaphore:
            job.status = JobStatus.ANALYZING
            run = await analyze_document(
                chunks, client=client, on_progress=job.record_progress
            )

        job.status = JobStatus.COMPILING

        if not run.analyzed:
            # Every chunk failed. Reporting this as a successful analysis with zero
            # findings would be the single most dangerous output the product can
            # produce — "no risks found" is exactly what a reader wants to believe.
            # It is a failure, and it is named as one.
            breakdown = Counter(f.reason.value for f in run.failures)
            logger.error(
                "job %s: all %s chunks failed (%s)",
                job.job_id,
                len(chunks),
                dict(breakdown),
            )
            first = run.failures[0].user_message if run.failures else ""
            job.fail(
                f"None of the {len(chunks)} sections of this document could be "
                f"analyzed. {first}".strip()
            )
            return

        job.succeed(_build_result(parsed, chunks, run, job.document))
        logger.info(
            "job %s complete: %s sections analyzed, %s skipped",
            job.job_id,
            len(run.analyzed),
            len(run.failures),
        )
    except asyncio.CancelledError:
        # Shutdown, not a document problem. Mark it so a poll during drain reports
        # something truthful, then let the cancellation propagate.
        job.fail("The analysis was interrupted. Upload the document again.")
        raise
    except Exception:  # noqa: BLE001 - a background task has nowhere to propagate
        logger.exception("job %s failed unexpectedly", job.job_id)
        job.fail(
            "Something went wrong while analyzing this document. Try again, and if "
            "it keeps happening the document may be in an unsupported format."
        )


@router.post(
    "/analyze", status_code=status.HTTP_202_ACCEPTED, response_model=JobState
)
async def start_analysis(
    request: Request, file: UploadFile = File(...)
) -> JobState:
    """Accept a PDF, extract and chunk it, and start the analysis.

    Returns 202 with a job id to poll. The synchronous part is bounded work —
    everything that can tell the user their file is unusable happens before the
    response.
    """
    client_ok = _require_client(request)
    assert client_ok is not None  # narrows for readers; _require_client raises

    filename = _safe_filename(file.filename)
    data = await _read_upload(file)

    try:
        parsed = await parse_pdf(data, filename=filename)
    except ParserError as exc:
        # user_message is written for a reader; detail is for us. CLAUDE.md forbids
        # returning a raw traceback, and this is where that rule is kept.
        logger.info("parse rejected %s: %s", filename, exc.detail)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=exc.user_message
        ) from exc

    chunks = await chunk_document_async(parsed)

    if not chunks:
        # The parser found text but chunking produced nothing — whitespace-only
        # pages. Distinct from the scanned-PDF case, which the parser rejects.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No readable text could be found in that PDF.",
        )

    if len(chunks) > MAX_CHUNKS_PER_DOCUMENT:
        # Refused before any API call, not partway through one. A limit enforced
        # after spending is not a limit.
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"That document is too long to analyze in one pass "
            f"({parsed.page_count} pages). Upload up to roughly 300 pages at a time.",
        )

    document = DocumentMeta(
        filename=filename,
        size_bytes=len(data),
        page_count=parsed.page_count,
        pages_with_text=parsed.pages_with_text,
        extraction_method=parsed.extraction_method,
        chunk_count=len(chunks),
    )
    job = request.app.state.jobs.create(document, len(chunks))

    task = asyncio.create_task(_run_analysis(request, job, parsed, chunks))
    # asyncio holds only a weak reference to a running task, so a task nobody keeps
    # can be garbage collected mid-flight. Hold it until it finishes.
    request.app.state.background_tasks.add(task)
    task.add_done_callback(request.app.state.background_tasks.discard)

    logger.info(
        "job %s accepted: %s (%s pages, %s chunks, method=%s)",
        job.job_id,
        filename,
        parsed.page_count,
        len(chunks),
        parsed.extraction_method.value,
    )
    return job.to_state()


@router.get("/analyze/{job_id}", response_model=JobState)
async def get_analysis(request: Request, job_id: str) -> JobState:
    """Poll one analysis.

    Unknown and expired ids are the same 404 on purpose — from the client's side
    they call for the same action, and distinguishing them would leak which ids
    once existed.
    """
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That analysis is no longer available. Upload the document again.",
        )
    return job.to_state()
