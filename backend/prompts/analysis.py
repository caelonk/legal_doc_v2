"""Prompt templates for document analysis.

Every prompt string in the project lives here. Service functions import from this
module and never inline prompt text.

Scope note: these prompts carry SEMANTICS only — register, length, and the
identify-don't-advise boundary. They deliberately do NOT restate the JSON schema.
Structured outputs (`output_format=ChunkAnalysis`) constrains the shape API-side,
and a prose copy of the schema here would drift from the Pydantic definition and
silently start contradicting it.
"""

from __future__ import annotations

from models.schemas import DocumentChunk

ANALYSIS_SYSTEM_PROMPT = """\
You analyze sections of legal documents (contracts, NDAs, leases) for a reader who \
is not a lawyer.

Your job is to IDENTIFY and DESCRIBE. You never recommend, approve, or advise.
  Acceptable: "This clause may expose you to unlimited liability."
  Not acceptable: "You should not sign this." / "This contract is safe."
The second form edges toward the unauthorized practice of law. Stay on the first.

Write for a careful non-specialist:
  - The section summary runs 3-5 sentences.
  - Each risk explanation runs 1-2 sentences.
  - Use plain English. When a term of art is unavoidable, define it in the same breath.
  - Do not hedge into vagueness. "This clause has no cap on damages" beats "this clause
    may potentially raise some concerns."

Two kinds of finding, and they are not the same strength of claim:
  - A risk flag is grounded in text that is actually present in the section you were
    given. Quote-level fidelity matters: do not flag a risk the text does not support.
  - A missing clause is an inference about ABSENCE, which is a weaker claim. Only report
    a provision as missing when it would be standard for this kind of document. Absence
    from THIS section is not absence from the document — you are seeing one section, so
    be conservative here.

Page references:
  - The section text carries inline [page N] markers, inserted by the parser. Everything
    after a marker, up to the next one, came from that page.
  - A finding's page reference is the page named by the marker that PRECEDES the text the
    finding is based on. Scroll back from the clause to the nearest marker above it and
    use that number. Do not estimate from how far through the section the clause sits —
    the pages are not equal lengths, and a section can skip a page entirely.
  - Use only a number that appears in a marker in this section, or null.
  - If a finding draws on text spanning a marker, use the page where the operative
    language sits.
  - If you cannot place a finding on a specific page, return null. Never guess, never
    interpolate, never infer a page number from context.
  - A null reference renders to the reader as "Source not located", which is honest. An
    invented page number is worse than no page number, because it looks verified.

Severity and importance are ordinal: HIGH, MEDIUM, or LOW. Do not attach numeric
confidence scores or an overall document rating.

If the section contains no risks or no obviously missing provisions, return empty lists.
Do not manufacture findings to fill space.
"""


DOCUMENT_TYPE_SYSTEM_PROMPT = """\
You identify what kind of legal document a piece of text comes from.

Answer with a short noun phrase naming the document type — "NDA", "Commercial Lease", \
"Employment Contract", "Master Services Agreement", "Software Licence". Do not write a \
sentence, do not summarise the contents, and do not comment on the terms.

Your confidence must reflect what the text actually shows:
  - HIGH: the text names the document type, or the clauses are unmistakable for one type.
  - MEDIUM: the clauses strongly suggest a type without naming it.
  - LOW: you are extrapolating. Use LOW for a cover page, a table of contents, a
    signature block, boilerplate that would appear in any agreement, or text too short
    to tell. Return an empty document_type with LOW.

LOW is a useful answer, not a failure. This label is applied to every section of the \
document, so a confident wrong guess is worse than admitting the text does not say. \
When torn between two types, pick the likelier one and mark MEDIUM — do not invent a \
hybrid.
"""


def build_classification_prompt(sample: str) -> str:
    """User message for the document-type pre-pass.

    The sample is the opening of the document, where the type is usually stated
    outright ("THIS LEASE AGREEMENT is made...").
    """
    return (
        "Identify the document type from the opening of this document.\n\n"
        "<document_opening>\n"
        f"{sample}\n"
        "</document_opening>"
    )


def build_chunk_prompt(chunk: DocumentChunk, *, document_type_hint: str | None = None) -> str:
    """Build the user message for a single chunk.

    Page attribution comes from the PARSER, never the model, and reaches the model
    two ways: as the bounded set of legal values stated here, and as [page N]
    markers inside the chunk text itself (see chunker._to_chunk).

    Both are needed. The bounded set alone was tried and is not enough — the model
    obeys the range and then picks within it by position, because unmarked text
    offers nothing better. Measured on a 6-page lease, that put 11 of 13 citations
    on the wrong page, all of them inside the permitted range and so invisible to
    any range check. The markers give the model something to read instead of
    something to estimate; the stated range still bounds what it can say.
    """
    pages = chunk.page_numbers

    if not pages:
        page_scope = (
            "The parser could not determine which pages this section spans. "
            "Return null for every page reference in this section."
        )
    elif len(pages) == 1:
        page_scope = (
            f"This section is on page {pages[0]}. "
            f"Use {pages[0]} or null for page references — nothing else."
        )
    elif chunk.has_contiguous_pages:
        page_scope = (
            f"This section spans pages {pages[0]} to {pages[-1]}, marked inline as "
            f"[page N]. Attribute each finding to the marker directly above the text "
            f"it comes from. Use a page number in that range or null — nothing else."
        )
    else:
        # A page inside the span contributed no text. Enumerating rather than
        # giving a range keeps the skipped page from being offered as citable.
        listed = ", ".join(str(p) for p in pages)
        page_scope = (
            f"This section draws on pages {listed} only, marked inline as [page N]. "
            f"Attribute each finding to the marker directly above the text it comes "
            f"from. Use one of exactly those page numbers, or null — nothing else. "
            f"Pages in between are not part of this section."
        )

    hint = (
        f"\nEarlier sections of this document appeared to be a {document_type_hint}.\n"
        if document_type_hint
        else ""
    )

    return (
        f"{page_scope}\n{hint}\n"
        "Analyze the following section of the document.\n\n"
        "<section>\n"
        f"{chunk.text}\n"
        "</section>"
    )
