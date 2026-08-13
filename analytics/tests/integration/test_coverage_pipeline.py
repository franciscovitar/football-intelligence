from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.coverage_lab.models import CoverageEntry
from football_intelligence.db.coverage_repository import CoverageRepository
from football_intelligence.db.provider_repository import connect


@pytest.mark.integration
def test_coverage_snapshot_persistence_is_idempotent() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    now = datetime.now(UTC)
    entry = CoverageEntry(
        provider_code="statsbomb-open",
        competition_code="GER_BL1",
        metric_name="shots_total",
        entity_type="player",
        freshness_role="historical",
        state="historical_only",
        sample_size=34,
        observed_count=34,
        source_reference="data/events/coverage-integration.json",
        last_checked_at=now,
        notes="integration test",
    )

    with connect(database_url) as connection:
        repository = CoverageRepository(connection)
        first_written = repository.replace_snapshots([entry])
        assert first_written == 1
        before_count = repository.snapshot_count()

        # Re-persisting the identical natural key must upsert, not duplicate.
        updated = CoverageEntry(
            provider_code=entry.provider_code,
            competition_code=entry.competition_code,
            metric_name=entry.metric_name,
            entity_type=entry.entity_type,
            freshness_role=entry.freshness_role,
            state="partial",
            sample_size=34,
            observed_count=10,
            source_reference=entry.source_reference,
            last_checked_at=now,
            notes="updated",
        )
        second_written = repository.replace_snapshots([updated])
        assert second_written == 1
        assert repository.snapshot_count() == before_count

        row = connection.execute(
            """
            select state, observed_count
            from ingestion.coverage_snapshots
            where competition_code = 'GER_BL1' and metric_name = 'shots_total'
              and entity_type = 'player' and freshness_role = 'historical'
            """
        ).fetchone()
        assert row is not None
        assert str(row[0]) == "partial"
        assert int(row[1]) == 10

        connection.rollback()
