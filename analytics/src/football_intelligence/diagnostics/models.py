"""Provider-independent data structures for the Diagnostic Rule Engine."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

DiagnosticEntityType = Literal["player", "team"]
DiagnosticSeverity = Literal["info", "notable", "high"]

MODEL_VERSION = "diagnostic-v1.0"


@dataclass(frozen=True, slots=True)
class DiagnosticFinding:
    diagnostic_code: str
    entity_type: DiagnosticEntityType
    entity_id: int
    severity: DiagnosticSeverity
    confidence: float
    supporting_metrics: Mapping[str, float | str | None]
    comparison_group: str
    window: str
    model_version: str
    computed_at: datetime
