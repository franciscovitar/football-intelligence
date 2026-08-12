from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from football_intelligence.db.provider_repository import connect
from football_intelligence.db.team_analytics_repository import TeamAnalyticsRepository
from football_intelligence.team_analytics.engine import (
    MODEL_VERSION,
    calculate_team_analytics,
)


@pytest.mark.integration
def test_team_analytics_pipeline_calculates_and_replaces_snapshots() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        competition_row = connection.execute(
            "select id from football.competitions where code = 'ENG_PL'"
        ).fetchone()
        assert competition_row is not None
        competition_id = int(competition_row[0])
        season_row = connection.execute(
            """
            insert into football.seasons (competition_id, label)
            values (%s, %s)
            on conflict (competition_id, label) do update set updated_at = now()
            returning id
            """,
            (competition_id, "team-analytics-integration"),
        ).fetchone()
        assert season_row is not None
        season_id = int(season_row[0])

        team_ids: list[int] = []
        for name in ("Strong Process Team", "Weak Process Team"):
            row = connection.execute(
                "insert into football.teams (name) values (%s) returning id",
                (name,),
            ).fetchone()
            assert row is not None
            team_ids.append(int(row[0]))

        for index in range(6):
            kickoff = datetime(2024, 4, 1, tzinfo=UTC) + timedelta(days=index * 7)
            match_row = connection.execute(
                """
                insert into football.matches (
                    season_id, home_team_id, away_team_id, kickoff_at,
                    status, home_score, away_score
                )
                values (%s, %s, %s, %s, 'finished', 2, 0)
                returning id
                """,
                (season_id, team_ids[0], team_ids[1], kickoff),
            ).fetchone()
            assert match_row is not None
            match_id = int(match_row[0])
            connection.execute(
                """
                insert into football.team_match_stats (
                    match_id, team_id, possession_pct, shots_total,
                    shots_on_target, shots_inside_box, corners,
                    passes_total, passes_accurate
                )
                values
                    (%s, %s, 64, 18, 8, 12, 8, 640, 576),
                    (%s, %s, 36, 5, 1, 2, 2, 300, 210)
                """,
                (match_id, team_ids[0], match_id, team_ids[1]),
            )

        repository = TeamAnalyticsRepository(connection)
        observations = repository.load_observations(
            season_label="team-analytics-integration",
            competition_codes=("ENG_PL",),
        )
        assert len(observations) == 12
        scope_key = "competition:ENG_PL:team-analytics-integration"
        result = calculate_team_analytics(
            observations,
            scope_key=scope_key,
            competition_id=competition_id,
            season_id=season_id,
            calculated_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        season_scores = {
            score.team_name: score for score in result.scores if score.window == "season"
        }
        assert (
            season_scores["Strong Process Team"].dimension_scores["process"]
            > season_scores["Weak Process Team"].dimension_scores["process"]
        )

        repository.replace_snapshots(
            result,
            scope_key=scope_key,
            season_id=season_id,
            model_version=MODEL_VERSION,
        )
        first = repository.snapshot_counts(
            scope_key=scope_key,
            season_id=season_id,
            model_version=MODEL_VERSION,
        )
        repository.replace_snapshots(
            result,
            scope_key=scope_key,
            season_id=season_id,
            model_version=MODEL_VERSION,
        )
        second = repository.snapshot_counts(
            scope_key=scope_key,
            season_id=season_id,
            model_version=MODEL_VERSION,
        )
        assert first == second
        assert first["features"] == len(result.features)
        assert first["scores"] == len(result.scores)
        assert first["elo"] == 12
        connection.rollback()
