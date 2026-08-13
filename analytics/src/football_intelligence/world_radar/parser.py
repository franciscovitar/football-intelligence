"""API-Football payload parsing for World Radar V1.

Provider-specific parsing is isolated here so the rest of the module stays
provider-independent. Provider payloads are treated as untrusted: every field
is defensively type-checked and missing data stays missing (never coerced to
zero).
"""

from __future__ import annotations

from typing import Any

from football_intelligence.world_radar.models import RawPlayerFeedEntry, SourceList

JsonObject = dict[str, Any]


def parse_player_feed(payload: JsonObject, *, source_list: SourceList) -> list[RawPlayerFeedEntry]:
    response = payload.get("response")
    if not isinstance(response, list):
        return []

    entries: list[RawPlayerFeedEntry] = []
    for item in response:
        entry = _parse_entry(item, source_list=source_list)
        if entry is not None:
            entries.append(entry)
    return entries


def find_league_matches(payload: JsonObject, *, name: str, country: str) -> list[int]:
    """Return provider league ids matching name+country unambiguously.

    Comparison is case-insensitive on trimmed values; callers must require
    exactly one match before proceeding.
    """
    response = payload.get("response")
    if not isinstance(response, list):
        return []

    target_name = name.strip().casefold()
    target_country = country.strip().casefold()
    matches: set[int] = set()

    for item in response:
        if not isinstance(item, dict):
            continue
        league = _mapping(item.get("league"))
        country_block = _mapping(item.get("country"))
        league_name = league.get("name")
        league_id = league.get("id")
        country_name = country_block.get("name")
        if (
            isinstance(league_name, str)
            and isinstance(country_name, str)
            and isinstance(league_id, int)
            and league_name.strip().casefold() == target_name
            and country_name.strip().casefold() == target_country
        ):
            matches.add(league_id)

    return sorted(matches)


def _parse_entry(item: Any, *, source_list: SourceList) -> RawPlayerFeedEntry | None:
    if not isinstance(item, dict):
        return None
    player = _mapping(item.get("player"))
    provider_player_id = player.get("id")
    if provider_player_id is None:
        return None
    name = player.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    statistics = item.get("statistics")
    if not isinstance(statistics, list) or not statistics:
        return None
    stats = statistics[0]
    if not isinstance(stats, dict):
        return None

    team = _mapping(stats.get("team"))
    games = _mapping(stats.get("games"))
    goals_block = _mapping(stats.get("goals"))
    shots_block = _mapping(stats.get("shots"))
    passes_block = _mapping(stats.get("passes"))
    dribbles_block = _mapping(stats.get("dribbles"))

    return RawPlayerFeedEntry(
        provider_player_id=str(provider_player_id),
        player_name=name.strip(),
        team_name=_optional_text(team.get("name")),
        position=_optional_text(games.get("position")),
        age=_optional_int(player.get("age")),
        nationality=_optional_text(player.get("nationality")),
        appearances=_optional_int(games.get("appearences")),
        minutes=_optional_int(games.get("minutes")),
        goals=_optional_int(goals_block.get("total")),
        assists=_optional_int(goals_block.get("assists")),
        shots_total=_optional_int(shots_block.get("total")),
        shots_on_target=_optional_int(shots_block.get("on")),
        key_passes=_optional_int(passes_block.get("key")),
        dribbles_successful=_optional_int(dribbles_block.get("success")),
        source_list=source_list,
    )


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None
