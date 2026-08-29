-- Persist the match-level editorial/analytical reading required by the public Match page.
-- Public source IDs are stored inside evidence_mix; raw research evidence remains private.

create table if not exists public.match_reviews (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references public.matches(id) on delete cascade,
  research_run_id uuid not null references public.research_runs(id) on delete restrict,
  review_version integer not null,
  summary text not null,
  key_takeaways jsonb not null default '[]'::jsonb,
  evidence_mix jsonb not null default '{}'::jsonb,
  methodology_sha text not null,
  rating_scale_version text not null,
  benchmark_version text not null,
  status text not null check (status in ('DRAFT','QA','PUBLISHED','REVISED','REJECTED')),
  published_at timestamptz,
  supersedes_review_id uuid references public.match_reviews(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (match_id, review_version),
  check ((status = 'PUBLISHED' and published_at is not null) or status <> 'PUBLISHED')
);

create index if not exists match_reviews_match_idx on public.match_reviews(match_id, review_version desc);
create index if not exists match_reviews_research_run_idx on public.match_reviews(research_run_id);
create index if not exists match_reviews_supersedes_idx on public.match_reviews(supersedes_review_id) where supersedes_review_id is not null;

alter table public.match_reviews enable row level security;

drop policy if exists match_reviews_public_read_published on public.match_reviews;
create policy match_reviews_public_read_published
on public.match_reviews
for select
to anon, authenticated
using (status = 'PUBLISHED');

grant select on public.match_reviews to anon, authenticated;

create or replace view public.v_current_match_reviews
with (security_invoker = true)
as
select * from public.match_reviews where status = 'PUBLISHED';

grant select on public.v_current_match_reviews to anon, authenticated;

-- Earlier experimental public evidence views are intentionally removed: published
-- match_reviews.evidence_mix stores source_document_ids and the UI resolves those
-- against the public source_documents table. Raw evidence remains private.
drop view if exists public.v_match_public_evidence;
drop view if exists public.v_match_public_sources;
