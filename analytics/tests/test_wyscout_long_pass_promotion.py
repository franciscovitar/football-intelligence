from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.data_mesh.adapters.wyscout_open import (
    _EMITTED_IDENTITIES,
    ESP_LL_SCOPE,
    SEMANTIC_VERSION,
    parse_player_match_observations,
)
from football_intelligence.player_analytics.engine_v2 import calculate_player_analytics_v2_result
from football_intelligence.player_analytics.models import PlayerObservation
from football_intelligence.providers.wyscout_open_mapping import adapter_safe_mappings

_MATCH = {
    "wyId": 1001,
    "competitionId": 364,
    "seasonId": 181150,
    "dateutc": "2018-01-01 15:00:00",
    "status": "Played",
    "gameweek": 1,
    "venue": "Test Arena",
    "teamsData": {
        "100": {
            "side": "home",
            "score": 0,
            "formation": {
                "lineup": [{"playerId": 12}, {"playerId": 13}, {"playerId": 14}],
                "bench": [],
                "substitutions": [],
            },
        },
        "200": {
            "side": "away",
            "score": 0,
            "formation": {
                "lineup": [{"playerId": 21}],
                "bench": [],
                "substitutions": [],
            },
        },
    },
}

_EVENTS = [
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 12,
        "teamId": 100,
        "positions": [{"x": 10, "y": 50}, {"x": 60, "y": 50}],
        "tags": [{"id": 1801}],
    },
    # Cross is explicitly non-long under v1.1, so absent geometry does not
    # poison the long-pass metric. Player 13 therefore has a confirmed zero.
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Cross",
        "playerId": 13,
        "teamId": 100,
        "tags": [{"id": 1801}],
    },
    # Simple pass needs geometry. The verified (0,0) endpoint sentinel makes
    # player 14's accurate-long value unknown, not zero.
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 14,
        "teamId": 100,
        "positions": [{"x": 20, "y": 50}, {"x": 0, "y": 0}],
        "tags": [{"id": 1801}],
    },
]


def test_long_pass_promotion_is_metric_specific_and_versioned() -> None:
    safe = {(item.catalog_key, item.catalog_granularity) for item in adapter_safe_mappings()}
    assert ("long_passes_accurate", "player_match") in safe
    assert ("progressive_passes", "player_match") not in safe
    assert ("passes_into_final_third", "player_match") in safe
    assert ("long_passes_accurate", "player_match") in _EMITTED_IDENTITIES
    assert ("passes_into_final_third", "player_match") in _EMITTED_IDENTITIES
    assert SEMANTIC_VERSION == "wyscout-open-v0.4"


def test_long_pass_emission_preserves_positive_zero_and_missing() -> None:
    observations = parse_player_match_observations([_MATCH], _EVENTS)
    values = {
        observation.entity_source_id: observation.value
        for observation in observations
        if observation.metric_name == "long_passes_accurate"
    }

    assert values["1001:12"] == 1
    assert values["1001:13"] == 0
    assert "1001:14" not in values
    # A participant with no Pass events has fully observed absence, not missing.
    assert values["1001:21"] == 0


def test_long_pass_promotion_does_not_leak_into_unaudited_league_scopes() -> None:
    esp_match = {**_MATCH, "competitionId": 795, "seasonId": 181144}
    observations = parse_player_match_observations([esp_match], _EVENTS, scope=ESP_LL_SCOPE)
    assert any(item.metric_name == "passes_total" for item in observations)
    assert all(item.metric_name != "long_passes_accurate" for item in observations)


def _v2_observation(match_id: int, long_passes_accurate: float | None) -> PlayerObservation:
    return PlayerObservation(
        player_id=77,
        player_name="Exact Evidence Player",
        match_id=match_id,
        kickoff_at=datetime(2018, 1, match_id, tzinfo=UTC),
        team_id=100,
        minutes=90,
        listed_position="CM",
        possession_pct=50.0,
        stats={"long_passes_accurate": long_passes_accurate},
    )


def test_player_v2_never_publishes_partial_long_pass_window_as_exact() -> None:
    partial = calculate_player_analytics_v2_result(
        [_v2_observation(1, 2.0), _v2_observation(2, None)],
        scope_key="competition:ENG_PL:2017/18",
    )
    assert not any(
        feature.window == "season" and feature.metric_name == "long_passes_accurate"
        for feature in partial.features
    )

    complete = calculate_player_analytics_v2_result(
        [_v2_observation(1, 2.0), _v2_observation(2, 0.0)],
        scope_key="competition:ENG_PL:2017/18",
    )
    season_feature = next(
        feature
        for feature in complete.features
        if feature.window == "season" and feature.metric_name == "long_passes_accurate"
    )
    assert season_feature.raw_value == 2.0
