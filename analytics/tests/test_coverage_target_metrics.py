from __future__ import annotations

import dataclasses

from football_intelligence.coverage_lab.target_metrics import build_target_metric_catalog
from football_intelligence.metric_catalog import METRIC_CATALOG_V2
from football_intelligence.normalization.models import (
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


def test_catalog_contains_all_player_match_stats_metrics() -> None:
    catalog_names = {metric.metric_name for metric in build_target_metric_catalog()}
    assert _dto_field_names(PlayerMatchStatsRecord) <= catalog_names


def test_catalog_contains_all_team_match_stats_metrics() -> None:
    catalog_names = {metric.metric_name for metric in build_target_metric_catalog()}
    assert _dto_field_names(TeamMatchStatsRecord) <= catalog_names


def test_catalog_preserves_appearance_and_lineup_metrics() -> None:
    catalog_names = {metric.metric_name for metric in build_target_metric_catalog()}
    assert _dto_field_names(PlayerAppearanceRecord) <= catalog_names
    assert _dto_field_names(TeamLineupRecord) <= catalog_names


def test_catalog_includes_advanced_namespace() -> None:
    catalog = build_target_metric_catalog()
    advanced = [metric for metric in catalog if metric.metric_name.startswith("advanced.")]
    assert advanced
    assert all(metric.domain == "advanced" for metric in advanced)


def test_catalog_never_shrinks_statistical_dtos() -> None:
    # A regression guard: the catalog is derived from the DTOs, so this can
    # only fail if someone shrinks a DTO or the catalog builder itself.
    catalog = build_target_metric_catalog()
    domains = {metric.domain for metric in catalog}
    assert {"match", "team_stats", "tactical", "appearance", "player_stats", "advanced"} <= domains
    assert len(catalog) >= (
        len(_dto_field_names(PlayerMatchStatsRecord))
        + len(_dto_field_names(TeamMatchStatsRecord))
        + len(_dto_field_names(TeamLineupRecord))
        + len(_dto_field_names(PlayerAppearanceRecord))
    )


def test_catalog_entries_are_unique_per_metric_and_granularity() -> None:
    # `metric_name` alone is not the identity: e.g. "shots_total" legitimately
    # exists at both team and player granularity, meaning different things.
    # The true identity is (metric_name, granularity).
    catalog = build_target_metric_catalog()
    keys = [(metric.metric_name, metric.granularity) for metric in catalog]
    assert len(keys) == len(set(keys))


def test_same_metric_name_can_exist_at_different_granularities() -> None:
    catalog = build_target_metric_catalog()
    shots_total_granularities = {
        metric.granularity for metric in catalog if metric.metric_name == "shots_total"
    }
    assert {"team_match", "player_match"} <= shots_total_granularities


def test_coverage_catalog_preserves_every_catalog_identity_and_all_nine_grains() -> None:
    coverage = build_target_metric_catalog()
    expected = {(metric.key, metric.granularity) for metric in METRIC_CATALOG_V2}
    actual = {(metric.metric_name, metric.granularity) for metric in coverage}

    assert len(coverage) == len(METRIC_CATALOG_V2)
    assert actual == expected
    assert {metric.granularity for metric in coverage} == {
        "competition",
        "team",
        "team_match",
        "match",
        "player_appearance",
        "player_match",
        "player_season",
        "goalkeeper_match",
        "goalkeeper_season",
    }
