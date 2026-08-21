\set ON_ERROR_STOP on

begin;

-- Block 20D.4: Reconciliation V2 persistence. `ingestion.source_observations`
-- and `ingestion.reconciliation_decisions` (Block 13) predate Metric Catalog
-- V2's `metric_granularity` field -- a certified V2 observation/decision
-- (e.g. `saves`/player_match vs `saves`/goalkeeper_match, same entity_type,
-- same entity_source_id/logical_entity_key) would silently upsert one over
-- the other without it. `db.data_mesh_repository.
-- MetricGranularityNotPersistableError` has fenced this off since Block
-- 20D.2; this migration is the schema change that lets it be removed once
-- proven safe.
--
-- NULL semantics: `metric_granularity` is nullable (legacy pre-V2
-- observations/decisions always have it NULL). A plain `UNIQUE` constraint
-- treats NULL as distinct from NULL, which would silently break the
-- existing legacy upsert contract (two otherwise-identical legacy rows
-- would stop conflicting). `UNIQUE NULLS NOT DISTINCT` (PostgreSQL 15+;
-- this repository targets PostgreSQL 17, see docs/DATA_MODEL.md) is used
-- instead: two legacy rows (metric_granularity IS NULL) still collide
-- exactly as before, while two rows with different non-NULL
-- metric_granularity values coexist as distinct facts.
--
-- No backfill: every existing row keeps metric_granularity = NULL, its
-- correct pre-V2 value. Purely additive -- no data rewritten or destroyed.

alter table ingestion.source_observations
    add column metric_granularity text;

alter table ingestion.source_observations
    add constraint source_observations_metric_granularity_check
        check (
            metric_granularity is null
            or metric_granularity in (
                'competition', 'team', 'match', 'team_match', 'player_appearance',
                'player_match', 'player_season', 'goalkeeper_match', 'goalkeeper_season'
            )
        );

alter table ingestion.source_observations
    drop constraint source_observations_natural_key;

alter table ingestion.source_observations
    add constraint source_observations_natural_key
        unique nulls not distinct (
            provider_id,
            entity_type,
            entity_source_id,
            metric_name,
            metric_granularity,
            observed_at
        );

alter table ingestion.reconciliation_decisions
    add column metric_granularity text;

alter table ingestion.reconciliation_decisions
    add constraint reconciliation_decisions_metric_granularity_check
        check (
            metric_granularity is null
            or metric_granularity in (
                'competition', 'team', 'match', 'team_match', 'player_appearance',
                'player_match', 'player_season', 'goalkeeper_match', 'goalkeeper_season'
            )
        );

-- Widen the status vocabulary: `not_comparable` (an explicit, reviewed
-- provider-pair comparability policy says these two sources' values for
-- this metric are known not to measure the same thing) and
-- `methodology_pending` (no reviewed policy exists yet for this exact
-- provider-pair/semantic-version/metric/granularity combination -- fails
-- closed rather than defaulting to `agreed`/`conflict`). Deliberately NOT
-- adding a `tolerated_agreement` status in this block -- numeric tolerance
-- reconciliation is explicitly deferred to Block 20D.5.
alter table ingestion.reconciliation_decisions
    drop constraint reconciliation_decisions_status_check;

alter table ingestion.reconciliation_decisions
    add constraint reconciliation_decisions_status_check
        check (
            status in (
                'agreed', 'single_source', 'conflict', 'unresolved',
                'not_comparable', 'methodology_pending'
            )
        );

alter table ingestion.reconciliation_decisions
    drop constraint reconciliation_decisions_natural_key;

alter table ingestion.reconciliation_decisions
    add constraint reconciliation_decisions_natural_key
        unique nulls not distinct (
            logical_entity_key,
            metric_name,
            metric_granularity,
            model_version
        );

commit;
