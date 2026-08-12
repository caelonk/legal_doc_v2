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

# Chunking -----------------------------------------------------------------
CHUNK_TOKENS = 3000
OVERLAP_TOKENS = 200
