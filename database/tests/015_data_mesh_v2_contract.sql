\set ON_ERROR_STOP on

begin;

-- Block 20D.4: proves the `20260820100000_add_data_mesh_v2_persistence.sql`
-- migration's `UNIQUE NULLS NOT DISTINCT` natural keys behave exactly as
-- designed against a real PostgreSQL engine -- the property a plain
-- `UNIQUE` constraint (with metric_granularity nullable) would NOT have
-- provided (NULL is never equal to NULL under standard uniqueness
-- semantics, which would have silently broken legacy upsert idempotence
-- the moment metric_granularity was added to the key).

do $$
declare
    statsbomb_id bigint;
    openligadb_id bigint;
    observation_count bigint;
    decision_count bigint;
begin
    select id into statsbomb_id from ingestion.providers where code = 'statsbomb-open';
    select id into openligadb_id from ingestion.providers where code = 'openligadb';
    if statsbomb_id is null then
        raise exception 'statsbomb-open provider seed is missing';
    end if;
    if openligadb_id is null then
        raise exception 'openligadb provider seed is missing';
    end if;

    -- (A) Legacy NULL-granularity repeated-identity upserts: two rows with
    -- an identical natural key EXCEPT both leave metric_granularity NULL
    -- must still collide into exactly one row -- the exact pre-Block-20D.4
    -- contract, preserved by NULLS NOT DISTINCT treating NULL as equal to
    -- NULL for this constraint's purposes only.
    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, value,
        observed_at, source_reference, semantic_version
    )
    values (
        statsbomb_id, 'objective_structured', 'match', 'v2-contract-legacy-1',
        '{}'::jsonb, 'home_score', '2'::jsonb,
        '2026-08-20T18:30:00+00', 'legacy-fixture', 'test-v1'
    )
    on conflict (
        provider_id, entity_type, entity_source_id, metric_name,
        metric_granularity, observed_at
    )
    do update set value = excluded.value;

    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, value,
        observed_at, source_reference, semantic_version
    )
    values (
        statsbomb_id, 'objective_structured', 'match', 'v2-contract-legacy-1',
        '{}'::jsonb, 'home_score', '3'::jsonb,
        '2026-08-20T18:30:00+00', 'legacy-fixture', 'test-v1'
    )
    on conflict (
        provider_id, entity_type, entity_source_id, metric_name,
        metric_granularity, observed_at
    )
    do update set value = excluded.value;

    select count(*) into observation_count from ingestion.source_observations
    where provider_id = statsbomb_id and entity_source_id = 'v2-contract-legacy-1';
    if observation_count <> 1 then
        raise exception '(A) expected exactly 1 legacy row after repeated NULL-granularity '
            'upsert, got %', observation_count;
    end if;

    -- (B) Same V2 identity + same granularity upserts: two rows identical
    -- down to metric_granularity='player_match' must also collide into
    -- exactly one row -- V2 identities are idempotent, not merely
    -- append-only.
    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, metric_granularity, value,
        observed_at, source_reference, semantic_version
    )
    values (
        statsbomb_id, 'objective_structured', 'player', 'v2-contract-player-1',
        '{}'::jsonb, 'saves', 'player_match', '3'::jsonb,
        '2026-08-20T18:30:00+00', 'v2-fixture', 'test-v1'
    )
    on conflict (
        provider_id, entity_type, entity_source_id, metric_name,
        metric_granularity, observed_at
    )
    do update set value = excluded.value;

    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, metric_granularity, value,
        observed_at, source_reference, semantic_version
    )
    values (
        statsbomb_id, 'objective_structured', 'player', 'v2-contract-player-1',
        '{}'::jsonb, 'saves', 'player_match', '4'::jsonb,
        '2026-08-20T18:30:00+00', 'v2-fixture', 'test-v1'
    )
    on conflict (
        provider_id, entity_type, entity_source_id, metric_name,
        metric_granularity, observed_at
    )
    do update set value = excluded.value;

    select count(*) into observation_count from ingestion.source_observations
    where provider_id = statsbomb_id and entity_source_id = 'v2-contract-player-1'
        and metric_granularity = 'player_match';
    if observation_count <> 1 then
        raise exception '(B) expected exactly 1 row after repeated same-granularity V2 '
            'upsert, got %', observation_count;
    end if;

    -- (C) Same base identity + different non-NULL granularities coexist:
    -- `saves`/player_match and `saves`/goalkeeper_match for the SAME
    -- (provider, entity_type, entity_source_id, observed_at) must persist
    -- as two distinct rows, never collapse -- this is the exact real
    -- collision `MetricGranularityNotPersistableError` used to refuse
    -- rather than risk.
    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, metric_granularity, value,
        observed_at, source_reference, semantic_version
    )
    values (
        statsbomb_id, 'objective_structured', 'player', 'v2-contract-player-1',
        '{}'::jsonb, 'saves', 'goalkeeper_match', '4'::jsonb,
        '2026-08-20T18:30:00+00', 'v2-fixture', 'test-v1'
    )
    on conflict (
        provider_id, entity_type, entity_source_id, metric_name,
        metric_granularity, observed_at
    )
    do update set value = excluded.value;

    select count(*) into observation_count from ingestion.source_observations
    where provider_id = statsbomb_id and entity_source_id = 'v2-contract-player-1'
        and metric_name = 'saves';
    if observation_count <> 2 then
        raise exception '(C) expected exactly 2 coexisting rows (player_match + '
            'goalkeeper_match), got %', observation_count;
    end if;

    -- (D) A mixed legacy/V2 batch behaves deterministically: a legacy
    -- (NULL) row and a V2 (non-NULL) row sharing the same base identity
    -- are two distinct rows, not a collision -- NULL is never equal to a
    -- real granularity value.
    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, value,
        observed_at, source_reference, semantic_version
    )
    values (
        statsbomb_id, 'objective_structured', 'player', 'v2-contract-mixed-1',
        '{}'::jsonb, 'assists', '1'::jsonb,
        '2026-08-20T18:30:00+00', 'mixed-fixture', 'test-v1'
    );

    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, metric_granularity, value,
        observed_at, source_reference, semantic_version
    )
    values (
        statsbomb_id, 'objective_structured', 'player', 'v2-contract-mixed-1',
        '{}'::jsonb, 'assists', 'player_match', '1'::jsonb,
        '2026-08-20T18:30:00+00', 'mixed-fixture', 'test-v1'
    );

    select count(*) into observation_count from ingestion.source_observations
    where provider_id = statsbomb_id and entity_source_id = 'v2-contract-mixed-1';
    if observation_count <> 2 then
        raise exception '(D) expected legacy NULL row and V2 row to coexist as 2 rows, '
            'got %', observation_count;
    end if;

    -- Invalid metric_granularity is rejected.
    begin
        insert into ingestion.source_observations (
            provider_id, source_type, entity_type, entity_source_id,
            entity_identity_hints, metric_name, metric_granularity, value,
            observed_at, source_reference, semantic_version
        )
        values (
            statsbomb_id, 'objective_structured', 'player', 'v2-contract-invalid-1',
            '{}'::jsonb, 'saves', 'not_a_real_granularity', '1'::jsonb,
            now(), 'invalid-fixture', 'test-v1'
        );
        raise exception 'expected invalid metric_granularity to be rejected';
    exception
        when check_violation then null;
    end;

    -- --- reconciliation_decisions: the equivalent natural-key + status
    -- --- widening, proven the same way.

    -- (A) Legacy NULL-granularity decision upserts idempotently.
    insert into ingestion.reconciliation_decisions (
        logical_entity_key, entity_type, metric_name, status,
        confidence, source_count, model_version, calculated_at
    )
    values (
        'match:v2-contract-legacy-decision-1', 'match', 'home_score', 'agreed',
        0.700, 2, 'data-mesh-reconciliation-v0.1', now()
    )
    on conflict (logical_entity_key, metric_name, metric_granularity, model_version)
    do update set status = excluded.status, confidence = excluded.confidence;

    insert into ingestion.reconciliation_decisions (
        logical_entity_key, entity_type, metric_name, status,
        confidence, source_count, model_version, calculated_at
    )
    values (
        'match:v2-contract-legacy-decision-1', 'match', 'home_score', 'agreed',
        0.750, 2, 'data-mesh-reconciliation-v0.1', now()
    )
    on conflict (logical_entity_key, metric_name, metric_granularity, model_version)
    do update set status = excluded.status, confidence = excluded.confidence;

    select count(*) into decision_count from ingestion.reconciliation_decisions
    where logical_entity_key = 'match:v2-contract-legacy-decision-1';
    if decision_count <> 1 then
        raise exception '(decisions A) expected exactly 1 legacy row after repeated '
            'NULL-granularity upsert, got %', decision_count;
    end if;

    -- (C) Same logical_entity_key + different non-NULL granularities
    -- coexist under the same model_version.
    insert into ingestion.reconciliation_decisions (
        logical_entity_key, entity_type, metric_name, metric_granularity, status,
        confidence, source_count, model_version, calculated_at
    )
    values (
        'player-match:v2-contract-decision-1', 'player', 'saves', 'player_match', 'agreed',
        0.600, 2, 'data-mesh-reconciliation-v2.0', now()
    )
    on conflict (logical_entity_key, metric_name, metric_granularity, model_version)
    do update set status = excluded.status;

    insert into ingestion.reconciliation_decisions (
        logical_entity_key, entity_type, metric_name, metric_granularity, status,
        confidence, source_count, model_version, calculated_at
    )
    values (
        'player-match:v2-contract-decision-1', 'player', 'saves', 'goalkeeper_match', 'agreed',
        0.600, 2, 'data-mesh-reconciliation-v2.0', now()
    )
    on conflict (logical_entity_key, metric_name, metric_granularity, model_version)
    do update set status = excluded.status;

    select count(*) into decision_count from ingestion.reconciliation_decisions
    where logical_entity_key = 'player-match:v2-contract-decision-1';
    if decision_count <> 2 then
        raise exception '(decisions C) expected 2 coexisting rows (player_match + '
            'goalkeeper_match), got %', decision_count;
    end if;

    -- New Block 20D.4 statuses are accepted.
    insert into ingestion.reconciliation_decisions (
        logical_entity_key, entity_type, metric_name, metric_granularity, status,
        confidence, source_count, model_version, calculated_at
    )
    values (
        'team-match:v2-contract-not-comparable-1', 'team', 'passes_total', 'team_match',
        'not_comparable', 0.000, 2, 'data-mesh-reconciliation-v2.0', now()
    );

    insert into ingestion.reconciliation_decisions (
        logical_entity_key, entity_type, metric_name, metric_granularity, status,
        confidence, source_count, model_version, calculated_at
    )
    values (
        'player-match:v2-contract-pending-1', 'player', 'aerial_duels', 'player_match',
        'methodology_pending', 0.000, 2, 'data-mesh-reconciliation-v2.0', now()
    );

    -- Invalid status is still rejected (widened vocabulary, not an open one).
    begin
        insert into ingestion.reconciliation_decisions (
            logical_entity_key, entity_type, metric_name, status,
            confidence, source_count, model_version, calculated_at
        )
        values (
            'match:v2-contract-bad-status', 'match', 'home_score', 'guessed',
            0.5, 1, 'data-mesh-reconciliation-v2.0', now()
        );
        raise exception 'expected invalid reconciliation status to be rejected';
    exception
        when check_violation then null;
    end;

    -- Invalid decision metric_granularity is rejected.
    begin
        insert into ingestion.reconciliation_decisions (
            logical_entity_key, entity_type, metric_name, metric_granularity, status,
            confidence, source_count, model_version, calculated_at
        )
        values (
            'match:v2-contract-bad-granularity', 'match', 'home_score', 'not_a_real_one',
            'agreed', 0.5, 1, 'data-mesh-reconciliation-v2.0', now()
        );
        raise exception 'expected invalid decision metric_granularity to be rejected';
    exception
        when check_violation then null;
    end;
end;
$$;

rollback;
