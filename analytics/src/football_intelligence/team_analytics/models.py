"""Provider-independent data structures for Team Analytics V1."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class TeamObservation:
    competition_id: int
    competition_code: str
    competition_name: str
    season_id: int
    season_label: str
    team_id: int
    team_name: str
    opponent_team_id: int
    match_id: int
    kickoff_at: datetime
    is_home: bool
    goals_for: int
    goals_against: int
    stats: Mapping[str, float | None]


@dataclass(frozen=True, slots=True)
class TeamFeature:
    team_id: int
    competition_id: int
    season_id: int
    scope_key: str
    window: str
    metric_name: str
    matches: int
    observed_matches: int
    raw_value: float
    adjusted_value: float
    percentile: float
    reference_sample_size: int
    model_version: str
    calculated_at: datetime


@dataclass(frozen=True, slots=True)
class TeamScore:
    team_id: int
    team_name: str
    competition_id: int
    season_id: int
    scope_key: str
    window: str
    matches: int
    overall_score: float
    confidence: float
    dimension_scores: Mapping[str, float]
    results_process_delta: float
    results_process_signal: str
    diagnostics: Mapping[str, Any]
    reference_sample_size: int
    current_elo: float
    elo_change_last_5: float
    model_version: str
    calculated_at: datetime


@dataclass(frozen=True, slots=True)
class TeamEloHistory:
    match_id: int
    team_id: int
    opponent_team_id: int
    competition_id: int
    season_id: int
    kickoff_at: datetime
    pre_match_rating: float
    opponent_pre_match_rating: float
    expected_result: float
    actual_result: float
    post_match_rating: float
    model_version: str
    calculated_at: datetime


@dataclass(frozen=True, slots=True)
class TeamAnalyticsResult:
    features: tuple[TeamFeature, ...]
    scores: tuple[TeamScore, ...]
    elo_history: tuple[TeamEloHistory, ...]
