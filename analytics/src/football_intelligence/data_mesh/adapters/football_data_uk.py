"""Football-Data.co.uk results CSV -> NormalizedObservation adapter.

Column semantics verified live during Block 15 implementation against the
site's own published key (https://www.football-data.co.uk/notes.txt) and
real current-season CSV downloads. Only columns with an unambiguous,
documented definition are mapped; odds/betting columns (the majority of each
file) are never mapped into objective football performance metrics.

Every row in these files is a completed result -- the site describes them as
"Current results (full time, half time)" -- so `status` is set to
"finished" for every row, not inferred per-row from a column that does not
exist.

The site provides no numeric match or team identifier, so `entity_source_id`
values here are deterministic composite keys built from the fields the CSV
actually provides (date + team names for a match; the raw team name for a
team) -- synthetic in the sense that Football-Data.co.uk did not hand them
to us directly, but fully reproducible from real published data, not
invented.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime
from typing import Any

from football_intelligence.data_mesh.models import EntityType, NormalizedObservation, SourceType

SOURCE_CODE = "football-data-uk"
SOURCE_TYPE: SourceType = "objective_structured"
SEMANTIC_VERSION = "football-data-uk-v1"

# Football-Data.co.uk's own published acknowledgements (notes.txt) name a
# different original source for Italian match statistics (Gazzetta.it) than
# for most other leagues (BBC, Flashscore, ESPN Soccer, Bundesliga.de,
# Football.fr). Shot counts in particular are known to be sourced/collected
# differently across leagues on this site, so Italian Serie A shot metrics
# carry a distinct semantic version -- they should not be blindly treated as
# directly comparable to another league's shot counts from this same file
# format without accounting for that documented source difference.
_ITALIAN_SHOTS_SEMANTIC_VERSION = "football-data-uk-shots-ITA-v1"
_ITALIAN_DIVISION_CODE = "I1"

# HS/AS = shots, HST/AST = shots on target, HF/AF = fouls committed,
# HC/AC = corners, HY/AY = yellow cards, HR/AR = red cards. Only these six
# team-level pairs have an unambiguous, exact `TeamMatchStatsRecord` match.
# HO/AO (offsides) is a documented column but not published in the current
# season files probed during implementation -- left unmapped rather than
# guessed. Betting/odds columns (the bulk of each file) are never mapped.
_TEAM_STAT_COLUMN_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("HS", "AS", "shots_total"),
    ("HST", "AST", "shots_on_target"),
    ("HF", "AF", "fouls"),
    ("HC", "AC", "corners"),
    ("HY", "AY", "yellow_cards"),
    ("HR", "AR", "red_cards"),
)


def parse_results_csv(
    csv_text: str,
    *,
    division_code: str,
    season_code: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    """Parse a results CSV.

    `season_code` is the site's own compressed file-path code (e.g.
    `"2526"` in `mmz4281/2526/E0.csv`) -- preserved verbatim in
    `source_reference` for accurate provenance, but converted to the
    cross-year `"2025-2026"` form for entity-resolution identity hints so it
    aligns with what `normalize_season_label` (and every other adapter)
    expects; passing the raw compressed code through unconverted would be
    misread as a literal 4-digit year.
    """

    reader = csv.DictReader(io.StringIO(csv_text))
    observations: list[NormalizedObservation] = []
    now = datetime.now(UTC)
    season_label = _season_code_to_label(season_code)

    for row in reader:
        parsed = _parse_row(
            row,
            division_code=division_code,
            season_code=season_code,
            season_label=season_label,
            ingestion_run_id=ingestion_run_id,
            fetched_at=now,
        )
        observations.extend(parsed)

    return observations


def _season_code_to_label(season_code: str) -> str:
    """`"2526"` -> `"2025-2026"`. Falls back to the raw code if malformed."""

    if len(season_code) == 4 and season_code.isdigit():
        first_year = 2000 + int(season_code[:2])
        second_year = 2000 + int(season_code[2:])
        return f"{first_year}-{second_year}"
    return season_code


def _parse_row(
    row: dict[str, str | None],
    *,
    division_code: str,
    season_code: str,
    season_label: str,
    ingestion_run_id: int | None,
    fetched_at: datetime,
) -> list[NormalizedObservation]:
    home_team = _text(row.get("HomeTeam"))
    away_team = _text(row.get("AwayTeam"))
    kickoff_date = _parse_uk_date(row.get("Date"))
    if home_team is None or away_team is None or kickoff_date is None:
        return []

    reference = f"mmz4281/{season_code}/{division_code}.csv"
    kickoff_iso = kickoff_date.isoformat()
    match_id = f"{division_code}:{kickoff_iso}:{home_team}:{away_team}"
    match_identity_hints = {
        "competition_external_id": division_code,
        "season_label": season_label,
        "home_team_name": home_team,
        "away_team_name": away_team,
        "kickoff_date": kickoff_iso,
    }

    observations: list[NormalizedObservation] = [
        _observation(
            entity_type="team",
            entity_source_id=home_team,
            identity_hints={"name": home_team, "competition_external_id": division_code},
            metric_name="name",
            value=home_team,
            observed_at=fetched_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
            semantic_version=SEMANTIC_VERSION,
        ),
        _observation(
            entity_type="team",
            entity_source_id=away_team,
            identity_hints={"name": away_team, "competition_external_id": division_code},
            metric_name="name",
            value=away_team,
            observed_at=fetched_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
            semantic_version=SEMANTIC_VERSION,
        ),
        _observation(
            entity_type="match",
            entity_source_id=match_id,
            identity_hints=match_identity_hints,
            metric_name="status",
            value="finished",
            observed_at=fetched_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
            semantic_version=SEMANTIC_VERSION,
        ),
    ]

    home_goals = _stat_int(row.get("FTHG"))
    away_goals = _stat_int(row.get("FTAG"))
    if home_goals is not None:
        observations.append(
            _observation(
                entity_type="match",
                entity_source_id=match_id,
                identity_hints=match_identity_hints,
                metric_name="home_score",
                value=home_goals,
                observed_at=fetched_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                semantic_version=SEMANTIC_VERSION,
            )
        )
    if away_goals is not None:
        observations.append(
            _observation(
                entity_type="match",
                entity_source_id=match_id,
                identity_hints=match_identity_hints,
                metric_name="away_score",
                value=away_goals,
                observed_at=fetched_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                semantic_version=SEMANTIC_VERSION,
            )
        )

    home_team_identity_hints = {
        "name": home_team,
        "competition_external_id": division_code,
        "match_external_id": match_id,
    }
    away_team_identity_hints = {
        "name": away_team,
        "competition_external_id": division_code,
        "match_external_id": match_id,
    }
    for home_column, away_column, metric_name in _TEAM_STAT_COLUMN_PAIRS:
        semantic_version = (
            _ITALIAN_SHOTS_SEMANTIC_VERSION
            if division_code == _ITALIAN_DIVISION_CODE and metric_name.startswith("shots_")
            else SEMANTIC_VERSION
        )
        home_value = _stat_int(row.get(home_column))
        if home_value is not None:
            observations.append(
                _observation(
                    entity_type="team",
                    entity_source_id=home_team,
                    identity_hints=home_team_identity_hints,
                    metric_name=metric_name,
                    value=home_value,
                    observed_at=fetched_at,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                    semantic_version=semantic_version,
                )
            )
        away_value = _stat_int(row.get(away_column))
        if away_value is not None:
            observations.append(
                _observation(
                    entity_type="team",
                    entity_source_id=away_team,
                    identity_hints=away_team_identity_hints,
                    metric_name=metric_name,
                    value=away_value,
                    observed_at=fetched_at,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                    semantic_version=semantic_version,
                )
            )

    return observations


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
    semantic_version: str,
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
        semantic_version=semantic_version,
    )


def _text(value: str | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _stat_int(value: str | None) -> int | None:
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _parse_uk_date(value: str | None) -> date | None:
    text = _text(value)
    if text is None:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
