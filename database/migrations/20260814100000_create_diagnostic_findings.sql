\set ON_ERROR_STOP on

begin;

-- `entity_id` intentionally has no foreign key: `entity_type` decides
-- whether it means a football.players.id or a football.teams.id, and a
-- single column cannot carry a conditional foreign key to two different
-- tables in PostgreSQL. Adding two nullable FK columns instead (one per
-- entity type) would let a row point at both a player and a team at once,
-- which is a worse integrity story than the one enforced here (a positive
-- integer, checked, with entity-type-scoped correctness left to the
-- application layer that writes these rows -- the deterministic Diagnostic
-- Rule Engine in analytics/.../diagnostics/, which only ever sources
-- entity_id from a real player_id/team_id it already validated upstream).
-- `analytics.world_radar_snapshots` already established this same
-- no-FK-into-core-tables pattern for a structurally similar reason.
create table analytics.diagnostic_findings (
    diagnostic_code text not null,
    entity_type text not null,
    entity_id integer not null,
    severity text not null,
    confidence numeric(6, 5) not null,
    supporting_metrics jsonb not null default '{}'::jsonb,
    comparison_group text not null,
    window_key text not null,
    model_version text not null,
    computed_at timestamptz not null,
    primary key (
        entity_type,
        entity_id,
        diagnostic_code,
        comparison_group,
        window_key,
        model_version
    ),
    constraint diagnostic_findings_diagnostic_code_not_blank_check
        check (btrim(diagnostic_code) <> ''),
    constraint diagnostic_findings_entity_type_check
        check (entity_type in ('player', 'team')),
    constraint diagnostic_findings_entity_id_check
        check (entity_id > 0),
    constraint diagnostic_findings_severity_check
        check (severity in ('info', 'notable', 'high')),
    constraint diagnostic_findings_confidence_check
        check (confidence between 0 and 1),
    constraint diagnostic_findings_supporting_metrics_object_check
        check (jsonb_typeof(supporting_metrics) = 'object'),
    constraint diagnostic_findings_comparison_group_not_blank_check
        check (btrim(comparison_group) <> ''),
    constraint diagnostic_findings_window_key_not_blank_check
        check (btrim(window_key) <> ''),
    constraint diagnostic_findings_model_version_not_blank_check
        check (btrim(model_version) <> '')
);

create index diagnostic_findings_lookup_idx
    on analytics.diagnostic_findings (
        entity_type,
        diagnostic_code,
        model_version
    );

revoke all on analytics.diagnostic_findings from public;

commit;
