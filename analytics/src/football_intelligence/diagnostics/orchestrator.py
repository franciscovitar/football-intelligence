"""Diagnostic Rule Engine orchestrators.

`evaluate_player_diagnostics` / `evaluate_team_diagnostics` run every
relevant rule against one bundle of already-computed evidence and return
only the findings with real evidence -- an empty tuple is a valid, correct
result (never padded with fabricated findings).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from football_intelligence.diagnostics.models import DiagnosticFinding
from football_intelligence.diagnostics.rules_player import (
    breakout_signal,
    finishing_overperformance,
    finishing_underperformance,
    high_volume_low_quality_shooting,
    overrated,
    underrated,
)
from football_intelligence.diagnostics.rules_team import (
    creation_problem,
    defensive_process_strong,
    defensive_process_weak,
    few_but_high_quality_chances_allowed,
    high_volume_low_quality_allowed,
    regression_risk,
    results_above_process,
    results_below_process,
    sterile_possession,
)
from football_intelligence.meta_analytics.models import PlayerMetaSnapshot
from football_intelligence.rating_intelligence.models import PlayerRatingSnapshot
from football_intelligence.team_analytics.models import TeamScore


@dataclass(frozen=True, slots=True)
class PlayerDiagnosticInputs:
    player_id: int
    player_name: str
    comparison_group: str
    window: str
    confidence: float
    goals: float | None = None
    goals_percentile: float | None = None
    xg: float | None = None
    xg_percentile: float | None = None
    shots_percentile: float | None = None
    shot_accuracy_percentile: float | None = None
    meta_snapshot: PlayerMetaSnapshot | None = None
    rating_snapshot: PlayerRatingSnapshot | None = None


@dataclass(frozen=True, slots=True)
class TeamDiagnosticInputs:
    team_id: int
    team_name: str
    comparison_group: str
    window: str
    confidence: float
    possession_percentile: float | None = None
    chance_generation_percentile: float | None = None
    shots_total_against_percentile: float | None = None
    shots_on_target_against_percentile: float | None = None
    xga_percentile: float | None = None
    score: TeamScore | None = None


def evaluate_player_diagnostics(
    inputs: PlayerDiagnosticInputs,
    *,
    computed_at: datetime,
) -> tuple[DiagnosticFinding, ...]:
    candidates = (
        finishing_underperformance(
            player_id=inputs.player_id,
            player_name=inputs.player_name,
            comparison_group=inputs.comparison_group,
            window=inputs.window,
            goals=inputs.goals,
            goals_percentile=inputs.goals_percentile,
            xg=inputs.xg,
            xg_percentile=inputs.xg_percentile,
            confidence=inputs.confidence,
            computed_at=computed_at,
        ),
        finishing_overperformance(
            player_id=inputs.player_id,
            player_name=inputs.player_name,
            comparison_group=inputs.comparison_group,
            window=inputs.window,
            goals=inputs.goals,
            goals_percentile=inputs.goals_percentile,
            xg=inputs.xg,
            xg_percentile=inputs.xg_percentile,
            confidence=inputs.confidence,
            computed_at=computed_at,
        ),
        high_volume_low_quality_shooting(
            player_id=inputs.player_id,
            player_name=inputs.player_name,
            comparison_group=inputs.comparison_group,
            window=inputs.window,
            shots_percentile=inputs.shots_percentile,
            shot_accuracy_percentile=inputs.shot_accuracy_percentile,
            confidence=inputs.confidence,
            computed_at=computed_at,
        ),
        breakout_signal(inputs.meta_snapshot, computed_at=computed_at),
        underrated(inputs.rating_snapshot, computed_at=computed_at),
        overrated(inputs.rating_snapshot, computed_at=computed_at),
    )
    return tuple(finding for finding in candidates if finding is not None)


def evaluate_team_diagnostics(
    inputs: TeamDiagnosticInputs,
    *,
    computed_at: datetime,
) -> tuple[DiagnosticFinding, ...]:
    candidates: list[DiagnosticFinding | None] = [
        sterile_possession(
            team_id=inputs.team_id,
            team_name=inputs.team_name,
            comparison_group=inputs.comparison_group,
            window=inputs.window,
            possession_percentile=inputs.possession_percentile,
            chance_generation_percentile=inputs.chance_generation_percentile,
            confidence=inputs.confidence,
            computed_at=computed_at,
        ),
        few_but_high_quality_chances_allowed(
            team_id=inputs.team_id,
            team_name=inputs.team_name,
            comparison_group=inputs.comparison_group,
            window=inputs.window,
            shots_total_against_percentile=inputs.shots_total_against_percentile,
            shots_on_target_against_percentile=inputs.shots_on_target_against_percentile,
            xga_percentile=inputs.xga_percentile,
            confidence=inputs.confidence,
            computed_at=computed_at,
        ),
        high_volume_low_quality_allowed(
            team_id=inputs.team_id,
            team_name=inputs.team_name,
            comparison_group=inputs.comparison_group,
            window=inputs.window,
            shots_total_against_percentile=inputs.shots_total_against_percentile,
            shots_on_target_against_percentile=inputs.shots_on_target_against_percentile,
            xga_percentile=inputs.xga_percentile,
            confidence=inputs.confidence,
            computed_at=computed_at,
        ),
    ]

    if inputs.score is not None:
        score = inputs.score
        candidates.extend(
            [
                results_above_process(score, computed_at=computed_at),
                results_below_process(score, computed_at=computed_at),
                defensive_process_strong(score, computed_at=computed_at),
                defensive_process_weak(score, computed_at=computed_at),
                creation_problem(score, computed_at=computed_at),
                regression_risk(score, computed_at=computed_at),
            ]
        )

    return tuple(finding for finding in candidates if finding is not None)
