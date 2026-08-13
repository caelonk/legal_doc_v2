"""HTTP layer: upload, analysis job lifecycle, and error surfacing.

No network. The Anthropic client on app.state is replaced with the same FakeClient
the pipeline tests use, and ANTHROPIC_API_KEY is removed from the environment
before the app starts, so a real client is never constructed and a real key is
never read.

Run: python backend/tests/test_api.py
"""

from __future__ import annotations

import json
import sys
import time

import anthropic
import httpx

from _harness import (
    Results,
    make_image_only_pdf,
    make_text_pdf,
    scrub_live_credentials,
)

import main
from models.schemas import (
    AnalysisResult,
    AnalysisRun,
    ChunkAnalysis,
    DocumentMeta,
    ExtractionMethod,
    JobStatus,
    RiskFlag,
    RiskLevel,
)
from routers import documents
from services.aggregator import aggregate_run
from services.jobs import JobStore, _stage_message
from test_pipeline import SUMMARY, FakeClient, stub_response

from fastapi.testclient import TestClient

# Belt and braces: main.py calls load_dotenv() at import, which puts the real
# credentials into the environment. Drop them before any app starts, so no test can
# construct a live Anthropic client or write a row into the real Supabase project,
# whatever else goes wrong below. Must run after `import main`, not before.
scrub_live_credentials()

CLAUSE = (
    "LIMITATION OF LIABILITY. In no event shall the Disclosing Party be liable for "
    "indirect, incidental or consequential damages, provided that liability for "
    "breach of confidentiality shall be unlimited and uncapped in all respects. "
)

GOOD = ChunkAnalysis(
    summary="This section limits liability.",
    risk_flags=[
        RiskFlag(
            clause_type="Limitation of Liability",
            severity=RiskLevel.HIGH,
            explanation="Liability for confidentiality breaches is uncapped.",
            page_reference=1,
        )
    ],
    missing_clauses=[],
    document_type="NDA",
)

LEAK_MARKER = "internal-diagnostic-marker-do-not-leak"


def empty_aggregate():
    """The aggregate of a run with nothing in it — built, not hand-written, so it
    cannot drift from what the real pipeline produces."""
    return aggregate_run(AnalysisRun(analyzed=[], failures=[]))


def api_error() -> anthropic.APIStatusError:
    """An APIStatusError whose message is easy to spot if it escapes to the wire."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(500, request=request)
    return anthropic.APIStatusError(LEAK_MARKER, response=response, body=None)


def one_page_pdf() -> bytes:
    return make_text_pdf([CLAUSE * 6])


# Each page is ~5700 characters (~1630 estimated tokens) of one unbroken
# paragraph, so the packer emits one chunk per page: a second page would push the
# chunk past the 3000-token ceiling. Asserted below rather than assumed — if the
# chunker's packing changes, the test should say so plainly instead of failing on
# an exhausted response script.
MULTI_CHUNK_PAGES = 3


def multi_chunk_pdf() -> bytes:
    """Long enough to split into MULTI_CHUNK_PAGES chunks.

    25 repetitions is near the most a generated page holds at this font size;
    _harness raises if that ever stops fitting.
    """
    page = CLAUSE * 25
    return make_text_pdf([page] * MULTI_CHUNK_PAGES)


def upload(client: TestClient, data: bytes, name: str = "contract.pdf"):
    return client.post(
        "/api/documents/analyze",
        files={"file": (name, data, "application/pdf")},
    )


def poll(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    """Poll until the job reaches a terminal status."""
    deadline = time.time() + timeout
    body: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/documents/analyze/{job_id}")
        body = response.json()
        if body["status"] in (JobStatus.COMPLETE.value, JobStatus.FAILED.value):
            return body
        time.sleep(0.02)
    return body


def make_client(chunk_script, summary=None) -> TestClient:
    """A TestClient whose app has a stubbed Anthropic client installed."""
    client = TestClient(main.app)
    client.__enter__()  # runs lifespan
    client.app.state.claude_client = FakeClient(chunk_script, summary=summary)
    return client


def main_tests() -> int:
    r = Results("api")

    # ---------------------------------------------------------------- health
    r.section("health")

    with TestClient(main.app) as client:
        response = client.get("/api/health")
        body = response.json()
        r.check("health returns 200", response.status_code == 200)
        r.check("status is ok", body["status"] == "ok")
        r.check(
            "analysis_available is false without a key",
            body["analysis_available"] is False,
        )
        r.check(
            "unavailable health explains why",
            "ANTHROPIC_API_KEY" in (body["detail"] or ""),
        )
        r.check("health names the analysis model", body["analysis_model"] == "claude-sonnet-5")

    # -------------------------------------------------- no key configured
    r.section("analysis unconfigured")

    with TestClient(main.app) as client:
        response = upload(client, one_page_pdf())
        r.check("upload returns 503 with no API key", response.status_code == 503)
        r.check(
            "503 names the cause",
            "not configured" in response.json()["detail"],
        )

    # ------------------------------------------------------- upload rejects
    r.section("upload rejection")

    client = make_client([])
    try:
        response = upload(client, b"this is plainly not a pdf", name="notes.txt")
        r.check("non-PDF returns 400", response.status_code == 400)
        detail = response.json()["detail"]
        r.check("non-PDF message names the accepted format", "PDF" in detail)
        r.check("non-PDF message is not a traceback", "Traceback" not in detail)

        response = upload(client, b"")
        r.check("empty file returns 400", response.status_code == 400)

        response = upload(client, make_image_only_pdf(2))
        r.check("scanned PDF returns 400", response.status_code == 400)
        r.check(
            "scanned message suggests OCR",
            "OCR" in response.json()["detail"],
        )

        original = documents.MAX_UPLOAD_BYTES
        documents.MAX_UPLOAD_BYTES = 1024
        try:
            response = upload(client, one_page_pdf())
            r.check("oversized upload returns 413", response.status_code == 413)
            r.check(
                "413 states the limit",
                "limit" in response.json()["detail"],
            )
        finally:
            documents.MAX_UPLOAD_BYTES = original

        original_chunks = documents.MAX_CHUNKS_PER_DOCUMENT
        documents.MAX_CHUNKS_PER_DOCUMENT = 1
        try:
            response = upload(client, multi_chunk_pdf())
            r.check("too many chunks returns 413", response.status_code == 413)
            r.check(
                "413 is raised before any API call",
                client.app.state.claude_client.messages.chunk_calls == 0,
            )
        finally:
            documents.MAX_CHUNKS_PER_DOCUMENT = original_chunks

        response = client.get("/api/documents/analyze/does-not-exist")
        r.check("unknown job id returns 404", response.status_code == 404)
    finally:
        client.__exit__(None, None, None)

    # ------------------------------------------------------------ happy path
    r.section("successful analysis")

    client = make_client([stub_response("end_turn", GOOD)])
    try:
        response = upload(client, one_page_pdf(), name="../../etc/nda.pdf")
        r.check("upload returns 202", response.status_code == 202)
        accepted = response.json()

        r.check("202 carries a job id", bool(accepted["job_id"]))
        r.check(
            "202 already carries document metadata",
            accepted["document"]["page_count"] == 1,
        )
        r.check(
            "filename is stripped of path components",
            accepted["document"]["filename"] == "nda.pdf",
        )
        r.check(
            "202 reports the size that was read",
            accepted["document"]["size_bytes"] > 0,
        )
        r.check("202 has no result yet", accepted["result"] is None)

        final = poll(client, accepted["job_id"])
        r.check("job completes", final["status"] == JobStatus.COMPLETE.value)
        r.check("stage message reads as complete", final["stage_message"] == "Analysis complete")
        r.check(
            "progress reaches the total",
            final["completed_chunks"] == final["total_chunks"],
        )

        result = final["result"]
        r.check("result has one section", len(result["sections"]) == 1)
        r.check("result has no skipped sections", result["skipped"] == [])
        r.check(
            "section carries the pages it came from",
            result["sections"][0]["pages"] == [1],
        )
        r.check(
            "risk flag survives to the wire",
            result["sections"][0]["analysis"]["risk_flags"][0]["severity"] == "HIGH",
        )
        r.check(
            "source page text is returned for provenance",
            len(result["pages"]) == 1 and "LIABILITY" in result["pages"][0]["text"],
        )
        r.check(
            "extraction method is disclosed",
            result["document"]["extraction_method"] in ("pdfplumber", "pymupdf"),
        )
        r.check(
            "the document-level summary reaches the wire",
            result["aggregate"]["summary"] == SUMMARY.summary,
            repr(result["aggregate"]["summary"]),
        )
        r.check(
            "the per-section summaries survive alongside it",
            bool(result["sections"][0]["analysis"]["summary"]),
            "the merged view never replaces the evidence behind it",
        )
    finally:
        client.__exit__(None, None, None)

    # A summary is a convenience laid on top of the findings. Losing an entire
    # analysis because the last, optional call failed would be absurd — and worse,
    # the route would report a completed analysis as a failed one.
    client = make_client(
        [stub_response("end_turn", GOOD)],
        summary=anthropic.APIStatusError(
            LEAK_MARKER,
            response=httpx.Response(
                500, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            ),
            body=None,
        ),
    )
    try:
        accepted = upload(client, one_page_pdf()).json()
        final = poll(client, accepted["job_id"])
        r.check(
            "a summary failure still completes the analysis",
            final["status"] == JobStatus.COMPLETE.value,
            final.get("error") or "",
        )
        r.check(
            "the findings are intact without a summary",
            len(final["result"]["aggregate"]["risk_flags"]) == 1,
        )
        r.check(
            "the missing summary is null, not an empty paragraph",
            final["result"]["aggregate"]["summary"] is None,
        )
        r.check(
            "the summary failure leaks no diagnostics to the wire",
            LEAK_MARKER not in json.dumps(final),
        )
    finally:
        client.__exit__(None, None, None)

    # -------------------------------------------------------- partial results
    r.section("partial results and diagnostic containment")

    # One scripted failure, the rest succeed. The fake dispatches in call order,
    # not chunk order, so which chunk fails is not fixed — only that exactly one
    # does, which is all this section is about.
    script = [api_error()] + [
        stub_response("end_turn", GOOD) for _ in range(MULTI_CHUNK_PAGES - 1)
    ]
    client = make_client(script)
    try:
        response = upload(client, multi_chunk_pdf())
        r.check("multi-chunk upload accepted", response.status_code == 202)
        accepted = response.json()
        r.check(
            "fixture chunks as expected",
            accepted["document"]["chunk_count"] == MULTI_CHUNK_PAGES,
            f"got {accepted['document']['chunk_count']}",
        )

        final = poll(client, accepted["job_id"])
        r.check(
            "partial run still completes", final["status"] == JobStatus.COMPLETE.value
        )
        result = final["result"]
        r.check(
            "surviving sections are analyzed",
            len(result["sections"]) == MULTI_CHUNK_PAGES - 1,
        )
        r.check("one section disclosed as skipped", len(result["skipped"]) == 1)
        r.check(
            "skipped section names a typed reason",
            result["skipped"][0]["reason"] == "API_ERROR",
        )
        r.check(
            "skipped section carries a plain-language message",
            "could not be analyzed" in result["skipped"][0]["message"],
        )
        r.check(
            "skipped section reports its pages",
            isinstance(result["skipped"][0]["pages"], list)
            and result["skipped"][0]["pages"],
        )
        r.check(
            "skipped section has no detail field",
            "detail" not in result["skipped"][0],
        )
        r.check(
            "raw diagnostics never reach the wire",
            LEAK_MARKER not in response.text and LEAK_MARKER not in str(final),
        )
    finally:
        client.__exit__(None, None, None)

    # ------------------------------------------------------- total failure
    r.section("total analysis failure")

    client = make_client([api_error()])
    try:
        accepted = upload(client, one_page_pdf()).json()
        final = poll(client, accepted["job_id"])
        r.check(
            "a run where every chunk failed is FAILED, not COMPLETE",
            final["status"] == JobStatus.FAILED.value,
        )
        r.check("failed job carries no result", final["result"] is None)
        r.check(
            "failure message says nothing was analyzed",
            "could be analyzed" in (final["error"] or ""),
        )
        r.check(
            "failure message carries no diagnostics",
            LEAK_MARKER not in (final["error"] or ""),
        )
    finally:
        client.__exit__(None, None, None)

    # ----------------------------------------------------------- stage text
    r.section("stage messages")

    r.check(
        "queued stage", _stage_message(JobStatus.QUEUED, 0, 4) == "Waiting to start"
    )
    r.check(
        "analyzing stage counts from one",
        _stage_message(JobStatus.ANALYZING, 0, 11) == "Analyzing 1 of 11 sections",
    )
    r.check(
        "analyzing stage tracks progress",
        _stage_message(JobStatus.ANALYZING, 3, 11) == "Analyzing 4 of 11 sections",
    )
    r.check(
        "analyzing stage never exceeds the total",
        _stage_message(JobStatus.ANALYZING, 11, 11) == "Analyzing 11 of 11 sections",
    )
    r.check(
        "single-section wording is singular",
        _stage_message(JobStatus.ANALYZING, 0, 1) == "Analyzing 1 of 1 section",
    )
    r.check(
        "compiling stage", _stage_message(JobStatus.COMPILING, 4, 4) == "Compiling results"
    )

    # ------------------------------------------------------------ job store
    r.section("job store")

    meta = DocumentMeta(
        filename="a.pdf",
        size_bytes=10,
        page_count=1,
        pages_with_text=1,
        extraction_method=ExtractionMethod.PDFPLUMBER,
        chunk_count=2,
    )

    store = JobStore(retention_seconds=1.0)
    job = store.create(meta, 2)
    r.check("created job is retrievable", store.get(job.job_id) is job)
    r.check("job ids are opaque", len(job.job_id) >= 32 and "-" not in job.job_id)

    job.record_progress(1, 2)
    r.check("progress is recorded", job.completed_chunks == 1)
    r.check(
        "running job with an old start is not evicted",
        (setattr(job, "created_at", time.monotonic() - 3600), store.get(job.job_id))[1]
        is job,
    )

    job.fail("nope")
    job.finished_at = time.monotonic() - 3600
    store.create(meta, 1)  # any write sweeps
    r.check("finished job past retention is evicted", store.get(job.job_id) is None)

    store2 = JobStore(retention_seconds=60.0)
    done = store2.create(meta, 1)
    done.succeed(
        AnalysisResult(
            document=meta,
            document_type_hint=None,
            aggregate=empty_aggregate(),
            pages=[],
            sections=[],
            skipped=[],
        )
    )
    state = done.to_state()
    r.check("succeeded job reports COMPLETE", state.status is JobStatus.COMPLETE)
    r.check(
        "succeeded job fills the progress count",
        state.completed_chunks == state.total_chunks,
    )
    r.check("succeeded job carries no error", state.error is None)

    # ------------------------------------------------------------- filenames
    r.section("filename handling")

    r.check(
        "posix path stripped",
        documents._safe_filename("/etc/passwd/lease.pdf") == "lease.pdf",
    )
    r.check(
        "windows path stripped",
        documents._safe_filename(r"C:\Users\x\lease.pdf") == "lease.pdf",
    )
    r.check("missing filename gets a default", documents._safe_filename(None) == "document.pdf")
    r.check("empty filename gets a default", documents._safe_filename("   ") == "document.pdf")
    r.check("filename length is bounded", len(documents._safe_filename("x" * 900)) == 255)

    return r.finish()


if __name__ == "__main__":
    sys.exit(main_tests())
