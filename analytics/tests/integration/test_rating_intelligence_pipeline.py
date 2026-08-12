from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest

from football_intelligence.db.provider_repository import connect
from football_intelligence.db.rating_intelligence_repository import (
    RatingIntelligenceRepository,
)
from football_intelligence.rating_intelligence.engine import (
    MODEL_VERSION,
    PERCEPTION_MODEL_VERSION,
    PERFORMANCE_MODEL_VERSION,
    calculate_rating_intelligence,
)


@pytest.mark.integration
def test_rating_pipeline_persists_underrated_snapshot() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    now = datetime.now(UTC)

    with connect(database_url) as connection:
        player_row = connection.execute(
            "insert into football.players (display_name) values (%s) returning id",
            ("Rating Integration Forward",),
        ).fetchone()
        assert player_row is not None
        player_id = int(player_row[0])

        connection.execute(
            """
            insert into analytics.player_meta_snapshots (
                player_id, scope_key, role,
                performance_score, performance_confidence,
                form_score, form_confidence,
                stable_score, stable_confidence,
                expectation_score, expectation_confidence,
                surprise_delta, surprise_signal,
                trend_delta, trend_confidence, trend_signal,
                watchlist_score, watchlist_signal,
                history_seasons, baseline_evidence, trend_evidence,
                source_model_version, model_version, calculated_at
            )
            values (
                %s, 'core:rating-integration', 'forward',
                86, 0.90,
                88, 0.84,
                84, 0.88,
                78, 0.80,
                8, 'aligned',
                4, 0.76, 'stable',
                72, 'monitor',
                1, '[]'::jsonb, '{}'::jsonb,
                'player-v1.0', %s, %s
            )
            """,
            (player_id, PERFORMANCE_MODEL_VERSION, now),
        )

        source_ids: list[int] = []
        for index in (1, 2):
            row = connection.execute(
                """
                insert into perception.sources (
                    code, display_name, source_kind, homepage_url, feed_url
                )
                values (%s, %s, 'media', %s, %s)
                returning id
                """,
                (
                    f"rating-integration-{index}",
                    f"Rating Integration {index}",
                    f"https://example{index}.com",
                    f"https://example{index}.com/feed.xml",
                ),
            ).fetchone()
            assert row is not None
            source_ids.append(int(row[0]))

        titles = (
            "Rating Integration Forward struggles in poor display",
            "Rating Integration Forward criticised after costly error",
            "Rating Integration Forward under fire after blunder",
            "Disappointing run continues for Rating Integration Forward",
        )
        for index, title in enumerate(titles):
            source_id = source_ids[0] if index < 2 else source_ids[1]
            row = connection.execute(
                """
                insert into perception.evidence_items (
                    source_id, external_id, canonical_url, title, excerpt,
                    published_at, content_sha256, raw_metadata, ingestion_version
                )
                values (%s, %s, %s, %s, null, %s, %s, '{}'::jsonb, %s)
                returning id
                """,
                (
                    source_id,
                    f"rating-{index}",
                    f"https://example.com/rating-{index}",
                    title,
                    now,
                    f"{index + 1:064x}",
                    PERCEPTION_MODEL_VERSION,
                ),
            ).fetchone()
            assert row is not None
            evidence_id = int(row[0])
            connection.execute(
                """
                insert into perception.player_evidence_mentions (
                    evidence_id, player_id, matched_text, match_method, context_excerpt
                )
                values (%s, %s, %s, 'display_name_exact', %s)
                """,
                (
                    evidence_id,
                    player_id,
                    "Rating Integration Forward",
                    title,
                ),
            )

        repository = RatingIntelligenceRepository(connection)
        performance = repository.load_performance(
            scope_key="core:rating-integration",
            model_version=PERFORMANCE_MODEL_VERSION,
        )
        evidence = repository.load_evidence(
            player_ids=[player_id],
            cutoff=now - timedelta(days=180),
            ingestion_version=PERCEPTION_MODEL_VERSION,
        )
        snapshots = calculate_rating_intelligence(
            performance,
            evidence,
            calculated_at=now,
        )
        repository.replace_snapshots(
            snapshots,
            scope_key="core:rating-integration",
            model_version=MODEL_VERSION,
        )

        row = connection.execute(
            """
            select rating_signal, rating_gap, scored_source_count
            from analytics.player_rating_snapshots
            where player_id = %s
              and scope_key = 'core:rating-integration'
              and model_version = %s
            """,
            (player_id, MODEL_VERSION),
        ).fetchone()
        assert row is not None
        assert str(row[0]) == "underrated"
        assert float(row[1]) > 50
        assert int(row[2]) == 2

        connection.rollback()
