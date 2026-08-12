"""Versioned V1 player analytics configuration."""

from __future__ import annotations

WINDOWS: tuple[tuple[str, int | None], ...] = (
    ("last_3", 3),
    ("last_5", 5),
    ("last_10", 10),
    ("season", None),
)

ROLE_ALIASES: dict[str, str] = {
    "G": "goalkeeper",
    "GK": "goalkeeper",
    "GOALKEEPER": "goalkeeper",
    "D": "defender",
    "DEF": "defender",
    "DEFENDER": "defender",
    "M": "midfielder",
    "MID": "midfielder",
    "MIDFIELDER": "midfielder",
    "F": "forward",
    "FW": "forward",
    "FORWARD": "forward",
}

FEATURE_METRICS: tuple[str, ...] = (
    "goals",
    "assists",
    "shots_total",
    "shots_on_target",
    "passes_total",
    "key_passes",
    "tackles",
    "blocks",
    "interceptions",
    "dribbles_successful",
    "duels_won",
    "fouls_drawn",
    "fouls_committed",
    "saves",
)

DEFENSIVE_CONTEXT_METRICS = frozenset({"tackles", "blocks", "interceptions"})

ROLE_SCORE_WEIGHTS: dict[str, tuple[tuple[str, float, int], ...]] = {
    "goalkeeper": (("saves", 1.00, 1),),
    "defender": (
        ("tackles", 0.22, 1),
        ("interceptions", 0.22, 1),
        ("blocks", 0.14, 1),
        ("duels_won", 0.22, 1),
        ("key_passes", 0.08, 1),
        ("dribbles_successful", 0.06, 1),
        ("fouls_committed", 0.06, -1),
    ),
    "midfielder": (
        ("key_passes", 0.20, 1),
        ("assists", 0.15, 1),
        ("dribbles_successful", 0.15, 1),
        ("tackles", 0.14, 1),
        ("interceptions", 0.14, 1),
        ("duels_won", 0.10, 1),
        ("goals", 0.07, 1),
        ("fouls_drawn", 0.05, 1),
    ),
    "forward": (
        ("goals", 0.30, 1),
        ("shots_on_target", 0.20, 1),
        ("shots_total", 0.10, 1),
        ("assists", 0.15, 1),
        ("key_passes", 0.10, 1),
        ("dribbles_successful", 0.10, 1),
        ("fouls_drawn", 0.05, 1),
    ),
}

DIMENSION_METRICS: dict[str, tuple[tuple[str, int], ...]] = {
    "scoring": (
        ("goals", 1),
        ("shots_on_target", 1),
        ("shots_total", 1),
    ),
    "creation": (
        ("assists", 1),
        ("key_passes", 1),
    ),
    "carrying": (
        ("dribbles_successful", 1),
        ("fouls_drawn", 1),
    ),
    "defending": (
        ("tackles", 1),
        ("interceptions", 1),
        ("blocks", 1),
        ("duels_won", 1),
        ("fouls_committed", -1),
    ),
    "goalkeeping": (("saves", 1),),
}

ROLE_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "goalkeeper": ("goalkeeping",),
    "defender": ("defending", "creation", "carrying"),
    "midfielder": ("scoring", "creation", "carrying", "defending"),
    "forward": ("scoring", "creation", "carrying"),
}
