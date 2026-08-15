"""Evidence profiles for the Team Statistical Engine V2."""

from __future__ import annotations

from football_intelligence.player_analytics.profiles_v2 import MetricWeight

PROFILE_VERSION = "team-dimensions-v2.0"

TEAM_DIMENSION_PROFILES: dict[str, tuple[MetricWeight, ...]] = {
    "attack": (
        MetricWeight("goals_for", 0.35, core=True),
        MetricWeight("xg", 0.35, core=True),
        MetricWeight("box_entries", 0.30),
    ),
    "defence": (
        MetricWeight("goals_against", 0.30, -1, True),
        MetricWeight("xga", 0.35, -1, True),
        MetricWeight("shots_allowed", 0.20, -1),
        MetricWeight("big_chances_allowed", 0.15, -1),
    ),
    "creation": (
        MetricWeight("xg", 0.30, core=True),
        MetricWeight("big_chances", 0.25, core=True),
        MetricWeight("box_entries", 0.25),
        MetricWeight("deep_completions", 0.20),
    ),
    "finishing": (
        MetricWeight("goals_for", 0.45, core=True),
        MetricWeight("xg_per_shot", 0.25),
        MetricWeight("shots_on_target", 0.30, core=True),
    ),
    "chance_quality": (
        MetricWeight("xg_per_shot", 0.55, core=True),
        MetricWeight("big_chances", 0.45),
    ),
    "shot_generation": (
        MetricWeight("shots_total", 0.45, core=True),
        MetricWeight("shots_on_target", 0.35),
        MetricWeight("shots_inside_box", 0.20),
    ),
    "control": (
        MetricWeight("possession_pct", 0.45, core=True),
        MetricWeight("field_tilt", 0.35),
        MetricWeight("recoveries", 0.20),
    ),
    "progression": (
        MetricWeight("progressive_passes", 0.55, core=True),
        MetricWeight("final_third_entries", 0.45),
    ),
    "penetration": (
        MetricWeight("box_entries", 0.40, core=True),
        MetricWeight("touches_in_box", 0.35),
        MetricWeight("deep_completions", 0.25),
    ),
    "build_up": (
        MetricWeight("pass_accuracy_pct", 0.40, core=True),
        MetricWeight("progressive_passes", 0.35, core=True),
        MetricWeight("final_third_entries", 0.25),
    ),
    "pressing": (
        MetricWeight("successful_pressures", 0.35, core=True),
        MetricWeight("pressures", 0.25, core=True),
        MetricWeight("ppda", 0.25, -1),
        MetricWeight("high_turnovers", 0.15),
    ),
    "offensive_transition": (
        MetricWeight("counter_attacks", 0.35, core=True),
        MetricWeight("counter_attack_shots", 0.30, core=True),
        MetricWeight("transition_xg", 0.35),
    ),
    # Catalog V2 currently has offensive transition evidence only. An empty
    # intended profile keeps this dimension explicit and insufficient rather
    # than manufacturing defensive transition from generic xGA/shot volume.
    "defensive_transition": (),
    "set_pieces": (
        MetricWeight("set_piece_shots", 0.35, core=True),
        MetricWeight("set_piece_xg", 0.40, core=True),
        MetricWeight("corners", 0.25),
    ),
}

TEAM_OVERALL_WEIGHTS: dict[str, float] = {
    "attack": 0.12,
    "defence": 0.12,
    "creation": 0.09,
    "finishing": 0.07,
    "chance_quality": 0.06,
    "shot_generation": 0.07,
    "control": 0.08,
    "progression": 0.08,
    "penetration": 0.07,
    "build_up": 0.06,
    "pressing": 0.06,
    "offensive_transition": 0.04,
    "defensive_transition": 0.04,
    "set_pieces": 0.04,
}
