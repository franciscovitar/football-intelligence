"""Provider-independent structures for Tactical Intelligence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

StyleSignal = Literal[
    "control_and_volume",
    "possession_control",
    "volume_without_control",
    "low_control_low_volume",
    "balanced",
    "insufficient_evidence",
]

DefensiveSignal = Literal[
    "restrictive_shot_profile",
    "balanced",
    "permissive_shot_profile",
    "insufficient_evidence",
]

FormationSignal = Literal[
    "stable",
    "variable",
    "mixed",
    "limited_evidence",
    "unavailable",
]


@dataclass(frozen=True, slots=True)
class FormationObservation:
    match_id: int
    kickoff_at: datetime
    formation: str


@dataclass(frozen=True, slots=True)
class TeamTacticalInput:
    team_id: int
    team_name: str
    competition_id: int
    competition_code: str
    competition_name: str
    season_id: int
    season_label: str
    scope_key: str
    matches: int
    source_confidence: float
    dimension_scores: Mapping[str, float]
    formations: tuple[FormationObservation, ...]


@dataclass(frozen=True, slots=True)
class TeamTacticalSnapshot:
    team_id: int
    team_name: str
    competition_id: int
    competition_code: str
    competition_name: str
    season_id: int
    season_label: str
    scope_key: str
    matches: int
    source_confidence: float
    control_score: float | None
    attacking_volume_score: float | None
    defensive_resistance_score: float | None
    style_signal: StyleSignal
    defensive_signal: DefensiveSignal
    primary_formation: str | None
    formation_matches: int
    formation_share: float | None
    formation_confidence: float
    formation_signal: FormationSignal
    alternative_formations: tuple[dict[str, Any], ...]
    tactical_confidence: float
    summary: str
    evidence: dict[str, Any]
    source_model_version: str
    model_version: str
    calculated_at: datetime
