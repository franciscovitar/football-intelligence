"""Calculate and persist Rating Intelligence V1."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from football_intelligence.db.provider_repository import connect
from football_intelligence.db.rating_intelligence_repository import (
    RatingIntelligenceRepository,
)
from football_intelligence.rating_intelligence.engine import (
    EVIDENCE_WINDOW_DAYS,
    MODEL_VERSION,
    PERCEPTION_MODEL_VERSION,
    PERFORMANCE_MODEL_VERSION,
    calculate_rating_intelligence,
)
from football_intelligence.rating_intelligence.models import PlayerRatingSnapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate Rating Intelligence V1")
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

    scope_key = f"core:{season}"
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=EVIDENCE_WINDOW_DAYS)

    with connect(database_url) as connection:
        repository = RatingIntelligenceRepository(connection)
        performance = repository.load_performance(
            scope_key=scope_key,
            model_version=PERFORMANCE_MODEL_VERSION,
        )
        if not performance:
            report = {
                "model_version": MODEL_VERSION,
                "performance_model_version": PERFORMANCE_MODEL_VERSION,
                "perception_model_version": PERCEPTION_MODEL_VERSION,
                "season": season,
                "scope_key": scope_key,
                "status": "skipped",
                "reason": f"No {PERFORMANCE_MODEL_VERSION} snapshots found",
                "evidence_window_days": EVIDENCE_WINDOW_DAYS,
                "evidence_rows": 0,
                "persisted_count": 0,
                "signals": {},
                "underrated": [],
                "overrated": [],
            }
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(f"RATING INTELLIGENCE: SKIP (no {PERFORMANCE_MODEL_VERSION} snapshots)")
            print(f"REPORT: {args.report}")
            return

        evidence = repository.load_evidence(
            player_ids=[item.player_id for item in performance],
            cutoff=cutoff,
            ingestion_version=PERCEPTION_MODEL_VERSION,
        )
        snapshots = calculate_rating_intelligence(
            performance,
            evidence,
            calculated_at=now,
        )
        repository.replace_snapshots(
            snapshots,
            scope_key=scope_key,
            model_version=MODEL_VERSION,
        )
        persisted_count = repository.snapshot_count(
            scope_key=scope_key,
            model_version=MODEL_VERSION,
        )
        connection.commit()

    report = _build_report(
        season=season,
        scope_key=scope_key,
        snapshots=snapshots,
        evidence_rows=len(evidence),
        persisted_count=persisted_count,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"RATING INTELLIGENCE: PASS ({persisted_count} player snapshots)")
    print(f"REPORT: {args.report}")


def _build_report(
    *,
    season: str,
    scope_key: str,
    snapshots: tuple[PlayerRatingSnapshot, ...],
    evidence_rows: int,
    persisted_count: int,
) -> dict[str, Any]:
    signals = Counter(item.rating_signal for item in snapshots)

    def candidates(signal: str, *, reverse: bool) -> list[dict[str, Any]]:
        selected = [
            item
            for item in snapshots
            if item.rating_signal == signal and item.rating_gap is not None
        ]
        selected.sort(key=lambda item: item.rating_gap or 0.0, reverse=reverse)
        return [
            {
                "player_id": item.player_id,
                "player_name": item.player_name,
                "rating_gap": item.rating_gap,
                "rating_confidence": item.rating_confidence,
                "performance_score": item.performance_score,
                "perception_score": item.perception_score,
            }
            for item in selected[:10]
        ]

    return {
        "model_version": MODEL_VERSION,
        "performance_model_version": PERFORMANCE_MODEL_VERSION,
        "perception_model_version": PERCEPTION_MODEL_VERSION,
        "season": season,
        "scope_key": scope_key,
        "evidence_window_days": EVIDENCE_WINDOW_DAYS,
        "evidence_rows": evidence_rows,
        "persisted_count": persisted_count,
        "signals": dict(sorted(signals.items())),
        "underrated": candidates("underrated", reverse=True),
        "overrated": candidates("overrated", reverse=False),
    }


if __name__ == "__main__":
    main()
