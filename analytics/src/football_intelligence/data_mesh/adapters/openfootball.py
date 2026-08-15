"""OpenFootball season JSON -> NormalizedObservation adapter.

Verified live during Block 18 implementation against
`https://raw.githubusercontent.com/openfootball/football.json/master/2025-26/en.1.json`:
a top-level `{"name": ..., "matches": [...]}` shape, 380 English Premier
League 2025/26 matches. Each match reports `team1`/`team2` (full official
club names, e.g. "Manchester City FC"), `date` (`YYYY-MM-DD`), and `score`,
which is either `{"ft": [home, away], "ht": [home, away]}` (350 of 380
matches) or a bare `[home, away]` full-time-only array (30 of 380 matches,
observed for scoreless/otherwise-unbroken-down results) -- only the
full-time pair is ever used; half-time is not part of the target metric
catalog. A match with no `score` key at all (not fixed/not yet played) is
skipped entirely -- never treated as 0-0.

Only match results and team identity are derived here: OpenFootball's
public JSON does not publish shots, cards, corners or any other team-match
statistic, and it publishes no player-level data at all.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from football_intelligence.data_mesh.models import EntityType, NormalizedObservation, SourceType

SOURCE_CODE = "openfootball"
SOURCE_TYPE: SourceType = "objective_structured"
SEMANTIC_VERSION = "openfootball-v1"


def parse_season_matches(
    payload: dict[str, Any],
    *,
    competition_external_id: str,
    season_label: str,
    source_reference: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    matches = payload.get("matches")
    if not isinstance(matches, list):
        return []

    observations: list[NormalizedObservation] = []
    now = datetime.now(UTC)
    for raw_match in matches:
        if not isinstance(raw_match, dict):
            continue
        observations.extend(
            _parse_match(
                raw_match,
                competition_external_id=competition_external_id,
                season_label=season_label,
                source_reference=source_reference,
                ingestion_run_id=ingestion_run_id,
                fetched_at=now,
            )
        )
    return observations


def _parse_match(
    raw_match: dict[str, Any],
    *,
    competition_external_id: str,
    season_label: str,
    source_reference: str,
    ingestion_run_id: int | None,
    fetched_at: datetime,
) -> list[NormalizedObservation]:
    home_team = _text(raw_match.get("team1"))
    away_team = _text(raw_match.get("team2"))
    kickoff_date = _parse_iso_date(raw_match.get("date"))
    if home_team is None or away_team is None or kickoff_date is None:
        return []

    full_time = _extract_full_time_score(raw_match.get("score"))
    kickoff_iso = kickoff_date.isoformat()
    match_id = f"{competition_external_id}:{kickoff_iso}:{home_team}:{away_team}"
    match_identity_hints = {
        "competition_external_id": competition_external_id,
        "season_label": season_label,
        "home_team_name": home_team,
        "away_team_name": away_team,
        "kickoff_date": kickoff_iso,
    }

    observations: list[NormalizedObservation] = [
        _observation(
            entity_type="team",
            entity_source_id=home_team,
            identity_hints={"name": home_team, "competition_external_id": competition_external_id},
            metric_name="name",
            value=home_team,
            observed_at=fetched_at,
            source_reference=source_reference,
            ingestion_run_id=ingestion_run_id,
        ),
        _observation(
            entity_type="team",
            entity_source_id=away_team,
            identity_hints={"name": away_team, "competition_external_id": competition_external_id},
            metric_name="name",
            value=away_team,
            observed_at=fetched_at,
            source_reference=source_reference,
            ingestion_run_id=ingestion_run_id,
        ),
    ]

    if full_time is None:
        # No full-time score published for this fixture (not yet played) --
        # missing, never a guessed "finished" status or a fabricated 0-0.
        return observations

    home_goals, away_goals = full_time
    observations.extend(
        [
            _observation(
                entity_type="match",
                entity_source_id=match_id,
                identity_hints=match_identity_hints,
                metric_name="status",
                value="finished",
                observed_at=fetched_at,
                source_reference=source_reference,
                ingestion_run_id=ingestion_run_id,
            ),
            _observation(
                entity_type="match",
                entity_source_id=match_id,
                identity_hints=match_identity_hints,
                metric_name="home_score",
                value=home_goals,
                observed_at=fetched_at,
                source_reference=source_reference,
                ingestion_run_id=ingestion_run_id,
            ),
            _observation(
                entity_type="match",
                entity_source_id=match_id,
                identity_hints=match_identity_hints,
                metric_name="away_score",
                value=away_goals,
                observed_at=fetched_at,
                source_reference=source_reference,
                ingestion_run_id=ingestion_run_id,
            ),
        ]
    )
    return observations


def _extract_full_time_score(raw_score: Any) -> tuple[int, int] | None:
    if isinstance(raw_score, dict):
        pair = raw_score.get("ft")
    elif isinstance(raw_score, list):
        pair = raw_score
    else:
        return None
    if not isinstance(pair, list) or len(pair) != 2:
        return None
    home_raw, away_raw = pair
    if not isinstance(home_raw, int) or isinstance(home_raw, bool):
        return None
    if not isinstance(away_raw, int) or isinstance(away_raw, bool):
        return None
    return home_raw, away_raw


def _observation(
    *,
    entity_type: EntityType,
    entity_source_id: str,
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
        entity_type=entity_type,
        entity_source_id=entity_source_id,
        entity_identity_hints=identity_hints,
        metric_name=metric_name,
        value=value,
        observed_at=observed_at,
        source_timestamp=None,
        source_reference=source_reference,
        ingestion_run_id=ingestion_run_id,
        semantic_version=SEMANTIC_VERSION,
    )


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_iso_date(value: Any) -> date | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None
