"""Scope metadata for Wyscout Open's five 2017/18 European domestic leagues.

The published Pappalardo et al. dataset contains one complete 2017/18 season
for each of the five major European domestic leagues. This module records only
stable source facts that are independent of a local cache layout: canonical
Football Intelligence competition code, Figshare country-file label, and the
published reference counts used to verify that a downloaded country payload is
complete.

Provider-native ``competitionId`` / ``seasonId`` values for a concrete run are
*not* guessed or copied from secondary mirrors. They are inferred from the real
official match payload and required to be unique across the whole file before an
``AdapterScope`` can be constructed by a caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SEASON_LABEL = "2017/18"
COLLECTION_DOI = "10.6084/m9.figshare.c.4415000.v5"
PAPER_DOI = "10.1038/s41597-019-0247-7"
LICENCE = "CC BY 4.0"


class WyscoutScopeEvidenceError(RuntimeError):
    """A cached country payload cannot prove one complete declared scope."""


@dataclass(frozen=True, slots=True)
class WyscoutCoreLeagueSpec:
    competition_code: str
    source_file_label: str
    expected_match_count: int
    expected_event_count: int
    expected_roster_player_count: int
    expected_team_count: int

    @property
    def match_filename(self) -> str:
        return f"matches_{self.source_file_label}.json"

    @property
    def event_filename(self) -> str:
        return f"events_{self.source_file_label}.json"


CORE_LEAGUE_SPECS: tuple[WyscoutCoreLeagueSpec, ...] = (
    WyscoutCoreLeagueSpec(
        competition_code="ENG_PL",
        source_file_label="England",
        expected_match_count=380,
        expected_event_count=643_150,
        expected_roster_player_count=603,
        expected_team_count=20,
    ),
    WyscoutCoreLeagueSpec(
        competition_code="ESP_LL",
        source_file_label="Spain",
        expected_match_count=380,
        expected_event_count=628_659,
        expected_roster_player_count=619,
        expected_team_count=20,
    ),
    WyscoutCoreLeagueSpec(
        competition_code="FRA_L1",
        source_file_label="France",
        expected_match_count=380,
        expected_event_count=632_807,
        expected_roster_player_count=629,
        expected_team_count=20,
    ),
    WyscoutCoreLeagueSpec(
        competition_code="GER_BL1",
        source_file_label="Germany",
        expected_match_count=306,
        expected_event_count=519_407,
        expected_roster_player_count=537,
        expected_team_count=18,
    ),
    WyscoutCoreLeagueSpec(
        competition_code="ITA_SA",
        source_file_label="Italy",
        expected_match_count=380,
        expected_event_count=647_372,
        expected_roster_player_count=686,
        expected_team_count=20,
    ),
)

_SPEC_BY_CODE = {spec.competition_code: spec for spec in CORE_LEAGUE_SPECS}


@dataclass(frozen=True, slots=True)
class WyscoutProviderScopeIds:
    competition_id: int
    season_id: int


def core_league_spec(competition_code: str) -> WyscoutCoreLeagueSpec:
    try:
        return _SPEC_BY_CODE[competition_code]
    except KeyError as exc:
        raise KeyError(f"unsupported Wyscout core competition {competition_code!r}") from exc


def infer_provider_scope_ids(
    matches_payload: list[Any], *, spec: WyscoutCoreLeagueSpec
) -> WyscoutProviderScopeIds:
    """Infer provider-native IDs only when the complete real file proves them.

    The function intentionally does not infer the canonical competition from a
    numeric Wyscout id. The caller first selects an explicit country-file spec;
    this function then proves that every usable match belongs to exactly one
    provider competition/season and that the file has the published match count.
    """

    if len(matches_payload) != spec.expected_match_count:
        raise WyscoutScopeEvidenceError(
            f"{spec.competition_code} {SEASON_LABEL} expected "
            f"{spec.expected_match_count} matches, got {len(matches_payload)}"
        )

    competition_ids: set[int] = set()
    season_ids: set[int] = set()
    invalid_rows = 0
    for match in matches_payload:
        if not isinstance(match, dict):
            invalid_rows += 1
            continue
        competition_id = match.get("competitionId")
        season_id = match.get("seasonId")
        if not isinstance(competition_id, int) or not isinstance(season_id, int):
            invalid_rows += 1
            continue
        competition_ids.add(competition_id)
        season_ids.add(season_id)

    if invalid_rows:
        raise WyscoutScopeEvidenceError(
            f"{spec.competition_code} payload has {invalid_rows} matches without integer "
            "competitionId/seasonId"
        )
    if len(competition_ids) != 1:
        raise WyscoutScopeEvidenceError(
            f"{spec.competition_code} payload must contain exactly one provider competitionId, "
            f"got {sorted(competition_ids)!r}"
        )
    if len(season_ids) != 1:
        raise WyscoutScopeEvidenceError(
            f"{spec.competition_code} payload must contain exactly one provider seasonId, "
            f"got {sorted(season_ids)!r}"
        )

    return WyscoutProviderScopeIds(
        competition_id=next(iter(competition_ids)),
        season_id=next(iter(season_ids)),
    )


def roster_player_ids(matches_payload: list[Any]) -> frozenset[int]:
    """Return the Wyscout paper's roster/squad player universe.

    The certified England probe established that the paper's per-competition
    player count means every non-sentinel player found in match formation lineup
    or bench arrays, including unused substitutes who never generate an event.
    """

    player_ids: set[int] = set()
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue
        for team_entry in teams_data.values():
            if not isinstance(team_entry, dict):
                continue
            formation = team_entry.get("formation")
            if not isinstance(formation, dict):
                continue
            for key in ("lineup", "bench"):
                entries = formation.get(key)
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    player_id = entry.get("playerId")
                    if isinstance(player_id, int) and player_id != 0:
                        player_ids.add(player_id)
    return frozenset(player_ids)


def team_ids(matches_payload: list[Any]) -> frozenset[int]:
    result: set[int] = set()
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue
        for raw_team_id, team_entry in teams_data.items():
            if isinstance(team_entry, dict) and isinstance(team_entry.get("teamId"), int):
                result.add(team_entry["teamId"])
                continue
            try:
                result.add(int(raw_team_id))
            except (TypeError, ValueError):
                continue
    return frozenset(result)


def verify_published_scope_counts(
    *,
    matches_payload: list[Any],
    events_payload: list[Any],
    spec: WyscoutCoreLeagueSpec,
) -> tuple[str, ...]:
    """Return deterministic count failures; empty means the published scope matches."""

    failures: list[str] = []
    if len(matches_payload) != spec.expected_match_count:
        failures.append(
            f"matches expected={spec.expected_match_count} actual={len(matches_payload)}"
        )
    if len(events_payload) != spec.expected_event_count:
        failures.append(f"events expected={spec.expected_event_count} actual={len(events_payload)}")
    roster_count = len(roster_player_ids(matches_payload))
    if roster_count != spec.expected_roster_player_count:
        failures.append(
            f"roster_players expected={spec.expected_roster_player_count} actual={roster_count}"
        )
    team_count = len(team_ids(matches_payload))
    if team_count != spec.expected_team_count:
        failures.append(f"teams expected={spec.expected_team_count} actual={team_count}")
    return tuple(failures)
