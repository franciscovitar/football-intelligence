"""Provider-independent target metric catalog for the Zero-Cost Coverage Lab.

This is what Football Intelligence WANTS, derived from the existing
statistical DTOs (`normalization.models`) rather than a hand-maintained
duplicate list -- so the catalog can never silently drift from the real
schema, and it never shrinks just because a free provider lacks a field.

Advanced metrics (the `advanced.*` namespace) do not yet have a DTO field
-- they are declared explicitly below. Adding one here never requires a
database migration: coverage rows key on `metric_name` as free text.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Literal

from football_intelligence.normalization.models import (
    MatchRecord,
    PlayerAppearanceRecord,
    PlayerMatchStatsRecord,
    TeamLineupRecord,
    TeamMatchStatsRecord,
)

MetricGranularity = Literal["competition", "team", "match", "player_appearance", "player_match"]
MetricDomain = Literal["match", "team_stats", "tactical", "appearance", "player_stats", "advanced"]
MetricImportance = Literal["critical", "standard", "advanced"]

CATALOG_VERSION = "target-metric-catalog-v1"

# Fields that identify/link a record rather than describe a metric value.
_EXCLUDED_FIELDS = frozenset(
    {
        "external_id",
        "match_external_id",
        "team_external_id",
        "player_external_id",
        "home_team_external_id",
        "away_team_external_id",
    }
)

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


# Metrics that do not exist as a field on any current DTO yet. Namespaced so
# they can never collide with a core metric name.
ADVANCED_METRICS: tuple[TargetMetric, ...] = (
    TargetMetric(
        metric_name="advanced.xg",
        granularity="player_match",
        domain="advanced",
        semantic_version=CATALOG_VERSION,
        importance="advanced",
    ),
)


def _fields_from(
    dataclass_type: type,
    *,
    granularity: MetricGranularity,
    domain: MetricDomain,
) -> tuple[TargetMetric, ...]:
    importance: MetricImportance
    metrics: list[TargetMetric] = []
    for field in dataclasses.fields(dataclass_type):
        if field.name in _EXCLUDED_FIELDS:
            continue
        importance = "critical" if field.name in CRITICAL_METRIC_NAMES else "standard"
        metrics.append(
            TargetMetric(
                metric_name=field.name,
                granularity=granularity,
                domain=domain,
                semantic_version=CATALOG_VERSION,
                importance=importance,
            )
        )
    return tuple(metrics)


def build_target_metric_catalog() -> tuple[TargetMetric, ...]:
    catalog: list[TargetMetric] = []
    catalog.extend(_fields_from(MatchRecord, granularity="match", domain="match"))
    catalog.extend(_fields_from(TeamMatchStatsRecord, granularity="team", domain="team_stats"))
    catalog.extend(_fields_from(TeamLineupRecord, granularity="team", domain="tactical"))
    catalog.extend(
        _fields_from(PlayerAppearanceRecord, granularity="player_appearance", domain="appearance")
    )
    catalog.extend(
        _fields_from(PlayerMatchStatsRecord, granularity="player_match", domain="player_stats")
    )
    catalog.extend(ADVANCED_METRICS)
    return tuple(catalog)
