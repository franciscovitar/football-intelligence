\set ON_ERROR_STOP on

begin;

-- Block 13: multi-source data mesh PoC. These tables live in the existing
-- ingestion schema (audit/provenance data), not in football.* -- the PoC
-- proves reconciliation without overwriting production canonical tables.

create table ingestion.source_observations (
    id bigint generated always as identity primary key,
    provider_id bigint not null
        references ingestion.providers(id) on delete restrict,
    source_type text not null,
    entity_type text not null,
    entity_source_id text not null,
    entity_identity_hints jsonb not null default '{}'::jsonb,
    metric_name text not null,
    value jsonb not null,
    observed_at timestamptz not null,
    source_timestamp timestamptz,
    source_reference text not null,
    ingestion_run_id bigint
        references ingestion.ingestion_runs(id) on delete set null,
    semantic_version text not null,
    created_at timestamptz not null default now(),
    constraint source_observations_source_type_check
        check (
            source_type in (
                'objective_structured',
                'objective_official',
                'objective_web',
                'qualitative_expert',
                'qualitative_fan'
            )
        ),
    constraint source_observations_entity_type_check
        check (entity_type in ('competition', 'team', 'match', 'player')),
    constraint source_observations_entity_source_id_not_blank_check
        check (btrim(entity_source_id) <> ''),
    constraint source_observations_hints_object_check
        check (jsonb_typeof(entity_identity_hints) = 'object'),
    constraint source_observations_metric_not_blank_check
        check (btrim(metric_name) <> ''),
    constraint source_observations_reference_not_blank_check
        check (btrim(source_reference) <> ''),
    constraint source_observations_semantic_version_not_blank_check
        check (btrim(semantic_version) <> ''),
    constraint source_observations_natural_key
        unique (provider_id, entity_type, entity_source_id, metric_name, observed_at)
);

create index source_observations_entity_idx
    on ingestion.source_observations (entity_type, entity_source_id, metric_name);

create index source_observations_run_idx
    on ingestion.source_observations (ingestion_run_id);

create table ingestion.reconciliation_decisions (
    id bigint generated always as identity primary key,
    logical_entity_key text not null,
    entity_type text not null,
    metric_name text not null,
    candidate_value jsonb,
    status text not null,
    confidence numeric(4, 3) not null,
    winning_provider_id bigint
        references ingestion.providers(id) on delete set null,
    source_count smallint not null,
    participating_sources jsonb not null default '[]'::jsonb,
    evidence jsonb not null default '{}'::jsonb,
    model_version text not null,
    calculated_at timestamptz not null,
    constraint reconciliation_decisions_entity_type_check
        check (entity_type in ('competition', 'team', 'match', 'player')),
    constraint reconciliation_decisions_key_not_blank_check
        check (btrim(logical_entity_key) <> ''),
    constraint reconciliation_decisions_metric_not_blank_check
        check (btrim(metric_name) <> ''),
    constraint reconciliation_decisions_status_check
        check (status in ('agreed', 'single_source', 'conflict', 'unresolved')),
    constraint reconciliation_decisions_confidence_check
        check (confidence between 0 and 1),
    constraint reconciliation_decisions_source_count_check
        check (source_count >= 0),
    constraint reconciliation_decisions_participating_array_check
        check (jsonb_typeof(participating_sources) = 'array'),
    constraint reconciliation_decisions_evidence_object_check
        check (jsonb_typeof(evidence) = 'object'),
    constraint reconciliation_decisions_model_version_not_blank_check
        check (btrim(model_version) <> ''),
    constraint reconciliation_decisions_natural_key
        unique (logical_entity_key, metric_name, model_version)
);

create index reconciliation_decisions_status_idx
    on ingestion.reconciliation_decisions (entity_type, status, calculated_at desc);

revoke all on ingestion.source_observations from public;
revoke all on ingestion.reconciliation_decisions from public;

commit;
