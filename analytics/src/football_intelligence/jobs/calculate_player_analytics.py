"""Persist V1 compatibility snapshots and catalog-driven Player V2."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from football_intelligence.config.core_leagues import CORE_LEAGUES, league_by_code
from football_intelligence.db.player_analytics_repository import PlayerAnalyticsRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.player_analytics.engine import (
    MODEL_VERSION as V1_MODEL_VERSION,
)
from football_intelligence.player_analytics.engine import (
    calculate_player_analytics,
)
from football_intelligence.player_analytics.engine_v2 import (
    MODEL_VERSION as V2_MODEL_VERSION,
)
from football_intelligence.player_analytics.engine_v2 import (
    PlayerAnalyticsResultV2,
    PlayerScoreV2,
    calculate_player_analytics_v2_result,
)
from football_intelligence.player_analytics.models import PlayerAnalyticsResult


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate evidence-aware V2 player analytics")
    parser.add_argument("--season", required=True)
    parser.add_argument("--competition")
    parser.add_argument("--scope-key")
    parser.add_argument("--database-url")
    parser.add_argument("--report", type=Path, required=True)
    return parser


def resolve_analysis_scope(
    *,
    season: str,
    competition: str | None,
    scope_key: str | None,
) -> tuple[tuple[str, ...], str, str | None]:
    normalized_season = season.strip()
    if not normalized_season:
        raise ValueError("--season must not be blank")

    normalized_competition = competition.strip().upper() if competition else None
    competition_codes: tuple[str, ...]
    if normalized_competition:
        try:
            league_by_code(normalized_competition)
        except KeyError as exc:
            raise ValueError(
                "Unsupported --competition "
                f"{normalized_competition!r}; use a configured core league code"
            ) from exc
        competition_codes = (normalized_competition,)
        default_scope = f"competition:{normalized_competition}:{normalized_season}"
    else:
        competition_codes = tuple(league.code for league in CORE_LEAGUES)
        default_scope = f"core:{normalized_season}"

    effective_scope = (scope_key or default_scope).strip()
    if not effective_scope:
        raise ValueError("--scope-key must not be blank")
    return competition_codes, effective_scope, normalized_competition


def main() -> None:
    args = build_parser().parse_args()
    season = str(args.season).strip()
    try:
        competition_codes, scope_key, competition = resolve_analysis_scope(
            season=season,
            competition=args.competition,
            scope_key=args.scope_key,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    with connect(database_url) as connection:
        repository = PlayerAnalyticsRepository(connection)
        observations = repository.load_observations(
            season_label=season,
            competition_codes=competition_codes,
        )
        if not observations:
            competition_note = competition or "configured core leagues"
            raise SystemExit(
                f"No finished player observations found for {competition_note} in season {season}"
            )

        result = calculate_player_analytics(
            observations,
            scope_key=scope_key,
        )
        if not result.scores:
            raise SystemExit("Player analytics produced no scores")

        v2_result = calculate_player_analytics_v2_result(
            observations,
            scope_key=scope_key,
        )
        v2_scores = v2_result.scores

        _persist_versioned_snapshots(
            repository,
            v1_result=result,
            v2_result=v2_result,
            scope_key=scope_key,
        )
        counts = repository.snapshot_counts(
            scope_key=scope_key,
            model_version=V2_MODEL_VERSION,
        )
        connection.commit()

    report = _build_report(
        season=season,
        competition=competition,
        scope_key=scope_key,
        scores=v2_scores,
        counts=counts,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        f"PLAYER ANALYTICS: PASS "
        f"({len(v2_scores)} score snapshots, {len(v2_result.features)} feature snapshots)"
    )
    print(f"REPORT: {args.report}")


def _persist_versioned_snapshots(
    repository: PlayerAnalyticsRepository,
    *,
    v1_result: PlayerAnalyticsResult,
    v2_result: PlayerAnalyticsResultV2,
    scope_key: str,
) -> None:
    """Persist each engine under its own model version.

    This intentionally keeps V1 compatibility snapshots separate from the
    evidence-aware V2 feature set. In particular, a nullable unsupported raw
    metric may participate in V1's legacy zero-event compatibility semantics,
    while V2 must keep it absent and expose the resulting evidence gap.
    """

    repository.replace_snapshots(
        v1_result,
        scope_key=scope_key,
        model_version=V1_MODEL_VERSION,
        data_context="real",
    )
    repository.replace_snapshots(
        v2_result,
        scope_key=scope_key,
        model_version=V2_MODEL_VERSION,
        data_context="real",
    )


def _build_report(
    *,
    season: str,
    competition: str | None,
    scope_key: str,
    scores: Sequence[PlayerScoreV2],
    counts: dict[str, int],
) -> dict[str, Any]:
    rankings: dict[str, dict[str, list[dict[str, Any]]]] = {}

    for window in ("season", "last_5"):
        rankings[window] = {}
        for role in ("goalkeeper", "defender", "midfielder", "forward"):
            candidates = [
                score
                for score in scores
                if score.window == window
                and score.role == role
                and score.evidence_state == "ready"
                and score.overall_score is not None
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
                    "evidence_coverage_pct": score.evidence_coverage_pct,
                    "evidence_state": score.evidence_state,
                    "dimensions": dict(score.dimension_scores),
                }
                for score in candidates[:10]
            ]

    return {
        "model_version": V2_MODEL_VERSION,
        "season": season,
        "competition": competition,
        "scope_key": scope_key,
        "score_snapshot_count": counts["scores"],
        "feature_snapshot_count": counts["features"],
        "evidence_state_counts": dict(Counter(score.evidence_state for score in scores)),
        "rankings": rankings,
    }


if __name__ == "__main__":
    main()
