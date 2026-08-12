"""PostgreSQL read/write path for Rating Intelligence V1."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from psycopg import Connection

from football_intelligence.rating_intelligence.models import (
    PlayerRatingInput,
    PlayerRatingSnapshot,
    RatingEvidence,
    SourceKind,
)


class RatingIntelligenceRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def load_performance(
        self,
        *,
        scope_key: str,
        model_version: str,
    ) -> list[PlayerRatingInput]:
        rows = self._connection.execute(
            """
            select
                m.player_id,
                p.display_name,
                m.scope_key,
                m.role,
                m.stable_score,
                m.stable_confidence
            from analytics.player_meta_snapshots as m
            join football.players as p on p.id = m.player_id
            where m.scope_key = %s
              and m.model_version = %s
            order by m.player_id
            """,
            (scope_key, model_version),
        ).fetchall()
        return [
            PlayerRatingInput(
                player_id=int(row[0]),
                player_name=str(row[1]),
                scope_key=str(row[2]),
                role=str(row[3]),
                stable_score=float(row[4]),
                stable_confidence=float(row[5]),
            )
            for row in rows
        ]

    def load_evidence(
        self,
        *,
        player_ids: Sequence[int],
        cutoff: datetime,
        ingestion_version: str,
    ) -> list[RatingEvidence]:
        if not player_ids:
            return []

        rows = self._connection.execute(
            """
            select
                e.id,
                m.player_id,
                s.id,
                s.code,
                s.source_kind,
                e.title,
                e.excerpt,
                m.matched_text,
                coalesce(e.published_at, e.discovered_at) as evidence_at,
                e.discovered_at
            from perception.player_evidence_mentions as m
            join perception.evidence_items as e on e.id = m.evidence_id
            join perception.sources as s on s.id = e.source_id
            where m.player_id = any(%s::bigint[])
              and e.duplicate_of_id is null
              and e.ingestion_version = %s
              and s.is_active
              and coalesce(e.published_at, e.discovered_at) >= %s
            order by m.player_id, s.id, e.id
            """,
            (list(player_ids), ingestion_version, cutoff),
        ).fetchall()

        return [
            RatingEvidence(
                evidence_id=int(row[0]),
                player_id=int(row[1]),
                source_id=int(row[2]),
                source_code=str(row[3]),
                source_kind=cast(SourceKind, str(row[4])),
                title=str(row[5]),
                excerpt=str(row[6]) if row[6] is not None else None,
                matched_text=str(row[7]),
                published_at=row[8],
                discovered_at=row[9],
            )
            for row in rows
        ]

    def replace_snapshots(
        self,
        snapshots: Sequence[PlayerRatingSnapshot],
        *,
        scope_key: str,
        model_version: str,
    ) -> None:
        self._connection.execute(
            """
            delete from analytics.player_rating_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        )

        for snapshot in snapshots:
            self._connection.execute(
                """
                insert into analytics.player_rating_snapshots (
                    player_id, scope_key, role,
                    performance_score, performance_confidence,
                    perception_score, perception_confidence, perception_signal,
                    rating_gap, rating_confidence, rating_signal,
                    consensus_score, polarization_score,
                    evidence_count, scored_evidence_count,
                    source_count, scored_source_count, evidence_window_days,
                    evidence_breakdown,
                    performance_model_version, perception_model_version,
                    model_version, calculated_at
                )
                values (
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s::jsonb,
                    %s, %s,
                    %s, %s
                )
                """,
                (
                    snapshot.player_id,
                    snapshot.scope_key,
                    snapshot.role,
                    snapshot.performance_score,
                    snapshot.performance_confidence,
                    snapshot.perception_score,
                    snapshot.perception_confidence,
                    snapshot.perception_signal,
                    snapshot.rating_gap,
                    snapshot.rating_confidence,
                    snapshot.rating_signal,
                    snapshot.consensus_score,
                    snapshot.polarization_score,
                    snapshot.evidence_count,
                    snapshot.scored_evidence_count,
                    snapshot.source_count,
                    snapshot.scored_source_count,
                    snapshot.evidence_window_days,
                    json.dumps(list(snapshot.evidence_breakdown), sort_keys=True),
                    snapshot.performance_model_version,
                    snapshot.perception_model_version,
                    snapshot.model_version,
                    snapshot.calculated_at,
                ),
            )

    def snapshot_count(self, *, scope_key: str, model_version: str) -> int:
        row = self._connection.execute(
            """
            select count(*)
            from analytics.player_rating_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to count rating snapshots")
        return int(row[0])
