"""PostgreSQL persistence for World Radar V1 snapshots.

World Radar candidates are external to the core league graph. This
repository never creates or links `football.players`/`football.teams` rows
for them; identity stays scoped to the provider.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from football_intelligence.world_radar.models import PlayerRadarSnapshot


class WorldRadarRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def replace_snapshots(
        self,
        snapshots: Sequence[PlayerRadarSnapshot],
        *,
        season_label: str,
        model_version: str,
    ) -> None:
        self._connection.execute(
            """
            delete from analytics.world_radar_snapshots
            where season_label = %s and model_version = %s
            """,
            (season_label, model_version),
        )

        for snapshot in snapshots:
            self._connection.execute(
                """
                insert into analytics.world_radar_snapshots (
                    provider_code, provider_player_id, player_name, team_name,
                    competition_code, competition_name, country, season_label,
                    position, appearances, minutes, goals, assists,
                    metrics, radar_score, confidence, reasons, source_lists,
                    model_version, calculated_at
                )
                values (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s::jsonb, %s, %s, %s::jsonb, %s::jsonb,
                    %s, %s
                )
                """,
                (
                    snapshot.provider_code,
                    snapshot.provider_player_id,
                    snapshot.player_name,
                    snapshot.team_name,
                    snapshot.competition_code,
                    snapshot.competition_name,
                    snapshot.country,
                    snapshot.season_label,
                    snapshot.position,
                    snapshot.appearances,
                    snapshot.minutes,
                    snapshot.goals,
                    snapshot.assists,
                    json.dumps(dict(snapshot.metrics), sort_keys=True),
                    snapshot.radar_score,
                    snapshot.confidence,
                    json.dumps(list(snapshot.reasons)),
                    json.dumps(list(snapshot.source_lists)),
                    snapshot.model_version,
                    snapshot.calculated_at,
                ),
            )

    def snapshot_count(self, *, season_label: str, model_version: str) -> int:
        row = self._connection.execute(
            """
            select count(*)
            from analytics.world_radar_snapshots
            where season_label = %s and model_version = %s
            """,
            (season_label, model_version),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to count world radar snapshots")
        return int(row[0])
