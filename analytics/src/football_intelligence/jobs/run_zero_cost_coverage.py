"""Block 14 Zero-Cost Coverage Lab.

Answers, for every target metric x every one of the 10 target competitions:
which free source can supply it, at what freshness (current vs
historical), how complete, and when was it last verified?

Runs tiny, bounded live probes against zero-auth sources (TheSportsDB,
OpenLigaDB), an optional-token probe against football-data.org (skipped
entirely, never failed, when no token is configured), and one bounded
StatsBomb Open Data deep sample. Produces a machine-readable coverage
report and, optionally, persists it to `ingestion.coverage_snapshots`.

This job never writes to `football.*` canonical tables. No API-Football
calls.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.coverage_lab.engine import ProbeResult, compute_coverage
from football_intelligence.coverage_lab.models import CoverageEntry, satisfies_current
from football_intelligence.coverage_lab.provider_capabilities import PROVIDER_CAPABILITIES
from football_intelligence.coverage_lab.target_competitions import build_target_competitions
from football_intelligence.coverage_lab.target_metrics import (
    CRITICAL_METRIC_NAMES,
    build_target_metric_catalog,
)
from football_intelligence.data_mesh.adapters.football_data_org import (
    parse_competitions as parse_football_data_org_competitions,
)
from football_intelligence.data_mesh.adapters.openligadb import parse_league_matches
from football_intelligence.data_mesh.adapters.statsbomb_open import (
    find_competition_season,
    parse_match_events,
    parse_match_list,
)
from football_intelligence.data_mesh.adapters.thesportsdb import parse_league_events
from football_intelligence.data_mesh.entity_resolution import COMPETITION_MAPPINGS
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.db.coverage_repository import CoverageRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.ingestion.raw_store import LocalRawStore
from football_intelligence.providers.football_data_org import (
    TOKEN_ENV_VAR,
    FootballDataOrgClient,
    FootballDataOrgError,
)
from football_intelligence.providers.openligadb import OpenLigaDbClient, OpenLigaDbError
from football_intelligence.providers.statsbomb_open import (
    StatsBombOpenDataClient,
    StatsBombOpenDataError,
)
from football_intelligence.providers.thesportsdb import TheSportsDbClient, TheSportsDbError

_CANONICAL_COMPETITION_CODE = "GER_BL1"

DEFAULT_CURRENT_SEASON_LABEL = "2025-2026"
DEFAULT_STATSBOMB_COMPETITION_NAME = "1. Bundesliga"
DEFAULT_STATSBOMB_SEASON_NAME = "2023/2024"
STATSBOMB_EVENT_SAMPLE_MATCHES = 2

# Known full Bundesliga season size (18 teams, double round-robin): used only
# to detect that StatsBomb Open Data's published sample is a *subset* of the
# real season, so match-level coverage correctly reports "partial" instead
# of quietly implying full-season historical coverage.
BUNDESLIGA_FULL_SEASON_MATCH_COUNT = 306

# thesportsdb(1) + openligadb(1) + statsbomb(competitions + matches + N events)
# + football-data-org(1, only spent if a token is configured).
PLANNED_REQUESTS_BASE = 2 + 2 + STATSBOMB_EVENT_SAMPLE_MATCHES
DEFAULT_REQUEST_BUDGET = PLANNED_REQUESTS_BASE + 1
MAX_REQUEST_BUDGET = 20

# thesportsdb/openligadb report a boolean finished/not-finished signal, not
# the full MatchRecord.status vocabulary -- a documented partial proxy.
_CURRENT_METRIC_NAME_REMAP: dict[str, str] = {"is_finished": "status"}

REPORT_EXAMPLE_LIMIT = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Block 14 Zero-Cost Coverage Lab: measure what free sources can supply."
    )
    parser.add_argument("--current-season", default=DEFAULT_CURRENT_SEASON_LABEL)
    parser.add_argument("--statsbomb-competition-name", default=DEFAULT_STATSBOMB_COMPETITION_NAME)
    parser.add_argument("--statsbomb-season-name", default=DEFAULT_STATSBOMB_SEASON_NAME)
    parser.add_argument("--request-budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.request_budget < 1 or args.request_budget > MAX_REQUEST_BUDGET:
        raise SystemExit(f"--request-budget must be between 1 and {MAX_REQUEST_BUDGET}")

    token = os.environ.get(TOKEN_ENV_VAR, "").strip()
    planned_requests = PLANNED_REQUESTS_BASE + (1 if token else 0)
    if planned_requests > args.request_budget:
        raise SystemExit(
            f"coverage lab planned_requests={planned_requests} exceeds "
            f"--request-budget={args.request_budget}"
        )

    raw_store = LocalRawStore(args.raw_dir)
    now = datetime.now(UTC)

    thesportsdb_status, thesportsdb_requests, thesportsdb_observations = _probe_thesportsdb(
        raw_store=raw_store, season_label=args.current_season
    )
    openligadb_status, openligadb_requests, openligadb_observations = _probe_openligadb(
        raw_store=raw_store, season_label=args.current_season
    )
    statsbomb_status, statsbomb_requests, statsbomb_observations, statsbomb_meta = _probe_statsbomb(
        raw_store=raw_store,
        competition_name=args.statsbomb_competition_name,
        season_name=args.statsbomb_season_name,
    )
    fd_status, fd_requests, fd_observations = _probe_football_data_org(
        raw_store=raw_store, token=token
    )

    total_requests = thesportsdb_requests + openligadb_requests + statsbomb_requests + fd_requests

    probe_results = _build_probe_results(
        thesportsdb_status=thesportsdb_status,
        thesportsdb_observations=thesportsdb_observations,
        openligadb_status=openligadb_status,
        openligadb_observations=openligadb_observations,
        statsbomb_status=statsbomb_status,
        statsbomb_observations=statsbomb_observations,
        statsbomb_match_sample_size=statsbomb_meta.get("match_sample_size", 0),
        fd_status=fd_status,
        fd_observations=fd_observations,
        token_present=bool(token),
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
        thesportsdb_status=thesportsdb_status,
        thesportsdb_requests=thesportsdb_requests,
        openligadb_status=openligadb_status,
        openligadb_requests=openligadb_requests,
        statsbomb_status=statsbomb_status,
        statsbomb_requests=statsbomb_requests,
        statsbomb_meta=statsbomb_meta,
        fd_status=fd_status,
        fd_requests=fd_requests,
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


def _probe_thesportsdb(
    *, raw_store: LocalRawStore, season_label: str
) -> tuple[str, int, list[NormalizedObservation]]:
    client = TheSportsDbClient()
    competition_external_id = _competition_external_id("thesportsdb")
    try:
        response = client.get(
            "eventsseason.php", {"id": competition_external_id, "s": season_label}
        )
    except TheSportsDbError as exc:
        return f"error: {exc}", 0, []

    raw_store.put(
        endpoint=response.endpoint, parameters=dict(response.parameters), payload=response.payload
    )
    observations = parse_league_events(
        response.payload, competition_external_id=competition_external_id, ingestion_run_id=None
    )
    return "ok", 1, observations


def _probe_openligadb(
    *, raw_store: LocalRawStore, season_label: str
) -> tuple[str, int, list[NormalizedObservation]]:
    client = OpenLigaDbClient()
    competition_external_id = _competition_external_id("openligadb")
    season = season_label.split("-")[0]
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


def _probe_football_data_org(
    *, raw_store: LocalRawStore, token: str
) -> tuple[str, int, list[NormalizedObservation]]:
    if not token:
        return "token_required", 0, []

    client = FootballDataOrgClient(token)
    try:
        response = client.get("competitions")
    except FootballDataOrgError as exc:
        return f"error: {exc}", 0, []

    raw_store.put(
        endpoint=response.endpoint, parameters=dict(response.parameters), payload=response.payload
    )
    observations = parse_football_data_org_competitions(response.payload, ingestion_run_id=None)
    return "ok", 1, observations


def _build_probe_results(
    *,
    thesportsdb_status: str,
    thesportsdb_observations: list[NormalizedObservation],
    openligadb_status: str,
    openligadb_observations: list[NormalizedObservation],
    statsbomb_status: str,
    statsbomb_observations: list[NormalizedObservation],
    statsbomb_match_sample_size: int,
    fd_status: str,
    fd_observations: list[NormalizedObservation],
    token_present: bool,
) -> dict[tuple[str, str], ProbeResult]:
    results: dict[tuple[str, str], ProbeResult] = {}

    for provider_code, status, observations, remap in (
        ("thesportsdb", thesportsdb_status, thesportsdb_observations, _CURRENT_METRIC_NAME_REMAP),
        ("openligadb", openligadb_status, openligadb_observations, _CURRENT_METRIC_NAME_REMAP),
    ):
        results[(provider_code, _CANONICAL_COMPETITION_CODE)] = _current_probe_result(
            status=status, observations=observations, metric_name_remap=remap
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

    if fd_status == "token_required":
        for competition in build_target_competitions():
            results[("football-data-org", competition.code)] = ProbeResult(
                status="skipped_token_required",
                sample_size=0,
                metric_observed_counts={},
                source_reference=None,
            )
    elif fd_status == "ok":
        counts = _count_observations(fd_observations)
        results[("football-data-org", _CANONICAL_COMPETITION_CODE)] = ProbeResult(
            status="ok",
            sample_size=len({item.entity_source_id for item in fd_observations}) or 1,
            metric_observed_counts=counts,
            source_reference="v4/competitions",
        )
    else:
        results[("football-data-org", _CANONICAL_COMPETITION_CODE)] = ProbeResult(
            status="error",
            sample_size=0,
            metric_observed_counts={},
            source_reference=None,
            notes=fd_status,
        )

    return results


def _current_probe_result(
    *,
    status: str,
    observations: list[NormalizedObservation],
    metric_name_remap: dict[str, str],
) -> ProbeResult:
    if status != "ok":
        return ProbeResult(
            status="error",
            sample_size=0,
            metric_observed_counts={},
            source_reference=None,
            notes=status,
        )

    match_observations = [item for item in observations if item.entity_type == "match"]
    sample_size = len({item.entity_source_id for item in match_observations})
    counts: dict[str, int] = defaultdict(int)
    for item in match_observations:
        metric_name = metric_name_remap.get(item.metric_name, item.metric_name)
        counts[metric_name] += 1
    return ProbeResult(
        status="ok",
        sample_size=sample_size,
        metric_observed_counts=dict(counts),
        source_reference=observations[0].source_reference if observations else None,
    )


def _statsbomb_counts(
    observations: list[NormalizedObservation],
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    match_observations = [item for item in observations if item.entity_type == "match"]
    match_counts: dict[str, int] = defaultdict(int)
    for item in match_observations:
        match_counts[item.metric_name] += 1

    deep_observations = [
        item
        for item in observations
        if item.entity_type in ("player", "team") and ":" in item.entity_source_id
    ]
    deep_counts: dict[str, int] = defaultdict(int)
    entities_by_metric: dict[str, set[str]] = defaultdict(set)
    for item in deep_observations:
        deep_counts[item.metric_name] += 1
        entities_by_metric[item.metric_name].add(item.entity_source_id)

    # Deep event metrics are force-zero-filled for every entity that
    # genuinely appeared in the bounded event sample (see the StatsBomb
    # adapter), so their honest denominator is "how many entities of this
    # metric's own granularity appeared in the sampled matches" -- never the
    # full published-season match count, which measures a different thing
    # (match-summary completeness, not per-entity event coverage).
    deep_sample_sizes = {
        metric_name: len(entity_ids) for metric_name, entity_ids in entities_by_metric.items()
    }

    return dict(match_counts), dict(deep_counts), deep_sample_sizes


def _count_observations(observations: list[NormalizedObservation]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in observations:
        counts[item.metric_name] += 1
    return dict(counts)


def _build_report(
    *,
    args: argparse.Namespace,
    planned_requests: int,
    total_requests: int,
    target_metrics: tuple[Any, ...],
    target_competitions: tuple[Any, ...],
    coverage: list[CoverageEntry],
    thesportsdb_status: str,
    thesportsdb_requests: int,
    openligadb_status: str,
    openligadb_requests: int,
    statsbomb_status: str,
    statsbomb_requests: int,
    statsbomb_meta: dict[str, Any],
    fd_status: str,
    fd_requests: int,
    token_present: bool,
    persistence: dict[str, Any],
) -> dict[str, Any]:
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_competition: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_domain: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    metric_domain_by_name = {metric.metric_name: metric.domain for metric in target_metrics}

    current_numerator = 0
    current_denominator = 0
    historical_numerator = 0
    historical_denominator = 0
    missing_critical_current: set[str] = set()

    for entry in coverage:
        by_source[entry.provider_code][entry.state] += 1
        by_competition[entry.competition_code][entry.state] += 1
        domain = metric_domain_by_name.get(entry.metric_name, "unknown")
        by_domain[domain][entry.state] += 1

        if entry.freshness_role == "current":
            current_denominator += 1
            if satisfies_current(entry.state):
                current_numerator += 1
            elif entry.metric_name in CRITICAL_METRIC_NAMES and entry.state in (
                "missing",
                "not_probed",
                "token_required",
            ):
                missing_critical_current.add(
                    f"{entry.provider_code}:{entry.competition_code}:{entry.metric_name}"
                )
        else:
            historical_denominator += 1
            if entry.state == "historical_only":
                historical_numerator += 1

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
        "current_coverage": {
            "numerator": current_numerator,
            "denominator": current_denominator,
        },
        "historical_deep_coverage": {
            "numerator": historical_numerator,
            "denominator": historical_denominator,
        },
        "missing_critical_current_metrics": sorted(missing_critical_current)[:REPORT_EXAMPLE_LIMIT],
        "statsbomb_deep_examples": statsbomb_examples,
        "sources": {
            "thesportsdb": {"status": thesportsdb_status, "requests": thesportsdb_requests},
            "openligadb": {"status": openligadb_status, "requests": openligadb_requests},
            "statsbomb-open": {
                "status": statsbomb_status,
                "requests": statsbomb_requests,
                **statsbomb_meta,
            },
            "football-data-org": {
                "status": fd_status,
                "requests": fd_requests,
                "token_present": token_present,
            },
        },
        "persistence": persistence,
        "scope": (
            "Coverage Lab only: measures what free sources can supply. No football.* "
            "canonical writes. StatsBomb Open Data is historical/deep, never current."
        ),
    }


if __name__ == "__main__":
    main()
