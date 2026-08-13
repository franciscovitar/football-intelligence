"""OpenLigaDB payload -> NormalizedObservation adapter.

Only fields OpenLigaDB's public `getmatchdata` endpoint actually returns are
parsed. A missing/blank field never becomes a fabricated statistic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from football_intelligence.data_mesh.models import EntityType, NormalizedObservation, SourceType
from football_intelligence.data_mesh.timeparse import normalize_season_label, parse_utc_timestamp

SOURCE_CODE = "openligadb"
SOURCE_TYPE: SourceType = "objective_structured"
SEMANTIC_VERSION = "data-mesh-v0.1"
FINAL_RESULT_KIND = "After90Minutes"


def parse_league_matches(
    payload: Any,
    *,
    competition_external_id: str,
    ingestion_run_id: int | None,
    limit: int | None = None,
) -> list[NormalizedObservation]:
    if not isinstance(payload, list):
        return []

    items = payload[:limit] if limit is not None else payload

    observations: list[NormalizedObservation] = []
    competition_name: str | None = None
    for item in items:
        if competition_name is None and isinstance(item, dict):
            league_name = item.get("leagueName")
            if isinstance(league_name, str) and league_name.strip():
                competition_name = league_name.strip()
        observations.extend(
            _parse_match(
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
                observed_at=_now_reference(items),
                source_timestamp=None,
                source_reference=f"getmatchdata/{competition_external_id}",
                ingestion_run_id=ingestion_run_id,
                semantic_version=SEMANTIC_VERSION,
            )
        )

    return observations


def _parse_match(
    item: Any,
    *,
    competition_external_id: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    if not isinstance(item, dict):
        return []

    match_id = item.get("matchID")
    team1 = item.get("team1")
    team2 = item.get("team2")
    is_finished = item.get("matchIsFinished")
    season_label = normalize_season_label(item.get("leagueSeason"))

    if match_id is None or not isinstance(team1, dict) or not isinstance(team2, dict):
        return []

    home_team_id = team1.get("teamId")
    away_team_id = team2.get("teamId")
    home_team_name = team1.get("teamName")
    away_team_name = team2.get("teamName")
    if home_team_id is None or away_team_id is None:
        return []
    if not isinstance(home_team_name, str) or not isinstance(away_team_name, str):
        return []
    if not home_team_name.strip() or not away_team_name.strip():
        return []

    observed_at = parse_utc_timestamp(item.get("matchDateTimeUTC"))
    if observed_at is None:
        return []

    reference = f"getmatchdata/{competition_external_id}"
    identity_hints = {
        "competition_external_id": competition_external_id,
        "season_label": season_label,
        "home_team_name": home_team_name,
        "away_team_name": away_team_name,
        "kickoff_date": observed_at.date().isoformat(),
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
            entity_source_id=str(home_team_id),
            entity_identity_hints={
                "name": home_team_name,
                "competition_external_id": competition_external_id,
            },
            metric_name="name",
            value=home_team_name,
        ),
        observation(
            entity_type="team",
            entity_source_id=str(away_team_id),
            entity_identity_hints={
                "name": away_team_name,
                "competition_external_id": competition_external_id,
            },
            metric_name="name",
            value=away_team_name,
        ),
    ]

    # `matchIsFinished` is OpenLigaDB's own boolean, so it maps 1:1 onto the
    # cross-source `is_finished` metric. If the field is ever absent, that is
    # a missing observation, never a fabricated `False`.
    if isinstance(is_finished, bool):
        observations.append(
            observation(
                entity_type="match",
                entity_source_id=str(match_id),
                entity_identity_hints=identity_hints,
                metric_name="is_finished",
                value=is_finished,
            )
        )

    final_result = _final_result(item.get("matchResults"))
    if final_result is not None:
        home_score, away_score = final_result
        observations.append(
            observation(
                entity_type="match",
                entity_source_id=str(match_id),
                entity_identity_hints=identity_hints,
                metric_name="home_score",
                value=home_score,
            )
        )
        observations.append(
            observation(
                entity_type="match",
                entity_source_id=str(match_id),
                entity_identity_hints=identity_hints,
                metric_name="away_score",
                value=away_score,
            )
        )

    return observations


def _final_result(results: Any) -> tuple[int, int] | None:
    if not isinstance(results, list):
        return None
    for entry in results:
        if isinstance(entry, dict) and entry.get("resultTypeKind") == FINAL_RESULT_KIND:
            home = entry.get("pointsTeam1")
            away = entry.get("pointsTeam2")
            if isinstance(home, int) and isinstance(away, int):
                return home, away
    return None


def _now_reference(items: list[Any]) -> datetime:
    for item in items:
        if isinstance(item, dict):
            observed = parse_utc_timestamp(item.get("matchDateTimeUTC"))
            if observed is not None:
                return observed
    return datetime.now(UTC)
