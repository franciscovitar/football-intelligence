\set ON_ERROR_STOP on

begin;

alter table analytics.player_feature_snapshots
    alter column percentile drop not null,
    add column raw_value numeric(16, 6),
    add column per90_value numeric(16, 6),
    add column value_basis text not null default 'per90',
    add column metric_kind text not null default 'raw',
    add column metric_unit text not null default 'per90',
    add column formula_version text,
    add column comparison_group text;

alter table analytics.player_feature_snapshots
    add constraint player_feature_snapshots_value_basis_not_blank_check
        check (btrim(value_basis) <> ''),
    add constraint player_feature_snapshots_metric_kind_check
        check (metric_kind in ('raw', 'derived')),
    add constraint player_feature_snapshots_metric_unit_not_blank_check
        check (btrim(metric_unit) <> '');

alter table analytics.player_score_snapshots
    add column evidence_metrics_expected text[] not null default '{}'::text[],
    add column evidence_core_metrics text[] not null default '{}'::text[],
    add column evidence_metrics_missing text[] not null default '{}'::text[],
    add column dimension_evidence jsonb not null default '{}'::jsonb,
    add column profile_version text;

alter table analytics.player_score_snapshots
    add constraint player_score_snapshots_dimension_evidence_object_check
        check (jsonb_typeof(dimension_evidence) = 'object');

comment on column analytics.player_score_snapshots.evidence_metrics_required is
    'Compatibility alias populated with the complete expected profile; use evidence_metrics_expected.';

alter table analytics.team_feature_snapshots
    alter column percentile drop not null,
    add column value_basis text not null default 'per_match',
    add column metric_kind text not null default 'raw',
    add column metric_unit text not null default 'count',
    add column formula_version text,
    add column comparison_group text;

alter table analytics.team_score_snapshots
    alter column overall_score drop not null,
    alter column results_process_delta drop not null,
    alter column results_process_signal drop not null,
    alter column current_elo drop not null,
    alter column elo_change_last_5 drop not null,
    add column evidence_coverage_pct numeric(5, 2) not null default 100,
    add column evidence_state text not null default 'ready',
    add column dimension_evidence jsonb not null default '{}'::jsonb,
    add column profile_version text;

alter table analytics.team_score_snapshots
    add constraint team_score_snapshots_evidence_coverage_check
        check (evidence_coverage_pct between 0 and 100),
    add constraint team_score_snapshots_evidence_state_check
        check (evidence_state in ('ready', 'partial', 'insufficient_data')),
    add constraint team_score_snapshots_dimension_evidence_object_check
        check (jsonb_typeof(dimension_evidence) = 'object');

commit;
