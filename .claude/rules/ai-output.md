---
paths:
  - "backend/services/analyzer.py"
  - "backend/prompts/*.py"
  - "backend/models/schemas.py"
  - "frontend/src/components/ResultsPanel.jsx"
  - "frontend/src/components/ClauseNavigator.jsx"
  - "frontend/src/components/RiskBadge.jsx"
  - "frontend/src/pages/Analysis.jsx"
---

# AI Output Rules

Full reference: `docs/ui-patterns.md`.

These files produce or display model output about a document a user may rely on. Treat
every claim as something the user must be able to check.

## Provenance
- Every risk flag and missing clause displays its `page_reference` as a clickable
  affordance that scrolls the source pane and highlights the target.
- `page_reference: null` renders as an explicit `Source not located` state. Do NOT hide
  the field and do NOT infer a page number — a visibly missing citation is honest, a
  silently absent one is misleading.
- Never render a conclusion without its `explanation` field in the same visual unit.

## Separation of claim types
- Risk flags (grounded in text that exists) and missing clauses (inferences about absence)
  are weaker and stronger claims respectively. Keep them in separate sections with
  distinct framing. Do not interleave them into one list.
- Skipped chunks must be disclosed in the UI (`2 sections could not be analyzed`).
  Silent partial results are a correctness failure.

## Presentation
- Sort risk flags by severity descending, then document position.
- No numeric confidence percentages — the ordinal HIGH/MEDIUM/LOW enum is the honest
  signal. No aggregate "document risk score."
- Show counts instead: `3 high · 5 medium · 2 low`.
- Each flag is dismissible or markable as reviewed in local state. The tool proposes; the
  reader decides.

## Framing and ethics
- Persistent, non-permanently-dismissible disclosure in the results header:
  *AI-generated analysis. Verify against the source document. This is not legal advice.*
- Prompts and UI copy identify and flag; they never recommend, approve, or advise.
  "This clause may expose you to unlimited liability" — acceptable.
  "You should not sign this" — not acceptable, edges toward unauthorized practice of law.
- Confidentiality note beside the upload control stating how the document is processed
  and stored.

## Prompt contract
- All prompt templates stay in `backend/prompts/analysis.py`.
- The JSON schema is enforced API-side by structured outputs (`output_format=ChunkAnalysis`),
  NOT by the system prompt. Prompts carry semantics only — register, length, the
  identify-don't-advise boundary. Never restate the schema as prose; a second copy drifts
  from the Pydantic model in `backend/models/schemas.py` and starts contradicting it.
- `page_reference` is a REQUIRED nullable field, so it cannot be omitted. The prompt
  instructs the model to return an explicit `null` rather than guess, and to use only a
  page number from the parser-supplied range for that chunk.
- Changing the output schema requires asking first (see CLAUDE.md). The V2 source-quote
  and verification-state proposal in `docs/ui-patterns.md` is a proposal, not a directive.
