"""Role-aware, shrinkage-stabilized player scoring."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from football_intelligence.player_analytics.config import (
    DEFENSIVE_CONTEXT_METRICS,
    DIMENSION_METRICS,
    FEATURE_METRICS,
    ROLE_ALIASES,
    ROLE_DIMENSIONS,
    ROLE_SCORE_WEIGHTS,
    WINDOWS,
)
from football_intelligence.player_analytics.models import (
    PlayerAnalyticsResult,
    PlayerFeature,
    PlayerObservation,
    PlayerScore,
)

MODEL_VERSION = "player-v1.0"
_PRIOR_MINUTES = 450.0
_FORM_HALF_LIFE_APPEARANCES = 3.0
_GOALKEEPER_CONFIDENCE_CAP = 0.65


@dataclass(frozen=True, slots=True)
class _PlayerAggregate:
    player_id: int
    player_name: str
    role: str
    role_confidence: float
    minutes: int
    appearances: int
    raw_rates: dict[str, float]
    context_rates: dict[str, float]


@dataclass(frozen=True, slots=True)
class _FeatureValue:
    raw_rate: float
    adjusted_rate: float
    percentile: float
    sample_size: int


def calculate_player_analytics(
    observations: Sequence[PlayerObservation],
    *,
    scope_key: str,
    calculated_at: datetime | None = None,
) -> PlayerAnalyticsResult:
    """Calculate V1 features and scores for each configured window.

    `last_3`, `last_5`, and `last_10` use exponentially decaying appearance
    weights. `season` uses equal weighting. Rates are shrunk toward the
    role/window population mean before percentile conversion.
    """

    if not scope_key.strip():
        raise ValueError("scope_key must not be blank")

    effective_calculated_at = calculated_at or datetime.now(UTC)
    grouped = _group_observations(observations)

    features: list[PlayerFeature] = []
    scores: list[PlayerScore] = []

    for window_name, appearance_limit in WINDOWS:
        aggregates = _aggregate_window(
            grouped,
            window_name=window_name,
            appearance_limit=appearance_limit,
        )
        by_role = _group_aggregates_by_role(aggregates)

        for role, role_population in by_role.items():
            feature_map = _build_role_features(role_population)

            for aggregate in role_population:
                player_features = feature_map[aggregate.player_id]
                for metric_name, value in player_features.items():
                    features.append(
                        PlayerFeature(
                            player_id=aggregate.player_id,
                            player_name=aggregate.player_name,
                            scope_key=scope_key,
                            window=window_name,
                            role=role,
                            metric_name=metric_name,
                            minutes=aggregate.minutes,
                            appearances=aggregate.appearances,
                            raw_per90=round(value.raw_rate, 4),
                            adjusted_per90=round(value.adjusted_rate, 4),
                            percentile=round(value.percentile, 2),
                            reference_sample_size=value.sample_size,
                            model_version=MODEL_VERSION,
                            calculated_at=effective_calculated_at,
                        )
                    )

                score = _score_player(
                    aggregate,
                    player_features,
                    population_size=len(role_population),
                )
                scores.append(
                    PlayerScore(
                        player_id=aggregate.player_id,
                        player_name=aggregate.player_name,
                        scope_key=scope_key,
                        window=window_name,
                        role=role,
                        role_confidence=round(aggregate.role_confidence, 4),
                        minutes=aggregate.minutes,
                        appearances=aggregate.appearances,
                        overall_score=round(score[0], 2),
                        confidence=round(score[1], 4),
                        dimension_scores={
                            name: round(value, 2) for name, value in score[2].items()
                        },
                        reference_sample_size=len(role_population),
                        model_version=MODEL_VERSION,
                        calculated_at=effective_calculated_at,
                    )
                )

    return PlayerAnalyticsResult(features=tuple(features), scores=tuple(scores))


def _group_observations(
    observations: Sequence[PlayerObservation],
) -> dict[int, list[PlayerObservation]]:
    grouped: dict[int, list[PlayerObservation]] = defaultdict(list)
    for observation in observations:
        if observation.minutes <= 0:
            continue
        grouped[observation.player_id].append(observation)

    for player_observations in grouped.values():
        player_observations.sort(key=lambda item: item.kickoff_at, reverse=True)
    return dict(grouped)


def _aggregate_window(
    grouped: dict[int, list[PlayerObservation]],
    *,
    window_name: str,
    appearance_limit: int | None,
) -> list[_PlayerAggregate]:
    result: list[_PlayerAggregate] = []

    for player_observations in grouped.values():
        role, role_confidence = _primary_role(player_observations)
        if role is None:
            continue

        selected = (
            player_observations
            if appearance_limit is None
            else player_observations[:appearance_limit]
        )
        if not selected:
            continue

        minutes = sum(item.minutes for item in selected)
        if minutes <= 0:
            continue

        raw_rates: dict[str, float] = {}
        context_rates: dict[str, float] = {}
        for metric_name in FEATURE_METRICS:
            raw_rate, context_rate = _metric_rates(
                selected,
                metric_name=metric_name,
                use_recency_weights=window_name != "season",
            )
            raw_rates[metric_name] = raw_rate
            context_rates[metric_name] = context_rate

        result.append(
            _PlayerAggregate(
                player_id=selected[0].player_id,
                player_name=selected[0].player_name,
                role=role,
                role_confidence=role_confidence,
                minutes=minutes,
                appearances=len(selected),
                raw_rates=raw_rates,
                context_rates=context_rates,
            )
        )

    return result


def _primary_role(observations: Sequence[PlayerObservation]) -> tuple[str | None, float]:
    minutes_by_role: dict[str, int] = defaultdict(int)
    for observation in observations:
        role = _normalize_role(observation.listed_position)
        if role is not None:
            minutes_by_role[role] += observation.minutes

    total_positioned_minutes = sum(minutes_by_role.values())
    if total_positioned_minutes <= 0:
        return None, 0.0

    role, role_minutes = max(minutes_by_role.items(), key=lambda item: item[1])
    return role, role_minutes / total_positioned_minutes


def _normalize_role(value: str | None) -> str | None:
    if value is None:
        return None
    return ROLE_ALIASES.get(value.strip().upper())


def _metric_rates(
    observations: Sequence[PlayerObservation],
    *,
    metric_name: str,
    use_recency_weights: bool,
) -> tuple[float, float]:
    weighted_minutes = 0.0
    weighted_raw_count = 0.0
    weighted_context_count = 0.0

    for index, observation in enumerate(observations):
        weight = _recency_weight(index) if use_recency_weights else 1.0
        count = _event_count(observation, metric_name)

        weighted_minutes += weight * observation.minutes
        weighted_raw_count += weight * count
        weighted_context_count += weight * _context_adjusted_count(
            count,
            metric_name=metric_name,
            possession_pct=observation.possession_pct,
        )

    if weighted_minutes <= 0:
        return 0.0, 0.0

    factor = 90.0 / weighted_minutes
    return weighted_raw_count * factor, weighted_context_count * factor


def _event_count(observation: PlayerObservation, metric_name: str) -> float:
    """Return an event count for an observed appearance.

    API-Football commonly represents zero-event player counts as null. At this
    semantic analytics layer, documented event-count fields are therefore
    interpreted as zero when the player has a valid appearance/stat row.
    Unsupported fields such as accurate-pass counts and clearances are excluded
    from FEATURE_METRICS instead of being fabricated.
    """

    value = observation.stats.get(metric_name)
    return 0.0 if value is None else max(0.0, float(value))


def _context_adjusted_count(
    count: float,
    *,
    metric_name: str,
    possession_pct: float | None,
) -> float:
    if metric_name not in DEFENSIVE_CONTEXT_METRICS or possession_pct is None:
        return count
    if possession_pct < 0.0 or possession_pct > 100.0:
        return count

    opponent_possession_share = 1.0 - possession_pct / 100.0
    if opponent_possession_share <= 0.05:
        return count

    return count * (0.5 / opponent_possession_share)


def _recency_weight(index: int) -> float:
    return math.pow(0.5, index / _FORM_HALF_LIFE_APPEARANCES)


def _group_aggregates_by_role(
    aggregates: Iterable[_PlayerAggregate],
) -> dict[str, list[_PlayerAggregate]]:
    grouped: dict[str, list[_PlayerAggregate]] = defaultdict(list)
    for aggregate in aggregates:
        grouped[aggregate.role].append(aggregate)
    return dict(grouped)


def _build_role_features(
    population: Sequence[_PlayerAggregate],
) -> dict[int, dict[str, _FeatureValue]]:
    result: dict[int, dict[str, _FeatureValue]] = {
        aggregate.player_id: {} for aggregate in population
    }

    for metric_name in FEATURE_METRICS:
        baseline = _weighted_population_mean(
            population,
            metric_name=metric_name,
        )
        adjusted_by_player: dict[int, float] = {}

        for aggregate in population:
            context_rate = aggregate.context_rates[metric_name]
            reliability = aggregate.minutes / (aggregate.minutes + _PRIOR_MINUTES)
            adjusted_by_player[aggregate.player_id] = (
                reliability * context_rate + (1.0 - reliability) * baseline
            )

        sorted_values = sorted(adjusted_by_player.values())
        for aggregate in population:
            adjusted = adjusted_by_player[aggregate.player_id]
            result[aggregate.player_id][metric_name] = _FeatureValue(
                raw_rate=aggregate.raw_rates[metric_name],
                adjusted_rate=adjusted,
                percentile=_percentile(sorted_values, adjusted),
                sample_size=len(sorted_values),
            )

    return result


def _weighted_population_mean(
    population: Sequence[_PlayerAggregate],
    *,
    metric_name: str,
) -> float:
    denominator = sum(aggregate.minutes for aggregate in population)
    if denominator <= 0:
        return 0.0

    numerator = sum(
        aggregate.context_rates[metric_name] * aggregate.minutes for aggregate in population
    )
    return numerator / denominator


def _percentile(sorted_values: Sequence[float], value: float) -> float:
    if not sorted_values:
        return 50.0
    left = bisect_left(sorted_values, value)
    right = bisect_right(sorted_values, value)
    return 100.0 * (left + 0.5 * (right - left)) / len(sorted_values)


def _score_player(
    aggregate: _PlayerAggregate,
    features: dict[str, _FeatureValue],
    *,
    population_size: int,
) -> tuple[float, float, dict[str, float]]:
    weights = ROLE_SCORE_WEIGHTS[aggregate.role]
    weighted_score = 0.0
    weight_sum = 0.0

    for metric_name, weight, direction in weights:
        feature = features.get(metric_name)
        if feature is None:
            continue
        percentile = feature.percentile if direction > 0 else 100.0 - feature.percentile
        weighted_score += weight * percentile
        weight_sum += weight

    overall_score = weighted_score / weight_sum if weight_sum else 50.0
    metric_coverage = min(1.0, weight_sum / sum(weight for _, weight, _ in weights))
    minute_confidence = 1.0 - math.exp(-aggregate.minutes / _PRIOR_MINUTES)
    population_confidence = min(1.0, population_size / 20.0)
    role_cap = _GOALKEEPER_CONFIDENCE_CAP if aggregate.role == "goalkeeper" else 1.0
    confidence = (
        role_cap
        * minute_confidence
        * (0.75 + 0.25 * aggregate.role_confidence)
        * (0.75 + 0.25 * metric_coverage)
        * (0.75 + 0.25 * population_confidence)
    )

    dimensions: dict[str, float] = {}
    for dimension_name in ROLE_DIMENSIONS[aggregate.role]:
        metric_specs = DIMENSION_METRICS[dimension_name]
        values: list[float] = []
        for metric_name, direction in metric_specs:
            feature = features.get(metric_name)
            if feature is None:
                continue
            values.append(feature.percentile if direction > 0 else 100.0 - feature.percentile)
        if values:
            dimensions[dimension_name] = sum(values) / len(values)

    return overall_score, min(1.0, confidence), dimensions
