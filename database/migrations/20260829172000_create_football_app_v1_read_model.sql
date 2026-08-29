-- Football App V1 — publication boundary and deterministic public read model.
-- The public web can read only verified facts and published intelligence.
-- Research runs/evidence/fan themes/revision audit remain private.

-- Supabase provides these roles. Plain PostgreSQL CI does not, so create
-- NOLOGIN fallbacks only when they are genuinely absent.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
end
$$;

alter table public.competitions enable row level security;
alter table public.seasons enable row level security;
alter table public.competition_stages enable row level security;
alter table public.rounds enable row level security;
alter table public.teams enable row level security;
alter table public.players enable row level security;
alter table public.managers enable row level security;
alter table public.sources enable row level security;
alter table public.source_documents enable row level security;
alter table public.expert_profiles enable row level security;
alter table public.player_team_tenures enable row level security;
alter table public.manager_team_tenures enable row level security;
alter table public.matches enable row level security;
alter table public.player_appearances enable row level security;
alter table public.match_events enable row level security;
alter table public.team_match_stats enable row level security;
alter table public.player_match_stats enable row level security;
alter table public.research_runs enable row level security;
alter table public.evidence_items enable row level security;
alter table public.fan_themes enable row level security;
alter table public.player_match_reviews enable row level security;
alter table public.team_match_reviews enable row level security;
alter table public.manager_match_reviews enable row level security;
alter table public.player_level_estimates enable row level security;
alter table public.player_dna_estimates enable row level security;
alter table public.player_archetypes enable row level security;
alter table public.intelligence_signals enable row level security;
alter table public.rating_benchmarks enable row level security;
alter table public.rating_revisions enable row level security;

-- Recreate public SELECT policies deterministically.
drop policy if exists public_read_competitions on public.competitions;
create policy public_read_competitions on public.competitions for select to anon, authenticated using (active = true);

drop policy if exists public_read_seasons on public.seasons;
create policy public_read_seasons on public.seasons for select to anon, authenticated using (status in ('ACTIVE','COMPLETED'));

drop policy if exists public_read_stages on public.competition_stages;
create policy public_read_stages on public.competition_stages for select to anon, authenticated using (true);

drop policy if exists public_read_rounds on public.rounds;
create policy public_read_rounds on public.rounds for select to anon, authenticated using (true);

drop policy if exists public_read_teams on public.teams;
create policy public_read_teams on public.teams for select to anon, authenticated using (true);

drop policy if exists public_read_players on public.players;
create policy public_read_players on public.players for select to anon, authenticated using (true);

drop policy if exists public_read_managers on public.managers;
create policy public_read_managers on public.managers for select to anon, authenticated using (true);

drop policy if exists public_read_sources on public.sources;
create policy public_read_sources on public.sources for select to anon, authenticated using (active = true);

drop policy if exists public_read_source_documents on public.source_documents;
create policy public_read_source_documents on public.source_documents for select to anon, authenticated using (true);

drop policy if exists public_read_expert_profiles on public.expert_profiles;
create policy public_read_expert_profiles on public.expert_profiles for select to anon, authenticated using (active = true);

drop policy if exists public_read_player_tenures on public.player_team_tenures;
create policy public_read_player_tenures on public.player_team_tenures for select to anon, authenticated using (true);

drop policy if exists public_read_manager_tenures on public.manager_team_tenures;
create policy public_read_manager_tenures on public.manager_team_tenures for select to anon, authenticated using (true);

drop policy if exists public_read_matches on public.matches;
create policy public_read_matches on public.matches for select to anon, authenticated using (identity_verified = true);

drop policy if exists public_read_appearances on public.player_appearances;
create policy public_read_appearances on public.player_appearances for select to anon, authenticated using (
  exists (select 1 from public.matches m where m.id = player_appearances.match_id and m.identity_verified = true)
);

drop policy if exists public_read_events on public.match_events;
create policy public_read_events on public.match_events for select to anon, authenticated using (
  exists (select 1 from public.matches m where m.id = match_events.match_id and m.identity_verified = true)
);

drop policy if exists public_read_team_stats on public.team_match_stats;
create policy public_read_team_stats on public.team_match_stats for select to anon, authenticated using (
  exists (select 1 from public.matches m where m.id = team_match_stats.match_id and m.identity_verified = true)
);

drop policy if exists public_read_player_stats on public.player_match_stats;
create policy public_read_player_stats on public.player_match_stats for select to anon, authenticated using (
  exists (select 1 from public.matches m where m.id = player_match_stats.match_id and m.identity_verified = true)
);

drop policy if exists public_read_published_player_reviews on public.player_match_reviews;
create policy public_read_published_player_reviews on public.player_match_reviews for select to anon, authenticated using (status = 'PUBLISHED');

drop policy if exists public_read_published_team_reviews on public.team_match_reviews;
create policy public_read_published_team_reviews on public.team_match_reviews for select to anon, authenticated using (status = 'PUBLISHED');

drop policy if exists public_read_published_manager_reviews on public.manager_match_reviews;
create policy public_read_published_manager_reviews on public.manager_match_reviews for select to anon, authenticated using (status = 'PUBLISHED');

drop policy if exists public_read_published_player_level on public.player_level_estimates;
create policy public_read_published_player_level on public.player_level_estimates for select to anon, authenticated using (status = 'PUBLISHED');

drop policy if exists public_read_published_player_dna on public.player_dna_estimates;
create policy public_read_published_player_dna on public.player_dna_estimates for select to anon, authenticated using (status = 'PUBLISHED');

drop policy if exists public_read_published_archetypes on public.player_archetypes;
create policy public_read_published_archetypes on public.player_archetypes for select to anon, authenticated using (status = 'PUBLISHED');

drop policy if exists public_read_published_signals on public.intelligence_signals;
create policy public_read_published_signals on public.intelligence_signals for select to anon, authenticated using (
  published_at is not null and status in ('SUPPORTED','PARTIAL','MIXED')
);

drop policy if exists public_read_active_benchmarks on public.rating_benchmarks;
create policy public_read_active_benchmarks on public.rating_benchmarks for select to anon, authenticated using (active = true and anchor_status <> 'RETIRED');

-- Keep internal research and audit tables inaccessible to public roles.
revoke all on public.research_runs, public.evidence_items, public.fan_themes, public.rating_revisions from anon, authenticated;

-- Safe public relations.
grant usage on schema public to anon, authenticated;
grant select on public.competitions, public.seasons, public.competition_stages, public.rounds,
  public.teams, public.players, public.managers, public.sources, public.source_documents,
  public.expert_profiles, public.player_team_tenures, public.manager_team_tenures,
  public.matches, public.player_appearances, public.match_events, public.team_match_stats,
  public.player_match_stats, public.player_match_reviews, public.team_match_reviews,
  public.manager_match_reviews, public.player_level_estimates, public.player_dna_estimates,
  public.player_archetypes, public.intelligence_signals, public.rating_benchmarks
  to anon, authenticated;

create or replace view public.v_current_player_match_reviews
with (security_invoker = true)
as select * from public.player_match_reviews where status = 'PUBLISHED';

create or replace view public.v_current_team_match_reviews
with (security_invoker = true)
as select * from public.team_match_reviews where status = 'PUBLISHED';

create or replace view public.v_current_manager_match_reviews
with (security_invoker = true)
as select * from public.manager_match_reviews where status = 'PUBLISHED';

create or replace view public.v_player_match_history
with (security_invoker = true)
as
select
  r.player_id,
  r.team_id,
  r.match_id,
  m.kickoff_at,
  m.season_id,
  m.home_team_id,
  m.away_team_id,
  m.home_goals,
  m.away_goals,
  a.minutes,
  coalesce(r.role_label, a.role_label, a.broad_position) as role_label,
  r.final_score,
  r.confidence,
  r.evidence_status,
  r.summary
from public.v_current_player_match_reviews r
join public.matches m on m.id = r.match_id
left join public.player_appearances a on a.match_id = r.match_id and a.player_id = r.player_id
where m.identity_verified = true;

create or replace view public.v_player_recent_form
with (security_invoker = true)
as
with ordered as (
  select h.*, row_number() over (partition by h.player_id order by h.kickoff_at desc, h.match_id desc) as rn
  from public.v_player_match_history h
)
select
  player_id,
  count(*) as rated_appearances,
  avg(final_score) as season_mean,
  percentile_cont(0.5) within group (order by final_score::double precision) as season_median,
  avg(final_score) filter (where rn <= 5) as last_5_mean,
  avg(final_score) filter (where rn <= 10) as last_10_mean,
  stddev_pop(final_score) as volatility_stddev,
  avg(case when final_score >= 8.0 then 1.0 else 0.0 end) as high_performance_rate,
  avg(case when final_score < 5.5 then 1.0 else 0.0 end) as poor_performance_rate
from ordered
group by player_id;

create or replace view public.v_team_recent_form
with (security_invoker = true)
as
with base as (
  select r.team_id, r.match_id, m.kickoff_at, r.final_score, r.confidence,
    row_number() over (partition by r.team_id order by m.kickoff_at desc, r.match_id desc) as rn
  from public.v_current_team_match_reviews r
  join public.matches m on m.id = r.match_id
  where m.identity_verified = true
)
select
  team_id,
  count(*) as rated_matches,
  avg(final_score) as season_mean,
  percentile_cont(0.5) within group (order by final_score::double precision) as season_median,
  avg(final_score) filter (where rn <= 5) as last_5_mean,
  avg(final_score) filter (where rn <= 10) as last_10_mean,
  stddev_pop(final_score) as volatility_stddev
from base
group by team_id;

create or replace view public.v_manager_recent_form
with (security_invoker = true)
as
with base as (
  select r.manager_id, r.team_id, r.match_id, m.kickoff_at, r.final_score, r.confidence,
    row_number() over (partition by r.manager_id order by m.kickoff_at desc, r.match_id desc) as rn
  from public.v_current_manager_match_reviews r
  join public.matches m on m.id = r.match_id
  where m.identity_verified = true
)
select
  manager_id,
  (array_agg(team_id order by rn))[1] as current_team_id,
  count(*) as rated_matches,
  avg(final_score) as season_mean,
  avg(final_score) filter (where rn <= 5) as last_5_mean,
  avg(final_score) filter (where rn <= 10) as last_10_mean,
  stddev_pop(final_score) as volatility_stddev
from base
group by manager_id;

grant select on public.v_current_player_match_reviews, public.v_current_team_match_reviews,
  public.v_current_manager_match_reviews, public.v_player_match_history,
  public.v_player_recent_form, public.v_team_recent_form, public.v_manager_recent_form
  to anon, authenticated;
