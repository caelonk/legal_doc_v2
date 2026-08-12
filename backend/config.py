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

# Chunking -----------------------------------------------------------------
CHUNK_TOKENS = 3000
OVERLAP_TOKENS = 200
