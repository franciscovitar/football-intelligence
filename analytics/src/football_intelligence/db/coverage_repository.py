"""PostgreSQL persistence for Block 14 Zero-Cost Coverage Lab evidence.

Writes only to `ingestion.coverage_snapshots`. Never writes to `football.*`
canonical tables -- coverage is measurement/evidence, not a promotion path.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from football_intelligence.coverage_lab.models import CoverageEntry


class CoverageRepository:
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

    def replace_snapshots(self, entries: Sequence[CoverageEntry]) -> int:
        written = 0
        for entry in entries:
            provider_id = self.lookup_provider_id(entry.provider_code)
            self._connection.execute(
                """
                insert into ingestion.coverage_snapshots (
                    provider_id, competition_code, metric_name, granularity, entity_type,
                    freshness_role, state, sample_size, observed_count,
                    source_reference, last_checked_at, notes
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (
                    provider_id, competition_code, metric_name, granularity, freshness_role
                )
                do update set
                    state = excluded.state,
                    entity_type = excluded.entity_type,
                    sample_size = excluded.sample_size,
                    observed_count = excluded.observed_count,
                    source_reference = excluded.source_reference,
                    last_checked_at = excluded.last_checked_at,
                    notes = excluded.notes
                """,
                (
                    provider_id,
                    entry.competition_code,
                    entry.metric_name,
                    entry.granularity,
                    entry.entity_type,
                    entry.freshness_role,
                    entry.state,
                    entry.sample_size,
                    entry.observed_count,
                    entry.source_reference,
                    entry.last_checked_at,
                    entry.notes,
                ),
            )
            written += 1
        return written

    def snapshot_count(self) -> int:
        row = self._connection.execute(
            "select count(*) from ingestion.coverage_snapshots"
        ).fetchone()
        return int(row[0]) if row else 0
