from __future__ import annotations

import os

import pytest

from football_intelligence.data_mesh.entity_resolution import COMPETITION_MAPPINGS
from football_intelligence.db.provider_repository import connect
from football_intelligence.jobs import load_real_snapshot


@pytest.mark.integration
def test_loading_the_real_snapshot_twice_yields_identical_canonical_counts() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        connection.autocommit = False
        try:
            season_id = load_real_snapshot._ensure_season(connection)
            matches_path = load_real_snapshot.DEFAULT_INPUT_DIR / "eng_pl_matches.json"
            if not matches_path.exists():
                pytest.skip("committed real snapshot file not present")

            first_count = load_real_snapshot._load_matches(
                connection, matches_path=matches_path, season_id=season_id
            )
            match_count_after_first = connection.execute(
                "select count(*) from football.matches where season_id = %s", (season_id,)
            ).fetchone()[0]

            second_count = load_real_snapshot._load_matches(
                connection, matches_path=matches_path, season_id=season_id
            )
            match_count_after_second = connection.execute(
                "select count(*) from football.matches where season_id = %s", (season_id,)
            ).fetchone()[0]

            assert first_count == second_count
            assert match_count_after_first == match_count_after_second
        finally:
            connection.rollback()


@pytest.mark.integration
def test_openfootball_competition_mapping_matches_a_seeded_provider() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    mapping = next(
        m
        for m in COMPETITION_MAPPINGS
        if m.source_code == "openfootball" and m.canonical_code == "ENG_PL"
    )
    with connect(database_url) as connection:
        row = connection.execute(
            "select id from ingestion.providers where code = %s", (mapping.source_code,)
        ).fetchone()
        connection.rollback()
    assert row is not None, "openfootball must be seeded in ingestion.providers"
