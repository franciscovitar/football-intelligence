"""Provider-independent structures for World Radar V1.

World Radar is explicitly an offensive/creative radar: it detects standout
attacking and creative production from `topscorers`/`topassists` feeds outside
the core leagues. It never claims to cover defenders, goalkeepers, full
scouting, league quality, market value, or transfer potential.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

SourceList = Literal["topscorers", "topassists"]
RadarProfile = Literal["attacker", "midfielder"]


@dataclass(frozen=True, slots=True)
class ResolvedCompetition:
    """A World Radar competition after an unambiguous `/leagues` match."""

    code: str
    name: str
    country: str
    provider_league_id: int
    season: int


@dataclass(frozen=True, slots=True)
class RawPlayerFeedEntry:
    """One player row parsed from a single `topscorers`/`topassists` response."""

    provider_player_id: str
    player_name: str
    team_name: str | None
    position: str | None
    age: int | None
    nationality: str | None
    appearances: int | None
    minutes: int | None
    goals: int | None
    assists: int | None
    shots_total: int | None
    shots_on_target: int | None
    key_passes: int | None
    dribbles_successful: int | None
    source_list: SourceList


@dataclass(frozen=True, slots=True)
class PlayerRadarCandidate:
    """A player merged across feeds within one competition, processed once."""

    provider_player_id: str
    player_name: str
    team_name: str | None
    position: str | None
    appearances: int | None
    minutes: int | None
    goals: int | None
    assists: int | None
    shots_total: int | None
    shots_on_target: int | None
    key_passes: int | None
    dribbles_successful: int | None
    source_lists: tuple[SourceList, ...]


@dataclass(frozen=True, slots=True)
class PlayerRadarSnapshot:
    """Final, auditable World Radar V1 output for one player/competition/season."""

    provider_code: str
    provider_player_id: str
    player_name: str
    team_name: str | None
    competition_code: str
    competition_name: str
    country: str
    season_label: str
    position: str | None
    appearances: int | None
    minutes: int | None
    goals: int | None
    assists: int | None
    metrics: Mapping[str, float | None]
    radar_score: float
    confidence: float
    reasons: tuple[str, ...]
    source_lists: tuple[SourceList, ...]
    profile: RadarProfile
    model_version: str
    calculated_at: datetime
