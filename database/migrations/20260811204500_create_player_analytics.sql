\set ON_ERROR_STOP on

begin;

create schema if not exists analytics;

revoke all on schema analytics from public;

create table analytics.player_feature_snapshots (
    player_id bigint not null
        references football.players(id) on delete cascade,
    scope_key text not null,
    window text not null,
    role text not null,
    metric_name text not null,
    minutes integer not null,
    appearances smallint not null,
    raw_per90 numeric(12, 4) not null,
    adjusted_per90 numeric(12, 4) not null,
    percentile numeric(5, 2) not null,
    reference_sample_size integer not null,
    model_version text not null,
    calculated_at timestamptz not null,
    primary key (
        player_id,
        scope_key,
        window,
        metric_name,
        model_version
    ),
    constraint player_feature_snapshots_scope_not_blank_check
        check (btrim(scope_key) <> ''),
    constraint player_feature_snapshots_window_check
        check (window in ('last_3', 'last_5', 'last_10', 'season')),
    constraint player_feature_snapshots_role_check
        check (role in ('goalkeeper', 'defender', 'midfielder', 'forward')),
    constraint player_feature_snapshots_metric_not_blank_check
        check (btrim(metric_name) <> ''),
    constraint player_feature_snapshots_minutes_check
        check (minutes > 0),
    constraint player_feature_snapshots_appearances_check
        check (appearances > 0),
    constraint player_feature_snapshots_percentile_check
        check (percentile between 0 and 100),
    constraint player_feature_snapshots_reference_sample_check
        check (reference_sample_size > 0),
    constraint player_feature_snapshots_model_version_not_blank_check
        check (btrim(model_version) <> '')
);

create index player_feature_snapshots_lookup_idx
    on analytics.player_feature_snapshots (
        scope_key,
        window,
        role,
        model_version,
        metric_name,
        percentile desc
    );

create table analytics.player_score_snapshots (
    player_id bigint not null
        references football.players(id) on delete cascade,
    scope_key text not null,
    window text not null,
    role text not null,
    role_confidence numeric(6, 5) not null,
    minutes integer not null,
    appearances smallint not null,
    overall_score numeric(5, 2) not null,
    confidence numeric(6, 5) not null,
    dimension_scores jsonb not null default '{}'::jsonb,
    reference_sample_size integer not null,
    model_version text not null,
    calculated_at timestamptz not null,
    primary key (
        player_id,
        scope_key,
        window,
        model_version
    ),
    constraint player_score_snapshots_scope_not_blank_check
        check (btrim(scope_key) <> ''),
    constraint player_score_snapshots_window_check
        check (window in ('last_3', 'last_5', 'last_10', 'season')),
    constraint player_score_snapshots_role_check
        check (role in ('goalkeeper', 'defender', 'midfielder', 'forward')),
    constraint player_score_snapshots_role_confidence_check
        check (role_confidence between 0 and 1),
    constraint player_score_snapshots_minutes_check
        check (minutes > 0),
    constraint player_score_snapshots_appearances_check
        check (appearances > 0),
    constraint player_score_snapshots_overall_score_check
        check (overall_score between 0 and 100),
    constraint player_score_snapshots_confidence_check
        check (confidence between 0 and 1),
    constraint player_score_snapshots_dimensions_object_check
        check (jsonb_typeof(dimension_scores) = 'object'),
    constraint player_score_snapshots_reference_sample_check
        check (reference_sample_size > 0),
    constraint player_score_snapshots_model_version_not_blank_check
        check (btrim(model_version) <> '')
);

create index player_score_snapshots_ranking_idx
    on analytics.player_score_snapshots (
        scope_key,
        window,
        role,
        model_version,
        overall_score desc,
        confidence desc
    );

revoke all on all tables in schema analytics from public;

commit;
