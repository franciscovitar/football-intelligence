"""RSSSF Argentina 2016 fixture/result evidence -> NormalizedObservation.

The adapter is intentionally narrow: match identity/context and final result
only. RSSSF's top-flight 2016 fixture list does not provide regular-round
player participation, so this module never emits player observations, minutes,
starts, lineups or player statistics.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from football_intelligence.data_mesh.models import EntityType, NormalizedObservation, SourceType
from football_intelligence.metric_catalog.types import MetricGranularity
from football_intelligence.providers.rsssf import (
    RSSSF_ARGENTINA_2016_COMPETITION_ID,
    RSSSF_ARGENTINA_2016_SEASON_LABEL,
    RSSSFArgentina2016Snapshot,
    RSSSFMatch,
)

SOURCE_CODE = "rsssf"
SOURCE_TYPE: SourceType = "objective_web"
SEMANTIC_VERSION = "rsssf-arg-2016-v1"


def adapt_argentina_2016_snapshot(
    snapshot: RSSSFArgentina2016Snapshot,
    *,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    observations: list[NormalizedObservation] = []
    for match in snapshot.matches:
        observations.extend(
            _adapt_match(
                match,
                observed_at=snapshot.fetched_at,
                source_reference=snapshot.source_url,
                ingestion_run_id=ingestion_run_id,
            )
        )
    return observations


def _round_name(match: RSSSFMatch) -> str:
    if match.phase == "final":
        return "Round 17 — Final"
    if match.phase == "third_place_playoff":
        return "Round 17 — Third Position"
    if match.subgroup is None:
        return f"Round {match.round_number}"
    return f"Round {match.round_number} — {match.subgroup}"


def _adapt_match(
    match: RSSSFMatch,
    *,
    observed_at: datetime,
    source_reference: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    kickoff_date = match.match_date.isoformat()
    match_hints = {
        "match_external_id": match.external_id,
        "competition_external_id": RSSSF_ARGENTINA_2016_COMPETITION_ID,
        "season_label": RSSSF_ARGENTINA_2016_SEASON_LABEL,
        "home_team_external_id": match.home_team,
        "home_team_name": match.home_team,
        "away_team_external_id": match.away_team,
        "away_team_name": match.away_team,
        "kickoff_date": kickoff_date,
    }

    observations = [
        _observation(
            entity_type="team",
            entity_source_id=match.home_team,
            identity_hints={
                "name": match.home_team,
                "team_external_id": match.home_team,
                "team_name": match.home_team,
                "competition_external_id": RSSSF_ARGENTINA_2016_COMPETITION_ID,
            },
            metric_name="name",
            value=match.home_team,
            metric_granularity="team",
            observed_at=observed_at,
            source_reference=source_reference,
            ingestion_run_id=ingestion_run_id,
        ),
        _observation(
            entity_type="team",
            entity_source_id=match.away_team,
            identity_hints={
                "name": match.away_team,
                "team_external_id": match.away_team,
                "team_name": match.away_team,
                "competition_external_id": RSSSF_ARGENTINA_2016_COMPETITION_ID,
            },
            metric_name="name",
            value=match.away_team,
            metric_granularity="team",
            observed_at=observed_at,
            source_reference=source_reference,
            ingestion_run_id=ingestion_run_id,
        ),
    ]

    match_values: tuple[tuple[str, str | int], ...] = (
        ("status", "finished"),
        ("round_name", _round_name(match)),
        ("venue_name", match.venue),
        ("home_score", match.home_score),
        ("away_score", match.away_score),
    )
    for metric_name, value in match_values:
        observations.append(
            _observation(
                entity_type="match",
                entity_source_id=match.external_id,
                identity_hints=match_hints,
                metric_name=metric_name,
                value=value,
                metric_granularity="match",
                observed_at=observed_at,
                source_reference=source_reference,
                ingestion_run_id=ingestion_run_id,
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
    metric_granularity: MetricGranularity,
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
        metric_granularity=metric_granularity,
    )
