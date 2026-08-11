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
  - You will be told which pages the section spans. Use only a page number from that
    range, or null.
  - If you cannot place a finding on a specific page, return null. Never guess, never
    interpolate, never infer a page number from context.
  - A null reference renders to the reader as "Source not located", which is honest. An
    invented page number is worse than no page number, because it looks verified.

Severity and importance are ordinal: HIGH, MEDIUM, or LOW. Do not attach numeric
confidence scores or an overall document rating.

If the section contains no risks or no obviously missing provisions, return empty lists.
Do not manufacture findings to fill space.
"""


def build_chunk_prompt(chunk: DocumentChunk, *, document_type_hint: str | None = None) -> str:
    """Build the user message for a single chunk.

    The page range is supplied by the PARSER, not the model, and is stated
    explicitly so the model has a bounded set of legal page values. This is what
    operationalizes the "never hallucinate page numbers" rule — an unbounded model
    guessing at pages is exactly the failure the rule exists to prevent.
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
            f"This section spans pages {pages[0]} to {pages[-1]}. "
            f"Use a page number in that range or null — nothing else."
        )
    else:
        # A page inside the span contributed no text. Enumerating rather than
        # giving a range keeps the skipped page from being offered as citable.
        listed = ", ".join(str(p) for p in pages)
        page_scope = (
            f"This section draws on pages {listed} only. Use one of exactly those "
            f"page numbers, or null — nothing else. Pages in between are not part "
            f"of this section."
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
