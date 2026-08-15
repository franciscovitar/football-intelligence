"""Shared types for the Metric Catalog V2 registry.

Split out from `catalog.py` so the domain modules under `domains/` can import
the shared `MetricDefinition` shape without creating a circular import with
the module that assembles them into the final registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CATALOG_V2_VERSION = "metric-catalog-v2.0"

# Closed, small set of comparison/storage grains a metric can be measured at.
# "team_match" is a team's own stats within one specific match (distinct from
# "team", which is season/team identity context rather than one team's facts
# within a specific match). Coverage Lab preserves this distinction exactly.
# "player_season" / "goalkeeper_season" are season-aggregate grains that do
# not decompose into individual match observations, distinct from the match-level "player_match" /
# "goalkeeper_match" grains.
MetricGranularity = Literal[
    "competition",
    "team",
    "match",
    "team_match",
    "player_appearance",
    "player_match",
    "player_season",
    "goalkeeper_match",
    "goalkeeper_season",
]

# Closed, small set of statistical families. "match_context" and "team_misc"
# are additive beyond the initial product-spec list to give match-identity
# facts (kickoff time, status, venue) and team-identity/misc facts
# (formation, coach, lineup stability) an honest home instead of forcing them
# into an unrelated family.
MetricCategory = Literal[
    "match_context",
    "participation",
    "output",
    "expected_output",
    "shooting",
    "creation",
    "passing",
    "progression",
    "dribbling",
    "possession_security",
    "defending",
    "duels",
    "discipline",
    "goalkeeping",
    "team_performance",
    "team_possession",
    "team_set_pieces",
    "team_pressing",
    "team_transition",
    "team_misc",
    "advanced_context",
]

MetricKind = Literal["raw", "derived"]
MetricDirection = Literal["higher_better", "lower_better", "contextual"]


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    key: str
    display_name: str
    granularity: MetricGranularity
    category: MetricCategory
    # Free string by design (not a closed Literal): "count" | "percentage" |
    # "per90" | "rating" | "distance_m" | "label" | "boolean" | "minutes" |
    # similar short unit tags. Kept open so a new unit never requires
    # touching this shared type file.
    unit: str
    kind: MetricKind
    per90_eligible: bool
    percentile_eligible: bool
    direction: MetricDirection
    min_sample_policy: str
    semantic_version: str
    notes: str = ""
