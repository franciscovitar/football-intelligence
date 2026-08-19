from __future__ import annotations

import dataclasses

from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2, catalog_by_granularity
from football_intelligence.metric_catalog.types import CATALOG_V2_VERSION
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


def test_catalog_has_no_arbitrary_upper_ceiling() -> None:
    assert len(METRIC_CATALOG_V2) >= 110


def test_catalog_contains_every_block_16_required_metric_at_its_product_grain() -> None:
    identities = {(metric.key, metric.granularity) for metric in METRIC_CATALOG_V2}
    player_metrics = {
        "goals_per_shot",
        "goals_per_shot_on_target",
        "big_chances_missed",
        "touches_in_box",
        "headed_shots",
        "shot_distance",
        "non_penalty_goals_minus_npxg",
        "passes_into_final_third",
        "shot_creating_actions",
        "goal_creating_actions",
        "xa_per90",
        "expected_threat_pass",
        "expected_threat_created",
        "expected_assists_open_play",
        "short_passes_accurate",
        "medium_passes_accurate",
        "long_passes_accurate",
        "progressive_pass_distance",
        "switches",
        "passes_under_pressure",
        "passes_received",
        "progressive_passes_received",
        "progressive_carry_distance",
        "carry_distance",
        "carries_into_box",
        "progressive_actions",
        "ball_progressions",
        "touches",
        "touches_final_third",
        "touches_box",
        "players_beaten",
        "take_on_success_pct",
        "turnovers",
        "receiving_errors",
        "shot_blocks",
        "pass_blocks",
        "successful_pressures",
        "pressure_success_pct",
        "errors_leading_to_shot",
        "errors_leading_to_goal",
        "ground_duels",
        "ground_duels_won",
        "aerial_duels_won",
        "aerial_duel_win_pct",
    }
    goalkeeper_metrics = {
        "xg_on_target_faced",
        "psxg",
        "crosses_stopped",
        "sweeper_actions",
        "passes",
        "long_passes",
        "launches",
        "average_distance_from_goal",
    }
    team_metrics = {
        "npxg",
        "npxga",
        "shots_on_target_allowed",
        "xga_per_shot",
        "big_chances",
        "big_chances_allowed",
        "box_entries",
        "touches_in_box",
        "high_turnovers",
        "successful_pressures",
        "counter_attacks",
        "counter_attack_shots",
        "transition_xg",
        "deep_completions",
    }

    assert {(key, "player_match") for key in player_metrics} <= identities
    assert {(key, "goalkeeper_match") for key in goalkeeper_metrics} <= identities
    assert {(key, "team_match") for key in team_metrics} <= identities


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


def test_home_away_is_team_match_granularity_and_carries_the_current_release_version() -> None:
    # Block 20D.2 final micro-audit: home_away's real catalog identity is
    # (key="home_away", granularity="team_match") -- corrected from the
    # earlier, wrong "match" classification (the primitive is inherently
    # per-team-in-this-match, not a single match-wide value). The catalog
    # release version must not stay attached to the old identity.
    home_away = next(metric for metric in METRIC_CATALOG_V2 if metric.key == "home_away")
    assert home_away.granularity == "team_match"
    assert home_away.semantic_version == CATALOG_V2_VERSION
    assert CATALOG_V2_VERSION != "metric-catalog-v2.0"
    assert not any(
        metric.key == "home_away" and metric.granularity == "match" for metric in METRIC_CATALOG_V2
    )


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
