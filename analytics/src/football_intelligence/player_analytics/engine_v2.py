"""Player Analytics V2: position-family scoring, ranking gate, results-vs-process.

Does NOT rewrite `player_analytics/engine.py` V1 (model version `player-v1.0`
stays exactly as-is, still used/tested as-is). V2 layers on top of the V1
computation instead of recomputing percentiles from scratch:

- V1 already computes role-aware, shrinkage-stabilized, context-adjusted
  per-90 percentiles within each broad role (`goalkeeper`/`defender`/
  `midfielder`/`forward`) population. Recomputing those percentiles within a
  finer position-family population (Task 2) would need a materially smaller
  reference population per family -- often too small to be meaningful with
  today's fixture-scale data -- and would duplicate a large amount of V1's
  aggregation/shrinkage logic for no accuracy gain. V2 therefore reuses V1's
  percentiles unchanged and instead recombines them using a finer,
  position-family-specific weight profile (`position_profiles.
  POSITION_FAMILY_SCORE_WEIGHTS`) when the player's primary position family
  is classified; both the coarse V1 role and the fine V2 family are exposed
  on `PlayerScoreV2` (`role`, `position_family`), never just one.
- When a player's primary listed position doesn't resolve to a fine family,
  or the complete intended evidence profile is unavailable, V2 exposes an
  explicit evidence state and no numeric score. It never substitutes V1 or
  renormalizes a partial metric set into an apparently complete V2 score.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from football_intelligence.player_analytics.engine import calculate_player_analytics
from football_intelligence.player_analytics.models import PlayerFeature, PlayerObservation
from football_intelligence.position_profiles import (
    MIN_PROFILE_EVIDENCE_COVERAGE,
    POSITION_FAMILY_CORE_METRICS,
    POSITION_FAMILY_SCORE_WEIGHTS,
    classify_position_family,
)

MODEL_VERSION = "player-v2.0"

# V1's own role recognition (`player_analytics.config.ROLE_ALIASES`) only
# understands broad tokens (G/D/M/F and their synonyms) -- the only shape
# the current provider (API-Football) actually emits, per
# docs/PLAYER_ANALYTICS.md. A fine-grained token (e.g. "CB", "CAM") that a
# future provider might supply is invisible to V1's `_primary_role`, so a
# player with only fine tokens would silently be excluded from V1 entirely
# (never scored at all) before V2 could ever apply a fine weight profile to
# them. To keep "layer on top of V1" honest without touching engine.py, V2
# rewrites each observation's `listed_position` to an equivalent broad token
# V1 already understands before calling V1 -- the *original* token is what
# `_primary_position_family` below uses to determine the true fine family
# for weighting, so no precision is lost, only V1's input vocabulary is
# widened.
_FINE_FAMILY_TO_BROAD_TOKEN: dict[str, str] = {
    "goalkeeper": "G",
    "centre_back": "D",
    "fullback_wingback": "D",
    "defensive_midfielder": "M",
    "central_midfielder": "M",
    "attacking_midfielder": "M",
    "winger": "M",
    "forward": "F",
}

# A player is only eligible to rank purely on score once their score
# snapshot clears this confidence floor. Below it, the player is real
# evidence (never hidden) but is never allowed to outrank an eligible player
# on raw score alone -- see `rank_by_confidence_gated_score`.
MIN_RANKING_CONFIDENCE = 0.40

# A two-goal direct residual is the minimum notable finishing magnitude;
# diagnostics add opportunity/minutes/shots confidence gates around it.
MIN_FINISHING_RESIDUAL = 2.0

ResultsVsProcessSignal = (
    str  # "results_above_process" | "results_below_process" | "aligned" | "insufficient_data"
)
EvidenceState = Literal["ready", "partial", "insufficient_data"]


@dataclass(frozen=True, slots=True)
class WeightedScoreEvidence:
    score: float | None
    evidence_weight_available: float
    evidence_weight_required: float
    evidence_coverage_pct: float
    evidence_state: EvidenceState
    evidence_metrics_available: tuple[str, ...]
    evidence_metrics_required: tuple[str, ...]


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
    evidence_metrics_available: tuple[str, ...]
    evidence_metrics_required: tuple[str, ...]
    dimension_scores: Mapping[str, float]
    reference_sample_size: int
    model_version: str
    calculated_at: datetime


def calculate_player_analytics_v2(
    observations: Sequence[PlayerObservation],
    *,
    scope_key: str,
    calculated_at: datetime | None = None,
) -> tuple[PlayerScoreV2, ...]:
    """Layer position-family scoring on top of the V1 computation.

    Reuses `player_analytics.engine.calculate_player_analytics` (V1) for
    feature percentiles and the coarse-role score/confidence/dimensions,
    then recombines each player's already-computed percentiles using a
    finer position-family weight profile where one is classified and usable.
    """

    if not scope_key.strip():
        raise ValueError("scope_key must not be blank")

    effective_calculated_at = calculated_at or datetime.now(UTC)
    v1_result = calculate_player_analytics(
        _v1_compatible_observations(observations),
        scope_key=scope_key,
        calculated_at=effective_calculated_at,
    )

    features_by_player_window: dict[tuple[int, str], dict[str, PlayerFeature]] = defaultdict(dict)
    for feature in v1_result.features:
        features_by_player_window[(feature.player_id, feature.window)][feature.metric_name] = (
            feature
        )

    position_family_by_player = _primary_position_family(observations)

    scores: list[PlayerScoreV2] = []
    for v1_score in v1_result.scores:
        family = position_family_by_player.get(v1_score.player_id)
        weights = POSITION_FAMILY_SCORE_WEIGHTS.get(family) if family is not None else None
        feature_map = features_by_player_window.get((v1_score.player_id, v1_score.window), {})

        evidence = (
            _weighted_percentile_score(
                feature_map,
                weights,
                core_metrics=POSITION_FAMILY_CORE_METRICS.get(family or "", frozenset()),
            )
            if weights
            else WeightedScoreEvidence(
                score=None,
                evidence_weight_available=0.0,
                evidence_weight_required=0.0,
                evidence_coverage_pct=0.0,
                evidence_state="insufficient_data",
                evidence_metrics_available=(),
                evidence_metrics_required=(),
            )
        )
        overall_score = evidence.score

        scores.append(
            PlayerScoreV2(
                player_id=v1_score.player_id,
                player_name=v1_score.player_name,
                scope_key=v1_score.scope_key,
                window=v1_score.window,
                role=v1_score.role,
                position_family=family,
                role_confidence=v1_score.role_confidence,
                minutes=v1_score.minutes,
                appearances=v1_score.appearances,
                overall_score=None if overall_score is None else round(overall_score, 2),
                confidence=round(v1_score.confidence * evidence.evidence_coverage_pct / 100.0, 5),
                evidence_weight_available=evidence.evidence_weight_available,
                evidence_weight_required=evidence.evidence_weight_required,
                evidence_coverage_pct=evidence.evidence_coverage_pct,
                evidence_state=evidence.evidence_state,
                evidence_metrics_available=evidence.evidence_metrics_available,
                evidence_metrics_required=evidence.evidence_metrics_required,
                dimension_scores=v1_score.dimension_scores,
                reference_sample_size=v1_score.reference_sample_size,
                model_version=MODEL_VERSION,
                calculated_at=effective_calculated_at,
            )
        )

    return tuple(scores)


def _v1_compatible_observations(
    observations: Sequence[PlayerObservation],
) -> tuple[PlayerObservation, ...]:
    """Rewrite `listed_position` to a token V1's `ROLE_ALIASES` recognizes.

    A token already broad (e.g. "D", "MID") round-trips through
    `classify_position_family` to the same broad fallback string and back to
    an equivalent broad token, so this is a no-op for today's real
    API-Football data; it only changes behavior for a fine-grained token V1
    itself cannot see.
    """

    rewritten: list[PlayerObservation] = []
    for observation in observations:
        classification = classify_position_family(observation.listed_position)
        if classification is None:
            rewritten.append(observation)
            continue
        broad_token = _FINE_FAMILY_TO_BROAD_TOKEN.get(classification, classification)
        rewritten.append(dataclasses.replace(observation, listed_position=broad_token))
    return tuple(rewritten)


def _primary_position_family(
    observations: Sequence[PlayerObservation],
) -> dict[int, str | None]:
    minutes_by_player_family: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for observation in observations:
        if observation.minutes <= 0:
            continue
        family = classify_position_family(observation.listed_position)
        if family is None:
            continue
        minutes_by_player_family[observation.player_id][family] += observation.minutes

    result: dict[int, str | None] = {}
    for player_id, family_minutes in minutes_by_player_family.items():
        result[player_id] = max(family_minutes.items(), key=lambda item: item[1])[0]
    return result


def _weighted_percentile_score(
    feature_map: Mapping[str, PlayerFeature],
    weights: tuple[tuple[str, float, int], ...],
    *,
    core_metrics: frozenset[str] = frozenset(),
) -> WeightedScoreEvidence:
    weighted_score = 0.0
    available_weight = 0.0
    required_weight = sum(weight for _, weight, _ in weights)
    available_metrics: list[str] = []
    for metric_name, weight, direction in weights:
        feature = feature_map.get(metric_name)
        if feature is None:
            continue
        percentile = feature.percentile if direction > 0 else 100.0 - feature.percentile
        weighted_score += weight * percentile
        available_weight += weight
        available_metrics.append(metric_name)

    coverage = available_weight / required_weight if required_weight > 0 else 0.0
    missing_core = core_metrics - set(available_metrics)
    if available_weight <= 0 or missing_core or coverage < MIN_PROFILE_EVIDENCE_COVERAGE:
        state: EvidenceState = "insufficient_data"
    elif coverage < 1.0:
        state = "partial"
    else:
        state = "ready"

    # A numeric profile score exists only when the complete intended weight is
    # present. Missing evidence is neither renormalized nor treated as zero.
    score = weighted_score / required_weight if state == "ready" else None
    return WeightedScoreEvidence(
        score=score,
        evidence_weight_available=round(available_weight, 6),
        evidence_weight_required=round(required_weight, 6),
        evidence_coverage_pct=round(coverage * 100.0, 2),
        evidence_state=state,
        evidence_metrics_available=tuple(available_metrics),
        evidence_metrics_required=tuple(sorted(core_metrics)),
    )


def rank_by_confidence_gated_score(
    entries: Sequence[tuple[float, float, int]],
) -> tuple[int, ...]:
    """Order `(overall_score, confidence, minutes)` entries for display ranking.

    A player is "ranking eligible" once `confidence >= MIN_RANKING_CONFIDENCE`
    (0.40). Eligible entries are ranked strictly ahead of ineligible ones,
    regardless of raw score, so a low-confidence, low-minute outlier can
    never outrank a high-confidence, high-minute player purely because its
    score happens to be numerically higher. Within each tier, entries sort
    by score desc, then confidence desc, then minutes desc -- deterministic,
    no ML.

    Returns the indices of `entries` in ranked (best-first) order. Example:
    Player A (score=96, confidence=0.94, minutes=2183) and Player B
    (score=98, confidence=0.31, minutes=238) -> A ranks first: B's raw score
    is higher but its confidence falls below the eligibility gate.
    """

    def sort_key(index: int) -> tuple[bool, float, float, int]:
        score, confidence, minutes = entries[index]
        ineligible = confidence < MIN_RANKING_CONFIDENCE
        return (ineligible, -score, -confidence, -minutes)

    return tuple(sorted(range(len(entries)), key=sort_key))


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
    """Classify raw output vs expected/underlying-process output.

    Uses the direct residual (`goals - xG`, or NPG - npxG when both are
    available). Percentiles are accepted for backwards-compatible provenance
    only; subtracting two population ranks is not a finishing residual.
    """

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
