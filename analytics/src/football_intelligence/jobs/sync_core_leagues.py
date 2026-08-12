"""Incremental synchronizer for Football Intelligence core leagues."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from football_intelligence.config.core_leagues import CORE_LEAGUES, CoreLeague
from football_intelligence.data_quality.coverage import build_normalized_coverage
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.ingestion.raw_store import LocalRawStore, RawObjectRef
from football_intelligence.normalization.api_football import normalize_fixture_bundle
from football_intelligence.providers.api_football import ApiFootballClient, ApiFootballResponse

_FINISHED = {"FT", "AET", "PEN"}

DEFAULT_REQUEST_BUDGET = 60
REQUESTS_PER_FIXTURE_LIST = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize the six core football leagues")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--max-fixtures-per-league", type=int, default=8)
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--from-date", type=date.fromisoformat)
    parser.add_argument("--to-date", type=date.fromisoformat)
    parser.add_argument("--request-budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    return parser


def check_request_budget(
    *, league_count: int, max_fixtures_per_league: int, request_budget: int
) -> int:
    """Return planned_requests, or raise SystemExit before any network call is made."""

    planned_requests = league_count * (REQUESTS_PER_FIXTURE_LIST + max_fixtures_per_league)
    if planned_requests > request_budget:
        raise SystemExit(
            f"core sync planned_requests={planned_requests} exceeds "
            f"--request-budget={request_budget}; lower --max-fixtures-per-league "
            "or raise the budget"
        )
    return planned_requests


def main() -> None:
    args = build_parser().parse_args()
    if not 1 <= args.max_fixtures_per_league <= 20:
        raise SystemExit("--max-fixtures-per-league must be between 1 and 20")
    if args.lookback_days < 1 or args.lookback_days > 14:
        raise SystemExit("--lookback-days must be between 1 and 14")
    if args.request_budget < 1:
        raise SystemExit("--request-budget must be at least 1")

    planned_requests = check_request_budget(
        league_count=len(CORE_LEAGUES),
        max_fixtures_per_league=args.max_fixtures_per_league,
        request_budget=args.request_budget,
    )

    api_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        raise SystemExit("API_FOOTBALL_KEY is required")

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    client = ApiFootballClient(api_key)
    raw_store = LocalRawStore(args.raw_dir)

    from_date, to_date = _resolve_window(
        explicit_from=args.from_date,
        explicit_to=args.to_date,
        lookback_days=args.lookback_days,
    )

    league_reports: list[dict[str, Any]] = []
    total_requests = 0

    for league in CORE_LEAGUES:
        result = _sync_league(
            client=client,
            raw_store=raw_store,
            league=league,
            season=args.season,
            from_date=from_date,
            to_date=to_date,
            max_fixtures=args.max_fixtures_per_league,
            database_url=database_url,
        )
        total_requests += int(result["request_count"])
        league_reports.append(result)

    report = {
        "provider": "api-football",
        "season": args.season,
        "window": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "generated_at": datetime.now(UTC).isoformat(),
        "request_budget": args.request_budget,
        "planned_requests": planned_requests,
        "request_count": total_requests,
        "league_count": len(league_reports),
        "leagues": league_reports,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"SYNC: PASS ({len(league_reports)} leagues, "
        f"{sum(int(item['matches']) for item in league_reports)} matches, "
        f"{total_requests} API requests)"
    )
    print(f"REPORT: {args.report}")


def _sync_league(
    *,
    client: ApiFootballClient,
    raw_store: LocalRawStore,
    league: CoreLeague,
    season: int,
    from_date: date,
    to_date: date,
    max_fixtures: int,
    database_url: str | None,
) -> dict[str, Any]:
    responses: list[ApiFootballResponse] = []
    raw_refs: list[RawObjectRef] = []

    fixtures_response = client.get(
        "fixtures",
        {
            "league": league.provider_league_id,
            "season": season,
            "from": from_date.isoformat(),
            "to": to_date.isoformat(),
        },
    )
    responses.append(fixtures_response)
    raw_refs.append(_store(raw_store, fixtures_response))

    fixture_ids = select_finished_fixture_ids(
        fixtures_response.payload,
        limit=max_fixtures,
    )

    detail_items: list[Any] = []
    for fixture_id in fixture_ids:
        detail = client.get("fixtures", {"id": fixture_id})
        responses.append(detail)
        raw_refs.append(_store(raw_store, detail))
        items = detail.payload.get("response")
        if not isinstance(items, list) or len(items) != 1:
            raise RuntimeError(f"{league.code}: fixture {fixture_id} detail unavailable")
        detail_items.extend(items)

    persistence: dict[str, Any] = {"mode": "not_requested"}
    normalized_counts = _empty_counts()
    coverage: dict[str, Any] = {}

    if detail_items:
        batch = normalize_fixture_bundle({"response": detail_items})
        normalized_counts = {
            "teams": len(batch.teams),
            "players": len(batch.players),
            "matches": len(batch.matches),
            "team_match_stats": len(batch.team_match_stats),
            "player_appearances": len(batch.appearances),
            "player_match_stats": len(batch.player_match_stats),
        }
        coverage = build_normalized_coverage(
            team_stats=batch.team_match_stats,
            player_stats=batch.player_match_stats,
        )
        if database_url:
            persistence = _persist(
                database_url=database_url,
                league=league,
                batch=batch,
                raw_refs=raw_refs,
                coverage=coverage,
                request_count=len(responses),
                season=season,
                from_date=from_date,
                to_date=to_date,
            )

    latest_kickoff = _latest_finished_kickoff(detail_items)
    freshness_hours = None
    if latest_kickoff is not None:
        freshness_hours = round(
            (datetime.now(UTC) - latest_kickoff).total_seconds() / 3600,
            2,
        )

    return {
        "competition_code": league.code,
        "provider_league_id": league.provider_league_id,
        "name": league.name,
        "request_count": len(responses),
        "fixture_ids": fixture_ids,
        "matches": normalized_counts["matches"],
        "normalized_counts": normalized_counts,
        "coverage": coverage,
        "persistence": persistence,
        "freshness": {
            "latest_finished_kickoff": latest_kickoff.isoformat() if latest_kickoff else None,
            "age_hours": freshness_hours,
            "checked_at": datetime.now(UTC).isoformat(),
        },
    }


def _persist(
    *,
    database_url: str,
    league: CoreLeague,
    batch: Any,
    raw_refs: list[RawObjectRef],
    coverage: dict[str, Any],
    request_count: int,
    season: int,
    from_date: date,
    to_date: date,
) -> dict[str, Any]:
    with connect(database_url) as connection:
        repository = ProviderRepository(connection, provider_code="api-football")
        run_id = repository.start_run(
            job_name="core-league-sync",
            trigger_kind="schedule",
            scope={
                "competition_code": league.code,
                "season": season,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
            },
        )
        repository.record_raw_objects(run_id, raw_refs)
        rows_written = repository.persist_batch(
            competition_code=league.code,
            batch=batch,
        )
        repository.upsert_capabilities(coverage)
        repository.finish_run(
            run_id,
            status="succeeded",
            request_count=request_count,
            rows_written=rows_written,
            metadata={"incremental": True},
        )
        connection.commit()
    return {"mode": "postgresql", "rows_written": rows_written}


def _store(raw_store: LocalRawStore, response: ApiFootballResponse) -> RawObjectRef:
    return raw_store.put(
        endpoint=response.endpoint,
        parameters=dict(response.parameters),
        payload=response.payload,
    )


def _resolve_window(
    *,
    explicit_from: date | None,
    explicit_to: date | None,
    lookback_days: int,
) -> tuple[date, date]:
    if (explicit_from is None) != (explicit_to is None):
        raise SystemExit("--from-date and --to-date must be supplied together")
    if explicit_from is not None and explicit_to is not None:
        if explicit_to < explicit_from:
            raise SystemExit("--to-date must be on or after --from-date")
        return explicit_from, explicit_to

    today = datetime.now(UTC).date()
    return today - timedelta(days=lookback_days - 1), today


def select_finished_fixture_ids(payload: dict[str, Any], *, limit: int) -> list[str]:
    response = payload.get("response")
    if not isinstance(response, list):
        return []

    finished: list[tuple[str, str]] = []
    for item in response:
        if not isinstance(item, dict):
            continue
        fixture = item.get("fixture")
        if not isinstance(fixture, dict):
            continue
        status = fixture.get("status")
        if not isinstance(status, dict) or status.get("short") not in _FINISHED:
            continue
        fixture_id = fixture.get("id")
        fixture_date = fixture.get("date")
        if isinstance(fixture_id, int) and isinstance(fixture_date, str):
            finished.append((fixture_date, str(fixture_id)))

    finished.sort(reverse=True)
    return [fixture_id for _, fixture_id in finished[:limit]]


def _latest_finished_kickoff(items: list[Any]) -> datetime | None:
    values: list[datetime] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        fixture = item.get("fixture")
        if not isinstance(fixture, dict):
            continue
        value = fixture.get("date")
        if not isinstance(value, str):
            continue
        try:
            values.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            continue
    return max(values) if values else None


def _empty_counts() -> dict[str, int]:
    return {
        "teams": 0,
        "players": 0,
        "matches": 0,
        "team_match_stats": 0,
        "player_appearances": 0,
        "player_match_stats": 0,
    }


if __name__ == "__main__":
    main()
