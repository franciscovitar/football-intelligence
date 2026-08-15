"""Provider-independent target metric catalog for the Zero-Cost Coverage Lab.

Block 16 changed the *source* of this catalog: it used to be derived purely
from `dataclasses.fields()` on the statistical DTOs (`normalization.models`)
plus a small hand-maintained `advanced.*` namespace. It is now sourced from
`metric_catalog.METRIC_CATALOG_V2` -- the full declarative product
specification (~130 metrics across the whole statistical product, not just
what today's normalization DTOs happen to carry). This is the whole point of
Block 16: the target catalog grows to represent the full product Football
Intelligence wants, never shrinking to fit what a free provider currently
offers.

The original 48 metrics this module used to derive directly from the DTOs
keep the exact same `(metric_name, granularity)` identity here -- never
renamed -- so existing coverage rows, `provider_capabilities.py` manifests,
and `coverage_lab` tests all keep working unchanged. `metric_catalog`'s
granularity space is richer (9 grains, e.g. `team_match`/`player_season`/
`goalkeeper_match`) than this module's narrower, pre-existing 5-grain
`MetricGranularity`; `_collapse_granularity` maps the richer space down onto
this module's existing grains (`team_match` -> `team`, `player_season` /
`goalkeeper_match` / `goalkeeper_season` -> `player_match`), exactly
reproducing the original 48's identity. Likewise `_domain_for` maps
`metric_catalog`'s 21 categories down onto this module's existing 6-value
`MetricDomain`, reproducing the original per-DTO domain assignment exactly
(e.g. `TeamLineupRecord` fields stayed `tactical`, `advanced.xg` stayed
`advanced`).

Because the collapse is coarser than `metric_catalog`'s own granularity
space, a small number of distinct `metric_catalog` entries collapse onto the
same `(metric_name, granularity)` pair here (e.g. `saves` at both
`player_match` and `goalkeeper_match` both collapse to `player_match`);
`build_target_metric_catalog` deduplicates deterministically, keeping the
first occurrence in `metric_catalog.METRIC_CATALOG_V2` order, so the
uniqueness invariant `coverage_lab` already relies on holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2
from football_intelligence.metric_catalog.types import MetricDefinition
from football_intelligence.metric_catalog.types import MetricGranularity as CatalogGranularity

MetricGranularity = Literal["competition", "team", "match", "player_appearance", "player_match"]
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


# metric_catalog's 9-grain space collapsed onto this module's original
# 5-grain space. "team_match" collapses to "team" (matching the existing
# convention that every `TeamMatchStatsRecord`/`TeamLineupRecord` field is
# already reported at "team" granularity here, even though it is really
# scoped to one team within one match). "player_season" and the two
# goalkeeper grains collapse to "player_match" as the closest existing
# player-scoped bucket -- there is no dedicated season-aggregate grain in
# this module's pre-existing type, and introducing one would require
# touching `provider_capabilities.py`'s and `engine.py`'s granularity
# handling for no coverage-measurement benefit today (no provider reports
# any of these new metrics yet regardless of grain).
_GRANULARITY_COLLAPSE: dict[CatalogGranularity, MetricGranularity] = {
    "competition": "competition",
    "team": "team",
    "team_match": "team",
    "match": "match",
    "player_appearance": "player_appearance",
    "player_match": "player_match",
    "player_season": "player_match",
    "goalkeeper_match": "player_match",
    "goalkeeper_season": "player_match",
}

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
    catalog: list[TargetMetric] = []
    seen: set[tuple[str, str]] = set()

    for metric in METRIC_CATALOG_V2:
        granularity = _GRANULARITY_COLLAPSE[metric.granularity]
        identity = (metric.key, granularity)
        if identity in seen:
            continue
        seen.add(identity)
        catalog.append(
            TargetMetric(
                metric_name=metric.key,
                granularity=granularity,
                domain=_domain_for(metric),
                semantic_version=CATALOG_VERSION,
                importance=_importance_for(metric.key),
            )
        )
    return tuple(catalog)


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
    "match": "match",
    "player_appearance": "player",
    "player_match": "player",
}
