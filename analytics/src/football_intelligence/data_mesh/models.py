"""Provider-independent normalized observation model (Block 13).

A `NormalizedObservation` is one source's fact claim about one entity/metric.
A source that does not report a metric simply produces no observation for it
-- missing is represented by absence, never by a synthetic zero or `None`
value. Zero is only ever a real, explicitly reported zero.

**Metric granularity (Block 20D.2)**: the Metric Catalog V2 explicitly
permits the same `metric_name` to exist at more than one granularity (e.g.
`saves` at both `player_match` and `goalkeeper_match`) -- both share
`entity_type == "player"` and the same match-scoped provider id shape, so
`entity_type`/`entity_source_id` alone cannot disambiguate them. A certified
V2 adapter already knows the exact `(catalog_key, catalog_granularity)`
identity it is emitting at every call site (it is the same identity its own
`adapter_safe_mappings()` allowlist is built from) -- `metric_granularity`
lets it preserve that knowledge on the observation itself instead of forcing
a later stage to reconstruct or guess it. Legacy (pre-Metric-Catalog-V2)
adapters may leave it `None`; nothing about their behavior changes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football_intelligence.metric_catalog.types import MetricGranularity

SourceType = Literal[
    "objective_structured",
    "objective_official",
    "objective_web",
    "qualitative_expert",
    "qualitative_fan",
]

OBJECTIVE_SOURCE_TYPES: frozenset[SourceType] = frozenset(
    {"objective_structured", "objective_official", "objective_web"}
)

QUALITATIVE_SOURCE_TYPES: frozenset[SourceType] = frozenset(
    {"qualitative_expert", "qualitative_fan"}
)

EntityType = Literal["competition", "team", "match", "player"]

ObservationValue = str | int | float | bool


@dataclass(frozen=True, slots=True)
class NormalizedObservation:
    source_code: str
    source_type: SourceType
    entity_type: EntityType
    entity_source_id: str
    entity_identity_hints: Mapping[str, str]
    metric_name: str
    value: ObservationValue
    observed_at: datetime
    source_timestamp: datetime | None
    source_reference: str
    ingestion_run_id: int | None
    semantic_version: str
    # None for legacy (pre-Metric-Catalog-V2) adapters. A certified V2
    # adapter must always set this explicitly -- see the module docstring.
    metric_granularity: MetricGranularity | None = None


ResolutionStatus = Literal["resolved", "unresolved"]


@dataclass(frozen=True, slots=True)
class EntityResolution:
    status: ResolutionStatus
    logical_key: str | None
    entity_type: EntityType
    confidence: float
    reason: str


ReconciliationStatus = Literal["agreed", "single_source", "conflict", "unresolved"]


@dataclass(frozen=True, slots=True)
class ReconciliationDecision:
    logical_entity_key: str
    entity_type: EntityType
    metric_name: str
    candidate_value: ObservationValue | None
    status: ReconciliationStatus
    confidence: float
    winning_source_code: str | None
    participating_sources: tuple[str, ...]
    source_count: int
    evidence: Mapping[str, object]
    model_version: str
    calculated_at: datetime
