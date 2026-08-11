from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from football_intelligence.data_quality.coverage import build_normalized_coverage
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.ingestion.raw_store import LocalRawStore
from football_intelligence.normalization.api_football import normalize_fixture_bundle


@pytest.mark.integration
def test_provider_batch_is_idempotent_and_traceable(tmp_path) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    payload = json.loads(
        (Path(__file__).parents[1] / "fixtures" / "api_football_fixture_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    batch = normalize_fixture_bundle(payload)
    coverage = build_normalized_coverage(
        team_stats=batch.team_match_stats,
        player_stats=batch.player_match_stats,
    )
    raw = LocalRawStore(tmp_path).put(
        endpoint="fixtures",
        parameters={"ids": "1001"},
        payload=payload,
    )

    with connect(database_url) as connection:
        repo = ProviderRepository(connection, provider_code="api-football")
        run_id = repo.start_run(
            job_name="integration-test",
            trigger_kind="test",
            scope={"fixture": 1001},
        )
        repo.record_raw_objects(run_id, [raw])
        repo.persist_batch(competition_code="ENG_PL", batch=batch)
        repo.upsert_capabilities(coverage)
        first_counts = repo.snapshot_counts()

        repo.persist_batch(competition_code="ENG_PL", batch=batch)
        second_counts = repo.snapshot_counts()

        repo.finish_run(
            run_id,
            status="succeeded",
            request_count=1,
            rows_written=1,
            metadata={"idempotency_verified": first_counts == second_counts},
        )
        connection.commit()

        assert first_counts == second_counts
        assert second_counts["teams"] == 2
        assert second_counts["players"] == 2
        assert second_counts["matches"] == 1

        raw_count = connection.execute(
            "select count(*) from ingestion.raw_objects where ingestion_run_id = %s",
            (run_id,),
        ).fetchone()
        assert raw_count is not None
        assert raw_count[0] == 1

        unavailable = connection.execute(
            """
            select availability, sample_size, non_null_count
            from ingestion.data_capabilities
            where entity_type = 'player_match_stats'
              and metric_name = 'passes_accurate'
            """
        ).fetchone()
        assert unavailable == ("unavailable", 2, 0)
