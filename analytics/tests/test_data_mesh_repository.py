"""Unit tests for `db.data_mesh_repository.DataMeshRepository`'s V2
`metric_granularity` persistence (Block 20D.4).

Pure unit tests over a fake `Connection` double -- no real Postgres, no
`DATABASE_URL`, no `@pytest.mark.integration`. They prove the SQL this
repository issues: `metric_granularity` is included in both the column
list and the `ON CONFLICT` target for `source_observations`/
`reconciliation_decisions`, and persisting a V2 (non-`None`
`metric_granularity`) observation no longer raises (the
`MetricGranularityNotPersistableError` fail-closed guard that used to
reject every V2 batch here was removed once
`database/migrations/20260820100000_add_data_mesh_v2_persistence.sql`
widened both tables' natural keys with `UNIQUE NULLS NOT DISTINCT`).

The actual upsert BEHAVIOR this SQL shape is designed to produce (legacy
NULL-granularity idempotence, same-identity-same-granularity idempotence,
cross-granularity coexistence) can only be proven against a real
PostgreSQL engine -- that proof lives in
`database/tests/015_data_mesh_v2_contract.sql`, run by CI, not here."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from football_intelligence.data_mesh.models import NormalizedObservation, ReconciliationDecision
from football_intelligence.db.data_mesh_repository import DataMeshRepository

_NOW = datetime(2026, 8, 22, 18, 30, tzinfo=UTC)


class _FakeCursorResult:
    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeCursor:
    def __init__(self, connection: _FakeConnection) -> None:
        self._connection = connection

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def executemany(self, sql: str, params: list[tuple[Any, ...]]) -> None:
        self._connection.executemany_calls.append((sql, params))


class _FakeConnection:
    """Records SQL calls -- never actually touches a database."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _FakeCursorResult:
        self.executed.append((sql, params))
        if "select id from ingestion.providers" in sql:
            return _FakeCursorResult((1,))
        return _FakeCursorResult(None)

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)


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


def _decision(
    *, metric_granularity: str | None, metric_name: str = "saves"
) -> ReconciliationDecision:
    return ReconciliationDecision(
        logical_entity_key="player-match:repo-test-match-1:repo-test-player-1",
        entity_type="player",
        metric_name=metric_name,
        candidate_value=3,
        status="agreed",
        confidence=0.6,
        winning_source_code=None,
        participating_sources=("statsbomb-open", "wyscout-open"),
        source_count=2,
        evidence={"values_by_source": {"statsbomb-open": 3, "wyscout-open": 3}},
        model_version="data-mesh-reconciliation-v2.0",
        calculated_at=_NOW,
        metric_granularity=metric_granularity,  # type: ignore[arg-type]
    )


def test_legacy_none_granularity_observation_persists_unchanged() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    legacy_observation = _observation(metric_granularity=None)

    written = repository.persist_observations([legacy_observation])

    assert written == 1
    assert len(connection.executed) == 2  # provider lookup + one INSERT
    insert_sql, insert_params = connection.executed[1]
    assert "insert into ingestion.source_observations" in insert_sql
    assert "metric_granularity" in insert_sql
    assert insert_params is not None
    assert insert_params[0] == 1  # provider_id resolved from the fake lookup
    assert insert_params[3] == "repo-test-event-1"  # entity_source_id
    assert insert_params[5] == "home_score"  # metric_name
    assert insert_params[6] is None  # metric_granularity


def test_v2_observation_persists_without_raising() -> None:
    """The old MetricGranularityNotPersistableError guard rejected every
    batch containing a non-None metric_granularity -- removed once the V2
    schema migration widened the natural key. This must no longer raise."""

    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    v2_observation = _observation(metric_granularity="goalkeeper_match", metric_name="saves")

    written = repository.persist_observations([v2_observation])

    assert written == 1
    insert_sql, insert_params = connection.executed[1]
    assert insert_params is not None
    assert insert_params[6] == "goalkeeper_match"


def test_observation_on_conflict_target_includes_metric_granularity() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    repository.persist_observations([_observation(metric_granularity="player_match")])

    insert_sql, _params = connection.executed[1]
    on_conflict_target = insert_sql.split("on conflict (")[1].split(")")[0]
    assert "metric_granularity" in on_conflict_target
    assert "observed_at" in on_conflict_target


def test_mixed_legacy_and_v2_batch_persists_every_item() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    legacy_observation = _observation(metric_granularity=None, metric_name="home_score")
    v2_observation = _observation(metric_granularity="player_match", metric_name="saves")

    written = repository.persist_observations([legacy_observation, v2_observation])

    assert written == 2


def test_large_observation_path_uses_bounded_executemany_batches() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    observations = [
        _observation(metric_granularity="player_match", metric_name=f"metric-{index}")
        for index in range(5)
    ]

    written = repository.persist_observations_batched(observations, batch_size=2)

    assert written == 5
    assert len(connection.executed) == 1  # provider lookup is cached across all batches
    assert len(connection.executemany_calls) == 3
    assert [len(params) for _sql, params in connection.executemany_calls] == [2, 2, 1]
    for sql, params in connection.executemany_calls:
        assert "insert into ingestion.source_observations" in sql
        assert "metric_granularity" in sql
        assert all(row[0] == 1 for row in params)


def test_batched_observation_path_rejects_non_positive_batch_size() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]

    try:
        repository.persist_observations_batched([], batch_size=0)
    except ValueError as exc:
        assert str(exc) == "batch_size must be positive"
    else:
        raise AssertionError("expected ValueError")


def test_legacy_decision_persists_with_null_granularity() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    legacy_decision = _decision(metric_granularity=None)

    written = repository.replace_decisions([legacy_decision])

    assert written == 1
    insert_sql, insert_params = connection.executed[0]
    assert "insert into ingestion.reconciliation_decisions" in insert_sql
    assert "metric_granularity" in insert_sql
    assert insert_params is not None
    assert insert_params[3] is None  # metric_granularity


def test_v2_decision_persists_with_explicit_granularity() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    v2_decision = _decision(metric_granularity="goalkeeper_match")

    written = repository.replace_decisions([v2_decision])

    assert written == 1
    insert_sql, insert_params = connection.executed[0]
    assert insert_params is not None
    assert insert_params[3] == "goalkeeper_match"


def test_decision_on_conflict_target_includes_metric_granularity() -> None:
    connection = _FakeConnection()
    repository = DataMeshRepository(connection)  # type: ignore[arg-type]
    repository.replace_decisions([_decision(metric_granularity="player_match")])

    insert_sql, _params = connection.executed[0]
    on_conflict_target = insert_sql.split("on conflict (")[1].split(")")[0]
    assert "metric_granularity" in on_conflict_target
    assert "model_version" in on_conflict_target
