"""PostgreSQL persistence for Block 13 multi-source data mesh evidence.

Writes only to the `ingestion` schema (raw/audit evidence + reconciliation
decisions). This repository never writes to `football.*` canonical tables --
the PoC proves reconciliation without feeding production data.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from football_intelligence.data_mesh.models import NormalizedObservation, ReconciliationDecision


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
