\set ON_ERROR_STOP on

begin;

-- Block 16: a season-aggregate observation table, distinct from
-- football.player_match_stats (per-match). Some real sources (e.g. the
-- permitted season-summary sources may only publish a season rollup, with
-- no match-by-match breakdown -- last-3/last-5/last-10 form windows cannot
-- be derived from this table, only a `season` window.
--
-- Provenance is carried inline (source, source_url, retrieved_at,
-- semantic_version) rather than through ingestion.raw_objects/
-- ingestion_runs: this table is populated by a one-off, manually-run
-- curated-snapshot job (analytics' collect_real_snapshot.py), not the
-- scheduled provider-sync pipeline those tables track. A (player, season,
-- source) row is unique, not (player, season) alone, so a second source's
-- season-aggregate claim is retained alongside the first rather than
-- averaged or silently overwritten -- matching the "never average
-- disagreeing sources" rule the rest of the project already follows for
-- provider observations.
create table football.player_season_stats (
    id bigint generated always as identity primary key,
    player_id bigint not null
        references football.players(id) on delete cascade,
    season_id bigint not null
        references football.seasons(id) on delete cascade,
    minutes integer,
    starts smallint,
    appearances smallint,
    goals smallint,
    assists smallint,
    clean_sheets smallint,
    goals_conceded smallint,
    own_goals smallint,
    penalties_saved smallint,
    penalties_missed smallint,
    yellow_cards smallint,
    red_cards smallint,
    saves smallint,
    bonus smallint,
    bps integer,
    influence numeric(8, 1),
    creativity numeric(8, 1),
    threat numeric(8, 1),
    ict_index numeric(8, 1),
    tackles smallint,
    recoveries smallint,
    clearances_blocks_interceptions smallint,
    defensive_contribution smallint,
    expected_goals numeric(6, 2),
    expected_assists numeric(6, 2),
    expected_goal_involvements numeric(6, 2),
    expected_goals_conceded numeric(6, 2),
    source text not null,
    source_url text not null,
    retrieved_at timestamptz not null,
    semantic_version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint player_season_stats_source_key
        unique (player_id, season_id, source),
    constraint player_season_stats_source_not_blank_check
        check (btrim(source) <> ''),
    constraint player_season_stats_source_url_not_blank_check
        check (btrim(source_url) <> ''),
    constraint player_season_stats_semantic_version_not_blank_check
        check (btrim(semantic_version) <> ''),
    constraint player_season_stats_minutes_check
        check (minutes is null or minutes >= 0),
    constraint player_season_stats_starts_check
        check (starts is null or starts >= 0),
    constraint player_season_stats_appearances_check
        check (appearances is null or appearances >= 0),
    constraint player_season_stats_goals_check
        check (goals is null or goals >= 0),
    constraint player_season_stats_assists_check
        check (assists is null or assists >= 0),
    constraint player_season_stats_clean_sheets_check
        check (clean_sheets is null or clean_sheets >= 0),
    constraint player_season_stats_goals_conceded_check
        check (goals_conceded is null or goals_conceded >= 0),
    constraint player_season_stats_own_goals_check
        check (own_goals is null or own_goals >= 0),
    constraint player_season_stats_penalties_saved_check
        check (penalties_saved is null or penalties_saved >= 0),
    constraint player_season_stats_penalties_missed_check
        check (penalties_missed is null or penalties_missed >= 0),
    constraint player_season_stats_yellow_cards_check
        check (yellow_cards is null or yellow_cards >= 0),
    constraint player_season_stats_red_cards_check
        check (red_cards is null or red_cards >= 0),
    constraint player_season_stats_saves_check
        check (saves is null or saves >= 0),
    constraint player_season_stats_bonus_check
        check (bonus is null or bonus >= 0),
    constraint player_season_stats_bps_check
        check (bps is null or bps >= 0),
    constraint player_season_stats_tackles_check
        check (tackles is null or tackles >= 0),
    constraint player_season_stats_recoveries_check
        check (recoveries is null or recoveries >= 0),
    constraint player_season_stats_cbi_check
        check (clearances_blocks_interceptions is null or clearances_blocks_interceptions >= 0),
    constraint player_season_stats_defensive_contribution_check
        check (defensive_contribution is null or defensive_contribution >= 0),
    constraint player_season_stats_expected_goals_check
        check (expected_goals is null or expected_goals >= 0),
    constraint player_season_stats_expected_assists_check
        check (expected_assists is null or expected_assists >= 0),
    constraint player_season_stats_expected_goal_involvements_check
        check (expected_goal_involvements is null or expected_goal_involvements >= 0),
    constraint player_season_stats_expected_goals_conceded_check
        check (expected_goals_conceded is null or expected_goals_conceded >= 0)
);

create index player_season_stats_season_idx
    on football.player_season_stats (season_id, player_id);

revoke all on football.player_season_stats from public;

commit;
