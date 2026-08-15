from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.db.provider_repository import connect
from football_intelligence.jobs.build_real_snapshot_v2 import (
    _persist_audit_evidence,
    _read_canonical_state,
    _validate_database_url,
)


def _local_database_url() -> str | None:
    """Only used to derive a genuinely local URL for this DB-gated test --
    never a hidden fallback inside the job itself (see
    `_validate_database_url`'s module docstring)."""

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return None
    return database_url


@pytest.mark.integration
def test_explicit_local_url_with_persist_flag_actually_writes_audit_evidence() -> None:
    database_url = _local_database_url()
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    validated = _validate_database_url(database_url)
    assert validated == database_url

    # A unique entity_source_id/observed_at pair so this test's row cannot
    # collide with any other test's writes in the same shared database --
    # a global row-count delta would be fragile against suite ordering and
    # reruns, unlike looking up this test's own specific row.
    unique_entity_id = f"db-safety-test-match-{datetime.now(UTC).isoformat()}"
    observed_at = datetime.now(UTC)
    observation = NormalizedObservation(
        source_code="football-data-uk",
        source_type="objective_structured",
        entity_type="match",
        entity_source_id=unique_entity_id,
        entity_identity_hints={},
        metric_name="home_score",
        value=3,
        observed_at=observed_at,
        source_timestamp=None,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version="football-data-uk-v1",
    )

    persistence = _persist_audit_evidence(
        database_url=validated, all_observations=[observation], decisions=[]
    )
    assert persistence["mode"] == "postgresql_ingestion_schema_audit_only"
    assert persistence["observations_written"] == 1

    with connect(validated) as connection:
        row = connection.execute(
            """
            select value from ingestion.source_observations
            where entity_source_id = %s and metric_name = %s and observed_at = %s
            """,
            (unique_entity_id, "home_score", observed_at),
        ).fetchone()
        connection.rollback()
    assert row is not None
    assert row[0] == 3


@pytest.mark.integration
def test_no_flag_means_read_only_canonical_state_check_never_writes() -> None:
    database_url = _local_database_url()
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    validated = _validate_database_url(database_url)
    # _read_canonical_state is a read-only path (assess_real_snapshot only
    # SELECTs, then rolls back) -- exercised here against a real connection
    # to prove it never raises and never depends on any write having
    # happened first.
    canonical = _read_canonical_state(validated)
    assert canonical["mode"] == "postgresql"
    assert "matches_loaded" in canonical
