"""StatsBomb Open Data payload -> NormalizedObservation adapter.

Historical/deep role only -- this adapter is never a current-season feed
(see `docs/ZERO_COST_COVERAGE.md`). Every derived metric below has a
verified StatsBomb event-field mapping confirmed against real Bundesliga
2023/24 event data during Block 14 implementation; nothing here is guessed
from documentation alone. Metrics without a verified, reliable derivation
(passes_accurate is the one exception below, verified via the `pass.outcome`
absence convention; things like duels_won, minutes, or xA are deliberately
NOT derived) are simply never emitted -- missing stays missing.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from football_intelligence.data_mesh.models import EntityType, NormalizedObservation, SourceType
from football_intelligence.data_mesh.timeparse import parse_utc_timestamp

SOURCE_CODE = "statsbomb-open"
SOURCE_TYPE: SourceType = "objective_structured"
SEMANTIC_VERSION = "statsbomb-open-v0.1"

# Verified against a real Bundesliga 2023/24 match's events.json.
_ON_TARGET_SHOT_OUTCOMES = frozenset({"Goal", "Saved"})
_GOAL_SHOT_OUTCOME = "Goal"
_RED_CARD_NAMES = frozenset({"Red Card", "Second Yellow"})
_YELLOW_CARD_NAME = "Yellow Card"
_SAVE_GOALKEEPER_TYPE = "Shot Saved"
_TACKLE_DUEL_TYPE = "Tackle"
_DRIBBLE_COMPLETE_OUTCOME = "Complete"
_SHOT_ASSIST_KIND = "shot_assist"

# Every metric an appeared player is force-filled to a real 0 for, if no
# qualifying event occurred for them (see `parse_match_events`).
_COUNT_METRIC_NAMES: tuple[str, ...] = (
    "shots_total",
    "shots_on_target",
    "goals",
    "key_passes",
    "passes_total",
    "passes_accurate",
    "interceptions",
    "clearances",
    "blocks",
    "dribbles_attempted",
    "dribbles_successful",
    "tackles",
    "fouls_committed",
    "fouls_drawn",
    "yellow_cards",
    "red_cards",
    "saves",
    "advanced.xg",
)


def find_competition_season(
    payload: Any,
    *,
    competition_name: str,
    season_name: str,
) -> tuple[int, int] | None:
    """Locate (competition_id, season_id) in competitions.json by exact name match."""

    if not isinstance(payload, list):
        return None
    for item in payload:
        if not isinstance(item, dict):
            continue
        if (
            item.get("competition_name") == competition_name
            and item.get("season_name") == season_name
            and item.get("competition_gender") == "male"
        ):
            competition_id = item.get("competition_id")
            season_id = item.get("season_id")
            if isinstance(competition_id, int) and isinstance(season_id, int):
                return competition_id, season_id
    return None


def parse_match_list(
    payload: Any,
    *,
    competition_code: str,
    season_label: str,
    ingestion_run_id: int | None,
    limit: int | None = None,
) -> list[NormalizedObservation]:
    if not isinstance(payload, list):
        return []
    items = payload[:limit] if limit is not None else payload

    observations: list[NormalizedObservation] = []
    competition_name: str | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if competition_name is None:
            name = item.get("competition", {}).get("competition_name")
            if isinstance(name, str) and name.strip():
                competition_name = name.strip()
        observations.extend(
            _parse_match_summary(
                item,
                competition_code=competition_code,
                season_label=season_label,
                ingestion_run_id=ingestion_run_id,
            )
        )

    if competition_name is not None and items:
        observations.append(
            _observation(
                entity_type="competition",
                entity_source_id=competition_code,
                entity_identity_hints={"name": competition_name},
                metric_name="name",
                value=competition_name,
                observed_at=observations[0].observed_at if observations else _fallback_now(),
                source_reference=f"data/matches/{competition_code}",
                ingestion_run_id=ingestion_run_id,
            )
        )
    return observations


def _parse_match_summary(
    item: dict[str, Any],
    *,
    competition_code: str,
    season_label: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    match_id = item.get("match_id")
    home_team = item.get("home_team", {}).get("home_team_name")
    away_team = item.get("away_team", {}).get("away_team_name")
    home_score = item.get("home_score")
    away_score = item.get("away_score")
    match_date = item.get("match_date")
    if match_id is None or not isinstance(home_team, str) or not isinstance(away_team, str):
        return []

    observed_at = parse_utc_timestamp(f"{match_date}T00:00:00") if match_date else None
    if observed_at is None:
        return []

    reference = f"data/matches/{competition_code}/{season_label}.json"
    identity_hints = {
        "competition_external_id": competition_code,
        "season_label": season_label,
        "home_team_name": home_team,
        "away_team_name": away_team,
        "kickoff_date": observed_at.date().isoformat(),
    }

    observations = [
        _observation(
            entity_type="team",
            entity_source_id=str(item.get("home_team", {}).get("home_team_id", home_team)),
            entity_identity_hints={"name": home_team, "competition_external_id": competition_code},
            metric_name="name",
            value=home_team,
            observed_at=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
        ),
        _observation(
            entity_type="team",
            entity_source_id=str(item.get("away_team", {}).get("away_team_id", away_team)),
            entity_identity_hints={"name": away_team, "competition_external_id": competition_code},
            metric_name="name",
            value=away_team,
            observed_at=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
        ),
        # StatsBomb Open Data only ever publishes completed historical
        # matches -- there is no "scheduled"/"live" state to represent.
        _observation(
            entity_type="match",
            entity_source_id=str(match_id),
            entity_identity_hints=identity_hints,
            metric_name="status",
            value="finished",
            observed_at=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
        ),
    ]
    if isinstance(home_score, int):
        observations.append(
            _observation(
                entity_type="match",
                entity_source_id=str(match_id),
                entity_identity_hints=identity_hints,
                metric_name="home_score",
                value=home_score,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
            )
        )
    if isinstance(away_score, int):
        observations.append(
            _observation(
                entity_type="match",
                entity_source_id=str(match_id),
                entity_identity_hints=identity_hints,
                metric_name="away_score",
                value=away_score,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
            )
        )
    return observations


def parse_match_events(
    payload: Any,
    *,
    match_id: str,
    competition_code: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    """Deep per-player-per-match metrics derived from one match's event log.

    A player only receives a metric observation (including a real `0`) when
    they are known to have appeared in the match (tagged on at least one
    event) -- a player never mentioned in the event log gets no observation
    at all, correctly represented as missing rather than a fabricated zero.
    """

    if not isinstance(payload, list):
        return []

    reference = f"data/events/{match_id}.json"
    now = _fallback_now()

    player_counts: dict[int, dict[str, int | float]] = defaultdict(lambda: defaultdict(int))
    player_team: dict[int, int] = {}
    player_name: dict[int, str] = {}
    team_name: dict[int, str] = {}
    formation_by_team: dict[int, str] = {}
    lineup_starters: dict[int, set[int]] = defaultdict(set)

    for event in payload:
        if not isinstance(event, dict):
            continue
        _record_participant(event, player_team, player_name, team_name)
        type_name = event.get("type", {}).get("name")

        if type_name == "Starting XI":
            _record_starting_xi(event, formation_by_team, lineup_starters, player_name, player_team)
            continue
        if type_name == "Shot":
            _count_shot(event, player_counts)
        elif type_name == "Pass":
            _count_pass(event, player_counts)
        elif type_name == "Interception":
            _increment(event, player_counts, "interceptions")
        elif type_name == "Clearance":
            _increment(event, player_counts, "clearances")
        elif type_name == "Block":
            _increment(event, player_counts, "blocks")
        elif type_name == "Dribble":
            _count_dribble(event, player_counts)
        elif type_name == "Duel":
            _count_duel(event, player_counts)
        elif type_name == "Foul Committed":
            _count_foul_committed(event, player_counts)
        elif type_name == "Foul Won":
            _increment(event, player_counts, "fouls_drawn")
        elif type_name == "Goal Keeper":
            _count_goalkeeper(event, player_counts)

    # A player tagged on any event has genuinely "appeared" -- force a real
    # 0 for every count metric they never triggered, so the coverage
    # distinction between "missing" (never appeared) and "a real zero"
    # (appeared, metric simply never happened) holds for every metric, not
    # just the ones a given player happened to record.
    for player_id in player_team:
        counts = player_counts[player_id]
        for metric_name in _COUNT_METRIC_NAMES:
            if metric_name not in counts:
                counts[metric_name] = 0

    observations: list[NormalizedObservation] = []
    team_counts: dict[int, dict[str, int | float]] = defaultdict(lambda: defaultdict(int))

    for player_id, counts in player_counts.items():
        team_id = player_team.get(player_id)
        for metric_name, value in counts.items():
            observations.append(
                _observation(
                    entity_type="player",
                    entity_source_id=f"{match_id}:{player_id}",
                    entity_identity_hints={
                        "name": player_name.get(player_id, ""),
                        "match_external_id": str(match_id),
                        "competition_external_id": competition_code,
                    },
                    metric_name=metric_name,
                    value=value,
                    observed_at=now,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                )
            )
            if team_id is not None and metric_name in _TEAM_ROLLUP_METRICS:
                team_counts[team_id][metric_name] += value

    for team_id, counts in team_counts.items():
        for metric_name, value in counts.items():
            observations.append(
                _observation(
                    entity_type="team",
                    entity_source_id=f"{match_id}:{team_id}",
                    entity_identity_hints={
                        "name": team_name.get(team_id, ""),
                        "match_external_id": str(match_id),
                        "competition_external_id": competition_code,
                    },
                    metric_name=_TEAM_METRIC_NAME.get(metric_name, metric_name),
                    value=value,
                    observed_at=now,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                )
            )

    for team_id, formation in formation_by_team.items():
        observations.append(
            _observation(
                entity_type="team",
                entity_source_id=f"{match_id}:{team_id}",
                entity_identity_hints={
                    "name": team_name.get(team_id, ""),
                    "match_external_id": str(match_id),
                    "competition_external_id": competition_code,
                },
                metric_name="formation",
                value=formation,
                observed_at=now,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
            )
        )

    all_starters = {player_id for starters in lineup_starters.values() for player_id in starters}
    for player_id in player_team:
        # Confirmed Starting XI membership is a real True; any other player
        # who is known to have appeared (tagged on an event) is a confirmed
        # substitute, a real False -- never a guess for players we never
        # saw at all.
        started = player_id in all_starters
        observations.append(
            _observation(
                entity_type="player",
                entity_source_id=f"{match_id}:{player_id}",
                entity_identity_hints={
                    "name": player_name.get(player_id, ""),
                    "match_external_id": str(match_id),
                    "competition_external_id": competition_code,
                },
                metric_name="started",
                value=started,
                observed_at=now,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
            )
        )

    return observations


_TEAM_ROLLUP_METRICS = frozenset(
    {
        "shots_total",
        "shots_on_target",
        "passes_total",
        "passes_accurate",
        "fouls_committed",
        "yellow_cards",
        "red_cards",
        "saves",
    }
)

# TeamMatchStatsRecord names "fouls" (not "fouls_committed") and
# "goalkeeper_saves" (not "saves") at team granularity.
_TEAM_METRIC_NAME: dict[str, str] = {
    "fouls_committed": "fouls",
    "saves": "goalkeeper_saves",
}


def _record_participant(
    event: dict[str, Any],
    player_team: dict[int, int],
    player_name: dict[int, str],
    team_name: dict[int, str],
) -> None:
    team = event.get("team")
    if isinstance(team, dict):
        team_id = team.get("id")
        name = team.get("name")
        if isinstance(team_id, int) and isinstance(name, str):
            team_name[team_id] = name
    player = event.get("player")
    if isinstance(player, dict) and isinstance(team, dict):
        player_id = player.get("id")
        name = player.get("name")
        team_id = team.get("id")
        if isinstance(player_id, int) and isinstance(team_id, int):
            player_team[player_id] = team_id
            if isinstance(name, str):
                player_name[player_id] = name


def _record_starting_xi(
    event: dict[str, Any],
    formation_by_team: dict[int, str],
    lineup_starters: dict[int, set[int]],
    player_name: dict[int, str],
    player_team: dict[int, int],
) -> None:
    team = event.get("team", {})
    team_id = team.get("id")
    tactics = event.get("tactics", {})
    formation_raw = tactics.get("formation")
    if isinstance(team_id, int) and isinstance(formation_raw, int):
        formation_by_team[team_id] = _format_formation(formation_raw)
    lineup = tactics.get("lineup")
    if isinstance(team_id, int) and isinstance(lineup, list):
        for entry in lineup:
            if not isinstance(entry, dict):
                continue
            player = entry.get("player", {})
            player_id = player.get("id")
            if isinstance(player_id, int):
                lineup_starters[team_id].add(player_id)
                player_team[player_id] = team_id
                name = player.get("name")
                if isinstance(name, str):
                    player_name[player_id] = name


def _format_formation(raw: int) -> str:
    digits = str(raw)
    return "-".join(digits)


def _increment(
    event: dict[str, Any],
    counts: dict[int, dict[str, int | float]],
    metric_name: str,
    amount: int = 1,
) -> None:
    player = event.get("player")
    if not isinstance(player, dict):
        return
    player_id = player.get("id")
    if isinstance(player_id, int):
        counts[player_id][metric_name] += amount


def _count_shot(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    shot = event.get("shot")
    if not isinstance(shot, dict):
        return
    _increment(event, counts, "shots_total")
    outcome = shot.get("outcome", {}).get("name")
    if outcome in _ON_TARGET_SHOT_OUTCOMES:
        _increment(event, counts, "shots_on_target")
    if outcome == _GOAL_SHOT_OUTCOME:
        _increment(event, counts, "goals")
    xg = shot.get("statsbomb_xg")
    if isinstance(xg, int | float):
        player = event.get("player", {})
        player_id = player.get("id")
        if isinstance(player_id, int):
            existing = counts[player_id].get("advanced.xg", 0.0)
            counts[player_id]["advanced.xg"] = round(float(existing) + float(xg), 4)


def _count_pass(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    pass_block = event.get("pass")
    if not isinstance(pass_block, dict):
        return
    _increment(event, counts, "passes_total")
    if pass_block.get("outcome") is None:
        _increment(event, counts, "passes_accurate")
    if pass_block.get(_SHOT_ASSIST_KIND) is True:
        _increment(event, counts, "key_passes")


def _count_dribble(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    dribble = event.get("dribble")
    if not isinstance(dribble, dict):
        return
    _increment(event, counts, "dribbles_attempted")
    if dribble.get("outcome", {}).get("name") == _DRIBBLE_COMPLETE_OUTCOME:
        _increment(event, counts, "dribbles_successful")


def _count_duel(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    duel = event.get("duel")
    if not isinstance(duel, dict):
        return
    if duel.get("type", {}).get("name") == _TACKLE_DUEL_TYPE:
        _increment(event, counts, "tackles")


def _count_foul_committed(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    _increment(event, counts, "fouls_committed")
    foul = event.get("foul_committed")
    card_name = foul.get("card", {}).get("name") if isinstance(foul, dict) else None
    if card_name == _YELLOW_CARD_NAME:
        _increment(event, counts, "yellow_cards")
    elif card_name in _RED_CARD_NAMES:
        _increment(event, counts, "red_cards")


def _count_goalkeeper(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    goalkeeper = event.get("goalkeeper")
    if not isinstance(goalkeeper, dict):
        return
    if goalkeeper.get("type", {}).get("name") == _SAVE_GOALKEEPER_TYPE:
        _increment(event, counts, "saves")


def _observation(
    *,
    entity_type: EntityType,
    entity_source_id: str,
    entity_identity_hints: dict[str, str],
    metric_name: str,
    value: Any,
    observed_at: datetime,
    source_reference: str,
    ingestion_run_id: int | None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=SOURCE_CODE,
        source_type=SOURCE_TYPE,
        entity_type=entity_type,
        entity_source_id=entity_source_id,
        entity_identity_hints=entity_identity_hints,
        metric_name=metric_name,
        value=value,
        observed_at=observed_at,
        source_timestamp=observed_at,
        source_reference=source_reference,
        ingestion_run_id=ingestion_run_id,
        semantic_version=SEMANTIC_VERSION,
    )


def _fallback_now() -> datetime:
    return datetime.now(UTC)
