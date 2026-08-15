from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.normalization.fpl import normalize_fpl_element_summary

_RETRIEVED_AT = datetime(2026, 8, 14, tzinfo=UTC)
_ELEMENT = {
    "id": 1,
    "web_name": "Raya",
    "first_name": "David",
    "second_name": "Raya Martín",
    "team": 1,
    "element_type": 1,
}

# Captured real shape (element id=1, history_past[-1]) from a live
# `GET https://fantasy.premierleague.com/api/element-summary/1/` call made
# during implementation -- not hit in this test, offline fixture only.
_REAL_HISTORY_PAST_ENTRY = {
    "season_name": "2025/26",
    "element_code": 154561,
    "start_cost": 55,
    "end_cost": 62,
    "total_points": 162,
    "minutes": 3330,
    "goals_scored": 0,
    "assists": 0,
    "clean_sheets": 19,
    "goals_conceded": 26,
    "own_goals": 0,
    "penalties_saved": 0,
    "penalties_missed": 0,
    "yellow_cards": 1,
    "red_cards": 0,
    "saves": 60,
    "bonus": 11,
    "bps": 633,
    "influence": "541.6",
    "creativity": "33.5",
    "threat": "0.0",
    "ict_index": "57.5",
    "clearances_blocks_interceptions": 37,
    "recoveries": 304,
    "tackles": 1,
    "defensive_contribution": 0,
    "starts": 37,
    "expected_goals": "0.00",
    "expected_assists": "0.07",
    "expected_goal_involvements": "0.07",
    "expected_goals_conceded": "27.56",
}


def test_normalizes_real_shaped_entry() -> None:
    record = normalize_fpl_element_summary(
        _ELEMENT,
        _REAL_HISTORY_PAST_ENTRY,
        season_label="2025/26",
        competition_external_id="ENG_PL",
        retrieved_at=_RETRIEVED_AT,
    )
    assert record is not None
    assert record.player_external_id == "1"
    assert record.season_label == "2025/26"
    assert record.minutes == 3330
    assert record.starts == 37
    assert record.saves == 60
    assert record.clean_sheets == 19


def test_zero_real_value_is_preserved_not_missing() -> None:
    # goals_scored: 0 is a real, verified value -- it must stay 0, never
    # silently treated as "not reported".
    record = normalize_fpl_element_summary(
        _ELEMENT,
        _REAL_HISTORY_PAST_ENTRY,
        season_label="2025/26",
        competition_external_id="ENG_PL",
        retrieved_at=_RETRIEVED_AT,
    )
    assert record is not None
    assert record.goals == 0
    assert record.assists == 0
    assert record.own_goals == 0
    assert record.red_cards == 0


def test_string_numeric_fields_are_parsed_to_float() -> None:
    record = normalize_fpl_element_summary(
        _ELEMENT,
        _REAL_HISTORY_PAST_ENTRY,
        season_label="2025/26",
        competition_external_id="ENG_PL",
        retrieved_at=_RETRIEVED_AT,
    )
    assert record is not None
    assert record.influence == 541.6
    assert record.creativity == 33.5
    assert record.threat == 0.0
    assert record.ict_index == 57.5
    assert record.expected_goals == 0.0
    assert record.expected_assists == 0.07
    assert record.expected_goal_involvements == 0.07
    assert record.expected_goals_conceded == 27.56


def test_unparseable_string_field_stays_none_never_crashes() -> None:
    entry = dict(_REAL_HISTORY_PAST_ENTRY)
    entry["influence"] = "not-a-number"
    record = normalize_fpl_element_summary(
        _ELEMENT,
        entry,
        season_label="2025/26",
        competition_external_id="ENG_PL",
        retrieved_at=_RETRIEVED_AT,
    )
    assert record is not None
    assert record.influence is None


def test_missing_field_stays_none_never_fabricated_as_zero() -> None:
    entry = dict(_REAL_HISTORY_PAST_ENTRY)
    del entry["bonus"]
    del entry["expected_goals"]
    record = normalize_fpl_element_summary(
        _ELEMENT,
        entry,
        season_label="2025/26",
        competition_external_id="ENG_PL",
        retrieved_at=_RETRIEVED_AT,
    )
    assert record is not None
    assert record.bonus is None
    assert record.expected_goals is None


def test_appearances_is_always_none_fpl_never_reports_it() -> None:
    record = normalize_fpl_element_summary(
        _ELEMENT,
        _REAL_HISTORY_PAST_ENTRY,
        season_label="2025/26",
        competition_external_id="ENG_PL",
        retrieved_at=_RETRIEVED_AT,
    )
    assert record is not None
    assert record.appearances is None


def test_season_name_mismatch_returns_none() -> None:
    record = normalize_fpl_element_summary(
        _ELEMENT,
        _REAL_HISTORY_PAST_ENTRY,
        season_label="2024/25",
        competition_external_id="ENG_PL",
        retrieved_at=_RETRIEVED_AT,
    )
    assert record is None


def test_missing_element_id_returns_none() -> None:
    record = normalize_fpl_element_summary(
        {"web_name": "No Id"},
        _REAL_HISTORY_PAST_ENTRY,
        season_label="2025/26",
        competition_external_id="ENG_PL",
        retrieved_at=_RETRIEVED_AT,
    )
    assert record is None


def test_provenance_fields_are_populated() -> None:
    record = normalize_fpl_element_summary(
        _ELEMENT,
        _REAL_HISTORY_PAST_ENTRY,
        season_label="2025/26",
        competition_external_id="ENG_PL",
        retrieved_at=_RETRIEVED_AT,
    )
    assert record is not None
    assert record.source == "fpl-official-api"
    assert record.source_url == "https://fantasy.premierleague.com/api/element-summary/1/"
    assert record.retrieved_at == _RETRIEVED_AT
    assert record.semantic_version.strip()
