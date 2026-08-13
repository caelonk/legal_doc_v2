# Legal Document Analyzer — Project Context

## Project Overview
A full-stack web application that parses legal documents (contracts, NDAs, leases) and
returns plain-English summaries, risk-flagged clauses, and missing clause detection.
Built as a portfolio project targeting legal tech, SaaS, and analytics roles.

## Tech Stack
- **Frontend:** React + Tailwind CSS + shadcn/ui
- **Backend:** FastAPI (Python)
- **LLM:** Anthropic Claude API (claude-sonnet-5 for analysis, claude-haiku-4-5-20251001 for lightweight tasks)
- **PDF Parsing:** pdfplumber (primary), PyMuPDF (fallback for layout-heavy docs)
- **Storage:** Supabase PostgreSQL for document history (analysis + extracted text).
  No file storage bucket — the uploaded PDF is never persisted.
- **Auth:** Supabase Auth (if user accounts are added in V2)

## Project Structure
```
legal-doc-analyzer/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Model IDs + request/pipeline constants (single source)
│   ├── routers/
│   │   ├── documents.py         # Upload and analysis endpoints
│   │   ├── history.py           # Stored analyses: list, fetch, delete
│   │   └── health.py
│   ├── services/
│   │   ├── parser.py            # PDF text extraction logic
│   │   ├── chunker.py           # Token-aware text chunking
│   │   ├── analyzer.py          # Claude API calls + prompt logic
│   │   ├── aggregator.py        # Per-section results -> one document-level view
│   │   ├── jobs.py              # In-memory analysis job store (see API Surface)
│   │   └── supabase.py          # Document history. Analysis + extracted text to
│   │                            # Postgres. NO PDF bytes, no storage bucket.
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   ├── prompts/
│   │   └── analysis.py          # All prompt templates (centralized)
│   ├── sql/
│   │   └── 001_analyses.sql     # Applied by hand in the Supabase SQL editor
│   └── tests/                   # Dependency-free suite; python backend/tests/run_all.py
├── frontend/
│   ├── tailwind.config.js       # Semantic tokens; src/globals.css holds the raw values
│   ├── src/
│   │   ├── components/
│   │   │   ├── UploadZone.jsx
│   │   │   ├── AnalysisView.jsx      # The finished view. Shared by a live job and a
│   │   │   │                         # stored one — same payload, one renderer.
│   │   │   ├── AnalysisProgress.jsx  # Renders stage_message verbatim from the API
│   │   │   ├── DocumentHeader.jsx    # Owns the page h1 — OUTSIDE the tabs, see note
│   │   │   ├── SourcePane.jsx        # Extracted text + the citation jump target
│   │   │   ├── ResultsPanel.jsx
│   │   │   ├── ClauseNavigator.jsx   # Jump list in DOCUMENT order, not severity
│   │   │   ├── PageReference.jsx     # The provenance affordance
│   │   │   ├── Skeleton.jsx          # Loading shapes matching the final layout
│   │   │   ├── Tabs.jsx              # Styled Radix Tabs wrapper
│   │   │   └── RiskBadge.jsx
│   │   ├── pages/
│   │   │   ├── Home.jsx
│   │   │   ├── Analysis.jsx
│   │   │   ├── History.jsx           # Saved analyses. Counts only — no findings text
│   │   │   └── StoredAnalysis.jsx    # One saved analysis, via AnalysisView
│   │   ├── hooks/
│   │   │   ├── useAnalysisJob.js     # Polls a job to a terminal state
│   │   │   ├── useMediaQuery.js      # Picks the split-pane vs tabbed layout
│   │   │   └── useReviewState.js     # Per-flag "reviewed", in memory by design
│   │   ├── lib/
│   │   │   └── severity.js           # Ordering + counts; see the rank note inside
│   │   ├── tests/                    # Vitest + jsdom; npm test. README states what
│   │   │                             # jsdom CANNOT check (target size, zoom, contrast)
│   │   └── api/
│   │       └── client.js        # Axios instance + API calls
├── docs/
│   ├── design-system.md         # Visual language: color, type, spacing, tokens
│   └── ui-patterns.md           # Legal-AI UX patterns: citations, risk, states
├── .claude/
│   └── rules/                   # Path-scoped rules (auto-load on matching files)
│       ├── ai-output.md         # AI output display + prompt contract rules
│       └── frontend-ui.md       # Token, shape, a11y rules for frontend/src
└── CLAUDE.md
```

## Core Features (MVP)
1. PDF upload → text extraction → chunked Claude analysis
2. Plain-English document summary
3. Risk flag scanner (severity: HIGH / MEDIUM / LOW)
4. Missing clause detector (checks for standard provisions)
5. Clause navigator sidebar (jump to flagged sections)

## Claude API Usage Rules
- ALWAYS use `claude-sonnet-5` for full document analysis
- Use `claude-haiku-4-5-20251001` only for lightweight tasks (e.g. quick clause classification)
- ALWAYS request structured JSON output — never free-form text from the analyzer
- ALWAYS use structured outputs to enforce it: `client.messages.parse(...)` with
  `output_format=ChunkAnalysis` from `backend/models/schemas.py`. That Pydantic model is the
  single source of truth for the contract, the validation, and the API-side constraint.
- The system prompt covers SEMANTICS the schema cannot express — sentence counts, plain-English
  register, the identify-don't-advise boundary. It must NOT restate the JSON schema as prose;
  the API enforces shape, and a second copy in the prompt will drift from the first.
- Structured outputs guarantee SHAPE, NOT TRUTH. `page_reference` is still governed by the
  "only if the parser provides it" rule below — a schema cannot tell a real page number from
  an invented one.
- ALWAYS check `stop_reason` before trusting `parsed_output`. `refusal` and `max_tokens` both
  bypass the schema guarantee and can yield non-conforming or truncated output.
- Every schema model sets `extra="forbid"` (structured outputs requires
  `additionalProperties: false` on every object), and `page_reference` stays `int | None` with
  NO default — a default makes the field optional and reopens the silent-omission hole that
  `.claude/rules/ai-output.md` forbids.
- Do NOT combine `output_config.format` with the Citations API — the pair returns a 400. Not
  reachable today (we send parser-extracted text, not document blocks); revisit only if V2
  moves to document-block input for native page citations.
- ALWAYS set `thinking` explicitly — never rely on the model default, which varies by model
  and changed between Sonnet 4.6 and Sonnet 5. Use `{"type": "adaptive"}` with
  `output_config: {"effort": "low"}` for analysis chunks: risk-flag identification is a
  judgment task where reasoning reduces missed clauses, and `low` keeps the spend modest.
- Set max_tokens to 4000 per analysis chunk. **max_tokens is a single ceiling covering
  thinking tokens AND response text together** — it is not an output-only budget. The JSON
  payload for one chunk runs ~400-900 tokens; the rest is thinking headroom. This is the
  "explicit reason" for exceeding the old 1500 ceiling — do not raise it further without a
  new one.
- A chunk that returns truncated JSON with `stop_reason: "max_tokens"` is a budget failure,
  not a malformed-JSON failure. Log the two cases separately — silently routing truncation
  into the skip-the-chunk path hides a systematic problem as random noise.
- To trade reasoning quality for a tight token budget, set `thinking: {"type": "disabled"}`
  and drop max_tokens back to 1500 — but change both together, never one alone.
- NEVER pass `temperature`, `top_p`, or `top_k` on `claude-sonnet-5` — a non-default value
  returns a 400. Omit them entirely; steer behavior through the system prompt instead.
  (They are still accepted on `claude-haiku-4-5-20251001`, but omit them there too so the
  two call sites stay consistent.)
- Do NOT reach for `temperature=0` to make analyzer output deterministic or better-formed.
  It never guaranteed identical outputs on any model, and it is not the lever for schema
  conformance — the enforced JSON schema and system prompt above are.
- Chunk documents at 3000 tokens with 200-token overlap to preserve clause context.
  `chunker._overlap_tail` carries whole trailing segments where they fit and a PARTIAL
  sentence-level tail where none does. The partial path is load-bearing, not a fallback:
  it carried nothing at all before 2026-08-12, because a paragraph bigger than the
  200-token budget can never be carried whole and real legal paragraphs routinely are —
  the sample lease measures a 673-token median with every segment over budget, and
  consecutive chunks shared zero text. Do not "simplify" it back to whole segments; the
  overlap silently becomes nothing and the one guarantee it exists for is lost.
  The carried tail is always a STRICT suffix of the chunk. If it could be the whole
  chunk, the next chunk opens as a copy of the previous one — which is the shape a
  non-terminating chunker takes.
- NEVER send the full document text in a single API call
- The document-level summary is a REDUCE pass over the per-section summaries, never a
  second read of the document — that would be the single-call-with-everything the line
  above forbids. `analyzer.summarize_document` runs on ANALYSIS_MODEL with
  `thinking: {"type": "disabled"}` and `SUMMARY_MAX_TOKENS = 1000`, changed together per
  the rule above: the judgment already happened in the chunk calls, and this is a writing
  task over material that has been analyzed. Do NOT send `output_config.effort` with
  thinking disabled.
- The summary NEVER fails the analysis. `summarize_document` returns None on every
  non-clean outcome — API error, refusal, truncation, empty text — and null renders as no
  summary section at all. Truncation is discarded rather than shown: a summary cut off
  mid-sentence still renders, and reads as a complete thought that simply stops.
- It runs inside the COMPILING stage and inside the concurrency semaphore. The stage the
  reader is watching should be the stage that is happening, and the per-document ceiling
  has to cover every call the document makes, not just the chunk fan-out.
- The summary is the ONLY claim in the payload with no page reference. That is why the
  prompt forbids writing any page, section, or clause number, and forbids restating the
  risk findings — a conclusion without provenance is what `.claude/rules/ai-output.md`
  exists to prevent, and the findings already have citations of their own. It describes
  the document; it does not re-judge it.
- When sections were skipped, `build_summary_prompt` says so. Prose reads as a complete
  account of a document in a way a table of flags does not, so the model is told what it
  is missing and the UI repeats the limitation on the paragraph itself.

## Expected JSON Output Schema
Every Claude analysis call must return this exact structure:
```json
{
  "summary": "string — plain English, 3-5 sentences",
  "risk_flags": [
    {
      "clause_type": "string",
      "severity": "HIGH | MEDIUM | LOW",
      "explanation": "string — plain English, 1-2 sentences",
      "page_reference": "number | null"
    }
  ],
  "missing_clauses": [
    {
      "clause_name": "string",
      "importance": "HIGH | MEDIUM | LOW",
      "explanation": "string"
    }
  ],
  "document_type": "string — e.g. NDA, Lease, Employment Contract"
}
```

## Coding Conventions
- Python: use type hints on all function signatures
- Python: Pydantic models for all request/response validation — no raw dicts in route handlers
- Python: async/await throughout FastAPI — no blocking calls
- React: functional components only, hooks for state
- React: no inline styles — Tailwind classes only
- File naming: snake_case for Python, PascalCase for React components, kebab-case for CSS
- NEVER commit API keys or Supabase credentials — use .env and python-dotenv
- All prompts live in backend/prompts/analysis.py — never hardcode prompts inside service functions

## UI/UX Rules
Aesthetic target: institutional restraint — traditional legal gravitas, modern execution.
Read `docs/design-system.md` before any visual work and `docs/ui-patterns.md` before
building analysis, viewer, or state-handling UI.

- Use semantic design tokens from tailwind.config.js. NEVER hardcode hex values in components.
- Risk severity ALWAYS renders as color + icon + text label. Never color alone.
- NEVER display an AI-generated claim without its provenance affordance (page ref now,
  source span in V2). No bare conclusions.
- Every analysis view carries persistent "AI-generated — verify against source. Not legal
  advice." framing. Do not let a user dismiss it permanently.
- Max border-radius 8px. No glassmorphism, gradient buttons, or celebratory animation.
- WCAG 2.2 AA is a build requirement, not a polish pass: 4.5:1 body text, visible focus
  rings, full keyboard operability.
- Long-form document text: 16-18px, line-height 1.6, max ~70ch measure.

## API Surface
```
GET    /api/health                        liveness + whether analysis and history are configured
POST   /api/documents/analyze             multipart PDF -> 202 { job_id, document, ... }
GET    /api/documents/analyze/{job_id}    progress, then the result once COMPLETE
GET    /api/documents/history             recent analyses, summary fields only
GET    /api/documents/history/{id}        one stored AnalysisResult
DELETE /api/documents/history/{id}        remove one
```
- Upload is parsed and chunked INSIDE the POST, so an unusable file gets an immediate
  400 naming the reason, and the 202 already carries filename/page count for the UI.
- Analysis runs as a background job because it is slow and because determinate progress
  ("Analyzing 4 of 11 sections") only exists if it can be read while it happens.
- Job state is in this process's memory (`services/jobs.py`). **Run a single worker.**
  `--workers 2` would answer polls for jobs the other worker owns. Lifting this means
  moving job state to Supabase, alongside document history.
- `AnalysisResult` carries BOTH `aggregate` (the merged document-level view from
  `services/aggregator.py`) and `sections` (the per-chunk evidence). The merge is an
  inference; the raw view is the recourse when an inference is wrong, so both ship.
  `aggregate.summary` is the document-level summary, and it is the one field the
  aggregator does NOT compute — producing it takes an API call, and that module is pure
  by design, which is what lets every merge rule be pinned without a network. The
  analyzer produces it; `aggregate_run` carries it through.
  Aggregation is conservative on purpose: over-merging deletes a finding, under-merging
  only shows a duplicate. Those are not symmetric harms.
- `ChunkFailure.detail` NEVER crosses the wire. `SkippedSection` is the public form and
  omits it; `routers/documents.py::_build_result` is the only conversion point. Keep it
  the only one.
- Ceilings live in config.py: `MAX_UPLOAD_BYTES`, `MAX_CHUNKS_PER_DOCUMENT` (the only
  thing bounding per-document API spend), `MAX_CONCURRENT_ANALYSES`.
- A run in which EVERY chunk failed is reported as FAILED, not as a successful analysis
  with zero findings. "No risks found" is the most dangerous thing this product can say,
  so it is never said by accident.

## Document History (Supabase)
- What is stored: the serialized `AnalysisResult` — which carries the EXTRACTED TEXT in
  its `pages` field — plus denormalized summary columns. What is NOT stored: the uploaded
  PDF. There is no storage bucket. Smallest confidentiality surface that still supports
  history; adding bucket upload changes what the user was told and is not a silent change.
- `analyses` has RLS ENABLED WITH NO POLICIES, so only the service role reaches it. The
  backend uses `SUPABASE_SERVICE_ROLE_KEY`, which bypasses RLS and must never reach the
  browser. Do NOT add a permissive policy to "make it work" — the table holds full
  contract text and the anon key is public.
- Two failure policies, and the split is the point:
  `save_analysis` NEVER raises — the analysis has already succeeded and a storage error
  must not turn it into a failure. Every READ raises `HistoryError` — a list that returned
  `[]` because the database was down would say "you have no documents", which is the same
  species of lie as "no risks found".
  `routers/documents.py` ALSO wraps the save call: without that, a raise would reach the
  background task's handler and call `job.fail()` on a completed analysis. Both layers are
  load-bearing and both are mutation-tested.
- The save runs AFTER the job is reported COMPLETE, so there is a short window (~1s, one
  insert round trip) where a finished analysis is not yet in history. That ordering is
  deliberate — the job must be readable the instant it completes — but it is why the INSERT
  goes before the retention purge rather than after: housekeeping does not get to widen it.
- The history LIST renders counts only, never a severity or an explanation. It has no page
  reference to attach one to, and a conclusion without its provenance is the thing
  `.claude/rules/ai-output.md` forbids. Open the analysis to see claims.
- Retention is `config.HISTORY_RETENTION_DAYS`, swept on write by `purge_expired` (the same
  pattern as `JobStore._evict_expired` — no background task, no pg_cron). That number is
  USER-FACING: `/api/health` reports it and `UploadZone.jsx` interpolates it. Change the
  constant and the promise follows; hardcode it in the component and the promise drifts.
- The upload disclosure is a factual claim about where confidential text goes. If what is
  stored ever changes, `UploadZone.jsx` changes in the SAME commit. `frontend/src/tests/
  upload.test.jsx` exists to make that non-optional.
- Schema DDL is `backend/sql/001_analyses.sql`, applied by hand. Tests never touch a real
  project: `_harness.scrub_live_credentials()` removes every credential after `import main`
  — before it, `load_dotenv` just puts them back.

## Error Handling Rules
- All Claude API calls wrapped in try/except with specific error messages returned to frontend
- If PDF parsing fails, return a clear user-facing error — never a raw traceback
- If a chunk returns malformed JSON from Claude, log it and skip that chunk gracefully
- Frontend must handle loading, error, and empty states for every API call

## What NOT to Do
- Do NOT use LangChain or LlamaIndex — build the chunking and prompt logic directly
- Do NOT use WidthType.PERCENTAGE in any docx output
- Do NOT store raw PDF files ANYWHERE — not in the repo, and not in a Supabase bucket.
  Only extracted text and the analysis are persisted. See Document History.
- Do NOT use synchronous requests in FastAPI routes
- Do NOT hallucinate page numbers — only include page_reference if the parser provides it.
  Three mechanisms, and all three are load-bearing:
  1. The chunker writes inline `[page N]` markers into the chunk text, so the model reads
     page attribution instead of estimating it from position.
  2. The prompt states the permitted page set, bounding what can be said.
  3. `analyzer._sanitize_page_references` nulls anything outside the chunk's own
     `page_numbers`. The prompt asks; the code checks.
  Do NOT remove the markers on the grounds that the range is already stated. That exact
  configuration was measured live on a 6-page lease: 11 of 13 citations landed on the
  wrong page, every one inside the permitted range and so invisible to the range check.
  With markers the same document scored 15 of 15. A citation that is wrong but plausible
  is the worst output this product can produce.

## Dev Commands
```bash
# One-time: apply the history schema. Paste backend/sql/001_analyses.sql into the
# Supabase SQL editor. Without it the app runs fine and simply stores nothing —
# /api/health reports history_available: false.

# Backend — single worker only, see API Surface
cd backend
uvicorn main:app --reload --port 8000

# Backend tests (no pytest needed)
python backend/tests/run_all.py

# Frontend
cd frontend
npm run dev

# Frontend tests (Vitest + jsdom)
cd frontend
npm test
# jsdom has no layout engine, so target size, 200% reflow and contrast are NOT
# covered here — see frontend/src/tests/README.md for the browser checklist.

# Install backend deps
pip install fastapi uvicorn pdfplumber pymupdf anthropic supabase python-dotenv pydantic

# Install frontend deps (package.json is committed — this just restores it)
cd frontend
npm install
# Runtime: axios, react-router-dom, lucide-react, @fontsource-variable/* (self-hosted
# fonts — no third-party request from a page showing confidential contract text).
# Build: vite, @vitejs/plugin-react, tailwindcss v3, postcss, autoprefixer.
# Test: vitest, jsdom, @testing-library/react, @testing-library/jest-dom,
#       @testing-library/user-event (Radix triggers fire on mousedown/focus, not
#       click — element.click() alone silently does nothing).
# UI:   @radix-ui/react-tabs, for the roving tabindex and ARIA wiring the
#       findings/navigator/document tabs need. Added per component, as intended.
# Tailwind stays on v3: docs and .claude/rules/frontend-ui.md both key off
# frontend/tailwind.config.js, and v4's CSS-first setup has no such file.
# Radix primitives are pulled in per-component by the shadcn/ui CLI when a component
# actually needs them (tabs, dialog, tooltip) — do not add @headlessui/react
```

## Environment Variables Required
```
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

## Current Phase
**June 2026 — Foundation Phase**
Focus: PDF upload pipeline, text extraction, basic Claude integration, raw JSON output rendering.
Do NOT build V2 features (doc comparison, chat mode) until MVP is complete and tested.

## Ask Before Doing
- Adding new dependencies not listed above
- Changing the JSON output schema
- Switching PDF parsing libraries
- Any destructive database operation
- Adding a design token, font, or color not defined in docs/design-system.md
