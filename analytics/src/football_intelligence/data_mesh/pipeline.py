"""Shared resolve-then-reconcile orchestration for Data Mesh jobs.

Extracted from the Block 13 Data Mesh PoC job so the Zero-Cost Coverage Lab
job (Block 15) can reconcile TheSportsDB against Football-Data.co.uk using
the exact same entity-resolution/date-tolerance/grouping pipeline as the
original PoC used for TheSportsDB against OpenLigaDB -- one implementation,
not a parallel one, regardless of which sources are being combined.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date
from typing import Any

from football_intelligence.data_mesh.entity_resolution import (
    cluster_match_dates,
    resolve_competition,
    resolve_match,
    resolve_player,
    resolve_team,
)
from football_intelligence.data_mesh.models import (
    EntityResolution,
    EntityType,
    NormalizedObservation,
    ReconciliationDecision,
)
from football_intelligence.data_mesh.reconciliation import reconcile_metric
from football_intelligence.data_mesh.timeparse import normalize_season_label, parse_date

REPORT_EXAMPLE_LIMIT = 10

# (competition_code, season_label, home_team_key, away_team_key) -> per-group
# kickoff-date -> canonical clustered date.
MatchGroupKey = tuple[str, str, str, str]
MatchDateClusters = Mapping[MatchGroupKey, Mapping[date, date]]


def resolve_logical_key(
    observation: NormalizedObservation,
    *,
    match_date_clusters: MatchDateClusters,
) -> EntityResolution:
    hints = observation.entity_identity_hints

    if observation.entity_type == "competition":
        return resolve_competition(
            source_code=observation.source_code,
            external_id=observation.entity_source_id,
        )

    competition_resolution = resolve_competition(
        source_code=observation.source_code,
        external_id=hints.get("competition_external_id", ""),
    )
    if competition_resolution.status != "resolved" or competition_resolution.logical_key is None:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type=observation.entity_type,
            confidence=0.0,
            reason="competition identity not resolved",
        )
    competition_code = competition_resolution.logical_key.removeprefix("competition:")

    if observation.entity_type == "team":
        return resolve_team(name=hints.get("name", ""), competition_code=competition_code)

    if observation.entity_type == "match":
        season_label = normalize_season_label(hints.get("season_label", ""))
        home_resolution = resolve_team(
            name=hints.get("home_team_name", ""), competition_code=competition_code
        )
        away_resolution = resolve_team(
            name=hints.get("away_team_name", ""), competition_code=competition_code
        )
        kickoff_date = parse_date(hints.get("kickoff_date"))
        canonical_date = kickoff_date
        if (
            kickoff_date is not None
            and home_resolution.logical_key is not None
            and away_resolution.logical_key is not None
        ):
            group_key = (
                competition_code,
                season_label,
                home_resolution.logical_key,
                away_resolution.logical_key,
            )
            canonical_date = match_date_clusters.get(group_key, {}).get(kickoff_date, kickoff_date)
        return resolve_match(
            competition_code=competition_code,
            season_label=season_label,
            home_team_key=home_resolution.logical_key,
            away_team_key=away_resolution.logical_key,
            kickoff_date=canonical_date,
        )

    return resolve_player(
        normalized_name="",
        date_of_birth=None,
        nationality_code=None,
        team_context_key=None,
    )


def build_match_date_clusters(
    observations: list[NormalizedObservation],
) -> MatchDateClusters:
    """Precompute deterministic kickoff-date clusters per resolved match group.

    `resolve_match()` stays a pure function of its exact inputs (easy to
    test/audit), so tolerance is applied here instead: two providers
    reporting the same real fixture on adjacent dates must still converge on
    one logical match identity, and the canonical date chosen must not
    depend on which provider's observation is processed first.
    """

    dates_by_group: dict[MatchGroupKey, set[date]] = defaultdict(set)
    for observation in observations:
        if observation.entity_type != "match":
            continue
        hints = observation.entity_identity_hints
        competition_resolution = resolve_competition(
            source_code=observation.source_code,
            external_id=hints.get("competition_external_id", ""),
        )
        if (
            competition_resolution.status != "resolved"
            or competition_resolution.logical_key is None
        ):
            continue
        competition_code = competition_resolution.logical_key.removeprefix("competition:")
        season_label = normalize_season_label(hints.get("season_label", ""))
        home_resolution = resolve_team(
            name=hints.get("home_team_name", ""), competition_code=competition_code
        )
        away_resolution = resolve_team(
            name=hints.get("away_team_name", ""), competition_code=competition_code
        )
        kickoff_date = parse_date(hints.get("kickoff_date"))
        if (
            kickoff_date is None
            or home_resolution.logical_key is None
            or away_resolution.logical_key is None
        ):
            continue
        group_key = (
            competition_code,
            season_label,
            home_resolution.logical_key,
            away_resolution.logical_key,
        )
        dates_by_group[group_key].add(kickoff_date)

    return {group_key: cluster_match_dates(dates) for group_key, dates in dates_by_group.items()}


def resolve_and_reconcile(
    observations: list[NormalizedObservation],
) -> tuple[list[ReconciliationDecision], dict[str, Any]]:
    match_date_clusters = build_match_date_clusters(observations)
    grouped: dict[tuple[str, EntityType, str], list[NormalizedObservation]] = defaultdict(list)
    unresolved_examples: list[dict[str, str]] = []
    resolved_count = 0
    unresolved_count = 0

    for observation in observations:
        resolution = resolve_logical_key(observation, match_date_clusters=match_date_clusters)
        if resolution.status != "resolved" or resolution.logical_key is None:
            unresolved_count += 1
            if len(unresolved_examples) < REPORT_EXAMPLE_LIMIT:
                unresolved_examples.append(
                    {
                        "source_code": observation.source_code,
                        "entity_type": observation.entity_type,
                        "entity_source_id": observation.entity_source_id,
                        "reason": resolution.reason,
                    }
                )
            continue
        resolved_count += 1
        grouped[(resolution.logical_key, observation.entity_type, observation.metric_name)].append(
            observation
        )

    decisions = [
        reconcile_metric(
            items,
            logical_entity_key=key,
            entity_type=entity_type,
            metric_name=metric_name,
        )
        for (key, entity_type, metric_name), items in sorted(grouped.items())
    ]

    overlap_count = sum(1 for decision in decisions if decision.source_count >= 2)

    return decisions, {
        "resolved_observation_count": resolved_count,
        "unresolved_observation_count": unresolved_count,
        "unresolved_identity_examples": unresolved_examples,
        "overlap_count": overlap_count,
    }


def coverage_by_source(observations: list[NormalizedObservation]) -> dict[str, dict[str, int]]:
    coverage: dict[str, dict[str, int]] = defaultdict(dict)
    for observation in observations:
        key = f"{observation.entity_type}.{observation.metric_name}"
        per_source = coverage[observation.source_code]
        per_source[key] = per_source.get(key, 0) + 1
    return dict(coverage)
