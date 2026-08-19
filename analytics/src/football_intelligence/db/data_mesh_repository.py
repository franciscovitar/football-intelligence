"""PostgreSQL persistence for Block 13 multi-source data mesh evidence.

Writes only to the `ingestion` schema (raw/audit evidence + reconciliation
decisions). This repository never writes to `football.*` canonical tables --
the PoC proves reconciliation without feeding production data.

## Temporary persistence boundary: `metric_granularity` (Block 20D.2)

`ingestion.source_observations` is Block 13's original persistence
contract. Its columns and natural key (`provider_id, entity_type,
entity_source_id, metric_name, observed_at`) predate Metric Catalog V2's
`metric_granularity` field and have no column or natural-key component for
it. A certified V2 observation's `metric_granularity` genuinely
distinguishes two different real facts that would otherwise collide on
this table's own natural key -- e.g. `saves`/`player_match` and
`saves`/`goalkeeper_match` for the same match/player share the same
`entity_type` ("player") and the same `entity_source_id`, so persisting
both here would silently upsert one over the other, destroying real
evidence rather than merely mislabeling it.

Rather than silently dropping `metric_granularity`, serializing it into
`entity_identity_hints` as an undocumented workaround, or attempting a
schema migration as part of this block, `persist_observations()` refuses
the entire batch up front -- before any SQL statement executes -- the
moment any observation in it carries a non-`None` `metric_granularity`.
Legacy (pre-Metric-Catalog-V2) observations, which always have
`metric_granularity=None`, are completely unaffected and persist exactly
as before. Real V2-aware persistence (a genuine schema change: a new
column and a widened natural key) is deferred to the Reconciliation V2 /
Block 20D.4 work, not implemented here.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from football_intelligence.data_mesh.models import NormalizedObservation, ReconciliationDecision


class MetricGranularityNotPersistableError(RuntimeError):
    """A batch contained an observation with an explicit `metric_granularity`,
    but `ingestion.source_observations` (Block 13's legacy pre-V2
    persistence contract) has no column or natural key to preserve it.
    Persisting it anyway would risk silently collapsing distinct catalog
    identities onto the same row. Real V2 DB persistence/schema support is
    deferred to the Reconciliation V2 / Block 20D.4 work -- see this
    module's docstring."""


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

    def persist_observations(self, observations: Sequence[NormalizedObservation]) -> int:
        # Fail the whole batch before any INSERT -- see this module's
        # docstring ("Temporary persistence boundary: metric_granularity").
        non_persistable = [obs for obs in observations if obs.metric_granularity is not None]
        if non_persistable:
            first = non_persistable[0]
            raise MetricGranularityNotPersistableError(
                f"refusing to persist a batch of {len(observations)} observation(s): "
                f"{len(non_persistable)} carry an explicit metric_granularity (e.g. "
                f"{first.metric_granularity!r} for {first.source_code}:{first.entity_type}:"
                f"{first.entity_source_id}:{first.metric_name}). "
                "ingestion.source_observations is a legacy pre-V2 persistence contract with "
                "no column or natural key for metric_granularity -- persisting would risk "
                "silently collapsing distinct catalog identities (e.g. saves/player_match "
                "and saves/goalkeeper_match) onto the same row. V2 DB persistence/schema "
                "support is deferred to the Reconciliation V2 / Block 20D.4 work."
            )

        written = 0
        for item in observations:
            provider_id = self.lookup_provider_id(item.source_code)
            self._connection.execute(
                """
                insert into ingestion.source_observations (
                    provider_id, source_type, entity_type, entity_source_id,
                    entity_identity_hints, metric_name, value,
                    observed_at, source_timestamp, source_reference,
                    ingestion_run_id, semantic_version
                )
                values (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s, %s, %s)
                on conflict (provider_id, entity_type, entity_source_id, metric_name, observed_at)
                do update set
                    value = excluded.value,
                    entity_identity_hints = excluded.entity_identity_hints,
                    source_timestamp = excluded.source_timestamp,
                    source_reference = excluded.source_reference,
                    ingestion_run_id = excluded.ingestion_run_id,
                    semantic_version = excluded.semantic_version
                """,
                (
                    provider_id,
                    item.source_type,
                    item.entity_type,
                    item.entity_source_id,
                    json.dumps(dict(item.entity_identity_hints), sort_keys=True),
                    item.metric_name,
                    json.dumps(item.value),
                    item.observed_at,
                    item.source_timestamp,
                    item.source_reference,
                    item.ingestion_run_id,
                    item.semantic_version,
                ),
            )
            written += 1
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
                    logical_entity_key, entity_type, metric_name, candidate_value,
                    status, confidence, winning_provider_id, source_count,
                    participating_sources, evidence, model_version, calculated_at
                )
                values (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                on conflict (logical_entity_key, metric_name, model_version)
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
