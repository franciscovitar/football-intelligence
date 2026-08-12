"""PostgreSQL persistence for Perception Intelligence evidence."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from football_intelligence.perception.models import (
    EvidenceDraft,
    LinkablePlayer,
    PlayerMention,
    SourceDefinition,
    StoredSource,
)


class PerceptionRepository:
    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def sync_sources(self, definitions: Sequence[SourceDefinition]) -> None:
        for source in definitions:
            self._connection.execute(
                """
                insert into perception.sources (
                    code, display_name, source_kind, homepage_url, feed_url, is_active
                )
                values (%s, %s, %s, %s, %s, %s)
                on conflict (code) do update
                set
                    display_name = excluded.display_name,
                    source_kind = excluded.source_kind,
                    homepage_url = excluded.homepage_url,
                    feed_url = excluded.feed_url,
                    is_active = excluded.is_active,
                    updated_at = now()
                """,
                (
                    source.code,
                    source.display_name,
                    source.source_kind,
                    source.homepage_url,
                    source.feed_url,
                    source.is_active,
                ),
            )

    def active_sources(self) -> tuple[StoredSource, ...]:
        rows = self._connection.execute(
            """
            select id, code, display_name, source_kind, homepage_url, feed_url, is_active
            from perception.sources
            where is_active
            order by code
            """
        ).fetchall()
        return tuple(
            StoredSource(
                id=int(row[0]),
                code=str(row[1]),
                display_name=str(row[2]),
                source_kind=row[3],
                homepage_url=str(row[4]) if row[4] is not None else None,
                feed_url=str(row[5]),
                is_active=bool(row[6]),
            )
            for row in rows
        )

    def linkable_players(self) -> tuple[LinkablePlayer, ...]:
        rows = self._connection.execute(
            """
            select id, display_name
            from football.players
            where is_active
            order by id
            """
        ).fetchall()
        return tuple(
            LinkablePlayer(player_id=int(row[0]), display_name=str(row[1])) for row in rows
        )

    def find_duplicate_root(
        self,
        *,
        content_sha256: str,
        source_id: int,
    ) -> int | None:
        row = self._connection.execute(
            """
            select id
            from perception.evidence_items
            where content_sha256 = %s
              and duplicate_of_id is null
              and source_id <> %s
            order by id
            limit 1
            """,
            (content_sha256, source_id),
        ).fetchone()
        return int(row[0]) if row is not None else None

    def upsert_evidence(
        self,
        *,
        source_id: int,
        evidence: EvidenceDraft,
        duplicate_of_id: int | None,
        ingestion_version: str,
    ) -> int:
        existing_ids = {
            int(row[0])
            for row in self._connection.execute(
                """
                select id
                from perception.evidence_items
                where source_id = %s
                  and (
                    canonical_url = %s
                    or external_id = %s
                  )
                """,
                (
                    source_id,
                    evidence.canonical_url,
                    evidence.external_id,
                ),
            ).fetchall()
        }
        if len(existing_ids) > 1:
            raise RuntimeError("source evidence identifiers resolve to different rows")

        if existing_ids:
            evidence_id = next(iter(existing_ids))
            self._connection.execute(
                """
                update perception.evidence_items
                set
                    external_id = %s,
                    canonical_url = %s,
                    title = %s,
                    excerpt = %s,
                    published_at = %s,
                    content_sha256 = %s,
                    duplicate_of_id = %s,
                    raw_metadata = %s::jsonb,
                    ingestion_version = %s
                where id = %s
                """,
                (
                    evidence.external_id,
                    evidence.canonical_url,
                    evidence.title,
                    evidence.excerpt,
                    evidence.published_at,
                    evidence.content_sha256,
                    duplicate_of_id,
                    json.dumps(evidence.raw_metadata),
                    ingestion_version,
                    evidence_id,
                ),
            )
            return evidence_id

        row = self._connection.execute(
            """
            insert into perception.evidence_items (
                source_id, external_id, canonical_url, title, excerpt,
                published_at, content_sha256, duplicate_of_id,
                raw_metadata, ingestion_version
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            returning id
            """,
            (
                source_id,
                evidence.external_id,
                evidence.canonical_url,
                evidence.title,
                evidence.excerpt,
                evidence.published_at,
                evidence.content_sha256,
                duplicate_of_id,
                json.dumps(evidence.raw_metadata),
                ingestion_version,
            ),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to persist perception evidence")
        return int(row[0])

    def replace_mentions(
        self,
        evidence_id: int,
        mentions: Sequence[PlayerMention],
    ) -> None:
        self._connection.execute(
            "delete from perception.player_evidence_mentions where evidence_id = %s",
            (evidence_id,),
        )
        for mention in mentions:
            self._connection.execute(
                """
                insert into perception.player_evidence_mentions (
                    evidence_id, player_id, matched_text, match_method, context_excerpt
                )
                values (%s, %s, %s, %s, %s)
                """,
                (
                    evidence_id,
                    mention.player_id,
                    mention.matched_text,
                    mention.match_method,
                    mention.context_excerpt,
                ),
            )
