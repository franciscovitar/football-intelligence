"""Player-level diagnostic rules.

Every rule is a pure function of already-computed evidence (percentiles,
scores, meta/rating snapshots) -- never raw provider payloads -- and returns
`DiagnosticFinding | None`. `None` means the required evidence was not
available or did not clear the rule's threshold; it is never fabricated.

`finishing_underperformance`/`finishing_overperformance`/
`high_volume_low_quality_shooting` are genuinely new computations built only
from percentile-scale inputs. `breakout_signal`/`underrated`/`overrated`
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
) -> DiagnosticFinding | None:
    """Goals materially below xG (output percentile << expected-output percentile)."""

    if goals is None or goals_percentile is None or xg is None or xg_percentile is None:
        return None
    signal = classify_results_vs_process(
        raw_output=goals,
        output_percentile=goals_percentile,
        expected_output=xg,
        expected_output_percentile=xg_percentile,
    )
    if signal != "results_below_process":
        return None

    gap = xg_percentile - goals_percentile
    return DiagnosticFinding(
        diagnostic_code="finishing_underperformance",
        entity_type="player",
        entity_id=player_id,
        severity=severity_from_magnitude(gap, notable=12.0, high=25.0),
        confidence=confidence,
        supporting_metrics={
            "player_name": player_name,
            "goals": goals,
            "goals_percentile": goals_percentile,
            "xg": xg,
            "xg_percentile": xg_percentile,
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
) -> DiagnosticFinding | None:
    """Goals materially above xG (output percentile >> expected-output percentile)."""

    if goals is None or goals_percentile is None or xg is None or xg_percentile is None:
        return None
    signal = classify_results_vs_process(
        raw_output=goals,
        output_percentile=goals_percentile,
        expected_output=xg,
        expected_output_percentile=xg_percentile,
    )
    if signal != "results_above_process":
        return None

    gap = goals_percentile - xg_percentile
    return DiagnosticFinding(
        diagnostic_code="finishing_overperformance",
        entity_type="player",
        entity_id=player_id,
        severity=severity_from_magnitude(gap, notable=12.0, high=25.0),
        confidence=confidence,
        supporting_metrics={
            "player_name": player_name,
            "goals": goals,
            "goals_percentile": goals_percentile,
            "xg": xg,
            "xg_percentile": xg_percentile,
        },
        comparison_group=comparison_group,
        window=window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


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
