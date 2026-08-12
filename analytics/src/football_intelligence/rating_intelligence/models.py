"""Provider-independent structures for Rating Intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

SourceKind = Literal["expert", "media", "fan", "other"]
RatingSignal = Literal[
    "underrated",
    "overrated",
    "aligned",
    "polarized",
    "insufficient_evidence",
]
PerceptionSignal = Literal["positive", "negative", "neutral", "mixed", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class PlayerRatingInput:
    player_id: int
    player_name: str
    scope_key: str
    role: str
    stable_score: float
    stable_confidence: float


@dataclass(frozen=True, slots=True)
class RatingEvidence:
    evidence_id: int
    player_id: int
    source_id: int
    source_code: str
    source_kind: SourceKind
    title: str
    excerpt: str | None
    matched_text: str
    published_at: datetime
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class EvidenceEvaluation:
    evidence_id: int
    source_id: int
    source_code: str
    source_kind: SourceKind
    stance_score: float
    stance_confidence: float
    recency_weight: float
    matched_terms: tuple[str, ...]
    context: str


@dataclass(frozen=True, slots=True)
class PlayerRatingSnapshot:
    player_id: int
    player_name: str
    scope_key: str
    role: str
    performance_score: float
    performance_confidence: float
    perception_score: float | None
    perception_confidence: float
    perception_signal: PerceptionSignal
    rating_gap: float | None
    rating_confidence: float
    rating_signal: RatingSignal
    consensus_score: float | None
    polarization_score: float | None
    evidence_count: int
    scored_evidence_count: int
    source_count: int
    scored_source_count: int
    evidence_window_days: int
    evidence_breakdown: tuple[dict[str, Any], ...]
    performance_model_version: str
    perception_model_version: str
    model_version: str
    calculated_at: datetime
