"""Document history persistence.

Stores the ANALYSIS and the EXTRACTED TEXT of a document, never the uploaded PDF.
No storage bucket is involved. That is the smallest confidentiality surface that
still supports document history, and the upload disclosure in
`frontend/src/components/UploadZone.jsx` states it to the user — if that ever
changes, the copy changes in the same commit.

Table: `analyses`. The DDL is `backend/sql/001_analyses.sql`, applied by hand.

Credentials. This uses SUPABASE_SERVICE_ROLE_KEY, which BYPASSES row-level
security. It is a server-only secret: it must never be sent to the browser, put in
a Vite env var, or returned by an endpoint. `analyses` has RLS enabled with no
policies precisely so that the service role is the only thing that can read it —
the table holds the full text of confidential contracts.

Two different failure policies live in this module, and the difference is the
point:

  * `save_analysis` SWALLOWS every error. The result already exists in memory and
    is already on its way to the user; persistence is a side effect, and a
    database problem must never turn a completed analysis into a failed one.
  * Every read raises `HistoryError`. A list endpoint that returned `[]` because
    the database was unreachable would tell the user "you have no documents",
    which is the same species of lie as reporting "no risks found" for a document
    whose chunks all failed. Unavailable is not empty.

`import supabase` below resolves to the installed package, not to this module:
`backend/` is on the path, `backend/services/` is not, so the top-level name is
unambiguous. Do not add `backend/services` to sys.path.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import ValidationError
from supabase import AsyncClient, acreate_client

from config import HISTORY_RETENTION_DAYS
from models.schemas import AnalysisResult, HistoryEntry

logger = logging.getLogger(__name__)

TABLE = "analyses"

# The list view never selects `result` — that column holds an entire document's
# text, and pulling twenty of them to render twenty filenames would be the whole
# reason the summary columns exist.
_LIST_COLUMNS = (
    "id,created_at,filename,page_count,pages_with_text,document_type,"
    "risk_flag_count,missing_clause_count,skipped_count"
)


class HistoryError(Exception):
    """A history failure with a message that is safe to show the user.

    Same shape as `parser.ParserError`: route handlers surface `user_message` and
    log `detail`. A raw postgrest error body can carry the connection string and
    the SQL, so `detail` never crosses the wire.
    """

    def __init__(self, user_message: str, detail: str) -> None:
        super().__init__(detail)
        self.user_message = user_message
        self.detail = detail


class StaleAnalysisError(HistoryError):
    """A stored row that no longer validates against the current schema.

    Separated from a plain `HistoryError` so the route can answer 410 rather than
    503. The server is fine; that particular saved analysis is not, and telling the
    user "temporarily unavailable" about something that will never come back sends
    them away to retry forever.
    """


_UNAVAILABLE = (
    "Document history is temporarily unavailable. Your analysis itself is "
    "unaffected — try again shortly."
)


async def create_client(url: str | None, key: str | None) -> AsyncClient | None:
    """Build the history client, or None when it was never configured.

    Returns None rather than raising for the same reason `main.py` tolerates a
    missing ANTHROPIC_API_KEY: a local checkout without Supabase credentials
    should still upload and analyze documents, with the missing capability
    reported by /api/health instead of by a server that will not boot.
    """
    if not url or not key:
        return None
    try:
        return await acreate_client(url, key)
    except Exception:
        # Bad URL or malformed key. Log it once, at startup, and run without
        # history rather than taking the whole process down.
        logger.exception("could not create the Supabase client — history disabled")
        return None


async def close_client(client: AsyncClient | None) -> None:
    """Release the underlying HTTP pool at shutdown.

    `AsyncClient` itself has no close(); the pool belongs to its postgrest client,
    which does. Guarded because that internal shape is not part of the package's
    public API and a future version may move it.
    """
    if client is None:
        return
    try:
        await client.postgrest.aclose()
    except Exception:  # noqa: BLE001 - shutdown must not raise
        logger.warning("failed to close the Supabase client cleanly", exc_info=True)


def _coerce_id(analysis_id: str) -> str | None:
    """Validate an id before it reaches the database.

    A malformed uuid makes postgrest return an error, which would surface as "history
    unavailable" — a server-fault message for what is plainly a bad id. Rejecting it
    here keeps that case a 404.
    """
    try:
        return str(uuid.UUID(str(analysis_id)))
    except (ValueError, AttributeError, TypeError):
        return None


def _row(result: AnalysisResult) -> dict[str, Any]:
    """Project an AnalysisResult onto the table's columns.

    The summary columns are derived from `aggregate`, the merged document-level
    view, so a history list reports the same counts the results page shows rather
    than a second, differently-computed number.
    """
    document = result.document
    aggregate = result.aggregate
    return {
        "filename": document.filename,
        "size_bytes": document.size_bytes,
        "page_count": document.page_count,
        "pages_with_text": document.pages_with_text,
        "extraction_method": document.extraction_method.value,
        "chunk_count": document.chunk_count,
        "document_type": aggregate.document_type,
        "risk_flag_count": len(aggregate.risk_flags),
        "missing_clause_count": len(aggregate.missing_clauses),
        "skipped_count": len(result.skipped),
        # mode="json" so enums become their string values and the payload is
        # jsonb-serializable without a custom encoder.
        "result": result.model_dump(mode="json"),
    }


async def save_analysis(client: AsyncClient | None, result: AnalysisResult) -> str | None:
    """Persist one completed analysis. Returns its id, or None if it was not stored.

    NEVER RAISES. See the module docstring: the analysis has already succeeded by
    the time this is called, and losing it to a storage error would be a strictly
    worse outcome than losing the history row.
    """
    if client is None:
        return None

    # The INSERT goes first. This runs after the job is already reported COMPLETE,
    # so every round trip before the write is a window in which a reader who opens
    # their history sees the analysis they just ran missing from it. Retention
    # housekeeping is not worth widening that window — measured at ~1.1s from
    # COMPLETE to the row landing when the purge went first.
    try:
        response = await client.table(TABLE).insert(_row(result)).execute()
    except Exception:  # noqa: BLE001 - see docstring
        logger.exception(
            "could not save %s to history — the analysis itself is unaffected",
            result.document.filename,
        )
        return None

    rows = response.data or []
    if not rows:
        logger.warning("history insert returned no row for %s", result.document.filename)
        analysis_id = None
    else:
        analysis_id = str(rows[0].get("id", "")) or None
        logger.info("saved %s to history as %s", result.document.filename, analysis_id)

    # Sweeping on write keeps retention bounded without a background task or a
    # pg_cron dependency — the same approach, for the same reason, as
    # JobStore._evict_expired. In its own try: failing to delete old rows must not
    # be reported as failing to save the new one.
    try:
        await purge_expired(client)
    except Exception:  # noqa: BLE001 - best effort, never fatal
        logger.warning("history purge failed; the save itself succeeded", exc_info=True)

    return analysis_id


async def list_analyses(client: AsyncClient, limit: int) -> list[HistoryEntry]:
    """Most recent analyses first, summary columns only."""
    try:
        response = (
            await client.table(TABLE)
            .select(_LIST_COLUMNS)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - converted, not swallowed
        logger.exception("history list failed")
        raise HistoryError(_UNAVAILABLE, repr(exc)) from exc

    entries: list[HistoryEntry] = []
    for row in response.data or []:
        try:
            entries.append(HistoryEntry.model_validate(row))
        except ValidationError:
            # One unreadable row must not blank the whole list. Skipped and
            # logged, the same call the analyzer makes for one bad chunk.
            logger.warning("skipping malformed history row %s", row.get("id"))
    return entries


async def get_analysis(client: AsyncClient, analysis_id: str) -> AnalysisResult | None:
    """One stored analysis, or None if there is no such row."""
    valid_id = _coerce_id(analysis_id)
    if valid_id is None:
        return None

    try:
        response = (
            await client.table(TABLE)
            .select("result")
            .eq("id", valid_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("history fetch failed for %s", valid_id)
        raise HistoryError(_UNAVAILABLE, repr(exc)) from exc

    rows = response.data or []
    if not rows:
        return None

    try:
        return AnalysisResult.model_validate(rows[0]["result"])
    except (ValidationError, KeyError, TypeError) as exc:
        # Written by an older schema. Reported as a failure rather than as an
        # empty analysis, because "this document has no findings" is the one thing
        # this product must never say by accident.
        logger.exception("stored analysis %s no longer matches the schema", valid_id)
        raise StaleAnalysisError(
            "That saved analysis was produced by an older version and can no "
            "longer be displayed. Upload the document again.",
            repr(exc),
        ) from exc


async def delete_analysis(client: AsyncClient, analysis_id: str) -> bool:
    """Delete one stored analysis. True if a row was removed.

    Existence is checked with a select before the delete rather than inferred from
    what delete returns: whether postgrest echoes deleted rows depends on a
    return-representation default we do not control, and a successful delete
    reported as "not found" would send the user looking for a row that is gone.
    """
    valid_id = _coerce_id(analysis_id)
    if valid_id is None:
        return False

    try:
        existing = (
            await client.table(TABLE).select("id").eq("id", valid_id).limit(1).execute()
        )
        if not (existing.data or []):
            return False
        await client.table(TABLE).delete().eq("id", valid_id).execute()
    except Exception as exc:  # noqa: BLE001
        logger.exception("history delete failed for %s", valid_id)
        raise HistoryError(
            "That analysis could not be deleted right now. Try again shortly.",
            repr(exc),
        ) from exc

    logger.info("deleted history entry %s", valid_id)
    return True


async def purge_expired(client: AsyncClient) -> None:
    """Drop rows past the retention window.

    This is what makes the upload disclosure's "deleted automatically after N
    days" a fact rather than a promise, so it runs on every write. Retention comes
    from `config.HISTORY_RETENTION_DAYS`, which is the same value /api/health
    reports to the frontend for that sentence.
    """
    if HISTORY_RETENTION_DAYS <= 0:
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=HISTORY_RETENTION_DAYS)
    await client.table(TABLE).delete().lt("created_at", cutoff.isoformat()).execute()
