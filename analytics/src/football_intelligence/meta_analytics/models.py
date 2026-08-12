"""Provider-independent data structures for Expectation & Meta Intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class PlayerScoreEvidence:
    player_id: int
    player_name: str
    scope_key: str
    period_index: int
    window: str
    role: str
    overall_score: float
    confidence: float
    model_version: str


@dataclass(frozen=True, slots=True)
class PlayerMetaSnapshot:
    player_id: int
    player_name: str
    scope_key: str
    role: str
    performance_score: float
    performance_confidence: float
    form_score: float | None
    form_confidence: float | None
    stable_score: float
    stable_confidence: float
    expectation_score: float | None
    expectation_confidence: float | None
    surprise_delta: float | None
    surprise_signal: str
    trend_delta: float | None
    trend_confidence: float | None
    trend_signal: str
    watchlist_score: float
    watchlist_signal: str
    history_seasons: int
    baseline_evidence: tuple[dict[str, Any], ...]
    trend_evidence: dict[str, Any]
    source_model_version: str
    model_version: str
    calculated_at: datetime
