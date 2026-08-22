from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from football_intelligence.jobs.calculate_player_analytics import (
    V1_MODEL_VERSION,
    V2_MODEL_VERSION,
    _persist_versioned_snapshots,
)
from football_intelligence.player_analytics.engine_v2 import (
    PlayerAnalyticsResultV2,
    calculate_player_analytics_v2_result,
)
from football_intelligence.player_analytics.models import (
    PlayerAnalyticsResult,
    PlayerObservation,
)


class _RecordingRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, str, str]] = []

    def replace_snapshots(
        self,
        result: object,
        *,
        scope_key: str,
        model_version: str,
        data_context: str = "real",
        **_kwargs: Any,
    ) -> None:
        self.calls.append((result, scope_key, model_version, data_context))


def test_each_player_engine_is_persisted_under_its_own_model_version() -> None:
    repository = _RecordingRepository()
    v1_result = PlayerAnalyticsResult(features=(), scores=())
    v2_result = PlayerAnalyticsResultV2(features=(), scores=())

    _persist_versioned_snapshots(  # type: ignore[arg-type]
        repository,
        v1_result=v1_result,
        v2_result=v2_result,
        scope_key="test:scope",
    )

    assert repository.calls == [
        (v1_result, "test:scope", V1_MODEL_VERSION, "real"),
        (v2_result, "test:scope", V2_MODEL_VERSION, "real"),
    ]


def test_player_v2_keeps_null_metric_as_missing_evidence_not_zero() -> None:
    observation = PlayerObservation(
        player_id=1,
        player_name="Test Forward",
        match_id=10,
        kickoff_at=datetime(2026, 8, 1, tzinfo=UTC),
        team_id=20,
        minutes=90,
        listed_position="FW",
        possession_pct=None,
        stats={
            "goals": 1.0,
            "assists": 0.0,
            "shots_total": 2.0,
            "shots_on_target": 1.0,
            "tackles": None,
        },
    )

    result = calculate_player_analytics_v2_result(
        [observation],
        scope_key="test:missing-vs-zero",
        calculated_at=datetime(2026, 8, 2, tzinfo=UTC),
    )

    feature_names = {feature.metric_name for feature in result.features}
    assert "goals" in feature_names
    assert "tackles" not in feature_names
    assert result.scores
    assert "tackles" not in result.scores[0].evidence_metrics_available
