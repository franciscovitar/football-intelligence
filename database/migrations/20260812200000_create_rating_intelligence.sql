\set ON_ERROR_STOP on

begin;

create table analytics.player_rating_snapshots (
    player_id bigint not null
        references football.players(id) on delete cascade,
    scope_key text not null,
    role text not null,
    performance_score numeric(5, 2) not null,
    performance_confidence numeric(6, 5) not null,
    perception_score numeric(5, 2),
    perception_confidence numeric(6, 5) not null,
    perception_signal text not null,
    rating_gap numeric(6, 2),
    rating_confidence numeric(6, 5) not null,
    rating_signal text not null,
    consensus_score numeric(5, 2),
    polarization_score numeric(5, 2),
    evidence_count smallint not null,
    scored_evidence_count smallint not null,
    source_count smallint not null,
    scored_source_count smallint not null,
    evidence_window_days smallint not null,
    evidence_breakdown jsonb not null default '[]'::jsonb,
    performance_model_version text not null,
    perception_model_version text not null,
    model_version text not null,
    calculated_at timestamptz not null,
    primary key (player_id, scope_key, model_version),
    constraint player_rating_scope_not_blank_check
        check (btrim(scope_key) <> ''),
    constraint player_rating_role_check
        check (role in ('goalkeeper', 'defender', 'midfielder', 'forward')),
    constraint player_rating_performance_score_check
        check (performance_score between 0 and 100),
    constraint player_rating_performance_confidence_check
        check (performance_confidence between 0 and 1),
    constraint player_rating_perception_score_check
        check (perception_score is null or perception_score between 0 and 100),
    constraint player_rating_perception_confidence_check
        check (perception_confidence between 0 and 1),
    constraint player_rating_perception_signal_check
        check (
            perception_signal in (
                'positive',
                'negative',
                'neutral',
                'mixed',
                'insufficient_evidence'
            )
        ),
    constraint player_rating_confidence_check
        check (rating_confidence between 0 and 1),
    constraint player_rating_signal_check
        check (
            rating_signal in (
                'underrated',
                'overrated',
                'aligned',
                'polarized',
                'insufficient_evidence'
            )
        ),
    constraint player_rating_consensus_check
        check (consensus_score is null or consensus_score between 0 and 100),
    constraint player_rating_polarization_check
        check (polarization_score is null or polarization_score between 0 and 100),
    constraint player_rating_evidence_counts_check
        check (
            evidence_count >= 0
            and scored_evidence_count >= 0
            and scored_evidence_count <= evidence_count
            and source_count >= 0
            and scored_source_count >= 0
            and scored_source_count <= source_count
        ),
    constraint player_rating_window_days_check
        check (evidence_window_days > 0),
    constraint player_rating_breakdown_array_check
        check (jsonb_typeof(evidence_breakdown) = 'array'),
    constraint player_rating_performance_model_not_blank_check
        check (btrim(performance_model_version) <> ''),
    constraint player_rating_perception_model_not_blank_check
        check (btrim(perception_model_version) <> ''),
    constraint player_rating_model_not_blank_check
        check (btrim(model_version) <> '')
);

create index player_rating_signal_idx
    on analytics.player_rating_snapshots (
        scope_key,
        model_version,
        rating_signal,
        rating_confidence desc,
        rating_gap desc nulls last
    );

create index player_rating_consensus_idx
    on analytics.player_rating_snapshots (
        scope_key,
        model_version,
        consensus_score desc nulls last
    );

create index player_rating_polarization_idx
    on analytics.player_rating_snapshots (
        scope_key,
        model_version,
        polarization_score desc nulls last
    );

revoke all on all tables in schema analytics from public;

commit;
