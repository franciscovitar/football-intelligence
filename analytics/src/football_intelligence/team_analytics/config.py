"""Versioned Team Analytics V1 configuration."""

from __future__ import annotations

WINDOWS: tuple[tuple[str, int | None], ...] = (
    ("last_3", 3),
    ("last_5", 5),
    ("last_10", 10),
    ("season", None),
)

CHANCE_GENERATION_WEIGHTS: dict[str, float] = {
    "shots_on_target_for": 0.40,
    "shots_inside_box_for": 0.30,
    "shots_total_for": 0.20,
    "corners_for": 0.10,
}

DEFENSIVE_PROCESS_WEIGHTS: dict[str, float] = {
    "shots_on_target_against": 0.45,
    "shots_inside_box_against": 0.35,
    "shots_total_against": 0.20,
}

CONTROL_WEIGHTS: dict[str, float] = {
    "possession_pct": 0.50,
    "pass_accuracy_pct": 0.30,
    "pass_share": 0.20,
}

FINISHING_WEIGHTS: dict[str, float] = {
    "goals_per_shot": 0.55,
    "goals_per_shot_on_target": 0.45,
}

RESULTS_WEIGHTS: dict[str, float] = {
    "points_per_match": 0.60,
    "goal_difference_per_match": 0.40,
}

PROCESS_WEIGHTS: dict[str, float] = {
    "chance_generation": 0.40,
    "defense": 0.35,
    "control": 0.25,
}

ATTACK_WEIGHTS: dict[str, float] = {
    "chance_generation": 0.70,
    "finishing_proxy": 0.30,
}

OVERALL_WEIGHTS: dict[str, float] = {
    "process": 0.65,
    "results": 0.35,
}

LOWER_IS_BETTER = frozenset(
    {
        "goals_against",
        "shots_total_against",
        "shots_on_target_against",
        "shots_inside_box_against",
    }
)

PROCESS_COVERAGE_METRICS: tuple[str, ...] = (
    "shots_total_for",
    "shots_on_target_for",
    "shots_inside_box_for",
    "corners_for",
    "shots_total_against",
    "shots_on_target_against",
    "shots_inside_box_against",
    "possession_pct",
    "pass_accuracy_pct",
    "pass_share",
)

FORM_HALF_LIFE_MATCHES = 3.0
FINISHING_PRIOR_SHOTS = 20.0
FINISHING_PRIOR_SHOTS_ON_TARGET = 8.0

ELO_INITIAL_RATING = 1500.0
ELO_K_FACTOR = 20.0
ELO_HOME_ADVANTAGE = 60.0
