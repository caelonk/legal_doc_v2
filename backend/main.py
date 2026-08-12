"""FastAPI application entry point.

Run from this directory (CLAUDE.md, Dev Commands):

    uvicorn main:app --reload --port 8000

Single worker only, for now. Analysis jobs live in this process's memory — see
services/jobs.py — so a second worker would answer polls for jobs it has never
heard of. `--workers` stays off the table until job state moves to Supabase.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import ALLOWED_ORIGINS, MAX_CONCURRENT_ANALYSES
from routers import documents, health, history
from services.jobs import JobStore
from services.supabase import close_client as close_history_client
from services.supabase import create_client as create_history_client

# .env sits at the project root, one level above this file. Resolved explicitly
# rather than by search so behaviour does not depend on the directory uvicorn was
# started from.
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(ENV_PATH if ENV_PATH.exists() else None)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Own the API client and the job registry for the process lifetime.

    One AsyncAnthropic for the whole app: it holds a connection pool, and building
    a client per request would discard that pool on every upload.

    A missing key is NOT fatal here. Startup succeeds, /api/health reports
    analysis as unavailable and says why, and the analysis endpoint returns a 503
    that names the cause. Refusing to boot would make the most common local-setup
    mistake present as a server that will not start, with the reason buried in
    whichever terminal scrolled past.

    Supabase gets the same treatment, one step weaker: without it, analysis still
    works end to end and only history is missing, so its absence is a warning
    rather than an error.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        app.state.claude_client = AsyncAnthropic(api_key=api_key)
    else:
        app.state.claude_client = None
        logger.error(
            "ANTHROPIC_API_KEY is not set — analysis endpoints will return 503. "
            "Copy .env.example to .env and fill it in."
        )

    # The service-role key, not the anon key: `analyses` has RLS on with no
    # policies, so the anon key can read nothing. See services/supabase.py.
    app.state.supabase = await create_history_client(
        os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    )
    if app.state.supabase is None:
        logger.warning(
            "Supabase is not configured — analyses will run normally but will not "
            "be saved to history."
        )

    app.state.jobs = JobStore()
    app.state.analysis_semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANALYSES)
    # Strong references to in-flight background tasks. asyncio keeps only weak
    # ones, so without this a running analysis can be garbage collected.
    app.state.background_tasks = set()

    try:
        yield
    finally:
        tasks = list(app.state.background_tasks)
        if tasks:
            logger.info("cancelling %s in-flight analysis task(s)", len(tasks))
            for task in tasks:
                task.cancel()
            # return_exceptions so one task's failure cannot abandon the others
            # mid-cleanup and leak the client below.
            await asyncio.gather(*tasks, return_exceptions=True)
        if app.state.claude_client is not None:
            await app.state.claude_client.close()
        await close_history_client(app.state.supabase)


app = FastAPI(
    title="Legal Document Analyzer",
    description="Parses legal documents and returns plain-English summaries, "
    "risk-flagged clauses, and missing-clause detection. AI-generated output — "
    "verify against the source. Not legal advice.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # Explicit origins, never "*": these requests carry an uploaded document.
    allow_origins=list(ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(history.router)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Replace FastAPI's field-path error dump with something a person can read.

    The default body is a list of pydantic error objects with `loc` paths into the
    request model. Useful in a terminal, meaningless in a UI, and it exposes
    internal field names. Details still go to the log.

    Worded for any route, not just the upload. It used to say "attach a PDF",
    which was true while /analyze was the only endpoint that could fail
    validation; the history routes can now reject a query parameter, and a message
    telling that caller to attach a PDF would send them somewhere useless.
    """
    logger.info("request validation failed for %s: %s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=422,
        content={
            "detail": "That request was not valid. Check the file or parameters "
            "and try again."
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last line of the no-raw-tracebacks rule.

    Anything that reaches here is a bug. The traceback goes to the log; the client
    gets one sentence, because an exception message can carry file paths, SQL, or
    an API error body.
    """
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our end. Please try again."},
    )
