from __future__ import annotations

from datetime import UTC, datetime

import pytest

from football_intelligence.data_mesh.adapters.wyscout_open import (
    parse_england_season,
)
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.jobs.load_wyscout_historical import (
    _apply_safe_minutes_policy,
)
from football_intelligence.normalization.models import (
    NormalizedFixtureBatch,
    PlayerAppearanceRecord,
)
from football_intelligence.normalization.wyscout_historical import (
    WyscoutHistoricalNormalizationError,
    normalize_england_2017_18,
)


PLAYERS = [
    {"wyId": 11, "shortName": "H. Keeper", "role": {"code2": "GK"}},
    {"wyId": 12, "shortName": "H. Forward", "role": {"code2": "FW"}},
    {"wyId": 13, "shortName": "H. Mid", "role": {"code2": "MD"}},
    {"wyId": 21, "shortName": "A. Defender", "role": {"code2": "DF"}},
]

TEAMS = [
    {"wyId": 100, "name": "Team A"},
    {"wyId": 200, "name": "Team B"},
]

MATCH = {
    "wyId": 1001,
    "competitionId": 364,
    "seasonId": 181150,
    "dateutc": "2018-01-01 15:00:00",
    "duration": "Regular",
    "status": "Played",
    "gameweek": 1,
    "venue": "Test Arena",
    "teamsData": {
        "100": {
            "side": "home",
            "score": 1,
            "formation": {
                "lineup": [{"playerId": 11}, {"playerId": 12}],
                "bench": [{"playerId": 13}],
                "substitutions": [{"playerIn": 13, "playerOut": 12, "minute": 60}],
            },
        },
        "200": {
            "side": "away",
            "score": 0,
            "formation": {
                "lineup": [{"playerId": 21}],
                "bench": [],
                "substitutions": "null",
            },
        },
    },
}

EVENTS = [
    {
        "matchId": 1001,
        "eventName": "Shot",
        "subEventName": "Shot",
        "playerId": 12,
        "teamId": 100,
        "tags": [{"id": 101}, {"id": 1801}],
    },
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 13,
        "teamId": 100,
        "tags": [{"id": 1801}],
    },
    {
        "matchId": 1001,
        "eventName": "Save attempt",
        "subEventName": "Save attempt",
        "playerId": 11,
        "teamId": 100,
        "tags": [{"id": 1801}],
    },
    {
        "matchId": 1001,
        "eventName": "Foul",
        "subEventName": "Foul",
        "playerId": 21,
        "teamId": 200,
        "tags": [{"id": 1701}],
    },
]


def test_wyscout_historical_normalization_preserves_supported_vs_missing() -> None:
    result = normalize_england_2017_18(
        matches_payload=[MATCH],
        events_payload=EVENTS,
        players_payload=PLAYERS,
        teams_payload=TEAMS,
        expected_match_count=None,
    )

    assert result.unresolved_participating_player_ids == ()
    assert len(result.batch.matches) == 1
    assert result.batch.matches[0].status == "finished"
    assert len(result.batch.team_match_stats) == 2

    appearances = {item.player_external_id: item for item in result.batch.appearances}
    assert appearances["11"].minutes == 90
    assert appearances["12"].minutes == 60
    assert appearances["13"].minutes == 30
    assert appearances["21"].minutes == 90
    assert appearances["11"].listed_position == "GK"
    assert appearances["12"].listed_position == "FW"
    assert appearances["13"].listed_position == "MID"
    assert appearances["21"].listed_position == "DEF"

    stats = {item.player_external_id: item for item in result.batch.player_match_stats}
    assert stats["12"].goals == 1
    assert stats["12"].shots_total == 1
    assert stats["13"].passes_total == 1
    assert stats["21"].red_cards == 1

    # The source/adapter does not support these legacy canonical fields with
    # the required semantics. Missing must stay missing, never become zero.
    assert stats["12"].tackles is None
    assert stats["12"].blocks is None
    assert stats["12"].dribbles_attempted is None
    assert stats["12"].dribbles_successful is None
    assert stats["12"].fouls_drawn is None


def test_wyscout_historical_normalization_refuses_non_regular_match() -> None:
    bad_match = {**MATCH, "duration": "ExtraTime"}
    with pytest.raises(WyscoutHistoricalNormalizationError, match="unsupported duration"):
        normalize_england_2017_18(
            matches_payload=[bad_match],
            events_payload=EVENTS,
            players_payload=PLAYERS,
            teams_payload=TEAMS,
            expected_match_count=None,
        )


def test_safe_minutes_policy_excludes_ambiguous_exposure_without_dropping_rows() -> None:
    batch = NormalizedFixtureBatch(
        provider_competition_id="364",
        season_label="2017/18",
        teams=(),
        players=(),
        matches=(),
        team_match_stats=(),
        appearances=(
            PlayerAppearanceRecord("1001", "21", "200", 90, True, None, None, "DEF"),
            PlayerAppearanceRecord("1001", "22", "200", 0, False, None, None, "FW"),
        ),
        player_match_stats=(),
    )
    red_card = NormalizedObservation(
        source_code="wyscout-open",
        source_type="objective_structured",
        entity_type="player",
        entity_source_id="1001:21",
        entity_identity_hints={
            "match_external_id": "1001",
            "player_external_id": "21",
            "season_label": "2017/18",
        },
        metric_name="red_cards",
        value=1,
        observed_at=datetime(2018, 1, 1, 15, tzinfo=UTC),
        source_timestamp=datetime(2018, 1, 1, 15, tzinfo=UTC),
        source_reference="test",
        ingestion_run_id=None,
        semantic_version="wyscout-open-v0.2",
        metric_granularity="player_match",
    )

    safe_batch, report = _apply_safe_minutes_policy(batch, observations=[red_card])

    assert [item.minutes for item in safe_batch.appearances] == [None, None]
    assert len(safe_batch.appearances) == 2
    assert report.red_card_appearances_excluded == 1
    assert report.zero_duration_appearances_excluded == 1


def test_real_shape_adapter_red_card_drives_safe_minutes_policy() -> None:
    observations = parse_england_season(
        matches_payload=[MATCH],
        events_payload=EVENTS,
        players_payload=PLAYERS,
        teams_payload=TEAMS,
    )
    normalized = normalize_england_2017_18(
        matches_payload=[MATCH],
        events_payload=EVENTS,
        players_payload=PLAYERS,
        teams_payload=TEAMS,
        expected_match_count=None,
    )

    safe_batch, report = _apply_safe_minutes_policy(normalized.batch, observations=observations)
    appearances = {item.player_external_id: item for item in safe_batch.appearances}

    assert appearances["21"].minutes is None
    assert appearances["12"].minutes == 60
    assert report.red_card_appearances_excluded == 1
