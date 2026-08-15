"""PostgreSQL access for player analytics inputs and snapshots."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from psycopg import Connection

from football_intelligence.player_analytics.engine_v2 import (
    PlayerAnalyticsResultV2,
    PlayerScoreV2,
)
from football_intelligence.player_analytics.models import (
    PlayerAnalyticsResult,
    PlayerObservation,
)

_STAT_COLUMNS = (
    "goals",
    "assists",
    "shots_total",
    "shots_on_target",
    "passes_total",
    "key_passes",
    "tackles",
    "blocks",
    "interceptions",
    "dribbles_successful",
    "duels_won",
    "fouls_drawn",
    "fouls_committed",
    "saves",
)


class PlayerAnalyticsRepository:
    """Load normalized observations and replace one model/scope snapshot."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def load_observations(
        self,
        *,
        season_label: str,
        competition_codes: Sequence[str],
    ) -> list[PlayerObservation]:
        if not season_label.strip():
            raise ValueError("season_label must not be blank")
        if not competition_codes:
            raise ValueError("competition_codes must not be empty")

        rows = self._connection.execute(
            """
            select
                p.id,
                p.display_name,
                pa.match_id,
                m.kickoff_at,
                pa.team_id,
                pa.minutes,
                pa.listed_position,
                tms.possession_pct,
                pms.goals,
                pms.assists,
                pms.shots_total,
                pms.shots_on_target,
                pms.passes_total,
                pms.key_passes,
                pms.tackles,
                pms.blocks,
                pms.interceptions,
                pms.dribbles_successful,
                pms.duels_won,
                pms.fouls_drawn,
                pms.fouls_committed,
                pms.saves
            from football.player_appearances as pa
            join football.players as p
              on p.id = pa.player_id
            join football.matches as m
              on m.id = pa.match_id
            join football.seasons as s
              on s.id = m.season_id
            join football.competitions as c
              on c.id = s.competition_id
            left join football.player_match_stats as pms
              on pms.match_id = pa.match_id
             and pms.player_id = pa.player_id
            left join football.team_match_stats as tms
              on tms.match_id = pa.match_id
             and tms.team_id = pa.team_id
            where s.label = %s
              and c.code = any(%s)
              and m.status = 'finished'
              and m.kickoff_at is not null
              and pa.minutes is not null
              and pa.minutes > 0
            order by p.id, m.kickoff_at desc
            """,
            (season_label, list(competition_codes)),
        ).fetchall()

        observations: list[PlayerObservation] = []
        for row in rows:
            stats = {
                metric_name: _optional_float(row[8 + index])
                for index, metric_name in enumerate(_STAT_COLUMNS)
            }
            observations.append(
                PlayerObservation(
                    player_id=int(row[0]),
                    player_name=str(row[1]),
                    match_id=int(row[2]),
                    kickoff_at=_require_datetime(row[3]),
                    team_id=int(row[4]),
                    minutes=int(row[5]),
                    listed_position=None if row[6] is None else str(row[6]),
                    possession_pct=_optional_float(row[7]),
                    stats=stats,
                )
            )
        return observations

    def replace_snapshots(
        self,
        result: PlayerAnalyticsResult | PlayerAnalyticsResultV2,
        *,
        scope_key: str,
        model_version: str,
        v2_scores: Sequence[PlayerScoreV2] | None = None,
        data_context: str = "real",
    ) -> None:
        self._connection.execute(
            """
            delete from analytics.player_feature_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        )
        self._connection.execute(
            """
            delete from analytics.player_score_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        )

        for feature in result.features:
            self._connection.execute(
                """
                insert into analytics.player_feature_snapshots (
                    player_id,
                    scope_key,
                    window_key,
                    role,
                    metric_name,
                    minutes,
                    appearances,
                    raw_per90,
                    adjusted_per90,
                    percentile,
                    reference_sample_size,
                    model_version,
                    calculated_at,
                    raw_value,
                    per90_value,
                    value_basis,
                    metric_kind,
                    metric_unit,
                    formula_version,
                    comparison_group,
                    metric_granularity,
                    percentile_state
                )
                values (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s
                )
                """,
                (
                    feature.player_id,
                    feature.scope_key,
                    feature.window,
                    feature.role,
                    feature.metric_name,
                    feature.minutes,
                    feature.appearances,
                    feature.raw_per90,
                    feature.adjusted_per90,
                    feature.percentile,
                    feature.reference_sample_size,
                    model_version,
                    feature.calculated_at,
                    getattr(feature, "raw_value", None),
                    getattr(feature, "per90_value", None),
                    getattr(feature, "value_basis", "per90"),
                    getattr(feature, "metric_kind", "raw"),
                    getattr(feature, "metric_unit", "per90"),
                    getattr(feature, "formula_version", None),
                    getattr(feature, "comparison_group", None),
                    getattr(feature, "metric_granularity", "player_match"),
                    getattr(feature, "percentile_state", "ready"),
                ),
            )

        scores = v2_scores if v2_scores is not None else result.scores
        for score in scores:
            if isinstance(score, PlayerScoreV2):
                position_family = score.position_family
                evidence_weight_available = score.evidence_weight_available
                evidence_weight_required = score.evidence_weight_required
                evidence_coverage_pct = score.evidence_coverage_pct
                evidence_state = score.evidence_state
                evidence_metrics_available = list(score.evidence_metrics_available)
                evidence_metrics_required = list(score.evidence_metrics_required)
                evidence_metrics_expected = list(score.evidence_metrics_expected)
                evidence_core_metrics = list(score.evidence_core_metrics)
                evidence_metrics_missing = list(score.evidence_metrics_missing)
                dimension_evidence = {
                    name: dataclasses.asdict(evidence)
                    for name, evidence in score.dimension_evidence.items()
                }
                profile_version = score.profile_version
            else:
                position_family = None
                evidence_weight_available = 1.0
                evidence_weight_required = 1.0
                evidence_coverage_pct = 100.0
                evidence_state = "ready"
                evidence_metrics_available = []
                evidence_metrics_required = []
                evidence_metrics_expected = []
                evidence_core_metrics = []
                evidence_metrics_missing = []
                dimension_evidence = {}
                profile_version = None
            self._connection.execute(
                """
                insert into analytics.player_score_snapshots (
                    player_id,
                    scope_key,
                    window_key,
                    role,
                    role_confidence,
                    minutes,
                    appearances,
                    overall_score,
                    confidence,
                    dimension_scores,
                    reference_sample_size,
                    model_version,
                    calculated_at,
                    position_family,
                    data_context,
                    evidence_weight_available,
                    evidence_weight_required,
                    evidence_coverage_pct,
                    evidence_state,
                    evidence_metrics_available,
                    evidence_metrics_required,
                    evidence_metrics_expected,
                    evidence_core_metrics,
                    evidence_metrics_missing,
                    dimension_evidence,
                    profile_version
                )
                values (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s::jsonb, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s::jsonb, %s
                )
                """,
                (
                    score.player_id,
                    score.scope_key,
                    score.window,
                    score.role,
                    score.role_confidence,
                    score.minutes,
                    score.appearances,
                    score.overall_score,
                    score.confidence,
                    json.dumps(dict(score.dimension_scores), sort_keys=True),
                    score.reference_sample_size,
                    model_version,
                    score.calculated_at,
                    position_family,
                    data_context,
                    evidence_weight_available,
                    evidence_weight_required,
                    evidence_coverage_pct,
                    evidence_state,
                    evidence_metrics_available,
                    evidence_metrics_required,
                    evidence_metrics_expected,
                    evidence_core_metrics,
                    evidence_metrics_missing,
                    json.dumps(dimension_evidence, sort_keys=True),
                    profile_version,
                ),
            )

    def snapshot_counts(self, *, scope_key: str, model_version: str) -> dict[str, int]:
        feature_row = self._connection.execute(
            """
            select count(*)
            from analytics.player_feature_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        ).fetchone()
        score_row = self._connection.execute(
            """
            select count(*)
            from analytics.player_score_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, model_version),
        ).fetchone()
        if feature_row is None or score_row is None:
            raise RuntimeError("failed to count player analytics snapshots")
        return {
            "features": int(feature_row[0]),
            "scores": int(score_row[0]),
        }


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _require_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError("expected PostgreSQL timestamptz as datetime")
    return value
