from __future__ import annotations

import dataclasses
import os
from datetime import UTC, datetime, timedelta

import pytest

from football_intelligence.db.player_analytics_repository import PlayerAnalyticsRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.player_analytics.engine import (
    MODEL_VERSION,
    calculate_player_analytics,
)
from football_intelligence.player_analytics.engine_v2 import (
    MODEL_VERSION as V2_MODEL_VERSION,
)
from football_intelligence.player_analytics.engine_v2 import (
    calculate_player_analytics_v2,
)


@pytest.mark.integration
def test_player_analytics_pipeline_ranks_and_replaces_snapshots() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    scope_key = "integration:player-analytics"
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
            on conflict (competition_id, label) do update
            set updated_at = now()
            returning id
            """,
            (competition_id, "analytics-integration"),
        ).fetchone()
        assert season_row is not None
        season_id = int(season_row[0])

        team_ids = []
        for name in ("Analytics Home", "Analytics Away"):
            row = connection.execute(
                "insert into football.teams (name) values (%s) returning id",
                (name,),
            ).fetchone()
            assert row is not None
            team_ids.append(int(row[0]))

        player_specs = (
            ("Strong Forward", "F"),
            ("Weak Forward", "F"),
            ("Strong Defender", "D"),
            ("Weak Defender", "D"),
        )
        player_ids: list[int] = []
        for name, _ in player_specs:
            row = connection.execute(
                "insert into football.players (display_name) values (%s) returning id",
                (name,),
            ).fetchone()
            assert row is not None
            player_ids.append(int(row[0]))

        for index in range(3):
            kickoff = datetime(2024, 5, 1, tzinfo=UTC) + timedelta(days=index * 7)
            match_row = connection.execute(
                """
                insert into football.matches (
                    season_id,
                    home_team_id,
                    away_team_id,
                    kickoff_at,
                    status,
                    home_score,
                    away_score
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
                    match_id,
                    team_id,
                    possession_pct
                )
                values (%s, %s, 60), (%s, %s, 40)
                """,
                (match_id, team_ids[0], match_id, team_ids[1]),
            )

            for player_index, (_, position) in enumerate(player_specs):
                player_id = player_ids[player_index]
                connection.execute(
                    """
                    insert into football.player_appearances (
                        match_id,
                        player_id,
                        team_id,
                        minutes,
                        started,
                        listed_position
                    )
                    values (%s, %s, %s, 90, true, %s)
                    """,
                    (match_id, player_id, team_ids[0], position),
                )

                if player_index == 0:
                    stats = (1, 1, 5, 3, 2, 1, 0, 0, 1, 4, 1, 1, 0)
                elif player_index == 1:
                    stats = (0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 1, 0)
                elif player_index == 2:
                    stats = (0, 0, 0, 0, 0, 5, 2, 4, 0, 7, 1, 1, 0)
                else:
                    stats = (0, 0, 0, 0, 0, 1, 0, 1, 0, 3, 0, 3, 0)

                connection.execute(
                    """
                    insert into football.player_match_stats (
                        match_id,
                        player_id,
                        goals,
                        assists,
                        shots_total,
                        shots_on_target,
                        key_passes,
                        tackles,
                        blocks,
                        interceptions,
                        dribbles_successful,
                        duels_won,
                        fouls_drawn,
                        fouls_committed,
                        saves
                    )
                    values (
                        %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    (match_id, player_id, *stats),
                )

        repository = PlayerAnalyticsRepository(connection)
        observations = repository.load_observations(
            season_label="analytics-integration",
            competition_codes=("ENG_PL",),
        )
        assert len(observations) == 12

        result = calculate_player_analytics(
            observations,
            scope_key=scope_key,
            calculated_at=datetime(2024, 6, 1, tzinfo=UTC),
        )

        season_scores = {
            score.player_name: score for score in result.scores if score.window == "season"
        }
        assert (
            season_scores["Strong Forward"].overall_score
            > season_scores["Weak Forward"].overall_score
        )
        assert (
            season_scores["Strong Defender"].overall_score
            > season_scores["Weak Defender"].overall_score
        )

        repository.replace_snapshots(
            result,
            scope_key=scope_key,
            model_version=MODEL_VERSION,
        )
        first_counts = repository.snapshot_counts(
            scope_key=scope_key,
            model_version=MODEL_VERSION,
        )
        repository.replace_snapshots(
            result,
            scope_key=scope_key,
            model_version=MODEL_VERSION,
        )
        second_counts = repository.snapshot_counts(
            scope_key=scope_key,
            model_version=MODEL_VERSION,
        )

        assert first_counts == second_counts
        assert first_counts["scores"] == len(result.scores)
        assert first_counts["features"] == len(result.features)

        fine_observations = [
            dataclasses.replace(
                observation,
                listed_position="ST" if observation.listed_position == "F" else "CB",
            )
            for observation in observations
        ]
        v2_scores = calculate_player_analytics_v2(
            fine_observations,
            scope_key=scope_key,
            calculated_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        repository.replace_snapshots(
            result,
            scope_key=scope_key,
            model_version=V2_MODEL_VERSION,
            v2_scores=v2_scores,
            data_context="real",
        )
        ready_count = connection.execute(
            """
            select count(*)
            from analytics.product_player_score_snapshots
            where scope_key = %s and model_version = %s
            """,
            (scope_key, V2_MODEL_VERSION),
        ).fetchone()
        assert ready_count is not None
        assert int(ready_count[0]) == sum(score.evidence_state == "ready" for score in v2_scores)

        connection.rollback()
