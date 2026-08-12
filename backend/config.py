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
# max_tokens is ONE ceiling covering thinking tokens AND response text. The JSON
# payload for a chunk runs ~400-900 tokens; the remainder is thinking headroom.
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

# NOTE ON `thinking` FOR THE CLASSIFICATION CALL
# CLAUDE.md says to always set `thinking` explicitly. That rule exists because the
# default varies by model and changed between Sonnet 4.6 and Sonnet 5. It does not
# extend to LIGHTWEIGHT_MODEL: Haiku 4.5 predates adaptive thinking, and on pre-4.6
# models omitting `thinking` unambiguously means "no thinking". So the classifier
# omits it deliberately.
#   - Do NOT send {"type": "adaptive"} here — that is a 4.6+ mode.
#   - {"type": "disabled"} may well be accepted, but it is unverified against the
#     live API for this model, and omission is definitively safe.
#   - Do NOT send output_config={"effort": ...} — effort errors on Haiku 4.5.

# Chunking -----------------------------------------------------------------
CHUNK_TOKENS = 3000
OVERLAP_TOKENS = 200
