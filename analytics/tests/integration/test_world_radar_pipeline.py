from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.db.provider_repository import connect
from football_intelligence.db.world_radar_repository import WorldRadarRepository
from football_intelligence.world_radar.engine import MODEL_VERSION, calculate_world_radar
from football_intelligence.world_radar.models import PlayerRadarCandidate


@pytest.mark.integration
def test_world_radar_persistence_is_idempotent() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    now = datetime.now(UTC)
    candidates = [
        PlayerRadarCandidate(
            provider_player_id="wr-integration-1",
            player_name="World Radar Integration Forward",
            team_name="Integration FC",
            position="Attacker",
            appearances=12,
            minutes=1000,
            goals=9,
            assists=2,
            shots_total=25,
            shots_on_target=14,
            key_passes=8,
            dribbles_successful=6,
            source_lists=("topscorers", "topassists"),
        ),
        PlayerRadarCandidate(
            provider_player_id="wr-integration-2",
            player_name="World Radar Integration Playmaker",
            team_name="Integration FC",
            position="Midfielder",
            appearances=11,
            minutes=950,
            goals=2,
            assists=8,
            shots_total=10,
            shots_on_target=4,
            key_passes=22,
            dribbles_successful=9,
            source_lists=("topassists",),
        ),
    ]

    snapshots = calculate_world_radar(
        candidates,
        provider_code="api-football",
        competition_code="NED_ED",
        competition_name="Eredivisie",
        country="Netherlands",
        season_label="wr-integration",
        calculated_at=now,
    )
    assert len(snapshots) == 2

    with connect(database_url) as connection:
        repository = WorldRadarRepository(connection)
        repository.replace_snapshots(
            snapshots, season_label="wr-integration", model_version=MODEL_VERSION
        )
        first_count = repository.snapshot_count(
            season_label="wr-integration", model_version=MODEL_VERSION
        )
        assert first_count == 2

        # Re-running the same season/model_version must replace, not duplicate.
        repository.replace_snapshots(
            snapshots, season_label="wr-integration", model_version=MODEL_VERSION
        )
        second_count = repository.snapshot_count(
            season_label="wr-integration", model_version=MODEL_VERSION
        )
        assert second_count == 2

        row = connection.execute(
            """
            select player_name, radar_score, confidence
            from analytics.world_radar_snapshots
            where season_label = %s
              and model_version = %s
              and provider_player_id = %s
            """,
            ("wr-integration", MODEL_VERSION, "wr-integration-1"),
        ).fetchone()
        assert row is not None
        assert str(row[0]) == "World Radar Integration Forward"

        connection.rollback()
