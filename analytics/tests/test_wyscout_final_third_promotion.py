from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.data_mesh.adapters.wyscout_open import (
    ESP_LL_SCOPE,
    parse_player_match_observations,
)
from football_intelligence.player_analytics.engine_v2 import (
    calculate_player_analytics_v2_result,
)
from football_intelligence.player_analytics.models import PlayerObservation
from football_intelligence.providers.wyscout_spatial_v1 import (
    classify_pass_into_final_third,
    parse_pass_coordinates,
)

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
                "lineup": [
                    {"playerId": 12},
                    {"playerId": 13},
                    {"playerId": 14},
                    {"playerId": 15},
                ],
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
        "positions": [{"x": 60, "y": 50}, {"x": 80, "y": 50}],
        "tags": [{"id": 1801}],
    },
    # Endpoint unavailable, but start already inside the final third: exact negative.
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Cross",
        "playerId": 13,
        "teamId": 100,
        "positions": [{"x": 80, "y": 20}, {"x": 0, "y": 0}],
        "tags": [{"id": 1802}],
    },
    # Endpoint unavailable and start outside: must remain missing.
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 14,
        "teamId": 100,
        "positions": [{"x": 20, "y": 50}, {"x": 0, "y": 0}],
        "tags": [{"id": 1801}],
    },
    # Complete geometry that stays outside the final third: exact zero.
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 15,
        "teamId": 100,
        "positions": [{"x": 20, "y": 50}, {"x": 40, "y": 50}],
        "tags": [{"id": 1801}],
    },
]


def test_final_third_classifier_preserves_exact_negative_without_imputation() -> None:
    inside_missing = parse_pass_coordinates(_EVENTS[1])
    outside_missing = parse_pass_coordinates(_EVENTS[2])
    positive = parse_pass_coordinates(_EVENTS[0])

    assert classify_pass_into_final_third(inside_missing) == "not_into_final_third"
    assert classify_pass_into_final_third(outside_missing) == "ambiguous"
    assert classify_pass_into_final_third(positive) == "into_final_third"


def test_final_third_emission_preserves_positive_zero_and_missing() -> None:
    observations = parse_player_match_observations([_MATCH], _EVENTS)
    values = {
        observation.entity_source_id: observation.value
        for observation in observations
        if observation.metric_name == "passes_into_final_third"
    }

    assert values["1001:12"] == 1
    assert values["1001:13"] == 0
    assert "1001:14" not in values
    assert values["1001:15"] == 0
    assert values["1001:21"] == 0


def test_final_third_emission_does_not_leak_into_unaudited_scope() -> None:
    esp_match = {**_MATCH, "competitionId": 795, "seasonId": 181144}
    observations = parse_player_match_observations([esp_match], _EVENTS, scope=ESP_LL_SCOPE)
    assert all(item.metric_name != "passes_into_final_third" for item in observations)


def _v2_observation(match_id: int, passes_into_final_third: float | None) -> PlayerObservation:
    return PlayerObservation(
        player_id=77,
        player_name="Exact Final Third Player",
        match_id=match_id,
        kickoff_at=datetime(2018, 1, match_id, tzinfo=UTC),
        team_id=100,
        minutes=90,
        listed_position="CM",
        possession_pct=50.0,
        stats={"passes_into_final_third": passes_into_final_third},
    )


def test_player_v2_never_publishes_partial_final_third_window_as_exact() -> None:
    partial = calculate_player_analytics_v2_result(
        [_v2_observation(1, 2.0), _v2_observation(2, None)],
        scope_key="competition:ENG_PL:2017/18",
    )
    assert not any(
        feature.window == "season" and feature.metric_name == "passes_into_final_third"
        for feature in partial.features
    )

    complete = calculate_player_analytics_v2_result(
        [_v2_observation(1, 2.0), _v2_observation(2, 0.0)],
        scope_key="competition:ENG_PL:2017/18",
    )
    season_feature = next(
        feature
        for feature in complete.features
        if feature.window == "season" and feature.metric_name == "passes_into_final_third"
    )
    assert season_feature.raw_value == 2.0
