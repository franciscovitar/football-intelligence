"""Fine-grained position-family classification and per-family score weights."""

from __future__ import annotations

from football_intelligence.position_profiles.classifier import classify_position_family
from football_intelligence.position_profiles.config import (
    FINE_POSITION_ALIASES,
    MIN_PROFILE_EVIDENCE_COVERAGE,
    POSITION_FAMILY_CORE_METRICS,
    POSITION_FAMILY_SCORE_WEIGHTS,
    PositionFamily,
)

__all__ = [
    "FINE_POSITION_ALIASES",
    "MIN_PROFILE_EVIDENCE_COVERAGE",
    "POSITION_FAMILY_CORE_METRICS",
    "POSITION_FAMILY_SCORE_WEIGHTS",
    "PositionFamily",
    "classify_position_family",
]
