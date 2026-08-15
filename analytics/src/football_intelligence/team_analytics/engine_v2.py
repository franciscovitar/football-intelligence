"""Catalog-driven Team Statistical Engine V2 and legacy diagnostic adapters.

The independent V2 path consumes provider-independent team observations,
derives safe formulas, calculates comparison percentiles and exposes fourteen
evidence-aware dimensions. V1 remains untouched; its two established helper
adapters stay here for compatibility with Blocks 9-15.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal

from football_intelligence.metric_catalog import METRIC_CATALOG_V2
from football_intelligence.player_analytics.engine_v2 import (
    WeightedScoreEvidence,
    _weighted_percentile_score,
)
from football_intelligence.statistical_engine import derive_available_metrics
from football_intelligence.team_analytics.config import WINDOWS
from football_intelligence.team_analytics.models import TeamObservation, TeamScore
from football_intelligence.team_analytics.profiles_v2 import (
    PROFILE_VERSION,
    TEAM_DIMENSION_PROFILES,
    TEAM_OVERALL_WEIGHTS,
)

MODEL_VERSION = "team-v2.0"
EvidenceState = Literal["ready", "partial", "insufficient_data"]

_TEAM_CATALOG = {
    metric.key: metric for metric in METRIC_CATALOG_V2 if metric.granularity == "team_match"
}

# Mirrors the strong-threshold pattern engine.py's `_score_team` already uses
# for finishing_issue/creation_issue/defensive_process_issue: a percentile at
# or beyond these bounds is a real, deliberate signal, not measurement noise.
_HIGH_PERCENTILE_THRESHOLD = 65.0
_LOW_PERCENTILE_THRESHOLD = 35.0

# "few_but_high_quality_chances_allowed" | "high_volume_low_quality_allowed" | "insufficient_data"
ChanceQualityAllowedSignal = str


@dataclass(frozen=True, slots=True)
class TeamIssueSignal:
    team_id: int
    team_name: str
    scope_key: str
    window: str
    signal_code: str
    results_process_delta: float
    confidence: float
    supporting_metrics: Mapping[str, float | str | None]
    model_version: str
    calculated_at: datetime


@dataclass(frozen=True, slots=True)
class TeamFeatureV2:
    team_id: int
    team_name: str
    competition_id: int
    season_id: int
    scope_key: str
    window: str
    metric_name: str
    matches: int
    observed_matches: int
    raw_value: float
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


@dataclass(frozen=True, slots=True)
class TeamScoreV2:
    team_id: int
    team_name: str
    competition_id: int
    season_id: int
    scope_key: str
    window: str
    matches: int
    overall_score: float | None
    confidence: float
    evidence_state: EvidenceState
    evidence_coverage_pct: float
    dimension_scores: Mapping[str, float]
    dimension_evidence: Mapping[str, WeightedScoreEvidence]
    diagnostics: tuple[str, ...]
    reference_sample_size: int
    model_version: str
    profile_version: str
    calculated_at: datetime


@dataclass(frozen=True, slots=True)
class TeamAnalyticsResultV2:
    features: tuple[TeamFeatureV2, ...]
    scores: tuple[TeamScoreV2, ...]


def calculate_team_analytics_v2(
    observations: Sequence[TeamObservation],
    *,
    scope_key: str,
    calculated_at: datetime | None = None,
) -> TeamAnalyticsResultV2:
    """Calculate all catalog-backed Team V2 features and evidence dimensions."""
    if not scope_key.strip():
        raise ValueError("scope_key must not be blank")
    effective_at = calculated_at or datetime.now(UTC)
    grouped: dict[int, list[TeamObservation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.team_id].append(observation)
    features: list[TeamFeatureV2] = []
    windows: dict[tuple[int, str], list[TeamObservation]] = {}
    for team_id, team_observations in grouped.items():
        ordered = sorted(team_observations, key=lambda item: item.kickoff_at, reverse=True)
        for window, limit in WINDOWS:
            selected = ordered if limit is None else ordered[:limit]
            if selected:
                windows[(team_id, window)] = selected
                features.extend(
                    _team_window_features(
                        selected, scope_key=scope_key, window=window, calculated_at=effective_at
                    )
                )
    percentiled = _assign_team_percentiles(features)
    feature_maps: dict[tuple[int, str], dict[str, TeamFeatureV2]] = defaultdict(dict)
    for feature in percentiled:
        feature_maps[(feature.team_id, feature.window)][feature.metric_name] = feature
    scores: list[TeamScoreV2] = []
    for (team_id, window), selected in windows.items():
        feature_map = feature_maps[(team_id, window)]
        dimensions = {
            name: _weighted_percentile_score(
                feature_map,
                tuple((item.metric_name, item.weight, item.direction) for item in profile),
                core_metrics=frozenset(item.metric_name for item in profile if item.core),
            )
            for name, profile in TEAM_DIMENSION_PROFILES.items()
        }
        ready = {
            name: evidence.score
            for name, evidence in dimensions.items()
            if evidence.score is not None
        }
        supported_weight = sum(TEAM_OVERALL_WEIGHTS[name] for name in ready)
        coverage = sum(
            TEAM_OVERALL_WEIGHTS[name] * dimensions[name].evidence_coverage_pct / 100.0
            for name in TEAM_OVERALL_WEIGHTS
        )
        state: EvidenceState = (
            "ready"
            if len(ready) == len(TEAM_OVERALL_WEIGHTS)
            else ("partial" if supported_weight else "insufficient_data")
        )
        # Overall is never a renormalized recombination of whichever
        # dimensions happen to be ready (that would silently rescale a
        # partial subset up to look like a complete 0-100 score). It is only
        # ever populated once every one of the fourteen intended dimensions
        # individually reached "ready" -- mirrors
        # `player_analytics.engine_v2._compose_overall`'s `all_ready` gate.
        overall = (
            sum(TEAM_OVERALL_WEIGHTS[name] * value for name, value in ready.items())
            if state == "ready"
            else None
        )
        reference = max((item.reference_sample_size for item in feature_map.values()), default=1)
        first = selected[0]
        scores.append(
            TeamScoreV2(
                team_id=team_id,
                team_name=first.team_name,
                competition_id=first.competition_id,
                season_id=first.season_id,
                scope_key=scope_key,
                window=window,
                matches=len(selected),
                overall_score=None if overall is None else round(overall, 2),
                confidence=round(min(len(selected) / 10.0, 1.0) * coverage, 5),
                evidence_state=state,
                evidence_coverage_pct=round(coverage * 100.0, 2),
                dimension_scores=ready,
                dimension_evidence=dimensions,
                diagnostics=_team_v2_diagnostics(feature_map, dimensions),
                reference_sample_size=reference,
                model_version=MODEL_VERSION,
                profile_version=PROFILE_VERSION,
                calculated_at=effective_at,
            )
        )
    return TeamAnalyticsResultV2(tuple(percentiled), tuple(scores))


def _team_window_features(
    observations: Sequence[TeamObservation],
    *,
    scope_key: str,
    window: str,
    calculated_at: datetime,
) -> list[TeamFeatureV2]:
    aliases = {
        "shots_total_for": "shots_total",
        "shots_on_target_for": "shots_on_target",
        "shots_inside_box_for": "shots_inside_box",
        "corners_for": "corners",
        "shots_total_against": "shots_allowed",
        "shots_on_target_against": "shots_on_target_allowed",
    }
    samples: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        samples["goals_for"].append(float(observation.goals_for))
        samples["goals_against"].append(float(observation.goals_against))
        for raw_name, value in observation.stats.items():
            metric_name = aliases.get(raw_name, raw_name)
            if value is not None and metric_name in _TEAM_CATALOG:
                samples[metric_name].append(float(value))
    aggregate_values: dict[str, float] = {}
    formula_values: dict[str, float] = {}
    for name, values in samples.items():
        definition = _TEAM_CATALOG[name]
        additive = definition.per90_eligible or definition.unit in {"count", "minutes"}
        aggregate_values[name] = sum(values) if additive else sum(values) / len(values)
        # Deterministic ratios use aggregate event numerators/denominators.
        # Excluding their observed output lets complete formula inputs take
        # precedence over an average of per-match percentages.
        if definition.kind != "derived":
            formula_values[name] = sum(values) if additive else aggregate_values[name]
    observed_counts = {name: len(values) for name, values in samples.items()}
    derived, versions = derive_available_metrics(
        formula_values,
        team=True,
        observed_counts=observed_counts,
        required_observations=len(observations),
    )
    first = observations[0]
    result: list[TeamFeatureV2] = []
    feature_values = dict(aggregate_values)
    feature_values.update({name: derived[name] for name in versions})
    for name, raw_value in feature_values.items():
        output_definition = _TEAM_CATALOG.get(name)
        if output_definition is None:
            continue
        observed = len(observations) if name in versions else len(samples[name])
        adjusted = (
            raw_value / observed if output_definition.per90_eligible and observed else raw_value
        )
        result.append(
            TeamFeatureV2(
                team_id=first.team_id,
                team_name=first.team_name,
                competition_id=first.competition_id,
                season_id=first.season_id,
                scope_key=scope_key,
                window=window,
                metric_name=name,
                matches=len(observations),
                observed_matches=max(observed, 1),
                raw_value=round(raw_value, 6),
                adjusted_value=round(adjusted, 6),
                value_basis="per_match"
                if output_definition.per90_eligible
                else ("derived_rate" if name in versions else "observed_average"),
                metric_kind="derived" if name in versions else output_definition.kind,
                metric_unit=output_definition.unit,
                formula_version=versions.get(name),
                percentile=None,
                comparison_group=f"{scope_key}:{window}",
                reference_sample_size=1,
                model_version=MODEL_VERSION,
                calculated_at=calculated_at,
            )
        )
    return result


def _assign_team_percentiles(features: Sequence[TeamFeatureV2]) -> list[TeamFeatureV2]:
    groups: dict[tuple[str, str], list[TeamFeatureV2]] = defaultdict(list)
    result: list[TeamFeatureV2] = []
    for feature in features:
        definition = _TEAM_CATALOG[feature.metric_name]
        if definition.percentile_eligible:
            groups[(feature.comparison_group, feature.metric_name)].append(feature)
        else:
            result.append(feature)
    for group in groups.values():
        ordered = sorted(group, key=lambda item: item.adjusted_value)
        size = len(ordered)
        for item in ordered:
            ranks = [
                index
                for index, other in enumerate(ordered)
                if other.adjusted_value == item.adjusted_value
            ]
            percentile = (
                50.0
                if size == 1
                else sum(index / (size - 1) * 100.0 for index in ranks) / len(ranks)
            )
            result.append(
                replace(item, percentile=round(percentile, 2), reference_sample_size=size)
            )
    return sorted(result, key=lambda item: (item.team_id, item.window, item.metric_name))


def _team_v2_diagnostics(
    features: Mapping[str, TeamFeatureV2],
    dimensions: Mapping[str, WeightedScoreEvidence],
) -> tuple[str, ...]:
    """Emit only findings whose explicit V2 evidence is available."""
    findings: list[str] = []
    finishing = dimensions["finishing"].score
    creation = dimensions["creation"].score
    control = dimensions["control"].score
    penetration = dimensions["penetration"].score
    if finishing is not None and finishing <= _LOW_PERCENTILE_THRESHOLD:
        findings.append("finishing_problem")
    if creation is not None and creation <= _LOW_PERCENTILE_THRESHOLD:
        findings.append("creation_problem")
    if control is not None and penetration is not None and control >= 65 and penetration <= 35:
        findings.append("territorial_dominance_without_penetration")
    xg = features.get("xg")
    goals = features.get("goals_for")
    if xg and goals and xg.raw_value != 0:
        delta = goals.raw_value - xg.raw_value
        if delta >= 2:
            findings.append("results_above_process")
        elif delta <= -2:
            findings.append("results_below_process")
    return tuple(findings)


def extract_team_issue_signals(score: TeamScore) -> tuple[TeamIssueSignal, ...]:
    """Reshape `TeamScore.diagnostics["signals"]` into per-signal structures.

    Pure reshaping, no recomputation: every `TeamIssueSignal` reuses the
    exact `results_process_delta`, `confidence`, and dimension scores V1
    already calculated for this `TeamScore`. Returns one `TeamIssueSignal`
    per signal code present -- an empty tuple is a valid, correct result
    when V1 found no notable signal for this scope/window.
    """

    raw_signals = score.diagnostics.get("signals", ())
    supporting_metrics: dict[str, float | str | None] = {
        "overall_score": score.overall_score,
        "metric_coverage": _as_float_or_none(score.diagnostics.get("metric_coverage")),
        **{f"dimension_{name}": value for name, value in score.dimension_scores.items()},
    }

    return tuple(
        TeamIssueSignal(
            team_id=score.team_id,
            team_name=score.team_name,
            scope_key=score.scope_key,
            window=score.window,
            signal_code=code,
            results_process_delta=score.results_process_delta,
            confidence=score.confidence,
            supporting_metrics=supporting_metrics,
            model_version=score.model_version,
            calculated_at=score.calculated_at,
        )
        for code in raw_signals
    )


def classify_chance_quality_allowed(
    *,
    shots_total_against_percentile: float | None,
    shots_on_target_against_percentile: float | None = None,
    xga_percentile: float | None = None,
) -> ChanceQualityAllowedSignal:
    """Classify shot volume allowed vs shot quality allowed.

    Both inputs are expected on team_analytics's existing 0-100
    defense-percentile scale, where higher is always better (V1 already
    inverts opponent-volume percentiles before storing them, per
    `team_analytics.config.LOWER_IS_BETTER` / `docs/TEAM_ANALYTICS.md`).

    `xga_percentile` is preferred as the quality signal when available;
    `shots_on_target_against_percentile` is the fallback (a real proxy, not
    as precise as xGA). Returns `"insufficient_data"` -- never a fabricated
    verdict -- whenever the volume percentile or both quality percentiles
    are missing, and also whenever neither strong-threshold pattern below
    is met (a real but unremarkable case; this classifier's closed 3-label
    contract has no separate "aligned" label).
    """

    quality_percentile = (
        xga_percentile if xga_percentile is not None else shots_on_target_against_percentile
    )
    if shots_total_against_percentile is None or quality_percentile is None:
        return "insufficient_data"

    if (
        shots_total_against_percentile >= _HIGH_PERCENTILE_THRESHOLD
        and quality_percentile <= _LOW_PERCENTILE_THRESHOLD
    ):
        return "few_but_high_quality_chances_allowed"
    if (
        shots_total_against_percentile <= _LOW_PERCENTILE_THRESHOLD
        and quality_percentile >= _HIGH_PERCENTILE_THRESHOLD
    ):
        return "high_volume_low_quality_allowed"
    return "insufficient_data"


def _as_float_or_none(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None
