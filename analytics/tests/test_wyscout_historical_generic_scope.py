from __future__ import annotations

from football_intelligence.data_mesh.adapters.wyscout_open import (
    FRA_L1_SCOPE,
    GER_BL1_SCOPE,
    ITA_SA_SCOPE,
    parse_match_observations,
)
from football_intelligence.normalization.wyscout_historical import (
    normalize_wyscout_historical_scope,
)

PLAYERS = [
    {"wyId": 11, "shortName": "Home Forward", "role": {"code2": "FW"}},
    {"wyId": 21, "shortName": "Away Defender", "role": {"code2": "DF"}},
]
TEAMS = [
    {"wyId": 100, "name": "Home FC"},
    {"wyId": 200, "name": "Away FC"},
]
FRA_MATCH = {
    "wyId": 5001,
    "competitionId": 412,
    "seasonId": 181189,
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
                "lineup": [{"playerId": 11}],
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
EVENTS = [
    {
        "matchId": 5001,
        "eventName": "Shot",
        "subEventName": "Shot",
        "playerId": 11,
        "teamId": 100,
        "tags": [{"id": 101}, {"id": 1801}],
    }
]


def test_real_audit_native_scope_ids_are_encoded_explicitly() -> None:
    assert (FRA_L1_SCOPE.provider_competition_id, FRA_L1_SCOPE.provider_season_id) == (412, 181189)
    assert (GER_BL1_SCOPE.provider_competition_id, GER_BL1_SCOPE.provider_season_id) == (426, 181137)
    assert (ITA_SA_SCOPE.provider_competition_id, ITA_SA_SCOPE.provider_season_id) == (524, 181248)


def test_verified_french_scope_normalizes_with_country_provenance() -> None:
    observations = parse_match_observations([FRA_MATCH], TEAMS, scope=FRA_L1_SCOPE)
    assert observations
    assert all("matches_France.json" in item.source_reference for item in observations)

    result = normalize_wyscout_historical_scope(
        matches_payload=[FRA_MATCH],
        events_payload=EVENTS,
        players_payload=PLAYERS,
        teams_payload=TEAMS,
        scope=FRA_L1_SCOPE,
        expected_match_count=1,
    )

    assert result.batch.provider_competition_id == "412"
    assert result.batch.season_label == "2017/18"
    stats = {row.player_external_id: row for row in result.batch.player_match_stats}
    assert stats["11"].goals == 1
    assert stats["21"].goals == 0
