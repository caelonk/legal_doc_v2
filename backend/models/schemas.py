"""Pydantic models for the document analysis pipeline.

These models are the single source of truth for the analyzer's output contract.
`ChunkAnalysis` is passed directly to the Claude API via structured outputs:

    response = client.messages.parse(..., output_format=ChunkAnalysis)
    result = response.parsed_output          # a validated ChunkAnalysis

The SDK compiles the model to a JSON schema the API constrains generation to
satisfy, so one definition drives the API contract, the response validation, and
FastAPI serialisation. Do not restate this schema as prose in a prompt template.

Changing any field here changes the output schema documented in CLAUDE.md, which
per project rules requires asking first.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class RiskLevel(str, Enum):
    """Ordinal risk level, shared by risk-flag `severity` and missing-clause
    `importance`.

    Deliberately ordinal rather than numeric: the analyzer never emits confidence
    percentages or an aggregate document score (see docs/ui-patterns.md section 3).
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @property
    def rank(self) -> int:
        """Sort key for severity-descending order.

        Never sort these values alphabetically — that yields HIGH, LOW, MEDIUM and
        silently mis-orders the risk list that ResultsPanel and ClauseNavigator
        render. Sort on `.rank` instead.
        """
        return _RISK_LEVEL_RANK[self]


_RISK_LEVEL_RANK: dict[RiskLevel, int] = {
    RiskLevel.HIGH: 3,
    RiskLevel.MEDIUM: 2,
    RiskLevel.LOW: 1,
}


class RiskFlag(BaseModel):
    """A risk grounded in text that exists in the document.

    Distinct from MissingClause, which is an inference about absence. The two are
    rendered in separate sections and never interleaved.
    """

    # extra="forbid" emits `additionalProperties: false`, which structured outputs
    # requires on every object. Removing it breaks schema compilation.
    model_config = ConfigDict(extra="forbid")

    clause_type: str = Field(
        description="The kind of clause this flag concerns, e.g. 'Limitation of Liability', "
        "'Indemnification', 'Auto-renewal'."
    )
    severity: RiskLevel = Field(
        description="How serious the risk is. HIGH, MEDIUM, or LOW."
    )
    explanation: str = Field(
        description="Plain-English explanation of the risk, 1-2 sentences. Identify and "
        "describe the exposure; never recommend, approve, or advise. 'This clause may "
        "expose you to unlimited liability' is acceptable; 'you should not sign this' is not."
    )
    # MUST stay `int | None` with NO default. Adding `= None` would make the field
    # optional in the generated schema, letting the model omit it entirely — which
    # reopens the silent-omission hole that .claude/rules/ai-output.md forbids. A
    # required nullable field forces an explicit null, which the UI renders as
    # "Source not located".
    page_reference: int | None = Field(
        description="1-indexed page number this clause appears on, or null if it is not "
        "known. Return null rather than guessing — an omitted or invented citation is "
        "worse than an absent one."
    )


class MissingClause(BaseModel):
    """A standard provision the analyzer did not find.

    This is an inference about absence — a weaker claim than a RiskFlag, and framed
    separately in the UI for that reason.
    """

    model_config = ConfigDict(extra="forbid")

    clause_name: str = Field(
        description="The standard provision that appears to be absent, e.g. "
        "'Governing Law', 'Confidentiality', 'Termination for Convenience'."
    )
    importance: RiskLevel = Field(
        description="How consequential the absence is for this document type."
    )
    explanation: str = Field(
        description="Plain-English explanation of why this provision is normally present "
        "and what its absence means. Identify; do not advise."
    )


class ChunkAnalysis(BaseModel):
    """The contract every Claude analysis call must satisfy.

    This is the per-chunk result. Merging chunk results into one document-level
    view (deduplicating flags across the 200-token overlap, reconciling
    `document_type`, counting chunks that failed) is a separate concern and is not
    modelled here yet.
    """

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(
        description="Plain-English summary of this section, 3-5 sentences, written for a "
        "non-lawyer."
    )
    risk_flags: list[RiskFlag] = Field(
        description="Risks grounded in text present in this section. Empty list if none."
    )
    missing_clauses: list[MissingClause] = Field(
        description="Standard provisions that appear to be absent. Empty list if none."
    )
    document_type: str = Field(
        description="The kind of document this appears to be, e.g. 'NDA', 'Lease', "
        "'Employment Contract'."
    )


# --------------------------------------------------------------------------
# Pipeline models. These are internal — they are NOT part of the analyzer's
# API output contract and are not sent to Claude.
# --------------------------------------------------------------------------


class DocumentChunk(BaseModel):
    """One token-aware slice of parser-extracted text, produced by chunker.py."""

    model_config = ConfigDict(extra="forbid")

    index: int
    text: str
    # Supplied by the parser, never by the model. These bound what the analyzer is
    # allowed to report as a page_reference — see prompts/analysis.py.
    start_page: int | None = None
    end_page: int | None = None


class ChunkFailureReason(str, Enum):
    """Why a chunk produced no analysis.

    TRUNCATED and INVALID_OUTPUT are deliberately distinct: truncation is a token
    budget problem with a systematic cause, while invalid output is a model
    problem. Collapsing them hides a budget misconfiguration as random noise.
    """

    TRUNCATED = "TRUNCATED"
    REFUSED = "REFUSED"
    INVALID_OUTPUT = "INVALID_OUTPUT"
    RATE_LIMITED = "RATE_LIMITED"
    CONNECTION_ERROR = "CONNECTION_ERROR"
    API_ERROR = "API_ERROR"


class ChunkFailure(BaseModel):
    """A chunk that could not be analyzed.

    Never discard these. `.claude/rules/ai-output.md` requires the UI to disclose
    skipped sections ("2 sections could not be analyzed") — silent partial results
    are a correctness failure, not a cosmetic one.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_index: int
    reason: ChunkFailureReason
    user_message: str = Field(
        description="Plain-language, safe to render in the UI. Never contains a "
        "traceback, stack frame, or raw API error body."
    )
    detail: str = Field(
        description="Diagnostic text for logs only. Do NOT return this to the frontend."
    )


class AnalyzedChunk(BaseModel):
    """A successful chunk result, tagged with its position in the document."""

    model_config = ConfigDict(extra="forbid")

    chunk_index: int
    analysis: ChunkAnalysis


class AnalysisRun(BaseModel):
    """The raw outcome of one analysis pass over a document's chunks.

    This is NOT the merged document-level view. Deduplicating flags across the
    200-token chunk overlap and reconciling `document_type` across chunks are
    separate concerns, not yet modelled.
    """

    model_config = ConfigDict(extra="forbid")

    analyzed: list[AnalyzedChunk]
    failures: list[ChunkFailure]

    @property
    def total_chunks(self) -> int:
        return len(self.analyzed) + len(self.failures)

    @property
    def is_partial(self) -> bool:
        """True when the UI must disclose that some sections were skipped."""
        return bool(self.failures)
