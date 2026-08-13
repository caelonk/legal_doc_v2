"""API and pipeline constants mandated by CLAUDE.md.

Single source of truth. Every value here is fixed by a rule in "Claude API Usage
Rules"; changing one means changing that rule too.

This module exists because these values were previously duplicated across
modules, and a model ID that lives in two places drifts — this project has
already had one stale model ID sitting in two spots. A migration should touch one
line here, not grep the tree.
"""

from __future__ import annotations

# Model selection ----------------------------------------------------------
# Sonnet 5 rejects non-default temperature/top_p/top_k with a 400. Do not add
# sampling parameters anywhere that uses ANALYSIS_MODEL.
ANALYSIS_MODEL = "claude-sonnet-5"
LIGHTWEIGHT_MODEL = "claude-haiku-4-5-20251001"

# Request shape ------------------------------------------------------------
# max_tokens is ONE ceiling covering thinking tokens AND response text.
#
# Measured against the live API on 2026-08-11 (Sonnet 5, adaptive thinking, effort
# low), output_tokens = thinking + JSON:
#   full 18-clause chunk (~2400 input tokens) -> 989 tokens, 25% of the ceiling
#   the same chunk at max_tokens=12000        -> 985 tokens, so it is not
#                                                budget-constrained here
#   sparse chunks (one clause, signature page, exhibit stub), 12 runs
#                                             -> 114-498 tokens, no truncation
# 4000 therefore carries roughly 4x headroom on realistic input.
#
# Truncation is still possible as a rare tail event and WAS observed twice in early
# live testing. It does not surface as stop_reason="max_tokens": the SDK validates
# the response while constructing it, so a cut-off payload raises ValidationError
# first. services/analyzer.py detects that case explicitly — see _is_truncated_json.
MAX_TOKENS_PER_CHUNK = 4000

# Budget for the single retry after a truncated chunk. Deliberately 3x rather than
# 2x: a truncation at 8000 tokens was observed during live testing, so doubling is
# not demonstrably enough, while measured demand on real chunks (~1000 tokens)
# leaves this with ample room. Only ever tried once — a chunk that truncates twice
# is reported as a skipped section rather than retried into an unbounded spend.
TRUNCATION_RETRY_MAX_TOKENS = 12000

# Set explicitly — never rely on the model default, which varies by model and
# changed between Sonnet 4.6 and Sonnet 5. Treat as read-only; callers pass it
# straight to the API.
THINKING_CONFIG: dict[str, str] = {"type": "adaptive"}

# Risk-flag identification is a judgment task where some reasoning reduces missed
# clauses; "low" keeps the spend modest.
EFFORT = "low"

# Document-type classification pre-pass ------------------------------------
# One cheap Haiku call classifies the document before the Sonnet chunks run, so
# every chunk knows what kind of document it is judging "missing" clauses against.
# The payload is two short fields.
CLASSIFICATION_MAX_TOKENS = 200

# Roughly 1700 tokens of opening text — enough to cover a title page plus the
# opening recitals, which is where the document type is actually stated.
CLASSIFICATION_SAMPLE_CHARS = 6000

# Classification runs without thinking — it is a labelling task, not a judgment
# one. Set explicitly rather than omitted, per the always-set-thinking rule in
# CLAUDE.md, so the intent is visible in the request and a future default change
# cannot alter behaviour silently.
#
# The three shapes below were checked against the live API on 2026-08-11 for
# claude-haiku-4-5-20251001. Do not "modernise" them to match the Sonnet path:
#   - {"type": "disabled"}          -> accepted (what we send)
#   - {"type": "adaptive"}          -> 400 "adaptive thinking is not supported
#                                      on this model"
#   - output_config={"effort": ...} -> 400 "This model does not support the
#                                      effort parameter."
CLASSIFICATION_THINKING: dict[str, str] = {"type": "disabled"}

# Document-level summary reduce pass ---------------------------------------
# One call AFTER the chunks settle, turning the per-section summaries into a
# single plain-English summary. Input is the summaries, not the document — the
# sections have already been read with page markers in place, and re-reading the
# raw text would mean one call carrying the whole document, which CLAUDE.md
# forbids outright.
#
# Runs on ANALYSIS_MODEL, not the lightweight one. This is the first paragraph a
# non-lawyer reads about their contract, which is not a labelling task; the input
# is a few hundred tokens, so the quality is nearly free.
SUMMARY_MAX_TOKENS = 1000

# Thinking off, and max_tokens dropped to match — the sanctioned pairing in
# CLAUDE.md, never one without the other. Synthesising prose from material that
# has already been analyzed is a writing task, not a judgment one; the judgment
# happened in the chunk calls, where thinking IS enabled.
SUMMARY_THINKING: dict[str, str] = {"type": "disabled"}

# Chunking -----------------------------------------------------------------
CHUNK_TOKENS = 3000
OVERLAP_TOKENS = 200

# HTTP layer ---------------------------------------------------------------
# Upload ceiling. Enforced by reading the stream incrementally rather than by
# trusting Content-Length, which a client controls. 15 MB is a long text-based
# contract; scanned PDFs blow past it, but those are rejected by the parser anyway
# for having no text layer.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

# Cost ceiling per document. Each chunk is one Sonnet call, so this is the only
# thing standing between a 900-page filing and an unbounded bill. Roughly 300-350
# pages of ordinary contract text.
MAX_CHUNKS_PER_DOCUMENT = 60

# Analyses allowed to run at once across the whole process. Each one internally
# fans out to DEFAULT_MAX_CONCURRENCY chunk calls, so the real ceiling on in-flight
# API requests is the product of the two.
MAX_CONCURRENT_ANALYSES = 2

# How long a finished job stays readable before eviction. Long enough for a user to
# reload the results tab, short enough that the in-memory store cannot grow without
# bound.
JOB_RETENTION_SECONDS = 60 * 60

# Document history ---------------------------------------------------------
# How long a stored analysis is kept. This number is USER-FACING: the upload
# disclosure tells the reader their document's text is deleted after this many
# days, and /api/health reports it so that sentence is interpolated rather than
# duplicated. Changing it here changes what the user is promised — there is no
# second place to update, and that is the point.
#
# Enforced by services/supabase.py::purge_expired, swept on write.
HISTORY_RETENTION_DAYS = 30

# How many history entries one list request returns. Summary columns only, so this
# is a UI pagination choice rather than a payload-size defence.
HISTORY_PAGE_SIZE = 25

# Browser origins allowed to call the API. The Vite dev server defaults to 5173;
# CRA to 3000. Deployment adds its real origin here — never "*", because these
# requests carry an uploaded document.
ALLOWED_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)
