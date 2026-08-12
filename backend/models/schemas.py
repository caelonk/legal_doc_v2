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

from datetime import datetime
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
# Document-type classification. A separate, internal structured-output contract
# used by the cheap pre-pass — NOT part of the documented analyzer output schema
# in CLAUDE.md, and never rendered to the user.
# --------------------------------------------------------------------------


class Confidence(str, Enum):
    """How sure the classifier is.

    Ordinal, not numeric — same reasoning as RiskLevel. Kept as its own enum
    because "how confident is this guess" and "how severe is this risk" are
    different quantities that should not be interchangeable in a type signature.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DocumentTypeGuess(BaseModel):
    """Result of the document-type pre-pass.

    `confidence` exists so a weak guess can be discarded rather than propagated.
    A hint is applied to EVERY chunk, so a wrong one biases the whole run in a
    single direction — worse than the independent errors we would get with no
    hint at all. LOW is treated as "no answer".
    """

    model_config = ConfigDict(extra="forbid")

    document_type: str = Field(
        description="Short noun phrase, e.g. 'NDA', 'Commercial Lease', "
        "'Employment Contract'. Empty string if the sample is uninformative."
    )
    confidence: Confidence = Field(
        description="LOW when the sample is a cover page, table of contents, or "
        "otherwise does not identify the document type."
    )


# --------------------------------------------------------------------------
# Pipeline models. These are internal — they are NOT part of the analyzer's
# API output contract and are not sent to Claude.
# --------------------------------------------------------------------------


class ExtractionMethod(str, Enum):
    """Which library produced the text.

    Surfaced so a support conversation can distinguish "the PDF was awkward and
    we fell back" from "extraction was clean".
    """

    PDFPLUMBER = "pdfplumber"
    PYMUPDF = "pymupdf"


class PageText(BaseModel):
    """Text extracted from one page, with the page number the parser observed.

    This is the ONLY origin of page numbers in the system. The model never
    supplies one — see CLAUDE.md, "Do NOT hallucinate page numbers".
    """

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(description="1-indexed, matching what a reader sees.")
    text: str


class ParsedDocument(BaseModel):
    """The result of extracting text from an uploaded PDF."""

    model_config = ConfigDict(extra="forbid")

    filename: str
    pages: list[PageText]
    extraction_method: ExtractionMethod

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def total_characters(self) -> int:
        return sum(len(p.text) for p in self.pages)

    @property
    def pages_with_text(self) -> int:
        """Pages that yielded any non-whitespace text.

        A document where this is far below `page_count` is likely part-scanned —
        worth surfacing rather than silently analyzing the readable half.
        """
        return sum(1 for p in self.pages if p.text.strip())


class DocumentChunk(BaseModel):
    """One token-aware slice of parser-extracted text, produced by chunker.py."""

    model_config = ConfigDict(extra="forbid")

    index: int
    text: str
    # The EXACT pages that contributed text to this chunk, ascending and deduped.
    # Not a min/max range: a page inside the span may have no text layer (a scanned
    # exhibit, a full-page diagram), and offering it as a citable page would let the
    # model cite a page this chunk never saw. Supplied by the parser, never by the
    # model — see prompts/analysis.py.
    page_numbers: list[int] = Field(default_factory=list)
    token_estimate: int = 0

    @property
    def start_page(self) -> int | None:
        return self.page_numbers[0] if self.page_numbers else None

    @property
    def end_page(self) -> int | None:
        return self.page_numbers[-1] if self.page_numbers else None

    @property
    def has_contiguous_pages(self) -> bool:
        """False when a page inside the span contributed no text.

        Drives whether the prompt states a range or enumerates pages explicitly.
        """
        if len(self.page_numbers) < 2:
            return True
        first, last = self.page_numbers[0], self.page_numbers[-1]
        return last - first + 1 == len(self.page_numbers)


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

    Per-section and unmerged, by design. Deduplicating flags across the 200-token
    chunk overlap and reconciling `document_type` happen in
    services/aggregator.py, which consumes this — so the evidence and the merge
    stay separable, and a merge that gets something wrong can be checked against
    what the sections actually said.
    """

    model_config = ConfigDict(extra="forbid")

    analyzed: list[AnalyzedChunk]
    failures: list[ChunkFailure]
    # What the classification pre-pass concluded, or None when it was skipped or
    # not confident enough to use. Reported rather than discarded because it
    # conditioned every chunk's missing-clause judgments: a run whose findings look
    # odd is not diagnosable without knowing what the model thought it was reading.
    document_type_hint: str | None = None

    @property
    def total_chunks(self) -> int:
        return len(self.analyzed) + len(self.failures)

    @property
    def is_partial(self) -> bool:
        """True when the UI must disclose that some sections were skipped."""
        return bool(self.failures)


# --------------------------------------------------------------------------
# HTTP response models. What the frontend actually receives.
#
# Kept separate from the pipeline models above because the two have different
# audiences. The pipeline carries diagnostic text; the wire must not. Returning
# a pipeline model straight out of a route would serialise `ChunkFailure.detail`
# — raw API error bodies and pydantic tracebacks — into the browser, which
# CLAUDE.md's error-handling rules forbid. The conversion functions in
# routers/documents.py are the only bridge, so that leak has one place to happen
# and one place to prevent.
# --------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Liveness plus the one dependency that silently breaks everything.

    `analysis_available` is false when no ANTHROPIC_API_KEY was configured. Parsing
    and chunking still work in that state, so a plain "ok" would be true and
    useless — every upload would fail at the last step with no way to tell why from
    outside the process.
    """

    model_config = ConfigDict(extra="forbid")

    status: str
    analysis_available: bool
    analysis_model: str
    history_available: bool = Field(
        description="False when no Supabase credentials were configured. Analysis "
        "is unaffected; results simply are not stored."
    )
    history_retention_days: int = Field(
        description="How long a stored analysis is kept. Reported because the "
        "upload disclosure states this number to the user, and a promise about "
        "deleting confidential text must come from the value the server actually "
        "enforces rather than from a copy of it in the frontend."
    )
    detail: str | None = Field(
        default=None, description="Why analysis is unavailable, when it is."
    )


class JobStatus(str, Enum):
    """Lifecycle of one analysis request.

    The values map onto the processing stages docs/ui-patterns.md asks the UI to
    show ("Extracting text" -> "Analyzing 4 of 11 sections" -> "Compiling
    results"). Anything vaguer would force the frontend back to an opaque spinner.
    """

    QUEUED = "QUEUED"
    ANALYZING = "ANALYZING"
    COMPILING = "COMPILING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class SkippedSection(BaseModel):
    """A chunk that could not be analyzed, in the form the frontend receives.

    `ChunkFailure.detail` is deliberately absent — it carries raw API error bodies
    and validation tracebacks, which belong in logs only.

    `pages` is included so the disclosure can be specific ("pages 12-14 could not
    be analyzed") rather than an unlocatable count.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_index: int
    reason: ChunkFailureReason
    message: str = Field(description="Plain language, safe to render.")
    pages: list[int]


class SectionAnalysis(BaseModel):
    """One successfully analyzed chunk, tagged with the pages it came from."""

    model_config = ConfigDict(extra="forbid")

    chunk_index: int
    pages: list[int]
    analysis: ChunkAnalysis


class DocumentMeta(BaseModel):
    """What was uploaded and what extraction made of it.

    `pages_with_text` next to `page_count` is what lets the UI say "34 of 40 pages
    contained readable text" — a part-scanned document analyzed silently is the
    failure this exists to prevent.
    """

    model_config = ConfigDict(extra="forbid")

    filename: str
    size_bytes: int
    page_count: int
    pages_with_text: int
    extraction_method: ExtractionMethod
    chunk_count: int


class AggregatedRiskFlag(BaseModel):
    """One risk, after identical reports from overlapping sections are merged.

    `reported_by` keeps the provenance a merge would otherwise destroy: which
    sections raised this, so a reader can still trace a claim back to the text it
    came from.
    """

    model_config = ConfigDict(extra="forbid")

    clause_type: str
    severity: RiskLevel = Field(
        description="The HIGHEST severity any reporting section assigned. Sections "
        "that disagree are never averaged down — a risk one section called HIGH "
        "does not become MEDIUM because another was more relaxed."
    )
    explanation: str
    page_reference: int | None
    reported_by: list[int] = Field(description="Chunk indices that reported this, ascending.")
    severity_disagreement: bool = Field(
        default=False,
        description="True when reporting sections assigned different severities. "
        "Surfaced rather than hidden: it means the model was not consistent about "
        "the same clause.",
    )


class AggregatedMissingClause(BaseModel):
    """A standard provision reported absent, merged across sections.

    Still a per-section inference, not a document-level proof. A section that
    CONTAINS a provision simply does not mention it, so "3 of 4 sections reported
    this missing" is entirely consistent with it being present in the fourth.
    `reported_by` is therefore provenance, NOT a confidence score, and must not be
    presented as one.
    """

    model_config = ConfigDict(extra="forbid")

    clause_name: str
    importance: RiskLevel
    explanation: str
    reported_by: list[int]


class DocumentAggregate(BaseModel):
    """The merged, document-level view of an analysis.

    Added ALONGSIDE the per-section results rather than replacing them. A merge is
    an inference, and when an inference is wrong the raw view is the only recourse
    — so the evidence stays on the wire.
    """

    model_config = ConfigDict(extra="forbid")

    document_type: str | None = Field(
        description="Reconciled across sections by majority. Null when nothing was analyzed."
    )
    document_type_agreement: int = Field(
        description="How many analyzed sections reported the winning type."
    )
    sections_analyzed: int
    risk_flags: list[AggregatedRiskFlag]
    missing_clauses: list[AggregatedMissingClause]
    merged_duplicate_count: int = Field(
        description="Risk flags removed by merging. Disclosed so a suspiciously "
        "small finding count is explainable rather than mysterious."
    )
    contradicted_missing_clauses: list[str] = Field(
        description="Provisions a section reported missing while another section "
        "raised a risk flag about that same clause type — so the provision "
        "demonstrably exists somewhere in the document. Withheld from "
        "`missing_clauses` and named here, because dropping a claim silently is "
        "the thing this codebase does not do."
    )


class AnalysisResult(BaseModel):
    """The completed analysis payload.

    Carries BOTH views. `aggregate` is the merged document-level result — the one
    to render — and `sections` is the per-chunk evidence behind it, kept because a
    merge is an inference and the raw view is the only recourse when an inference
    is wrong.

    `pages` carries the extracted source text so the frontend can implement the
    provenance affordance — clicking "p. 12" scrolls a source pane and highlights
    it — without a second round trip. Provenance is the point of the product; it
    should not be one network failure away from unavailable.
    """

    model_config = ConfigDict(extra="forbid")

    document: DocumentMeta
    document_type_hint: str | None = Field(
        description="What the classification pre-pass concluded, or null if it was "
        "skipped or not confident. Exposed because it conditioned every section's "
        "missing-clause judgments, so a wrong hint should be visible, not buried."
    )
    aggregate: DocumentAggregate = Field(
        description="The merged document-level view. Derived from `sections`, which "
        "remain the evidence behind it."
    )
    pages: list[PageText]
    sections: list[SectionAnalysis]
    skipped: list[SkippedSection]

    @property
    def is_partial(self) -> bool:
        return bool(self.skipped)


class JobState(BaseModel):
    """Poll response: where an analysis has got to, and its result once done."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    stage_message: str = Field(
        description="Ready-to-render progress line, e.g. 'Analyzing 4 of 11 sections'."
    )
    completed_chunks: int
    total_chunks: int
    document: DocumentMeta = Field(
        description="Available from the first response — the UI shows filename and "
        "page count before analysis finishes."
    )
    result: AnalysisResult | None = Field(
        description="Populated only when status is COMPLETE."
    )
    error: str | None = Field(
        description="Plain-language failure reason when status is FAILED. Never a "
        "traceback."
    )


class HistoryEntry(BaseModel):
    """One stored analysis, as it appears in a list.

    Summary fields only — deliberately NOT the analysis. A history list showing
    twenty documents would otherwise ship twenty documents' worth of extracted
    contract text to render twenty filenames. The full result is a separate
    request, made when a reader actually opens one.

    Field names match the columns in `backend/sql/001_analyses.sql` so a row
    validates directly.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime
    filename: str
    page_count: int
    pages_with_text: int
    document_type: str | None = Field(
        description="Null when nothing in the document could be analyzed."
    )
    risk_flag_count: int
    missing_clause_count: int
    skipped_count: int = Field(
        description="Sections that could not be analyzed. Carried into the list so "
        "a partial analysis is identifiable before it is opened, not after."
    )


class HistoryPage(BaseModel):
    """A page of stored analyses.

    An object rather than a bare array: a top-level JSON array cannot grow a field
    later without breaking every client, and pagination is exactly the thing that
    grows one.
    """

    model_config = ConfigDict(extra="forbid")

    entries: list[HistoryEntry]
    limit: int = Field(description="The maximum this request could have returned.")
