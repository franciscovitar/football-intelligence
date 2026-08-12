"""PostgreSQL read/write path for Tactical Intelligence V1."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from psycopg import Connection

from football_intelligence.tactical_intelligence.models import (
    FormationObservation,
    TeamTacticalInput,
    TeamTacticalSnapshot,
)


class TacticalIntelligenceRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def load_inputs(
        self,
        *,
        season_label: str,
        source_model_version: str,
    ) -> list[TeamTacticalInput]:
        rows = self._connection.execute(
            """
            select
                score.team_id,
                t.name,
                s.competition_id,
                c.code,
                c.name,
                score.season_id,
                s.label,
                score.scope_key,
                score.matches,
                score.confidence,
                score.dimension_scores
            from analytics.team_score_snapshots as score
            join football.teams as t on t.id = score.team_id
            join football.seasons as s on s.id = score.season_id
            join football.competitions as c on c.id = s.competition_id
            where s.label = %s
              and score.window_key = 'season'
              and score.model_version = %s
            order by c.code, score.team_id
            """,
            (season_label, source_model_version),
        ).fetchall()
        if not rows:
            return []

        team_seasons = {(int(row[0]), int(row[5])) for row in rows}
        team_ids = sorted({team_id for team_id, _ in team_seasons})
        season_ids = sorted({season_id for _, season_id in team_seasons})

        formation_rows = self._connection.execute(
            """
            select
                lineup.team_id,
                m.season_id,
                lineup.match_id,
                m.kickoff_at,
                lineup.formation
            from football.team_match_lineups as lineup
            join football.matches as m on m.id = lineup.match_id
            where lineup.team_id = any(%s::bigint[])
              and m.season_id = any(%s::bigint[])
              and lineup.formation is not null
            order by lineup.team_id, m.kickoff_at desc, lineup.match_id desc
            """,
            (team_ids, season_ids),
        ).fetchall()

        formations: dict[tuple[int, int], list[FormationObservation]] = defaultdict(list)
        for row in formation_rows:
            kickoff_at = row[3]
            if not isinstance(kickoff_at, datetime):
                continue
            formations[(int(row[0]), int(row[1]))].append(
                FormationObservation(
                    match_id=int(row[2]),
                    kickoff_at=kickoff_at,
                    formation=str(row[4]),
                )
            )

        result: list[TeamTacticalInput] = []
        for row in rows:
            team_id = int(row[0])
            season_id = int(row[5])
            result.append(
                TeamTacticalInput(
                    team_id=team_id,
                    team_name=str(row[1]),
                    competition_id=int(row[2]),
                    competition_code=str(row[3]),
                    competition_name=str(row[4]),
                    season_id=season_id,
                    season_label=str(row[6]),
                    scope_key=str(row[7]),
                    matches=int(row[8]),
                    source_confidence=float(row[9]),
                    dimension_scores=_numeric_mapping(row[10]),
                    formations=tuple(formations.get((team_id, season_id), [])),
                )
            )
        return result

    def replace_scope(
        self,
        snapshots: Sequence[TeamTacticalSnapshot],
        *,
        scope_key: str,
        model_version: str,
    ) -> None:
        self._connection.execute(
            """
            delete from analytics.team_tactical_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        )

        for snapshot in snapshots:
            self._connection.execute(
                """
                insert into analytics.team_tactical_snapshots (
                    team_id, season_id, scope_key, matches,
                    source_confidence,
                    control_score, attacking_volume_score,
                    defensive_resistance_score,
                    style_signal, defensive_signal,
                    primary_formation, formation_matches,
                    formation_share, formation_confidence, formation_signal,
                    alternative_formations,
                    tactical_confidence, summary, evidence,
                    source_model_version, model_version, calculated_at
                )
                values (
                    %s, %s, %s, %s,
                    %s,
                    %s, %s,
                    %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s::jsonb,
                    %s, %s, %s::jsonb,
                    %s, %s, %s
                )
                """,
                (
                    snapshot.team_id,
                    snapshot.season_id,
                    snapshot.scope_key,
                    snapshot.matches,
                    snapshot.source_confidence,
                    snapshot.control_score,
                    snapshot.attacking_volume_score,
                    snapshot.defensive_resistance_score,
                    snapshot.style_signal,
                    snapshot.defensive_signal,
                    snapshot.primary_formation,
                    snapshot.formation_matches,
                    snapshot.formation_share,
                    snapshot.formation_confidence,
                    snapshot.formation_signal,
                    json.dumps(list(snapshot.alternative_formations), sort_keys=True),
                    snapshot.tactical_confidence,
                    snapshot.summary,
                    json.dumps(snapshot.evidence, sort_keys=True),
                    snapshot.source_model_version,
                    snapshot.model_version,
                    snapshot.calculated_at,
                ),
            )

    def snapshot_count(self, *, scope_key: str, model_version: str) -> int:
        row = self._connection.execute(
            """
            select count(*)
            from analytics.team_tactical_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to count tactical snapshots")
        return int(row[0])


def _numeric_mapping(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, candidate in value.items():
        if (
            isinstance(key, str)
            and isinstance(candidate, (int, float))
            and not isinstance(candidate, bool)
        ):
            result[key] = float(candidate)
    return result
