"""Granularity-safe Metric Catalog access for Player Statistical Engine V2."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from football_intelligence.metric_catalog import METRIC_CATALOG_V2, MetricDefinition
from football_intelligence.metric_catalog.types import MetricGranularity
from football_intelligence.player_analytics.models import (
    GoalkeeperSeasonObservation,
    PlayerSeasonObservation,
)

MetricCatalogEntry = tuple[MetricGranularity, MetricDefinition]


def index_catalog_by_identity(
    metrics: Iterable[MetricDefinition],
) -> dict[tuple[MetricGranularity, str], MetricDefinition]:
    """Index definitions by the complete catalog identity, including grain."""

    return {(metric.granularity, metric.key): metric for metric in metrics}


# Metric identity always includes its grain. A plain metric key is never used
# to assemble definitions across multiple grains.
CATALOG_BY_IDENTITY = index_catalog_by_identity(METRIC_CATALOG_V2)


def _entries_at(granularity: MetricGranularity) -> dict[str, MetricCatalogEntry]:
    return {
        key: (grain, definition)
        for (grain, key), definition in CATALOG_BY_IDENTITY.items()
        if grain == granularity
    }


PLAYER_MATCH_CATALOG = _entries_at("player_match")
PLAYER_SEASON_CATALOG = _entries_at("player_season")
GOALKEEPER_MATCH_CATALOG = _entries_at("goalkeeper_match")
GOALKEEPER_SEASON_CATALOG = _entries_at("goalkeeper_season")


def match_catalog_for_role(role: str) -> Mapping[str, MetricCatalogEntry]:
    """Return match-only definitions, with explicit GK-match precedence."""

    if role != "goalkeeper":
        return PLAYER_MATCH_CATALOG
    return {**PLAYER_MATCH_CATALOG, **GOALKEEPER_MATCH_CATALOG}


def season_catalog_for_observation(
    observation: PlayerSeasonObservation | GoalkeeperSeasonObservation,
) -> Mapping[str, MetricCatalogEntry]:
    """Explicit future input path for season aggregates; not a match adapter."""

    if isinstance(observation, GoalkeeperSeasonObservation):
        return GOALKEEPER_SEASON_CATALOG
    if isinstance(observation, PlayerSeasonObservation):
        return PLAYER_SEASON_CATALOG
    raise TypeError("season catalog requires an explicit season observation")
