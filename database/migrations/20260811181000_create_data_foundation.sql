begin;

create schema if not exists football;
create schema if not exists ingestion;

revoke all on schema football from public;
revoke all on schema ingestion from public;

create table ingestion.providers (
    id bigint generated always as identity primary key,
    code text not null unique,
    display_name text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    constraint providers_code_format_check
        check (code ~ '^[a-z0-9][a-z0-9-]*$'),
    constraint providers_display_name_not_blank_check
        check (btrim(display_name) <> '')
);

create table football.competitions (
    id bigint generated always as identity primary key,
    code text not null unique,
    name text not null,
    country_code text,
    kind text not null default 'league',
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint competitions_code_format_check
        check (code ~ '^[A-Z0-9_]+$'),
    constraint competitions_name_not_blank_check
        check (btrim(name) <> ''),
    constraint competitions_country_code_check
        check (country_code is null or country_code ~ '^[A-Z]{3}$'),
    constraint competitions_kind_check
        check (kind in ('league', 'cup', 'international'))
);

create table football.seasons (
    id bigint generated always as identity primary key,
    competition_id bigint not null
        references football.competitions(id) on delete cascade,
    label text not null,
    starts_on date,
    ends_on date,
    is_current boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint seasons_label_not_blank_check
        check (btrim(label) <> ''),
    constraint seasons_date_order_check
        check (starts_on is null or ends_on is null or ends_on >= starts_on),
    constraint seasons_competition_label_key
        unique (competition_id, label)
);

create unique index seasons_one_current_per_competition_idx
    on football.seasons (competition_id)
    where is_current;

create table football.teams (
    id bigint generated always as identity primary key,
    name text not null,
    short_name text,
    country_code text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint teams_name_not_blank_check
        check (btrim(name) <> ''),
    constraint teams_short_name_not_blank_check
        check (short_name is null or btrim(short_name) <> ''),
    constraint teams_country_code_check
        check (country_code is null or country_code ~ '^[A-Z]{3}$')
);

create table football.players (
    id bigint generated always as identity primary key,
    display_name text not null,
    first_name text,
    last_name text,
    date_of_birth date,
    nationality_code text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint players_display_name_not_blank_check
        check (btrim(display_name) <> ''),
    constraint players_first_name_not_blank_check
        check (first_name is null or btrim(first_name) <> ''),
    constraint players_last_name_not_blank_check
        check (last_name is null or btrim(last_name) <> ''),
    constraint players_nationality_code_check
        check (nationality_code is null or nationality_code ~ '^[A-Z]{3}$')
);

create table football.matches (
    id bigint generated always as identity primary key,
    season_id bigint not null
        references football.seasons(id) on delete restrict,
    home_team_id bigint not null
        references football.teams(id) on delete restrict,
    away_team_id bigint not null
        references football.teams(id) on delete restrict,
    kickoff_at timestamptz,
    status text not null default 'scheduled',
    round_name text,
    venue_name text,
    home_score smallint,
    away_score smallint,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint matches_distinct_teams_check
        check (home_team_id <> away_team_id),
    constraint matches_status_check
        check (
            status in (
                'scheduled',
                'live',
                'finished',
                'postponed',
                'cancelled',
                'abandoned',
                'unknown'
            )
        ),
    constraint matches_home_score_check
        check (home_score is null or home_score >= 0),
    constraint matches_away_score_check
        check (away_score is null or away_score >= 0),
    constraint matches_finished_score_check
        check (
            status <> 'finished'
            or (home_score is not null and away_score is not null)
        )
);

create index matches_season_kickoff_idx
    on football.matches (season_id, kickoff_at desc);

create index matches_home_team_kickoff_idx
    on football.matches (home_team_id, kickoff_at desc);

create index matches_away_team_kickoff_idx
    on football.matches (away_team_id, kickoff_at desc);

create table football.competition_provider_ids (
    provider_id bigint not null
        references ingestion.providers(id) on delete restrict,
    competition_id bigint not null
        references football.competitions(id) on delete cascade,
    external_id text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (provider_id, competition_id),
    constraint competition_provider_ids_external_not_blank_check
        check (btrim(external_id) <> ''),
    constraint competition_provider_ids_external_key
        unique (provider_id, external_id)
);

create table football.team_provider_ids (
    provider_id bigint not null
        references ingestion.providers(id) on delete restrict,
    team_id bigint not null
        references football.teams(id) on delete cascade,
    external_id text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (provider_id, team_id),
    constraint team_provider_ids_external_not_blank_check
        check (btrim(external_id) <> ''),
    constraint team_provider_ids_external_key
        unique (provider_id, external_id)
);

create table football.player_provider_ids (
    provider_id bigint not null
        references ingestion.providers(id) on delete restrict,
    player_id bigint not null
        references football.players(id) on delete cascade,
    external_id text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (provider_id, player_id),
    constraint player_provider_ids_external_not_blank_check
        check (btrim(external_id) <> ''),
    constraint player_provider_ids_external_key
        unique (provider_id, external_id)
);

create table football.match_provider_ids (
    provider_id bigint not null
        references ingestion.providers(id) on delete restrict,
    match_id bigint not null
        references football.matches(id) on delete cascade,
    external_id text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (provider_id, match_id),
    constraint match_provider_ids_external_not_blank_check
        check (btrim(external_id) <> ''),
    constraint match_provider_ids_external_key
        unique (provider_id, external_id)
);

create table football.team_match_stats (
    match_id bigint not null
        references football.matches(id) on delete cascade,
    team_id bigint not null
        references football.teams(id) on delete restrict,
    possession_pct numeric(5, 2),
    shots_total smallint,
    shots_on_target smallint,
    shots_inside_box smallint,
    shots_outside_box smallint,
    blocked_shots smallint,
    corners smallint,
    offsides smallint,
    fouls smallint,
    yellow_cards smallint,
    red_cards smallint,
    passes_total integer,
    passes_accurate integer,
    goalkeeper_saves smallint,
    updated_at timestamptz not null default now(),
    primary key (match_id, team_id),
    constraint team_match_stats_possession_check
        check (possession_pct is null or possession_pct between 0 and 100),
    constraint team_match_stats_shots_total_check
        check (shots_total is null or shots_total >= 0),
    constraint team_match_stats_shots_on_target_check
        check (shots_on_target is null or shots_on_target >= 0),
    constraint team_match_stats_shots_inside_box_check
        check (shots_inside_box is null or shots_inside_box >= 0),
    constraint team_match_stats_shots_outside_box_check
        check (shots_outside_box is null or shots_outside_box >= 0),
    constraint team_match_stats_blocked_shots_check
        check (blocked_shots is null or blocked_shots >= 0),
    constraint team_match_stats_corners_check
        check (corners is null or corners >= 0),
    constraint team_match_stats_offsides_check
        check (offsides is null or offsides >= 0),
    constraint team_match_stats_fouls_check
        check (fouls is null or fouls >= 0),
    constraint team_match_stats_yellow_cards_check
        check (yellow_cards is null or yellow_cards >= 0),
    constraint team_match_stats_red_cards_check
        check (red_cards is null or red_cards >= 0),
    constraint team_match_stats_passes_total_check
        check (passes_total is null or passes_total >= 0),
    constraint team_match_stats_passes_accurate_check
        check (passes_accurate is null or passes_accurate >= 0),
    constraint team_match_stats_goalkeeper_saves_check
        check (goalkeeper_saves is null or goalkeeper_saves >= 0),
    constraint team_match_stats_shots_consistency_check
        check (
            shots_on_target is null
            or shots_total is null
            or shots_on_target <= shots_total
        ),
    constraint team_match_stats_passes_consistency_check
        check (
            passes_accurate is null
            or passes_total is null
            or passes_accurate <= passes_total
        )
);

create index team_match_stats_team_match_idx
    on football.team_match_stats (team_id, match_id);

create table football.player_appearances (
    match_id bigint not null
        references football.matches(id) on delete cascade,
    player_id bigint not null
        references football.players(id) on delete restrict,
    team_id bigint not null
        references football.teams(id) on delete restrict,
    minutes smallint,
    started boolean,
    captain boolean,
    shirt_number smallint,
    listed_position text,
    updated_at timestamptz not null default now(),
    primary key (match_id, player_id),
    constraint player_appearances_minutes_check
        check (minutes is null or minutes between 0 and 130),
    constraint player_appearances_shirt_number_check
        check (shirt_number is null or shirt_number between 1 and 999),
    constraint player_appearances_position_not_blank_check
        check (listed_position is null or btrim(listed_position) <> '')
);

create index player_appearances_player_match_idx
    on football.player_appearances (player_id, match_id);

create index player_appearances_team_match_idx
    on football.player_appearances (team_id, match_id);

create table football.player_match_stats (
    match_id bigint not null,
    player_id bigint not null,
    goals smallint,
    assists smallint,
    shots_total smallint,
    shots_on_target smallint,
    passes_total integer,
    passes_accurate integer,
    key_passes smallint,
    tackles smallint,
    blocks smallint,
    interceptions smallint,
    clearances smallint,
    dribbles_attempted smallint,
    dribbles_successful smallint,
    duels_total smallint,
    duels_won smallint,
    fouls_drawn smallint,
    fouls_committed smallint,
    yellow_cards smallint,
    red_cards smallint,
    saves smallint,
    updated_at timestamptz not null default now(),
    primary key (match_id, player_id),
    constraint player_match_stats_appearance_fk
        foreign key (match_id, player_id)
        references football.player_appearances(match_id, player_id)
        on delete cascade,
    constraint player_match_stats_goals_check
        check (goals is null or goals >= 0),
    constraint player_match_stats_assists_check
        check (assists is null or assists >= 0),
    constraint player_match_stats_shots_total_check
        check (shots_total is null or shots_total >= 0),
    constraint player_match_stats_shots_on_target_check
        check (shots_on_target is null or shots_on_target >= 0),
    constraint player_match_stats_passes_total_check
        check (passes_total is null or passes_total >= 0),
    constraint player_match_stats_passes_accurate_check
        check (passes_accurate is null or passes_accurate >= 0),
    constraint player_match_stats_key_passes_check
        check (key_passes is null or key_passes >= 0),
    constraint player_match_stats_tackles_check
        check (tackles is null or tackles >= 0),
    constraint player_match_stats_blocks_check
        check (blocks is null or blocks >= 0),
    constraint player_match_stats_interceptions_check
        check (interceptions is null or interceptions >= 0),
    constraint player_match_stats_clearances_check
        check (clearances is null or clearances >= 0),
    constraint player_match_stats_dribbles_attempted_check
        check (dribbles_attempted is null or dribbles_attempted >= 0),
    constraint player_match_stats_dribbles_successful_check
        check (dribbles_successful is null or dribbles_successful >= 0),
    constraint player_match_stats_duels_total_check
        check (duels_total is null or duels_total >= 0),
    constraint player_match_stats_duels_won_check
        check (duels_won is null or duels_won >= 0),
    constraint player_match_stats_fouls_drawn_check
        check (fouls_drawn is null or fouls_drawn >= 0),
    constraint player_match_stats_fouls_committed_check
        check (fouls_committed is null or fouls_committed >= 0),
    constraint player_match_stats_yellow_cards_check
        check (yellow_cards is null or yellow_cards >= 0),
    constraint player_match_stats_red_cards_check
        check (red_cards is null or red_cards >= 0),
    constraint player_match_stats_saves_check
        check (saves is null or saves >= 0),
    constraint player_match_stats_shots_consistency_check
        check (
            shots_on_target is null
            or shots_total is null
            or shots_on_target <= shots_total
        ),
    constraint player_match_stats_passes_consistency_check
        check (
            passes_accurate is null
            or passes_total is null
            or passes_accurate <= passes_total
        ),
    constraint player_match_stats_dribbles_consistency_check
        check (
            dribbles_successful is null
            or dribbles_attempted is null
            or dribbles_successful <= dribbles_attempted
        ),
    constraint player_match_stats_duels_consistency_check
        check (
            duels_won is null
            or duels_total is null
            or duels_won <= duels_total
        )
);

create index player_match_stats_player_match_idx
    on football.player_match_stats (player_id, match_id);

create or replace function football.enforce_match_team_membership()
returns trigger
language plpgsql
set search_path = pg_catalog, football
as $$
begin
    if not exists (
        select 1
        from football.matches as m
        where m.id = new.match_id
          and new.team_id in (m.home_team_id, m.away_team_id)
    ) then
        raise exception
            'team % is not part of match %',
            new.team_id,
            new.match_id
            using errcode = '23514';
    end if;

    return new;
end;
$$;

create trigger team_match_stats_match_team_check
before insert or update of match_id, team_id
on football.team_match_stats
for each row
execute function football.enforce_match_team_membership();

create trigger player_appearances_match_team_check
before insert or update of match_id, team_id
on football.player_appearances
for each row
execute function football.enforce_match_team_membership();

create table ingestion.ingestion_runs (
    id bigint generated always as identity primary key,
    provider_id bigint not null
        references ingestion.providers(id) on delete restrict,
    job_name text not null,
    trigger_kind text not null default 'manual',
    status text not null default 'running',
    scope jsonb not null default '{}'::jsonb,
    request_count integer not null default 0,
    rows_written integer not null default 0,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    error_code text,
    error_message text,
    metadata jsonb not null default '{}'::jsonb,
    constraint ingestion_runs_job_name_not_blank_check
        check (btrim(job_name) <> ''),
    constraint ingestion_runs_trigger_kind_check
        check (trigger_kind in ('manual', 'schedule', 'retry', 'test')),
    constraint ingestion_runs_status_check
        check (status in ('running', 'succeeded', 'failed', 'partial')),
    constraint ingestion_runs_scope_object_check
        check (jsonb_typeof(scope) = 'object'),
    constraint ingestion_runs_metadata_object_check
        check (jsonb_typeof(metadata) = 'object'),
    constraint ingestion_runs_request_count_check
        check (request_count >= 0),
    constraint ingestion_runs_rows_written_check
        check (rows_written >= 0),
    constraint ingestion_runs_finished_state_check
        check (
            (status = 'running' and finished_at is null)
            or (status <> 'running' and finished_at is not null)
        )
);

create index ingestion_runs_provider_started_idx
    on ingestion.ingestion_runs (provider_id, started_at desc);

create table ingestion.raw_objects (
    id bigint generated always as identity primary key,
    ingestion_run_id bigint not null
        references ingestion.ingestion_runs(id) on delete cascade,
    storage_bucket text not null,
    storage_path text not null,
    endpoint text not null,
    request_fingerprint text,
    fetched_at timestamptz not null default now(),
    http_status smallint,
    content_type text,
    content_encoding text,
    payload_sha256 text,
    byte_size bigint,
    metadata jsonb not null default '{}'::jsonb,
    constraint raw_objects_bucket_not_blank_check
        check (btrim(storage_bucket) <> ''),
    constraint raw_objects_path_not_blank_check
        check (btrim(storage_path) <> ''),
    constraint raw_objects_endpoint_not_blank_check
        check (btrim(endpoint) <> ''),
    constraint raw_objects_request_fingerprint_not_blank_check
        check (
            request_fingerprint is null
            or btrim(request_fingerprint) <> ''
        ),
    constraint raw_objects_http_status_check
        check (http_status is null or http_status between 100 and 599),
    constraint raw_objects_sha256_check
        check (
            payload_sha256 is null
            or payload_sha256 ~ '^[0-9a-f]{64}$'
        ),
    constraint raw_objects_byte_size_check
        check (byte_size is null or byte_size >= 0),
    constraint raw_objects_metadata_object_check
        check (jsonb_typeof(metadata) = 'object'),
    constraint raw_objects_storage_key
        unique (storage_bucket, storage_path)
);

create index raw_objects_run_fetched_idx
    on ingestion.raw_objects (ingestion_run_id, fetched_at);

create table ingestion.data_capabilities (
    provider_id bigint not null
        references ingestion.providers(id) on delete cascade,
    entity_type text not null,
    metric_name text not null,
    availability text not null default 'unknown',
    sample_size integer not null default 0,
    non_null_count integer not null default 0,
    observed_at timestamptz not null default now(),
    notes text,
    primary key (provider_id, entity_type, metric_name),
    constraint data_capabilities_entity_type_check
        check (
            entity_type in (
                'competition',
                'team',
                'player',
                'match',
                'team_match_stats',
                'player_match_stats'
            )
        ),
    constraint data_capabilities_metric_name_not_blank_check
        check (btrim(metric_name) <> ''),
    constraint data_capabilities_availability_check
        check (
            availability in (
                'unknown',
                'available',
                'partial',
                'unavailable'
            )
        ),
    constraint data_capabilities_sample_size_check
        check (sample_size >= 0),
    constraint data_capabilities_non_null_count_check
        check (non_null_count >= 0 and non_null_count <= sample_size),
    constraint data_capabilities_notes_not_blank_check
        check (notes is null or btrim(notes) <> '')
);

commit;
