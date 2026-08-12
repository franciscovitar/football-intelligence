"""Hard invariant checks for Player/Team Analytics weight configuration (Block 12 B1).

Any violation here is a HARD FAIL: it means the shipped scoring config is
internally inconsistent (weights that do not sum to 1, a metric reference
that does not exist, a direction outside +/-1). This never adjusts the
config; it only reports a contract violation.
"""

from __future__ import annotations

import math

from football_intelligence.player_analytics import config as player_config
from football_intelligence.team_analytics import config as team_config

_EPSILON = 1e-6

_TEAM_WEIGHT_GROUPS: tuple[tuple[str, dict[str, float]], ...] = (
    ("CHANCE_GENERATION_WEIGHTS", team_config.CHANCE_GENERATION_WEIGHTS),
    ("DEFENSIVE_PROCESS_WEIGHTS", team_config.DEFENSIVE_PROCESS_WEIGHTS),
    ("CONTROL_WEIGHTS", team_config.CONTROL_WEIGHTS),
    ("FINISHING_WEIGHTS", team_config.FINISHING_WEIGHTS),
    ("RESULTS_WEIGHTS", team_config.RESULTS_WEIGHTS),
    ("PROCESS_WEIGHTS", team_config.PROCESS_WEIGHTS),
    ("ATTACK_WEIGHTS", team_config.ATTACK_WEIGHTS),
    ("OVERALL_WEIGHTS", team_config.OVERALL_WEIGHTS),
)


def check_player_analytics_config() -> list[str]:
    violations: list[str] = []
    metrics = set(player_config.FEATURE_METRICS)

    for role, weights in player_config.ROLE_SCORE_WEIGHTS.items():
        total = sum(weight for _, weight, _ in weights)
        if abs(total - 1.0) > _EPSILON:
            violations.append(f"player role '{role}': weights sum to {total}, expected 1.0")
        for metric_name, weight, direction in weights:
            if weight <= 0 or not math.isfinite(weight):
                violations.append(
                    f"player role '{role}': weight for '{metric_name}' must be positive, "
                    f"got {weight}"
                )
            if direction not in (1, -1):
                violations.append(
                    f"player role '{role}': direction for '{metric_name}' must be +1/-1, "
                    f"got {direction}"
                )
            if metric_name not in metrics:
                violations.append(
                    f"player role '{role}': references unknown metric '{metric_name}'"
                )

    for dimension, entries in player_config.DIMENSION_METRICS.items():
        for metric_name, direction in entries:
            if metric_name not in metrics:
                violations.append(
                    f"player dimension '{dimension}': references unknown metric '{metric_name}'"
                )
            if direction not in (1, -1):
                violations.append(
                    f"player dimension '{dimension}': direction for '{metric_name}' must be +1/-1, "
                    f"got {direction}"
                )

    dimensions = set(player_config.DIMENSION_METRICS)
    for role, role_dimensions in player_config.ROLE_DIMENSIONS.items():
        for dimension in role_dimensions:
            if dimension not in dimensions:
                violations.append(
                    f"player role '{role}': references unknown dimension '{dimension}'"
                )

    return violations


def check_team_analytics_config() -> list[str]:
    violations: list[str] = []
    for group_name, weights in _TEAM_WEIGHT_GROUPS:
        if not weights:
            violations.append(f"team group '{group_name}': must not be empty")
            continue
        total = sum(weights.values())
        if abs(total - 1.0) > _EPSILON:
            violations.append(f"team group '{group_name}': weights sum to {total}, expected 1.0")
        for key, weight in weights.items():
            if not key.strip():
                violations.append(f"team group '{group_name}': contains a blank metric key")
            if weight <= 0 or not math.isfinite(weight):
                violations.append(
                    f"team group '{group_name}': weight for '{key}' must be positive, got {weight}"
                )

    return violations


def check_config_invariants() -> list[str]:
    return check_player_analytics_config() + check_team_analytics_config()
