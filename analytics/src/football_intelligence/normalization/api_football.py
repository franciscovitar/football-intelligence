"""Normalize API-Football fixture payloads into provider-independent DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from football_intelligence.normalization.models import (
    MatchRecord,
    NormalizedFixtureBatch,
    PlayerAppearanceRecord,
    PlayerMatchStatsRecord,
    PlayerRecord,
    TeamLineupRecord,
    TeamMatchStatsRecord,
    TeamRecord,
)

JsonObject = dict[str, Any]

_FINISHED_STATUSES = {"FT", "AET", "PEN"}
_LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}
_POSTPONED_STATUSES = {"PST"}
_CANCELLED_STATUSES = {"CANC"}
_ABANDONED_STATUSES = {"ABD"}


def normalize_fixture_bundle(payload: JsonObject) -> NormalizedFixtureBatch:
    response = payload.get("response")
    if not isinstance(response, list) or not response:
        raise ValueError("fixture payload must contain at least one response item")

    provider_competition_id: str | None = None
    season_label: str | None = None
    teams: dict[str, TeamRecord] = {}
    players: dict[str, PlayerRecord] = {}
    matches: list[MatchRecord] = []
    team_stats: list[TeamMatchStatsRecord] = []
    team_lineups: list[TeamLineupRecord] = []
    appearances: list[PlayerAppearanceRecord] = []
    player_stats: list[PlayerMatchStatsRecord] = []

    for item in response:
        if not isinstance(item, dict):
            continue

        league = _mapping(item.get("league"))
        league_id = _required_external_id(league.get("id"), "league.id")
        season = _required_text_or_number(league.get("season"), "league.season")
        if provider_competition_id is None:
            provider_competition_id = league_id
            season_label = season
        elif provider_competition_id != league_id or season_label != season:
            raise ValueError("fixture bundle must contain one competition and season")

        fixture = _mapping(item.get("fixture"))
        fixture_id = _required_external_id(fixture.get("id"), "fixture.id")
        status = _mapping(fixture.get("status"))
        short_status = _optional_text(status.get("short"))
        teams_payload = _mapping(item.get("teams"))
        home = _mapping(teams_payload.get("home"))
        away = _mapping(teams_payload.get("away"))
        home_id = _required_external_id(home.get("id"), "teams.home.id")
        away_id = _required_external_id(away.get("id"), "teams.away.id")

        teams[home_id] = _normalize_team(home)
        teams[away_id] = _normalize_team(away)

        goals = _mapping(item.get("goals"))
        venue = _mapping(fixture.get("venue"))
        matches.append(
            MatchRecord(
                external_id=fixture_id,
                kickoff_at=_parse_datetime(fixture.get("date")),
                status=_normalize_status(short_status),
                round_name=_optional_text(league.get("round")),
                venue_name=_optional_text(venue.get("name")),
                home_team_external_id=home_id,
                away_team_external_id=away_id,
                home_score=_optional_int(goals.get("home")),
                away_score=_optional_int(goals.get("away")),
            )
        )

        for lineup_group in _list_of_mappings(item.get("lineups")):
            team = _mapping(lineup_group.get("team"))
            team_id = _required_external_id(team.get("id"), "lineups.team.id")
            if team_id not in {home_id, away_id}:
                continue
            coach = _mapping(lineup_group.get("coach"))
            team_lineups.append(
                TeamLineupRecord(
                    match_external_id=fixture_id,
                    team_external_id=team_id,
                    formation=_optional_text(lineup_group.get("formation")),
                    coach_name=_optional_text(coach.get("name")),
                )
            )

        for stats_group in _list_of_mappings(item.get("statistics")):
            team = _mapping(stats_group.get("team"))
            team_id = _required_external_id(team.get("id"), "statistics.team.id")
            values = _stat_map(stats_group.get("statistics"))
            team_stats.append(
                TeamMatchStatsRecord(
                    match_external_id=fixture_id,
                    team_external_id=team_id,
                    possession_pct=_optional_percent(values.get("Ball Possession")),
                    shots_total=_optional_int(values.get("Total Shots")),
                    shots_on_target=_optional_int(values.get("Shots on Goal")),
                    shots_inside_box=_optional_int(values.get("Shots insidebox")),
                    shots_outside_box=_optional_int(values.get("Shots outsidebox")),
                    blocked_shots=_optional_int(values.get("Blocked Shots")),
                    corners=_optional_int(values.get("Corner Kicks")),
                    offsides=_optional_int(values.get("Offsides")),
                    fouls=_optional_int(values.get("Fouls")),
                    yellow_cards=_optional_int(values.get("Yellow Cards")),
                    red_cards=_optional_int(values.get("Red Cards")),
                    passes_total=_optional_int(values.get("Total passes")),
                    passes_accurate=_optional_int(values.get("Passes accurate")),
                    goalkeeper_saves=_optional_int(values.get("Goalkeeper Saves")),
                )
            )

        for players_group in _list_of_mappings(item.get("players")):
            team = _mapping(players_group.get("team"))
            team_id = _required_external_id(team.get("id"), "players.team.id")
            for player_item in _list_of_mappings(players_group.get("players")):
                player = _mapping(player_item.get("player"))
                player_id = _required_external_id(player.get("id"), "player.id")
                display_name = _required_text_or_number(player.get("name"), "player.name")
                players[player_id] = PlayerRecord(
                    external_id=player_id,
                    display_name=display_name,
                )

                statistics = _list_of_mappings(player_item.get("statistics"))
                if not statistics:
                    appearances.append(
                        PlayerAppearanceRecord(
                            match_external_id=fixture_id,
                            player_external_id=player_id,
                            team_external_id=team_id,
                            minutes=None,
                            started=None,
                            captain=None,
                            shirt_number=None,
                            listed_position=None,
                        )
                    )
                    player_stats.append(_empty_player_stats(fixture_id, player_id))
                    continue

                stat = statistics[0]
                games = _mapping(stat.get("games"))
                substitute = _optional_bool(games.get("substitute"))
                appearances.append(
                    PlayerAppearanceRecord(
                        match_external_id=fixture_id,
                        player_external_id=player_id,
                        team_external_id=team_id,
                        minutes=_optional_int(games.get("minutes")),
                        started=None if substitute is None else not substitute,
                        captain=_optional_bool(games.get("captain")),
                        shirt_number=_optional_int(games.get("number")),
                        listed_position=_optional_text(games.get("position")),
                    )
                )

                shots = _mapping(stat.get("shots"))
                goals = _mapping(stat.get("goals"))
                passes = _mapping(stat.get("passes"))
                tackles = _mapping(stat.get("tackles"))
                dribbles = _mapping(stat.get("dribbles"))
                duels = _mapping(stat.get("duels"))
                fouls = _mapping(stat.get("fouls"))
                cards = _mapping(stat.get("cards"))

                player_stats.append(
                    PlayerMatchStatsRecord(
                        match_external_id=fixture_id,
                        player_external_id=player_id,
                        goals=_optional_int(goals.get("total")),
                        assists=_optional_int(goals.get("assists")),
                        shots_total=_optional_int(shots.get("total")),
                        shots_on_target=_optional_int(shots.get("on")),
                        passes_total=_optional_int(passes.get("total")),
                        # API-Football exposes pass accuracy as a percentage in fixture
                        # player stats, not a verified accurate-pass count. Preserve NULL
                        # rather than fabricate a count from a rounded percentage.
                        passes_accurate=None,
                        key_passes=_optional_int(passes.get("key")),
                        tackles=_optional_int(tackles.get("total")),
                        blocks=_optional_int(tackles.get("blocks")),
                        interceptions=_optional_int(tackles.get("interceptions")),
                        # Fixture player stats currently do not expose a verified
                        # clearance count in the documented response shape.
                        clearances=None,
                        dribbles_attempted=_optional_int(dribbles.get("attempts")),
                        dribbles_successful=_optional_int(dribbles.get("success")),
                        duels_total=_optional_int(duels.get("total")),
                        duels_won=_optional_int(duels.get("won")),
                        fouls_drawn=_optional_int(fouls.get("drawn")),
                        fouls_committed=_optional_int(fouls.get("committed")),
                        yellow_cards=_optional_int(cards.get("yellow")),
                        red_cards=_optional_int(cards.get("red")),
                        saves=_optional_int(goals.get("saves")),
                    )
                )

    if provider_competition_id is None or season_label is None:
        raise ValueError("fixture bundle did not contain a valid competition")

    return NormalizedFixtureBatch(
        provider_competition_id=provider_competition_id,
        season_label=season_label,
        teams=tuple(teams.values()),
        players=tuple(players.values()),
        matches=tuple(matches),
        team_match_stats=tuple(team_stats),
        appearances=tuple(appearances),
        player_match_stats=tuple(player_stats),
        team_lineups=tuple(team_lineups),
    )


def _normalize_team(team: JsonObject) -> TeamRecord:
    external_id = _required_external_id(team.get("id"), "team.id")
    return TeamRecord(
        external_id=external_id,
        name=_required_text_or_number(team.get("name"), "team.name"),
        short_name=_optional_text(team.get("code")),
        country_code=None,
    )


def _empty_player_stats(match_id: str, player_id: str) -> PlayerMatchStatsRecord:
    return PlayerMatchStatsRecord(
        match_external_id=match_id,
        player_external_id=player_id,
        goals=None,
        assists=None,
        shots_total=None,
        shots_on_target=None,
        passes_total=None,
        passes_accurate=None,
        key_passes=None,
        tackles=None,
        blocks=None,
        interceptions=None,
        clearances=None,
        dribbles_attempted=None,
        dribbles_successful=None,
        duels_total=None,
        duels_won=None,
        fouls_drawn=None,
        fouls_committed=None,
        yellow_cards=None,
        red_cards=None,
        saves=None,
    )


def _normalize_status(short_status: str | None) -> str:
    if short_status in _FINISHED_STATUSES:
        return "finished"
    if short_status in _LIVE_STATUSES:
        return "live"
    if short_status in _POSTPONED_STATUSES:
        return "postponed"
    if short_status in _CANCELLED_STATUSES:
        return "cancelled"
    if short_status in _ABANDONED_STATUSES:
        return "abandoned"
    if short_status in {"TBD", "NS"}:
        return "scheduled"
    return "unknown"


def _mapping(value: object) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _list_of_mappings(value: object) -> list[JsonObject]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _stat_map(value: object) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in _list_of_mappings(value):
        stat_type = item.get("type")
        if isinstance(stat_type, str):
            result[stat_type] = item.get("value")
    return result


def _required_external_id(value: object, field: str) -> str:
    if isinstance(value, (int, str)) and str(value).strip():
        return str(value)
    raise ValueError(f"{field} is required")


def _required_text_or_number(value: object, field: str) -> str:
    if isinstance(value, (int, str)) and str(value).strip():
        return str(value)
    raise ValueError(f"{field} is required")


def _optional_text(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def _optional_percent(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
