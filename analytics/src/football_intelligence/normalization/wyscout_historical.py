"""Canonical-ready normalization for Wyscout Open ENG_PL 2017/18.

Historical-only conversion from the already-certified Wyscout Open adapter
output into the repository's provider-independent persistence DTOs.

The only additional derivation introduced here is ``minutes``. The verified
ENG_PL 2017/18 source marks every league fixture ``duration == \"Regular\"``
and publishes substitution minutes, but no final-whistle timestamp. For
analytics, a regular match therefore uses a standardized 90-minute endpoint:
starters begin at 0, substitutes begin at their (clamped) substitution minute,
and a player's end is their (clamped) substitution-out minute or 90.

These are standardized analytics minutes, not a claim about exact elapsed
stoppage time. The methodology is versioned so a future exact source can
coexist without silently rewriting historical semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from football_intelligence.data_mesh.adapters.wyscout_open import (
    DEFAULT_SCOPE,
    parse_player_match_observations,
    parse_team_match_observations,
)
from football_intelligence.normalization.models import (
    MatchRecord,
    NormalizedFixtureBatch,
    PlayerAppearanceRecord,
    PlayerMatchStatsRecord,
    PlayerRecord,
    TeamMatchStatsRecord,
    TeamRecord,
)
from football_intelligence.providers.wyscout_open_text import (
    repair_wyscout_double_escaped_unicode,
)

COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2017/18"
PROVIDER_COMPETITION_ID = str(DEFAULT_SCOPE.provider_competition_id)
MINUTES_METHODOLOGY_VERSION = "wyscout-regular-90-v1.0"

_SENTINEL_PLAYER_ID = 0
_REGULAR_MATCH_MINUTES = 90

# Wyscout players.json exposes a broad global role, not a match-specific
# position. Preserve only that broad source fact in the existing position
# token field; never invent CB/RB/CM/etc. precision that the source lacks.
_ROLE_TO_LISTED_POSITION = {
    "GK": "GK",
    "DF": "DEF",
    "MD": "MID",
    "FW": "FW",
}

_PLAYER_STAT_COLUMNS = (
    "goals",
    "assists",
    "shots_total",
    "shots_on_target",
    "passes_total",
    "passes_accurate",
    "key_passes",
    "interceptions",
    "clearances",
    "duels_total",
    "duels_won",
    "fouls_committed",
    "yellow_cards",
    "red_cards",
    "saves",
)

_TEAM_STAT_COLUMNS = (
    "shots_total",
    "shots_on_target",
    "blocked_shots",
    "corners",
    "offsides",
    "fouls",
    "yellow_cards",
    "red_cards",
    "passes_total",
    "passes_accurate",
    "goalkeeper_saves",
)


class WyscoutHistoricalNormalizationError(RuntimeError):
    """The certified historical payload cannot be normalized safely."""


@dataclass(frozen=True, slots=True)
class WyscoutHistoricalNormalizationResult:
    batch: NormalizedFixtureBatch
    unresolved_participating_player_ids: tuple[int, ...]
    minutes_methodology_version: str = MINUTES_METHODOLOGY_VERSION


@dataclass(frozen=True, slots=True)
class _AppearanceSeed:
    match_external_id: str
    player_external_id: str
    team_external_id: str
    minutes: int
    started: bool


def normalize_england_2017_18(
    *,
    matches_payload: list[Any],
    events_payload: list[Any],
    players_payload: list[Any],
    teams_payload: list[Any],
    expected_match_count: int | None = 380,
) -> WyscoutHistoricalNormalizationResult:
    """Build a provider-independent canonical batch from the certified scope."""

    if expected_match_count is not None and len(matches_payload) != expected_match_count:
        raise WyscoutHistoricalNormalizationError(
            f"ENG_PL 2017/18 must contain exactly {expected_match_count} matches, "
            f"got {len(matches_payload)}"
        )

    team_names = _team_names_by_id(teams_payload)
    player_info = _player_info_by_id(players_payload)
    appearances = _derive_appearances(matches_payload)

    player_observations = parse_player_match_observations(
        matches_payload,
        events_payload,
        players_payload,
        scope=DEFAULT_SCOPE,
    )
    team_observations = parse_team_match_observations(
        matches_payload,
        events_payload,
        players_payload,
        teams_payload,
        scope=DEFAULT_SCOPE,
    )

    team_ids = _team_ids_from_matches(matches_payload)
    missing_team_names = tuple(sorted(team_ids - team_names.keys()))
    if missing_team_names:
        raise WyscoutHistoricalNormalizationError(
            "Wyscout teams.json is missing names for competition teams: "
            f"{list(missing_team_names)}"
        )

    unresolved_players = tuple(
        sorted(
            {
                int(seed.player_external_id)
                for seed in appearances.values()
                if int(seed.player_external_id) not in player_info
            }
        )
    )

    resolved_appearances = tuple(
        PlayerAppearanceRecord(
            match_external_id=seed.match_external_id,
            player_external_id=seed.player_external_id,
            team_external_id=seed.team_external_id,
            minutes=seed.minutes,
            started=seed.started,
            captain=None,
            shirt_number=None,
            listed_position=player_info[int(seed.player_external_id)][1],
        )
        for seed in sorted(
            appearances.values(),
            key=lambda item: (int(item.match_external_id), int(item.player_external_id)),
        )
        if int(seed.player_external_id) in player_info
    )

    participant_ids = {int(item.player_external_id) for item in resolved_appearances}
    players = tuple(
        PlayerRecord(external_id=str(player_id), display_name=player_info[player_id][0])
        for player_id in sorted(participant_ids)
    )

    teams = tuple(
        TeamRecord(
            external_id=str(team_id),
            name=team_names[team_id],
            short_name=None,
            country_code=None,
        )
        for team_id in sorted(team_ids, key=lambda item: team_names[item].casefold())
    )

    matches = tuple(_normalize_match(match) for match in matches_payload if isinstance(match, dict))
    if expected_match_count is not None and len(matches) != expected_match_count:
        raise WyscoutHistoricalNormalizationError(
            f"only {len(matches)} of {expected_match_count} Wyscout matches were "
            "structurally usable"
        )

    player_metric_map = _metric_map(
        player_observations,
        entity_type="player",
        metric_granularity="player_match",
    )
    team_metric_map = _metric_map(
        team_observations,
        entity_type="team",
        metric_granularity="team_match",
    )

    player_stats = tuple(
        _player_stats_record(appearance, player_metric_map)
        for appearance in resolved_appearances
    )
    team_stats = tuple(
        _team_stats_record(match_id, team_id, team_metric_map)
        for match_id, team_id in sorted(_match_team_pairs(matches_payload))
    )

    return WyscoutHistoricalNormalizationResult(
        batch=NormalizedFixtureBatch(
            provider_competition_id=PROVIDER_COMPETITION_ID,
            season_label=SEASON_LABEL,
            teams=teams,
            players=players,
            matches=matches,
            team_match_stats=team_stats,
            appearances=resolved_appearances,
            player_match_stats=player_stats,
        ),
        unresolved_participating_player_ids=unresolved_players,
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clamp_substitution_minute(value: Any) -> int:
    if not isinstance(value, int):
        raise WyscoutHistoricalNormalizationError(
            f"substitution minute must be an integer, got {value!r}"
        )
    return max(0, min(_REGULAR_MATCH_MINUTES, value))


def _derive_appearances(matches_payload: list[Any]) -> dict[tuple[int, int], _AppearanceSeed]:
    result: dict[tuple[int, int], _AppearanceSeed] = {}

    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        match_id = match.get("wyId")
        if not isinstance(match_id, int):
            raise WyscoutHistoricalNormalizationError("match without integer wyId")
        if match.get("duration") != "Regular":
            raise WyscoutHistoricalNormalizationError(
                f"match {match_id} has unsupported duration {match.get('duration')!r}; "
                "the 90-minute methodology only applies to Regular matches"
            )
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            raise WyscoutHistoricalNormalizationError(f"match {match_id} has no teamsData")

        for raw_team_id, team_entry in teams_data.items():
            if not isinstance(team_entry, dict):
                continue
            try:
                team_id = int(raw_team_id)
            except (TypeError, ValueError) as exc:
                raise WyscoutHistoricalNormalizationError(
                    f"match {match_id} has invalid team id {raw_team_id!r}"
                ) from exc

            formation = team_entry.get("formation")
            if not isinstance(formation, dict):
                raise WyscoutHistoricalNormalizationError(
                    f"match {match_id} team {team_id} has no formation structure"
                )

            starters = _player_ids(_as_list(formation.get("lineup")), "playerId")
            bench = _player_ids(_as_list(formation.get("bench")), "playerId")

            in_minutes: dict[int, int] = {}
            out_minutes: dict[int, int] = {}
            for substitution in _as_list(formation.get("substitutions")):
                if not isinstance(substitution, dict):
                    continue
                minute = _clamp_substitution_minute(substitution.get("minute"))
                player_in = substitution.get("playerIn")
                player_out = substitution.get("playerOut")
                if isinstance(player_in, int) and player_in != _SENTINEL_PLAYER_ID:
                    _put_unique_minute(
                        in_minutes, player_in, minute, match_id=match_id, direction="in"
                    )
                if isinstance(player_out, int) and player_out != _SENTINEL_PLAYER_ID:
                    _put_unique_minute(
                        out_minutes, player_out, minute, match_id=match_id, direction="out"
                    )

            # Match the certified adapter's participation universe exactly:
            # lineup players + bench players explicitly substituted in.
            participants = starters | (bench & set(in_minutes))
            for player_id in participants:
                start_minute = 0 if player_id in starters else in_minutes[player_id]
                end_minute = out_minutes.get(player_id, _REGULAR_MATCH_MINUTES)
                if end_minute < start_minute:
                    raise WyscoutHistoricalNormalizationError(
                        f"match {match_id} player {player_id} has substitution out "
                        f"minute {end_minute} before in minute {start_minute}"
                    )
                seed = _AppearanceSeed(
                    match_external_id=str(match_id),
                    player_external_id=str(player_id),
                    team_external_id=str(team_id),
                    minutes=end_minute - start_minute,
                    started=player_id in starters,
                )
                key = (match_id, player_id)
                existing = result.get(key)
                if existing is not None and existing != seed:
                    raise WyscoutHistoricalNormalizationError(
                        f"match {match_id} player {player_id} has conflicting team/appearance "
                        "evidence"
                    )
                result[key] = seed

    return result


def _player_ids(entries: list[Any], field: str) -> set[int]:
    result: set[int] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        value = entry.get(field)
        if isinstance(value, int) and value != _SENTINEL_PLAYER_ID:
            result.add(value)
    return result


def _put_unique_minute(
    target: dict[int, int],
    player_id: int,
    minute: int,
    *,
    match_id: int,
    direction: str,
) -> None:
    existing = target.get(player_id)
    if existing is not None and existing != minute:
        raise WyscoutHistoricalNormalizationError(
            f"match {match_id} player {player_id} has conflicting substitution-{direction} "
            f"minutes {existing} and {minute}"
        )
    target[player_id] = minute


def _team_names_by_id(payload: list[Any]) -> dict[int, str]:
    result: dict[int, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        team_id = item.get("wyId")
        raw_name = item.get("name") or item.get("officialName")
        if isinstance(team_id, int) and isinstance(raw_name, str) and raw_name.strip():
            result[team_id] = repair_wyscout_double_escaped_unicode(raw_name).strip()
    return result


def _player_info_by_id(payload: list[Any]) -> dict[int, tuple[str, str | None]]:
    result: dict[int, tuple[str, str | None]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        player_id = item.get("wyId")
        if not isinstance(player_id, int):
            continue
        raw_name = item.get("shortName")
        if not isinstance(raw_name, str) or not raw_name.strip():
            parts = [
                part.strip()
                for part in (item.get("firstName"), item.get("lastName"))
                if isinstance(part, str) and part.strip()
            ]
            raw_name = " ".join(parts)
        if not raw_name:
            continue
        role = item.get("role")
        code2 = role.get("code2") if isinstance(role, dict) else None
        listed_position = _ROLE_TO_LISTED_POSITION.get(code2) if isinstance(code2, str) else None
        result[player_id] = (
            repair_wyscout_double_escaped_unicode(raw_name).strip(),
            listed_position,
        )
    return result


def _team_ids_from_matches(matches_payload: list[Any]) -> set[int]:
    result: set[int] = set()
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue
        for raw_team_id in teams_data:
            try:
                result.add(int(raw_team_id))
            except (TypeError, ValueError):
                continue
    return result


def _match_team_pairs(matches_payload: list[Any]) -> set[tuple[int, int]]:
    pairs: set[tuple[int, int]] = set()
    for match in matches_payload:
        if not isinstance(match, dict) or not isinstance(match.get("wyId"), int):
            continue
        match_id = int(match["wyId"])
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue
        for raw_team_id in teams_data:
            try:
                pairs.add((match_id, int(raw_team_id)))
            except (TypeError, ValueError):
                continue
    return pairs


def _normalize_match(match: dict[str, Any]) -> MatchRecord:
    match_id = match.get("wyId")
    if not isinstance(match_id, int):
        raise WyscoutHistoricalNormalizationError("match without integer wyId")
    if match.get("competitionId") != DEFAULT_SCOPE.provider_competition_id:
        raise WyscoutHistoricalNormalizationError(
            f"match {match_id} is outside Wyscout ENG_PL competition scope"
        )
    if match.get("seasonId") != DEFAULT_SCOPE.provider_season_id:
        raise WyscoutHistoricalNormalizationError(
            f"match {match_id} is outside Wyscout ENG_PL 2017/18 season scope"
        )
    if match.get("status") != "Played":
        raise WyscoutHistoricalNormalizationError(
            f"match {match_id} has unsupported status {match.get('status')!r}"
        )

    teams_data = match.get("teamsData")
    if not isinstance(teams_data, dict):
        raise WyscoutHistoricalNormalizationError(f"match {match_id} has no teamsData")

    home_id: int | None = None
    away_id: int | None = None
    home_score: int | None = None
    away_score: int | None = None
    for raw_team_id, team_entry in teams_data.items():
        if not isinstance(team_entry, dict):
            continue
        try:
            team_id = int(raw_team_id)
        except (TypeError, ValueError):
            continue
        side = team_entry.get("side")
        score = team_entry.get("score")
        if side == "home":
            home_id = team_id
            home_score = score if isinstance(score, int) else None
        elif side == "away":
            away_id = team_id
            away_score = score if isinstance(score, int) else None

    if home_id is None or away_id is None or home_score is None or away_score is None:
        raise WyscoutHistoricalNormalizationError(
            f"match {match_id} is missing home/away identity or score"
        )

    raw_kickoff = match.get("dateutc")
    if not isinstance(raw_kickoff, str) or not raw_kickoff.strip():
        raise WyscoutHistoricalNormalizationError(f"match {match_id} has no dateutc")
    try:
        kickoff_at = datetime.strptime(raw_kickoff.strip(), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=UTC
        )
    except ValueError as exc:
        raise WyscoutHistoricalNormalizationError(
            f"match {match_id} has invalid dateutc {raw_kickoff!r}"
        ) from exc

    gameweek = match.get("gameweek")
    venue = match.get("venue")
    return MatchRecord(
        external_id=str(match_id),
        kickoff_at=kickoff_at,
        status="finished",
        round_name=str(gameweek) if isinstance(gameweek, int) else None,
        venue_name=venue.strip() if isinstance(venue, str) and venue.strip() else None,
        home_team_external_id=str(home_id),
        away_team_external_id=str(away_id),
        home_score=home_score,
        away_score=away_score,
    )


def _metric_map(
    observations: list[Any],
    *,
    entity_type: str,
    metric_granularity: str,
) -> dict[tuple[str, str], Any]:
    result: dict[tuple[str, str], Any] = {}
    for observation in observations:
        if (
            observation.entity_type != entity_type
            or observation.metric_granularity != metric_granularity
        ):
            continue
        hints = observation.entity_identity_hints
        match_id = hints.get("match_external_id")
        entity_id = (
            hints.get("player_external_id")
            if entity_type == "player"
            else hints.get("team_external_id")
        )
        if not match_id or not entity_id:
            continue
        key = (f"{match_id}:{entity_id}", observation.metric_name)
        if key in result and result[key] != observation.value:
            raise WyscoutHistoricalNormalizationError(
                f"conflicting normalized observation for {key}: "
                f"{result[key]!r} != {observation.value!r}"
            )
        result[key] = observation.value
    return result


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise WyscoutHistoricalNormalizationError(f"expected integer metric, got {value!r}")


def _player_stats_record(
    appearance: PlayerAppearanceRecord,
    metric_map: dict[tuple[str, str], Any],
) -> PlayerMatchStatsRecord:
    entity = f"{appearance.match_external_id}:{appearance.player_external_id}"
    values = {
        metric: _optional_int(metric_map.get((entity, metric))) for metric in _PLAYER_STAT_COLUMNS
    }
    return PlayerMatchStatsRecord(
        match_external_id=appearance.match_external_id,
        player_external_id=appearance.player_external_id,
        goals=values["goals"],
        assists=values["assists"],
        shots_total=values["shots_total"],
        shots_on_target=values["shots_on_target"],
        passes_total=values["passes_total"],
        passes_accurate=values["passes_accurate"],
        key_passes=values["key_passes"],
        tackles=None,
        blocks=None,
        interceptions=values["interceptions"],
        clearances=values["clearances"],
        dribbles_attempted=None,
        dribbles_successful=None,
        duels_total=values["duels_total"],
        duels_won=values["duels_won"],
        fouls_drawn=None,
        fouls_committed=values["fouls_committed"],
        yellow_cards=values["yellow_cards"],
        red_cards=values["red_cards"],
        saves=values["saves"],
    )


def _team_stats_record(
    match_id: int,
    team_id: int,
    metric_map: dict[tuple[str, str], Any],
) -> TeamMatchStatsRecord:
    entity = f"{match_id}:{team_id}"
    values = {
        metric: _optional_int(metric_map.get((entity, metric))) for metric in _TEAM_STAT_COLUMNS
    }
    return TeamMatchStatsRecord(
        match_external_id=str(match_id),
        team_external_id=str(team_id),
        possession_pct=None,
        shots_total=values["shots_total"],
        shots_on_target=values["shots_on_target"],
        shots_inside_box=None,
        shots_outside_box=None,
        blocked_shots=values["blocked_shots"],
        corners=values["corners"],
        offsides=values["offsides"],
        fouls=values["fouls"],
        yellow_cards=values["yellow_cards"],
        red_cards=values["red_cards"],
        passes_total=values["passes_total"],
        passes_accurate=values["passes_accurate"],
        goalkeeper_saves=values["goalkeeper_saves"],
    )
