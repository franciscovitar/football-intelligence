-- Football App V1 — canonical public persistence core.
-- Mirrors the Supabase schema provisioned for the research-first application.
-- Historical schemas (football/analytics/ingestion/perception) are intentionally untouched.

create extension if not exists pgcrypto;

create table if not exists public.competitions (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  country_code text,
  competition_type text not null default 'LEAGUE',
  active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.seasons (
  id uuid primary key default gen_random_uuid(),
  competition_id uuid not null references public.competitions(id) on delete restrict,
  label text not null,
  start_date date,
  end_date date,
  status text not null default 'PLANNED' check (status in ('PLANNED','ACTIVE','COMPLETED','ARCHIVED')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (competition_id, label)
);

create table if not exists public.competition_stages (
  id uuid primary key default gen_random_uuid(),
  season_id uuid not null references public.seasons(id) on delete cascade,
  name text not null,
  stage_type text not null,
  order_index integer,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (season_id, name)
);

create table if not exists public.rounds (
  id uuid primary key default gen_random_uuid(),
  season_id uuid not null references public.seasons(id) on delete cascade,
  stage_id uuid references public.competition_stages(id) on delete set null,
  label text not null,
  sequence integer,
  start_date date,
  end_date date,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (season_id, stage_id, label)
);

create table if not exists public.teams (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  name text not null,
  short_name text,
  country_code text,
  crest_url text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.players (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  display_name text not null,
  full_name text,
  birth_date date,
  nationality text,
  preferred_foot text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.managers (
  id uuid primary key default gen_random_uuid(),
  slug text not null unique,
  display_name text not null,
  birth_date date,
  nationality text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.sources (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  source_type text not null,
  domain text,
  base_url text,
  rights_notes text,
  active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (name, source_type)
);

create table if not exists public.source_documents (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.sources(id) on delete restrict,
  url text not null,
  normalized_url text,
  title text,
  author_text text,
  published_at timestamptz,
  retrieved_at timestamptz not null default now(),
  document_type text not null,
  upstream_notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create unique index if not exists source_documents_normalized_url_uq
  on public.source_documents(normalized_url) where normalized_url is not null;

create table if not exists public.expert_profiles (
  id uuid primary key default gen_random_uuid(),
  display_name text not null,
  source_id uuid references public.sources(id) on delete set null,
  expert_type text not null,
  domains text[] not null default '{}',
  clubs_or_leagues text[] not null default '{}',
  direct_familiarity text,
  independence_notes text,
  track_record_summary text,
  active boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.player_team_tenures (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references public.players(id) on delete cascade,
  team_id uuid not null references public.teams(id) on delete restrict,
  start_date date not null,
  end_date date,
  shirt_number text,
  source_id uuid references public.sources(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (end_date is null or end_date >= start_date)
);

create table if not exists public.manager_team_tenures (
  id uuid primary key default gen_random_uuid(),
  manager_id uuid not null references public.managers(id) on delete cascade,
  team_id uuid not null references public.teams(id) on delete restrict,
  start_date date not null,
  end_date date,
  source_id uuid references public.sources(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (end_date is null or end_date >= start_date)
);

create table if not exists public.matches (
  id uuid primary key default gen_random_uuid(),
  external_identity_key text unique,
  season_id uuid not null references public.seasons(id) on delete restrict,
  stage_id uuid references public.competition_stages(id) on delete set null,
  round_id uuid references public.rounds(id) on delete set null,
  home_team_id uuid not null references public.teams(id) on delete restrict,
  away_team_id uuid not null references public.teams(id) on delete restrict,
  kickoff_at timestamptz,
  status text not null default 'SCHEDULED' check (status in ('SCHEDULED','LIVE','FINAL','POSTPONED','CANCELLED')),
  home_goals smallint,
  away_goals smallint,
  venue text,
  attendance integer,
  referee text,
  home_red_cards smallint,
  away_red_cards smallint,
  match_context jsonb not null default '{}'::jsonb,
  identity_verified boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (home_team_id <> away_team_id),
  check (home_goals is null or home_goals >= 0),
  check (away_goals is null or away_goals >= 0)
);

create table if not exists public.player_appearances (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references public.matches(id) on delete cascade,
  player_id uuid not null references public.players(id) on delete restrict,
  team_id uuid not null references public.teams(id) on delete restrict,
  starter boolean,
  minute_on smallint,
  minute_off smallint,
  minutes smallint,
  broad_position text,
  role_label text,
  role_confidence numeric(5,2),
  captain boolean,
  penalty_taker boolean,
  set_piece_role text,
  source_id uuid references public.sources(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (match_id, player_id),
  check (minutes is null or minutes >= 0),
  check (role_confidence is null or (role_confidence >= 0 and role_confidence <= 100))
);

create table if not exists public.match_events (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references public.matches(id) on delete cascade,
  team_id uuid references public.teams(id) on delete set null,
  player_id uuid references public.players(id) on delete set null,
  related_player_id uuid references public.players(id) on delete set null,
  event_type text not null,
  minute smallint,
  added_time smallint,
  score_home smallint,
  score_away smallint,
  source_id uuid references public.sources(id) on delete set null,
  evidence_class text not null default 'OBSERVED',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.team_match_stats (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references public.matches(id) on delete cascade,
  team_id uuid not null references public.teams(id) on delete restrict,
  goals smallint,
  xg numeric(6,3),
  npxg numeric(6,3),
  shots smallint,
  shots_on_target smallint,
  possession_pct numeric(5,2),
  big_chances smallint,
  box_touches smallint,
  corners smallint,
  fouls smallint,
  field_tilt numeric(5,2),
  ppda numeric(7,3),
  extra_stats jsonb not null default '{}'::jsonb,
  provider_source_id uuid references public.sources(id) on delete restrict,
  provider_model text,
  definition_version text,
  evidence_class text not null,
  retrieved_at timestamptz not null default now(),
  coverage_notes text,
  created_at timestamptz not null default now(),
  unique (match_id, team_id, provider_source_id, provider_model, definition_version),
  check (possession_pct is null or (possession_pct >= 0 and possession_pct <= 100)),
  check (field_tilt is null or (field_tilt >= 0 and field_tilt <= 100))
);

create table if not exists public.player_match_stats (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references public.matches(id) on delete cascade,
  player_id uuid not null references public.players(id) on delete restrict,
  team_id uuid not null references public.teams(id) on delete restrict,
  minutes smallint,
  goals smallint,
  assists smallint,
  penalties_scored smallint,
  xg numeric(6,3),
  npxg numeric(6,3),
  xa numeric(6,3),
  shots smallint,
  shots_on_target smallint,
  chances_created smallint,
  big_chances_created smallint,
  touches integer,
  box_touches smallint,
  passes_attempted integer,
  passes_completed integer,
  progressive_passes smallint,
  carries smallint,
  progressive_carries smallint,
  dribbles_attempted smallint,
  dribbles_completed smallint,
  duels_attempted smallint,
  duels_won smallint,
  aerials_attempted smallint,
  aerials_won smallint,
  tackles smallint,
  interceptions smallint,
  recoveries smallint,
  pressures smallint,
  extra_stats jsonb not null default '{}'::jsonb,
  provider_source_id uuid references public.sources(id) on delete restrict,
  provider_model text,
  definition_version text,
  evidence_class text not null,
  retrieved_at timestamptz not null default now(),
  coverage_notes text,
  created_at timestamptz not null default now(),
  unique (match_id, player_id, provider_source_id, provider_model, definition_version),
  check (minutes is null or minutes >= 0)
);

create table if not exists public.research_runs (
  id uuid primary key default gen_random_uuid(),
  run_type text not null check (run_type in ('MATCH_REVIEW','PLAYER_PROFILE','TEAM_PROFILE','MANAGER_REVIEW','INTELLIGENCE_SIGNAL','RECALCULATION')),
  target_type text,
  target_id uuid,
  match_id uuid references public.matches(id) on delete set null,
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  methodology_sha text not null,
  search_protocol_version text not null,
  output_contract_version text not null,
  rating_scale_version text,
  benchmark_version text,
  data_cutoff timestamptz not null,
  status text not null check (status in ('QUEUED','RESEARCHING','QA','PUBLISHED','REJECTED','NEEDS_RESEARCH','DATA_CONFLICT','IDENTITY_BLOCKED','REVISED')),
  qa_status text,
  notes text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.evidence_items (
  id uuid primary key default gen_random_uuid(),
  research_run_id uuid references public.research_runs(id) on delete cascade,
  document_id uuid references public.source_documents(id) on delete set null,
  expert_profile_id uuid references public.expert_profiles(id) on delete set null,
  match_id uuid references public.matches(id) on delete set null,
  entity_type text not null check (entity_type in ('PLAYER','TEAM','MANAGER','MATCH')),
  entity_id uuid,
  channel text not null check (channel in ('FACT','EXPERT','FAN','TACTICAL','OFFICIAL','MODEL')),
  domain text,
  evidence_class text not null,
  claim_type text not null,
  normalized_claim text not null,
  direction text,
  pre_post_status text,
  confidence numeric(5,2),
  validation_status text,
  notes text,
  created_at timestamptz not null default now(),
  check (confidence is null or (confidence >= 0 and confidence <= 100))
);

create table if not exists public.fan_themes (
  id uuid primary key default gen_random_uuid(),
  research_run_id uuid references public.research_runs(id) on delete cascade,
  match_id uuid references public.matches(id) on delete set null,
  entity_type text not null check (entity_type in ('PLAYER','TEAM','MANAGER','MATCH')),
  entity_id uuid not null,
  theme text not null,
  direction text not null,
  community_cohort text not null,
  coverage text,
  repeated_signal_count integer,
  source_document_ids uuid[],
  caveats text,
  created_at timestamptz not null default now(),
  check (repeated_signal_count is null or repeated_signal_count >= 0)
);

create index if not exists seasons_competition_idx on public.seasons(competition_id);
create index if not exists rounds_stage_idx on public.rounds(stage_id);
create index if not exists matches_season_kickoff_idx on public.matches(season_id, kickoff_at);
create index if not exists matches_round_idx on public.matches(round_id);
create index if not exists matches_home_team_idx on public.matches(home_team_id, kickoff_at);
create index if not exists matches_away_team_idx on public.matches(away_team_id, kickoff_at);
create index if not exists player_appearances_player_idx on public.player_appearances(player_id, match_id);
create index if not exists player_appearances_team_idx on public.player_appearances(team_id, match_id);
create index if not exists match_events_match_idx on public.match_events(match_id, minute);
create index if not exists team_match_stats_match_idx on public.team_match_stats(match_id, team_id);
create index if not exists player_match_stats_player_idx on public.player_match_stats(player_id, match_id);
create index if not exists evidence_items_match_entity_idx on public.evidence_items(match_id, entity_type, entity_id);
create index if not exists evidence_items_run_idx on public.evidence_items(research_run_id);
create index if not exists evidence_items_document_idx on public.evidence_items(document_id);
create index if not exists evidence_items_expert_idx on public.evidence_items(expert_profile_id);
create index if not exists fan_themes_match_entity_idx on public.fan_themes(match_id, entity_type, entity_id);
create index if not exists fan_themes_run_idx on public.fan_themes(research_run_id);
create index if not exists research_runs_match_idx on public.research_runs(match_id, status);
create index if not exists source_documents_source_idx on public.source_documents(source_id);
create index if not exists expert_profiles_source_idx on public.expert_profiles(source_id);
create index if not exists player_team_tenures_player_idx on public.player_team_tenures(player_id, start_date desc);
create index if not exists player_team_tenures_team_idx on public.player_team_tenures(team_id, start_date desc);
create index if not exists manager_team_tenures_manager_idx on public.manager_team_tenures(manager_id, start_date desc);
create index if not exists manager_team_tenures_team_idx on public.manager_team_tenures(team_id, start_date desc);
