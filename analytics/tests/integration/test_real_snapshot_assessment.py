from __future__ import annotations

import os

import pytest

from football_intelligence.db.provider_repository import connect
from football_intelligence.jobs.score_real_snapshot import assess_real_snapshot


@pytest.mark.integration
def test_real_snapshot_without_player_appearances_is_explicitly_insufficient() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        competition = connection.execute(
            "select id from football.competitions where code = 'ENG_PL'"
        ).fetchone()
        assert competition is not None
        connection.execute(
            """
            insert into football.seasons (competition_id, label)
            values (%s, '2025/26')
            on conflict (competition_id, label) do nothing
            """,
            (int(competition[0]),),
        )

        assessment = assess_real_snapshot(connection)
        assert assessment.state == "insufficient_data"
        assert assessment.player_observation_rows == 0
        assert assessment.score_rows_written == 0
        assert assessment.diagnostic_findings_written == 0
        connection.rollback()
