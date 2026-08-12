from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.db.tactical_intelligence_repository import (
    TacticalIntelligenceRepository,
)
from football_intelligence.normalization.models import (
    MatchRecord,
    NormalizedFixtureBatch,
    TeamLineupRecord,
    TeamRecord,
)
from football_intelligence.tactical_intelligence.engine import (
    MODEL_VERSION,
    SOURCE_MODEL_VERSION,
    calculate_tactical_intelligence,
)


@pytest.mark.integration
def test_lineup_persistence_and_tactical_pipeline() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    now = datetime.now(UTC)
    batch = NormalizedFixtureBatch(
        provider_competition_id="39",
        season_label="tactical-integration",
        teams=(
            TeamRecord("tactical-home", "Tactical Home", None, None),
            TeamRecord("tactical-away", "Tactical Away", None, None),
        ),
        players=(),
        matches=(
            MatchRecord(
                external_id="tactical-match",
                kickoff_at=now,
                status="finished",
                round_name="Integration",
                venue_name=None,
                home_team_external_id="tactical-home",
                away_team_external_id="tactical-away",
                home_score=2,
                away_score=0,
            ),
        ),
        team_match_stats=(),
        appearances=(),
        player_match_stats=(),
        team_lineups=(
            TeamLineupRecord(
                match_external_id="tactical-match",
                team_external_id="tactical-home",
                formation="4-3-3",
                coach_name="Integration Coach",
            ),
            TeamLineupRecord(
                match_external_id="tactical-match",
                team_external_id="tactical-away",
                formation="4-4-2",
                coach_name=None,
            ),
        ),
    )

    with connect(database_url) as connection:
        provider = ProviderRepository(connection, provider_code="api-football")
        provider.persist_batch(competition_code="ENG_PL", batch=batch)

        team_row = connection.execute(
            """
            select mapping.team_id
            from football.team_provider_ids as mapping
            join ingestion.providers as provider on provider.id = mapping.provider_id
            where provider.code = 'api-football'
              and mapping.external_id = 'tactical-home'
            """
        ).fetchone()
        assert team_row is not None
        team_id = int(team_row[0])

        season_row = connection.execute(
            """
            select s.id
            from football.seasons as s
            join football.competitions as c on c.id = s.competition_id
            where c.code = 'ENG_PL'
              and s.label = 'tactical-integration'
            """
        ).fetchone()
        assert season_row is not None
        season_id = int(season_row[0])

        connection.execute(
            """
            insert into analytics.team_score_snapshots (
                team_id, season_id, scope_key, window_key, matches,
                overall_score, confidence, dimension_scores,
                results_process_delta, results_process_signal, diagnostics,
                reference_sample_size, current_elo, elo_change_last_5,
                model_version, calculated_at
            )
            values (
                %s, %s, 'competition:ENG_PL:tactical-integration',
                'season', 4,
                81, 0.84,
                '{"control":80,"chance_generation":78,"defense":72}'::jsonb,
                0, 'results_aligned', '{}'::jsonb,
                20, 1510, 4,
                %s, %s
            )
            """,
            (team_id, season_id, SOURCE_MODEL_VERSION, now),
        )

        repository = TacticalIntelligenceRepository(connection)
        inputs = repository.load_inputs(
            season_label="tactical-integration",
            source_model_version=SOURCE_MODEL_VERSION,
        )
        target = [item for item in inputs if item.team_id == team_id]
        assert len(target) == 1
        assert target[0].formations[0].formation == "4-3-3"

        snapshots = calculate_tactical_intelligence(target, calculated_at=now)
        repository.replace_scope(
            snapshots,
            scope_key="competition:ENG_PL:tactical-integration",
            model_version=MODEL_VERSION,
        )

        persisted = connection.execute(
            """
            select primary_formation, style_signal, defensive_signal
            from analytics.team_tactical_snapshots
            where team_id = %s
              and scope_key = 'competition:ENG_PL:tactical-integration'
              and model_version = %s
            """,
            (team_id, MODEL_VERSION),
        ).fetchone()
        assert persisted is not None
        assert str(persisted[0]) == "4-3-3"
        assert str(persisted[1]) == "control_and_volume"
        assert str(persisted[2]) == "restrictive_shot_profile"

        connection.rollback()
