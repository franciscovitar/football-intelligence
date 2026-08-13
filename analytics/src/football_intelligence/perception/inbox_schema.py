"""Perception Inbox contract: pure DTO + validation for the external Google
Sheet "Football Intelligence — Perception Inbox" (tabs: Inbox, Source
Registry, Runs), populated by an externally configured ChatGPT daily task.

This module is intentionally inert: it defines what a valid row looks like
and validates one, nothing more. It does NOT read Google Sheets, does NOT
hold a spreadsheet URL/ID, and does NOT use any Google credentials. Actual
Sheet -> Supabase ingestion/authentication is a later block.

`InboxSourceType` is a deliberately separate, qualitative-only vocabulary --
it shares no values with `data_mesh.models.SourceType`'s `objective_*`
members, so a row parsed here can never be mistaken for an objective
observation by the reconciliation engine. Nothing in this module writes to
`ingestion.source_observations` or participates in reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football_intelligence.data_mesh.timeparse import parse_utc_timestamp

InboxSourceType = Literal["expert", "media", "fan", "other"]
InboxEntityType = Literal["player", "team", "competition", "match"]

_SOURCE_TYPES: frozenset[str] = frozenset({"expert", "media", "fan", "other"})
_ENTITY_TYPES: frozenset[str] = frozenset({"player", "team", "competition", "match"})

REQUIRED_COLUMNS: tuple[str, ...] = (
    "evidence_id",
    "collected_at",
    "entity_type",
    "entity_name",
    "source_type",
    "source_name",
    "claim_type",
    "claim",
)

# The full documented column contract, in Sheet order.
INBOX_COLUMNS: tuple[str, ...] = (
    "evidence_id",
    "collected_at",
    "published_at",
    "competition_code",
    "entity_type",
    "entity_name",
    "entity_hint",
    "source_type",
    "source_name",
    "author",
    "source_url",
    "claim_type",
    "claim",
    "topic",
    "sentiment",
    "stance",
    "credibility_score",
    "confidence",
    "consensus_key",
    "language",
    "country",
    "processed",
    "processed_at",
    "notes",
)


@dataclass(frozen=True, slots=True)
class PerceptionInboxRow:
    evidence_id: str
    collected_at: datetime
    published_at: datetime | None
    competition_code: str | None
    entity_type: InboxEntityType
    entity_name: str
    entity_hint: str | None
    source_type: InboxSourceType
    source_name: str
    author: str | None
    source_url: str | None
    claim_type: str
    claim: str
    topic: str | None
    sentiment: str | None
    stance: str | None
    credibility_score: float | None
    confidence: float | None
    consensus_key: str | None
    language: str | None
    country: str | None
    processed: bool
    processed_at: datetime | None
    notes: str | None


class InboxRowError(ValueError):
    """A Sheet row does not satisfy the Perception Inbox contract."""


def parse_inbox_row(raw: dict[str, str]) -> PerceptionInboxRow:
    """Parse and validate one Inbox row. Raises `InboxRowError` when invalid.

    Purely defensive: this never mutates objective data, never touches the
    data mesh, and only ever produces a qualitative-typed DTO.
    """

    missing = [column for column in REQUIRED_COLUMNS if not (raw.get(column) or "").strip()]
    if missing:
        raise InboxRowError(f"missing required column(s): {', '.join(missing)}")

    entity_type = raw["entity_type"].strip().lower()
    if entity_type not in _ENTITY_TYPES:
        raise InboxRowError(f"unsupported entity_type: {entity_type!r}")

    source_type = raw["source_type"].strip().lower()
    if source_type not in _SOURCE_TYPES:
        raise InboxRowError(f"unsupported source_type: {source_type!r}")

    collected_at = parse_utc_timestamp(raw["collected_at"])
    if collected_at is None:
        raise InboxRowError(f"invalid collected_at: {raw['collected_at']!r}")

    return PerceptionInboxRow(
        evidence_id=raw["evidence_id"].strip(),
        collected_at=collected_at,
        published_at=parse_utc_timestamp(raw.get("published_at")),
        competition_code=_optional_text(raw.get("competition_code")),
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_name=raw["entity_name"].strip(),
        entity_hint=_optional_text(raw.get("entity_hint")),
        source_type=source_type,  # type: ignore[arg-type]
        source_name=raw["source_name"].strip(),
        author=_optional_text(raw.get("author")),
        source_url=_optional_text(raw.get("source_url")),
        claim_type=raw["claim_type"].strip(),
        claim=raw["claim"].strip(),
        topic=_optional_text(raw.get("topic")),
        sentiment=_optional_text(raw.get("sentiment")),
        stance=_optional_text(raw.get("stance")),
        credibility_score=_optional_unit_float(raw.get("credibility_score")),
        confidence=_optional_unit_float(raw.get("confidence")),
        consensus_key=_optional_text(raw.get("consensus_key")),
        language=_optional_text(raw.get("language")),
        country=_optional_text(raw.get("country")),
        processed=_parse_bool(raw.get("processed")),
        processed_at=parse_utc_timestamp(raw.get("processed_at")),
        notes=_optional_text(raw.get("notes")),
    )


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _optional_unit_float(value: str | None) -> float | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        parsed = float(text)
    except ValueError:
        raise InboxRowError(f"invalid numeric value: {value!r}") from None
    if not (0.0 <= parsed <= 1.0):
        raise InboxRowError(f"value must be between 0 and 1: {parsed!r}")
    return parsed


def _parse_bool(value: str | None) -> bool:
    text = (value or "").strip().lower()
    return text in {"true", "1", "yes", "y"}
