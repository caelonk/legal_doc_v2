"""In-memory store for in-flight and recently finished analysis jobs.

Why a job at all, rather than one blocking POST that returns the analysis:

  - docs/ui-patterns.md requires determinate progress ("Analyzing 4 of 11
    sections"), and `analyzer.analyze_document` already exposes the `on_progress`
    callback that feeds it. A blocking request cannot report anything until it is
    finished, so that signal would be thrown away and rebuilt later.
  - A multi-chunk document takes tens of seconds. That sits right on the default
    idle timeout of most reverse proxies, which turns a working analysis into a
    504 the client cannot distinguish from a real failure.

Scope, stated plainly: this store lives in one process's memory. Jobs do not
survive a restart and are invisible to a second worker, so the API must run
single-worker until they move to Supabase — which is where document history is
already planned to live. That migration replaces this module; nothing else
imports the dict.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from config import JOB_RETENTION_SECONDS
from models.schemas import AnalysisResult, DocumentMeta, JobState, JobStatus


def _stage_message(status: JobStatus, completed: int, total: int) -> str:
    """The progress line the UI renders verbatim.

    Composed here rather than in the frontend so the count and the wording cannot
    drift apart, and so a status added later cannot silently render as a blank
    line.
    """
    if status is JobStatus.QUEUED:
        return "Waiting to start"
    if status is JobStatus.ANALYZING:
        # Singular reads badly as "Analyzing 1 of 1 sections" on short documents.
        noun = "section" if total == 1 else "sections"
        return f"Analyzing {min(completed + 1, total)} of {total} {noun}"
    if status is JobStatus.COMPILING:
        return "Compiling results"
    if status is JobStatus.COMPLETE:
        return "Analysis complete"
    return "Analysis failed"


@dataclass
class AnalysisJob:
    """One document's trip through the pipeline.

    Mutated in place from the event loop only — the progress callback and the
    route handlers all run there — so the plain field writes below need no lock.
    Do not update these from a worker thread without adding one.
    """

    job_id: str
    document: DocumentMeta
    total_chunks: int
    status: JobStatus = JobStatus.QUEUED
    completed_chunks: int = 0
    result: AnalysisResult | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None

    def record_progress(self, completed: int, total: int) -> None:
        """Callback target for `analyze_document(on_progress=...)`.

        Chunks settle out of order, so `completed` is a count and never an index.
        """
        self.completed_chunks = completed
        self.total_chunks = total

    def succeed(self, result: AnalysisResult) -> None:
        self.result = result
        self.completed_chunks = self.total_chunks
        self.status = JobStatus.COMPLETE
        self.finished_at = time.monotonic()

    def fail(self, message: str) -> None:
        """`message` is rendered to the user, so it must never carry a traceback."""
        self.error = message
        self.status = JobStatus.FAILED
        self.finished_at = time.monotonic()

    def to_state(self) -> JobState:
        return JobState(
            job_id=self.job_id,
            status=self.status,
            stage_message=_stage_message(
                self.status, self.completed_chunks, self.total_chunks
            ),
            completed_chunks=self.completed_chunks,
            total_chunks=self.total_chunks,
            document=self.document,
            result=self.result,
            error=self.error,
        )


class JobStore:
    """Bounded, TTL-evicting job registry.

    A finished job holds the whole result, including extracted page text, so
    without eviction a long-running server would accumulate every document it has
    ever seen. Sweeping on write keeps that bounded without a background task.
    """

    def __init__(self, retention_seconds: float = JOB_RETENTION_SECONDS) -> None:
        self._jobs: dict[str, AnalysisJob] = {}
        self._retention = retention_seconds

    def create(self, document: DocumentMeta, total_chunks: int) -> AnalysisJob:
        self._evict_expired()
        job = AnalysisJob(
            job_id=uuid.uuid4().hex, document=document, total_chunks=total_chunks
        )
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> AnalysisJob | None:
        self._evict_expired()
        return self._jobs.get(job_id)

    def _evict_expired(self) -> None:
        """Drop finished jobs past their retention window.

        Only FINISHED jobs are eligible. A slow analysis is not a stale one, and
        evicting a running job would strand its background task writing into an
        object no route can read.
        """
        if self._retention <= 0:
            return
        cutoff = time.monotonic() - self._retention
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at is not None and job.finished_at < cutoff
        ]
        for job_id in expired:
            del self._jobs[job_id]

    def __len__(self) -> int:
        return len(self._jobs)
