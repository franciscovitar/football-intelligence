"""Audit Wyscout Open's five complete 2017/18 European domestic leagues.

Local-only and read-only. The existing England acquisition probe downloads the
official Figshare ``matches.zip`` and ``events.zip`` archives plus the shared
``players.json`` / ``teams.json`` reference files. Those archives contain one
country JSON file per competition. This job reuses the cached official bytes and
checks every European core league against the reference counts published by
Pappalardo et al.

The audit also infers each country's provider-native ``competitionId`` and
``seasonId`` from the complete real match file. IDs are evidence outputs, not
hard-coded assumptions. Nothing is written to PostgreSQL or canonical tables.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from football_intelligence.jobs.audit_wyscout_metric_mapping import (
    WyscoutMappingAuditError,
    _find_cached_file,
    _load_local_json,
)
from football_intelligence.providers.wyscout_open_scopes import (
    COLLECTION_DOI,
    CORE_LEAGUE_SPECS,
    LICENCE,
    PAPER_DOI,
    SEASON_LABEL,
    WyscoutCoreLeagueSpec,
    WyscoutScopeEvidenceError,
    infer_provider_scope_ids,
    roster_player_ids,
    team_ids,
    verify_published_scope_counts,
)

DEFAULT_CACHE_DIR = Path("data/cache/wyscout-open")


class WyscoutCoreLeagueAuditError(RuntimeError):
    """The five-league audit cannot safely interpret the local cache."""


@dataclass(frozen=True, slots=True)
class CoreLeagueAuditResult:
    competition_code: str
    source_file_label: str
    season_label: str
    provider_competition_id: int | None
    provider_season_id: int | None
    match_count: int
    event_count: int
    roster_player_count: int
    team_count: int
    roster_players_missing_from_players_reference: int
    competition_teams_missing_from_teams_reference: int
    events_outside_match_scope: int
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures


@dataclass(frozen=True, slots=True)
class WyscoutCoreLeagueAuditReport:
    collection_doi: str
    paper_doi: str
    licence: str
    season_label: str
    results: tuple[CoreLeagueAuditResult, ...]

    @property
    def passed(self) -> bool:
        return bool(self.results) and all(result.passed for result in self.results)


def _load_country_payload(
    cache_dir: Path, *, spec: WyscoutCoreLeagueSpec, kind: str
) -> list[Any]:
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
        raise WyscoutCoreLeagueAuditError(f"{filename} is not a JSON array")
    return payload


def _load_reference_payload(cache_dir: Path, pattern: str, *, label: str) -> list[Any]:
    path = _find_cached_file(cache_dir, pattern)
    with path.open("rb") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise WyscoutCoreLeagueAuditError(f"cached {label} payload is not a JSON array")
    return payload


def _reference_ids(payload: list[Any]) -> frozenset[int]:
    return frozenset(
        item["wyId"]
        for item in payload
        if isinstance(item, dict) and isinstance(item.get("wyId"), int)
    )


def audit_core_league(
    *,
    spec: WyscoutCoreLeagueSpec,
    matches_payload: list[Any],
    events_payload: list[Any],
    player_reference_ids: frozenset[int],
    team_reference_ids: frozenset[int],
) -> CoreLeagueAuditResult:
    failures = list(
        verify_published_scope_counts(
            matches_payload=matches_payload,
            events_payload=events_payload,
            spec=spec,
        )
    )

    provider_competition_id: int | None = None
    provider_season_id: int | None = None
    try:
        scope_ids = infer_provider_scope_ids(matches_payload, spec=spec)
    except WyscoutScopeEvidenceError as exc:
        failures.append(f"scope_ids: {exc}")
    else:
        provider_competition_id = scope_ids.competition_id
        provider_season_id = scope_ids.season_id

    match_ids = frozenset(
        match["wyId"]
        for match in matches_payload
        if isinstance(match, dict) and isinstance(match.get("wyId"), int)
    )
    event_match_ids = frozenset(
        event["matchId"]
        for event in events_payload
        if isinstance(event, dict) and isinstance(event.get("matchId"), int)
    )
    outside_matches = event_match_ids - match_ids
    if outside_matches:
        failures.append(f"events reference {len(outside_matches)} matches outside country scope")

    roster_ids = roster_player_ids(matches_payload)
    competition_team_ids = team_ids(matches_payload)
    missing_players = roster_ids - player_reference_ids
    missing_teams = competition_team_ids - team_reference_ids
    # England's already-certified source demonstrates that a small number of
    # roster player IDs can be absent from players.json. Preserve/report that
    # source-quality gap rather than fabricating a profile. It is therefore not
    # a completeness failure by itself. Missing teams are different: team names
    # are required for canonical normalization and must fail the audit.
    if missing_teams:
        failures.append(f"teams.json missing {len(missing_teams)} competition team ids")

    return CoreLeagueAuditResult(
        competition_code=spec.competition_code,
        source_file_label=spec.source_file_label,
        season_label=SEASON_LABEL,
        provider_competition_id=provider_competition_id,
        provider_season_id=provider_season_id,
        match_count=len(matches_payload),
        event_count=len(events_payload),
        roster_player_count=len(roster_ids),
        team_count=len(competition_team_ids),
        roster_players_missing_from_players_reference=len(missing_players),
        competition_teams_missing_from_teams_reference=len(missing_teams),
        events_outside_match_scope=len(outside_matches),
        failures=tuple(failures),
    )


def run_audit(cache_dir: Path = DEFAULT_CACHE_DIR) -> WyscoutCoreLeagueAuditReport:
    try:
        players_payload = _load_reference_payload(cache_dir, "*players.json", label="players.json")
        teams_payload = _load_reference_payload(cache_dir, "*teams.json", label="teams.json")
    except WyscoutMappingAuditError as exc:
        raise WyscoutCoreLeagueAuditError(str(exc)) from exc

    player_reference_ids = _reference_ids(players_payload)
    team_reference_ids = _reference_ids(teams_payload)
    results: list[CoreLeagueAuditResult] = []
    for spec in CORE_LEAGUE_SPECS:
        try:
            matches_payload = _load_country_payload(cache_dir, spec=spec, kind="matches")
            events_payload = _load_country_payload(cache_dir, spec=spec, kind="events")
        except WyscoutMappingAuditError as exc:
            raise WyscoutCoreLeagueAuditError(
                f"{spec.competition_code}: unable to load cached official source: {exc}"
            ) from exc
        results.append(
            audit_core_league(
                spec=spec,
                matches_payload=matches_payload,
                events_payload=events_payload,
                player_reference_ids=player_reference_ids,
                team_reference_ids=team_reference_ids,
            )
        )

    return WyscoutCoreLeagueAuditReport(
        collection_doi=COLLECTION_DOI,
        paper_doi=PAPER_DOI,
        licence=LICENCE,
        season_label=SEASON_LABEL,
        results=tuple(results),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit all five Wyscout Open 2017/18 European domestic league files."
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--report", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = run_audit(args.cache_dir)
    except (OSError, json.JSONDecodeError, WyscoutCoreLeagueAuditError) as exc:
        raise SystemExit(f"WYSCOUT CORE LEAGUES: FAIL - {exc}") from exc

    payload = {
        "status": "PASS" if report.passed else "FAIL",
        "collection_doi": report.collection_doi,
        "paper_doi": report.paper_doi,
        "licence": report.licence,
        "season_label": report.season_label,
        "results": [
            {**asdict(result), "passed": result.passed}
            for result in report.results
        ],
    }
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    for result in report.results:
        state = "PASS" if result.passed else "FAIL"
        print(
            f"{result.competition_code}: {state} matches={result.match_count} "
            f"events={result.event_count} players={result.roster_player_count} "
            f"teams={result.team_count} provider_ids="
            f"({result.provider_competition_id}, {result.provider_season_id})"
        )
        for failure in result.failures:
            print(f"  - {failure}")

    if not report.passed:
        raise SystemExit("WYSCOUT CORE LEAGUES: FAIL")
    print("WYSCOUT CORE LEAGUES: PASS")
    if args.report is not None:
        print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
