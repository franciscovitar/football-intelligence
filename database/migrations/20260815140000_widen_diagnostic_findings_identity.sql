\set ON_ERROR_STOP on

begin;

-- Block 19 correction: `analytics.diagnostic_findings`'s primary key
-- predates the `data_context`/`source_model_version`/`scope_key`
-- provenance columns added in
-- `20260815130000_isolate_diagnostic_findings_v2_context.sql`. Those
-- columns are enforced by `DiagnosticFindingsRepository.replace_scope`'s
-- DELETE (scoped to an exact
-- entity_type/data_context/source_model_version/scope_key tuple) but were
-- never part of row identity, so a real and a `test_smoke` finding sharing
-- the same underlying (entity_type, entity_id, diagnostic_code,
-- comparison_group, window_key, model_version) natural key could not
-- coexist -- inserting one would silently `ON CONFLICT ... DO UPDATE` the
-- other's context away. Widening the primary key to include the three
-- provenance columns makes every distinct context its own row. This is a
-- pure identity change: every existing row already satisfies the wider key
-- (a superset of a unique key is itself unique), so no data is
-- lost, rewritten, or deduplicated.
alter table analytics.diagnostic_findings
    drop constraint diagnostic_findings_pkey,
    add constraint diagnostic_findings_pkey primary key (
        entity_type,
        entity_id,
        diagnostic_code,
        comparison_group,
        window_key,
        model_version,
        data_context,
        source_model_version,
        scope_key
    );

commit;
