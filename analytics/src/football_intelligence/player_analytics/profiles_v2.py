"""Versioned evidence profiles for Player Statistical Engine V2."""

from __future__ import annotations

from dataclasses import dataclass

PROFILE_VERSION = "player-dimensions-v2.0"


@dataclass(frozen=True, slots=True)
class MetricWeight:
    metric_name: str
    weight: float
    direction: int = 1
    core: bool = False


DIMENSION_PROFILES: dict[str, tuple[MetricWeight, ...]] = {
    "performance": (
        MetricWeight("goal_contributions", 0.55, core=True),
        MetricWeight("goals", 0.25),
        MetricWeight("assists", 0.20),
    ),
    "underlying_performance": (
        MetricWeight("npxg", 0.40, core=True),
        MetricWeight("xa", 0.35, core=True),
        MetricWeight("xg_plus_xa", 0.25),
    ),
    "finishing": (
        MetricWeight("goals_minus_xg", 0.25, core=True),
        MetricWeight("non_penalty_goals_minus_npxg", 0.25),
        MetricWeight("goals_per_shot", 0.20),
        MetricWeight("shots_on_target_pct", 0.15),
        MetricWeight("xg_per_shot", 0.15),
    ),
    "shot_generation": (
        MetricWeight("advanced.xg", 0.35, core=True),
        MetricWeight("shots_total", 0.25, core=True),
        MetricWeight("touches_in_box", 0.20),
        MetricWeight("big_chances", 0.20),
    ),
    "creation": (
        MetricWeight("xa", 0.30, core=True),
        MetricWeight("key_passes", 0.20, core=True),
        MetricWeight("shot_creating_actions", 0.20),
        MetricWeight("passes_into_box", 0.15),
        MetricWeight("expected_threat_created", 0.15),
    ),
    "progression": (
        MetricWeight("progressive_passes", 0.30, core=True),
        MetricWeight("progressive_carries", 0.30, core=True),
        MetricWeight("passes_into_final_third", 0.20),
        MetricWeight("carries_into_final_third", 0.20),
    ),
    "passing": (
        MetricWeight("pass_completion_pct", 0.35, core=True),
        MetricWeight("progressive_passes", 0.30),
        MetricWeight("passes_into_final_third", 0.20),
        MetricWeight("long_passes_accurate", 0.15),
    ),
    "one_v_one": (
        MetricWeight("take_on_success_pct", 0.35, core=True),
        MetricWeight("dribbles_successful", 0.30),
        MetricWeight("players_beaten", 0.20),
        MetricWeight("progressive_carries", 0.15),
    ),
    "defence": (
        MetricWeight("tackles", 0.20, core=True),
        MetricWeight("interceptions", 0.25, core=True),
        MetricWeight("blocks", 0.20),
        MetricWeight("errors_leading_to_shot", 0.20, -1),
        MetricWeight("errors_leading_to_goal", 0.15, -1),
    ),
    "ball_winning": (
        MetricWeight("tackles_won", 0.30, core=True),
        MetricWeight("recoveries", 0.25),
        MetricWeight("successful_pressures", 0.25),
        MetricWeight("duel_win_pct", 0.20),
    ),
    "aerial": (
        MetricWeight("aerial_duels_won", 0.55, core=True),
        MetricWeight("aerial_duel_win_pct", 0.45),
    ),
    "goalkeeping": (
        MetricWeight("save_pct", 0.35, core=True),
        MetricWeight("goals_prevented", 0.30, core=True),
        MetricWeight("crosses_stopped", 0.15),
        MetricWeight("sweeper_actions", 0.10),
        MetricWeight("distribution_accuracy_pct", 0.10),
    ),
}

# Overall is deliberately composed from dimensions, not their underlying metrics.
POSITION_DIMENSION_WEIGHTS: dict[str, tuple[tuple[str, float], ...]] = {
    # Distribution is already an explicit component of Goalkeeping; general
    # outfield Passing inputs are not required for a goalkeeper Overall.
    "goalkeeper": (("goalkeeping", 1.00),),
    "centre_back": (
        ("defence", 0.35),
        ("ball_winning", 0.20),
        ("aerial", 0.20),
        ("passing", 0.15),
        ("progression", 0.10),
    ),
    "fullback_wingback": (
        ("defence", 0.20),
        ("ball_winning", 0.15),
        ("progression", 0.25),
        ("creation", 0.15),
        ("one_v_one", 0.15),
        ("passing", 0.10),
    ),
    "defensive_midfielder": (
        ("ball_winning", 0.30),
        ("defence", 0.20),
        ("passing", 0.20),
        ("progression", 0.20),
        ("creation", 0.10),
    ),
    "central_midfielder": (
        ("passing", 0.25),
        ("progression", 0.25),
        ("creation", 0.20),
        ("ball_winning", 0.20),
        ("underlying_performance", 0.10),
    ),
    "attacking_midfielder": (
        ("creation", 0.30),
        ("underlying_performance", 0.20),
        ("progression", 0.20),
        ("one_v_one", 0.15),
        ("performance", 0.15),
    ),
    "winger": (
        ("one_v_one", 0.25),
        ("creation", 0.20),
        ("progression", 0.20),
        ("shot_generation", 0.15),
        ("finishing", 0.10),
        ("performance", 0.10),
    ),
    "forward": (
        ("finishing", 0.30),
        ("shot_generation", 0.25),
        ("underlying_performance", 0.15),
        ("creation", 0.10),
        ("one_v_one", 0.10),
        ("performance", 0.10),
    ),
}

MIN_DIMENSION_EVIDENCE_COVERAGE = 0.60
