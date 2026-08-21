\set ON_ERROR_STOP on

-- The data mesh PoC never calls live providers in CI. This fixture seeds
-- deterministic observations/decisions directly so /sources can be
-- smoke-tested without spending TheSportsDB/OpenLigaDB quota.

do $$
declare
    thesportsdb_id bigint;
    openligadb_id bigint;
begin
    select id into thesportsdb_id from ingestion.providers where code = 'thesportsdb';
    select id into openligadb_id from ingestion.providers where code = 'openligadb';

    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, value,
        observed_at, source_timestamp, source_reference, semantic_version
    )
    values
        (
            thesportsdb_id, 'objective_structured', 'match', 'web-smoke-event-1',
            '{"home_team_name":"Web Smoke Radar Forward FC"}'::jsonb, 'home_score', '2'::jsonb,
            '2025-08-22T18:30:00+00', '2025-08-22T18:30:00+00',
            'eventsseason.php?id=4331', 'data-mesh-v0.1'
        ),
        (
            openligadb_id, 'objective_structured', 'match', 'web-smoke-match-1',
            '{"home_team_name":"Web Smoke Radar Forward FC"}'::jsonb, 'home_score', '2'::jsonb,
            '2025-08-22T18:30:00+00', '2025-08-22T18:30:00+00',
            'getmatchdata/bl1', 'data-mesh-v0.1'
        ),
        (
            openligadb_id, 'objective_structured', 'match', 'web-smoke-match-2',
            '{"home_team_name":"Web Smoke Radar Playmaker FC"}'::jsonb, 'home_score', '1'::jsonb,
            '2025-08-23T15:30:00+00', '2025-08-23T15:30:00+00',
            'getmatchdata/bl1', 'data-mesh-v0.1'
        )
    on conflict (
        provider_id, entity_type, entity_source_id, metric_name,
        metric_granularity, observed_at
    )
    do update set value = excluded.value;

    insert into ingestion.reconciliation_decisions (
        logical_entity_key, entity_type, metric_name, candidate_value,
        status, confidence, winning_provider_id, source_count,
        participating_sources, evidence, model_version, calculated_at
    )
    values
        (
            'match:GER_BL1:2025-2026:web-smoke-agreed', 'match', 'home_score', '2'::jsonb,
            'agreed', 0.700, null, 2,
            '["openligadb","thesportsdb"]'::jsonb,
            '{"values_by_source":{"openligadb":2,"thesportsdb":2}}'::jsonb,
            'data-mesh-reconciliation-v0.1', now()
        ),
        (
            'match:GER_BL1:2025-2026:web-smoke-single', 'match', 'home_score', '1'::jsonb,
            'single_source', 0.350, openligadb_id, 1,
            '["openligadb"]'::jsonb,
            '{"values_by_source":{"openligadb":1}}'::jsonb,
            'data-mesh-reconciliation-v0.1', now()
        ),
        (
            'match:GER_BL1:2025-2026:web-smoke-conflict', 'match', 'shots_total', null,
            'conflict', 0.200, null, 2,
            '["openligadb","thesportsdb"]'::jsonb,
            '{"values_by_source":{"openligadb":13,"thesportsdb":11}}'::jsonb,
            'data-mesh-reconciliation-v0.1', now()
        )
    on conflict (logical_entity_key, metric_name, metric_granularity, model_version)
    do update set
        candidate_value = excluded.candidate_value,
        status = excluded.status,
        confidence = excluded.confidence,
        calculated_at = excluded.calculated_at;
end;
$$;
