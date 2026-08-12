-- 001_analyses.sql — document history storage.
--
-- Apply by hand in the Supabase SQL editor. Kept in the repo so the schema is
-- versioned alongside the code that reads it: services/supabase.py names these
-- columns, and a column renamed in the dashboard but not here is a failure that
-- only shows up at runtime.
--
-- WHAT IS STORED, and what is not:
--   * The extracted TEXT of the document and the analysis of it, as one jsonb
--     payload (the serialized AnalysisResult, whose `pages` field already carries
--     the text).
--   * NOT the uploaded PDF. No storage bucket is involved. The smallest
--     confidentiality surface that still supports document history.
--
-- The summary columns beside `result` are denormalized on purpose. A history list
-- must not pull an entire document's text just to render a filename and a date.

create table if not exists public.analyses (
    id                   uuid primary key default gen_random_uuid(),
    created_at           timestamptz not null default now(),

    -- Mirrors models.schemas.DocumentMeta.
    filename             text        not null,
    size_bytes           bigint      not null,
    page_count           integer     not null,
    pages_with_text      integer     not null,
    extraction_method    text        not null,
    chunk_count          integer     not null,

    -- Mirrors the merged view in models.schemas.DocumentAggregate, so a list can
    -- show "Lease · 7 risks" without deserializing `result`.
    document_type        text,
    risk_flag_count      integer     not null default 0,
    missing_clause_count integer     not null default 0,
    skipped_count        integer     not null default 0,

    -- The serialized AnalysisResult. Source of truth for a detail view; the
    -- columns above are a projection of it and are only ever written together
    -- with it.
    result               jsonb       not null
);

-- Every read is "newest first, limited" (list) or "by id" (detail). The primary
-- key covers the second.
create index if not exists analyses_created_at_idx
    on public.analyses (created_at desc);

-- RLS ON, WITH NO POLICIES — this is deliberate, not unfinished.
--
-- There is no auth yet, so there is no user to scope a row to. With RLS enabled
-- and no policy, the anon key can read nothing; only the service role, which
-- bypasses RLS, can touch this table. That key lives in the backend .env and is
-- never sent to the browser.
--
-- If V2 adds Supabase Auth, add a user_id column and an owner policy at that
-- point. Do NOT add a permissive policy to "make it work" in the meantime: this
-- table holds the full text of confidential contracts, and a permissive policy
-- plus the publishable anon key makes them world-readable.
alter table public.analyses enable row level security;
