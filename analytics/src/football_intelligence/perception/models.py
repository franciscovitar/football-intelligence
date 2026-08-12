"""Domain values for Perception Intelligence V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

SourceKind = Literal["expert", "media", "fan", "other"]
MatchMethod = Literal["display_name_exact", "manual"]


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    code: str
    display_name: str
    source_kind: SourceKind
    homepage_url: str | None
    feed_url: str
    is_active: bool = True


@dataclass(frozen=True, slots=True)
class StoredSource:
    id: int
    code: str
    display_name: str
    source_kind: SourceKind
    homepage_url: str | None
    feed_url: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class FeedItem:
    external_id: str | None
    url: str
    title: str
    excerpt: str | None
    published_at: datetime | None
    raw_metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class EvidenceDraft:
    external_id: str | None
    canonical_url: str
    title: str
    excerpt: str | None
    published_at: datetime | None
    content_sha256: str
    raw_metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LinkablePlayer:
    player_id: int
    display_name: str


@dataclass(frozen=True, slots=True)
class PlayerMention:
    player_id: int
    matched_text: str
    match_method: MatchMethod
    context_excerpt: str | None
