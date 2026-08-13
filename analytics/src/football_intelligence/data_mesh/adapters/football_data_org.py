"""football-data.org payload -> NormalizedObservation adapter.

Free-tier facts only: competitions, fixtures, results, standings context.
No deep player statistics are claimed (the Free tier does not expose them).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from football_intelligence.data_mesh.models import NormalizedObservation, SourceType
from football_intelligence.data_mesh.timeparse import parse_utc_timestamp

SOURCE_CODE = "football-data-org"
SOURCE_TYPE: SourceType = "objective_structured"
SEMANTIC_VERSION = "football-data-org-v0.1"

_FINISHED_STATUSES = frozenset({"FINISHED"})


def parse_competitions(
    payload: dict[str, Any], *, ingestion_run_id: int | None
) -> list[NormalizedObservation]:
    competitions = payload.get("competitions")
    if not isinstance(competitions, list):
        return []

    observations: list[NormalizedObservation] = []
    for item in competitions:
        if not isinstance(item, dict):
            continue
        competition_id = item.get("id")
        name = item.get("name")
        code = item.get("code")
        if competition_id is None or not isinstance(name, str) or not name.strip():
            continue
        observations.append(
            NormalizedObservation(
                source_code=SOURCE_CODE,
                source_type=SOURCE_TYPE,
                entity_type="competition",
                entity_source_id=str(competition_id),
                entity_identity_hints={
                    "name": name.strip(),
                    "provider_code": str(code) if isinstance(code, str) else "",
                },
                metric_name="name",
                value=name.strip(),
                observed_at=_now(),
                source_timestamp=None,
                source_reference="v4/competitions",
                ingestion_run_id=ingestion_run_id,
                semantic_version=SEMANTIC_VERSION,
            )
        )
    return observations


def parse_matches(
    payload: dict[str, Any],
    *,
    competition_code: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    matches = payload.get("matches")
    if not isinstance(matches, list):
        return []

    observations: list[NormalizedObservation] = []
    for item in matches:
        observations.extend(
            _parse_match(item, competition_code=competition_code, ingestion_run_id=ingestion_run_id)
        )
    return observations


def _parse_match(
    item: Any,
    *,
    competition_code: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    if not isinstance(item, dict):
        return []

    match_id = item.get("id")
    home_team = item.get("homeTeam", {}).get("name")
    away_team = item.get("awayTeam", {}).get("name")
    status = item.get("status")
    kickoff = item.get("utcDate")
    if match_id is None or not isinstance(home_team, str) or not isinstance(away_team, str):
        return []

    observed_at = parse_utc_timestamp(kickoff)
    if observed_at is None:
        return []

    reference = f"v4/competitions/{competition_code}/matches"
    identity_hints = {
        "competition_external_id": competition_code,
        "home_team_name": home_team,
        "away_team_name": away_team,
        "kickoff_date": observed_at.date().isoformat(),
    }

    def observation(metric_name: str, value: Any) -> NormalizedObservation:
        return NormalizedObservation(
            source_code=SOURCE_CODE,
            source_type=SOURCE_TYPE,
            entity_type="match",
            entity_source_id=str(match_id),
            entity_identity_hints=identity_hints,
            metric_name=metric_name,
            value=value,
            observed_at=observed_at,
            source_timestamp=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
            semantic_version=SEMANTIC_VERSION,
        )

    observations = [
        observation("status", "finished" if status in _FINISHED_STATUSES else "not_finished"),
    ]
    score = item.get("score", {}).get("fullTime", {})
    home_score = score.get("home")
    away_score = score.get("away")
    if isinstance(home_score, int):
        observations.append(observation("home_score", home_score))
    if isinstance(away_score, int):
        observations.append(observation("away_score", away_score))
    return observations


def _now() -> datetime:
    return datetime.now(UTC)
