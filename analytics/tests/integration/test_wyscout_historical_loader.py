from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.db.data_mesh_repository import DataMeshRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.jobs.load_wyscout_historical import (
    _prepare_canonical_team_links,
    _scoped_database_counts,
)
from football_intelligence.normalization.models import NormalizedFixtureBatch, TeamRecord


@pytest.mark.integration
def test_wyscout_team_link_reuses_canonical_team_and_preserves_display_fields() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    batch = NormalizedFixtureBatch(
        provider_competition_id="364",
        season_label="2017/18",
        teams=(
            TeamRecord(
                external_id="1611",
                name="Manchester United",
                short_name=None,
                country_code=None,
            ),
        ),
        players=(),
        matches=(),
        team_match_stats=(),
        appearances=(),
        player_match_stats=(),
    )

    with connect(database_url) as connection:
        row = connection.execute(
            """
            insert into football.teams (name, short_name, country_code)
            values ('Man United', 'MU', 'ENG')
            returning id
            """
        ).fetchone()
        assert row is not None
        canonical_team_id = int(row[0])

        prepared, report = _prepare_canonical_team_links(connection, batch)

        assert report.reused_existing_canonical == 1
        assert report.already_linked == 0
        assert report.new_canonical_required == 0
        assert prepared.teams == (
            TeamRecord(
                external_id="1611",
                name="Man United",
                short_name="MU",
                country_code="ENG",
            ),
        )

        mapping = connection.execute(
            """
            select provider_map.team_id
            from football.team_provider_ids as provider_map
            join ingestion.providers as provider on provider.id = provider_map.provider_id
            where provider.code = 'wyscout-open' and provider_map.external_id = '1611'
            """
        ).fetchone()
        assert mapping == (canonical_team_id,)

        prepared_again, rerun_report = _prepare_canonical_team_links(connection, batch)
        assert rerun_report.already_linked == 1
        assert rerun_report.reused_existing_canonical == 0
        assert prepared_again.teams[0].name == "Man United"
        assert prepared_again.teams[0].short_name == "MU"
        assert prepared_again.teams[0].country_code == "ENG"

        connection.rollback()


@pytest.mark.integration
def test_scoped_database_counts_do_not_mix_wyscout_leagues_from_same_season() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    observed_at = datetime(2018, 1, 1, 15, tzinfo=UTC)
    france = NormalizedObservation(
        source_code="wyscout-open",
        source_type="objective_structured",
        entity_type="team",
        entity_source_id="5001:100",
        entity_identity_hints={
            "competition_external_id": "412",
            "season_label": "2017/18",
            "match_external_id": "5001",
            "team_external_id": "100",
        },
        metric_name="goals_for",
        value=1,
        observed_at=observed_at,
        source_timestamp=observed_at,
        source_reference="matches_France.json#5001",
        ingestion_run_id=None,
        semantic_version="wyscout-open-v0.2",
        metric_granularity="team_match",
    )
    germany = NormalizedObservation(
        source_code="wyscout-open",
        source_type="objective_structured",
        entity_type="team",
        entity_source_id="6001:200",
        entity_identity_hints={
            "competition_external_id": "426",
            "season_label": "2017/18",
            "match_external_id": "6001",
            "team_external_id": "200",
        },
        metric_name="goals_for",
        value=2,
        observed_at=observed_at,
        source_timestamp=observed_at,
        source_reference="matches_Germany.json#6001",
        ingestion_run_id=None,
        semantic_version="wyscout-open-v0.2",
        metric_granularity="team_match",
    )

    with connect(database_url) as connection:
        competition_row = connection.execute(
            "select id from football.competitions where code = 'FRA_L1'"
        ).fetchone()
        assert competition_row is not None
        connection.execute(
            """
            insert into football.seasons (competition_id, label, is_current)
            values (%s, '2017/18', false)
            on conflict (competition_id, label) do nothing
            """,
            (int(competition_row[0]),),
        )

        repository = DataMeshRepository(connection)
        assert repository.persist_observations([france, germany]) == 2

        counts = _scoped_database_counts(
            connection,
            competition_code="FRA_L1",
            season_label="2017/18",
            provider_competition_id=412,
        )
        assert counts.source_observations == 1

        connection.rollback()
