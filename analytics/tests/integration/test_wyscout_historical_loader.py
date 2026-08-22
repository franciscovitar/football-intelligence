from __future__ import annotations

import os

import pytest

from football_intelligence.db.provider_repository import connect
from football_intelligence.jobs.load_wyscout_historical import _prepare_canonical_team_links
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
