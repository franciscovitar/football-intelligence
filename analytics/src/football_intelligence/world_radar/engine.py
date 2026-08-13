"""Deterministic, competition-relative scoring for World Radar V1.

Scores are percentile ranks computed strictly within one competition's
candidate pool. A score of 90 in one competition is never claimed to be
equivalent to a 90 in another: there is no cross-league strength coefficient
in V1.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime

from football_intelligence.world_radar.models import (
    PlayerRadarCandidate,
    PlayerRadarSnapshot,
    RadarProfile,
    RawPlayerFeedEntry,
)

MODEL_VERSION = "world-radar-v1.0"

METRIC_NAMES: tuple[str, ...] = (
    "goals_per90",
    "assists_per90",
    "shots_on_target_per90",
    "key_passes_per90",
    "successful_dribbles_per90",
)

ATTACKER_WEIGHTS: dict[str, float] = {
    "goals_per90": 0.35,
    "shots_on_target_per90": 0.20,
    "assists_per90": 0.20,
    "key_passes_per90": 0.15,
    "successful_dribbles_per90": 0.10,
}

MIDFIELDER_WEIGHTS: dict[str, float] = {
    "assists_per90": 0.30,
    "key_passes_per90": 0.25,
    "goals_per90": 0.20,
    "successful_dribbles_per90": 0.15,
    "shots_on_target_per90": 0.10,
}

MINUTES_CONFIDENCE_CAP = 1200.0
APPEARANCES_CONFIDENCE_CAP = 15.0
ELITE_PERCENTILE_THRESHOLD = 85.0
_WEIGHT_EPSILON = 1e-9


def _validate_weights(name: str, weights: dict[str, float]) -> None:
    total = sum(weights.values())
    if abs(total - 1.0) > _WEIGHT_EPSILON:
        raise AssertionError(f"{name} must sum to 1.0, got {total}")
    for metric_name, weight in weights.items():
        if metric_name not in METRIC_NAMES:
            raise AssertionError(f"{name} references unknown metric '{metric_name}'")
        if weight <= 0:
            raise AssertionError(f"{name} weight for '{metric_name}' must be positive")


_validate_weights("ATTACKER_WEIGHTS", ATTACKER_WEIGHTS)
_validate_weights("MIDFIELDER_WEIGHTS", MIDFIELDER_WEIGHTS)


def merge_feed_entries(entries: list[RawPlayerFeedEntry]) -> list[PlayerRadarCandidate]:
    """Merge topscorers+topassists entries so each player is processed once."""

    by_id: dict[str, list[RawPlayerFeedEntry]] = defaultdict(list)
    for entry in entries:
        by_id[entry.provider_player_id].append(entry)
    return [
        _merge_candidate(provider_player_id, by_id[provider_player_id])
        for provider_player_id in sorted(by_id)
    ]


def _merge_candidate(
    provider_player_id: str,
    items: list[RawPlayerFeedEntry],
) -> PlayerRadarCandidate:
    def pick_text(values: list[str | None]) -> str | None:
        for value in values:
            if value is not None:
                return value
        return None

    def pick_int(values: list[int | None]) -> int | None:
        for value in values:
            if value is not None:
                return value
        return None

    primary = items[0]
    source_lists = tuple(sorted({item.source_list for item in items}))
    return PlayerRadarCandidate(
        provider_player_id=provider_player_id,
        player_name=primary.player_name,
        team_name=pick_text([item.team_name for item in items]),
        position=pick_text([item.position for item in items]),
        appearances=pick_int([item.appearances for item in items]),
        minutes=pick_int([item.minutes for item in items]),
        goals=pick_int([item.goals for item in items]),
        assists=pick_int([item.assists for item in items]),
        shots_total=pick_int([item.shots_total for item in items]),
        shots_on_target=pick_int([item.shots_on_target for item in items]),
        key_passes=pick_int([item.key_passes for item in items]),
        dribbles_successful=pick_int([item.dribbles_successful for item in items]),
        source_lists=source_lists,
    )


def calculate_metrics(candidate: PlayerRadarCandidate) -> dict[str, float | None]:
    """Per-90 metrics, computed only when minutes > 0. Missing stays missing."""

    minutes = candidate.minutes
    if minutes is None or minutes <= 0:
        return dict.fromkeys(METRIC_NAMES)

    factor = 90.0 / minutes
    raw_values: dict[str, int | None] = {
        "goals_per90": candidate.goals,
        "assists_per90": candidate.assists,
        "shots_on_target_per90": candidate.shots_on_target,
        "key_passes_per90": candidate.key_passes,
        "successful_dribbles_per90": candidate.dribbles_successful,
    }
    return {name: _per90(value, factor) for name, value in raw_values.items()}


def _per90(value: int | None, factor: float) -> float | None:
    if value is None:
        return None
    return round(value * factor, 4)


def classify_profile(position: str | None) -> RadarProfile:
    if position is not None and "mid" in position.casefold():
        return "midfielder"
    return "attacker"


def weights_for_profile(profile: RadarProfile) -> dict[str, float]:
    return dict(MIDFIELDER_WEIGHTS if profile == "midfielder" else ATTACKER_WEIGHTS)


def _percentile_rank(values: Sequence[float], value: float) -> float:
    if len(values) <= 1:
        return 50.0
    less = sum(1 for item in values if item < value)
    equal = sum(1 for item in values if item == value)
    return 100.0 * (less + equal / 2.0) / len(values)


def calculate_world_radar(
    candidates: list[PlayerRadarCandidate],
    *,
    provider_code: str,
    competition_code: str,
    competition_name: str,
    country: str,
    season_label: str,
    calculated_at: datetime | None = None,
) -> tuple[PlayerRadarSnapshot, ...]:
    now = calculated_at or datetime.now(UTC)

    eligible = [item for item in candidates if item.minutes is not None and item.minutes > 0]
    metrics_by_id = {item.provider_player_id: calculate_metrics(item) for item in eligible}

    pool_values: dict[str, list[float]] = {name: [] for name in METRIC_NAMES}
    for metrics in metrics_by_id.values():
        for name in METRIC_NAMES:
            value = metrics[name]
            if value is not None:
                pool_values[name].append(value)

    snapshots: list[PlayerRadarSnapshot] = []
    for candidate in sorted(eligible, key=lambda item: item.provider_player_id):
        metrics = metrics_by_id[candidate.provider_player_id]
        profile = classify_profile(candidate.position)
        weights = weights_for_profile(profile)

        percentiles: dict[str, float] = {}
        weighted_sum = 0.0
        weight_total = 0.0
        for name, weight in weights.items():
            value = metrics[name]
            if value is None:
                continue
            percentile = _percentile_rank(pool_values[name], value)
            percentiles[name] = percentile
            weighted_sum += weight * percentile
            weight_total += weight
        score = weighted_sum / weight_total if weight_total > 0 else 0.0

        confidence = _confidence(candidate)
        reasons = _reasons(candidate, percentiles)

        snapshots.append(
            PlayerRadarSnapshot(
                provider_code=provider_code,
                provider_player_id=candidate.provider_player_id,
                player_name=candidate.player_name,
                team_name=candidate.team_name,
                competition_code=competition_code,
                competition_name=competition_name,
                country=country,
                season_label=season_label,
                position=candidate.position,
                appearances=candidate.appearances,
                minutes=candidate.minutes,
                goals=candidate.goals,
                assists=candidate.assists,
                metrics=metrics,
                radar_score=round(_clamp100(score), 2),
                confidence=round(confidence, 5),
                reasons=reasons,
                source_lists=candidate.source_lists,
                profile=profile,
                model_version=MODEL_VERSION,
                calculated_at=now,
            )
        )
    return tuple(snapshots)


def _confidence(candidate: PlayerRadarCandidate) -> float:
    minutes = candidate.minutes or 0
    appearances = candidate.appearances or 0
    minutes_component = min(1.0, minutes / MINUTES_CONFIDENCE_CAP)
    appearances_component = min(1.0, appearances / APPEARANCES_CONFIDENCE_CAP)
    source_component = 1.0 if len(candidate.source_lists) >= 2 else 0.5
    return _clamp01(0.5 * minutes_component + 0.3 * appearances_component + 0.2 * source_component)


def _reasons(candidate: PlayerRadarCandidate, percentiles: dict[str, float]) -> tuple[str, ...]:
    reasons: list[str] = []
    if "topscorers" in candidate.source_lists:
        reasons.append("top_scorer_feed")
    if "topassists" in candidate.source_lists:
        reasons.append("top_assist_feed")
    if percentiles.get("goals_per90", 0.0) >= ELITE_PERCENTILE_THRESHOLD:
        reasons.append("elite_goals_per90")
    creation_percentile = max(
        percentiles.get("assists_per90", 0.0),
        percentiles.get("key_passes_per90", 0.0),
    )
    if creation_percentile >= ELITE_PERCENTILE_THRESHOLD:
        reasons.append("elite_creation_per90")
    return tuple(reasons)


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _clamp100(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(100.0, max(0.0, value))
