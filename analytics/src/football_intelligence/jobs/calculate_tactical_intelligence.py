"""Calculate and persist Tactical Intelligence V1."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from football_intelligence.db.provider_repository import connect
from football_intelligence.db.tactical_intelligence_repository import (
    TacticalIntelligenceRepository,
)
from football_intelligence.tactical_intelligence.engine import (
    MODEL_VERSION,
    SOURCE_MODEL_VERSION,
    calculate_tactical_intelligence,
)
from football_intelligence.tactical_intelligence.models import TeamTacticalSnapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Calculate Tactical Intelligence V1")
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
        repository = TacticalIntelligenceRepository(connection)
        inputs = repository.load_inputs(
            season_label=season,
            source_model_version=SOURCE_MODEL_VERSION,
        )
        if not inputs:
            raise SystemExit(
                f"No {SOURCE_MODEL_VERSION} season snapshots found for season {season}"
            )

        snapshots = calculate_tactical_intelligence(inputs)
        by_scope: dict[str, list[TeamTacticalSnapshot]] = defaultdict(list)
        for snapshot in snapshots:
            by_scope[snapshot.scope_key].append(snapshot)

        scope_counts: dict[str, int] = {}
        for scope_key, scoped in by_scope.items():
            repository.replace_scope(
                scoped,
                scope_key=scope_key,
                model_version=MODEL_VERSION,
            )
            scope_counts[scope_key] = repository.snapshot_count(
                scope_key=scope_key,
                model_version=MODEL_VERSION,
            )
        connection.commit()

    report = _build_report(
        season=season,
        snapshots=snapshots,
        scope_counts=scope_counts,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"TACTICAL INTELLIGENCE: PASS ({len(snapshots)} teams, {len(scope_counts)} scopes)")
    print(f"REPORT: {args.report}")


def _build_report(
    *,
    season: str,
    snapshots: tuple[TeamTacticalSnapshot, ...],
    scope_counts: dict[str, int],
) -> dict[str, Any]:
    style_signals = Counter(item.style_signal for item in snapshots)
    formation_signals = Counter(item.formation_signal for item in snapshots)
    return {
        "model_version": MODEL_VERSION,
        "source_model_version": SOURCE_MODEL_VERSION,
        "season": season,
        "scope_counts": dict(sorted(scope_counts.items())),
        "persisted_count": sum(scope_counts.values()),
        "teams_with_formation": sum(1 for item in snapshots if item.primary_formation is not None),
        "style_signals": dict(sorted(style_signals.items())),
        "formation_signals": dict(sorted(formation_signals.items())),
    }


if __name__ == "__main__":
    main()
