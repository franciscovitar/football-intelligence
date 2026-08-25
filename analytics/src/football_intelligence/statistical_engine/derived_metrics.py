"""Inspectable, deterministic derived-metric registry for statistical V2.

Formulas operate on already aggregated values. A result is emitted only when
every input exists and every denominator is strictly non-zero. Observed values
always win over a formula so a provider can publish an authoritative metric.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

FORMULA_VERSION = "derived-v2.0"

# Exact spatial counts must never be published for a multi-match window when
# even one contributing match is missing. Keep this list metric-specific so
# the promotion does not silently change existing provider semantics.
_COMPLETE_OBSERVATION_REQUIRED_RAW_METRICS = frozenset(
    {"long_passes_accurate", "passes_into_final_third"}
)


@dataclass(frozen=True, slots=True)
class DerivedFormula:
    metric_name: str
    inputs: tuple[str, ...]
    expression: str
    calculate: Callable[[Mapping[str, float]], float | None]
    version: str = FORMULA_VERSION


def _sum(*names: str) -> Callable[[Mapping[str, float]], float]:
    return lambda values: sum(values[name] for name in names)


def _difference(left: str, right: str) -> Callable[[Mapping[str, float]], float]:
    return lambda values: values[left] - values[right]


def _ratio(
    numerator: str, denominator: str, *, multiplier: float = 1.0
) -> Callable[[Mapping[str, float]], float | None]:
    def calculate(values: Mapping[str, float]) -> float | None:
        divisor = values[denominator]
        if divisor == 0:
            return None
        return values[numerator] / divisor * multiplier

    return calculate


DERIVED_FORMULAS: tuple[DerivedFormula, ...] = (
    DerivedFormula(
        "goal_contributions", ("goals", "assists"), "goals + assists", _sum("goals", "assists")
    ),
    DerivedFormula(
        "sub_appearances",
        ("appearances", "starts"),
        "appearances - starts",
        _difference("appearances", "starts"),
    ),
    DerivedFormula(
        "minutes_per_appearance",
        ("minutes", "appearances"),
        "minutes / appearances",
        _ratio("minutes", "appearances"),
    ),
    DerivedFormula(
        "non_penalty_goals",
        ("goals", "penalty_goals"),
        "goals - penalty_goals",
        _difference("goals", "penalty_goals"),
    ),
    DerivedFormula(
        "xg_plus_xa", ("advanced.xg", "xa"), "advanced.xg + xa", _sum("advanced.xg", "xa")
    ),
    DerivedFormula(
        "goals_minus_xg",
        ("goals", "advanced.xg"),
        "goals - advanced.xg",
        _difference("goals", "advanced.xg"),
    ),
    DerivedFormula(
        "non_penalty_goals_minus_npxg",
        ("non_penalty_goals", "npxg"),
        "non_penalty_goals - npxg",
        _difference("non_penalty_goals", "npxg"),
    ),
    DerivedFormula(
        "assists_minus_xa", ("assists", "xa"), "assists - xa", _difference("assists", "xa")
    ),
    DerivedFormula(
        "xa_per90",
        ("xa", "minutes"),
        "90 * xa / minutes",
        _ratio("xa", "minutes", multiplier=90.0),
    ),
    DerivedFormula(
        "shots_on_target_pct",
        ("shots_on_target", "shots_total"),
        "100 * shots_on_target / shots_total",
        _ratio("shots_on_target", "shots_total", multiplier=100.0),
    ),
    DerivedFormula(
        "goals_per_shot",
        ("goals", "shots_total"),
        "goals / shots_total",
        _ratio("goals", "shots_total"),
    ),
    DerivedFormula(
        "goals_per_shot_on_target",
        ("goals", "shots_on_target"),
        "goals / shots_on_target",
        _ratio("goals", "shots_on_target"),
    ),
    DerivedFormula(
        "xg_per_shot",
        ("advanced.xg", "shots_total"),
        "advanced.xg / shots_total",
        _ratio("advanced.xg", "shots_total"),
    ),
    DerivedFormula(
        "pass_completion_pct",
        ("passes_accurate", "passes_total"),
        "100 * passes_accurate / passes_total",
        _ratio("passes_accurate", "passes_total", multiplier=100.0),
    ),
    DerivedFormula(
        "dribble_success_pct",
        ("dribbles_successful", "dribbles_attempted"),
        "100 * dribbles_successful / dribbles_attempted",
        _ratio("dribbles_successful", "dribbles_attempted", multiplier=100.0),
    ),
    DerivedFormula(
        "take_on_success_pct",
        ("take_ons_successful", "take_ons_attempted"),
        "100 * take_ons_successful / take_ons_attempted",
        _ratio("take_ons_successful", "take_ons_attempted", multiplier=100.0),
    ),
    DerivedFormula(
        "tackle_success_pct",
        ("tackles_won", "tackles"),
        "100 * tackles_won / tackles",
        _ratio("tackles_won", "tackles", multiplier=100.0),
    ),
    DerivedFormula(
        "pressure_success_pct",
        ("successful_pressures", "pressures"),
        "100 * successful_pressures / pressures",
        _ratio("successful_pressures", "pressures", multiplier=100.0),
    ),
    DerivedFormula(
        "duel_win_pct",
        ("duels_won", "duels_total"),
        "100 * duels_won / duels_total",
        _ratio("duels_won", "duels_total", multiplier=100.0),
    ),
    DerivedFormula(
        "aerial_duel_win_pct",
        ("aerial_duels_won", "aerial_duels"),
        "100 * aerial_duels_won / aerial_duels",
        _ratio("aerial_duels_won", "aerial_duels", multiplier=100.0),
    ),
    DerivedFormula(
        "possession_losses",
        ("dispossessed", "miscontrols"),
        "dispossessed + miscontrols",
        _sum("dispossessed", "miscontrols"),
    ),
    DerivedFormula(
        "save_pct",
        ("saves", "shots_on_target_faced"),
        "100 * saves / shots_on_target_faced",
        _ratio("saves", "shots_on_target_faced", multiplier=100.0),
    ),
    DerivedFormula(
        "goals_prevented",
        ("psxg", "goals_conceded"),
        "psxg - goals_conceded",
        _difference("psxg", "goals_conceded"),
    ),
    DerivedFormula(
        "progressive_actions",
        ("progressive_passes", "progressive_carries"),
        "progressive_passes + progressive_carries",
        _sum("progressive_passes", "progressive_carries"),
    ),
    DerivedFormula(
        "ball_progressions",
        ("progressive_passes", "progressive_carries"),
        "progressive_passes + progressive_carries",
        _sum("progressive_passes", "progressive_carries"),
    ),
    # Team aliases use the team catalog's plain xG key.
    DerivedFormula(
        "team.pass_accuracy_pct",
        ("passes_accurate", "passes_total"),
        "100 * passes_accurate / passes_total",
        _ratio("passes_accurate", "passes_total", multiplier=100.0),
    ),
    DerivedFormula(
        "team.xg_per_shot", ("xg", "shots_total"), "xg / shots_total", _ratio("xg", "shots_total")
    ),
    DerivedFormula(
        "team.xga_per_shot",
        ("xga", "shots_allowed"),
        "xga / shots_allowed",
        _ratio("xga", "shots_allowed"),
    ),
)


def derive_available_metrics(
    values: Mapping[str, float],
    *,
    team: bool = False,
    observed_counts: Mapping[str, int] | None = None,
    required_observations: int | None = None,
) -> tuple[dict[str, float], dict[str, str]]:
    """Return all deterministically derivable values and their formula versions."""

    available = dict(values)
    versions: dict[str, str] = {}
    counts = dict(observed_counts or {})
    if observed_counts is not None and required_observations is not None:
        for metric_name in _COMPLETE_OBSERVATION_REQUIRED_RAW_METRICS:
            if metric_name in available and counts.get(metric_name) != required_observations:
                available.pop(metric_name)
    for formula in DERIVED_FORMULAS:
        is_team_formula = formula.metric_name.startswith("team.")
        if is_team_formula != team:
            continue
        output_name = formula.metric_name.removeprefix("team.")
        if output_name in available or not all(name in available for name in formula.inputs):
            continue
        if (
            observed_counts is not None
            and required_observations is not None
            and any(counts.get(name) != required_observations for name in formula.inputs)
        ):
            continue
        result = formula.calculate(available)
        if result is None:
            continue
        available[output_name] = result
        versions[output_name] = formula.version
        if observed_counts is not None and required_observations is not None:
            counts[output_name] = required_observations

    # xGOT is an accepted workload input when PSxG is unavailable.
    if (
        not team
        and "goals_prevented" not in available
        and "xg_on_target_faced" in available
        and "goals_conceded" in available
        and (
            observed_counts is None
            or required_observations is None
            or (
                counts.get("xg_on_target_faced") == required_observations
                and counts.get("goals_conceded") == required_observations
            )
        )
    ):
        available["goals_prevented"] = available["xg_on_target_faced"] - available["goals_conceded"]
        versions["goals_prevented"] = FORMULA_VERSION
    return available, versions
