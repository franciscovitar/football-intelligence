"""Fine-grained position-family tokens and score weight profiles.

Extends `player_analytics.config`'s coarse 4-way role
(`goalkeeper`/`defender`/`midfielder`/`forward`) with a finer position-family
grain, the same way real football analysis distinguishes a centre-back from
a full-back, or a winger from a central midfielder -- without claiming
precision the provider data does not support: `classify_position_family`
falls back to the coarse broad role whenever a `listed_position` token isn't
one of the fine tokens below, so nothing V1 could already classify becomes
unclassified in V2.

Profiles describe the intended product, including catalog metrics that are
not available from today's providers. The scoring engine reports the exact
weight coverage and never renormalizes a partial profile to 100% evidence.
"""

from __future__ import annotations

from typing import Literal

PositionFamily = Literal[
    "goalkeeper",
    "centre_back",
    "fullback_wingback",
    "defensive_midfielder",
    "central_midfielder",
    "attacking_midfielder",
    "winger",
    "forward",
]

# listed_position token (upper-cased, stripped) -> fine position family.
# Deliberately small and explicit -- an unrecognized token is never guessed,
# it falls back to `player_analytics.config.ROLE_ALIASES`'s coarse role.
FINE_POSITION_ALIASES: dict[str, PositionFamily] = {
    "GK": "goalkeeper",
    "CB": "centre_back",
    "RB": "fullback_wingback",
    "LB": "fullback_wingback",
    "RWB": "fullback_wingback",
    "LWB": "fullback_wingback",
    "CDM": "defensive_midfielder",
    "DM": "defensive_midfielder",
    "CM": "central_midfielder",
    "CAM": "attacking_midfielder",
    "AM": "attacking_midfielder",
    "RW": "winger",
    "LW": "winger",
    "RM": "winger",
    "LM": "winger",
    "ST": "forward",
    "CF": "forward",
    "FW": "forward",
}

# (metric_name, weight, direction) tuples, in the same shape as
# `player_analytics.config.ROLE_SCORE_WEIGHTS`. The base profiles use today's
# computed features; the ideal additions below intentionally retain metrics
# that are absent until a permitted rich source can provide them.
#
# Keyed by plain `str`, not `PositionFamily`: `classify_position_family`
# returns a broader `str | None` (it can also return one of the coarse
# broad-role fallback strings, e.g. "defender", which is intentionally not a
# fine family / not a key here), so callers look this table up with a plain
# string and get `None` back for any non-fine-family key -- never a type
# mismatch on the lookup.
_BASE_POSITION_FAMILY_SCORE_WEIGHTS: dict[str, tuple[tuple[str, float, int], ...]] = {
    "goalkeeper": (("saves", 1.00, 1),),
    "centre_back": (
        ("tackles", 0.22, 1),
        ("interceptions", 0.24, 1),
        ("blocks", 0.16, 1),
        ("duels_won", 0.24, 1),
        ("key_passes", 0.06, 1),
        ("fouls_committed", 0.08, -1),
    ),
    "fullback_wingback": (
        ("tackles", 0.16, 1),
        ("interceptions", 0.16, 1),
        ("duels_won", 0.14, 1),
        ("key_passes", 0.20, 1),
        ("dribbles_successful", 0.18, 1),
        ("assists", 0.10, 1),
        ("fouls_committed", 0.06, -1),
    ),
    "defensive_midfielder": (
        ("tackles", 0.24, 1),
        ("interceptions", 0.24, 1),
        ("duels_won", 0.20, 1),
        ("blocks", 0.10, 1),
        ("key_passes", 0.12, 1),
        ("fouls_committed", 0.10, -1),
    ),
    "central_midfielder": (
        ("key_passes", 0.20, 1),
        ("assists", 0.15, 1),
        ("dribbles_successful", 0.13, 1),
        ("tackles", 0.14, 1),
        ("interceptions", 0.14, 1),
        ("duels_won", 0.10, 1),
        ("goals", 0.09, 1),
        ("fouls_drawn", 0.05, 1),
    ),
    "attacking_midfielder": (
        ("key_passes", 0.26, 1),
        ("assists", 0.20, 1),
        ("goals", 0.16, 1),
        ("dribbles_successful", 0.18, 1),
        ("shots_on_target", 0.10, 1),
        ("tackles", 0.06, 1),
        ("fouls_drawn", 0.04, 1),
    ),
    "winger": (
        ("dribbles_successful", 0.22, 1),
        ("key_passes", 0.20, 1),
        ("assists", 0.16, 1),
        ("goals", 0.16, 1),
        ("shots_on_target", 0.14, 1),
        ("fouls_drawn", 0.08, 1),
        ("tackles", 0.04, 1),
    ),
    "forward": (
        ("goals", 0.32, 1),
        ("shots_on_target", 0.20, 1),
        ("shots_total", 0.10, 1),
        ("assists", 0.14, 1),
        ("key_passes", 0.10, 1),
        ("dribbles_successful", 0.09, 1),
        ("fouls_drawn", 0.05, 1),
    ),
}

# Missing metrics remain in the intended denominator. Each addition is a
# catalog metric and is never fabricated when the source lacks it.
_IDEAL_PROFILE_ADDITIONS: dict[str, tuple[tuple[str, float, int], ...]] = {
    "goalkeeper": (
        ("shots_on_target_faced", 0.20, -1),
        ("xg_on_target_faced", 0.15, -1),
        ("crosses_stopped", 0.10, 1),
        ("sweeper_actions", 0.10, 1),
        ("distribution_accuracy_pct", 0.05, 1),
    ),
    "centre_back": (
        ("aerial_duels_won", 0.14, 1),
        ("pass_blocks", 0.08, 1),
        ("progressive_pass_distance", 0.10, 1),
        ("errors_leading_to_shot", 0.08, -1),
    ),
    "fullback_wingback": (
        ("progressive_carries", 0.10, 1),
        ("passes_into_final_third", 0.10, 1),
        ("crosses", 0.10, 1),
        ("touches_final_third", 0.10, 1),
    ),
    "defensive_midfielder": (
        ("successful_pressures", 0.10, 1),
        ("progressive_passes", 0.10, 1),
        ("passes_under_pressure", 0.08, 1),
        ("turnovers", 0.12, -1),
    ),
    "central_midfielder": (
        ("progressive_passes", 0.10, 1),
        ("passes_into_final_third", 0.10, 1),
        ("progressive_carries", 0.08, 1),
        ("shot_creating_actions", 0.12, 1),
    ),
    "attacking_midfielder": (
        ("xa", 0.10, 1),
        ("shot_creating_actions", 0.10, 1),
        ("touches_in_box", 0.08, 1),
        ("expected_threat_created", 0.12, 1),
    ),
    "winger": (
        ("progressive_carries", 0.10, 1),
        ("take_on_success_pct", 0.10, 1),
        ("touches_in_box", 0.08, 1),
        ("expected_assists_open_play", 0.12, 1),
    ),
    "forward": (
        ("npxg", 0.12, 1),
        ("touches_in_box", 0.08, 1),
        ("big_chances", 0.08, 1),
        ("goals_per_shot", 0.12, 1),
    ),
}

POSITION_FAMILY_SCORE_WEIGHTS: dict[str, tuple[tuple[str, float, int], ...]] = {
    family: weights + _IDEAL_PROFILE_ADDITIONS.get(family, ())
    for family, weights in _BASE_POSITION_FAMILY_SCORE_WEIGHTS.items()
}

POSITION_FAMILY_CORE_METRICS: dict[str, frozenset[str]] = {
    "goalkeeper": frozenset({"saves"}),
    "centre_back": frozenset({"tackles", "interceptions", "duels_won"}),
    "fullback_wingback": frozenset({"tackles", "key_passes", "dribbles_successful"}),
    "defensive_midfielder": frozenset({"tackles", "interceptions", "duels_won"}),
    "central_midfielder": frozenset({"key_passes", "tackles"}),
    "attacking_midfielder": frozenset({"key_passes", "goals"}),
    "winger": frozenset({"dribbles_successful", "key_passes"}),
    "forward": frozenset({"goals", "shots_total"}),
}

MIN_PROFILE_EVIDENCE_COVERAGE = 0.60
