"""Liveness and readiness."""

from __future__ import annotations

from fastapi import APIRouter, Request

from config import ANALYSIS_MODEL, HISTORY_RETENTION_DAYS
from models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Report process health and whether analysis can actually run.

    Deliberately does NOT call the Anthropic API, and does not query Supabase
    either. A health check that costs money and adds a second of latency gets
    polled into a bill, and an upstream outage is not this process being unhealthy
    — it is reported by the endpoint that needs the dependency, where it can be
    acted on. Both flags below report CONFIGURATION, which is what a caller can
    actually do something about.

    `history_retention_days` is here because the upload disclosure states that
    number to the user. Serving it from the value the server enforces means the
    promise and the purge cannot drift apart.
    """
    client = getattr(request.app.state, "claude_client", None)
    available = client is not None
    return HealthResponse(
        status="ok",
        analysis_available=available,
        analysis_model=ANALYSIS_MODEL,
        history_available=getattr(request.app.state, "supabase", None) is not None,
        history_retention_days=HISTORY_RETENTION_DAYS,
        detail=None
        if available
        else "ANTHROPIC_API_KEY is not set — upload and text extraction work, "
        "but analysis will be refused.",
    )
