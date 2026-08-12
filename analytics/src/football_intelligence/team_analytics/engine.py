"""Competition-relative team scoring and deterministic Elo history."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from football_intelligence.team_analytics.config import (
    ATTACK_WEIGHTS,
    CHANCE_GENERATION_WEIGHTS,
    CONTROL_WEIGHTS,
    DEFENSIVE_PROCESS_WEIGHTS,
    ELO_HOME_ADVANTAGE,
    ELO_INITIAL_RATING,
    ELO_K_FACTOR,
    FINISHING_PRIOR_SHOTS,
    FINISHING_PRIOR_SHOTS_ON_TARGET,
    FINISHING_WEIGHTS,
    FORM_HALF_LIFE_MATCHES,
    LOWER_IS_BETTER,
    OVERALL_WEIGHTS,
    PROCESS_COVERAGE_METRICS,
    PROCESS_WEIGHTS,
    RESULTS_WEIGHTS,
    WINDOWS,
)
from football_intelligence.team_analytics.models import (
    TeamAnalyticsResult,
    TeamEloHistory,
    TeamFeature,
    TeamObservation,
    TeamScore,
)

MODEL_VERSION = "team-v1.0"


@dataclass(frozen=True, slots=True)
class _Aggregate:
    team_id: int
    team_name: str
    matches: int
    raw_values: Mapping[str, float]
    observed_matches: Mapping[str, int]
    ratio_parts: Mapping[str, tuple[float, float]]


@dataclass(frozen=True, slots=True)
class _FeatureValue:
    raw_value: float
    adjusted_value: float
    percentile: float
    observed_matches: int
    sample_size: int


def calculate_team_analytics(
    observations: Sequence[TeamObservation],
    *,
    scope_key: str,
    competition_id: int,
    season_id: int,
    calculated_at: datetime | None = None,
) -> TeamAnalyticsResult:
    """Calculate one competition/season scope without cross-league comparison."""

    if not scope_key.strip():
        raise ValueError("scope_key must not be blank")
    scoped = [
        item
        for item in observations
        if item.competition_id == competition_id and item.season_id == season_id
    ]
    if len(scoped) != len(observations):
        raise ValueError("observations must belong to one competition and season")

    effective_at = calculated_at or datetime.now(UTC)
    elo_history = calculate_elo_history(scoped, calculated_at=effective_at)
    grouped = _group_observations(scoped)
    current_elo, elo_change = _elo_summaries(elo_history)
    features: list[TeamFeature] = []
    scores: list[TeamScore] = []

    for window_name, match_limit in WINDOWS:
        aggregates = _aggregate_window(grouped, window_name=window_name, match_limit=match_limit)
        feature_map = _build_features(aggregates)

        for aggregate in aggregates:
            team_features = feature_map[aggregate.team_id]
            for metric_name, value in team_features.items():
                features.append(
                    TeamFeature(
                        team_id=aggregate.team_id,
                        competition_id=competition_id,
                        season_id=season_id,
                        scope_key=scope_key,
                        window=window_name,
                        metric_name=metric_name,
                        matches=aggregate.matches,
                        observed_matches=value.observed_matches,
                        raw_value=round(value.raw_value, 4),
                        adjusted_value=round(value.adjusted_value, 4),
                        percentile=round(value.percentile, 2),
                        reference_sample_size=value.sample_size,
                        model_version=MODEL_VERSION,
                        calculated_at=effective_at,
                    )
                )

            score = _score_team(aggregate, team_features, population_size=len(aggregates))
            if score is None:
                continue
            dimensions, confidence, delta, signal, diagnostics = score
            scores.append(
                TeamScore(
                    team_id=aggregate.team_id,
                    team_name=aggregate.team_name,
                    competition_id=competition_id,
                    season_id=season_id,
                    scope_key=scope_key,
                    window=window_name,
                    matches=aggregate.matches,
                    overall_score=round(dimensions["overall"], 2),
                    confidence=round(confidence, 5),
                    dimension_scores={
                        name: round(value, 2)
                        for name, value in dimensions.items()
                        if name != "overall"
                    },
                    results_process_delta=round(delta, 2),
                    results_process_signal=signal,
                    diagnostics=diagnostics,
                    reference_sample_size=len(aggregates),
                    current_elo=round(current_elo.get(aggregate.team_id, ELO_INITIAL_RATING), 2),
                    elo_change_last_5=round(elo_change.get(aggregate.team_id, 0.0), 2),
                    model_version=MODEL_VERSION,
                    calculated_at=effective_at,
                )
            )

    return TeamAnalyticsResult(
        features=tuple(features),
        scores=tuple(scores),
        elo_history=tuple(elo_history),
    )


def calculate_elo_history(
    observations: Sequence[TeamObservation],
    *,
    calculated_at: datetime | None = None,
) -> list[TeamEloHistory]:
    """Calculate Elo independently for every competition/season context."""

    effective_at = calculated_at or datetime.now(UTC)
    by_context: dict[tuple[int, int], list[TeamObservation]] = defaultdict(list)
    for observation in observations:
        by_context[(observation.competition_id, observation.season_id)].append(observation)

    result: list[TeamEloHistory] = []
    for context in sorted(by_context):
        result.extend(_calculate_context_elo(by_context[context], calculated_at=effective_at))
    return result


def _calculate_context_elo(
    observations: Sequence[TeamObservation],
    *,
    calculated_at: datetime,
) -> list[TeamEloHistory]:
    by_match: dict[int, list[TeamObservation]] = defaultdict(list)
    for observation in observations:
        by_match[observation.match_id].append(observation)

    matches: list[tuple[TeamObservation, TeamObservation]] = []
    for pair in by_match.values():
        if len(pair) != 2:
            continue
        home = next((item for item in pair if item.is_home), None)
        away = next((item for item in pair if not item.is_home), None)
        if home is not None and away is not None:
            matches.append((home, away))
    matches.sort(key=lambda pair: (pair[0].kickoff_at, pair[0].match_id))

    ratings: dict[int, float] = defaultdict(lambda: ELO_INITIAL_RATING)
    history: list[TeamEloHistory] = []
    for home, away in matches:
        home_pre = ratings[home.team_id]
        away_pre = ratings[away.team_id]
        home_expected = 1.0 / (
            1.0 + math.pow(10.0, (away_pre - (home_pre + ELO_HOME_ADVANTAGE)) / 400.0)
        )
        if home.goals_for > away.goals_for:
            home_actual = 1.0
        elif home.goals_for < away.goals_for:
            home_actual = 0.0
        else:
            home_actual = 0.5
        away_expected = 1.0 - home_expected
        away_actual = 1.0 - home_actual
        home_post = home_pre + ELO_K_FACTOR * (home_actual - home_expected)
        away_post = away_pre + ELO_K_FACTOR * (away_actual - away_expected)
        ratings[home.team_id] = home_post
        ratings[away.team_id] = away_post

        for team, opponent, pre, opponent_pre, expected, actual, post in (
            (home, away, home_pre, away_pre, home_expected, home_actual, home_post),
            (away, home, away_pre, home_pre, away_expected, away_actual, away_post),
        ):
            history.append(
                TeamEloHistory(
                    match_id=team.match_id,
                    team_id=team.team_id,
                    opponent_team_id=opponent.team_id,
                    competition_id=team.competition_id,
                    season_id=team.season_id,
                    kickoff_at=team.kickoff_at,
                    pre_match_rating=round(pre, 4),
                    opponent_pre_match_rating=round(opponent_pre, 4),
                    expected_result=round(expected, 6),
                    actual_result=actual,
                    post_match_rating=round(post, 4),
                    model_version=MODEL_VERSION,
                    calculated_at=calculated_at,
                )
            )
    return history


def _group_observations(
    observations: Sequence[TeamObservation],
) -> dict[int, list[TeamObservation]]:
    grouped: dict[int, list[TeamObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.team_id].append(observation)
    for values in grouped.values():
        values.sort(key=lambda item: (item.kickoff_at, item.match_id), reverse=True)
    return dict(grouped)


def _aggregate_window(
    grouped: Mapping[int, list[TeamObservation]],
    *,
    window_name: str,
    match_limit: int | None,
) -> list[_Aggregate]:
    aggregates: list[_Aggregate] = []
    for team_observations in grouped.values():
        selected = team_observations if match_limit is None else team_observations[:match_limit]
        if not selected:
            continue
        weighted_values: dict[str, float] = defaultdict(float)
        weighted_denominators: dict[str, float] = defaultdict(float)
        observed: dict[str, int] = defaultdict(int)
        ratio_parts: dict[str, tuple[float, float]] = {}

        ratio_accumulators = {
            "goals_per_shot": [0.0, 0.0],
            "goals_per_shot_on_target": [0.0, 0.0],
        }
        for index, observation in enumerate(selected):
            weight = _recency_weight(index) if window_name != "season" else 1.0
            values = _observation_values(observation)
            for metric_name, value in values.items():
                if value is None:
                    continue
                weighted_values[metric_name] += weight * value
                weighted_denominators[metric_name] += weight
                observed[metric_name] += 1

            for ratio_name, denominator_name in (
                ("goals_per_shot", "shots_total_for"),
                ("goals_per_shot_on_target", "shots_on_target_for"),
            ):
                denominator = values[denominator_name]
                if denominator is None:
                    continue
                ratio_accumulators[ratio_name][0] += weight * observation.goals_for
                ratio_accumulators[ratio_name][1] += weight * denominator
                observed[ratio_name] += 1

        raw_values = {
            name: numerator / weighted_denominators[name]
            for name, numerator in weighted_values.items()
            if weighted_denominators[name] > 0
        }
        for ratio_name, (numerator, denominator) in ratio_accumulators.items():
            if denominator > 0:
                raw_values[ratio_name] = numerator / denominator
                ratio_parts[ratio_name] = (numerator, denominator)

        aggregates.append(
            _Aggregate(
                team_id=selected[0].team_id,
                team_name=selected[0].team_name,
                matches=len(selected),
                raw_values=raw_values,
                observed_matches=dict(observed),
                ratio_parts=ratio_parts,
            )
        )
    return aggregates


def _observation_values(observation: TeamObservation) -> dict[str, float | None]:
    shots_total = observation.stats.get("shots_total_for")
    shots_on_target = observation.stats.get("shots_on_target_for")
    passes_total = observation.stats.get("passes_total")
    passes_accurate = observation.stats.get("passes_accurate")
    opponent_passes = observation.stats.get("opponent_passes_total")
    pass_accuracy = (
        100.0 * passes_accurate / passes_total
        if passes_accurate is not None and passes_total is not None and passes_total > 0
        else None
    )
    combined_passes = (
        passes_total + opponent_passes
        if passes_total is not None and opponent_passes is not None
        else None
    )
    pass_share = (
        100.0 * passes_total / combined_passes
        if passes_total is not None and combined_passes is not None and combined_passes > 0
        else None
    )
    return {
        "goals_for": float(observation.goals_for),
        "goals_against": float(observation.goals_against),
        "goal_difference_per_match": float(observation.goals_for - observation.goals_against),
        "points_per_match": float(_points(observation.goals_for, observation.goals_against)),
        "shots_total_for": shots_total,
        "shots_on_target_for": shots_on_target,
        "shots_inside_box_for": observation.stats.get("shots_inside_box_for"),
        "corners_for": observation.stats.get("corners_for"),
        "shots_total_against": observation.stats.get("shots_total_against"),
        "shots_on_target_against": observation.stats.get("shots_on_target_against"),
        "shots_inside_box_against": observation.stats.get("shots_inside_box_against"),
        "possession_pct": observation.stats.get("possession_pct"),
        "pass_accuracy_pct": pass_accuracy,
        "pass_share": pass_share,
    }


def _points(goals_for: int, goals_against: int) -> int:
    if goals_for > goals_against:
        return 3
    if goals_for == goals_against:
        return 1
    return 0


def _recency_weight(index: int) -> float:
    return math.pow(0.5, index / FORM_HALF_LIFE_MATCHES)


def _build_features(
    aggregates: Sequence[_Aggregate],
) -> dict[int, dict[str, _FeatureValue]]:
    result: dict[int, dict[str, _FeatureValue]] = {
        aggregate.team_id: {} for aggregate in aggregates
    }
    metric_names = sorted({name for item in aggregates for name in item.raw_values})

    for metric_name in metric_names:
        adjusted: dict[int, float] = {}
        if metric_name in {"goals_per_shot", "goals_per_shot_on_target"}:
            population_numerator = sum(
                item.ratio_parts.get(metric_name, (0.0, 0.0))[0] for item in aggregates
            )
            population_denominator = sum(
                item.ratio_parts.get(metric_name, (0.0, 0.0))[1] for item in aggregates
            )
            population_mean = (
                population_numerator / population_denominator if population_denominator > 0 else 0.0
            )
            prior = (
                FINISHING_PRIOR_SHOTS
                if metric_name == "goals_per_shot"
                else FINISHING_PRIOR_SHOTS_ON_TARGET
            )
            for item in aggregates:
                parts = item.ratio_parts.get(metric_name)
                if parts is not None:
                    adjusted[item.team_id] = (parts[0] + prior * population_mean) / (
                        parts[1] + prior
                    )
        else:
            adjusted = {
                item.team_id: item.raw_values[metric_name]
                for item in aggregates
                if metric_name in item.raw_values
            }

        sorted_values = sorted(adjusted.values())
        for item in aggregates:
            if item.team_id not in adjusted:
                continue
            value = adjusted[item.team_id]
            percentile = _percentile(sorted_values, value)
            if metric_name in LOWER_IS_BETTER:
                percentile = 100.0 - percentile
            result[item.team_id][metric_name] = _FeatureValue(
                raw_value=item.raw_values[metric_name],
                adjusted_value=value,
                percentile=percentile,
                observed_matches=item.observed_matches[metric_name],
                sample_size=len(sorted_values),
            )
    return result


def _percentile(sorted_values: Sequence[float], value: float) -> float:
    if not sorted_values:
        return 50.0
    left = bisect_left(sorted_values, value)
    right = bisect_right(sorted_values, value)
    return 100.0 * (left + 0.5 * (right - left)) / len(sorted_values)


def _weighted_score(
    values: Mapping[str, float],
    weights: Mapping[str, float],
) -> float | None:
    available = [(values[name], weight) for name, weight in weights.items() if name in values]
    weight_sum = sum(weight for _, weight in available)
    if weight_sum <= 0:
        return None
    return sum(value * weight for value, weight in available) / weight_sum


def _score_team(
    aggregate: _Aggregate,
    features: Mapping[str, _FeatureValue],
    *,
    population_size: int,
) -> tuple[dict[str, float], float, float, str, dict[str, Any]] | None:
    percentiles = {name: value.percentile for name, value in features.items()}
    chance = _weighted_score(percentiles, CHANCE_GENERATION_WEIGHTS)
    defense = _weighted_score(percentiles, DEFENSIVE_PROCESS_WEIGHTS)
    control = _weighted_score(percentiles, CONTROL_WEIGHTS)
    finishing = _weighted_score(percentiles, FINISHING_WEIGHTS)
    results = _weighted_score(percentiles, RESULTS_WEIGHTS)

    base_dimensions = {
        name: value
        for name, value in {
            "chance_generation": chance,
            "defense": defense,
            "control": control,
            "finishing_proxy": finishing,
        }.items()
        if value is not None
    }
    process = _weighted_score(base_dimensions, PROCESS_WEIGHTS)
    attack = _weighted_score(base_dimensions, ATTACK_WEIGHTS)
    if process is None or results is None:
        return None
    overall = _weighted_score({"process": process, "results": results}, OVERALL_WEIGHTS)
    if overall is None:
        return None

    dimensions = dict(base_dimensions)
    if attack is not None:
        dimensions["attack"] = attack
    dimensions["process"] = process
    dimensions["results"] = results
    dimensions["overall"] = overall

    coverage = sum(
        aggregate.observed_matches.get(metric_name, 0) / aggregate.matches
        for metric_name in PROCESS_COVERAGE_METRICS
    ) / len(PROCESS_COVERAGE_METRICS)
    match_confidence = 1.0 - math.exp(-aggregate.matches / 5.0)
    population_confidence = min(1.0, population_size / 12.0)
    confidence = match_confidence * (0.55 + 0.45 * coverage) * (0.75 + 0.25 * population_confidence)

    delta = results - process
    if delta >= 12.0:
        signal = "results_above_process"
    elif delta <= -12.0:
        signal = "results_below_process"
    else:
        signal = "results_aligned"

    diagnostic_signals: list[str] = []
    if chance is not None and finishing is not None:
        if chance >= 65.0 and finishing <= 35.0:
            diagnostic_signals.append("finishing_issue")
        elif chance <= 35.0 and finishing >= 45.0:
            diagnostic_signals.append("creation_issue")
    if defense is not None and defense <= 35.0:
        diagnostic_signals.append("defensive_process_issue")
    if signal != "results_aligned":
        diagnostic_signals.append(signal)

    diagnostics: dict[str, Any] = {
        "signals": diagnostic_signals,
        "metric_coverage": round(coverage, 4),
    }
    return dimensions, min(1.0, confidence), delta, signal, diagnostics


def _elo_summaries(
    history: Sequence[TeamEloHistory],
) -> tuple[dict[int, float], dict[int, float]]:
    grouped: dict[int, list[TeamEloHistory]] = defaultdict(list)
    for item in history:
        grouped[item.team_id].append(item)
    current: dict[int, float] = {}
    change: dict[int, float] = {}
    for team_id, items in grouped.items():
        items.sort(key=lambda item: (item.kickoff_at, item.match_id))
        recent = items[-5:]
        current[team_id] = items[-1].post_match_rating
        change[team_id] = items[-1].post_match_rating - recent[0].pre_match_rating
    return current, change
