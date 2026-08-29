-- Football App V1 — researched intelligence and revision layer.

create table if not exists public.player_match_reviews (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references public.matches(id) on delete cascade,
  player_id uuid not null references public.players(id) on delete restrict,
  team_id uuid not null references public.teams(id) on delete restrict,
  research_run_id uuid not null references public.research_runs(id) on delete restrict,
  review_version integer not null,
  facts_score numeric(3,1),
  expert_score numeric(3,1),
  fan_score numeric(3,1),
  final_score numeric(3,1) not null,
  confidence smallint not null,
  evidence_status text not null,
  facts_coverage smallint,
  expert_coverage smallint,
  fan_coverage smallint,
  tactical_coverage smallint,
  role_label text,
  summary text not null,
  positive_notes jsonb not null default '[]'::jsonb,
  negative_notes jsonb not null default '[]'::jsonb,
  evidence_mix jsonb not null default '{}'::jsonb,
  methodology_sha text not null,
  rating_scale_version text not null,
  benchmark_version text not null,
  status text not null,
  published_at timestamptz,
  supersedes_review_id uuid references public.player_match_reviews(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (match_id, player_id, review_version),
  check (final_score between 0 and 10),
  check (facts_score is null or facts_score between 0 and 10),
  check (expert_score is null or expert_score between 0 and 10),
  check (fan_score is null or fan_score between 0 and 10),
  check (confidence between 0 and 100),
  check (facts_coverage is null or facts_coverage between 0 and 100),
  check (expert_coverage is null or expert_coverage between 0 and 100),
  check (fan_coverage is null or fan_coverage between 0 and 100),
  check (tactical_coverage is null or tactical_coverage between 0 and 100)
);

create table if not exists public.team_match_reviews (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references public.matches(id) on delete cascade,
  team_id uuid not null references public.teams(id) on delete restrict,
  research_run_id uuid not null references public.research_runs(id) on delete restrict,
  review_version integer not null,
  facts_score numeric(3,1),
  expert_score numeric(3,1),
  fan_score numeric(3,1),
  final_score numeric(3,1) not null,
  confidence smallint not null,
  evidence_status text not null,
  facts_coverage smallint,
  expert_coverage smallint,
  fan_coverage smallint,
  tactical_coverage smallint,
  attack_score numeric(3,1),
  creation_score numeric(3,1),
  control_score numeric(3,1),
  defence_score numeric(3,1),
  pressing_score numeric(3,1),
  offensive_transition_score numeric(3,1),
  defensive_transition_score numeric(3,1),
  set_pieces_score numeric(3,1),
  summary text not null,
  strengths jsonb not null default '[]'::jsonb,
  concerns jsonb not null default '[]'::jsonb,
  evidence_mix jsonb not null default '{}'::jsonb,
  methodology_sha text not null,
  rating_scale_version text not null,
  benchmark_version text not null,
  status text not null,
  published_at timestamptz,
  supersedes_review_id uuid references public.team_match_reviews(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (match_id, team_id, review_version),
  check (final_score between 0 and 10),
  check (confidence between 0 and 100)
);

create table if not exists public.manager_match_reviews (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references public.matches(id) on delete cascade,
  manager_id uuid not null references public.managers(id) on delete restrict,
  team_id uuid not null references public.teams(id) on delete restrict,
  research_run_id uuid not null references public.research_runs(id) on delete restrict,
  review_version integer not null,
  facts_score numeric(3,1),
  expert_score numeric(3,1),
  fan_score numeric(3,1),
  final_score numeric(3,1) not null,
  confidence smallint not null,
  evidence_status text not null,
  initial_plan_score numeric(3,1),
  adaptation_score numeric(3,1),
  substitutions_score numeric(3,1),
  initial_plan text,
  adjustments text,
  what_worked jsonb not null default '[]'::jsonb,
  what_failed jsonb not null default '[]'::jsonb,
  summary text not null,
  evidence_mix jsonb not null default '{}'::jsonb,
  methodology_sha text not null,
  rating_scale_version text not null,
  benchmark_version text not null,
  status text not null,
  published_at timestamptz,
  supersedes_review_id uuid references public.manager_match_reviews(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (match_id, manager_id, review_version),
  check (final_score between 0 and 10),
  check (confidence between 0 and 100)
);

create table if not exists public.player_level_estimates (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references public.players(id) on delete cascade,
  scope_start date,
  scope_end date,
  score_0_100 numeric(5,2) not null,
  confidence smallint not null,
  evidence_status text not null,
  summary text not null,
  research_run_id uuid not null references public.research_runs(id) on delete restrict,
  methodology_sha text not null,
  status text not null,
  published_at timestamptz,
  supersedes_id uuid references public.player_level_estimates(id) on delete set null,
  created_at timestamptz not null default now(),
  check (score_0_100 between 0 and 100),
  check (confidence between 0 and 100)
);

create table if not exists public.player_dna_estimates (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references public.players(id) on delete cascade,
  attribute text not null check (attribute in ('PAC','SHO','PAS','CRE','DRI','DEF','PHY','AER','PRESS','TACT','TECH')),
  score_low numeric(5,2),
  score_high numeric(5,2),
  display_score numeric(5,2),
  confidence smallint not null,
  evidence_status text not null,
  reason text not null,
  scope_start date,
  scope_end date,
  research_run_id uuid not null references public.research_runs(id) on delete restrict,
  methodology_sha text not null,
  status text not null,
  published_at timestamptz,
  supersedes_id uuid references public.player_dna_estimates(id) on delete set null,
  created_at timestamptz not null default now(),
  check (score_low is null or score_low between 0 and 100),
  check (score_high is null or score_high between 0 and 100),
  check (display_score is null or display_score between 0 and 100),
  check (confidence between 0 and 100)
);

create table if not exists public.player_archetypes (
  id uuid primary key default gen_random_uuid(),
  player_id uuid not null references public.players(id) on delete cascade,
  archetype text not null,
  rank_order smallint not null default 1,
  confidence smallint not null,
  summary text not null,
  research_run_id uuid not null references public.research_runs(id) on delete restrict,
  methodology_sha text not null,
  status text not null,
  published_at timestamptz,
  supersedes_id uuid references public.player_archetypes(id) on delete set null,
  created_at timestamptz not null default now(),
  check (confidence between 0 and 100)
);

create table if not exists public.intelligence_signals (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null,
  entity_id uuid not null,
  signal_type text not null,
  scope_start date,
  scope_end date,
  status text not null check (status in ('CANDIDATE','SUPPORTED','PARTIAL','MIXED','NOT_SUPPORTED','EXPIRED')),
  score_or_strength numeric,
  confidence smallint not null,
  baseline_description text not null,
  rationale text not null,
  research_run_id uuid not null references public.research_runs(id) on delete restrict,
  methodology_sha text not null,
  published_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz not null default now(),
  check (confidence between 0 and 100)
);

create table if not exists public.rating_benchmarks (
  id uuid primary key default gen_random_uuid(),
  rating_scale_version text not null,
  benchmark_version text not null,
  entity_type text not null,
  entity_id uuid,
  match_id uuid references public.matches(id) on delete set null,
  role_family text,
  target_score numeric(3,1) not null,
  description text not null,
  reference_review_ids uuid[] not null default '{}',
  anchor_status text not null default 'PROVISIONAL_ANCHOR' check (anchor_status in ('PRIMARY_ANCHOR','SECONDARY_ANCHOR','PROVISIONAL_ANCHOR','RETIRED')),
  active boolean not null default true,
  activated_at timestamptz,
  retired_at timestamptz,
  retirement_reason text,
  created_at timestamptz not null default now(),
  check (target_score between 0 and 10)
);

create table if not exists public.rating_revisions (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null,
  old_review_id uuid not null,
  new_review_id uuid not null,
  reason text not null,
  changed_at timestamptz not null default now(),
  methodology_change boolean not null default false,
  data_correction boolean not null default false,
  metadata jsonb not null default '{}'::jsonb
);

create index if not exists player_match_reviews_player_match_idx on public.player_match_reviews(player_id, match_id);
create index if not exists player_match_reviews_status_idx on public.player_match_reviews(status, published_at desc);
create index if not exists player_match_reviews_run_idx on public.player_match_reviews(research_run_id);
create index if not exists player_match_reviews_team_idx on public.player_match_reviews(team_id, match_id);
create index if not exists player_match_reviews_supersedes_idx on public.player_match_reviews(supersedes_review_id) where supersedes_review_id is not null;
create index if not exists team_match_reviews_team_match_idx on public.team_match_reviews(team_id, match_id);
create index if not exists team_match_reviews_status_idx on public.team_match_reviews(status, published_at desc);
create index if not exists team_match_reviews_run_idx on public.team_match_reviews(research_run_id);
create index if not exists team_match_reviews_supersedes_idx on public.team_match_reviews(supersedes_review_id) where supersedes_review_id is not null;
create index if not exists manager_match_reviews_manager_match_idx on public.manager_match_reviews(manager_id, match_id);
create index if not exists manager_match_reviews_team_idx on public.manager_match_reviews(team_id, match_id);
create index if not exists manager_match_reviews_status_idx on public.manager_match_reviews(status, published_at desc);
create index if not exists manager_match_reviews_run_idx on public.manager_match_reviews(research_run_id);
create index if not exists manager_match_reviews_supersedes_idx on public.manager_match_reviews(supersedes_review_id) where supersedes_review_id is not null;
create index if not exists player_level_estimates_player_idx on public.player_level_estimates(player_id, published_at desc);
create index if not exists player_level_estimates_run_idx on public.player_level_estimates(research_run_id);
create index if not exists player_level_estimates_supersedes_idx on public.player_level_estimates(supersedes_id) where supersedes_id is not null;
create index if not exists player_dna_estimates_player_idx on public.player_dna_estimates(player_id, attribute, published_at desc);
create index if not exists player_dna_estimates_run_idx on public.player_dna_estimates(research_run_id);
create index if not exists player_dna_estimates_supersedes_idx on public.player_dna_estimates(supersedes_id) where supersedes_id is not null;
create index if not exists player_archetypes_player_idx on public.player_archetypes(player_id, rank_order);
create index if not exists player_archetypes_run_idx on public.player_archetypes(research_run_id);
create index if not exists intelligence_signals_entity_idx on public.intelligence_signals(entity_type, entity_id, signal_type, published_at desc);
create index if not exists intelligence_signals_run_idx on public.intelligence_signals(research_run_id);
create index if not exists rating_benchmarks_score_idx on public.rating_benchmarks(entity_type, role_family, target_score);
create index if not exists rating_benchmarks_match_idx on public.rating_benchmarks(match_id);
