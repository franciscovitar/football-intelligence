"""Assess whether the real ENG_PL snapshot can produce player scores.

The retained public snapshot is match/team-only and explicitly uncertified
for redistribution while permission is unknown. This job therefore
reports an explicit insufficient-data state instead of manufacturing player
rankings or diagnostics. Real per-match player observations, when a permitted
source is configured, use the normal V2 player analytics job and the same
`analytics.player_score_snapshots` read path as Home/Rankings/Player.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Literal

import psycopg
from psycopg import Connection

COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2025/26"
RealSnapshotState = Literal["ready", "insufficient_data"]


@dataclass(frozen=True, slots=True)
class RealSnapshotAssessment:
    state: RealSnapshotState
    competition: str
    season: str
    match_count: int
    team_stat_rows: int
    player_observation_rows: int
    score_rows_written: int
    diagnostic_findings_written: int
    reason: str | None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assess real ENG_PL 2025/26 score readiness without synthetic fallbacks."
    )
    parser.add_argument("--database-url", type=str, default=None)
    return parser


def assess_real_snapshot(connection: Connection[Any]) -> RealSnapshotAssessment:
    row = connection.execute(
        """
        select
            count(distinct m.id),
            count(distinct (tms.match_id, tms.team_id)),
            count(distinct (pa.match_id, pa.player_id))
                filter (where pa.player_id is not null)
        from football.seasons s
        join football.competitions c on c.id = s.competition_id
        left join football.matches m on m.season_id = s.id and m.status = 'finished'
        left join football.team_match_stats tms on tms.match_id = m.id
        left join football.player_appearances pa on pa.match_id = m.id and pa.minutes > 0
        where c.code = %s and s.label = %s
        """,
        (COMPETITION_CODE, SEASON_LABEL),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to assess real snapshot")

    match_count, team_stat_rows, player_observation_rows = map(int, row)
    if player_observation_rows == 0:
        return RealSnapshotAssessment(
            state="insufficient_data",
            competition=COMPETITION_CODE,
            season=SEASON_LABEL,
            match_count=match_count,
            team_stat_rows=team_stat_rows,
            player_observation_rows=0,
            score_rows_written=0,
            diagnostic_findings_written=0,
            reason=(
                "No permitted rich domestic player-match source is present; "
                "team/match evidence cannot be converted into player rankings."
            ),
        )

    return RealSnapshotAssessment(
        state="ready",
        competition=COMPETITION_CODE,
        season=SEASON_LABEL,
        match_count=match_count,
        team_stat_rows=team_stat_rows,
        player_observation_rows=player_observation_rows,
        score_rows_written=0,
        diagnostic_findings_written=0,
        reason="Run football-intelligence-player-analytics to calculate and persist V2 scores.",
    )


def main() -> None:
    args = build_parser().parse_args()
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (env var or --database-url)")

    with psycopg.connect(database_url, autocommit=False) as connection:
        assessment = assess_real_snapshot(connection)
    print(json.dumps(asdict(assessment), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
