from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.db.perception_repository import PerceptionRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.perception.engine import (
    MODEL_VERSION,
    build_evidence,
    link_players,
)
from football_intelligence.perception.models import FeedItem, SourceDefinition


@pytest.mark.integration
def test_perception_pipeline_is_idempotent_and_deduplicates_cross_source() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        player_row = connection.execute(
            "insert into football.players (display_name) values (%s) returning id",
            ("Perception Integration Forward",),
        ).fetchone()
        assert player_row is not None
        player_id = int(player_row[0])

        repository = PerceptionRepository(connection)
        repository.sync_sources(
            (
                SourceDefinition(
                    code="integration-media-a",
                    display_name="Integration Media A",
                    source_kind="media",
                    homepage_url="https://example.com/a",
                    feed_url="https://example.com/a/feed",
                ),
                SourceDefinition(
                    code="integration-media-b",
                    display_name="Integration Media B",
                    source_kind="media",
                    homepage_url="https://example.com/b",
                    feed_url="https://example.com/b/feed",
                ),
            )
        )
        sources = {source.code: source for source in repository.active_sources()}
        players = repository.linkable_players()

        item_a = FeedItem(
            external_id="a-1",
            url="https://example.com/a/story?utm_source=test",
            title="Perception Integration Forward earns praise",
            excerpt="Perception Integration Forward controlled the match.",
            published_at=datetime(2026, 8, 12, tzinfo=UTC),
            raw_metadata={"fixture": "a"},
        )
        evidence_a = build_evidence(item_a)
        evidence_a_id = repository.upsert_evidence(
            source_id=sources["integration-media-a"].id,
            evidence=evidence_a,
            duplicate_of_id=None,
            ingestion_version=MODEL_VERSION,
        )
        repository.replace_mentions(evidence_a_id, link_players(evidence_a, players))

        same_id = repository.upsert_evidence(
            source_id=sources["integration-media-a"].id,
            evidence=evidence_a,
            duplicate_of_id=None,
            ingestion_version=MODEL_VERSION,
        )
        assert same_id == evidence_a_id

        item_b = FeedItem(
            external_id="b-1",
            url="https://example.com/b/story",
            title=item_a.title,
            excerpt=item_a.excerpt,
            published_at=item_a.published_at,
            raw_metadata={"fixture": "b"},
        )
        evidence_b = build_evidence(item_b)
        duplicate_root = repository.find_duplicate_root(
            content_sha256=evidence_b.content_sha256,
            source_id=sources["integration-media-b"].id,
        )
        assert duplicate_root == evidence_a_id

        evidence_b_id = repository.upsert_evidence(
            source_id=sources["integration-media-b"].id,
            evidence=evidence_b,
            duplicate_of_id=duplicate_root,
            ingestion_version=MODEL_VERSION,
        )
        repository.replace_mentions(evidence_b_id, link_players(evidence_b, players))

        row = connection.execute(
            """
            select e.duplicate_of_id, count(m.player_id)
            from perception.evidence_items as e
            left join perception.player_evidence_mentions as m
              on m.evidence_id = e.id
            where e.id = %s
            group by e.duplicate_of_id
            """,
            (evidence_b_id,),
        ).fetchone()
        assert row is not None
        assert int(row[0]) == evidence_a_id
        assert int(row[1]) == 1

        linked = connection.execute(
            """
            select count(*)
            from perception.player_evidence_mentions
            where player_id = %s
            """,
            (player_id,),
        ).fetchone()
        assert linked is not None
        assert int(linked[0]) == 2
        connection.rollback()
