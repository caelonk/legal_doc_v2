"""Document history endpoints.

    GET    /api/documents/history        recent analyses, summary fields only
    GET    /api/documents/history/{id}   one full AnalysisResult
    DELETE /api/documents/history/{id}   remove one

Reads live here rather than in `documents.py` because they share no state with the
in-memory job store: a job is one run in this process, a history entry outlives the
process. Keeping them in separate modules stops the next person reaching for
`app.state.jobs` from a handler that has nothing to do with a job.

`GET /history/{id}` returns the same `AnalysisResult` shape a completed job
returns, so the frontend renders a stored analysis through exactly the same
components — and `ChunkFailure.detail` stays absent because what was stored had
already been through `documents._build_result`. That remains the only conversion
point.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from supabase import AsyncClient

from config import HISTORY_PAGE_SIZE
from models.schemas import AnalysisResult, HistoryPage
from services.supabase import (
    HistoryError,
    StaleAnalysisError,
    delete_analysis,
    get_analysis,
    list_analyses,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["history"])

_NOT_FOUND = "That saved analysis is no longer available."


def _require_store(request: Request) -> AsyncClient:
    """The history client, or a 503 explaining that it was never configured.

    A server without Supabase credentials analyzes documents perfectly well and
    simply stores nothing. Saying so is better than an empty list, which would
    read as "you have never analyzed anything".
    """
    client = getattr(request.app.state, "supabase", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document history is not configured on this server. Uploads and "
            "analysis are unaffected, but results are not saved.",
        )
    return client


def _as_http(exc: HistoryError) -> HTTPException:
    """Convert a history failure into a response, dropping `detail`.

    `detail` can carry the postgrest error body — SQL, column names, the project
    URL. It goes to the log and nowhere else, the same rule `ParserError` follows
    in documents.py.
    """
    code = (
        status.HTTP_410_GONE
        if isinstance(exc, StaleAnalysisError)
        else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    return HTTPException(status_code=code, detail=exc.user_message)


@router.get("/history", response_model=HistoryPage)
async def get_history(
    request: Request,
    limit: int = Query(
        default=HISTORY_PAGE_SIZE,
        ge=1,
        le=HISTORY_PAGE_SIZE,
        description="Capped at the server's page size — a client cannot ask for "
        "the whole table.",
    ),
) -> HistoryPage:
    """Most recent analyses first."""
    client = _require_store(request)
    try:
        entries = await list_analyses(client, limit)
    except HistoryError as exc:
        raise _as_http(exc) from exc
    return HistoryPage(entries=entries, limit=limit)


@router.get("/history/{analysis_id}", response_model=AnalysisResult)
async def get_history_entry(request: Request, analysis_id: str) -> AnalysisResult:
    """One stored analysis, in the same shape a completed job returns.

    Unknown ids, malformed ids and expired ids are all the same 404: from the
    caller's side they call for the same action, and distinguishing them would leak
    which ids once existed. Same reasoning as the job poll in documents.py.
    """
    client = _require_store(request)
    try:
        result = await get_analysis(client, analysis_id)
    except HistoryError as exc:
        raise _as_http(exc) from exc

    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return result


@router.delete("/history/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history_entry(request: Request, analysis_id: str) -> Response:
    """Remove one stored analysis.

    docs/ui-patterns.md §5 requires that a stored document be deletable by the
    user, and the upload disclosure says so. This is the endpoint that makes that
    sentence true; retention expiry in `purge_expired` is the other half.
    """
    client = _require_store(request)
    try:
        deleted = await delete_analysis(client, analysis_id)
    except HistoryError as exc:
        raise _as_http(exc) from exc

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
