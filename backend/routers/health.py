"""Liveness and readiness."""

from __future__ import annotations

from fastapi import APIRouter, Request

from config import ANALYSIS_MODEL
from models.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Report process health and whether analysis can actually run.

    Deliberately does NOT call the Anthropic API. A health check that costs money
    and adds a second of latency gets polled into a bill, and an upstream outage is
    not this process being unhealthy — it is reported by the analysis endpoint,
    where it can be acted on.
    """
    client = getattr(request.app.state, "claude_client", None)
    available = client is not None
    return HealthResponse(
        status="ok",
        analysis_available=available,
        analysis_model=ANALYSIS_MODEL,
        detail=None
        if available
        else "ANTHROPIC_API_KEY is not set — upload and text extraction work, "
        "but analysis will be refused.",
    )
