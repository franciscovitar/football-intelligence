from __future__ import annotations

import dataclasses

from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2, catalog_by_granularity
from football_intelligence.normalization.models import (
    MatchRecord,
    PlayerAppearanceRecord,
    PlayerMatchStatsRecord,
    TeamLineupRecord,
    TeamMatchStatsRecord,
)

_EXCLUDED = {
    "match_external_id",
    "team_external_id",
    "player_external_id",
    "home_team_external_id",
    "away_team_external_id",
    "external_id",
}


def _dto_field_names(dataclass_type: type) -> set[str]:
    return {field.name for field in dataclasses.fields(dataclass_type)} - _EXCLUDED


def test_catalog_size_is_in_target_range() -> None:
    assert 110 <= len(METRIC_CATALOG_V2) <= 130


def test_catalog_entries_are_unique_per_key_and_granularity() -> None:
    keys = [(metric.key, metric.granularity) for metric in METRIC_CATALOG_V2]
    assert len(keys) == len(set(keys))


def test_catalog_preserves_the_48_dto_derived_metrics() -> None:
    catalog_keys = {metric.key for metric in METRIC_CATALOG_V2}
    for dto in (
        MatchRecord,
        TeamMatchStatsRecord,
        TeamLineupRecord,
        PlayerAppearanceRecord,
        PlayerMatchStatsRecord,
    ):
        assert _dto_field_names(dto) <= catalog_keys
    assert "advanced.xg" in catalog_keys


def test_same_key_can_exist_at_different_granularities() -> None:
    granularities = {metric.granularity for metric in METRIC_CATALOG_V2 if metric.key == "saves"}
    assert {"player_match", "goalkeeper_match"} <= granularities


def test_derived_metrics_are_never_marked_raw_and_vice_versa() -> None:
    for metric in METRIC_CATALOG_V2:
        assert metric.kind in ("raw", "derived")


def test_non_percentile_eligible_identity_fields_are_not_per90_eligible() -> None:
    # Identity/context fields (names, labels, timestamps) should never claim
    # to be a per90-normalizable rate.
    for metric in METRIC_CATALOG_V2:
        if metric.unit == "label":
            assert metric.per90_eligible is False


def test_every_metric_has_a_non_blank_min_sample_policy() -> None:
    for metric in METRIC_CATALOG_V2:
        assert metric.min_sample_policy.strip()
        assert metric.display_name.strip()
        assert metric.semantic_version.strip()


def test_catalog_by_granularity_groups_every_metric_exactly_once() -> None:
    grouped = catalog_by_granularity()
    total = sum(len(metrics) for metrics in grouped.values())
    assert total == len(METRIC_CATALOG_V2)
    for granularity, metrics in grouped.items():
        assert all(metric.granularity == granularity for metric in metrics)


def test_goalkeeping_metrics_never_have_shooting_or_dribbling_category() -> None:
    goalkeeping = [metric for metric in METRIC_CATALOG_V2 if metric.category == "goalkeeping"]
    assert goalkeeping
    assert all(metric.category == "goalkeeping" for metric in goalkeeping)
