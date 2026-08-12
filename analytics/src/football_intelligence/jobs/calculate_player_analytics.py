"""Calculate and persist V1 player analytics from normalized PostgreSQL data."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from football_intelligence.config.core_leagues import CORE_LEAGUES
from football_intelligence.db.player_analytics_repository import PlayerAnalyticsRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.player_analytics.engine import (
    MODEL_VERSION,
    calculate_player_analytics,
)
from football_intelligence.player_analytics.models import PlayerAnalyticsResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate V1 role-aware player analytics")
    parser.add_argument("--season", required=True)
    parser.add_argument("--scope-key")
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

    scope_key = args.scope_key or f"core:{season}"
    competition_codes = tuple(league.code for league in CORE_LEAGUES)

    with connect(database_url) as connection:
        repository = PlayerAnalyticsRepository(connection)
        observations = repository.load_observations(
            season_label=season,
            competition_codes=competition_codes,
        )
        if not observations:
            raise SystemExit(
                f"No finished player observations found for core leagues in season {season}"
            )

        result = calculate_player_analytics(
            observations,
            scope_key=scope_key,
        )
        if not result.scores:
            raise SystemExit("Player analytics produced no scores")

        repository.replace_snapshots(
            result,
            scope_key=scope_key,
            model_version=MODEL_VERSION,
        )
        counts = repository.snapshot_counts(
            scope_key=scope_key,
            model_version=MODEL_VERSION,
        )
        connection.commit()

    report = _build_report(
        season=season,
        scope_key=scope_key,
        result=result,
        counts=counts,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        f"PLAYER ANALYTICS: PASS "
        f"({len(result.scores)} score snapshots, {len(result.features)} feature snapshots)"
    )
    print(f"REPORT: {args.report}")


def _build_report(
    *,
    season: str,
    scope_key: str,
    result: PlayerAnalyticsResult,
    counts: dict[str, int],
) -> dict[str, Any]:
    rankings: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for window in ("season", "last_5"):
        rankings[window] = {}
        for role in ("goalkeeper", "defender", "midfielder", "forward"):
            candidates = [
                score for score in result.scores if score.window == window and score.role == role
            ]
            candidates.sort(
                key=lambda item: (item.overall_score, item.confidence),
                reverse=True,
            )
            rankings[window][role] = [
                {
                    "player_id": score.player_id,
                    "player_name": score.player_name,
                    "score": score.overall_score,
                    "confidence": score.confidence,
                    "minutes": score.minutes,
                    "dimensions": dict(score.dimension_scores),
                }
                for score in candidates[:10]
            ]

    return {
        "model_version": MODEL_VERSION,
        "season": season,
        "scope_key": scope_key,
        "score_snapshot_count": counts["scores"],
        "feature_snapshot_count": counts["features"],
        "rankings": rankings,
    }


if __name__ == "__main__":
    main()
