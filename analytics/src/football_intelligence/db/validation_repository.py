"""PostgreSQL read/write path for Block 12 V1 Validation."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import Connection

from football_intelligence.player_analytics.engine import MODEL_VERSION as PLAYER_MODEL_VERSION
from football_intelligence.rating_intelligence.engine import MODEL_VERSION as RATING_MODEL_VERSION
from football_intelligence.tactical_intelligence.engine import (
    MODEL_VERSION as TACTICAL_MODEL_VERSION,
)
from football_intelligence.team_analytics.engine import MODEL_VERSION as TEAM_MODEL_VERSION
from football_intelligence.validation.contracts import RatingRow, TacticalRow
from football_intelligence.validation.engine import ValidationReport, run_validation
from football_intelligence.validation.ingestion_report import IngestionRunRow

MIN_STABILITY_CONFIDENCE = 0.5


class ValidationRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def load_elo_pairs(self) -> list[tuple[float, float]]:
        rows = self._connection.execute(
            """
            select expected_result, actual_result
            from analytics.team_elo_history
            where model_version = %s
            """,
            (TEAM_MODEL_VERSION,),
        ).fetchall()
        return [(float(row[0]), float(row[1])) for row in rows]

    def load_stability_pairs(self) -> dict[str, list[tuple[float, float]]]:
        rows = self._connection.execute(
            """
            select role, window_key, player_id, scope_key, overall_score, confidence
            from analytics.player_score_snapshots
            where model_version = %s
              and window_key in ('season', 'last_10')
            """,
            (PLAYER_MODEL_VERSION,),
        ).fetchall()

        by_key: dict[tuple[str, str, int], dict[str, tuple[float, float]]] = defaultdict(dict)
        for role, window_key, player_id, scope_key, overall_score, confidence in rows:
            key = (str(role), str(scope_key), int(player_id))
            by_key[key][str(window_key)] = (float(overall_score), float(confidence))

        pairs_by_role: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for (role, _scope_key, _player_id), windows in by_key.items():
            season = windows.get("season")
            last10 = windows.get("last_10")
            if season is None or last10 is None:
                continue
            season_score, season_confidence = season
            last10_score, last10_confidence = last10
            if min(season_confidence, last10_confidence) < MIN_STABILITY_CONFIDENCE:
                continue
            pairs_by_role[role].append((season_score, last10_score))
        return dict(pairs_by_role)

    def load_rating_rows(self) -> list[RatingRow]:
        rows = self._connection.execute(
            """
            select
                rating_signal, rating_confidence, polarization_score,
                perception_confidence, evidence_count, scored_evidence_count,
                scored_source_count
            from analytics.player_rating_snapshots
            where model_version = %s
            """,
            (RATING_MODEL_VERSION,),
        ).fetchall()
        return [
            RatingRow(
                rating_signal=str(row[0]),
                rating_confidence=float(row[1]),
                polarization_score=(None if row[2] is None else float(row[2])),
                perception_confidence=float(row[3]),
                evidence_count=int(row[4]),
                scored_evidence_count=int(row[5]),
                scored_source_count=int(row[6]),
            )
            for row in rows
        ]

    def load_tactical_rows(self) -> list[TacticalRow]:
        rows = self._connection.execute(
            """
            select
                matches, formation_matches, style_signal,
                defensive_signal, formation_signal, tactical_confidence
            from analytics.team_tactical_snapshots
            where model_version = %s
            """,
            (TACTICAL_MODEL_VERSION,),
        ).fetchall()
        return [
            TacticalRow(
                matches=int(row[0]),
                formation_matches=int(row[1]),
                style_signal=str(row[2]),
                defensive_signal=str(row[3]),
                formation_signal=str(row[4]),
                tactical_confidence=float(row[5]),
            )
            for row in rows
        ]

    def load_ingestion_runs(self, *, since_days: int = 30) -> list[IngestionRunRow]:
        cutoff = datetime.now(UTC) - timedelta(days=since_days)
        rows = self._connection.execute(
            """
            select job_name, status, request_count, started_at
            from ingestion.ingestion_runs
            where started_at >= %s
            """,
            (cutoff,),
        ).fetchall()
        return [
            IngestionRunRow(
                job_name=str(row[0]),
                status=str(row[1]),
                request_count=int(row[2]),
                started_at=row[3],
            )
            for row in rows
        ]

    def persist_run(
        self,
        *,
        model_version: str,
        hard_status: str,
        calibration_status: str,
        summary: dict[str, Any],
        report: dict[str, Any],
        calculated_at: datetime,
    ) -> None:
        self._connection.execute(
            """
            insert into analytics.model_validation_runs (
                model_version, hard_status, calibration_status,
                summary, report, calculated_at
            )
            values (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
            """,
            (
                model_version,
                hard_status,
                calibration_status,
                json.dumps(summary, sort_keys=True),
                json.dumps(report, sort_keys=True),
                calculated_at,
            ),
        )

    def latest_run(self) -> dict[str, Any] | None:
        row = self._connection.execute(
            """
            select model_version, hard_status, calibration_status, summary, calculated_at
            from analytics.model_validation_runs
            order by calculated_at desc
            limit 1
            """
        ).fetchone()
        if row is None:
            return None
        return {
            "model_version": str(row[0]),
            "hard_status": str(row[1]),
            "calibration_status": str(row[2]),
            "summary": row[3],
            "calculated_at": row[4],
        }


def report_from_repository(repository: ValidationRepository) -> ValidationReport:
    return run_validation(
        elo_rows=repository.load_elo_pairs(),
        stability_pairs_by_role=repository.load_stability_pairs(),
        rating_rows=repository.load_rating_rows(),
        tactical_rows=repository.load_tactical_rows(),
        ingestion_rows=repository.load_ingestion_runs(),
    )
