"""TheSportsDB payload -> NormalizedObservation adapter.

Only fields TheSportsDB's free `eventsseason.php` endpoint actually returns
are parsed. A missing/blank field never becomes a fabricated statistic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from football_intelligence.data_mesh.models import EntityType, NormalizedObservation, SourceType
from football_intelligence.data_mesh.timeparse import parse_date, parse_utc_timestamp

SOURCE_CODE = "thesportsdb"
SOURCE_TYPE: SourceType = "objective_structured"
SEMANTIC_VERSION = "data-mesh-v0.1"

JsonObject = dict[str, Any]

# TheSportsDB's free `strStatus` vocabulary is undocumented and inconsistent
# across sports, so only values with an unambiguous, verified meaning are
# mapped to the cross-source `is_finished` metric. Anything else (postponed,
# cancelled, suspended, blank, or any unrecognized code) produces no
# observation at all -- missing, not a guessed value. The raw string is
# still available in the stored raw payload for audit.
_FINISHED_STATUSES = frozenset({"FT", "AET", "PEN"})
_NOT_FINISHED_STATUSES = frozenset({"NS", "1H", "HT", "2H", "ET", "BT"})


def is_finished_status(status: str | None) -> bool | None:
    if status in _FINISHED_STATUSES:
        return True
    if status in _NOT_FINISHED_STATUSES:
        return False
    return None


def parse_league_events(
    payload: JsonObject,
    *,
    competition_external_id: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    """Parse `eventsseason.php` events into match/team/competition observations.

    Note: `strTimestamp` has no explicit UTC offset in TheSportsDB's payload,
    but it has been observed to match OpenLigaDB's `matchDateTimeUTC` exactly
    for the same fixtures, so it is treated as UTC here. This is an inferred
    behavior of an undocumented field, not an official guarantee.
    """

    events = payload.get("events")
    if not isinstance(events, list):
        return []

    observations: list[NormalizedObservation] = []
    competition_name: str | None = None
    for item in events:
        if competition_name is None and isinstance(item, dict):
            league_name = item.get("strLeague")
            if isinstance(league_name, str) and league_name.strip():
                competition_name = league_name.strip()
        observations.extend(
            _parse_event(
                item,
                competition_external_id=competition_external_id,
                ingestion_run_id=ingestion_run_id,
            )
        )

    if competition_name is not None:
        observations.append(
            NormalizedObservation(
                source_code=SOURCE_CODE,
                source_type=SOURCE_TYPE,
                entity_type="competition",
                entity_source_id=competition_external_id,
                entity_identity_hints={"name": competition_name},
                metric_name="name",
                value=competition_name,
                observed_at=_now_reference(events),
                source_timestamp=None,
                source_reference=f"eventsseason.php?id={competition_external_id}",
                ingestion_run_id=ingestion_run_id,
                semantic_version=SEMANTIC_VERSION,
            )
        )

    return observations


def _parse_event(
    item: Any,
    *,
    competition_external_id: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    if not isinstance(item, dict):
        return []

    event_id = _text(item.get("idEvent"))
    home_team_id = _text(item.get("idHomeTeam"))
    away_team_id = _text(item.get("idAwayTeam"))
    home_team_name = _text(item.get("strHomeTeam"))
    away_team_name = _text(item.get("strAwayTeam"))
    date_event = item.get("dateEvent")
    season = _text(item.get("strSeason"))
    status = _text(item.get("strStatus"))

    if not all((event_id, home_team_id, away_team_id, home_team_name, away_team_name)):
        return []

    observed_at = parse_utc_timestamp(item.get("strTimestamp")) or _midnight(date_event)
    if observed_at is None:
        return []

    reference = f"eventsseason.php?id={competition_external_id}"
    identity_hints = {
        "competition_external_id": competition_external_id,
        "season_label": season or "",
        "home_team_name": home_team_name or "",
        "away_team_name": away_team_name or "",
        "kickoff_date": (parse_date(date_event) or observed_at.date()).isoformat(),
    }

    def observation(
        *,
        entity_type: EntityType,
        entity_source_id: str,
        entity_identity_hints: dict[str, str],
        metric_name: str,
        value: Any,
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
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
            semantic_version=SEMANTIC_VERSION,
        )

    observations = [
        observation(
            entity_type="team",
            entity_source_id=home_team_id or "",
            entity_identity_hints={
                "name": home_team_name or "",
                "competition_external_id": competition_external_id,
            },
            metric_name="name",
            value=home_team_name,
        ),
        observation(
            entity_type="team",
            entity_source_id=away_team_id or "",
            entity_identity_hints={
                "name": away_team_name or "",
                "competition_external_id": competition_external_id,
            },
            metric_name="name",
            value=away_team_name,
        ),
    ]

    is_finished = is_finished_status(status)
    if is_finished is not None:
        observations.append(
            observation(
                entity_type="match",
                entity_source_id=event_id or "",
                entity_identity_hints=identity_hints,
                metric_name="is_finished",
                value=is_finished,
            )
        )

    home_score = _score(item.get("intHomeScore"))
    away_score = _score(item.get("intAwayScore"))
    if home_score is not None:
        observations.append(
            observation(
                entity_type="match",
                entity_source_id=event_id or "",
                entity_identity_hints=identity_hints,
                metric_name="home_score",
                value=home_score,
            )
        )
    if away_score is not None:
        observations.append(
            observation(
                entity_type="match",
                entity_source_id=event_id or "",
                entity_identity_hints=identity_hints,
                metric_name="away_score",
                value=away_score,
            )
        )

    return observations


# `lookupeventstats.php` (v1 Free, documented): verified live during Block 15
# implementation to return at most 5 stat rows per match, consistently:
# "Shots on Goal", "Shots off Goal", "Total Shots", "Blocked Shots",
# "Shots insidebox". Only names with an unambiguous, exact
# `TeamMatchStatsRecord` match are mapped. "Shots off Goal" is deliberately
# NOT mapped to `shots_outside_box` -- off-target and outside-the-box are
# different classifications, not the same statistic under a different name.
_EVENT_STAT_METRIC_MAP: dict[str, str] = {
    "Shots on Goal": "shots_on_target",
    "Total Shots": "shots_total",
    "Blocked Shots": "blocked_shots",
    "Shots insidebox": "shots_inside_box",
}

# `lookuplineup.php` (v1 Free, documented): verified live to return at most 5
# player rows per match -- a real, useful sample, never a complete lineup.
_SUBSTITUTE_TRUE = "yes"
_SUBSTITUTE_FALSE = "no"


def parse_event_stats(
    payload: JsonObject,
    *,
    match_id: str,
    competition_external_id: str,
    home_team_external_id: str,
    away_team_external_id: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    """Parse `lookupeventstats.php` into team-level match-stat observations.

    Only the 4 verified, exact-semantics fields in `_EVENT_STAT_METRIC_MAP`
    are mapped -- anything else returned by the endpoint is ignored, never
    guessed into an existing metric it does not actually match.
    """

    rows = payload.get("eventstats")
    if not isinstance(rows, list):
        return []

    reference = f"lookupeventstats.php?id={match_id}"
    now = datetime.now(UTC)
    observations: list[NormalizedObservation] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metric_name = _EVENT_STAT_METRIC_MAP.get(_text(row.get("strStat")) or "")
        if metric_name is None:
            continue
        home_value = _stat_int(row.get("intHome"))
        away_value = _stat_int(row.get("intAway"))
        identity_hints = {
            "competition_external_id": competition_external_id,
            "match_external_id": match_id,
        }
        if home_value is not None:
            observations.append(
                NormalizedObservation(
                    source_code=SOURCE_CODE,
                    source_type=SOURCE_TYPE,
                    entity_type="team",
                    entity_source_id=home_team_external_id,
                    entity_identity_hints=identity_hints,
                    metric_name=metric_name,
                    value=home_value,
                    observed_at=now,
                    source_timestamp=None,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                    semantic_version=SEMANTIC_VERSION,
                )
            )
        if away_value is not None:
            observations.append(
                NormalizedObservation(
                    source_code=SOURCE_CODE,
                    source_type=SOURCE_TYPE,
                    entity_type="team",
                    entity_source_id=away_team_external_id,
                    entity_identity_hints=identity_hints,
                    metric_name=metric_name,
                    value=away_value,
                    observed_at=now,
                    source_timestamp=None,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                    semantic_version=SEMANTIC_VERSION,
                )
            )
    return observations


def parse_lineup(
    payload: JsonObject,
    *,
    match_id: str,
    competition_external_id: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    """Parse `lookuplineup.php` into player_appearance-granularity observations.

    Capped at 5 player rows by the Free API itself -- real evidence, but
    never treated as a complete lineup by the caller (see
    `provider_capabilities`: these metrics are permanently `partial`).
    """

    rows = payload.get("lineup")
    if not isinstance(rows, list):
        return []

    reference = f"lookuplineup.php?id={match_id}"
    now = datetime.now(UTC)
    observations: list[NormalizedObservation] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        player_id = _text(row.get("idPlayer"))
        if player_id is None:
            continue
        identity_hints = {
            "name": _text(row.get("strPlayer")) or "",
            "match_external_id": match_id,
            "competition_external_id": competition_external_id,
            "team_external_id": _text(row.get("idTeam")) or "",
        }

        position = _text(row.get("strPosition"))
        if position is not None:
            observations.append(
                _lineup_observation(
                    player_id=player_id,
                    identity_hints=identity_hints,
                    metric_name="listed_position",
                    value=position,
                    observed_at=now,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                )
            )

        substitute = _text(row.get("strSubstitute"))
        if substitute is not None and substitute.casefold() in (
            _SUBSTITUTE_TRUE,
            _SUBSTITUTE_FALSE,
        ):
            started = substitute.casefold() == _SUBSTITUTE_FALSE
            observations.append(
                _lineup_observation(
                    player_id=player_id,
                    identity_hints=identity_hints,
                    metric_name="started",
                    value=started,
                    observed_at=now,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                )
            )

        shirt_number = _stat_int(row.get("intSquadNumber"))
        if shirt_number is not None:
            observations.append(
                _lineup_observation(
                    player_id=player_id,
                    identity_hints=identity_hints,
                    metric_name="shirt_number",
                    value=shirt_number,
                    observed_at=now,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                )
            )

    return observations


def _lineup_observation(
    *,
    player_id: str,
    identity_hints: dict[str, str],
    metric_name: str,
    value: Any,
    observed_at: datetime,
    source_reference: str,
    ingestion_run_id: int | None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=SOURCE_CODE,
        source_type=SOURCE_TYPE,
        entity_type="player",
        entity_source_id=player_id,
        entity_identity_hints=identity_hints,
        metric_name=metric_name,
        value=value,
        observed_at=observed_at,
        source_timestamp=None,
        source_reference=source_reference,
        ingestion_run_id=ingestion_run_id,
        semantic_version=SEMANTIC_VERSION,
    )


def _stat_int(value: Any) -> int | None:
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _score(value: Any) -> int | None:
    # TheSportsDB reports scores as numeric strings; missing scores are `None`
    # or blank, never fabricated as zero.
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _midnight(date_event: Any) -> datetime | None:
    parsed = parse_date(date_event)
    if parsed is None:
        return None
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def _now_reference(events: list[Any]) -> datetime:
    for item in events:
        if isinstance(item, dict):
            observed = parse_utc_timestamp(item.get("strTimestamp"))
            if observed is not None:
                return observed
    return datetime.now(UTC)
