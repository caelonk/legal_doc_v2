# Legal Document Analyzer

Upload a contract. Get a plain-English summary, risk-flagged clauses, and a list of
standard provisions that appear to be missing — each finding linked back to the page it
came from.

Built with FastAPI, React, and the Anthropic Claude API.

```
PDF ──> extract ──> chunk ──> Claude (per section) ──> merge ──> findings + citations
        pdfplumber  3000 tok   Sonnet 5, structured    aggregator
        /PyMuPDF    200 overlap  output                 + one reduce pass
```

---

## Why this exists

A tool that reads contracts for you has one failure mode that matters more than all the
others: **being confidently wrong in a way the reader cannot check.** Everything below
follows from that.

The interesting parts of this codebase are not the API calls. They are the places where
the obvious implementation produces something that looks right and isn't.

---

## Four problems worth reading about

### 1. The model cited the wrong page 11 times out of 13

The first version told the model which pages a section spanned and asked it to cite one.
Measured against a 6-page lease, **11 of 13 citations landed on the wrong page** — every
one inside the permitted range, so every one invisible to a range check.

The model was obeying the constraint and then guessing *within* it by position, because
unmarked text offers nothing better to go on.

The fix is that the chunker writes inline `[page N]` markers into the chunk text, so the
model reads page attribution instead of estimating it. The same document then scored
**15 of 15**.

Three mechanisms now guard this, and all three are load-bearing:

| | |
|---|---|
| `chunker` | writes `[page N]` markers into the text |
| `prompts/analysis.py` | states the permitted page set |
| `analyzer._sanitize_page_references` | nulls anything outside the chunk's own pages |

The prompt asks; the code checks. An out-of-range citation becomes `null`, which renders
as an explicit **"Source not located"** — because a visibly missing citation is honest and
a silently absent one is not.

### 2. The chunk overlap was silently empty

Chunks overlap by 200 tokens so a clause on a boundary isn't cut in half. The overlap
carried whole trailing paragraphs — and stopped at the first one that didn't fit.

Real legal paragraphs don't fit. The sample lease measures a **673-token median**, with
every segment over the 200-token budget, so consecutive chunks shared **zero** text. The
one guarantee the overlap exists for was never delivered.

The existing test passed, because it tolerated one failing boundary and used repetitive
filler — with repeated text, "the tail of A appears in B" is true by accident.

`_overlap_tail` now falls back to a **partial, sentence-boundary tail**, guarded so the
carry is always a strict suffix (otherwise the next chunk opens as a copy of the previous
one, which is the shape a non-terminating chunker takes). On the sample lease, chunk 1's
page span went `[6]` → `[5, 6]`, and the boundary clause produced a finding it previously
could not.

### 3. Merging findings is asymmetric

Overlapping chunks report the same clause twice, so the aggregator merges duplicates.
The rule it is built around:

> **Over-merging deletes a finding. Under-merging shows a duplicate.**

Those are not the same size of mistake. A duplicate is visible and mildly annoying. A
wrongly merged pair is a risk that silently disappears — in a product whose worst possible
output is *"no risks found."*

So matching is exact on normalized labels: no stemming, no fuzzy distance, no synonyms.
Severity merges to the **maximum**, never an average, and disagreement between sections is
reported rather than smoothed away. `aggregate` ships **alongside** the raw per-section
results, never instead of them — a merge is an inference, and the evidence is the recourse
when an inference is wrong.

### 4. Storage changed what the user had been told

The upload disclosure said the document *"is not written to disk and not stored."* True —
until the commit that added document history, which would have made it a lie, in a product
about confidential contracts, in the one sentence a hesitating user actually reads.

Storage and the disclosure landed in the **same commit**, and the copy is now derived from
`/api/health` rather than written as a constant, so the promise cannot drift from the
retention the server actually enforces. `frontend/src/tests/upload.test.jsx` exists to keep
that non-optional.

---

## What it will not do

- **No "0 risks" as reassurance.** A run where every section failed is reported as FAILED,
  not as a clean analysis with an empty list.
- **No empty list for a broken database.** History reads return 503 when storage is
  unreachable, because a list that returned `[]` would say *"you have no documents"* — the
  same species of lie.
- **No advice.** Prompts and copy identify and describe. *"This clause may expose you to
  unlimited liability"* is in scope; *"you should not sign this"* is not.
- **No raw PDF storage.** Extracted text and analysis are persisted. The uploaded file is
  never written to disk and never uploaded to a bucket.
- **No conclusion without provenance.** Every risk flag and missing clause renders with its
  explanation and its page reference in the same visual unit.

---

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI · Python 3.14 · Pydantic v2 |
| Analysis | Claude Sonnet 5 (sections + summary), Haiku 4.5 (document-type pre-pass) |
| Parsing | pdfplumber, with PyMuPDF as the layout-heavy fallback |
| Storage | Supabase Postgres — analysis + extracted text only, RLS on with no policies |
| Frontend | React 19 · Vite · Tailwind v3 · Radix primitives |
| Tests | Dependency-free Python harness · Vitest + jsdom + Testing Library |

Structured outputs (`client.messages.parse(output_format=ChunkAnalysis)`) make the Pydantic
model the single definition of the contract, the validation, and the API-side constraint.
Structured outputs guarantee **shape, not truth** — which is why the page-reference check
above still exists.

---

## Running it

Requires an Anthropic API key. Supabase is optional: without it the app analyzes documents
normally and simply stores nothing, and `/api/health` says so.

```bash
cp .env.example .env    # then fill in ANTHROPIC_API_KEY and, optionally, Supabase
```

```bash
pip install fastapi uvicorn pdfplumber pymupdf anthropic supabase python-dotenv pydantic
```

Backend — **single worker only**, since job state lives in this process's memory:

```bash
cd backend && uvicorn main:app --reload --port 8000
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

For document history, paste `backend/sql/001_analyses.sql` into the Supabase SQL editor
once. Without it the app runs fine and `/api/health` reports `history_available: false`.

---

## Tests

```bash
python backend/tests/run_all.py
```

```bash
cd frontend && npm test
```

**417 backend checks across 7 modules, 201 frontend across 13 files.** No network in either
suite: the Anthropic and Supabase clients are replaced with doubles, and
`_harness.scrub_live_credentials()` strips every real credential after `import main` —
before it, `load_dotenv` just puts them back.

Every guard here was verified by **mutation**: break the rule in the source, confirm the
matching test goes red, restore. A test that has never failed is not evidence. Several
tests in this repo were written, passed, and were then found to be checking nothing.

### What the tests cannot catch

jsdom has no layout engine, so target size, reflow, and contrast are checked in a browser
against the checklist in `frontend/src/tests/README.md`. It has earned its place twice:

- a history row's filename link — the primary control on the page — measuring **118×17px**,
  under the 24px minimum, with all 193 tests passing
- a **white screen** on the landing page, from destructuring `null` in a parameter default.
  The unit test for that exact case passed the whole time: it rendered the component with
  the prop absent (`undefined`), while the app passed `null`. One value tested is not the
  rule tested.

---

## API

```
GET    /api/health                        liveness + whether analysis and history are configured
POST   /api/documents/analyze             multipart PDF -> 202 { job_id, document, ... }
GET    /api/documents/analyze/{job_id}    progress, then the result once COMPLETE
GET    /api/documents/history             recent analyses, summary fields only
GET    /api/documents/history/{id}        one stored AnalysisResult
DELETE /api/documents/history/{id}        remove one
```

Upload is parsed and chunked **inside** the POST, so an unusable file gets an immediate 400
naming the reason rather than a job that must be polled before it can report the file was
never usable. Analysis runs as a background job because determinate progress
("Analyzing 4 of 11 sections") only exists if it can be read while it happens.

---

## Not built

Deliberately out of scope for the MVP, and listed because a portfolio project that claims
to be finished usually isn't:

- **Auth.** No user accounts; history is single-tenant and the table is reachable only by
  the service role.
- **Distributed job state.** Jobs live in one process's memory, hence the single worker.
  Lifting it means moving them to Postgres alongside document history.
- **Playwright.** The four browser checks above are manual. They should be automated.
- **V2 features** — document comparison, chat over a contract, source-span highlighting
  rather than page-level citations.

---

*AI-generated analysis. Verify against the source document. This is not legal advice.*
