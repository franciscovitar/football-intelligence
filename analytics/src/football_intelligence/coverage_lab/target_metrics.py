"""Provider-independent target metric catalog for the Zero-Cost Coverage Lab.

Block 16 changed the *source* of this catalog: it used to be derived purely
from `dataclasses.fields()` on the statistical DTOs (`normalization.models`)
plus a small hand-maintained `advanced.*` namespace. It is now sourced from
`metric_catalog.METRIC_CATALOG_V2` -- the full declarative product
specification (the complete versioned registry across the whole product, not just
what today's normalization DTOs happen to carry). This is the whole point of
Block 16: the target catalog grows to represent the full product Football
Intelligence wants, never shrinking to fit what a free provider currently
offers.

The original metrics keep their names, but the requirement identity is the
catalog's full `(metric_name, granularity)` pair.  All nine catalog grains
remain distinct here; provider support at one grain never satisfies another
grain by accident. `_domain_for` maps
`metric_catalog`'s 21 categories down onto this module's existing 6-value
`MetricDomain`, reproducing the original per-DTO domain assignment exactly
(e.g. `TeamLineupRecord` fields stayed `tactical`, `advanced.xg` stayed
`advanced`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2
from football_intelligence.metric_catalog.types import MetricDefinition
from football_intelligence.metric_catalog.types import MetricGranularity as CatalogGranularity

MetricGranularity = CatalogGranularity
MetricDomain = Literal["match", "team_stats", "tactical", "appearance", "player_stats", "advanced"]
MetricImportance = Literal["critical", "standard", "advanced"]

CATALOG_VERSION = "target-metric-catalog-v2"

# A deliberately small set of metrics the product treats as critical for a
# *current* competition -- used only for "missing critical current metrics"
# reporting, never to hide or drop any other metric from the catalog.
CRITICAL_METRIC_NAMES = frozenset(
    {
        "home_score",
        "away_score",
        "status",
        "goals",
        "assists",
        "shots_total",
        "shots_on_target",
        "minutes",
        "formation",
    }
)


@dataclass(frozen=True, slots=True)
class TargetMetric:
    metric_name: str
    granularity: MetricGranularity
    domain: MetricDomain
    semantic_version: str
    importance: MetricImportance = "standard"


# Metrics whose (key, granularity) identity must resolve to the original
# per-DTO domain, reproduced by construction below rather than duplicated as
# a lookup table:
#   - MatchRecord fields (granularity "match") -> "match"
#   - PlayerAppearanceRecord fields (granularity "player_appearance") -> "appearance"
#   - TeamLineupRecord fields (formation, coach_name) -> "tactical"
#   - the expected_output family (advanced.xg and its siblings) -> "advanced"
#   - every other team-scoped metric -> "team_stats" (TeamMatchStatsRecord)
#   - everything else (player-scoped) -> "player_stats" (PlayerMatchStatsRecord)
_TACTICAL_KEYS = frozenset({"formation", "coach_name"})


def _domain_for(metric: MetricDefinition) -> MetricDomain:
    if metric.granularity == "match":
        return "match"
    if metric.granularity == "player_appearance":
        return "appearance"
    if metric.category == "expected_output":
        return "advanced"
    if metric.category == "team_misc" and metric.key in _TACTICAL_KEYS:
        return "tactical"
    if metric.granularity in ("team", "team_match"):
        return "team_stats"
    return "player_stats"


def _importance_for(metric_name: str) -> MetricImportance:
    return "critical" if metric_name in CRITICAL_METRIC_NAMES else "standard"


def build_target_metric_catalog() -> tuple[TargetMetric, ...]:
    return tuple(
        TargetMetric(
            metric_name=metric.key,
            granularity=metric.granularity,
            domain=_domain_for(metric),
            semantic_version=CATALOG_VERSION,
            importance=_importance_for(metric.key),
        )
        for metric in METRIC_CATALOG_V2
    )


# entity_type -> granularity is ambiguous for "player" alone (it could mean
# player_appearance or player_match), and the same bare metric_name can exist
# at two different granularities with different semantics (e.g. "shots_total"
# at both "team" and "player_match"). This index -- (entity_type, metric_name)
# -> granularity -- is derived directly from the catalog so it can never drift,
# and lets provider probes correctly attribute an observation to its real
# target-catalog identity instead of guessing from entity_type alone.
def build_metric_granularity_index() -> dict[tuple[str, str], MetricGranularity]:
    index: dict[tuple[str, str], MetricGranularity] = {}
    for metric in build_target_metric_catalog():
        entity_type = _ENTITY_TYPE_BY_GRANULARITY[metric.granularity]
        index[(entity_type, metric.metric_name)] = metric.granularity
    return index


_ENTITY_TYPE_BY_GRANULARITY: dict[MetricGranularity, str] = {
    "competition": "competition",
    "team": "team",
    "team_match": "team",
    "match": "match",
    "player_appearance": "player",
    "player_match": "player",
    "player_season": "player",
    "goalkeeper_match": "goalkeeper",
    "goalkeeper_season": "goalkeeper",
}
