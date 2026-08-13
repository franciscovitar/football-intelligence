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


def _is_finished(status: str | None) -> bool | None:
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

    is_finished = _is_finished(status)
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
