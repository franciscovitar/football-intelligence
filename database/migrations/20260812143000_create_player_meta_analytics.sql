\set ON_ERROR_STOP on

begin;

create table analytics.player_meta_snapshots (
    player_id bigint not null
        references football.players(id) on delete cascade,
    scope_key text not null,
    role text not null,
    performance_score numeric(5, 2) not null,
    performance_confidence numeric(6, 5) not null,
    form_score numeric(5, 2),
    form_confidence numeric(6, 5),
    stable_score numeric(5, 2) not null,
    stable_confidence numeric(6, 5) not null,
    expectation_score numeric(5, 2),
    expectation_confidence numeric(6, 5),
    surprise_delta numeric(6, 2),
    surprise_signal text not null,
    trend_delta numeric(6, 2),
    trend_confidence numeric(6, 5),
    trend_signal text not null,
    watchlist_score numeric(5, 2) not null,
    watchlist_signal text not null,
    history_seasons smallint not null,
    baseline_evidence jsonb not null default '[]'::jsonb,
    trend_evidence jsonb not null default '{}'::jsonb,
    source_model_version text not null,
    model_version text not null,
    calculated_at timestamptz not null,
    primary key (player_id, scope_key, model_version),
    constraint player_meta_scope_not_blank_check
        check (btrim(scope_key) <> ''),
    constraint player_meta_role_check
        check (role in ('goalkeeper', 'defender', 'midfielder', 'forward')),
    constraint player_meta_performance_score_check
        check (performance_score between 0 and 100),
    constraint player_meta_performance_confidence_check
        check (performance_confidence between 0 and 1),
    constraint player_meta_form_score_check
        check (form_score is null or form_score between 0 and 100),
    constraint player_meta_form_confidence_check
        check (form_confidence is null or form_confidence between 0 and 1),
    constraint player_meta_stable_score_check
        check (stable_score between 0 and 100),
    constraint player_meta_stable_confidence_check
        check (stable_confidence between 0 and 1),
    constraint player_meta_expectation_score_check
        check (expectation_score is null or expectation_score between 0 and 100),
    constraint player_meta_expectation_confidence_check
        check (expectation_confidence is null or expectation_confidence between 0 and 1),
    constraint player_meta_surprise_signal_check
        check (
            surprise_signal in (
                'surprise',
                'disappointment',
                'aligned',
                'insufficient_history',
                'insufficient_evidence'
            )
        ),
    constraint player_meta_trend_confidence_check
        check (trend_confidence is null or trend_confidence between 0 and 1),
    constraint player_meta_trend_signal_check
        check (
            trend_signal in (
                'rising',
                'falling',
                'stable',
                'insufficient_data',
                'insufficient_evidence'
            )
        ),
    constraint player_meta_watchlist_score_check
        check (watchlist_score between 0 and 100),
    constraint player_meta_watchlist_signal_check
        check (
            watchlist_signal in ('breakout', 'outperforming', 'rising', 'monitor', 'none')
        ),
    constraint player_meta_history_seasons_check
        check (history_seasons between 0 and 3),
    constraint player_meta_baseline_evidence_array_check
        check (jsonb_typeof(baseline_evidence) = 'array'),
    constraint player_meta_trend_evidence_object_check
        check (jsonb_typeof(trend_evidence) = 'object'),
    constraint player_meta_source_model_not_blank_check
        check (btrim(source_model_version) <> ''),
    constraint player_meta_model_not_blank_check
        check (btrim(model_version) <> '')
);

create index player_meta_watchlist_idx
    on analytics.player_meta_snapshots (
        scope_key,
        model_version,
        watchlist_score desc,
        stable_confidence desc
    );

create index player_meta_surprise_idx
    on analytics.player_meta_snapshots (
        scope_key,
        model_version,
        surprise_signal,
        surprise_delta desc nulls last
    );

create index player_meta_role_idx
    on analytics.player_meta_snapshots (
        scope_key,
        model_version,
        role,
        stable_score desc
    );

revoke all on all tables in schema analytics from public;

commit;
