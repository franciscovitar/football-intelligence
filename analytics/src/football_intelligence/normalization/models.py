"""Provider-independent DTOs used at the normalization/persistence boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TeamRecord:
    external_id: str
    name: str
    short_name: str | None
    country_code: str | None


@dataclass(frozen=True)
class PlayerRecord:
    external_id: str
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: str | None = None
    nationality_code: str | None = None


@dataclass(frozen=True)
class MatchRecord:
    external_id: str
    kickoff_at: datetime | None
    status: str
    round_name: str | None
    venue_name: str | None
    home_team_external_id: str
    away_team_external_id: str
    home_score: int | None
    away_score: int | None


@dataclass(frozen=True)
class TeamMatchStatsRecord:
    match_external_id: str
    team_external_id: str
    possession_pct: float | None
    shots_total: int | None
    shots_on_target: int | None
    shots_inside_box: int | None
    shots_outside_box: int | None
    blocked_shots: int | None
    corners: int | None
    offsides: int | None
    fouls: int | None
    yellow_cards: int | None
    red_cards: int | None
    passes_total: int | None
    passes_accurate: int | None
    goalkeeper_saves: int | None


@dataclass(frozen=True)
class PlayerAppearanceRecord:
    match_external_id: str
    player_external_id: str
    team_external_id: str
    minutes: int | None
    started: bool | None
    captain: bool | None
    shirt_number: int | None
    listed_position: str | None


@dataclass(frozen=True)
class PlayerMatchStatsRecord:
    match_external_id: str
    player_external_id: str
    goals: int | None
    assists: int | None
    shots_total: int | None
    shots_on_target: int | None
    passes_total: int | None
    passes_accurate: int | None
    key_passes: int | None
    tackles: int | None
    blocks: int | None
    interceptions: int | None
    clearances: int | None
    dribbles_attempted: int | None
    dribbles_successful: int | None
    duels_total: int | None
    duels_won: int | None
    fouls_drawn: int | None
    fouls_committed: int | None
    yellow_cards: int | None
    red_cards: int | None
    saves: int | None


@dataclass(frozen=True)
class NormalizedFixtureBatch:
    provider_competition_id: str
    season_label: str
    teams: tuple[TeamRecord, ...]
    players: tuple[PlayerRecord, ...]
    matches: tuple[MatchRecord, ...]
    team_match_stats: tuple[TeamMatchStatsRecord, ...]
    appearances: tuple[PlayerAppearanceRecord, ...]
    player_match_stats: tuple[PlayerMatchStatsRecord, ...]
