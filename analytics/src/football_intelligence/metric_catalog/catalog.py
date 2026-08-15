"""Metric Catalog V2: the assembled, versioned target metric registry.

This is what Football Intelligence wants to eventually measure across the
full statistical product -- independent of what any single free provider
currently supplies. It supersedes the pre-Block-16 approach of deriving
`coverage_lab`'s target metric list purely from `dataclasses.fields()` on
the normalization DTOs: those 48 metrics are still here (same `(key,
granularity)` identity, never renamed), wrapped by ~80 additional metrics
spanning participation, output, expected output, shooting, creation,
passing, progression, dribbling, possession security, defending, duels,
discipline, goalkeeping, team performance/possession/set-pieces/pressing/
transition, and advanced context.

Declaring a metric here never implies a live data source exists for it yet;
`coverage_lab` measures the real provider gap against this catalog (see
`docs/ZERO_COST_COVERAGE.md`). The V2 player/team engines can consume any
numeric analytics-relevant catalog metric present in provider-independent
observations. Missing provider coverage remains explicit evidence, not an
engine ceiling.
"""

from __future__ import annotations

from collections import defaultdict

from football_intelligence.metric_catalog.domains.context import CONTEXT_METRICS
from football_intelligence.metric_catalog.domains.goalkeeping import GOALKEEPING_METRICS
from football_intelligence.metric_catalog.domains.match_and_team import MATCH_AND_TEAM_METRICS
from football_intelligence.metric_catalog.domains.player_core import PLAYER_CORE_METRICS
from football_intelligence.metric_catalog.domains.player_technical import (
    PLAYER_TECHNICAL_METRICS,
)
from football_intelligence.metric_catalog.domains.product_gaps import PRODUCT_GAP_METRICS
from football_intelligence.metric_catalog.types import (
    CATALOG_V2_VERSION,
    MetricCategory,
    MetricDefinition,
    MetricGranularity,
)

__all__ = [
    "CATALOG_V2_VERSION",
    "METRIC_CATALOG_V2",
    "MetricCategory",
    "MetricDefinition",
    "MetricGranularity",
    "catalog_by_granularity",
]

METRIC_CATALOG_V2: tuple[MetricDefinition, ...] = (
    MATCH_AND_TEAM_METRICS
    + PLAYER_CORE_METRICS
    + PLAYER_TECHNICAL_METRICS
    + GOALKEEPING_METRICS
    + CONTEXT_METRICS
    + PRODUCT_GAP_METRICS
)


def _validate_uniqueness(catalog: tuple[MetricDefinition, ...]) -> None:
    """Enforce the (key, granularity) uniqueness invariant at import time.

    `metric_name` alone is not a safe identity (e.g. "shots_total" legitimately
    exists at both `team_match` and `player_match` granularity, meaning
    different things) -- the true identity, matching `coverage_lab`
    convention, is `(key, granularity)`.
    """

    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []
    for metric in catalog:
        identity = (metric.key, metric.granularity)
        if identity in seen:
            duplicates.append(identity)
        seen.add(identity)
    if duplicates:
        message = f"duplicate (key, granularity) pairs in METRIC_CATALOG_V2: {duplicates}"
        raise AssertionError(message)


_validate_uniqueness(METRIC_CATALOG_V2)


def catalog_by_granularity() -> dict[MetricGranularity, tuple[MetricDefinition, ...]]:
    grouped: dict[MetricGranularity, list[MetricDefinition]] = defaultdict(list)
    for metric in METRIC_CATALOG_V2:
        grouped[metric.granularity].append(metric)
    return {granularity: tuple(metrics) for granularity, metrics in grouped.items()}
