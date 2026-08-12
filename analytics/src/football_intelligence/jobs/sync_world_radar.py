"""Fetch, score, and persist World Radar V1 candidates from external competitions.

World Radar protects provider quota above all else: no pagination, no full
squad fetches, no fixture backfill, and a hard, pre-flight request budget
check that runs before any network call is made.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.config.world_radar_competitions import (
    RadarCompetitionConfig,
    load_radar_competitions,
)
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.db.world_radar_repository import WorldRadarRepository
from football_intelligence.ingestion.raw_store import LocalRawStore, RawObjectRef
from football_intelligence.providers.api_football import ApiFootballClient, ApiFootballResponse
from football_intelligence.world_radar.engine import (
    MODEL_VERSION,
    calculate_world_radar,
    merge_feed_entries,
)
from football_intelligence.world_radar.models import PlayerRadarSnapshot, ResolvedCompetition
from football_intelligence.world_radar.parser import find_league_matches, parse_player_feed

REQUESTS_PER_COMPETITION = 3
DEFAULT_REQUEST_BUDGET = 12
MAX_REQUEST_BUDGET = 60


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "World Radar V1: detect offensive/creative candidates outside the core "
            "leagues using bounded, budget-checked provider requests."
        )
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--request-budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    return parser


def check_request_budget(competition_count: int, request_budget: int) -> int:
    """Return planned_requests, or raise SystemExit before any network call is made."""

    planned_requests = competition_count * REQUESTS_PER_COMPETITION
    if planned_requests > request_budget:
        raise SystemExit(
            f"World Radar planned_requests={planned_requests} exceeds "
            f"--request-budget={request_budget}; reduce competitions or raise the budget"
        )
    return planned_requests


def main() -> None:
    args = build_parser().parse_args()

    if args.request_budget < 1 or args.request_budget > MAX_REQUEST_BUDGET:
        raise SystemExit(f"--request-budget must be between 1 and {MAX_REQUEST_BUDGET}")

    competitions = load_radar_competitions()
    planned_requests = check_request_budget(len(competitions), args.request_budget)

    api_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        raise SystemExit("API_FOOTBALL_KEY is required")

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    client = ApiFootballClient(api_key)
    raw_store = LocalRawStore(args.raw_dir)

    competition_reports: list[dict[str, Any]] = []
    all_snapshots: list[PlayerRadarSnapshot] = []
    raw_refs: list[RawObjectRef] = []
    total_requests = 0
    remaining_quota: int | None = None

    for config in competitions:
        result, snapshots, refs, request_count, quota = _process_competition(
            client=client,
            raw_store=raw_store,
            config=config,
            season=args.season,
        )
        competition_reports.append(result)
        all_snapshots.extend(snapshots)
        raw_refs.extend(refs)
        total_requests += request_count
        if quota is not None:
            remaining_quota = quota

    season_label = str(args.season)
    persistence: dict[str, Any] = {"mode": "not_requested"}

    if database_url:
        with connect(database_url) as connection:
            provider_repository = ProviderRepository(connection, provider_code="api-football")
            run_id = provider_repository.start_run(
                job_name="world-radar",
                trigger_kind="manual",
                scope={
                    "season": args.season,
                    "request_budget": args.request_budget,
                    "competitions": [item.code for item in competitions],
                },
            )
            provider_repository.record_raw_objects(run_id, raw_refs)

            radar_repository = WorldRadarRepository(connection)
            radar_repository.replace_snapshots(
                all_snapshots,
                season_label=season_label,
                model_version=MODEL_VERSION,
            )
            persisted_count = radar_repository.snapshot_count(
                season_label=season_label,
                model_version=MODEL_VERSION,
            )

            provider_repository.finish_run(
                run_id,
                status="succeeded",
                request_count=total_requests,
                rows_written=persisted_count,
                metadata={
                    "request_budget": args.request_budget,
                    "planned_requests": planned_requests,
                    "competitions": [item.code for item in competitions],
                },
            )
            connection.commit()
        persistence = {"mode": "postgresql", "rows_written": persisted_count}

    report = {
        "model_version": MODEL_VERSION,
        "provider": "api-football",
        "season": args.season,
        "generated_at": datetime.now(UTC).isoformat(),
        "request_budget": args.request_budget,
        "planned_requests": planned_requests,
        "actual_requests": total_requests,
        "provider_remaining_quota": remaining_quota,
        "candidate_count": len(all_snapshots),
        "persistence": persistence,
        "competitions": competition_reports,
        "scope": "offensive/creative radar only; not full scouting or market value",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"WORLD RADAR: PASS ({len(competition_reports)} competitions, "
        f"{len(all_snapshots)} candidates, {total_requests} API requests)"
    )
    print(f"REPORT: {args.report}")


def _process_competition(
    *,
    client: ApiFootballClient,
    raw_store: LocalRawStore,
    config: RadarCompetitionConfig,
    season: int,
) -> tuple[dict[str, Any], list[PlayerRadarSnapshot], list[RawObjectRef], int, int | None]:
    responses: list[ApiFootballResponse] = []
    raw_refs: list[RawObjectRef] = []

    leagues_response = client.get(
        "leagues",
        {"name": config.name, "country": config.country, "season": season},
    )
    responses.append(leagues_response)
    raw_refs.append(_store(raw_store, leagues_response))
    remaining_quota = leagues_response.request_count_remaining

    matches = find_league_matches(
        leagues_response.payload, name=config.name, country=config.country
    )

    if len(matches) != 1:
        return (
            {
                "competition_code": config.code,
                "name": config.name,
                "country": config.country,
                "status": "unresolved",
                "reason": f"expected exactly one /leagues match, found {len(matches)}",
                "request_count": len(responses),
                "candidate_count": 0,
            },
            [],
            raw_refs,
            len(responses),
            remaining_quota,
        )

    provider_league_id = matches[0]
    resolved = ResolvedCompetition(
        code=config.code,
        name=config.name,
        country=config.country,
        provider_league_id=provider_league_id,
        season=season,
    )

    scorers_response = client.get(
        "players/topscorers",
        {"league": provider_league_id, "season": season},
    )
    responses.append(scorers_response)
    raw_refs.append(_store(raw_store, scorers_response))
    remaining_quota = scorers_response.request_count_remaining or remaining_quota

    assists_response = client.get(
        "players/topassists",
        {"league": provider_league_id, "season": season},
    )
    responses.append(assists_response)
    raw_refs.append(_store(raw_store, assists_response))
    remaining_quota = assists_response.request_count_remaining or remaining_quota

    scorer_entries = parse_player_feed(scorers_response.payload, source_list="topscorers")
    assist_entries = parse_player_feed(assists_response.payload, source_list="topassists")
    candidates = merge_feed_entries(scorer_entries + assist_entries)

    snapshots = calculate_world_radar(
        candidates,
        provider_code="api-football",
        competition_code=resolved.code,
        competition_name=resolved.name,
        country=resolved.country,
        season_label=str(season),
    )

    return (
        {
            "competition_code": config.code,
            "name": config.name,
            "country": config.country,
            "status": "resolved",
            "provider_league_id": provider_league_id,
            "request_count": len(responses),
            "feed_counts": {"topscorers": len(scorer_entries), "topassists": len(assist_entries)},
            "merged_candidates": len(candidates),
            "scored_candidates": len(snapshots),
        },
        list(snapshots),
        raw_refs,
        len(responses),
        remaining_quota,
    )


def _store(raw_store: LocalRawStore, response: ApiFootballResponse) -> RawObjectRef:
    return raw_store.put(
        endpoint=response.endpoint,
        parameters=dict(response.parameters),
        payload=response.payload,
    )


if __name__ == "__main__":
    main()
