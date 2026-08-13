\set ON_ERROR_STOP on

begin;

create table analytics.world_radar_snapshots (
    provider_code text not null,
    provider_player_id text not null,
    player_name text not null,
    team_name text,
    competition_code text not null,
    competition_name text not null,
    country text not null,
    season_label text not null,
    position text,
    appearances smallint,
    minutes integer,
    goals smallint,
    assists smallint,
    metrics jsonb not null default '{}'::jsonb,
    radar_score numeric(5, 2) not null,
    confidence numeric(6, 5) not null,
    reasons jsonb not null default '[]'::jsonb,
    source_lists jsonb not null default '[]'::jsonb,
    model_version text not null,
    calculated_at timestamptz not null,
    primary key (
        provider_code, provider_player_id, competition_code, season_label, model_version
    ),
    constraint world_radar_provider_code_not_blank_check
        check (btrim(provider_code) <> ''),
    constraint world_radar_provider_player_id_not_blank_check
        check (btrim(provider_player_id) <> ''),
    constraint world_radar_player_name_not_blank_check
        check (btrim(player_name) <> ''),
    constraint world_radar_competition_code_not_blank_check
        check (btrim(competition_code) <> ''),
    constraint world_radar_competition_name_not_blank_check
        check (btrim(competition_name) <> ''),
    constraint world_radar_country_not_blank_check
        check (btrim(country) <> ''),
    constraint world_radar_season_label_not_blank_check
        check (btrim(season_label) <> ''),
    constraint world_radar_appearances_check
        check (appearances is null or appearances >= 0),
    constraint world_radar_minutes_check
        check (minutes is null or minutes >= 0),
    constraint world_radar_goals_check
        check (goals is null or goals >= 0),
    constraint world_radar_assists_check
        check (assists is null or assists >= 0),
    constraint world_radar_metrics_object_check
        check (jsonb_typeof(metrics) = 'object'),
    constraint world_radar_score_check
        check (radar_score between 0 and 100),
    constraint world_radar_confidence_check
        check (confidence between 0 and 1),
    constraint world_radar_reasons_array_check
        check (jsonb_typeof(reasons) = 'array'),
    constraint world_radar_source_lists_array_check
        check (jsonb_typeof(source_lists) = 'array'),
    constraint world_radar_model_version_not_blank_check
        check (btrim(model_version) <> '')
);

create index world_radar_ranking_idx
    on analytics.world_radar_snapshots (
        competition_code,
        season_label,
        model_version,
        radar_score desc,
        confidence desc
    );

-- World Radar candidates are external to the core league graph: no foreign
-- keys into football.players/football.teams, and this table must never be
-- used to fuzzy-link a candidate to an existing core player identity.

revoke all on analytics.world_radar_snapshots from public;

commit;
