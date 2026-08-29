-- Research-run idempotency and one-current-published-review invariants.

alter table public.research_runs add column if not exists run_key text;
drop index if exists public.research_runs_run_key_uq;
alter table public.research_runs drop constraint if exists research_runs_run_key_key;
alter table public.research_runs add constraint research_runs_run_key_key unique (run_key);

create unique index if not exists player_match_reviews_one_published_uq
  on public.player_match_reviews(match_id, player_id) where status = 'PUBLISHED';
create unique index if not exists team_match_reviews_one_published_uq
  on public.team_match_reviews(match_id, team_id) where status = 'PUBLISHED';
create unique index if not exists manager_match_reviews_one_published_uq
  on public.manager_match_reviews(match_id, manager_id) where status = 'PUBLISHED';
create unique index if not exists match_reviews_one_published_uq
  on public.match_reviews(match_id) where status = 'PUBLISHED';
