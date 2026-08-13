from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.data_mesh.models import NormalizedObservation, ReconciliationDecision
from football_intelligence.data_mesh.reconciliation import MODEL_VERSION
from football_intelligence.db.data_mesh_repository import DataMeshRepository
from football_intelligence.db.provider_repository import connect


@pytest.mark.integration
def test_observation_persistence_is_idempotent() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    now = datetime(2026, 8, 22, 18, 30, tzinfo=UTC)
    observation = NormalizedObservation(
        source_code="thesportsdb",
        source_type="objective_structured",
        entity_type="match",
        entity_source_id="mesh-integration-event-1",
        entity_identity_hints={"home_team_name": "Integration Home"},
        metric_name="home_score",
        value=2,
        observed_at=now,
        source_timestamp=now,
        source_reference="eventsseason.php?id=4331",
        ingestion_run_id=None,
        semantic_version="data-mesh-v0.1",
    )

    with connect(database_url) as connection:
        repository = DataMeshRepository(connection)
        first_written = repository.persist_observations([observation])
        assert first_written == 1
        assert repository.observation_count() >= 1

        before_count = repository.observation_count()
        # Re-persisting the identical natural key must upsert, not duplicate.
        second_written = repository.persist_observations([observation])
        assert second_written == 1
        assert repository.observation_count() == before_count

        row = connection.execute(
            """
            select value
            from ingestion.source_observations
            where entity_source_id = 'mesh-integration-event-1'
              and metric_name = 'home_score'
            """
        ).fetchone()
        assert row is not None
        assert int(row[0]) == 2

        connection.rollback()


@pytest.mark.integration
def test_decision_persistence_is_idempotent() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    now = datetime.now(UTC)
    decision = ReconciliationDecision(
        logical_entity_key="match:GER_BL1:integration-test",
        entity_type="match",
        metric_name="home_score",
        candidate_value=2,
        status="agreed",
        confidence=0.7,
        winning_source_code=None,
        participating_sources=("openligadb", "thesportsdb"),
        source_count=2,
        evidence={"values_by_source": {"openligadb": 2, "thesportsdb": 2}},
        model_version=MODEL_VERSION,
        calculated_at=now,
    )

    with connect(database_url) as connection:
        repository = DataMeshRepository(connection)
        first_written = repository.replace_decisions([decision])
        assert first_written == 1
        before_count = repository.decision_count()

        second_written = repository.replace_decisions([decision])
        assert second_written == 1
        assert repository.decision_count() == before_count

        row = connection.execute(
            """
            select status, confidence
            from ingestion.reconciliation_decisions
            where logical_entity_key = 'match:GER_BL1:integration-test'
              and metric_name = 'home_score'
              and model_version = %s
            """,
            (MODEL_VERSION,),
        ).fetchone()
        assert row is not None
        assert str(row[0]) == "agreed"

        connection.rollback()
