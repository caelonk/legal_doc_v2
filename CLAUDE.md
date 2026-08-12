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
- **Storage:** Supabase (file storage + PostgreSQL for document history)
- **Auth:** Supabase Auth (if user accounts are added in V2)

## Project Structure
```
legal-doc-analyzer/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Model IDs + request/pipeline constants (single source)
│   ├── routers/
│   │   ├── documents.py         # Upload and analysis endpoints
│   │   └── health.py
│   ├── services/
│   │   ├── parser.py            # PDF text extraction logic
│   │   ├── chunker.py           # Token-aware text chunking
│   │   ├── analyzer.py          # Claude API calls + prompt logic
│   │   ├── jobs.py              # In-memory analysis job store (see API Surface)
│   │   └── supabase.py          # Storage client
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   ├── prompts/
│   │   └── analysis.py          # All prompt templates (centralized)
│   └── tests/                   # Dependency-free suite; python backend/tests/run_all.py
├── frontend/
│   ├── tailwind.config.js       # Semantic tokens; src/globals.css holds the raw values
│   ├── src/
│   │   ├── components/
│   │   │   ├── UploadZone.jsx
│   │   │   ├── AnalysisProgress.jsx  # Renders stage_message verbatim from the API
│   │   │   ├── SourcePane.jsx        # Extracted text + the citation jump target
│   │   │   ├── ResultsPanel.jsx
│   │   │   ├── PageReference.jsx     # The provenance affordance
│   │   │   ├── ClauseNavigator.jsx   # NOT BUILT — pass 2
│   │   │   └── RiskBadge.jsx
│   │   ├── pages/
│   │   │   ├── Home.jsx
│   │   │   └── Analysis.jsx
│   │   ├── hooks/
│   │   │   └── useAnalysisJob.js     # Polls a job to a terminal state
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
- Chunk documents at 3000 tokens with 200-token overlap to preserve clause context
- NEVER send the full document text in a single API call

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
GET  /api/health                          liveness + whether analysis is configured
POST /api/documents/analyze               multipart PDF -> 202 { job_id, document, ... }
GET  /api/documents/analyze/{job_id}      progress, then the result once COMPLETE
```
- Upload is parsed and chunked INSIDE the POST, so an unusable file gets an immediate
  400 naming the reason, and the 202 already carries filename/page count for the UI.
- Analysis runs as a background job because it is slow and because determinate progress
  ("Analyzing 4 of 11 sections") only exists if it can be read while it happens.
- Job state is in this process's memory (`services/jobs.py`). **Run a single worker.**
  `--workers 2` would answer polls for jobs the other worker owns. Lifting this means
  moving job state to Supabase, alongside document history.
- `ChunkFailure.detail` NEVER crosses the wire. `SkippedSection` is the public form and
  omits it; `routers/documents.py::_build_result` is the only conversion point. Keep it
  the only one.
- Ceilings live in config.py: `MAX_UPLOAD_BYTES`, `MAX_CHUNKS_PER_DOCUMENT` (the only
  thing bounding per-document API spend), `MAX_CONCURRENT_ANALYSES`.
- A run in which EVERY chunk failed is reported as FAILED, not as a successful analysis
  with zero findings. "No risks found" is the most dangerous thing this product can say,
  so it is never said by accident.

## Error Handling Rules
- All Claude API calls wrapped in try/except with specific error messages returned to frontend
- If PDF parsing fails, return a clear user-facing error — never a raw traceback
- If a chunk returns malformed JSON from Claude, log it and skip that chunk gracefully
- Frontend must handle loading, error, and empty states for every API call

## What NOT to Do
- Do NOT use LangChain or LlamaIndex — build the chunking and prompt logic directly
- Do NOT use WidthType.PERCENTAGE in any docx output
- Do NOT store raw PDF files in the repo — use Supabase storage bucket
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
# Test: vitest, jsdom, @testing-library/react, @testing-library/jest-dom.
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
