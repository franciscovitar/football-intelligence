from __future__ import annotations

import pytest

from football_intelligence.providers.wikipedia_historical_squads import (
    WikipediaHistoricalSquadError,
    leading_player_article_title,
    parse_historical_active_squad_revision,
    wikidata_item_is_explicit_human,
)


def _player(name_value: str, number: int = 1) -> str:
    return f"{{{{fs player\n| no = {number}\n| name = {name_value}\n| pos = DF\n}}}}\n"


def _snapshot(wikitext: str):
    return parse_historical_active_squad_revision(
        wikitext,
        article_title="Example Club",
        revision_id=123456,
        revision_timestamp="2024-09-01T12:00:00Z",
        snapshot_target="2024-09-06T23:59:59Z",
    )


def _item_statement(qid: str, *, rank: str = "normal") -> dict[str, object]:
    return {
        "rank": rank,
        "mainsnak": {
            "snaktype": "value",
            "datavalue": {
                "type": "wikibase-entityid",
                "value": {"entity-type": "item", "id": qid},
            },
        },
    }


def test_explicit_active_squad_is_parsed_with_revision_provenance() -> None:
    snapshot = _snapshot(
        "== Current squad ==\n" + _player("[[Player One|One]]", 2) + _player("Player Two", 3)
    )

    assert snapshot is not None
    assert snapshot.heading == "Current squad"
    assert snapshot.source_article_title == "Example Club"
    assert snapshot.revision_id == 123456
    assert snapshot.revision_timestamp == "2024-09-01T12:00:00Z"
    assert snapshot.snapshot_target == "2024-09-06T23:59:59Z"
    assert [row.display_name for row in snapshot.observations] == ["One", "Player Two"]
    assert snapshot.observations[0].player_article_title == "Player One"
    assert snapshot.observations[1].player_article_title is None


def test_generic_players_heading_is_not_roster_evidence() -> None:
    assert _snapshot("== Players ==\n" + _player("[[Historic Star]]")) is None


def test_notable_players_child_section_is_excluded_from_parent_squad() -> None:
    snapshot = _snapshot(
        "== Squad ==\n"
        + _player("[[Active Player]]", 4)
        + "=== Notable players ===\n"
        + _player("[[Historic Star]]", 10)
    )

    assert snapshot is not None
    assert [row.display_name for row in snapshot.observations] == ["Active Player"]


def test_higher_priority_current_squad_beats_larger_generic_squad() -> None:
    snapshot = _snapshot(
        "== Squad ==\n"
        + _player("[[Squad One]]", 1)
        + _player("[[Squad Two]]", 2)
        + "== Current squad ==\n"
        + _player("[[Current One]]", 3)
    )

    assert snapshot is not None
    assert snapshot.heading == "Current squad"
    assert [row.display_name for row in snapshot.observations] == ["Current One"]


def test_leading_player_link_is_accepted_even_with_following_annotation() -> None:
    assert (
        leading_player_article_title("[[Player One]] (on loan from [[Example Club]])")
        == "Player One"
    )


def test_annotation_only_link_is_never_promoted_to_player_article() -> None:
    assert leading_player_article_title("Lucas Lopez (on loan from [[CA Nueva Chicago]])") is None


def test_human_wikidata_item_passes_fail_closed_gate() -> None:
    payload = {
        "entities": {
            "Q100": {
                "claims": {
                    "P31": [_item_statement("Q5")],
                }
            }
        }
    }

    assert wikidata_item_is_explicit_human(payload, expected_qid="Q100") is True


def test_non_human_wikidata_item_is_rejected() -> None:
    payload = {
        "entities": {
            "Q101": {
                "claims": {
                    "P31": [_item_statement("Q476028")],
                }
            }
        }
    }

    assert wikidata_item_is_explicit_human(payload, expected_qid="Q101") is False


def test_deprecated_human_claim_does_not_pass_gate() -> None:
    payload = {
        "entities": {
            "Q102": {
                "claims": {
                    "P31": [_item_statement("Q5", rank="deprecated")],
                }
            }
        }
    }

    assert wikidata_item_is_explicit_human(payload, expected_qid="Q102") is False


def test_missing_wikidata_entity_is_rejected() -> None:
    payload = {"entities": {"Q103": {"missing": ""}}}

    assert wikidata_item_is_explicit_human(payload, expected_qid="Q103") is False


def test_invalid_revision_metadata_fails_closed() -> None:
    with pytest.raises(WikipediaHistoricalSquadError, match="revision_id"):
        parse_historical_active_squad_revision(
            "== Squad ==\n" + _player("[[Player One]]"),
            article_title="Example Club",
            revision_id=0,
            revision_timestamp="2024-09-01T12:00:00Z",
            snapshot_target="2024-09-06T23:59:59Z",
        )
