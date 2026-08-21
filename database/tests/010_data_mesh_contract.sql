\set ON_ERROR_STOP on

begin;

do $$
declare
    thesportsdb_id bigint;
    openligadb_id bigint;
    observation_count_before bigint;
    observation_count_after bigint;
begin
    if to_regclass('ingestion.source_observations') is null then
        raise exception 'source_observations table is missing';
    end if;
    if to_regclass('ingestion.reconciliation_decisions') is null then
        raise exception 'reconciliation_decisions table is missing';
    end if;

    select id into thesportsdb_id from ingestion.providers where code = 'thesportsdb';
    select id into openligadb_id from ingestion.providers where code = 'openligadb';
    if thesportsdb_id is null then
        raise exception 'thesportsdb provider seed is missing';
    end if;
    if openligadb_id is null then
        raise exception 'openligadb provider seed is missing';
    end if;

    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, value,
        observed_at, source_timestamp, source_reference,
        semantic_version
    )
    values (
        thesportsdb_id, 'objective_structured', 'match', 'contract-event-1',
        '{"home_team_name":"Contract Home"}'::jsonb, 'home_score', '2'::jsonb,
        '2025-08-22T18:30:00+00', '2025-08-22T18:30:00+00',
        'eventsseason.php?id=4331', 'data-mesh-v0.1'
    );

    select count(*) into observation_count_before
    from ingestion.source_observations
    where provider_id = thesportsdb_id and entity_source_id = 'contract-event-1';

    -- Idempotent upsert on the natural key: same provider/entity/metric/observed_at.
    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, value,
        observed_at, source_timestamp, source_reference,
        semantic_version
    )
    values (
        thesportsdb_id, 'objective_structured', 'match', 'contract-event-1',
        '{"home_team_name":"Contract Home"}'::jsonb, 'home_score', '2'::jsonb,
        '2025-08-22T18:30:00+00', '2025-08-22T18:30:00+00',
        'eventsseason.php?id=4331', 'data-mesh-v0.1'
    )
    on conflict (
        provider_id, entity_type, entity_source_id, metric_name,
        metric_granularity, observed_at
    )
    do update set value = excluded.value;

    select count(*) into observation_count_after
    from ingestion.source_observations
    where provider_id = thesportsdb_id and entity_source_id = 'contract-event-1';

    if observation_count_before <> 1 or observation_count_after <> 1 then
        raise exception 'expected idempotent upsert to keep exactly one row, got % then %',
            observation_count_before, observation_count_after;
    end if;

    insert into ingestion.reconciliation_decisions (
        logical_entity_key, entity_type, metric_name, candidate_value,
        status, confidence, winning_provider_id, source_count,
        participating_sources, evidence, model_version, calculated_at
    )
    values (
        'match:GER_BL1:2025-2026:team:GER_BL1:contract home:team:GER_BL1:contract away:2025-08-22',
        'match', 'home_score', '2'::jsonb,
        'agreed', 0.700, null, 2,
        '["openligadb","thesportsdb"]'::jsonb,
        '{"values_by_source":{"openligadb":2,"thesportsdb":2}}'::jsonb,
        'data-mesh-reconciliation-v0.1', now()
    );

    begin
        insert into ingestion.source_observations (
            provider_id, source_type, entity_type, entity_source_id,
            entity_identity_hints, metric_name, value,
            observed_at, source_reference, semantic_version
        )
        values (
            openligadb_id, 'qualitative_hot_take', 'match', 'contract-event-2',
            '{}'::jsonb, 'home_score', '1'::jsonb,
            now(), 'getmatchdata/bl1/2025', 'data-mesh-v0.1'
        );
        raise exception 'expected invalid source_type to be rejected';
    exception
        when check_violation then null;
    end;

    begin
        insert into ingestion.reconciliation_decisions (
            logical_entity_key, entity_type, metric_name, status,
            confidence, source_count, model_version, calculated_at
        )
        values (
            'match:contract-bad-status', 'match', 'home_score', 'guessed',
            0.5, 1, 'data-mesh-reconciliation-v0.1', now()
        );
        raise exception 'expected invalid reconciliation status to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
