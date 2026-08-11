"""Live API-Football provider coverage audit.

This command intentionally samples a small number of completed fixtures. It is a
coverage/audit job, not the production synchronizer introduced in Block 4.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from football_intelligence.data_quality.coverage import build_normalized_coverage
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.ingestion.raw_store import LocalRawStore, RawObjectRef
from football_intelligence.normalization.api_football import normalize_fixture_bundle
from football_intelligence.providers.api_football import ApiFootballClient, ApiFootballResponse

_FINISHED_STATUSES = {"FT", "AET", "PEN"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit live API-Football coverage")
    parser.add_argument("--league-id", type=int, default=39)
    parser.add_argument("--competition-code", default="ENG_PL")
    parser.add_argument("--season", type=int, default=2025)
    parser.add_argument("--sample-fixtures", type=int, default=3)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.sample_fixtures < 1 or args.sample_fixtures > 20:
        raise SystemExit("--sample-fixtures must be between 1 and 20")

    api_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if not api_key:
        raise SystemExit("API_FOOTBALL_KEY is required")

    client = ApiFootballClient(api_key)
    raw_store = LocalRawStore(args.raw_dir)

    responses: list[ApiFootballResponse] = []
    raw_refs: list[RawObjectRef] = []

    league_response = client.get(
        "leagues",
        {"id": args.league_id, "season": args.season},
    )
    responses.append(league_response)
    raw_refs.append(_store_response(raw_store, league_response))
    _validate_league_response(league_response, args.league_id, args.season)

    fixtures_response = client.get(
        "fixtures",
        {"league": args.league_id, "season": args.season},
    )
    responses.append(fixtures_response)
    raw_refs.append(_store_response(raw_store, fixtures_response))

    fixture_ids = _select_finished_fixture_ids(
        fixtures_response.payload,
        limit=args.sample_fixtures,
    )
    if not fixture_ids:
        raise SystemExit("No completed fixtures were returned for the requested league/season")

    details_response = client.get("fixtures", {"ids": "-".join(fixture_ids)})
    responses.append(details_response)
    raw_refs.append(_store_response(raw_store, details_response))

    batch = normalize_fixture_bundle(details_response.payload)
    coverage = build_normalized_coverage(
        team_stats=batch.team_match_stats,
        player_stats=batch.player_match_stats,
    )

    persistence: dict[str, Any] = {"mode": "not_requested"}
    if args.database_url:
        persistence = _persist_and_verify(
            args.database_url,
            competition_code=args.competition_code,
            batch=batch,
            raw_refs=raw_refs,
            coverage=coverage,
            request_count=len(responses),
        )

    report: dict[str, Any] = {
        "provider": "api-football",
        "league_id": args.league_id,
        "competition_code": args.competition_code,
        "season": args.season,
        "sample_fixture_ids": fixture_ids,
        "request_count": len(responses),
        "quota": _quota_summary(responses),
        "provider_declared_coverage": _provider_declared_coverage(
            league_response.payload, args.season
        ),
        "normalized_counts": {
            "teams": len(batch.teams),
            "players": len(batch.players),
            "matches": len(batch.matches),
            "team_match_stats": len(batch.team_match_stats),
            "player_appearances": len(batch.appearances),
            "player_match_stats": len(batch.player_match_stats),
        },
        "normalized_coverage": coverage,
        "persistence": persistence,
        "raw_objects": [
            {
                "bucket": raw.storage_bucket,
                "path": raw.storage_path,
                "sha256": raw.payload_sha256,
                "byte_size": raw.byte_size,
            }
            for raw in raw_refs
        ],
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(f"AUDIT: PASS ({len(fixture_ids)} fixtures, {len(responses)} API requests)")
    print(f"REPORT: {args.report}")
    remaining = report["quota"].get("remaining")
    if remaining is not None:
        print(f"API REQUESTS REMAINING: {remaining}")


def _store_response(
    raw_store: LocalRawStore,
    response: ApiFootballResponse,
) -> RawObjectRef:
    return raw_store.put(
        endpoint=response.endpoint,
        parameters=dict(response.parameters),
        payload=response.payload,
    )


def _validate_league_response(
    response: ApiFootballResponse,
    league_id: int,
    season: int,
) -> None:
    items = response.payload.get("response")
    if not isinstance(items, list) or not items:
        raise SystemExit(f"League {league_id} season {season} is unavailable")


def _select_finished_fixture_ids(payload: dict[str, Any], *, limit: int) -> list[str]:
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
        if not isinstance(status, dict) or status.get("short") not in _FINISHED_STATUSES:
            continue
        fixture_id = fixture.get("id")
        fixture_date = fixture.get("date")
        if isinstance(fixture_id, int) and isinstance(fixture_date, str):
            finished.append((fixture_date, str(fixture_id)))

    finished.sort(reverse=True)
    return [fixture_id for _, fixture_id in finished[:limit]]


def _provider_declared_coverage(
    payload: dict[str, Any],
    requested_season: int,
) -> dict[str, Any]:
    response = payload.get("response")
    if not isinstance(response, list) or not response:
        return {}
    item = response[0]
    if not isinstance(item, dict):
        return {}
    seasons = item.get("seasons")
    if not isinstance(seasons, list):
        return {}
    for season in seasons:
        if not isinstance(season, dict) or season.get("year") != requested_season:
            continue
        coverage = season.get("coverage")
        return coverage if isinstance(coverage, dict) else {}
    return {}


def _quota_summary(responses: list[ApiFootballResponse]) -> dict[str, int | None]:
    remaining_values = [
        response.request_count_remaining
        for response in responses
        if response.request_count_remaining is not None
    ]
    limit_values = [
        response.request_limit for response in responses if response.request_limit is not None
    ]
    return {
        "remaining": remaining_values[-1] if remaining_values else None,
        "limit": limit_values[-1] if limit_values else None,
    }


def _persist_and_verify(
    database_url: str,
    *,
    competition_code: str,
    batch: Any,
    raw_refs: list[RawObjectRef],
    coverage: Any,
    request_count: int,
) -> dict[str, Any]:
    with connect(database_url) as connection:
        repository = ProviderRepository(connection, provider_code="api-football")
        run_id = repository.start_run(
            job_name="provider-audit",
            trigger_kind="manual",
            scope={
                "competition_code": competition_code,
                "season": batch.season_label,
            },
        )
        repository.record_raw_objects(run_id, raw_refs)
        rows_written = repository.persist_batch(
            competition_code=competition_code,
            batch=batch,
        )
        repository.upsert_capabilities(coverage)
        first_counts = repository.snapshot_counts()

        repository.persist_batch(
            competition_code=competition_code,
            batch=batch,
        )
        second_counts = repository.snapshot_counts()
        if first_counts != second_counts:
            raise RuntimeError(f"idempotency check failed: {first_counts!r} != {second_counts!r}")

        repository.finish_run(
            run_id,
            status="succeeded",
            request_count=request_count,
            rows_written=rows_written,
            metadata={"idempotency_verified": True},
        )
        connection.commit()

    return {
        "mode": "postgresql",
        "idempotency_verified": True,
        "row_counts": second_counts,
    }


if __name__ == "__main__":
    main()
