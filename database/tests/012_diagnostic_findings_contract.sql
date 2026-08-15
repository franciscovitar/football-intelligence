\set ON_ERROR_STOP on

begin;

do $$
declare
    row_count_before bigint;
    row_count_after bigint;
begin
    if to_regclass('analytics.diagnostic_findings') is null then
        raise exception 'diagnostic_findings table is missing';
    end if;

    insert into analytics.diagnostic_findings (
        diagnostic_code, entity_type, entity_id, severity, confidence,
        supporting_metrics, comparison_group, window_key, model_version, computed_at
    )
    values (
        'finishing_underperformance', 'player', 101, 'notable', 0.72000,
        '{"goals": 3, "xg": 8.5}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now()
    );

    insert into analytics.diagnostic_findings (
        diagnostic_code, entity_type, entity_id, severity, confidence,
        supporting_metrics, comparison_group, window_key, model_version, computed_at
    )
    values (
        'results_above_process', 'team', 7, 'high', 0.81000,
        '{"results_process_delta": 18.5}'::jsonb, 'competition:ENG_PL:2025', 'season',
        'diagnostic-v1.0', now()
    );

    select count(*) into row_count_before
    from analytics.diagnostic_findings
    where entity_type = 'player' and entity_id = 101 and diagnostic_code = 'finishing_underperformance';

    -- Idempotent upsert on the natural key.
    insert into analytics.diagnostic_findings (
        diagnostic_code, entity_type, entity_id, severity, confidence,
        supporting_metrics, comparison_group, window_key, model_version, computed_at
    )
    values (
        'finishing_underperformance', 'player', 101, 'high', 0.80000,
        '{"goals": 2, "xg": 9.0}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now()
    )
    on conflict (entity_type, entity_id, diagnostic_code, comparison_group, window_key, model_version)
    do update set
        severity = excluded.severity,
        confidence = excluded.confidence,
        supporting_metrics = excluded.supporting_metrics,
        computed_at = excluded.computed_at;

    select count(*) into row_count_after
    from analytics.diagnostic_findings
    where entity_type = 'player' and entity_id = 101 and diagnostic_code = 'finishing_underperformance';

    if row_count_before <> 1 or row_count_after <> 1 then
        raise exception 'expected idempotent upsert to keep exactly one row, got % then %',
            row_count_before, row_count_after;
    end if;

    if not exists (
        select 1 from analytics.diagnostic_findings
        where entity_type = 'player' and entity_id = 101
          and diagnostic_code = 'finishing_underperformance' and severity = 'high'
    ) then
        raise exception 'expected upsert to have updated severity to high';
    end if;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at
        )
        values (
            'contract-bad-entity-type', 'referee', 1, 'notable', 0.5,
            '{}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now()
        );
        raise exception 'expected invalid entity_type to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at
        )
        values (
            'contract-bad-severity', 'player', 1, 'critical', 0.5,
            '{}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now()
        );
        raise exception 'expected invalid severity to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at
        )
        values (
            'contract-bad-confidence', 'player', 1, 'notable', 1.5,
            '{}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now()
        );
        raise exception 'expected out-of-range confidence to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at
        )
        values (
            'contract-bad-entity-id', 'player', 0, 'notable', 0.5,
            '{}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now()
        );
        raise exception 'expected non-positive entity_id to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at
        )
        values (
            'contract-bad-metrics-shape', 'player', 1, 'notable', 0.5,
            '["not", "an", "object"]'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now()
        );
        raise exception 'expected non-object supporting_metrics to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at
        )
        values (
            '', 'player', 1, 'notable', 0.5,
            '{}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now()
        );
        raise exception 'expected blank diagnostic_code to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at
        )
        values (
            'contract-bad-window', 'player', 1, 'notable', 0.5,
            '{}'::jsonb, 'role:forward', '', 'diagnostic-v1.0', now()
        );
        raise exception 'expected blank window_key to be rejected';
    exception
        when check_violation then null;
    end;

    -- A row inserted without explicit provenance columns must default to
    -- "not product-safe" (`data_context = 'test_smoke'`), never to `real`.
    insert into analytics.diagnostic_findings (
        diagnostic_code, entity_type, entity_id, severity, confidence,
        supporting_metrics, comparison_group, window_key, model_version, computed_at
    )
    values (
        'contract-default-context', 'player', 1, 'notable', 0.5,
        '{}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now()
    );
    if not exists (
        select 1 from analytics.diagnostic_findings
        where diagnostic_code = 'contract-default-context'
          and data_context = 'test_smoke'
          and source_model_version = 'unknown'
          and scope_key = 'unknown'
    ) then
        raise exception 'expected default provenance to be conservative (test_smoke/unknown)';
    end if;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at,
            data_context
        )
        values (
            'contract-bad-data-context', 'player', 1, 'notable', 0.5,
            '{}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now(), 'fabricated'
        );
        raise exception 'expected invalid data_context to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at,
            source_model_version
        )
        values (
            'contract-bad-source-model-version', 'player', 1, 'notable', 0.5,
            '{}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now(), ''
        );
        raise exception 'expected blank source_model_version to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at,
            scope_key
        )
        values (
            'contract-bad-scope-key', 'player', 1, 'notable', 0.5,
            '{}'::jsonb, 'role:forward', 'season', 'diagnostic-v1.0', now(), ''
        );
        raise exception 'expected blank scope_key to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
