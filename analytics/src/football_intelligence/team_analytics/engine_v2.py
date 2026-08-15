"""Team Analytics V2: additive diagnostic-shape export + chance-quality signal.

Does NOT rewrite `team_analytics/engine.py` V1. `engine.py`'s `_score_team`
already computes `results_process_delta`, `results_process_signal`, and a
small set of deterministic issue flags (`finishing_issue`/`creation_issue`/
`defensive_process_issue`) into `TeamScore.diagnostics["signals"]` -- Team
Intelligence stays the single source of truth for those numbers.
`extract_team_issue_signals` only reshapes that already-computed evidence
into the structured, per-signal shape the Block 16 diagnostic rule engine
(`diagnostics/`) consumes; it never recomputes a score, delta, or signal.

`classify_chance_quality_allowed` is the one genuinely new team-level
diagnostic this module adds: how the team's shot-volume-against percentile
compares to its shot-quality-against percentile (shots on target allowed, or
xGA when available). This deliberately depends on `team_analytics.engine`'s
already-percentiled `TeamFeature` values (via the caller), never on raw
provider payloads.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from football_intelligence.team_analytics.models import TeamScore

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
