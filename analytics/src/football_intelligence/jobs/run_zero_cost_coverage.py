"""Zero-Cost Coverage Lab (Block 14, expanded Block 15).

Answers, for every target metric x every one of the 10 target competitions:
which free source can supply it, at what freshness (current vs
historical), how complete, and when was it last verified?

Block 15 deepens the two zero-auth current sources: TheSportsDB (event-stats
+ lineup, beyond match results, across all 10 competitions) and a new
Football-Data.co.uk provider (explicitly published results CSV files for the
7 European target competitions it covers). Both feed the existing Block 13
Data Mesh contracts -- normalized observations, entity resolution,
reconciliation -- rather than a parallel pipeline. StatsBomb Open Data stays
historical/deep; football-data.org stays optional-token.

This job never writes to `football.*` canonical tables. No API-Football
calls. No paid endpoints.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from football_intelligence.coverage_lab.engine import ProbeResult, compute_coverage
from football_intelligence.coverage_lab.models import CoverageEntry, satisfies_current
from football_intelligence.coverage_lab.product_coverage import (
    ProductCoverageResult,
    compute_product_coverage,
    compute_recent_season_coverage,
)
from football_intelligence.coverage_lab.provider_capabilities import PROVIDER_CAPABILITIES
from football_intelligence.coverage_lab.target_competitions import (
    TARGET_COMPETITION_COUNT,
    build_target_competitions,
)
from football_intelligence.coverage_lab.target_metrics import (
    CRITICAL_METRIC_NAMES,
    build_metric_granularity_index,
    build_target_metric_catalog,
)
from football_intelligence.data_mesh.adapters.football_data_org import (
    parse_competitions as parse_football_data_org_competitions,
)
from football_intelligence.data_mesh.adapters.football_data_org import (
    parse_matches as parse_football_data_org_matches,
)
from football_intelligence.data_mesh.adapters.football_data_uk import parse_results_csv
from football_intelligence.data_mesh.adapters.openligadb import parse_league_matches
from football_intelligence.data_mesh.adapters.statsbomb_open import (
    find_competition_season,
    parse_match_events,
    parse_match_list,
)
from football_intelligence.data_mesh.adapters.thesportsdb import (
    is_finished_status,
    parse_event_stats,
    parse_league_events,
    parse_lineup,
)
from football_intelligence.data_mesh.entity_resolution import COMPETITION_MAPPINGS
from football_intelligence.data_mesh.models import NormalizedObservation, ReconciliationDecision
from football_intelligence.data_mesh.pipeline import resolve_and_reconcile
from football_intelligence.db.coverage_repository import CoverageRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.ingestion.raw_store import LocalRawStore
from football_intelligence.providers.football_data_org import (
    TOKEN_ENV_VAR,
    FootballDataOrgClient,
    FootballDataOrgError,
)
from football_intelligence.providers.football_data_uk import (
    FootballDataUkClient,
    FootballDataUkError,
    FootballDataUkNotFoundError,
)
from football_intelligence.providers.openligadb import OpenLigaDbClient, OpenLigaDbError
from football_intelligence.providers.statsbomb_open import (
    StatsBombOpenDataClient,
    StatsBombOpenDataError,
)
from football_intelligence.providers.thesportsdb import TheSportsDbClient, TheSportsDbError

_CANONICAL_COMPETITION_CODE = "GER_BL1"

DEFAULT_STATSBOMB_COMPETITION_NAME = "1. Bundesliga"
DEFAULT_STATSBOMB_SEASON_NAME = "2023/2024"
STATSBOMB_EVENT_SAMPLE_MATCHES = 2

# Known full Bundesliga season size (18 teams, double round-robin): used only
# to detect that StatsBomb Open Data's published sample is a *subset* of the
# real season, so match-level coverage correctly reports "partial" instead
# of quietly implying full-season historical coverage.
BUNDESLIGA_FULL_SEASON_MATCH_COUNT = 306

# Competitions whose season is a single calendar year rather than a
# cross-year Aug-May cycle. Every other target competition is cross-year.
CALENDAR_YEAR_COMPETITIONS: frozenset[str] = frozenset({"ARG_LPF", "BRA_A", "USA_MLS"})


def expected_current_season(competition_code: str, as_of_date: date) -> str:
    """The TRUE current season label for `competition_code` as of `as_of_date`.

    A computed, deterministic derivation -- never a hardcoded label chosen
    because it happens to have finished matches. Verified live during Block
    15 implementation that this matches TheSportsDB's own
    `strCurrentSeason` convention for both calendar-year competitions
    (Argentina, Brazil, MLS: a single `"YYYY"` label) and cross-year ones
    (the 7 European leagues: `"YYYY-YYYY"`, rolling over every August 1st).
    A competition whose true current season has produced no finished match
    yet must report that honestly (see `previous_season` in
    `coverage_lab.models`), never silently borrow an older season's data as
    if it were current.
    """

    if competition_code in CALENDAR_YEAR_COMPETITIONS:
        return str(as_of_date.year)
    start_year = as_of_date.year if as_of_date.month >= 8 else as_of_date.year - 1
    return f"{start_year}-{start_year + 1}"


# Match discovery (`eventsseason.php`) runs for all 10 competitions -- one
# request each. Event-stats/lineup sampling adds real depth beyond match
# results but costs an extra request per competition, so both stay a
# deliberately small, explicit subset to respect the request budget.
THESPORTSDB_EVENT_STATS_SAMPLE_COMPETITIONS: tuple[str, ...] = ("GER_BL1", "ENG_PL", "ITA_SA")
THESPORTSDB_LINEUP_SAMPLE_COMPETITIONS: tuple[str, ...] = ("GER_BL1",)

FOOTBALL_DATA_UK_COMPETITIONS: tuple[str, ...] = (
    "ENG_PL",
    "ESP_LL",
    "ITA_SA",
    "GER_BL1",
    "FRA_L1",
    "NED_ED",
    "POR_PL",
)
# Football-Data.co.uk publishes no file for these -- never probed, never
# fabricated as coverage.
FOOTBALL_DATA_UK_UNCOVERED_COMPETITIONS: tuple[str, ...] = ("ARG_LPF", "BRA_A", "USA_MLS")

# Two attempts per covered competition (the newer computed season, falling
# back to the older one if not yet published) -- a real per-run discovery,
# never an assumption that either file exists.
FOOTBALL_DATA_UK_MAX_ATTEMPTS_PER_COMPETITION = 2

THESPORTSDB_PLANNED_REQUESTS = (
    TARGET_COMPETITION_COUNT
    + len(THESPORTSDB_EVENT_STATS_SAMPLE_COMPETITIONS)
    + len(THESPORTSDB_LINEUP_SAMPLE_COMPETITIONS)
)
FOOTBALL_DATA_UK_PLANNED_REQUESTS = (
    len(FOOTBALL_DATA_UK_COMPETITIONS) * FOOTBALL_DATA_UK_MAX_ATTEMPTS_PER_COMPETITION
)
STATSBOMB_PLANNED_REQUESTS = 2 + STATSBOMB_EVENT_SAMPLE_MATCHES  # competitions + matches + N events
OPENLIGADB_PLANNED_REQUESTS = 1
PLANNED_REQUESTS_BASE = (
    THESPORTSDB_PLANNED_REQUESTS
    + OPENLIGADB_PLANNED_REQUESTS
    + STATSBOMB_PLANNED_REQUESTS
    + FOOTBALL_DATA_UK_PLANNED_REQUESTS
)
# football-data.org is only spent if a token is configured -- CI never
# requires it.
FOOTBALL_DATA_ORG_TOKEN_REQUESTS = 2

# The task's explicit hard cap for one bounded live Coverage Lab run.
REQUEST_BUDGET_HARD_CAP = 35
DEFAULT_REQUEST_BUDGET = REQUEST_BUDGET_HARD_CAP
MAX_REQUEST_BUDGET = REQUEST_BUDGET_HARD_CAP

# thesportsdb/openligadb/football-data-org report a boolean finished/
# not-finished signal, not the full MatchRecord.status vocabulary -- a
# documented partial proxy.
_CURRENT_METRIC_NAME_REMAP: dict[str, str] = {"is_finished": "status"}

REPORT_EXAMPLE_LIMIT = 10

_GRANULARITY_INDEX = build_metric_granularity_index()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Zero-Cost Coverage Lab: measure what free sources can supply, for $0."
    )
    parser.add_argument("--statsbomb-competition-name", default=DEFAULT_STATSBOMB_COMPETITION_NAME)
    parser.add_argument("--statsbomb-season-name", default=DEFAULT_STATSBOMB_SEASON_NAME)
    parser.add_argument(
        "--as-of-date",
        default=None,
        help=(
            "ISO date used to compute the true current season for TheSportsDB/OpenLigaDB "
            "and the newer/older Football-Data.co.uk season codes (default: today, UTC)."
        ),
    )
    parser.add_argument("--request-budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.request_budget < 1 or args.request_budget > MAX_REQUEST_BUDGET:
        raise SystemExit(f"--request-budget must be between 1 and {MAX_REQUEST_BUDGET}")

    as_of_date = (
        date.fromisoformat(args.as_of_date) if args.as_of_date else datetime.now(UTC).date()
    )

    token = os.environ.get(TOKEN_ENV_VAR, "").strip()
    planned_requests = PLANNED_REQUESTS_BASE + (FOOTBALL_DATA_ORG_TOKEN_REQUESTS if token else 0)
    if planned_requests > args.request_budget:
        raise SystemExit(
            f"coverage lab planned_requests={planned_requests} exceeds "
            f"--request-budget={args.request_budget}"
        )

    raw_store = LocalRawStore(args.raw_dir)
    now = datetime.now(UTC)

    (
        thesportsdb_statuses,
        thesportsdb_requests,
        thesportsdb_observations_by_competition,
        thesportsdb_meta,
    ) = _probe_thesportsdb(raw_store=raw_store, as_of_date=as_of_date)
    openligadb_status, openligadb_requests, openligadb_observations = _probe_openligadb(
        raw_store=raw_store, as_of_date=as_of_date
    )
    statsbomb_status, statsbomb_requests, statsbomb_observations, statsbomb_meta = _probe_statsbomb(
        raw_store=raw_store,
        competition_name=args.statsbomb_competition_name,
        season_name=args.statsbomb_season_name,
    )
    fd_uk_statuses, fd_uk_requests, fd_uk_observations, fd_uk_meta = _probe_football_data_uk(
        raw_store=raw_store, as_of_date=as_of_date
    )
    fd_org_status, fd_org_requests, fd_org_observations, fd_org_meta = _probe_football_data_org(
        raw_store=raw_store, token=token
    )

    total_requests = (
        thesportsdb_requests
        + openligadb_requests
        + statsbomb_requests
        + fd_uk_requests
        + fd_org_requests
    )

    probe_results = _build_probe_results(
        thesportsdb_statuses=thesportsdb_statuses,
        thesportsdb_observations_by_competition=thesportsdb_observations_by_competition,
        openligadb_status=openligadb_status,
        openligadb_observations=openligadb_observations,
        statsbomb_status=statsbomb_status,
        statsbomb_observations=statsbomb_observations,
        statsbomb_match_sample_size=statsbomb_meta.get("match_sample_size", 0),
        fd_uk_statuses=fd_uk_statuses,
        fd_uk_observations=fd_uk_observations,
        fd_uk_meta=fd_uk_meta,
        fd_org_status=fd_org_status,
        fd_org_observations=fd_org_observations,
        fd_org_meta=fd_org_meta,
    )

    target_metrics = build_target_metric_catalog()
    target_competitions = build_target_competitions()
    coverage = compute_coverage(
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        providers=PROVIDER_CAPABILITIES,
        probe_results=probe_results,
        token_present_by_provider={"football-data-org": bool(token)},
        calculated_at=now,
    )

    all_thesportsdb_observations = [
        item
        for observations in thesportsdb_observations_by_competition.values()
        for item in observations
    ]
    decisions, resolution_meta = resolve_and_reconcile(
        all_thesportsdb_observations + fd_uk_observations
    )

    persistence: dict[str, Any] = {"mode": "not_requested"}
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if database_url:
        with connect(database_url) as connection:
            repository = CoverageRepository(connection)
            written = repository.replace_snapshots(coverage)
            connection.commit()
        persistence = {"mode": "postgresql", "snapshots_written": written}

    report = _build_report(
        args=args,
        planned_requests=planned_requests,
        total_requests=total_requests,
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        coverage=coverage,
        decisions=decisions,
        resolution_meta=resolution_meta,
        thesportsdb_statuses=thesportsdb_statuses,
        thesportsdb_requests=thesportsdb_requests,
        thesportsdb_meta=thesportsdb_meta,
        openligadb_status=openligadb_status,
        openligadb_requests=openligadb_requests,
        statsbomb_status=statsbomb_status,
        statsbomb_requests=statsbomb_requests,
        statsbomb_meta=statsbomb_meta,
        fd_uk_statuses=fd_uk_statuses,
        fd_uk_requests=fd_uk_requests,
        fd_uk_meta=fd_uk_meta,
        fd_org_status=fd_org_status,
        fd_org_requests=fd_org_requests,
        fd_org_meta=fd_org_meta,
        token_present=bool(token),
        persistence=persistence,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"ZERO-COST COVERAGE LAB: {len(coverage)} coverage rows, "
        f"{total_requests} API requests, {len(target_competitions)} competitions"
    )
    print(f"REPORT: {args.report}")


def _competition_external_id(source_code: str) -> str:
    for mapping in COMPETITION_MAPPINGS:
        if (
            mapping.source_code == source_code
            and mapping.canonical_code == _CANONICAL_COMPETITION_CODE
        ):
            return mapping.external_id
    raise RuntimeError(f"no PoC competition mapping configured for {source_code}")


def _thesportsdb_mappings() -> dict[str, str]:
    return {
        mapping.canonical_code: mapping.external_id
        for mapping in COMPETITION_MAPPINGS
        if mapping.source_code == "thesportsdb"
    }


def _football_data_uk_division_code(competition_code: str) -> str:
    for mapping in COMPETITION_MAPPINGS:
        if mapping.source_code == "football-data-uk" and mapping.canonical_code == competition_code:
            return mapping.external_id
    raise RuntimeError(f"no football-data-uk mapping for {competition_code}")


def _first_finished_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    events = payload.get("events")
    if not isinstance(events, list):
        return None
    for item in events:
        if isinstance(item, dict) and is_finished_status(item.get("strStatus")) is True:
            return item
    return None


def _probe_thesportsdb(
    *, raw_store: LocalRawStore, as_of_date: date
) -> tuple[dict[str, str], int, dict[str, list[NormalizedObservation]], dict[str, Any]]:
    client = TheSportsDbClient()
    league_ids = _thesportsdb_mappings()
    requests = 0
    statuses: dict[str, str] = {}
    observations_by_competition: dict[str, list[NormalizedObservation]] = {}
    event_stats_sample_matches: dict[str, str] = {}
    lineup_sample_matches: dict[str, str] = {}
    season_by_competition: dict[str, str] = {}

    for competition_code, league_id in league_ids.items():
        season_label = expected_current_season(competition_code, as_of_date)
        season_by_competition[competition_code] = season_label
        try:
            response = client.get("eventsseason.php", {"id": league_id, "s": season_label})
            requests += 1
        except TheSportsDbError as exc:
            statuses[competition_code] = f"error: {exc}"
            continue

        raw_store.put(
            endpoint=f"thesportsdb/eventsseason/{competition_code}",
            parameters=dict(response.parameters),
            payload=response.payload,
        )
        observations = parse_league_events(
            response.payload, competition_external_id=league_id, ingestion_run_id=None
        )
        observations_by_competition[competition_code] = observations
        statuses[competition_code] = "ok"

        needs_event_stats = competition_code in THESPORTSDB_EVENT_STATS_SAMPLE_COMPETITIONS
        needs_lineup = competition_code in THESPORTSDB_LINEUP_SAMPLE_COMPETITIONS
        if not (needs_event_stats or needs_lineup):
            continue

        first_finished = _first_finished_event(response.payload)
        if first_finished is None:
            continue
        match_id = str(first_finished.get("idEvent"))

        if needs_event_stats:
            home_id = str(first_finished.get("idHomeTeam"))
            away_id = str(first_finished.get("idAwayTeam"))
            try:
                stats_response = client.get("lookupeventstats.php", {"id": match_id})
                requests += 1
                raw_store.put(
                    endpoint=f"thesportsdb/lookupeventstats/{match_id}",
                    parameters=dict(stats_response.parameters),
                    payload=stats_response.payload,
                )
                observations_by_competition[competition_code].extend(
                    parse_event_stats(
                        stats_response.payload,
                        match_id=match_id,
                        competition_external_id=league_id,
                        home_team_external_id=home_id,
                        away_team_external_id=away_id,
                        ingestion_run_id=None,
                    )
                )
                event_stats_sample_matches[competition_code] = match_id
            except TheSportsDbError:
                pass

        if needs_lineup:
            try:
                lineup_response = client.get("lookuplineup.php", {"id": match_id})
                requests += 1
                raw_store.put(
                    endpoint=f"thesportsdb/lookuplineup/{match_id}",
                    parameters=dict(lineup_response.parameters),
                    payload=lineup_response.payload,
                )
                observations_by_competition[competition_code].extend(
                    parse_lineup(
                        lineup_response.payload,
                        match_id=match_id,
                        competition_external_id=league_id,
                        ingestion_run_id=None,
                    )
                )
                lineup_sample_matches[competition_code] = match_id
            except TheSportsDbError:
                pass

    meta = {
        "season_by_competition": season_by_competition,
        "event_stats_sample_matches": event_stats_sample_matches,
        "lineup_sample_matches": lineup_sample_matches,
    }
    return statuses, requests, observations_by_competition, meta


def _probe_openligadb(
    *, raw_store: LocalRawStore, as_of_date: date
) -> tuple[str, int, list[NormalizedObservation]]:
    client = OpenLigaDbClient()
    competition_external_id = _competition_external_id("openligadb")
    season = expected_current_season(_CANONICAL_COMPETITION_CODE, as_of_date).split("-")[0]
    try:
        response = client.get(f"getmatchdata/{competition_external_id}/{season}")
    except OpenLigaDbError as exc:
        return f"error: {exc}", 0, []

    raw_store.put(
        endpoint=response.endpoint,
        parameters={"competition": competition_external_id, "season": season},
        payload={"matches": response.payload},
    )
    observations = parse_league_matches(
        response.payload,
        competition_external_id=competition_external_id,
        ingestion_run_id=None,
        limit=15,
    )
    return "ok", 1, observations


def _probe_statsbomb(
    *, raw_store: LocalRawStore, competition_name: str, season_name: str
) -> tuple[str, int, list[NormalizedObservation], dict[str, Any]]:
    client = StatsBombOpenDataClient()
    requests = 0
    try:
        competitions_response = client.get("competitions.json")
        requests += 1
        raw_store.put(
            endpoint="statsbomb/competitions.json",
            parameters={},
            payload={"competitions": competitions_response.payload},
        )
    except StatsBombOpenDataError as exc:
        return f"error: {exc}", requests, [], {}

    resolved = find_competition_season(
        competitions_response.payload, competition_name=competition_name, season_name=season_name
    )
    if resolved is None:
        return (
            f"error: {competition_name} {season_name} not found in StatsBomb Open Data",
            requests,
            [],
            {},
        )
    competition_id, season_id = resolved

    try:
        matches_response = client.get(f"matches/{competition_id}/{season_id}.json")
        requests += 1
        raw_store.put(
            endpoint=f"statsbomb/matches/{competition_id}/{season_id}.json",
            parameters={},
            payload={"matches": matches_response.payload},
        )
    except StatsBombOpenDataError as exc:
        return f"error: {exc}", requests, [], {}

    match_payload = matches_response.payload if isinstance(matches_response.payload, list) else []
    match_sample_size = len(match_payload)

    observations = parse_match_list(
        match_payload,
        competition_code=_CANONICAL_COMPETITION_CODE,
        season_label=season_name,
        ingestion_run_id=None,
    )

    sampled_match_ids = [
        item.get("match_id")
        for item in match_payload[:STATSBOMB_EVENT_SAMPLE_MATCHES]
        if isinstance(item, dict) and isinstance(item.get("match_id"), int)
    ]
    for match_id in sampled_match_ids:
        try:
            events_response = client.get(f"events/{match_id}.json")
            requests += 1
            raw_store.put(
                endpoint=f"statsbomb/events/{match_id}.json",
                parameters={},
                payload={"events": events_response.payload},
            )
        except StatsBombOpenDataError:
            continue
        observations.extend(
            parse_match_events(
                events_response.payload,
                match_id=str(match_id),
                competition_code=_CANONICAL_COMPETITION_CODE,
                ingestion_run_id=None,
            )
        )

    meta = {
        "competition_id": competition_id,
        "season_id": season_id,
        "match_sample_size": match_sample_size,
        "event_sample_match_ids": sampled_match_ids,
        "expected_full_season_matches": BUNDESLIGA_FULL_SEASON_MATCH_COUNT,
    }
    return "ok", requests, observations, meta


def _football_data_uk_season_codes(as_of_date: date) -> tuple[str, str]:
    """(newer, older) 4-digit season codes for the Aug-May European calendar.

    E.g. for a date in August 2026: ("2627", "2526"). Neither is assumed to
    have a published file -- `_probe_football_data_uk` tries the newer one
    first and falls back to the older one, discovering availability live.
    """

    start_year = as_of_date.year if as_of_date.month >= 8 else as_of_date.year - 1
    newer = f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"
    older = f"{(start_year - 1) % 100:02d}{start_year % 100:02d}"
    return newer, older


def _probe_football_data_uk(
    *, raw_store: LocalRawStore, as_of_date: date
) -> tuple[dict[str, str], int, list[NormalizedObservation], dict[str, Any]]:
    client = FootballDataUkClient()
    newer_code, older_code = _football_data_uk_season_codes(as_of_date)
    mappings = [m for m in COMPETITION_MAPPINGS if m.source_code == "football-data-uk"]

    statuses: dict[str, str] = {}
    observations: list[NormalizedObservation] = []
    requests = 0
    season_used: dict[str, str | None] = {}

    for mapping in mappings:
        division_code = mapping.external_id
        competition_code = mapping.canonical_code
        used_season: str | None = None
        last_error: str | None = None

        for season_code in (newer_code, older_code):
            try:
                response = client.get_results_csv(
                    division_code=division_code, season_code=season_code
                )
                requests += 1
            except FootballDataUkNotFoundError as exc:
                requests += 1
                last_error = str(exc)
                continue
            except FootballDataUkError as exc:
                requests += 1
                last_error = str(exc)
                break

            raw_store.put(
                endpoint=f"football-data-uk/{season_code}/{division_code}",
                parameters={"division": division_code, "season": season_code},
                payload={"csv_text": response.csv_text},
            )
            used_season = season_code
            observations.extend(
                parse_results_csv(
                    response.csv_text,
                    division_code=division_code,
                    season_code=season_code,
                    ingestion_run_id=None,
                )
            )
            break

        season_used[competition_code] = used_season
        statuses[competition_code] = "ok" if used_season else f"error: {last_error}"

    meta = {
        "season_by_competition": season_used,
        "newer_season_code": newer_code,
        "older_season_code": older_code,
        "uncovered_competitions": list(FOOTBALL_DATA_UK_UNCOVERED_COMPETITIONS),
    }
    return statuses, requests, observations, meta


def _probe_football_data_org(
    *, raw_store: LocalRawStore, token: str
) -> tuple[str, int, list[NormalizedObservation], dict[str, Any]]:
    """Probe football-data.org: competitions catalog, then (bounded) matches.

    A competitions-catalog request alone only proves a competition is
    *listed* -- it is discovery evidence, never match-stat coverage. This
    probe additionally confirms which of our explicit, reviewed
    (`entity_resolution.COMPETITION_MAPPINGS`) football-data.org competition
    codes are actually present in this run's live response, then spends one
    bounded matches request for whichever of those is the job's canonical
    probe competition (GER_BL1/BL1, matching the other current sources).
    Mapped-but-not-live-confirmed and unmapped competitions are never
    probed for matches this run and stay `not_probed`, never fabricated.
    """

    if not token:
        return "token_required", 0, [], {}

    client = FootballDataOrgClient(token)
    try:
        response = client.get("competitions")
    except FootballDataOrgError as exc:
        return f"error: {exc}", 0, [], {}

    raw_store.put(
        endpoint=response.endpoint, parameters=dict(response.parameters), payload=response.payload
    )
    observations = parse_football_data_org_competitions(response.payload, ingestion_run_id=None)
    requests = 1

    live_codes = {
        item.get("code")
        for item in response.payload.get("competitions", [])
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }
    fd_mappings = [m for m in COMPETITION_MAPPINGS if m.source_code == "football-data-org"]
    supported_target_competitions = sorted(
        mapping.canonical_code for mapping in fd_mappings if mapping.external_id in live_codes
    )
    meta: dict[str, Any] = {
        "supported_target_competitions": supported_target_competitions,
        "matches_probed_competition": None,
    }

    probe_mapping = next(
        (
            mapping
            for mapping in fd_mappings
            if mapping.canonical_code == _CANONICAL_COMPETITION_CODE
            and mapping.external_id in live_codes
        ),
        None,
    )
    if probe_mapping is None:
        return "ok", requests, observations, meta

    try:
        matches_response = client.get(f"competitions/{probe_mapping.external_id}/matches")
        requests += 1
    except FootballDataOrgError as exc:
        meta["matches_probe_error"] = str(exc)
        return "ok", requests, observations, meta

    raw_store.put(
        endpoint=matches_response.endpoint,
        parameters=dict(matches_response.parameters),
        payload=matches_response.payload,
    )
    observations.extend(
        parse_football_data_org_matches(
            matches_response.payload,
            competition_code=probe_mapping.canonical_code,
            ingestion_run_id=None,
        )
    )
    meta["matches_probed_competition"] = probe_mapping.canonical_code
    return "ok", requests, observations, meta


def _metric_key_for_observation(entity_type: str, metric_name: str) -> tuple[str, str] | None:
    granularity = _GRANULARITY_INDEX.get((entity_type, metric_name))
    if granularity is None:
        return None
    return (metric_name, granularity)


def _build_current_probe_result(
    observations: list[NormalizedObservation],
    *,
    metric_name_remap: dict[str, str] | None = None,
    notes: str | None = None,
    is_current_period: bool = True,
) -> ProbeResult:
    """Build one ProbeResult from a batch of a *current* source's observations.

    Match-granularity metrics (home_score/status/...) are scoped to the
    number of distinct matches observed. Team-granularity metrics (from
    event-stats/CSV team rows) are scoped separately, via
    `metric_sample_sizes`, to the number of distinct (team, match) slots
    actually observed -- never the match count, which double-counts (each
    match has two team slots) or, worse, silently borrows an unrelated
    denominator the way a single shared `sample_size` would.

    `is_current_period` must be set to `False` by the caller when this batch
    is known to come from a previous/completed season rather than the true
    current one (e.g. Football-Data.co.uk's newer-season file was not yet
    published and the job fell back to the prior one) -- see `engine.
    ProbeResult` for how this gates `current_available` vs `previous_season`.
    """

    remap = metric_name_remap or {}
    match_ids = {item.entity_source_id for item in observations if item.entity_type == "match"}
    match_sample_size = len(match_ids)
    team_slot_ids = {
        (item.entity_source_id, item.entity_identity_hints.get("match_external_id", ""))
        for item in observations
        if item.entity_type == "team" and item.entity_identity_hints.get("match_external_id")
    }
    team_slot_sample_size = len(team_slot_ids)

    counts: dict[tuple[str, str], int] = defaultdict(int)
    metric_sample_sizes: dict[tuple[str, str], int] = {}
    for item in observations:
        metric_name = remap.get(item.metric_name, item.metric_name)
        key = _metric_key_for_observation(item.entity_type, metric_name)
        if key is None:
            continue
        counts[key] += 1
        if key[1] == "team":
            metric_sample_sizes[key] = team_slot_sample_size

    source_reference = observations[0].source_reference if observations else None
    return ProbeResult(
        status="ok",
        sample_size=match_sample_size,
        metric_observed_counts=dict(counts),
        metric_sample_sizes=metric_sample_sizes or None,
        source_reference=source_reference,
        notes=notes,
        is_current_period=is_current_period,
    )


def _statsbomb_counts(
    observations: list[NormalizedObservation],
) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], int], dict[tuple[str, str], int]]:
    match_observations = [item for item in observations if item.entity_type == "match"]
    match_counts: dict[tuple[str, str], int] = defaultdict(int)
    for item in match_observations:
        key = _metric_key_for_observation(item.entity_type, item.metric_name)
        if key is not None:
            match_counts[key] += 1

    deep_observations = [
        item
        for item in observations
        if item.entity_type in ("player", "team") and ":" in item.entity_source_id
    ]
    deep_counts: dict[tuple[str, str], int] = defaultdict(int)
    entities_by_metric: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in deep_observations:
        key = _metric_key_for_observation(item.entity_type, item.metric_name)
        if key is None:
            continue
        deep_counts[key] += 1
        entities_by_metric[key].add(item.entity_source_id)

    # Deep event metrics are force-zero-filled for every entity that
    # genuinely appeared in the bounded event sample (see the StatsBomb
    # adapter), so their honest denominator is "how many entities of this
    # metric's own granularity appeared in the sampled matches" -- never the
    # full published-season match count, which measures a different thing
    # (match-summary completeness, not per-entity event coverage).
    deep_sample_sizes = {key: len(entity_ids) for key, entity_ids in entities_by_metric.items()}

    return dict(match_counts), dict(deep_counts), deep_sample_sizes


def _build_probe_results(
    *,
    thesportsdb_statuses: dict[str, str],
    thesportsdb_observations_by_competition: dict[str, list[NormalizedObservation]],
    openligadb_status: str,
    openligadb_observations: list[NormalizedObservation],
    statsbomb_status: str,
    statsbomb_observations: list[NormalizedObservation],
    statsbomb_match_sample_size: int,
    fd_uk_statuses: dict[str, str],
    fd_uk_observations: list[NormalizedObservation],
    fd_uk_meta: dict[str, Any],
    fd_org_status: str,
    fd_org_observations: list[NormalizedObservation],
    fd_org_meta: dict[str, Any],
) -> dict[tuple[str, str], ProbeResult]:
    results: dict[tuple[str, str], ProbeResult] = {}

    for competition_code, status in thesportsdb_statuses.items():
        if status != "ok":
            continue
        observations = thesportsdb_observations_by_competition.get(competition_code, [])
        results[("thesportsdb", competition_code)] = _build_current_probe_result(
            observations, metric_name_remap=_CURRENT_METRIC_NAME_REMAP
        )

    if openligadb_status == "ok":
        results[("openligadb", _CANONICAL_COMPETITION_CODE)] = _build_current_probe_result(
            openligadb_observations, metric_name_remap=_CURRENT_METRIC_NAME_REMAP
        )
    else:
        results[("openligadb", _CANONICAL_COMPETITION_CODE)] = ProbeResult(
            status="error",
            sample_size=0,
            metric_observed_counts={},
            source_reference=None,
            notes=openligadb_status,
        )

    if statsbomb_status == "ok":
        match_counts, deep_counts, deep_sample_sizes = _statsbomb_counts(statsbomb_observations)
        # Two coverage rows share the same (provider, competition): match-
        # level facts are scoped to the full published match list (revealing
        # a "partial" season), deep event metrics are scoped to their own
        # small bounded event sample instead. `compute_coverage` only keeps
        # one ProbeResult per (provider, competition), so the counts are
        # merged here, but each metric keeps its own honest denominator via
        # `metric_sample_sizes` rather than sharing one misleading number.
        merged_counts = dict(match_counts)
        merged_counts.update(deep_counts)
        match_sample_size = max(statsbomb_match_sample_size, BUNDESLIGA_FULL_SEASON_MATCH_COUNT)
        metric_sample_sizes = dict.fromkeys(match_counts, match_sample_size)
        metric_sample_sizes.update(deep_sample_sizes)
        results[("statsbomb-open", _CANONICAL_COMPETITION_CODE)] = ProbeResult(
            status="ok",
            sample_size=match_sample_size,
            metric_observed_counts=merged_counts,
            metric_sample_sizes=metric_sample_sizes,
            source_reference="statsbomb-open/data",
            notes=(
                f"StatsBomb Open Data published {statsbomb_match_sample_size} of an "
                f"expected {BUNDESLIGA_FULL_SEASON_MATCH_COUNT} Bundesliga matches"
            ),
        )
    elif statsbomb_status == "token_required":
        results[("statsbomb-open", _CANONICAL_COMPETITION_CODE)] = ProbeResult(
            status="skipped_token_required",
            sample_size=0,
            metric_observed_counts={},
            source_reference=None,
        )
    else:
        results[("statsbomb-open", _CANONICAL_COMPETITION_CODE)] = ProbeResult(
            status="error",
            sample_size=0,
            metric_observed_counts={},
            source_reference=None,
            notes=statsbomb_status,
        )

    fd_uk_newer_code = fd_uk_meta.get("newer_season_code")
    fd_uk_season_by_competition: dict[str, str | None] = fd_uk_meta.get("season_by_competition", {})
    for competition_code, status in fd_uk_statuses.items():
        if status != "ok":
            continue
        division_code = _football_data_uk_division_code(competition_code)
        competition_observations = [
            item
            for item in fd_uk_observations
            if item.entity_identity_hints.get("competition_external_id") == division_code
        ]
        # The newer (true current) season was tried first; a competition
        # only ever falls back to the older one when the newer file has not
        # been published yet -- that fallback is real evidence, but never
        # the true current period.
        used_season = fd_uk_season_by_competition.get(competition_code)
        is_current_period = used_season is not None and used_season == fd_uk_newer_code
        results[("football-data-uk", competition_code)] = _build_current_probe_result(
            competition_observations, is_current_period=is_current_period
        )

    if fd_org_status == "token_required":
        for competition in build_target_competitions():
            results[("football-data-org", competition.code)] = ProbeResult(
                status="skipped_token_required",
                sample_size=0,
                metric_observed_counts={},
                source_reference=None,
            )
    elif fd_org_status == "ok":
        probed_competition = fd_org_meta.get("matches_probed_competition")
        if probed_competition:
            results[("football-data-org", probed_competition)] = _build_current_probe_result(
                fd_org_observations
            )
    else:
        results[("football-data-org", _CANONICAL_COMPETITION_CODE)] = ProbeResult(
            status="error",
            sample_size=0,
            metric_observed_counts={},
            source_reference=None,
            notes=fd_org_status,
        )

    return results


def _requirements_satisfied_by_provider(coverage: list[CoverageEntry], provider_code: str) -> int:
    def satisfied(entry: CoverageEntry) -> bool:
        if entry.freshness_role == "current":
            return satisfies_current(entry.state)
        return entry.state == "historical_only"

    return sum(1 for entry in coverage if entry.provider_code == provider_code and satisfied(entry))


def _build_report(
    *,
    args: argparse.Namespace,
    planned_requests: int,
    total_requests: int,
    target_metrics: tuple[Any, ...],
    target_competitions: tuple[Any, ...],
    coverage: list[CoverageEntry],
    decisions: list[ReconciliationDecision],
    resolution_meta: dict[str, Any],
    thesportsdb_statuses: dict[str, str],
    thesportsdb_requests: int,
    thesportsdb_meta: dict[str, Any],
    openligadb_status: str,
    openligadb_requests: int,
    statsbomb_status: str,
    statsbomb_requests: int,
    statsbomb_meta: dict[str, Any],
    fd_uk_statuses: dict[str, str],
    fd_uk_requests: int,
    fd_uk_meta: dict[str, Any],
    fd_org_status: str,
    fd_org_requests: int,
    fd_org_meta: dict[str, Any],
    token_present: bool,
    persistence: dict[str, Any],
) -> dict[str, Any]:
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_competition: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_domain: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    metric_domain_by_name = {metric.metric_name: metric.domain for metric in target_metrics}

    # Provider-level diagnostics: one row per (provider, competition, metric)
    # combination, so this denominator scales with provider count. Real
    # evidence about what any one provider does, but the WRONG denominator
    # for "can the product cover this metric at all" -- see
    # `product_current_coverage`/`product_historical_deep_coverage` below,
    # whose denominator is the fixed target catalog regardless of how many
    # providers exist.
    provider_current_numerator = 0
    provider_current_denominator = 0
    provider_historical_numerator = 0
    provider_historical_denominator = 0
    provider_missing_critical_current: set[str] = set()
    partial_examples: list[dict[str, Any]] = []

    for entry in coverage:
        by_source[entry.provider_code][entry.state] += 1
        by_competition[entry.competition_code][entry.state] += 1
        domain = metric_domain_by_name.get(entry.metric_name, "unknown")
        by_domain[domain][entry.state] += 1

        if entry.state == "partial" and len(partial_examples) < REPORT_EXAMPLE_LIMIT:
            partial_examples.append(
                {
                    "provider_code": entry.provider_code,
                    "competition_code": entry.competition_code,
                    "metric_name": entry.metric_name,
                    "granularity": entry.granularity,
                    "sample_size": entry.sample_size,
                    "observed_count": entry.observed_count,
                }
            )

        if entry.freshness_role == "current":
            provider_current_denominator += 1
            if satisfies_current(entry.state):
                provider_current_numerator += 1
            elif entry.metric_name in CRITICAL_METRIC_NAMES and entry.state in (
                "missing",
                "not_probed",
                "token_required",
            ):
                provider_missing_critical_current.add(
                    f"{entry.provider_code}:{entry.competition_code}:{entry.metric_name}"
                )
        else:
            provider_historical_denominator += 1
            if entry.state == "historical_only":
                provider_historical_numerator += 1

    product_current = compute_product_coverage(
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        coverage_entries=coverage,
        freshness_role="current",
    )
    product_historical = compute_product_coverage(
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        coverage_entries=coverage,
        freshness_role="historical",
    )
    product_recent_season = compute_recent_season_coverage(
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        coverage_entries=coverage,
    )

    coverage_added_by_source = {
        provider.provider_code: _requirements_satisfied_by_provider(
            coverage, provider.provider_code
        )
        for provider in PROVIDER_CAPABILITIES
    }

    statsbomb_examples = [
        {
            "competition_code": entry.competition_code,
            "metric_name": entry.metric_name,
            "entity_type": entry.entity_type,
            "state": entry.state,
            "sample_size": entry.sample_size,
            "observed_count": entry.observed_count,
        }
        for entry in coverage
        if entry.provider_code == "statsbomb-open" and entry.state != "unsupported"
    ][:REPORT_EXAMPLE_LIMIT]

    def _decision_example(decision: ReconciliationDecision) -> dict[str, Any]:
        return {
            "logical_entity_key": decision.logical_entity_key,
            "entity_type": decision.entity_type,
            "metric_name": decision.metric_name,
            "status": decision.status,
            "candidate_value": decision.candidate_value,
            "confidence": decision.confidence,
            "participating_sources": list(decision.participating_sources),
        }

    reconciliation_examples = [
        _decision_example(decision) for decision in decisions if decision.source_count >= 2
    ][:REPORT_EXAMPLE_LIMIT]

    # Match-scoped team stats specifically (logical_entity_key prefixed
    # "team-match:") -- separated out so the report can never conflate
    # "some team fact agreed/conflicted somewhere" with "the SAME team's
    # SAME match-level stat agreed/conflicted across sources".
    team_match_decisions = [
        decision for decision in decisions if decision.logical_entity_key.startswith("team-match:")
    ]
    team_match_examples = [
        _decision_example(decision)
        for decision in team_match_decisions
        if decision.source_count >= 2
    ][:REPORT_EXAMPLE_LIMIT]

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "request_budget": args.request_budget,
        "planned_requests": planned_requests,
        "actual_requests": total_requests,
        "target_metric_count": len(target_metrics),
        "target_competition_count": len(target_competitions),
        "coverage_row_count": len(coverage),
        "coverage_by_source": {code: dict(states) for code, states in by_source.items()},
        "coverage_by_competition": {code: dict(states) for code, states in by_competition.items()},
        "coverage_by_domain": {code: dict(states) for code, states in by_domain.items()},
        # PRODUCT coverage: "can Football Intelligence cover this metric, for
        # this competition, from ANY free current/historical source?" --
        # denominator is target_metric_count x target_competition_count
        # (127 x 10 = 1270 since Block 16's Metric Catalog V2 grew the
        # catalog from 48; was 48 x 10 = 480 before), independent of
        # provider count. This is the number that answers the product
        # question; the "provider_diagnostics" figures below are
        # diagnostic, not the headline result.
        "product_current_coverage": _coverage_fraction(product_current),
        "product_recent_season_coverage": _coverage_fraction(product_recent_season),
        "product_historical_deep_coverage": _coverage_fraction(product_historical),
        "missing_critical_current_metrics": list(
            product_current.critical_gap_keys[:REPORT_EXAMPLE_LIMIT]
        ),
        "still_missing_current_requirements": list(product_current.gap_keys[:REPORT_EXAMPLE_LIMIT]),
        "coverage_added_by_source": coverage_added_by_source,
        "partial_examples": partial_examples,
        "provider_diagnostics": {
            "current_entries": {
                "numerator": provider_current_numerator,
                "denominator": provider_current_denominator,
            },
            "historical_entries": {
                "numerator": provider_historical_numerator,
                "denominator": provider_historical_denominator,
            },
            "missing_critical_current_metrics": sorted(provider_missing_critical_current)[
                :REPORT_EXAMPLE_LIMIT
            ],
        },
        "statsbomb_deep_examples": statsbomb_examples,
        "reconciliation": {
            "overlap_count": resolution_meta["overlap_count"],
            "agreement_count": sum(1 for decision in decisions if decision.status == "agreed"),
            "single_source_count": sum(
                1 for decision in decisions if decision.status == "single_source"
            ),
            "conflict_count": sum(1 for decision in decisions if decision.status == "conflict"),
            "unresolved_identity_count": resolution_meta["unresolved_observation_count"],
            "unresolved_identity_examples": resolution_meta["unresolved_identity_examples"],
            "examples": reconciliation_examples,
            "team_match_scoped": {
                "overlap_count": sum(1 for d in team_match_decisions if d.source_count >= 2),
                "agreement_count": sum(1 for d in team_match_decisions if d.status == "agreed"),
                "conflict_count": sum(1 for d in team_match_decisions if d.status == "conflict"),
                "single_source_count": sum(
                    1 for d in team_match_decisions if d.status == "single_source"
                ),
                "examples": team_match_examples,
            },
        },
        "sources": {
            "thesportsdb": {
                "status_by_competition": thesportsdb_statuses,
                "requests": thesportsdb_requests,
                **thesportsdb_meta,
            },
            "openligadb": {"status": openligadb_status, "requests": openligadb_requests},
            "statsbomb-open": {
                "status": statsbomb_status,
                "requests": statsbomb_requests,
                **statsbomb_meta,
            },
            "football-data-uk": {
                "status_by_competition": fd_uk_statuses,
                "requests": fd_uk_requests,
                **fd_uk_meta,
            },
            "football-data-org": {
                "status": fd_org_status,
                "requests": fd_org_requests,
                "token_present": token_present,
                **fd_org_meta,
            },
        },
        "persistence": persistence,
        "scope": (
            "Coverage Lab only: measures what free sources can supply. No football.* "
            "canonical writes. StatsBomb Open Data is historical/deep, never current. "
            "product_current_coverage only counts probes that verified the TRUE current "
            "season/period (computed from the run date); a current-role provider's "
            "verified-but-previous-season evidence is real and reported separately in "
            "product_recent_season_coverage, never folded into the current numerator."
        ),
    }


def _coverage_fraction(result: ProductCoverageResult) -> dict[str, int]:
    return {"numerator": result.numerator, "denominator": result.denominator}


if __name__ == "__main__":
    main()
