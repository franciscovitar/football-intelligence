\set ON_ERROR_STOP on

begin;

-- Block 14: Zero-Cost Coverage Lab evidence. Lives in the existing
-- `ingestion` schema alongside source_observations/reconciliation_decisions
-- and the older `ingestion.data_capabilities` table.
--
-- `data_capabilities` is intentionally NOT reused/extended here: it is
-- scoped per (provider, entity_type, metric_name) with no competition
-- dimension, because it summarizes core-league sync capability across all
-- core leagues combined. The Coverage Lab's whole purpose is
-- competition-scoped coverage across many providers (including zero-cost
-- and historical-only ones) with a richer state model (7 states vs 4) and
-- an explicit current/historical distinction. Altering the existing table's
-- primary key or check constraint would also risk the write path already
-- used by `sync_core_leagues.py` and its contract test. A small, purpose-
-- built table keeps both concepts correct without duplicating logic.

create table ingestion.coverage_snapshots (
    id bigint generated always as identity primary key,
    provider_id bigint not null
        references ingestion.providers(id) on delete restrict,
    competition_code text not null,
    metric_name text not null,
    -- The true target-catalog identity is (metric_name, granularity), not
    -- metric_name alone: the same name can legitimately exist at two
    -- granularities (e.g. "shots_total" at both team and player_match).
    -- Stored explicitly rather than inferred from the coarser `entity_type`
    -- bucket (player_appearance and player_match both collapse to
    -- "player"), so product-level union coverage can group requirements
    -- precisely instead of relying on an implicit, lossy proxy.
    granularity text not null,
    entity_type text not null,
    freshness_role text not null,
    state text not null,
    sample_size integer not null default 0,
    observed_count integer not null default 0,
    source_reference text,
    last_checked_at timestamptz not null,
    notes text,
    created_at timestamptz not null default now(),
    constraint coverage_snapshots_competition_not_blank_check
        check (btrim(competition_code) <> ''),
    constraint coverage_snapshots_metric_not_blank_check
        check (btrim(metric_name) <> ''),
    constraint coverage_snapshots_granularity_check
        check (
            granularity in (
                'competition', 'team', 'match', 'player_appearance', 'player_match'
            )
        ),
    constraint coverage_snapshots_entity_type_check
        check (entity_type in ('competition', 'team', 'match', 'player')),
    constraint coverage_snapshots_freshness_role_check
        check (freshness_role in ('current', 'historical')),
    constraint coverage_snapshots_state_check
        check (
            state in (
                'current_available',
                'historical_only',
                'partial',
                'token_required',
                'not_probed',
                'missing',
                'unsupported'
            )
        ),
    constraint coverage_snapshots_sample_size_check
        check (sample_size >= 0),
    constraint coverage_snapshots_observed_count_check
        check (observed_count >= 0 and observed_count <= sample_size),
    constraint coverage_snapshots_natural_key
        unique (provider_id, competition_code, metric_name, granularity, freshness_role)
);

create index coverage_snapshots_lookup_idx
    on ingestion.coverage_snapshots (competition_code, metric_name, state);

create index coverage_snapshots_provider_idx
    on ingestion.coverage_snapshots (provider_id, state);

-- Supports the product-level union query (web `/sources` and any future
-- reporting): "for this freshness role, group by requirement identity and
-- check whether ANY provider satisfies it" -- independent of provider count.
create index coverage_snapshots_product_union_idx
    on ingestion.coverage_snapshots (freshness_role, competition_code, metric_name, granularity);

revoke all on ingestion.coverage_snapshots from public;

commit;
