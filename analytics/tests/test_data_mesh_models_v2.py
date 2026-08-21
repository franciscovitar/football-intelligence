"""Block 20D.4: `ReconciliationDecision.metric_granularity` and the widened
`ReconciliationStatus` vocabulary."""

from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.data_mesh.models import ReconciliationDecision

_NOW = datetime(2026, 8, 22, 18, 30, tzinfo=UTC)


def _decision(**overrides: object) -> ReconciliationDecision:
    defaults: dict[str, object] = dict(
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="home_score",
        candidate_value=2,
        status="agreed",
        confidence=0.6,
        winning_source_code=None,
        participating_sources=("thesportsdb", "openligadb"),
        source_count=2,
        evidence={},
        model_version="data-mesh-reconciliation-v0.1",
        calculated_at=_NOW,
    )
    defaults.update(overrides)
    return ReconciliationDecision(**defaults)  # type: ignore[arg-type]


def test_v0_style_construction_defaults_metric_granularity_to_none() -> None:
    decision = _decision()
    assert decision.metric_granularity is None


def test_v2_construction_carries_an_explicit_metric_granularity() -> None:
    decision = _decision(
        metric_granularity="goalkeeper_match",
        model_version="data-mesh-reconciliation-v2.0",
    )
    assert decision.metric_granularity == "goalkeeper_match"


def test_saves_player_match_and_goalkeeper_match_are_distinguishable_decisions() -> None:
    player_match_decision = _decision(
        metric_name="saves", metric_granularity="player_match", logical_entity_key="a"
    )
    goalkeeper_match_decision = _decision(
        metric_name="saves", metric_granularity="goalkeeper_match", logical_entity_key="a"
    )
    # Same logical_entity_key and metric_name, but distinguishable by
    # metric_granularity -- the exact information the pre-20D.4 shape lacked.
    assert player_match_decision.metric_granularity != goalkeeper_match_decision.metric_granularity
    assert player_match_decision != goalkeeper_match_decision


def test_not_comparable_and_methodology_pending_are_valid_statuses() -> None:
    not_comparable = _decision(status="not_comparable", candidate_value=None)
    methodology_pending = _decision(status="methodology_pending", candidate_value=None)
    assert not_comparable.status == "not_comparable"
    assert methodology_pending.status == "methodology_pending"
    assert not_comparable.candidate_value is None
    assert methodology_pending.candidate_value is None
