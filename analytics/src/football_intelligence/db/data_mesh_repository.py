"""PostgreSQL persistence for the multi-source data mesh evidence (Block 13,
V2 persistence added Block 20D.4).

Writes only to the `ingestion` schema (raw/audit evidence + reconciliation
decisions) -- this repository never writes to `football.*`/`intelligence.*`
canonical tables.

## `metric_granularity` persistence (Block 20D.4)

`ingestion.source_observations`/`ingestion.reconciliation_decisions` (Block
13) predated Metric Catalog V2's `metric_granularity` field: their natural
keys had no column or key component for it, so a certified V2 observation's
`metric_granularity` -- which genuinely distinguishes two different real
facts (e.g. `saves`/`player_match` and `saves`/`goalkeeper_match` for the
same match/player, sharing the same `entity_type`/`entity_source_id`) --
could not be persisted without silently upserting one over the other.
`persist_observations()` fenced this off with `MetricGranularityNotPersist
ableError` since Block 20D.2, refusing any batch containing a non-`None`
`metric_granularity` before any SQL executed.

`database/migrations/20260820100000_add_data_mesh_v2_persistence.sql` (Block
20D.4) closes that gap: both tables gained a nullable `metric_granularity`
column and their natural keys were widened to include it, using `UNIQUE
NULLS NOT DISTINCT` (PostgreSQL 15+; this repository targets PostgreSQL 17)
so legacy rows (`metric_granularity IS NULL`) still collide/upsert exactly
as before, while rows with different non-NULL `metric_granularity` values
coexist as distinct facts. `database/tests/015_data_mesh_v2_contract.sql`
proves both invariants against a real database. With the schema proven
safe, `MetricGranularityNotPersistableError`'s fail-closed guard is removed
here -- `persist_observations()`/`replace_decisions()` now persist V2
observations/decisions directly, with `ON CONFLICT` targets widened to
match the new natural keys.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from football_intelligence.data_mesh.models import NormalizedObservation, ReconciliationDecision

_OBSERVATION_UPSERT_SQL = """
    insert into ingestion.source_observations (
        provider_id, source_type, entity_type, entity_source_id,
        entity_identity_hints, metric_name, metric_granularity, value,
        observed_at, source_timestamp, source_reference,
        ingestion_run_id, semantic_version
    )
    values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
    on conflict (
        provider_id, entity_type, entity_source_id, metric_name,
        metric_granularity, observed_at
    )
    do update set
        value = excluded.value,
        entity_identity_hints = excluded.entity_identity_hints,
        source_timestamp = excluded.source_timestamp,
        source_reference = excluded.source_reference,
        ingestion_run_id = excluded.ingestion_run_id,
        semantic_version = excluded.semantic_version
"""


class DataMeshRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection
        self._provider_id_cache: dict[str, int] = {}

    def lookup_provider_id(self, provider_code: str) -> int:
        cached = self._provider_id_cache.get(provider_code)
        if cached is not None:
            return cached
        row = self._connection.execute(
            "select id from ingestion.providers where code = %s",
            (provider_code,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"provider seed not found: {provider_code}")
        provider_id = int(row[0])
        self._provider_id_cache[provider_code] = provider_id
        return provider_id

    def _observation_params(self, item: NormalizedObservation) -> tuple[Any, ...]:
        return (
            self.lookup_provider_id(item.source_code),
            item.source_type,
            item.entity_type,
            item.entity_source_id,
            json.dumps(dict(item.entity_identity_hints), sort_keys=True),
            item.metric_name,
            item.metric_granularity,
            json.dumps(item.value),
            item.observed_at,
            item.source_timestamp,
            item.source_reference,
            item.ingestion_run_id,
            item.semantic_version,
        )

    def persist_observations(self, observations: Sequence[NormalizedObservation]) -> int:
        written = 0
        for item in observations:
            self._connection.execute(_OBSERVATION_UPSERT_SQL, self._observation_params(item))
            written += 1
        return written

    def persist_observations_batched(
        self,
        observations: Sequence[NormalizedObservation],
        *,
        batch_size: int = 1_000,
    ) -> int:
        """Persist a large observation set with the same upsert semantics.

        The regular method intentionally remains unchanged for small callers.
        This bounded batch path uses psycopg ``executemany`` so historical
        production promotion does not pay one network round-trip per evidence
        row when writing hundreds of thousands of observations to a remote DB.
        """

        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        written = 0
        for offset in range(0, len(observations), batch_size):
            batch = observations[offset : offset + batch_size]
            params = [self._observation_params(item) for item in batch]
            with self._connection.cursor() as cursor:
                cursor.executemany(_OBSERVATION_UPSERT_SQL, params)
            written += len(batch)
        return written

    def replace_decisions(self, decisions: Sequence[ReconciliationDecision]) -> int:
        written = 0
        for decision in decisions:
            winning_provider_id = (
                self.lookup_provider_id(decision.winning_source_code)
                if decision.winning_source_code
                else None
            )
            self._connection.execute(
                """
                insert into ingestion.reconciliation_decisions (
                    logical_entity_key, entity_type, metric_name, metric_granularity,
                    candidate_value, status, confidence, winning_provider_id, source_count,
                    participating_sources, evidence, model_version, calculated_at
                )
                values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                on conflict (logical_entity_key, metric_name, metric_granularity, model_version)
                do update set
                    candidate_value = excluded.candidate_value,
                    status = excluded.status,
                    confidence = excluded.confidence,
                    winning_provider_id = excluded.winning_provider_id,
                    source_count = excluded.source_count,
                    participating_sources = excluded.participating_sources,
                    evidence = excluded.evidence,
                    calculated_at = excluded.calculated_at
                """,
                (
                    decision.logical_entity_key,
                    decision.entity_type,
                    decision.metric_name,
                    decision.metric_granularity,
                    (
                        json.dumps(decision.candidate_value)
                        if decision.candidate_value is not None
                        else None
                    ),
                    decision.status,
                    decision.confidence,
                    winning_provider_id,
                    decision.source_count,
                    json.dumps(list(decision.participating_sources)),
                    json.dumps(dict(decision.evidence), default=str, sort_keys=True),
                    decision.model_version,
                    decision.calculated_at,
                ),
            )
            written += 1
        return written

    def observation_count(self) -> int:
        row = self._connection.execute(
            "select count(*) from ingestion.source_observations"
        ).fetchone()
        return int(row[0]) if row else 0

    def decision_count(self) -> int:
        row = self._connection.execute(
            "select count(*) from ingestion.reconciliation_decisions"
        ).fetchone()
        return int(row[0]) if row else 0
