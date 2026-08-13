from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.data_mesh.reconciliation import (
    AGREEMENT_BASE_CONFIDENCE,
    CONFLICT_CONFIDENCE,
    SINGLE_SOURCE_CONFIDENCE,
    reconcile_metric,
)

_NOW = datetime(2026, 8, 22, 18, 30, tzinfo=UTC)


def _observation(
    *,
    source_code: str,
    value: object,
    source_type: str = "objective_structured",
    metric_name: str = "home_score",
    observed_at: datetime = _NOW,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=source_code,
        source_type=source_type,  # type: ignore[arg-type]
        entity_type="match",
        entity_source_id=f"{source_code}-1",
        entity_identity_hints={},
        metric_name=metric_name,
        value=value,  # type: ignore[arg-type]
        observed_at=observed_at,
        source_timestamp=observed_at,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version="test-v0",
    )


def test_two_sources_same_value_is_agreed() -> None:
    observations = [
        _observation(source_code="thesportsdb", value=2),
        _observation(source_code="openligadb", value=2),
    ]
    decision = reconcile_metric(
        observations,
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="home_score",
    )
    assert decision.status == "agreed"
    assert decision.candidate_value == 2
    assert decision.source_count == 2
    assert decision.confidence >= AGREEMENT_BASE_CONFIDENCE


def test_single_source_produces_lower_confidence_single_source_status() -> None:
    observations = [_observation(source_code="openligadb", value=3)]
    decision = reconcile_metric(
        observations,
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="home_score",
    )
    assert decision.status == "single_source"
    assert decision.candidate_value == 3
    assert decision.winning_source_code == "openligadb"
    assert decision.confidence == SINGLE_SOURCE_CONFIDENCE
    assert decision.confidence < AGREEMENT_BASE_CONFIDENCE


def test_conflicting_values_are_marked_conflict() -> None:
    observations = [
        _observation(source_code="thesportsdb", value=11),
        _observation(source_code="openligadb", value=13),
    ]
    decision = reconcile_metric(
        observations,
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="shots_total",
    )
    assert decision.status == "conflict"
    assert decision.confidence == CONFLICT_CONFIDENCE


def test_conflict_does_not_average_or_silently_pick_a_value() -> None:
    observations = [
        _observation(source_code="thesportsdb", value=11),
        _observation(source_code="openligadb", value=13),
    ]
    decision = reconcile_metric(
        observations,
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="shots_total",
    )
    # Never 12 (the average), and never silently promoted to one side's value
    # without an explicit priority rule.
    assert decision.candidate_value is None
    assert decision.winning_source_code is None
    assert decision.evidence["values_by_source"] == {"thesportsdb": 11, "openligadb": 13}


def test_conflict_with_explicit_metric_priority_still_stays_conflict_status() -> None:
    observations = [
        _observation(source_code="thesportsdb", value=11),
        _observation(source_code="openligadb", value=13),
    ]
    decision = reconcile_metric(
        observations,
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="shots_total",
        source_priority={"shots_total": ("openligadb",)},
    )
    # A priority rule may propose a display candidate, but the disagreement
    # is never hidden: status remains "conflict" and the losing value stays
    # in the evidence.
    assert decision.status == "conflict"
    assert decision.candidate_value == 13
    assert decision.winning_source_code == "openligadb"
    assert decision.evidence["priority_rule_applied"] is True
    assert decision.evidence["values_by_source"]["thesportsdb"] == 11


def test_int_and_float_equal_values_do_not_create_a_false_conflict() -> None:
    observations = [
        _observation(source_code="thesportsdb", value=2),
        _observation(source_code="openligadb", value=2.0),
    ]
    decision = reconcile_metric(
        observations,
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="home_score",
    )
    assert decision.status == "agreed"


def test_no_objective_observations_is_unresolved() -> None:
    qualitative_only = [
        _observation(source_code="fan-forum", value="great game", source_type="qualitative_fan")
    ]
    decision = reconcile_metric(
        qualitative_only,
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="vibe",
    )
    assert decision.status == "unresolved"
    assert decision.source_count == 0


def test_qualitative_observations_never_participate_alongside_objective_ones() -> None:
    observations = [
        _observation(source_code="thesportsdb", value=2),
        _observation(source_code="fan-forum", value=99, source_type="qualitative_fan"),
    ]
    decision = reconcile_metric(
        observations,
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="home_score",
    )
    # Only the objective source counts -- the qualitative value never enters
    # the objective reconciliation at all.
    assert decision.status == "single_source"
    assert decision.participating_sources == ("thesportsdb",)


def test_only_the_latest_observation_per_source_counts() -> None:
    earlier = _observation(source_code="thesportsdb", value=1, observed_at=_NOW)
    later = _observation(
        source_code="thesportsdb",
        value=2,
        observed_at=datetime(2026, 8, 22, 19, 0, tzinfo=UTC),
    )
    decision = reconcile_metric(
        [earlier, later],
        logical_entity_key="match:1",
        entity_type="match",
        metric_name="home_score",
    )
    assert decision.status == "single_source"
    assert decision.candidate_value == 2
