"""PostgreSQL read/write path for Expectation & Meta Intelligence."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from football_intelligence.meta_analytics.models import (
    PlayerMetaSnapshot,
    PlayerScoreEvidence,
)


class MetaAnalyticsRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def load_score_evidence(
        self,
        *,
        current_scope_key: str,
        history_scope_keys: Sequence[str],
        source_model_version: str,
    ) -> list[PlayerScoreEvidence]:
        scopes = [current_scope_key, *history_scope_keys]
        period_by_scope = {scope: index for index, scope in enumerate(scopes)}
        rows = self._connection.execute(
            """
            select
                s.player_id,
                p.display_name,
                s.scope_key,
                s.window_key,
                s.role,
                s.overall_score,
                s.confidence,
                s.model_version
            from analytics.player_score_snapshots as s
            join football.players as p
              on p.id = s.player_id
            where s.scope_key = any(%s)
              and s.model_version = %s
              and s.window_key in ('season', 'last_3', 'last_5', 'last_10')
            order by s.player_id, s.scope_key, s.window_key
            """,
            (scopes, source_model_version),
        ).fetchall()

        evidence: list[PlayerScoreEvidence] = []
        for row in rows:
            scope_key = str(row[2])
            period_index = period_by_scope.get(scope_key)
            if period_index is None:
                continue
            evidence.append(
                PlayerScoreEvidence(
                    player_id=int(row[0]),
                    player_name=str(row[1]),
                    scope_key=scope_key,
                    period_index=period_index,
                    window=str(row[3]),
                    role=str(row[4]),
                    overall_score=float(row[5]),
                    confidence=float(row[6]),
                    model_version=str(row[7]),
                )
            )
        return evidence

    def replace_snapshots(
        self,
        snapshots: Sequence[PlayerMetaSnapshot],
        *,
        scope_key: str,
        model_version: str,
    ) -> None:
        self._connection.execute(
            """
            delete from analytics.player_meta_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        )

        for snapshot in snapshots:
            self._connection.execute(
                """
                insert into analytics.player_meta_snapshots (
                    player_id, scope_key, role,
                    performance_score, performance_confidence,
                    form_score, form_confidence,
                    stable_score, stable_confidence,
                    expectation_score, expectation_confidence,
                    surprise_delta, surprise_signal,
                    trend_delta, trend_confidence, trend_signal,
                    watchlist_score, watchlist_signal,
                    history_seasons, baseline_evidence, trend_evidence,
                    source_model_version, model_version, calculated_at
                )
                values (
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s::jsonb, %s::jsonb,
                    %s, %s, %s
                )
                """,
                (
                    snapshot.player_id,
                    snapshot.scope_key,
                    snapshot.role,
                    snapshot.performance_score,
                    snapshot.performance_confidence,
                    snapshot.form_score,
                    snapshot.form_confidence,
                    snapshot.stable_score,
                    snapshot.stable_confidence,
                    snapshot.expectation_score,
                    snapshot.expectation_confidence,
                    snapshot.surprise_delta,
                    snapshot.surprise_signal,
                    snapshot.trend_delta,
                    snapshot.trend_confidence,
                    snapshot.trend_signal,
                    snapshot.watchlist_score,
                    snapshot.watchlist_signal,
                    snapshot.history_seasons,
                    json.dumps(list(snapshot.baseline_evidence), sort_keys=True),
                    json.dumps(snapshot.trend_evidence, sort_keys=True),
                    snapshot.source_model_version,
                    snapshot.model_version,
                    snapshot.calculated_at,
                ),
            )

    def snapshot_count(self, *, scope_key: str, model_version: str) -> int:
        row = self._connection.execute(
            """
            select count(*)
            from analytics.player_meta_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to count meta snapshots")
        return int(row[0])
