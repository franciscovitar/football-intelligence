"""Data structures for provider-independent player analytics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class PlayerObservation:
    player_id: int
    player_name: str
    match_id: int
    kickoff_at: datetime
    team_id: int
    minutes: int
    listed_position: str | None
    possession_pct: float | None
    stats: Mapping[str, float | None]


@dataclass(frozen=True, slots=True)
class PlayerSeasonObservation:
    """Provider-supplied player-season evidence, never synthesized from matches."""

    player_id: int
    player_name: str
    season_id: int
    season_label: str
    team_id: int | None
    minutes: int
    appearances: int
    listed_position: str | None
    stats: Mapping[str, float | None]


@dataclass(frozen=True, slots=True)
class GoalkeeperSeasonObservation:
    """Provider-supplied goalkeeper-season evidence at its native grain."""

    player_id: int
    player_name: str
    season_id: int
    season_label: str
    team_id: int | None
    minutes: int
    appearances: int
    stats: Mapping[str, float | None]


@dataclass(frozen=True, slots=True)
class PlayerFeature:
    player_id: int
    player_name: str
    scope_key: str
    window: str
    role: str
    metric_name: str
    minutes: int
    appearances: int
    raw_per90: float
    adjusted_per90: float
    percentile: float
    reference_sample_size: int
    model_version: str
    calculated_at: datetime


@dataclass(frozen=True, slots=True)
class PlayerScore:
    player_id: int
    player_name: str
    scope_key: str
    window: str
    role: str
    role_confidence: float
    minutes: int
    appearances: int
    overall_score: float
    confidence: float
    dimension_scores: Mapping[str, float]
    reference_sample_size: int
    model_version: str
    calculated_at: datetime


@dataclass(frozen=True, slots=True)
class PlayerAnalyticsResult:
    features: tuple[PlayerFeature, ...]
    scores: tuple[PlayerScore, ...]
