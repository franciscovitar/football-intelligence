from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.db.meta_analytics_repository import MetaAnalyticsRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.meta_analytics.engine import (
    MODEL_VERSION,
    SOURCE_MODEL_VERSION,
    calculate_meta_analytics,
)


@pytest.mark.integration
def test_meta_analytics_pipeline_replaces_snapshots_idempotently() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        player_row = connection.execute(
            "insert into football.players (display_name) values (%s) returning id",
            ("Meta Integration Forward",),
        ).fetchone()
        assert player_row is not None
        player_id = int(player_row[0])

        current_scope = "core:meta-integration-2024"
        history_scope = "core:meta-integration-2023"

        for scope, window, score, confidence in (
            (current_scope, "season", 84, 0.8),
            (current_scope, "last_10", 74, 0.75),
            (current_scope, "last_5", 90, 0.7),
            (current_scope, "last_3", 94, 0.65),
            (history_scope, "season", 62, 0.85),
        ):
            connection.execute(
                """
                insert into analytics.player_score_snapshots (
                    player_id, scope_key, window_key, role, role_confidence,
                    minutes, appearances, overall_score, confidence,
                    dimension_scores, reference_sample_size,
                    model_version, calculated_at
                )
                values (%s, %s, %s, 'forward', 1, 900, 10, %s, %s,
                        '{}'::jsonb, 20, %s, %s)
                """,
                (
                    player_id,
                    scope,
                    window,
                    score,
                    confidence,
                    SOURCE_MODEL_VERSION,
                    datetime(2024, 8, 1, tzinfo=UTC),
                ),
            )

        repository = MetaAnalyticsRepository(connection)
        evidence = repository.load_score_evidence(
            current_scope_key=current_scope,
            history_scope_keys=(history_scope,),
            source_model_version=SOURCE_MODEL_VERSION,
        )
        snapshots = calculate_meta_analytics(
            evidence,
            current_scope_key=current_scope,
            calculated_at=datetime(2024, 8, 1, tzinfo=UTC),
        )
        assert len(snapshots) == 1
        assert snapshots[0].surprise_signal == "surprise"

        repository.replace_snapshots(
            snapshots,
            scope_key=current_scope,
            model_version=MODEL_VERSION,
        )
        first = repository.snapshot_count(
            scope_key=current_scope,
            model_version=MODEL_VERSION,
        )
        repository.replace_snapshots(
            snapshots,
            scope_key=current_scope,
            model_version=MODEL_VERSION,
        )
        second = repository.snapshot_count(
            scope_key=current_scope,
            model_version=MODEL_VERSION,
        )
        assert first == second == 1
        connection.rollback()
