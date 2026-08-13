"""Deterministic reconciliation engine for the multi-source data mesh (Block 13).

Only objective observations participate; qualitative evidence is rejected
defensively here even if a caller passes it by mistake -- that lane belongs
to Perception Intelligence and must never touch objective statistics.

Conflicting objective values are never silently overwritten or averaged. A
metric-specific priority rule may name an authoritative source for display,
but the decision status stays "conflict" and every disagreeing value remains
in the evidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from football_intelligence.data_mesh.models import (
    OBJECTIVE_SOURCE_TYPES,
    EntityType,
    NormalizedObservation,
    ObservationValue,
    ReconciliationDecision,
)

MODEL_VERSION = "data-mesh-reconciliation-v0.1"

SINGLE_SOURCE_CONFIDENCE = 0.35
CONFLICT_CONFIDENCE = 0.20
AGREEMENT_BASE_CONFIDENCE = 0.60
AGREEMENT_STEP_CONFIDENCE = 0.10
AGREEMENT_MAX_CONFIDENCE = 0.95


def reconcile_metric(
    observations: Sequence[NormalizedObservation],
    *,
    logical_entity_key: str,
    entity_type: EntityType,
    metric_name: str,
    source_priority: Mapping[str, tuple[str, ...]] | None = None,
    calculated_at: datetime | None = None,
) -> ReconciliationDecision:
    now = calculated_at or datetime.now(UTC)
    objective = [item for item in observations if item.source_type in OBJECTIVE_SOURCE_TYPES]

    if not objective:
        return ReconciliationDecision(
            logical_entity_key=logical_entity_key,
            entity_type=entity_type,
            metric_name=metric_name,
            candidate_value=None,
            status="unresolved",
            confidence=0.0,
            winning_source_code=None,
            participating_sources=(),
            source_count=0,
            evidence={"reason": "no objective observations"},
            model_version=MODEL_VERSION,
            calculated_at=now,
        )

    # Keep the most recently observed value per source; a source should not
    # count twice just because it was fetched more than once in a run.
    latest_by_source: dict[str, NormalizedObservation] = {}
    for item in sorted(objective, key=lambda obs: obs.observed_at):
        latest_by_source[item.source_code] = item

    values_by_source: dict[str, ObservationValue] = {
        code: item.value for code, item in latest_by_source.items()
    }
    participating_sources = tuple(sorted(latest_by_source))
    source_count = len(participating_sources)
    distinct_values = {_comparable(value) for value in values_by_source.values()}

    if source_count == 1:
        only_source = participating_sources[0]
        return ReconciliationDecision(
            logical_entity_key=logical_entity_key,
            entity_type=entity_type,
            metric_name=metric_name,
            candidate_value=values_by_source[only_source],
            status="single_source",
            confidence=SINGLE_SOURCE_CONFIDENCE,
            winning_source_code=only_source,
            participating_sources=participating_sources,
            source_count=source_count,
            evidence={"values_by_source": values_by_source},
            model_version=MODEL_VERSION,
            calculated_at=now,
        )

    if len(distinct_values) == 1:
        confidence = min(
            AGREEMENT_MAX_CONFIDENCE,
            AGREEMENT_BASE_CONFIDENCE + AGREEMENT_STEP_CONFIDENCE * (source_count - 1),
        )
        agreed_value = values_by_source[participating_sources[0]]
        return ReconciliationDecision(
            logical_entity_key=logical_entity_key,
            entity_type=entity_type,
            metric_name=metric_name,
            candidate_value=agreed_value,
            status="agreed",
            confidence=confidence,
            winning_source_code=None,
            participating_sources=participating_sources,
            source_count=source_count,
            evidence={"values_by_source": values_by_source},
            model_version=MODEL_VERSION,
            calculated_at=now,
        )

    priority_order = (source_priority or {}).get(metric_name, ())
    candidate_value: ObservationValue | None = None
    winning_source: str | None = None
    for candidate_source in priority_order:
        if candidate_source in values_by_source:
            candidate_value = values_by_source[candidate_source]
            winning_source = candidate_source
            break

    return ReconciliationDecision(
        logical_entity_key=logical_entity_key,
        entity_type=entity_type,
        metric_name=metric_name,
        candidate_value=candidate_value,
        status="conflict",
        confidence=CONFLICT_CONFIDENCE,
        winning_source_code=winning_source,
        participating_sources=participating_sources,
        source_count=source_count,
        evidence={
            "values_by_source": values_by_source,
            "priority_rule_applied": winning_source is not None,
        },
        model_version=MODEL_VERSION,
        calculated_at=now,
    )


def _comparable(value: ObservationValue) -> ObservationValue:
    """Avoid false conflicts between equal numbers of different Python types (2 vs 2.0)."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return float(value)
    return value
