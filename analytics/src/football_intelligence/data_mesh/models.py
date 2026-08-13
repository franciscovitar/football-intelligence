"""Provider-independent normalized observation model (Block 13).

A `NormalizedObservation` is one source's fact claim about one entity/metric.
A source that does not report a metric simply produces no observation for it
-- missing is represented by absence, never by a synthetic zero or `None`
value. Zero is only ever a real, explicitly reported zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

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
