"""Team-level diagnostic rules.

Every rule is a pure function of already-computed evidence (percentiles,
`TeamScore` snapshots) -- never raw provider payloads -- and returns
`DiagnosticFinding | None`.

`results_above_process`/`results_below_process`/`creation_problem`/
`defensive_process_weak` wrap `team_analytics.engine`'s already-computed
`TeamScore.results_process_signal` / `TeamScore.diagnostics["signals"]`
verbatim -- Team Intelligence stays the single source of truth for those
numbers, this only reshapes them. `defensive_process_strong`,
`sterile_possession`, `few_but_high_quality_chances_allowed`, and
`high_volume_low_quality_allowed` are genuinely new deterministic
classifications built only from `TeamScore`/`TeamFeature` percentile-scale
inputs (the last two via `team_analytics.engine_v2.
classify_chance_quality_allowed`).
"""

from __future__ import annotations

from datetime import datetime

from football_intelligence.diagnostics.models import DiagnosticFinding
from football_intelligence.diagnostics.severity import severity_from_magnitude
from football_intelligence.team_analytics.engine_v2 import classify_chance_quality_allowed
from football_intelligence.team_analytics.models import TeamScore

DIAGNOSTIC_MODEL_VERSION = "diagnostic-v1.0"

_POSSESSION_THRESHOLD = 65.0
_CREATION_THRESHOLD = 35.0
_DEFENSE_STRONG_THRESHOLD = 65.0
_REGRESSION_DELTA_THRESHOLD = 20.0
_REGRESSION_CONFIDENCE_CEILING = 0.45


def results_above_process(
    score: TeamScore,
    *,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """Wrap `TeamScore.results_process_signal == "results_above_process"`."""

    if score.results_process_signal != "results_above_process":
        return None
    return _wrap_delta_signal(
        score, diagnostic_code="results_above_process", computed_at=computed_at
    )


def results_below_process(
    score: TeamScore,
    *,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """Wrap `TeamScore.results_process_signal == "results_below_process"`."""

    if score.results_process_signal != "results_below_process":
        return None
    return _wrap_delta_signal(
        score, diagnostic_code="results_below_process", computed_at=computed_at
    )


def _wrap_delta_signal(
    score: TeamScore,
    *,
    diagnostic_code: str,
    computed_at: datetime,
) -> DiagnosticFinding:
    return DiagnosticFinding(
        diagnostic_code=diagnostic_code,
        entity_type="team",
        entity_id=score.team_id,
        severity=severity_from_magnitude(score.results_process_delta, notable=12.0, high=25.0),
        confidence=score.confidence,
        supporting_metrics={
            "team_name": score.team_name,
            "results_process_delta": score.results_process_delta,
            "overall_score": score.overall_score,
            "process": score.dimension_scores.get("process"),
            "results": score.dimension_scores.get("results"),
        },
        comparison_group=score.scope_key,
        window=score.window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def creation_problem(
    score: TeamScore,
    *,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """Wrap `TeamScore.diagnostics["signals"]`'s existing `"creation_issue"` flag."""

    if "creation_issue" not in score.diagnostics.get("signals", ()):
        return None
    return DiagnosticFinding(
        diagnostic_code="creation_problem",
        entity_type="team",
        entity_id=score.team_id,
        severity="notable",
        confidence=score.confidence,
        supporting_metrics={
            "team_name": score.team_name,
            "chance_generation": score.dimension_scores.get("chance_generation"),
            "finishing_proxy": score.dimension_scores.get("finishing_proxy"),
        },
        comparison_group=score.scope_key,
        window=score.window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def defensive_process_weak(
    score: TeamScore,
    *,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """Wrap `TeamScore.diagnostics["signals"]`'s existing `"defensive_process_issue"` flag."""

    if "defensive_process_issue" not in score.diagnostics.get("signals", ()):
        return None
    return DiagnosticFinding(
        diagnostic_code="defensive_process_weak",
        entity_type="team",
        entity_id=score.team_id,
        severity="notable",
        confidence=score.confidence,
        supporting_metrics={
            "team_name": score.team_name,
            "defense": score.dimension_scores.get("defense"),
        },
        comparison_group=score.scope_key,
        window=score.window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def defensive_process_strong(
    score: TeamScore,
    *,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """New threshold: defense dimension score at or above 65 (V1 never flags a 'strong' case)."""

    defense = score.dimension_scores.get("defense")
    if defense is None or defense < _DEFENSE_STRONG_THRESHOLD:
        return None
    return DiagnosticFinding(
        diagnostic_code="defensive_process_strong",
        entity_type="team",
        entity_id=score.team_id,
        severity=severity_from_magnitude(
            defense - _DEFENSE_STRONG_THRESHOLD, notable=0.0, high=20.0
        ),
        confidence=score.confidence,
        supporting_metrics={"team_name": score.team_name, "defense": defense},
        comparison_group=score.scope_key,
        window=score.window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def regression_risk(
    score: TeamScore,
    *,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """Results far above process, but built on a low-confidence sample."""

    if score.results_process_delta < _REGRESSION_DELTA_THRESHOLD:
        return None
    if score.confidence > _REGRESSION_CONFIDENCE_CEILING:
        return None
    return DiagnosticFinding(
        diagnostic_code="regression_risk",
        entity_type="team",
        entity_id=score.team_id,
        severity="high" if score.results_process_delta >= 30.0 else "notable",
        confidence=score.confidence,
        supporting_metrics={
            "team_name": score.team_name,
            "results_process_delta": score.results_process_delta,
            "matches": score.matches,
        },
        comparison_group=score.scope_key,
        window=score.window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def sterile_possession(
    *,
    team_id: int,
    team_name: str,
    comparison_group: str,
    window: str,
    possession_percentile: float | None,
    chance_generation_percentile: float | None,
    confidence: float,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    """High possession, but low chance creation."""

    if possession_percentile is None or chance_generation_percentile is None:
        return None
    if possession_percentile < _POSSESSION_THRESHOLD:
        return None
    if chance_generation_percentile > _CREATION_THRESHOLD:
        return None

    gap = possession_percentile - chance_generation_percentile
    return DiagnosticFinding(
        diagnostic_code="sterile_possession",
        entity_type="team",
        entity_id=team_id,
        severity=severity_from_magnitude(gap, notable=40.0, high=60.0),
        confidence=confidence,
        supporting_metrics={
            "team_name": team_name,
            "possession_percentile": possession_percentile,
            "chance_generation_percentile": chance_generation_percentile,
        },
        comparison_group=comparison_group,
        window=window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def few_but_high_quality_chances_allowed(
    *,
    team_id: int,
    team_name: str,
    comparison_group: str,
    window: str,
    shots_total_against_percentile: float | None,
    shots_on_target_against_percentile: float | None,
    xga_percentile: float | None,
    confidence: float,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    signal = classify_chance_quality_allowed(
        shots_total_against_percentile=shots_total_against_percentile,
        shots_on_target_against_percentile=shots_on_target_against_percentile,
        xga_percentile=xga_percentile,
    )
    if signal != "few_but_high_quality_chances_allowed":
        return None
    return DiagnosticFinding(
        diagnostic_code="few_but_high_quality_chances_allowed",
        entity_type="team",
        entity_id=team_id,
        severity="notable",
        confidence=confidence,
        supporting_metrics={
            "team_name": team_name,
            "shots_total_against_percentile": shots_total_against_percentile,
            "shots_on_target_against_percentile": shots_on_target_against_percentile,
            "xga_percentile": xga_percentile,
        },
        comparison_group=comparison_group,
        window=window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )


def high_volume_low_quality_allowed(
    *,
    team_id: int,
    team_name: str,
    comparison_group: str,
    window: str,
    shots_total_against_percentile: float | None,
    shots_on_target_against_percentile: float | None,
    xga_percentile: float | None,
    confidence: float,
    computed_at: datetime,
) -> DiagnosticFinding | None:
    signal = classify_chance_quality_allowed(
        shots_total_against_percentile=shots_total_against_percentile,
        shots_on_target_against_percentile=shots_on_target_against_percentile,
        xga_percentile=xga_percentile,
    )
    if signal != "high_volume_low_quality_allowed":
        return None
    return DiagnosticFinding(
        diagnostic_code="high_volume_low_quality_allowed",
        entity_type="team",
        entity_id=team_id,
        severity="notable",
        confidence=confidence,
        supporting_metrics={
            "team_name": team_name,
            "shots_total_against_percentile": shots_total_against_percentile,
            "shots_on_target_against_percentile": shots_on_target_against_percentile,
            "xga_percentile": xga_percentile,
        },
        comparison_group=comparison_group,
        window=window,
        model_version=DIAGNOSTIC_MODEL_VERSION,
        computed_at=computed_at,
    )
