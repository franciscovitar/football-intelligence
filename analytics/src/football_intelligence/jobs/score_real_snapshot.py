"""Block 16: run the diagnostic engine against the real ENG_PL 2025/26 snapshot.

`football.player_season_stats` is season-aggregate only (see
`load_real_snapshot.py`/`data/real/2025-26/README.md`) -- it has no
match-by-match rows, so the existing `player_analytics` engine (built around
per-match `PlayerObservation` aggregation) cannot consume it directly. This
job is a small, standalone bridge: it computes percentiles directly from the
season-aggregate rows (goals, expected_goals) across players meeting a
minimum-minutes sample policy, then runs the SAME deterministic
`classify_results_vs_process` classifier and diagnostic rule functions the
rest of the product uses, and persists the results into
`analytics.diagnostic_findings` exactly like every other block's diagnostics.

This does not compute an `overall_score`/full percentile suite for these
players (that needs match-level features V1 does not have here) -- it
specifically exercises and validates the finishing under/over-performance
diagnostic (the one real, currently-available-for-this-snapshot xG-based
signal) end-to-end against real numbers, per the product spec's requirement
to sanity-check the pipeline against real football before trusting it.
"""

from __future__ import annotations

import argparse
import os
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.types.json import Jsonb

from football_intelligence.diagnostics.orchestrator import (
    PlayerDiagnosticInputs,
    evaluate_player_diagnostics,
)

COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2025/26"
MIN_MINUTES_FOR_PERCENTILE = 450
_PRIOR_MINUTES = 450.0


@dataclass(frozen=True, slots=True)
class _PlayerSeasonRow:
    player_id: int
    player_name: str
    minutes: int
    goals: float | None
    expected_goals: float | None
    shots_total: float | None
    shots_on_target: float | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute results-vs-process diagnostics from football.player_season_stats "
            "(real ENG_PL 2025/26 snapshot) and persist them to analytics.diagnostic_findings."
        )
    )
    parser.add_argument("--database-url", type=str, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (env var or --database-url)")

    with psycopg.connect(database_url, autocommit=False) as connection:
        rows = _load_season_rows(connection)
        eligible = [row for row in rows if row.minutes >= MIN_MINUTES_FOR_PERCENTILE]
        print(
            f"Loaded {len(rows)} player-season rows, "
            f"{len(eligible)} eligible for percentiles (minutes >= {MIN_MINUTES_FOR_PERCENTILE})"
        )

        goals_values = sorted(row.goals for row in eligible if row.goals is not None)
        xg_values = sorted(row.expected_goals for row in eligible if row.expected_goals is not None)

        computed_at = datetime.now(UTC)
        comparison_group = f"competition:{COMPETITION_CODE}:{SEASON_LABEL}"
        findings_written = 0
        underperformers: list[tuple[str, float, float]] = []
        overperformers: list[tuple[str, float, float]] = []

        for row in eligible:
            goals_percentile = (
                _percentile(goals_values, row.goals) if row.goals is not None else None
            )
            xg_percentile = (
                _percentile(xg_values, row.expected_goals)
                if row.expected_goals is not None
                else None
            )
            confidence = min(1.0, row.minutes / (row.minutes + _PRIOR_MINUTES))

            inputs = PlayerDiagnosticInputs(
                player_id=row.player_id,
                player_name=row.player_name,
                comparison_group=comparison_group,
                window="season",
                confidence=confidence,
                goals=row.goals,
                goals_percentile=goals_percentile,
                xg=row.expected_goals,
                xg_percentile=xg_percentile,
            )
            findings = evaluate_player_diagnostics(inputs, computed_at=computed_at)
            for finding in findings:
                _upsert_finding(connection, finding)
                findings_written += 1
                if finding.diagnostic_code == "finishing_underperformance":
                    underperformers.append(
                        (row.player_name, row.goals or 0, row.expected_goals or 0)
                    )
                elif finding.diagnostic_code == "finishing_overperformance":
                    overperformers.append(
                        (row.player_name, row.goals or 0, row.expected_goals or 0)
                    )

        connection.commit()
        print(f"DONE: {findings_written} diagnostic findings written")
        _print_sample("Finishing UNDER-performance (goals << xG)", underperformers)
        _print_sample("Finishing OVER-performance (goals >> xG)", overperformers)


def _load_season_rows(connection: Connection[Any]) -> list[_PlayerSeasonRow]:
    rows = connection.execute(
        """
        select pss.player_id, p.display_name, pss.minutes, pss.goals, pss.expected_goals
        from football.player_season_stats pss
        join football.players p on p.id = pss.player_id
        join football.seasons s on s.id = pss.season_id
        join football.competitions c on c.id = s.competition_id
        where c.code = %s and s.label = %s and pss.source = 'fpl-official-api'
        """,
        (COMPETITION_CODE, SEASON_LABEL),
    ).fetchall()
    return [
        _PlayerSeasonRow(
            player_id=row[0],
            player_name=row[1],
            minutes=row[2] or 0,
            goals=float(row[3]) if row[3] is not None else None,
            expected_goals=float(row[4]) if row[4] is not None else None,
            shots_total=None,
            shots_on_target=None,
        )
        for row in rows
    ]


def _percentile(sorted_values: Sequence[float], value: float) -> float:
    if not sorted_values:
        return 50.0
    left = bisect_left(sorted_values, value)
    right = bisect_right(sorted_values, value)
    return 100.0 * (left + 0.5 * (right - left)) / len(sorted_values)


def _upsert_finding(connection: Connection[Any], finding: Any) -> None:
    connection.execute(
        """
        insert into analytics.diagnostic_findings (
            diagnostic_code, entity_type, entity_id, severity, confidence,
            supporting_metrics, comparison_group, window_key, model_version, computed_at
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (
            entity_type, entity_id, diagnostic_code, comparison_group, window_key, model_version
        )
        do update set
            severity = excluded.severity,
            confidence = excluded.confidence,
            supporting_metrics = excluded.supporting_metrics,
            computed_at = excluded.computed_at
        """,
        (
            finding.diagnostic_code,
            finding.entity_type,
            finding.entity_id,
            finding.severity,
            finding.confidence,
            Jsonb(dict(finding.supporting_metrics)),
            finding.comparison_group,
            finding.window,
            finding.model_version,
            finding.computed_at,
        ),
    )


def _print_sample(title: str, entries: list[tuple[str, float, float]]) -> None:
    print(f"\n{title} ({len(entries)} found):")
    for name, goals, xg in sorted(entries, key=lambda item: abs(item[1] - item[2]), reverse=True)[
        :5
    ]:
        print(f"  {name}: goals={goals:.0f} xG={xg:.2f}")


if __name__ == "__main__":
    main()
