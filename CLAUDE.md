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
│   ├── routers/
│   │   ├── documents.py         # Upload and analysis endpoints
│   │   └── health.py
│   ├── services/
│   │   ├── parser.py            # PDF text extraction logic
│   │   ├── chunker.py           # Token-aware text chunking
│   │   ├── analyzer.py          # Claude API calls + prompt logic
│   │   └── supabase.py          # Storage client
│   ├── models/
│   │   └── schemas.py           # Pydantic request/response models
│   └── prompts/
│       └── analysis.py          # All prompt templates (centralized)
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── UploadZone.jsx
│   │   │   ├── ResultsPanel.jsx
│   │   │   ├── ClauseNavigator.jsx
│   │   │   └── RiskBadge.jsx
│   │   ├── pages/
│   │   │   ├── Home.jsx
│   │   │   └── Analysis.jsx
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
- Do NOT hallucinate page numbers — only include page_reference if the parser provides it

## Dev Commands
```bash
# Backend
cd backend
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm run dev

# Install backend deps
pip install fastapi uvicorn pdfplumber pymupdf anthropic supabase python-dotenv pydantic

# Install frontend deps
npm install axios react-router-dom lucide-react
# Radix primitives are pulled in per-component by the shadcn/ui CLI — do not add @headlessui/react
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
