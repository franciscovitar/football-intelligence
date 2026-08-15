"""Metric Catalog V2: the declarative statistical product specification.

This package is a static, versioned catalog of every metric Football
Intelligence wants to eventually measure -- independent of what any single
free provider currently supplies. It supersedes the DTO-derived 48-metric
catalog `coverage_lab.target_metrics` used before Block 16 as the *source*
of the product's target metric list; `coverage_lab.target_metrics` now
builds its `TargetMetric` rows from this registry instead of deriving them
purely from `dataclasses.fields()` on the normalization DTOs.
"""

from __future__ import annotations

from football_intelligence.metric_catalog.catalog import (
    CATALOG_V2_VERSION,
    METRIC_CATALOG_V2,
    MetricCategory,
    MetricDefinition,
    MetricGranularity,
    catalog_by_granularity,
)

__all__ = [
    "CATALOG_V2_VERSION",
    "METRIC_CATALOG_V2",
    "MetricCategory",
    "MetricDefinition",
    "MetricGranularity",
    "catalog_by_granularity",
]
