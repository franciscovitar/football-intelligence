"""Calculate and persist competition-relative Team Analytics V1."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from football_intelligence.config.core_leagues import CORE_LEAGUES
from football_intelligence.db.provider_repository import connect
from football_intelligence.db.team_analytics_repository import TeamAnalyticsRepository
from football_intelligence.team_analytics.engine import (
    MODEL_VERSION,
    calculate_team_analytics,
)
from football_intelligence.team_analytics.models import TeamObservation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate competition-relative Team Analytics V1")
    parser.add_argument("--season", required=True)
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

    with connect(database_url) as connection:
        repository = TeamAnalyticsRepository(connection)
        observations = repository.load_observations(
            season_label=season,
            competition_codes=tuple(league.code for league in CORE_LEAGUES),
        )
        if not observations:
            raise SystemExit(f"No finished team observations found for season {season}")

        grouped: dict[tuple[int, int], list[TeamObservation]] = defaultdict(list)
        for observation in observations:
            grouped[(observation.competition_id, observation.season_id)].append(observation)

        scope_reports: list[dict[str, Any]] = []
        total_scores = 0
        total_features = 0
        total_elo = 0
        for (competition_id, season_id), scoped in grouped.items():
            first = scoped[0]
            scope_key = f"competition:{first.competition_code}:{first.season_label}"
            result = calculate_team_analytics(
                scoped,
                scope_key=scope_key,
                competition_id=competition_id,
                season_id=season_id,
            )
            if not result.scores and not result.elo_history:
                continue
            repository.replace_snapshots(
                result,
                scope_key=scope_key,
                season_id=season_id,
                model_version=MODEL_VERSION,
            )
            counts = repository.snapshot_counts(
                scope_key=scope_key,
                season_id=season_id,
                model_version=MODEL_VERSION,
            )
            total_scores += counts["scores"]
            total_features += counts["features"]
            total_elo += counts["elo"]
            scope_reports.append(
                {
                    "competition_code": first.competition_code,
                    "competition_name": first.competition_name,
                    "scope_key": scope_key,
                    "counts": counts,
                }
            )
        connection.commit()

    if not scope_reports:
        raise SystemExit("Team analytics produced no competition scopes")
    report = {
        "model_version": MODEL_VERSION,
        "season": season,
        "scope_count": len(scope_reports),
        "score_snapshot_count": total_scores,
        "feature_snapshot_count": total_features,
        "elo_history_count": total_elo,
        "scopes": sorted(scope_reports, key=lambda item: str(item["competition_code"])),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "TEAM ANALYTICS: PASS "
        f"({len(scope_reports)} scopes, {total_scores} scores, "
        f"{total_features} features, {total_elo} Elo rows)"
    )
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
