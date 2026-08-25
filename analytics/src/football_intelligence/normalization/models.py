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
class TeamLineupRecord:
    match_external_id: str
    team_external_id: str
    formation: str | None
    coach_name: str | None


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
    # Optional additions preserve backwards compatibility for providers that
    # do not expose aerial subtypes. Missing stays None; confirmed Wyscout
    # participants may carry real zero counts.
    aerial_duels: int | None = None
    aerial_duels_won: int | None = None


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
    team_lineups: tuple[TeamLineupRecord, ...] = ()


@dataclass(frozen=True)
class PlayerSeasonStatsRecord:
    """A season-aggregate player record (Block 16), distinct from the
    per-match `PlayerMatchStatsRecord` above -- some sources (e.g. the
    permitted season-summary sources may only publish a season rollup,
    with no match-by-match breakdown to derive last-3/last-5/last-10 form
    windows from. Missing fields stay `None`; a real `0` (e.g. a striker who
    genuinely scored zero goals) is preserved as `0`, never conflated with
    "not reported".
    """

    player_external_id: str
    competition_external_id: str
    season_label: str
    minutes: int | None
    starts: int | None
    appearances: int | None
    goals: int | None
    assists: int | None
    clean_sheets: int | None
    goals_conceded: int | None
    own_goals: int | None
    penalties_saved: int | None
    penalties_missed: int | None
    yellow_cards: int | None
    red_cards: int | None
    saves: int | None
    bonus: int | None
    bps: int | None
    influence: float | None
    creativity: float | None
    threat: float | None
    ict_index: float | None
    tackles: int | None
    recoveries: int | None
    clearances_blocks_interceptions: int | None
    defensive_contribution: int | None
    expected_goals: float | None
    expected_assists: float | None
    expected_goal_involvements: float | None
    expected_goals_conceded: float | None
    source: str
    source_url: str
    retrieved_at: datetime
    semantic_version: str
