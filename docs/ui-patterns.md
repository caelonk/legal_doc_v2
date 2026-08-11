# UI Patterns — Legal AI & Document Analysis

Reference document. Read before building `ResultsPanel`, `ClauseNavigator`, `RiskBadge`,
`UploadZone`, or any analysis-facing view.

`design-system.md` covers how it looks. This covers how it behaves — specifically the
patterns that make an AI legal tool trustworthy rather than merely attractive.

---

## 1. Provenance: the defining pattern

In legal AI, the single highest-value UI feature is the ability to check a claim against
the source. An unverifiable summary is worse than no summary, because it invites reliance
without recourse.

The stakes are not hypothetical. Damien Charlotin's AI Hallucination Cases Database
tracked 1,668 court cases worldwide involving AI-fabricated citations as of July 2026, up
from roughly 200 in mid-2025 — 653 of them involving practising lawyers. Sanctions have
reached five figures per attorney. Any tool in this category is designed against that
backdrop.

### MVP behavior (current schema)

Your schema gives you `page_reference: number | null`. Use it fully:

- Every risk flag and missing clause displays its page reference as a persistent,
  clickable affordance — `mono` styling, `accent` colored, e.g. `p. 12`.
- Clicking scrolls the left pane to that page's extracted text and applies a temporary
  highlight (`brand-subtle` background, fading after ~2s).
- When `page_reference` is `null`, render an explicit muted state: `Source not located`.
  **Do not hide the field and do not guess.** A visibly missing citation is honest; a
  silently absent one looks like the claim was verified when it was not. This is the UI
  counterpart to the existing rule "Do NOT hallucinate page numbers."
- `ClauseNavigator` is the aggregate view of this: a jump list of every flagged location,
  ordered by document position, with severity color + icon per entry.

### V2 consideration (requires schema change — ask first)

`CLAUDE.md` requires asking before changing the JSON schema, so treat this as a proposal,
not a directive. The stronger pattern is character-level provenance: have the analyzer
return the exact quoted span it based each flag on, plus its character offsets in the
chunk.

```
"source_quote": "string — verbatim text the flag is based on",
"source_offset": { "start": number, "end": number } | null
```

That upgrade unlocks: exact-text highlighting rather than page-level, and a verification
state per flag — `verified` (span matched in source text), `paraphrase` (semantically
derived), `unverified` (no matching span found). Render those three as distinct visual
states so a failed match surfaces as "unverified" rather than as confident-looking text.

Cost: a larger prompt contract and post-hoc string matching in `analyzer.py`. Worth it
after MVP, not during.

---

## 2. Presenting AI output

- **Never render a bare conclusion.** Every claim carries its explanation and its source
  affordance in the same visual unit. The explanation field in your schema exists for
  this — surface it, don't truncate it behind a tooltip.
- **Separate what the model found from what the model inferred.** Risk flags are grounded
  in text that exists. Missing clauses are inferences about absence — a fundamentally
  weaker claim. Give them separate sections with distinct framing; do not interleave them
  in one list.
- **No false precision.** Do not display numeric confidence percentages unless the number
  is genuinely calibrated. `HIGH | MEDIUM | LOW` from your schema is honest ordinal
  information; `87% confident` invented from nothing is not.
- **Human-in-the-loop affordances.** Even in MVP, each flag should be dismissible or
  markable as reviewed in local state. The mental model should be "the tool proposes, the
  reader decides," not "the tool decided."

---

## 3. Risk display

`RiskBadge.jsx` contract:

- Renders color + icon + text label, always. No prop can suppress the label.
- Icons: `HIGH` → `AlertTriangle`, `MEDIUM` → `AlertCircle`, `LOW` → `Info`. Consistent
  across badges, navigator entries, and table rows.
- Sort risk flags by severity descending, then by page order. The reviewer's first
  question is always "what's the worst thing in here."
- Do not aggregate severity into a single overall "document score." A composite number
  invites reliance on a figure nothing in the pipeline actually validates. Show counts
  instead: `3 high · 5 medium · 2 low`.

---

## 4. States

`CLAUDE.md` already requires loading, error, and empty states for every API call. The
specifics that matter here:

**Upload (`UploadZone`)**
- Drag-and-drop plus a visible file-picker button. Drag-only is an accessibility failure.
- Show filename, size, and page count once parsed, before analysis begins.
- Reject non-PDFs at the client with a specific message naming the accepted formats.
- Never lose the uploaded file on a downstream error.

**Processing**
- Analysis is chunked and slow. Show stage, not just motion: `Extracting text` →
  `Analyzing 4 of 11 sections` → `Compiling results`. A determinate count is available to
  you because you control the chunker — use it.
- Skeleton layout matching the final results shape, not a centered spinner.
- If chunks are skipped due to malformed JSON (per the existing error handling rule),
  disclose it: `2 sections could not be analyzed`. Silent partial results are a
  correctness problem disguised as a UI problem.

**Empty**
- Pre-upload: state what the tool does, what file types it accepts, and one clear action.
  An empty screen is an invitation to act, not a blank panel.
- Zero risk flags found: say so explicitly and positively — `No high-risk clauses
  identified in this document` — followed immediately by the verification reminder. A
  clean result is the most dangerous moment for over-reliance.

**Error**
- Plain language, name the cause, offer the next action. "This PDF appears to be a scanned
  image with no extractable text. Try a text-based PDF." Not "Parse error 422."

---

## 5. Ethics and framing

Not optional, and cheap to implement.

- **Persistent disclosure** on every analysis view: *AI-generated analysis. Verify against
  the source document. This is not legal advice.* Place it in the results panel header
  where it's read, not in a footer. It may be collapsible but not permanently dismissible.
- **Never phrase output as advice or conclusion.** The tool identifies and flags; it does
  not recommend, approve, or advise. Copy audit: "This clause may expose you to unlimited
  liability" is acceptable framing; "You should not sign this" is not — that edges toward
  unauthorized practice of law.
- **Confidentiality signal near upload.** State plainly what happens to the document:
  processed via the Anthropic API, stored in Supabase, deletable by the user. Trust copy
  belongs at the moment of hesitation — beside the upload control — not buried in a
  privacy page.
- ABA Formal Opinion 512 (July 2024) frames the professional-responsibility backdrop:
  competence, confidentiality, and supervision duties all apply when lawyers use
  generative AI. It binds the lawyer, not your app — but a tool that makes those duties
  easy to discharge is the one a legal reviewer respects. It is advisory until adopted by
  a state supreme court, and several states have issued their own guidance.

---

## 6. Reference products

Worth looking at when you need a concrete visual answer:

| Product | Borrow |
|---|---|
| Harvey | Citation "paper trail," review tables, restrained institutional palette |
| Ironclad | Obligations dashboards, structured metadata display |
| Juro | Modern contract editor feel, non-lawyer-friendly summaries |
| Spellbook | Clause-level flagging with plain-English explanations |
| Stripe | Data table design, documentation-grade clarity |
| Linear | Speed as a feature, spacing discipline, keyboard-first — not the dark skin |
| Mercury | Empty states used as onboarding, trustworthy financial restraint |
