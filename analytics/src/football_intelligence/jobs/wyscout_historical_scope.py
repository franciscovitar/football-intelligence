"""Shared source/adapter validation for Wyscout Open historical core leagues.

This module is local/read-only. It loads one already-cached official Figshare
country payload plus the shared player/team references, verifies the published
scope counts and provider-native ids, and validates the normalized adapter
output before any PostgreSQL write is allowed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.scope import AdapterScope
from football_intelligence.data_mesh.adapters.wyscout_open import (
    DEFAULT_SCOPE,
    ESP_LL_SCOPE,
    FRA_L1_SCOPE,
    GER_BL1_SCOPE,
    ITA_SA_SCOPE,
    SOURCE_CODE,
)
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.jobs.audit_wyscout_metric_mapping import (
    WyscoutMappingAuditError,
    _find_cached_file,
    _load_local_json,
)
from football_intelligence.providers.wyscout_open_mapping import adapter_safe_mappings
from football_intelligence.providers.wyscout_open_scopes import (
    SEASON_LABEL,
    WyscoutCoreLeagueSpec,
    WyscoutScopeEvidenceError,
    core_league_spec,
    infer_provider_scope_ids,
    verify_published_scope_counts,
)


class WyscoutHistoricalScopeError(RuntimeError):
    """The selected historical scope cannot be proven safe for loading."""


@dataclass(frozen=True, slots=True)
class WyscoutHistoricalScopeConfig:
    spec: WyscoutCoreLeagueSpec
    scope: AdapterScope


@dataclass(frozen=True, slots=True)
class WyscoutHistoricalSourceValidation:
    match_count: int
    event_count: int
    roster_player_count: int
    team_count: int
    provider_competition_id: int
    provider_season_id: int
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass(frozen=True, slots=True)
class WyscoutHistoricalAdapterValidation:
    total_observations: int
    safe_identity_count: int
    identities_with_observations: int
    distinct_matches: int
    distinct_teams: int
    conflicting_duplicates: int
    native_goal_total: int
    observed_team_goal_total: int
    wrong_country_source_references: int
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


_SCOPE_BY_COMPETITION: dict[str, AdapterScope] = {
    "ENG_PL": DEFAULT_SCOPE,
    "ESP_LL": ESP_LL_SCOPE,
    "FRA_L1": FRA_L1_SCOPE,
    "GER_BL1": GER_BL1_SCOPE,
    "ITA_SA": ITA_SA_SCOPE,
}


def supported_competition_codes() -> tuple[str, ...]:
    return tuple(_SCOPE_BY_COMPETITION)


def scope_config(competition_code: str) -> WyscoutHistoricalScopeConfig:
    try:
        scope = _SCOPE_BY_COMPETITION[competition_code]
    except KeyError as exc:
        raise WyscoutHistoricalScopeError(
            f"unsupported Wyscout historical competition {competition_code!r}"
        ) from exc
    spec = core_league_spec(competition_code)
    if scope.season_label != SEASON_LABEL:
        raise WyscoutHistoricalScopeError(
            f"scope/spec season mismatch for {competition_code}: "
            f"{scope.season_label!r} != {SEASON_LABEL!r}"
        )
    return WyscoutHistoricalScopeConfig(spec=spec, scope=scope)


def _load_country_payload(cache_dir: Path, *, spec: WyscoutCoreLeagueSpec, kind: str) -> list[Any]:
    if kind not in {"matches", "events"}:
        raise ValueError(f"unsupported Wyscout country payload kind {kind!r}")
    filename = spec.match_filename if kind == "matches" else spec.event_filename
    payload = _load_local_json(
        cache_dir,
        zip_pattern=f"*{kind}.zip",
        extracted_pattern=filename,
        keyword=spec.source_file_label.casefold(),
    )
    if not isinstance(payload, list):
        raise WyscoutHistoricalScopeError(f"{filename} is not a JSON array")
    return payload


def _load_reference_payload(cache_dir: Path, pattern: str, *, label: str) -> list[Any]:
    path = _find_cached_file(cache_dir, pattern)
    with path.open("rb") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise WyscoutHistoricalScopeError(f"cached {label} payload is not a JSON array")
    return payload


def load_scope_inputs(
    cache_dir: Path, *, config: WyscoutHistoricalScopeConfig
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    try:
        matches_payload = _load_country_payload(cache_dir, spec=config.spec, kind="matches")
        events_payload = _load_country_payload(cache_dir, spec=config.spec, kind="events")
        players_payload = _load_reference_payload(cache_dir, "*players.json", label="players.json")
        teams_payload = _load_reference_payload(cache_dir, "*teams.json", label="teams.json")
    except WyscoutMappingAuditError as exc:
        raise WyscoutHistoricalScopeError(str(exc)) from exc
    return matches_payload, events_payload, players_payload, teams_payload


def validate_source_scope(
    *,
    matches_payload: list[Any],
    events_payload: list[Any],
    config: WyscoutHistoricalScopeConfig,
) -> WyscoutHistoricalSourceValidation:
    failures = list(
        verify_published_scope_counts(
            matches_payload=matches_payload,
            events_payload=events_payload,
            spec=config.spec,
        )
    )
    try:
        provider_ids = infer_provider_scope_ids(matches_payload, spec=config.spec)
    except WyscoutScopeEvidenceError as exc:
        failures.append(str(exc))
        provider_competition_id = -1
        provider_season_id = -1
    else:
        provider_competition_id = provider_ids.competition_id
        provider_season_id = provider_ids.season_id
        if provider_competition_id != config.scope.provider_competition_id:
            failures.append(
                "provider competition id differs from certified adapter scope: "
                f"{provider_competition_id} != {config.scope.provider_competition_id}"
            )
        if provider_season_id != config.scope.provider_season_id:
            failures.append(
                "provider season id differs from certified adapter scope: "
                f"{provider_season_id} != {config.scope.provider_season_id}"
            )

    return WyscoutHistoricalSourceValidation(
        match_count=len(matches_payload),
        event_count=len(events_payload),
        roster_player_count=config.spec.expected_roster_player_count,
        team_count=config.spec.expected_team_count,
        provider_competition_id=provider_competition_id,
        provider_season_id=provider_season_id,
        failures=tuple(failures),
    )


def _native_goal_total(matches_payload: list[Any]) -> int:
    total = 0
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue
        for team_entry in teams_data.values():
            if not isinstance(team_entry, dict):
                continue
            score = team_entry.get("score")
            if isinstance(score, int):
                total += score
    return total


def validate_adapter_observations(
    *,
    observations: list[NormalizedObservation],
    matches_payload: list[Any],
    config: WyscoutHistoricalScopeConfig,
) -> WyscoutHistoricalAdapterValidation:
    failures: list[str] = []
    safe_identities = {
        (mapping.catalog_key, mapping.catalog_granularity) for mapping in adapter_safe_mappings()
    }
    observed_identities: set[tuple[str, str]] = set()
    matches_seen: set[str] = set()
    teams_seen: set[str] = set()
    competition_ids: set[str] = set()
    seasons: set[str] = set()
    seen_values: dict[tuple[str, str, str, str, str | None], Any] = {}
    conflicting_duplicates = 0
    sentinel_player_observations = 0
    observed_team_goal_total = 0
    wrong_country_source_references = 0

    for observation in observations:
        if observation.source_code != SOURCE_CODE:
            failures.append(f"unexpected source_code {observation.source_code!r}")
            continue
        if observation.metric_granularity is None:
            failures.append(
                f"observation {observation.entity_source_id}/{observation.metric_name} "
                "has no metric_granularity"
            )
        else:
            observed_identities.add((observation.metric_name, observation.metric_granularity))

        identity = (
            observation.source_code,
            observation.entity_type,
            observation.entity_source_id,
            observation.metric_name,
            observation.metric_granularity,
        )
        previous = seen_values.get(identity)
        if identity in seen_values and previous != observation.value:
            conflicting_duplicates += 1
        else:
            seen_values[identity] = observation.value

        competition_id = observation.entity_identity_hints.get("competition_external_id")
        if competition_id:
            competition_ids.add(competition_id)
        season = observation.entity_identity_hints.get("season_label")
        if season:
            seasons.add(season)

        if observation.entity_type == "match":
            matches_seen.add(observation.entity_source_id)
        elif observation.entity_type == "team":
            teams_seen.add(observation.entity_source_id.rsplit(":", maxsplit=1)[-1])
            if (
                observation.metric_name == "goals_for"
                and isinstance(observation.value, (int, float))
                and not isinstance(observation.value, bool)
            ):
                observed_team_goal_total += int(observation.value)
        elif (
            observation.entity_type == "player"
            and observation.entity_source_id.rsplit(":", maxsplit=1)[-1] == "0"
        ):
            sentinel_player_observations += 1

        if config.spec.source_file_label not in observation.source_reference:
            wrong_country_source_references += 1

    unexpected_identities = observed_identities - safe_identities
    missing_identities = safe_identities - observed_identities
    expected_competition_id = str(config.scope.provider_competition_id)
    native_goal_total = _native_goal_total(matches_payload)

    if not observations:
        failures.append("adapter emitted no observations")
    if len(matches_seen) != config.spec.expected_match_count:
        failures.append(
            f"adapter match count expected={config.spec.expected_match_count} "
            f"actual={len(matches_seen)}"
        )
    if len(teams_seen) != config.spec.expected_team_count:
        failures.append(
            f"adapter team count expected={config.spec.expected_team_count} "
            f"actual={len(teams_seen)}"
        )
    if competition_ids != {expected_competition_id}:
        failures.append(
            f"adapter competition scope expected={{{expected_competition_id!r}}} "
            f"actual={competition_ids!r}"
        )
    if seasons != {config.scope.season_label}:
        failures.append(
            f"adapter season scope expected={{{config.scope.season_label!r}}} actual={seasons!r}"
        )
    if unexpected_identities:
        failures.append(
            f"adapter emitted {len(unexpected_identities)} non-safe identities: "
            f"{sorted(unexpected_identities)[:10]!r}"
        )
    if missing_identities:
        failures.append(
            f"adapter-safe identities with zero observations: {sorted(missing_identities)!r}"
        )
    if conflicting_duplicates:
        failures.append(f"adapter has {conflicting_duplicates} conflicting duplicates")
    if sentinel_player_observations:
        failures.append(
            f"adapter emitted {sentinel_player_observations} observations for player id 0"
        )
    if wrong_country_source_references:
        failures.append(
            f"adapter emitted {wrong_country_source_references} wrong-country source references"
        )
    if observed_team_goal_total != native_goal_total:
        failures.append(
            f"team goals mismatch native={native_goal_total} observed={observed_team_goal_total}"
        )

    return WyscoutHistoricalAdapterValidation(
        total_observations=len(observations),
        safe_identity_count=len(safe_identities),
        identities_with_observations=len(observed_identities & safe_identities),
        distinct_matches=len(matches_seen),
        distinct_teams=len(teams_seen),
        conflicting_duplicates=conflicting_duplicates,
        native_goal_total=native_goal_total,
        observed_team_goal_total=observed_team_goal_total,
        wrong_country_source_references=wrong_country_source_references,
        failures=tuple(failures),
    )
