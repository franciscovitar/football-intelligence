"""PostgreSQL inputs and versioned Team Analytics snapshot persistence."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from psycopg import Connection

from football_intelligence.team_analytics.engine_v2 import TeamAnalyticsResultV2
from football_intelligence.team_analytics.models import (
    TeamAnalyticsResult,
    TeamObservation,
)


class TeamAnalyticsRepository:
    """Load finished team observations and replace versioned scope snapshots."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def load_observations(
        self,
        *,
        season_label: str,
        competition_codes: Sequence[str],
    ) -> list[TeamObservation]:
        if not season_label.strip():
            raise ValueError("season_label must not be blank")
        if not competition_codes:
            raise ValueError("competition_codes must not be empty")

        rows = self._connection.execute(
            """
            select
                c.id as competition_id,
                c.code as competition_code,
                c.name as competition_name,
                s.id as season_id,
                s.label as season_label,
                side.team_id,
                t.name as team_name,
                side.opponent_team_id,
                m.id as match_id,
                m.kickoff_at,
                side.is_home,
                side.goals_for,
                side.goals_against,
                own_stats.shots_total,
                own_stats.shots_on_target,
                own_stats.shots_inside_box,
                own_stats.corners,
                opponent_stats.shots_total,
                opponent_stats.shots_on_target,
                opponent_stats.shots_inside_box,
                own_stats.possession_pct,
                own_stats.passes_total,
                own_stats.passes_accurate,
                opponent_stats.passes_total
            from football.matches as m
            join football.seasons as s
              on s.id = m.season_id
            join football.competitions as c
              on c.id = s.competition_id
            cross join lateral (
                values
                    (
                        m.home_team_id,
                        m.away_team_id,
                        true,
                        m.home_score,
                        m.away_score
                    ),
                    (
                        m.away_team_id,
                        m.home_team_id,
                        false,
                        m.away_score,
                        m.home_score
                    )
            ) as side(team_id, opponent_team_id, is_home, goals_for, goals_against)
            join football.teams as t
              on t.id = side.team_id
            left join football.team_match_stats as own_stats
              on own_stats.match_id = m.id
             and own_stats.team_id = side.team_id
            left join football.team_match_stats as opponent_stats
              on opponent_stats.match_id = m.id
             and opponent_stats.team_id = side.opponent_team_id
            where s.label = %s
              and c.code = any(%s)
              and m.status = 'finished'
              and m.kickoff_at is not null
              and m.home_score is not null
              and m.away_score is not null
            order by c.code, s.id, m.kickoff_at, m.id, side.is_home desc
            """,
            (season_label, list(competition_codes)),
        ).fetchall()

        return [
            TeamObservation(
                competition_id=int(row[0]),
                competition_code=str(row[1]),
                competition_name=str(row[2]),
                season_id=int(row[3]),
                season_label=str(row[4]),
                team_id=int(row[5]),
                team_name=str(row[6]),
                opponent_team_id=int(row[7]),
                match_id=int(row[8]),
                kickoff_at=_require_datetime(row[9]),
                is_home=bool(row[10]),
                goals_for=int(row[11]),
                goals_against=int(row[12]),
                stats={
                    "shots_total_for": _optional_float(row[13]),
                    "shots_on_target_for": _optional_float(row[14]),
                    "shots_inside_box_for": _optional_float(row[15]),
                    "corners_for": _optional_float(row[16]),
                    "shots_total_against": _optional_float(row[17]),
                    "shots_on_target_against": _optional_float(row[18]),
                    "shots_inside_box_against": _optional_float(row[19]),
                    "possession_pct": _optional_float(row[20]),
                    "passes_total": _optional_float(row[21]),
                    "passes_accurate": _optional_float(row[22]),
                    "opponent_passes_total": _optional_float(row[23]),
                },
            )
            for row in rows
        ]

    def replace_snapshots(
        self,
        result: TeamAnalyticsResult,
        *,
        scope_key: str,
        season_id: int,
        model_version: str,
    ) -> None:
        self._connection.execute(
            "delete from analytics.team_feature_snapshots "
            "where scope_key = %s and model_version = %s",
            (scope_key, model_version),
        )
        self._connection.execute(
            "delete from analytics.team_score_snapshots "
            "where scope_key = %s and model_version = %s",
            (scope_key, model_version),
        )
        self._connection.execute(
            "delete from analytics.team_elo_history where season_id = %s and model_version = %s",
            (season_id, model_version),
        )

        for feature in result.features:
            self._connection.execute(
                """
                insert into analytics.team_feature_snapshots (
                    team_id, season_id, scope_key, window_key, metric_name,
                    matches, observed_matches, raw_value, adjusted_value,
                    percentile, reference_sample_size, model_version, calculated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    feature.team_id,
                    feature.season_id,
                    feature.scope_key,
                    feature.window,
                    feature.metric_name,
                    feature.matches,
                    feature.observed_matches,
                    feature.raw_value,
                    feature.adjusted_value,
                    feature.percentile,
                    feature.reference_sample_size,
                    feature.model_version,
                    feature.calculated_at,
                ),
            )

        for score in result.scores:
            self._connection.execute(
                """
                insert into analytics.team_score_snapshots (
                    team_id, season_id, scope_key, window_key, matches,
                    overall_score, confidence, dimension_scores,
                    results_process_delta, results_process_signal, diagnostics,
                    reference_sample_size, current_elo, elo_change_last_5,
                    model_version, calculated_at
                )
                values (
                    %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                    %s, %s, %s::jsonb, %s, %s, %s, %s, %s
                )
                """,
                (
                    score.team_id,
                    score.season_id,
                    score.scope_key,
                    score.window,
                    score.matches,
                    score.overall_score,
                    score.confidence,
                    json.dumps(dict(score.dimension_scores), sort_keys=True),
                    score.results_process_delta,
                    score.results_process_signal,
                    json.dumps(dict(score.diagnostics), sort_keys=True),
                    score.reference_sample_size,
                    score.current_elo,
                    score.elo_change_last_5,
                    score.model_version,
                    score.calculated_at,
                ),
            )

        for item in result.elo_history:
            self._connection.execute(
                """
                insert into analytics.team_elo_history (
                    match_id, team_id, opponent_team_id, season_id,
                    pre_match_rating, opponent_pre_match_rating,
                    expected_result, actual_result, post_match_rating,
                    model_version, calculated_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    item.match_id,
                    item.team_id,
                    item.opponent_team_id,
                    item.season_id,
                    item.pre_match_rating,
                    item.opponent_pre_match_rating,
                    item.expected_result,
                    item.actual_result,
                    item.post_match_rating,
                    item.model_version,
                    item.calculated_at,
                ),
            )

    def snapshot_counts(
        self,
        *,
        scope_key: str,
        season_id: int,
        model_version: str,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for key, table, where_column, where_value in (
            ("features", "team_feature_snapshots", "scope_key", scope_key),
            ("scores", "team_score_snapshots", "scope_key", scope_key),
            ("elo", "team_elo_history", "season_id", season_id),
        ):
            row = self._connection.execute(
                f"select count(*) from analytics.{table} "
                f"where {where_column} = %s and model_version = %s",
                (where_value, model_version),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"failed to count {table}")
            counts[key] = int(row[0])
        return counts

    def replace_v2_snapshots(
        self,
        result: TeamAnalyticsResultV2,
        *,
        scope_key: str,
        season_id: int,
        data_context: str = "real",
    ) -> None:
        """Persist Team V2 without altering the established V1/Elo contract."""
        model_version = "team-v2.0"
        self._connection.execute(
            "delete from analytics.team_feature_snapshots "
            "where scope_key = %s and model_version = %s",
            (scope_key, model_version),
        )
        self._connection.execute(
            "delete from analytics.team_score_snapshots "
            "where scope_key = %s and model_version = %s",
            (scope_key, model_version),
        )
        for feature in result.features:
            self._connection.execute(
                """
                insert into analytics.team_feature_snapshots (
                    team_id, season_id, scope_key, window_key, metric_name,
                    matches, observed_matches, raw_value, adjusted_value,
                    percentile, reference_sample_size, model_version, calculated_at,
                    value_basis, metric_kind, metric_unit, formula_version, comparison_group,
                    data_context
                ) values (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    feature.team_id,
                    season_id,
                    scope_key,
                    feature.window,
                    feature.metric_name,
                    feature.matches,
                    feature.observed_matches,
                    feature.raw_value,
                    feature.adjusted_value,
                    feature.percentile,
                    feature.reference_sample_size,
                    model_version,
                    feature.calculated_at,
                    feature.value_basis,
                    feature.metric_kind,
                    feature.metric_unit,
                    feature.formula_version,
                    feature.comparison_group,
                    data_context,
                ),
            )
        for score in result.scores:
            evidence = {
                name: dataclasses.asdict(item) for name, item in score.dimension_evidence.items()
            }
            self._connection.execute(
                """
                insert into analytics.team_score_snapshots (
                    team_id, season_id, scope_key, window_key, matches,
                    overall_score, confidence, dimension_scores,
                    results_process_delta, results_process_signal, diagnostics,
                    reference_sample_size, current_elo, elo_change_last_5,
                    model_version, calculated_at, evidence_coverage_pct,
                    evidence_state, dimension_evidence, profile_version, data_context
                ) values (
                    %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                    null, null, %s::jsonb, %s, null, null,
                    %s, %s, %s, %s, %s::jsonb, %s, %s
                )
                """,
                (
                    score.team_id,
                    season_id,
                    scope_key,
                    score.window,
                    score.matches,
                    score.overall_score,
                    score.confidence,
                    json.dumps(dict(score.dimension_scores), sort_keys=True),
                    json.dumps({"signals": score.diagnostics}, sort_keys=True),
                    score.reference_sample_size,
                    model_version,
                    score.calculated_at,
                    score.evidence_coverage_pct,
                    score.evidence_state,
                    json.dumps(evidence, sort_keys=True),
                    score.profile_version,
                    data_context,
                ),
            )


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _require_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise RuntimeError("expected PostgreSQL timestamptz as datetime")
    return value
