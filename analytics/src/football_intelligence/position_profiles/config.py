"""Fine-grained position-family tokens and score weight profiles.

Extends `player_analytics.config`'s coarse 4-way role
(`goalkeeper`/`defender`/`midfielder`/`forward`) with a finer position-family
grain, the same way real football analysis distinguishes a centre-back from
a full-back, or a winger from a central midfielder -- without claiming
precision the provider data does not support: `classify_position_family`
falls back to the coarse broad role whenever a `listed_position` token isn't
one of the fine tokens below, so nothing V1 could already classify becomes
unclassified in V2.

Weight profiles only use metrics already wired into scoring today
(`player_analytics.config.FEATURE_METRICS`) -- Metric Catalog V2 declares
many more metrics (crosses, progressive carries, aerial duels, ...) that a
fullback or winger profile would ideally weight, but none of those have a
real per-match observation source yet (`PlayerObservation.stats` cannot
carry them), so they are deliberately not wired into any weight profile.
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
# `player_analytics.config.ROLE_SCORE_WEIGHTS`. Every metric_name here must
# be a member of `player_analytics.config.FEATURE_METRICS` -- there is no
# real per-match observation for anything richer yet.
#
# Keyed by plain `str`, not `PositionFamily`: `classify_position_family`
# returns a broader `str | None` (it can also return one of the coarse
# broad-role fallback strings, e.g. "defender", which is intentionally not a
# fine family / not a key here), so callers look this table up with a plain
# string and get `None` back for any non-fine-family key -- never a type
# mismatch on the lookup.
POSITION_FAMILY_SCORE_WEIGHTS: dict[str, tuple[tuple[str, float, int], ...]] = {
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
