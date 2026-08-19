"""Unit tests for `db.data_mesh_repository.DataMeshRepository`'s
`metric_granularity` fail-safe boundary (Block 20D.2 final micro-audit).

Pure unit tests over a fake `Connection` double -- no real Postgres, no
`DATABASE_URL`, no `@pytest.mark.integration`. They prove the pre-scan
happens before ANY SQL statement is executed (including the provider-id
lookup), which is precisely what makes it safe against partial writes
within one batch. Real end-to-end legacy persistence against a real
database is already covered by
`tests/integration/test_data_mesh_pipeline.py::test_observation_persistence_is_idempotent`,
unaffected by this change (it persists a `metric_granularity=None`
observation, which this fail-safe never touches).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.db.data_mesh_repository import (
    DataMeshRepository,
    MetricGranularityNotPersistableError,
)

_NOW = datetime(2026, 8, 22, 18, 30, tzinfo=UTC)


class _FakeCursorResult:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeConnection:
    """Records every `execute()` call -- never actually touches a database.
    A test asserting `connection.executed == []` is asserting that not a
    single SQL statement (not even the provider-id lookup) was issued."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _FakeCursorResult:
        self.executed.append((sql, params))
        if "select id from ingestion.providers" in sql:
            return _FakeCursorResult((1,))
        return _FakeCursorResult(None)


def _observation(*, metric_granularity: str | None, metric_name: str = "home_score") -> Any:
    return NormalizedObservation(
        source_code="thesportsdb",
        source_type="objective_structured",
        entity_type="match",
        entity_source_id="repo-test-event-1",
        entity_identity_hints={},
        metric_name=metric_name,
        value=2,
        observed_at=_NOW,
        source_timestamp=_NOW,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version="test-v1",
        metric_granularity=metric_granularity,  # type: ignore[arg-type]
    )


def test_a_a_v2_observation_is_rejected_before_any_insert_occurs() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    v2_observation = _observation(metric_granularity="player_match")

    with pytest.raises(MetricGranularityNotPersistableError):
        repository.persist_observations([v2_observation])

    # Not even the provider-id lookup ran -- the pre-scan happens before
    # any SQL statement, not merely before the INSERT itself.
    assert connection.executed == []


def test_b_a_mixed_batch_fails_before_partially_persisting_the_legacy_item() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    legacy_observation = _observation(metric_granularity=None, metric_name="home_score")
    v2_observation = _observation(metric_granularity="player_match", metric_name="saves")

    with pytest.raises(MetricGranularityNotPersistableError):
        repository.persist_observations([legacy_observation, v2_observation])

    # The legacy item, first in the batch, must never be persisted just
    # because it appears before the V2 item -- the whole batch is scanned
    # up front, so zero writes happen either way.
    assert connection.executed == []


def test_c_legacy_none_granularity_persistence_behavior_is_unchanged() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    legacy_observation = _observation(metric_granularity=None)

    written = repository.persist_observations([legacy_observation])

    assert written == 1
    # Exactly the provider lookup + one INSERT -- the pre-scan adds no
    # extra SQL for a legacy-only batch.
    assert len(connection.executed) == 2
    insert_sql, insert_params = connection.executed[1]
    assert "insert into ingestion.source_observations" in insert_sql
    assert insert_params is not None
    assert insert_params[0] == 1  # provider_id resolved from the fake lookup
    assert insert_params[3] == "repo-test-event-1"  # entity_source_id
    assert insert_params[5] == "home_score"  # metric_name


def test_error_message_names_a_real_offending_identity() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    v2_observation = _observation(metric_granularity="goalkeeper_match", metric_name="saves")

    with pytest.raises(MetricGranularityNotPersistableError) as excinfo:
        repository.persist_observations([v2_observation])

    message = str(excinfo.value)
    assert "goalkeeper_match" in message
    assert "saves" in message
    assert "ingestion.source_observations" in message
