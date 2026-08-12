"""Calculate and persist Expectation & Meta Intelligence V1."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from football_intelligence.db.meta_analytics_repository import MetaAnalyticsRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.meta_analytics.engine import (
    MODEL_VERSION,
    SOURCE_MODEL_VERSION,
    calculate_meta_analytics,
)
from football_intelligence.meta_analytics.models import PlayerMetaSnapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate Expectation & Meta Intelligence V1")
    parser.add_argument("--season", required=True)
    parser.add_argument("--history-season", action="append", default=[])
    parser.add_argument("--database-url")
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    season = str(args.season).strip()
    if not season:
        raise SystemExit("--season must not be blank")

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    history_seasons = _history_seasons(season, tuple(str(item) for item in args.history_season))
    current_scope_key = f"core:{season}"
    history_scope_keys = tuple(f"core:{item}" for item in history_seasons)

    with connect(database_url) as connection:
        repository = MetaAnalyticsRepository(connection)
        evidence = repository.load_score_evidence(
            current_scope_key=current_scope_key,
            history_scope_keys=history_scope_keys,
            source_model_version=SOURCE_MODEL_VERSION,
        )
        snapshots = calculate_meta_analytics(
            evidence,
            current_scope_key=current_scope_key,
        )
        if not snapshots:
            raise SystemExit(
                "No current player season scores found in "
                f"{current_scope_key} for {SOURCE_MODEL_VERSION}"
            )

        repository.replace_snapshots(
            snapshots,
            scope_key=current_scope_key,
            model_version=MODEL_VERSION,
        )
        count = repository.snapshot_count(
            scope_key=current_scope_key,
            model_version=MODEL_VERSION,
        )
        connection.commit()

    report = _build_report(
        season=season,
        history_seasons=history_seasons,
        scope_key=current_scope_key,
        snapshots=snapshots,
        persisted_count=count,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"META ANALYTICS: PASS ({count} player snapshots)")
    print(f"REPORT: {args.report}")


def _history_seasons(season: str, explicit: tuple[str, ...]) -> tuple[str, ...]:
    cleaned = tuple(item.strip() for item in explicit if item.strip())
    if cleaned:
        return cleaned[:3]
    if season.isdigit():
        current = int(season)
        return tuple(str(current - offset) for offset in range(1, 4))
    return ()


def _build_report(
    *,
    season: str,
    history_seasons: tuple[str, ...],
    scope_key: str,
    snapshots: tuple[PlayerMetaSnapshot, ...],
    persisted_count: int,
) -> dict[str, Any]:
    def top(key: Any, reverse: bool = True) -> list[dict[str, Any]]:
        candidates = sorted(snapshots, key=key, reverse=reverse)[:10]
        return [
            {
                "player_id": item.player_id,
                "player_name": item.player_name,
                "role": item.role,
                "stable_score": item.stable_score,
                "expectation_score": item.expectation_score,
                "surprise_delta": item.surprise_delta,
                "trend_delta": item.trend_delta,
                "watchlist_score": item.watchlist_score,
                "watchlist_signal": item.watchlist_signal,
            }
            for item in candidates
        ]

    surprise_candidates = tuple(item for item in snapshots if item.surprise_delta is not None)
    return {
        "model_version": MODEL_VERSION,
        "source_model_version": SOURCE_MODEL_VERSION,
        "season": season,
        "scope_key": scope_key,
        "history_seasons_requested": list(history_seasons),
        "persisted_count": persisted_count,
        "watchlist": top(lambda item: item.watchlist_score),
        "stable": top(lambda item: item.stable_score),
        "surprises": [
            {
                "player_id": item.player_id,
                "player_name": item.player_name,
                "surprise_delta": item.surprise_delta,
            }
            for item in sorted(
                surprise_candidates,
                key=lambda item: item.surprise_delta or 0.0,
                reverse=True,
            )[:10]
        ],
    }


if __name__ == "__main__":
    main()
