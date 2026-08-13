from __future__ import annotations

import pytest

from football_intelligence.data_mesh.models import OBJECTIVE_SOURCE_TYPES
from football_intelligence.perception.inbox_schema import (
    InboxRowError,
    InboxSourceType,
    parse_inbox_row,
)

_VALID_ROW: dict[str, str] = {
    "evidence_id": "abc123",
    "collected_at": "2026-08-13T10:00:00Z",
    "published_at": "2026-08-12T09:00:00Z",
    "competition_code": "ENG_PL",
    "entity_type": "player",
    "entity_name": "Sample Player",
    "entity_hint": "forward, Sample FC",
    "source_type": "media",
    "source_name": "Sample Outlet",
    "author": "J. Reporter",
    "source_url": "https://example.com/article",
    "claim_type": "performance_opinion",
    "claim": "Had an excellent game.",
    "topic": "form",
    "sentiment": "positive",
    "stance": "support",
    "credibility_score": "0.8",
    "confidence": "0.7",
    "consensus_key": "sample-player-form",
    "language": "en",
    "country": "GB",
    "processed": "false",
    "processed_at": "",
    "notes": "",
}


def test_parse_valid_row() -> None:
    row = parse_inbox_row(_VALID_ROW)
    assert row.evidence_id == "abc123"
    assert row.entity_type == "player"
    assert row.source_type == "media"
    assert row.credibility_score == 0.8
    assert row.processed is False


def test_missing_required_column_raises() -> None:
    incomplete = dict(_VALID_ROW)
    del incomplete["claim"]
    with pytest.raises(InboxRowError, match="claim"):
        parse_inbox_row(incomplete)


def test_unsupported_entity_type_raises() -> None:
    bad = dict(_VALID_ROW)
    bad["entity_type"] = "referee"
    with pytest.raises(InboxRowError, match="entity_type"):
        parse_inbox_row(bad)


def test_unsupported_source_type_raises() -> None:
    bad = dict(_VALID_ROW)
    bad["source_type"] = "objective_structured"
    with pytest.raises(InboxRowError, match="source_type"):
        parse_inbox_row(bad)


def test_invalid_collected_at_raises() -> None:
    bad = dict(_VALID_ROW)
    bad["collected_at"] = "not-a-timestamp"
    with pytest.raises(InboxRowError, match="collected_at"):
        parse_inbox_row(bad)


def test_credibility_score_out_of_range_raises() -> None:
    bad = dict(_VALID_ROW)
    bad["credibility_score"] = "1.5"
    with pytest.raises(InboxRowError):
        parse_inbox_row(bad)


def test_optional_columns_may_be_blank() -> None:
    minimal = {key: _VALID_ROW[key] for key in _VALID_ROW}
    minimal["published_at"] = ""
    minimal["credibility_score"] = ""
    minimal["confidence"] = ""
    row = parse_inbox_row(minimal)
    assert row.published_at is None
    assert row.credibility_score is None
    assert row.confidence is None


def test_inbox_source_types_never_overlap_objective_source_types() -> None:
    # Structural guarantee: a qualitative inbox row can never be mistaken
    # for an objective observation by the reconciliation engine, because
    # the two source-type vocabularies share no values.
    inbox_types = set(InboxSourceType.__args__)  # type: ignore[attr-defined]
    assert inbox_types.isdisjoint(OBJECTIVE_SOURCE_TYPES)


def test_parsed_row_is_never_a_normalized_observation() -> None:
    from football_intelligence.data_mesh.models import NormalizedObservation

    row = parse_inbox_row(_VALID_ROW)
    assert not isinstance(row, NormalizedObservation)
