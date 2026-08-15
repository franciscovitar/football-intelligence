"""Player-level diagnostic rules.

Every rule is a pure function of already-computed evidence (percentiles,
scores, meta/rating snapshots) -- never raw provider payloads -- and returns
`DiagnosticFinding | None`. `None` means the required evidence was not
available or did not clear the rule's threshold; it is never fabricated.

`finishing_underperformance`/`finishing_overperformance`/
`high_volume_low_quality_shooting` are deterministic computations from direct
residual and percentile evidence respectively. `breakout_signal`/`underrated`/`overrated`
wrap an already-computed `meta_analytics`/`rating_intelligence` snapshot
into the finding shape without recomputing anything -- those packages stay
the single source of truth for their numbers.
"""

from __future__ import annotations

from datetime import datetime

from football_intelligence.diagnostics.models import DiagnosticFinding
from football_intelligence.diagnostics.severity import severity_from_magnitude
from football_intelligence.meta_analytics.models import PlayerMetaSnapshot
from football_intelligence.player_analytics.engine_v2 import classify_results_vs_process
from football_intelligence.rating_intelligence.models import PlayerRatingSnapshot

DIAGNOSTIC_MODEL_VERSION = "diagnostic-v1.0"

_SHOOTING_VOLUME_THRESHOLD = 65.0
_SHOOTING_ACCURACY_THRESHOLD = 35.0
_MIN_FINISHING_EXPECTED_OUTPUT = 5.0
_MIN_FINISHING_MINUTES = 450
_MIN_FINISHING_SHOTS = 10.0


def finishing_underperformance(
    *,
    player_id: int,
    player_name: str,
    comparison_group: str,
    window: str,
    goals: float | None,
    goals_percentile: float | None,
    xg: float | None,
    xg_percentile: float | None,
    confidence: float,
    computed_at: datetime,
    minutes: int | None = None,
    shots_total: float | None = None,
    non_penalty_goals: float | None = None,
    npxg: float | None = None,
) -> DiagnosticFinding | None:
    """Goals materially below xG using a direct residual and sample gates."""

    evidence = _finishing_evidence(
        goals=goals,
        xg=xg,
        confidence=confidence,
        minutes=minutes,
        shots_total=shots_total,
        non_penalty_goals=non_penalty_goals,
        npxg=npxg,
    )
    if evidence is None:
        return None
    actual, expected, residual, evidence_confidence = evidence
    signal = classify_results_vs_process(
        raw_output=actual,
        output_percentile=goals_percentile,
        expected_output=expected,
        expected_output_percentile=xg_percentile,
    )
    if signal != "results_below_process":
        return None

    magnitude = abs(residual)
    return DiagnosticFinding(
        diagnostic_code="finishing_underperformance",
        entity_type="player",
        entity_id=player_id,
        severity=severity_from_magnitude(magnitude, notable=2.0, high=5.0),
        confidence=evidence_confidence,
        supporting_metrics={
            "player_name": player_name,
            "goals": goals,
            "goals_percentile": goals_percentile,
            "xg": xg,
            "xg_percentile": xg_percentile,
            "non_penalty_goals": non_penalty_goals,
            "npxg": npxg,
            "finishing_residual": residual,
            "finishing_residual_per90": (
                residual * 90.0 / minutes if minutes is not None and minutes > 0 else None
            ),
            "minutes": minutes,
            "shots_total": shots_total,
        },
        comparison_group=comparison_group,
        window=window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def finishing_overperformance(
    *,
    player_id: int,
    player_name: str,
    comparison_group: str,
    window: str,
    goals: float | None,
    goals_percentile: float | None,
    xg: float | None,
    xg_percentile: float | None,
    confidence: float,
    computed_at: datetime,
    minutes: int | None = None,
    shots_total: float | None = None,
    non_penalty_goals: float | None = None,
    npxg: float | None = None,
) -> DiagnosticFinding | None:
    """Goals materially above xG using a direct residual and sample gates."""

    evidence = _finishing_evidence(
        goals=goals,
        xg=xg,
        confidence=confidence,
        minutes=minutes,
        shots_total=shots_total,
        non_penalty_goals=non_penalty_goals,
        npxg=npxg,
    )
    if evidence is None:
        return None
    actual, expected, residual, evidence_confidence = evidence
    signal = classify_results_vs_process(
        raw_output=actual,
        output_percentile=goals_percentile,
        expected_output=expected,
        expected_output_percentile=xg_percentile,
    )
    if signal != "results_above_process":
        return None

    magnitude = abs(residual)
    return DiagnosticFinding(
        diagnostic_code="finishing_overperformance",
        entity_type="player",
        entity_id=player_id,
        severity=severity_from_magnitude(magnitude, notable=2.0, high=5.0),
        confidence=evidence_confidence,
        supporting_metrics={
            "player_name": player_name,
            "goals": goals,
            "goals_percentile": goals_percentile,
            "xg": xg,
            "xg_percentile": xg_percentile,
            "non_penalty_goals": non_penalty_goals,
            "npxg": npxg,
            "finishing_residual": residual,
            "finishing_residual_per90": (
                residual * 90.0 / minutes if minutes is not None and minutes > 0 else None
            ),
            "minutes": minutes,
            "shots_total": shots_total,
        },
        comparison_group=comparison_group,
        window=window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def _finishing_evidence(
    *,
    goals: float | None,
    xg: float | None,
    confidence: float,
    minutes: int | None,
    shots_total: float | None,
    non_penalty_goals: float | None,
    npxg: float | None,
) -> tuple[float, float, float, float] | None:
    if goals is None or xg is None:
        return None
    actual = non_penalty_goals if non_penalty_goals is not None and npxg is not None else goals
    expected = npxg if non_penalty_goals is not None and npxg is not None else xg
    if expected < _MIN_FINISHING_EXPECTED_OUTPUT:
        return None
    if minutes is not None and minutes < _MIN_FINISHING_MINUTES:
        return None
    if shots_total is not None and shots_total < _MIN_FINISHING_SHOTS:
        return None

    opportunity_confidence = expected / (expected + _MIN_FINISHING_EXPECTED_OUTPUT)
    if minutes is not None:
        opportunity_confidence = min(
            opportunity_confidence,
            minutes / (minutes + _MIN_FINISHING_MINUTES),
        )
    evidence_confidence = max(0.0, min(1.0, min(confidence, opportunity_confidence)))
    return actual, expected, actual - expected, evidence_confidence


def high_volume_low_quality_shooting(
    *,
    player_id: int,
    player_name: str,
    comparison_group: str,
    window: str,
    shots_percentile: float | None,
    shot_accuracy_percentile: float | None,
    confidence: float,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """High shot volume but low accuracy (shots_on_target_pct-style percentile)."""

    if shots_percentile is None or shot_accuracy_percentile is None:
        return None
    if shots_percentile < _SHOOTING_VOLUME_THRESHOLD:
        return None
    if shot_accuracy_percentile > _SHOOTING_ACCURACY_THRESHOLD:
        return None

    gap = shots_percentile - shot_accuracy_percentile
    return DiagnosticFinding(
        diagnostic_code="high_volume_low_quality_shooting",
        entity_type="player",
        entity_id=player_id,
        severity=severity_from_magnitude(gap, notable=40.0, high=60.0),
        confidence=confidence,
        supporting_metrics={
            "player_name": player_name,
            "shots_percentile": shots_percentile,
            "shot_accuracy_percentile": shot_accuracy_percentile,
        },
        comparison_group=comparison_group,
        window=window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def breakout_signal(
    snapshot: PlayerMetaSnapshot | None,
    *,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """Wrap `meta_analytics`'s existing `watchlist_signal == "breakout"` verdict."""

    if snapshot is None or snapshot.watchlist_signal != "breakout":
        return None
    return DiagnosticFinding(
        diagnostic_code="breakout_signal",
        entity_type="player",
        entity_id=snapshot.player_id,
        severity="high" if snapshot.watchlist_score >= 80.0 else "notable",
        confidence=snapshot.stable_confidence,
        supporting_metrics={
            "player_name": snapshot.player_name,
            "watchlist_score": snapshot.watchlist_score,
            "stable_score": snapshot.stable_score,
            "surprise_delta": snapshot.surprise_delta,
            "trend_delta": snapshot.trend_delta,
        },
        comparison_group=f"role:{snapshot.role}",
        window="stable",
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def underrated(
    snapshot: PlayerRatingSnapshot | None,
    *,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """Wrap `rating_intelligence`'s existing `rating_signal == "underrated"` verdict."""

    if snapshot is None or snapshot.rating_signal != "underrated" or snapshot.rating_gap is None:
        return None
    return DiagnosticFinding(
        diagnostic_code="underrated",
        entity_type="player",
        entity_id=snapshot.player_id,
        severity=severity_from_magnitude(snapshot.rating_gap, notable=12.0, high=25.0),
        confidence=snapshot.rating_confidence,
        supporting_metrics={
            "player_name": snapshot.player_name,
            "performance_score": snapshot.performance_score,
            "perception_score": snapshot.perception_score,
            "rating_gap": snapshot.rating_gap,
        },
        comparison_group=f"role:{snapshot.role}",
        window="rating",
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def overrated(
    snapshot: PlayerRatingSnapshot | None,
    *,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """Wrap `rating_intelligence`'s existing `rating_signal == "overrated"` verdict."""

    if snapshot is None or snapshot.rating_signal != "overrated" or snapshot.rating_gap is None:
        return None
    return DiagnosticFinding(
        diagnostic_code="overrated",
        entity_type="player",
        entity_id=snapshot.player_id,
        severity=severity_from_magnitude(snapshot.rating_gap, notable=12.0, high=25.0),
        confidence=snapshot.rating_confidence,
        supporting_metrics={
            "player_name": snapshot.player_name,
            "performance_score": snapshot.performance_score,
            "perception_score": snapshot.perception_score,
            "rating_gap": snapshot.rating_gap,
        },
        comparison_group=f"role:{snapshot.role}",
        window="rating",
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )
