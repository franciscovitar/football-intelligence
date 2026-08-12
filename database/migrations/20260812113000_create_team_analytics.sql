\set ON_ERROR_STOP on

begin;

create table analytics.team_feature_snapshots (
    team_id bigint not null
        references football.teams(id) on delete cascade,
    season_id bigint not null
        references football.seasons(id) on delete cascade,
    scope_key text not null,
    window_key text not null,
    metric_name text not null,
    matches smallint not null,
    observed_matches smallint not null,
    raw_value numeric(14, 4) not null,
    adjusted_value numeric(14, 4) not null,
    percentile numeric(5, 2) not null,
    reference_sample_size integer not null,
    model_version text not null,
    calculated_at timestamptz not null,
    primary key (team_id, scope_key, window_key, metric_name, model_version),
    constraint team_feature_snapshots_scope_not_blank_check
        check (btrim(scope_key) <> ''),
    constraint team_feature_snapshots_window_key_check
        check (window_key in ('last_3', 'last_5', 'last_10', 'season')),
    constraint team_feature_snapshots_metric_not_blank_check
        check (btrim(metric_name) <> ''),
    constraint team_feature_snapshots_matches_check
        check (matches > 0),
    constraint team_feature_snapshots_observed_matches_check
        check (observed_matches > 0 and observed_matches <= matches),
    constraint team_feature_snapshots_percentile_check
        check (percentile between 0 and 100),
    constraint team_feature_snapshots_reference_sample_check
        check (reference_sample_size > 0),
    constraint team_feature_snapshots_model_version_not_blank_check
        check (btrim(model_version) <> '')
);

create index team_feature_snapshots_lookup_idx
    on analytics.team_feature_snapshots (
        season_id,
        scope_key,
        window_key,
        model_version,
        metric_name,
        percentile desc
    );

create table analytics.team_score_snapshots (
    team_id bigint not null
        references football.teams(id) on delete cascade,
    season_id bigint not null
        references football.seasons(id) on delete cascade,
    scope_key text not null,
    window_key text not null,
    matches smallint not null,
    overall_score numeric(5, 2) not null,
    confidence numeric(6, 5) not null,
    dimension_scores jsonb not null default '{}'::jsonb,
    results_process_delta numeric(6, 2) not null,
    results_process_signal text not null,
    diagnostics jsonb not null default '{}'::jsonb,
    reference_sample_size integer not null,
    current_elo numeric(8, 2) not null,
    elo_change_last_5 numeric(7, 2) not null,
    model_version text not null,
    calculated_at timestamptz not null,
    primary key (team_id, scope_key, window_key, model_version),
    constraint team_score_snapshots_scope_not_blank_check
        check (btrim(scope_key) <> ''),
    constraint team_score_snapshots_window_key_check
        check (window_key in ('last_3', 'last_5', 'last_10', 'season')),
    constraint team_score_snapshots_matches_check
        check (matches > 0),
    constraint team_score_snapshots_overall_score_check
        check (overall_score between 0 and 100),
    constraint team_score_snapshots_confidence_check
        check (confidence between 0 and 1),
    constraint team_score_snapshots_dimensions_object_check
        check (jsonb_typeof(dimension_scores) = 'object'),
    constraint team_score_snapshots_signal_check
        check (
            results_process_signal in (
                'results_above_process',
                'results_below_process',
                'results_aligned'
            )
        ),
    constraint team_score_snapshots_diagnostics_object_check
        check (jsonb_typeof(diagnostics) = 'object'),
    constraint team_score_snapshots_reference_sample_check
        check (reference_sample_size > 0),
    constraint team_score_snapshots_current_elo_check
        check (current_elo > 0),
    constraint team_score_snapshots_model_version_not_blank_check
        check (btrim(model_version) <> '')
);

create index team_score_snapshots_ranking_idx
    on analytics.team_score_snapshots (
        season_id,
        scope_key,
        window_key,
        model_version,
        overall_score desc,
        confidence desc
    );

create table analytics.team_elo_history (
    match_id bigint not null
        references football.matches(id) on delete cascade,
    team_id bigint not null
        references football.teams(id) on delete cascade,
    opponent_team_id bigint not null
        references football.teams(id) on delete cascade,
    season_id bigint not null
        references football.seasons(id) on delete cascade,
    pre_match_rating numeric(10, 4) not null,
    opponent_pre_match_rating numeric(10, 4) not null,
    expected_result numeric(7, 6) not null,
    actual_result numeric(2, 1) not null,
    post_match_rating numeric(10, 4) not null,
    model_version text not null,
    calculated_at timestamptz not null,
    primary key (match_id, team_id, model_version),
    constraint team_elo_history_distinct_teams_check
        check (team_id <> opponent_team_id),
    constraint team_elo_history_ratings_check
        check (
            pre_match_rating > 0
            and opponent_pre_match_rating > 0
            and post_match_rating > 0
        ),
    constraint team_elo_history_expected_check
        check (expected_result between 0 and 1),
    constraint team_elo_history_actual_check
        check (actual_result in (0, 0.5, 1)),
    constraint team_elo_history_model_version_not_blank_check
        check (btrim(model_version) <> '')
);

create index team_elo_history_team_season_idx
    on analytics.team_elo_history (team_id, season_id, model_version, match_id desc);

revoke all on all tables in schema analytics from public;

commit;
