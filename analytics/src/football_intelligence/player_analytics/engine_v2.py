"""Catalog-driven, evidence-aware Player Statistical Engine V2.

V1 remains untouched. V2 consumes any numeric player/goalkeeper catalog
metric present in ``PlayerObservation.stats`` and publishes missing ideal
profile inputs as evidence gaps rather than silently shrinking the product.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from math import isclose
from typing import Literal, Protocol

from football_intelligence.metric_catalog import METRIC_CATALOG_V2
from football_intelligence.player_analytics.config import ROLE_ALIASES, WINDOWS
from football_intelligence.player_analytics.models import PlayerObservation
from football_intelligence.player_analytics.profiles_v2 import (
    DIMENSION_PROFILES,
    MIN_DIMENSION_EVIDENCE_COVERAGE,
    POSITION_DIMENSION_WEIGHTS,
    PROFILE_VERSION,
    MetricWeight,
)
from football_intelligence.position_profiles import classify_position_family
from football_intelligence.statistical_engine import derive_available_metrics

MODEL_VERSION = "player-v2.0"
MIN_RANKING_CONFIDENCE = 0.40
MIN_FINISHING_RESIDUAL = 2.0

EvidenceState = Literal["ready", "partial", "insufficient_data"]
ResultsVsProcessSignal = str

_FAMILY_TO_ROLE = {
    "goalkeeper": "goalkeeper",
    "centre_back": "defender",
    "fullback_wingback": "defender",
    "defensive_midfielder": "midfielder",
    "central_midfielder": "midfielder",
    "attacking_midfielder": "midfielder",
    "winger": "midfielder",
    "forward": "forward",
    "defender": "defender",
    "midfielder": "midfielder",
}
_PLAYER_CATALOG = {
    metric.key: metric
    for metric in METRIC_CATALOG_V2
    if metric.granularity in {"player_match", "player_season"}
}
_GOALKEEPER_CATALOG = {
    metric.key: metric
    for metric in METRIC_CATALOG_V2
    if metric.granularity in {"goalkeeper_match", "goalkeeper_season"}
}


class _PercentileFeature(Protocol):
    @property
    def percentile(self) -> float | None: ...


@dataclass(frozen=True, slots=True)
class PlayerFeatureV2:
    player_id: int
    player_name: str
    scope_key: str
    window: str
    role: str
    position_family: str | None
    metric_name: str
    minutes: int
    appearances: int
    raw_value: float
    per90_value: float | None
    adjusted_value: float
    value_basis: str
    metric_kind: str
    metric_unit: str
    formula_version: str | None
    percentile: float | None
    comparison_group: str
    reference_sample_size: int
    model_version: str
    calculated_at: datetime

    @property
    def raw_per90(self) -> float:
        return self.per90_value if self.per90_value is not None else self.raw_value

    @property
    def adjusted_per90(self) -> float:
        return self.adjusted_value


@dataclass(frozen=True, slots=True)
class WeightedScoreEvidence:
    score: float | None
    evidence_weight_available: float
    evidence_weight_required: float
    evidence_coverage_pct: float
    evidence_state: EvidenceState
    evidence_metrics_expected: tuple[str, ...]
    evidence_core_metrics: tuple[str, ...]
    evidence_metrics_available: tuple[str, ...]
    evidence_metrics_missing: tuple[str, ...]

    @property
    def evidence_metrics_required(self) -> tuple[str, ...]:
        return self.evidence_metrics_expected


@dataclass(frozen=True, slots=True)
class PlayerScoreV2:
    player_id: int
    player_name: str
    scope_key: str
    window: str
    role: str
    position_family: str | None
    role_confidence: float
    minutes: int
    appearances: int
    overall_score: float | None
    confidence: float
    evidence_weight_available: float
    evidence_weight_required: float
    evidence_coverage_pct: float
    evidence_state: EvidenceState
    evidence_metrics_expected: tuple[str, ...]
    evidence_core_metrics: tuple[str, ...]
    evidence_metrics_available: tuple[str, ...]
    evidence_metrics_missing: tuple[str, ...]
    dimension_scores: Mapping[str, float]
    dimension_evidence: Mapping[str, WeightedScoreEvidence]
    reference_sample_size: int
    model_version: str
    profile_version: str
    calculated_at: datetime

    @property
    def evidence_metrics_required(self) -> tuple[str, ...]:
        return self.evidence_metrics_expected


@dataclass(frozen=True, slots=True)
class PlayerAnalyticsResultV2:
    features: tuple[PlayerFeatureV2, ...]
    scores: tuple[PlayerScoreV2, ...]


def calculate_player_analytics_v2_result(
    observations: Sequence[PlayerObservation],
    *,
    scope_key: str,
    calculated_at: datetime | None = None,
) -> PlayerAnalyticsResultV2:
    if not scope_key.strip():
        raise ValueError("scope_key must not be blank")
    effective_at = calculated_at or datetime.now(UTC)
    families = _primary_position_family(observations)
    roles = _primary_role(observations, families)
    grouped: dict[int, list[PlayerObservation]] = defaultdict(list)
    for observation in observations:
        if observation.minutes > 0 and observation.player_id in roles:
            grouped[observation.player_id].append(observation)

    features: list[PlayerFeatureV2] = []
    player_windows: dict[tuple[int, str], tuple[list[PlayerObservation], int]] = {}
    for player_id, player_observations in grouped.items():
        ordered = sorted(player_observations, key=lambda item: item.kickoff_at, reverse=True)
        for window, limit in WINDOWS:
            selected = ordered if limit is None else ordered[:limit]
            if not selected:
                continue
            player_windows[(player_id, window)] = (selected, sum(item.minutes for item in selected))
            features.extend(
                _build_window_features(
                    selected,
                    scope_key=scope_key,
                    window=window,
                    role=roles[player_id],
                    position_family=families.get(player_id),
                    calculated_at=effective_at,
                )
            )

    percentiled = _assign_percentiles(features)
    feature_maps: dict[tuple[int, str], dict[str, PlayerFeatureV2]] = defaultdict(dict)
    for feature in percentiled:
        feature_maps[(feature.player_id, feature.window)][feature.metric_name] = feature

    scores: list[PlayerScoreV2] = []
    names = {item.player_id: item.player_name for item in observations}
    for (player_id, window), (selected, minutes) in player_windows.items():
        feature_map = feature_maps[(player_id, window)]
        dimensions = {
            name: _score_metric_profile(feature_map, profile)
            for name, profile in DIMENSION_PROFILES.items()
        }
        dimension_scores = {
            name: evidence.score
            for name, evidence in dimensions.items()
            if evidence.score is not None
        }
        family = families.get(player_id)
        overall = _compose_overall(dimensions, family)
        reference_size = max(
            (item.reference_sample_size for item in feature_map.values()), default=1
        )
        confidence = (
            min(len(selected) / 10.0, 1.0)
            * min(reference_size / 10.0, 1.0)
            * overall.evidence_coverage_pct
            / 100.0
        )
        scores.append(
            PlayerScoreV2(
                player_id=player_id,
                player_name=names[player_id],
                scope_key=scope_key,
                window=window,
                role=roles[player_id],
                position_family=family,
                role_confidence=_role_confidence(selected, family),
                minutes=minutes,
                appearances=len(selected),
                overall_score=None if overall.score is None else round(overall.score, 2),
                confidence=round(confidence, 5),
                evidence_weight_available=overall.evidence_weight_available,
                evidence_weight_required=overall.evidence_weight_required,
                evidence_coverage_pct=overall.evidence_coverage_pct,
                evidence_state=overall.evidence_state,
                evidence_metrics_expected=overall.evidence_metrics_expected,
                evidence_core_metrics=overall.evidence_core_metrics,
                evidence_metrics_available=overall.evidence_metrics_available,
                evidence_metrics_missing=overall.evidence_metrics_missing,
                dimension_scores=dimension_scores,
                dimension_evidence=dimensions,
                reference_sample_size=reference_size,
                model_version=MODEL_VERSION,
                profile_version=PROFILE_VERSION,
                calculated_at=effective_at,
            )
        )
    return PlayerAnalyticsResultV2(tuple(percentiled), tuple(scores))


def calculate_player_analytics_v2(
    observations: Sequence[PlayerObservation],
    *,
    scope_key: str,
    calculated_at: datetime | None = None,
) -> tuple[PlayerScoreV2, ...]:
    return calculate_player_analytics_v2_result(
        observations, scope_key=scope_key, calculated_at=calculated_at
    ).scores


def _build_window_features(
    observations: Sequence[PlayerObservation],
    *,
    scope_key: str,
    window: str,
    role: str,
    position_family: str | None,
    calculated_at: datetime,
) -> list[PlayerFeatureV2]:
    catalog = dict(_PLAYER_CATALOG)
    if role == "goalkeeper":
        catalog.update(_GOALKEEPER_CATALOG)
    samples: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        for raw_name, raw_value in observation.stats.items():
            metric_name = "advanced.xg" if raw_name == "xg" else raw_name
            if raw_value is not None and metric_name in catalog:
                samples[metric_name].append(float(raw_value))
    totals: dict[str, float] = {}
    for metric_name, values in samples.items():
        definition = catalog[metric_name]
        totals[metric_name] = (
            sum(values)
            if definition.per90_eligible or definition.unit in {"count", "minutes"}
            else sum(values) / len(values)
        )
    totals.update(
        appearances=float(len(observations)),
        matches=float(len(observations)),
        minutes=float(sum(item.minutes for item in observations)),
    )
    observed_counts = {name: len(values) for name, values in samples.items()}
    observed_counts.update(
        appearances=len(observations), matches=len(observations), minutes=len(observations)
    )
    derived, versions = derive_available_metrics(
        totals,
        observed_counts=observed_counts,
        required_observations=len(observations),
    )
    minutes = int(totals["minutes"])
    first = observations[0]
    result: list[PlayerFeatureV2] = []
    for metric_name, raw_value in derived.items():
        catalog_definition = catalog.get(metric_name)
        if catalog_definition is None or metric_name == "minutes":
            continue
        per90 = (
            raw_value * 90.0 / minutes if catalog_definition.per90_eligible and minutes else None
        )
        adjusted = per90 if per90 is not None else raw_value
        result.append(
            PlayerFeatureV2(
                player_id=first.player_id,
                player_name=first.player_name,
                scope_key=scope_key,
                window=window,
                role=role,
                position_family=position_family,
                metric_name=metric_name,
                minutes=minutes,
                appearances=len(observations),
                raw_value=round(raw_value, 6),
                per90_value=None if per90 is None else round(per90, 6),
                adjusted_value=round(adjusted, 6),
                value_basis="per90"
                if per90 is not None
                else ("derived_rate" if metric_name in versions else "raw_rate"),
                metric_kind="derived" if metric_name in versions else catalog_definition.kind,
                metric_unit=catalog_definition.unit,
                formula_version=versions.get(metric_name),
                percentile=None,
                comparison_group=f"{scope_key}:{window}:{position_family or role}",
                reference_sample_size=1,
                model_version=MODEL_VERSION,
                calculated_at=calculated_at,
            )
        )
    return result


def _assign_percentiles(features: Sequence[PlayerFeatureV2]) -> list[PlayerFeatureV2]:
    groups: dict[tuple[str, str], list[PlayerFeatureV2]] = defaultdict(list)
    result: list[PlayerFeatureV2] = []
    for feature in features:
        definition = _PLAYER_CATALOG.get(feature.metric_name) or _GOALKEEPER_CATALOG.get(
            feature.metric_name
        )
        if definition is not None and definition.percentile_eligible:
            groups[(feature.comparison_group, feature.metric_name)].append(feature)
        else:
            result.append(feature)
    for group in groups.values():
        ordered = sorted(group, key=lambda item: item.adjusted_value)
        size = len(ordered)
        for item in ordered:
            ranks = [
                index
                for index, candidate in enumerate(ordered)
                if candidate.adjusted_value == item.adjusted_value
            ]
            percentile = (
                50.0
                if size == 1
                else sum(index / (size - 1) * 100.0 for index in ranks) / len(ranks)
            )
            result.append(
                replace(item, percentile=round(percentile, 2), reference_sample_size=size)
            )
    return sorted(result, key=lambda item: (item.player_id, item.window, item.metric_name))


def _score_metric_profile(
    feature_map: Mapping[str, PlayerFeatureV2], profile: tuple[MetricWeight, ...]
) -> WeightedScoreEvidence:
    return _weighted_percentile_score(
        feature_map,
        tuple((item.metric_name, item.weight, item.direction) for item in profile),
        core_metrics=frozenset(item.metric_name for item in profile if item.core),
    )


def _weighted_percentile_score[FeatureT: _PercentileFeature](
    feature_map: Mapping[str, FeatureT],
    weights: tuple[tuple[str, float, int], ...],
    *,
    core_metrics: frozenset[str] = frozenset(),
) -> WeightedScoreEvidence:
    expected = tuple(metric for metric, _, _ in weights)
    required_weight = sum(weight for _, weight, _ in weights)
    available: list[str] = []
    weighted = available_weight = 0.0
    for metric, weight, direction in weights:
        feature = feature_map.get(metric)
        if feature is None or feature.percentile is None:
            continue
        weighted += weight * (feature.percentile if direction > 0 else 100.0 - feature.percentile)
        available_weight += weight
        available.append(metric)
    coverage = available_weight / required_weight if required_weight else 0.0
    missing = tuple(metric for metric in expected if metric not in available)
    if not available or core_metrics - set(available) or coverage < MIN_DIMENSION_EVIDENCE_COVERAGE:
        state: EvidenceState = "insufficient_data"
    elif not isclose(coverage, 1.0):
        state = "partial"
    else:
        state = "ready"
    return WeightedScoreEvidence(
        score=weighted / required_weight if state == "ready" else None,
        evidence_weight_available=round(available_weight, 6),
        evidence_weight_required=round(required_weight, 6),
        evidence_coverage_pct=round(coverage * 100.0, 2),
        evidence_state=state,
        evidence_metrics_expected=expected,
        evidence_core_metrics=tuple(sorted(core_metrics)),
        evidence_metrics_available=tuple(available),
        evidence_metrics_missing=missing,
    )


def _compose_overall(
    dimensions: Mapping[str, WeightedScoreEvidence], family: str | None
) -> WeightedScoreEvidence:
    profile = POSITION_DIMENSION_WEIGHTS.get(family or "")
    if not profile:
        return WeightedScoreEvidence(None, 0.0, 0.0, 0.0, "insufficient_data", (), (), (), ())
    expected_metrics: set[str] = set()
    core_metrics: set[str] = set()
    available_metrics: set[str] = set()
    available_weight = weighted_score = 0.0
    for name, weight in profile:
        evidence = dimensions[name]
        expected_metrics.update(evidence.evidence_metrics_expected)
        core_metrics.update(evidence.evidence_core_metrics)
        available_metrics.update(evidence.evidence_metrics_available)
        available_weight += weight * evidence.evidence_coverage_pct / 100.0
        if evidence.score is not None:
            weighted_score += weight * evidence.score
    required_weight = sum(weight for _, weight in profile)
    all_ready = all(dimensions[name].evidence_state == "ready" for name, _ in profile)
    state: EvidenceState = (
        "ready" if all_ready else ("partial" if available_metrics else "insufficient_data")
    )
    expected = tuple(sorted(expected_metrics))
    available = tuple(sorted(available_metrics))
    return WeightedScoreEvidence(
        score=weighted_score / required_weight if all_ready else None,
        evidence_weight_available=round(available_weight, 6),
        evidence_weight_required=round(required_weight, 6),
        evidence_coverage_pct=round(available_weight / required_weight * 100.0, 2),
        evidence_state=state,
        evidence_metrics_expected=expected,
        evidence_core_metrics=tuple(sorted(core_metrics)),
        evidence_metrics_available=available,
        evidence_metrics_missing=tuple(
            metric for metric in expected if metric not in available_metrics
        ),
    )


def _primary_position_family(observations: Sequence[PlayerObservation]) -> dict[int, str | None]:
    minutes: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for observation in observations:
        family = classify_position_family(observation.listed_position)
        if family is not None and observation.minutes > 0:
            minutes[observation.player_id][family] += observation.minutes
    return {
        player: max(values.items(), key=lambda item: item[1])[0]
        for player, values in minutes.items()
    }


def _primary_role(
    observations: Sequence[PlayerObservation], families: Mapping[int, str | None]
) -> dict[int, str]:
    result: dict[int, str] = {}
    for observation in observations:
        family = families.get(observation.player_id)
        role = _FAMILY_TO_ROLE.get(family or "")
        if role is None and observation.listed_position:
            role = ROLE_ALIASES.get(observation.listed_position.strip().upper())
        if role is not None:
            result[observation.player_id] = role
    return result


def _role_confidence(observations: Sequence[PlayerObservation], family: str | None) -> float:
    total = sum(item.minutes for item in observations)
    matching = sum(
        item.minutes
        for item in observations
        if classify_position_family(item.listed_position) == family
    )
    return round(matching / total, 5) if total else 0.0


def rank_by_confidence_gated_score(entries: Sequence[tuple[float, float, int]]) -> tuple[int, ...]:
    return tuple(
        sorted(
            range(len(entries)),
            key=lambda index: (
                entries[index][1] < MIN_RANKING_CONFIDENCE,
                -entries[index][0],
                -entries[index][1],
                -entries[index][2],
            ),
        )
    )


def classify_results_vs_process(
    *,
    raw_output: float,
    output_percentile: float | None,
    expected_output: float | None,
    expected_output_percentile: float | None,
    shot_generation_percentile: float | None = None,
    threshold: float = MIN_FINISHING_RESIDUAL,
    non_penalty_goals: float | None = None,
    npxg: float | None = None,
) -> ResultsVsProcessSignal:
    del output_percentile, expected_output_percentile, shot_generation_percentile
    actual = non_penalty_goals if non_penalty_goals is not None and npxg is not None else raw_output
    expected = npxg if non_penalty_goals is not None and npxg is not None else expected_output
    if expected is None:
        return "insufficient_data"
    delta = actual - expected
    if delta >= threshold:
        return "results_above_process"
    if delta <= -threshold:
        return "results_below_process"
    return "aligned"
