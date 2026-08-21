"""Focused tests for the Block 20D.3 `AdapterScope` generalization of both
certified adapters.

Proves: (1) the default scope is byte-for-byte the original certified
ENG_PL scope for each adapter (backward compatibility); (2) the prepared
ESP_LL scope emits the real, verified provider-native ids, never the
canonical code; (3) a match whose own native competition/season id
disagrees with the declared scope is refused outright
(`ScopeMismatchError`), never silently accepted or misattributed.
"""

from __future__ import annotations

import pytest

from football_intelligence.data_mesh.adapters import statsbomb_open, wyscout_open
from football_intelligence.data_mesh.adapters.scope import ScopeMismatchError

# ---------------------------------------------------------------------------
# Default-scope backward compatibility
# ---------------------------------------------------------------------------


def test_wyscout_default_scope_matches_the_original_certified_eng_pl_constants() -> None:
    scope = wyscout_open.DEFAULT_SCOPE
    assert scope.canonical_competition_code == wyscout_open.COMPETITION_CODE == "ENG_PL"
    assert scope.season_label == wyscout_open.SEASON_LABEL == "2017/18"
    assert scope.provider_competition_id == 364
    assert scope.provider_season_id == 181150


def test_statsbomb_default_scope_matches_the_original_certified_eng_pl_constants() -> None:
    scope = statsbomb_open.DEFAULT_SCOPE
    assert scope.canonical_competition_code == statsbomb_open.COMPETITION_CODE == "ENG_PL"
    assert scope.season_label == statsbomb_open.SEASON_LABEL == "2015/16"
    assert scope.provider_competition_id == 2
    assert scope.provider_season_id == 27


# ---------------------------------------------------------------------------
# Wyscout ESP_LL scope
# ---------------------------------------------------------------------------

_WYSCOUT_ESP_MATCH = {
    "wyId": 5001,
    "competitionId": 795,
    "seasonId": 181144,
    "dateutc": "2018-01-01 15:00:00",
    "status": "Played",
    "gameweek": 1,
    "venue": "Test Arena",
    "teamsData": {
        "100": {"side": "home", "score": 2, "formation": {}},
        "200": {"side": "away", "score": 1, "formation": {}},
    },
}


def test_wyscout_esp_ll_scope_constant_uses_real_provider_native_ids() -> None:
    scope = wyscout_open.ESP_LL_SCOPE
    assert scope.canonical_competition_code == "ESP_LL"
    assert scope.season_label == "2017/18"
    assert scope.provider_competition_id == 795
    assert scope.provider_season_id == 181144
    # Never the canonical code used as if it were the provider's own id.
    assert scope.provider_competition_id != scope.canonical_competition_code


def test_wyscout_esp_ll_scope_emits_correct_canonical_scope_and_native_ids() -> None:
    observations = wyscout_open.parse_match_observations(
        [_WYSCOUT_ESP_MATCH], scope=wyscout_open.ESP_LL_SCOPE
    )
    assert observations
    for obs in observations:
        assert obs.entity_identity_hints["season_label"] == "2017/18"
        if "competition_external_id" in obs.entity_identity_hints:
            assert obs.entity_identity_hints["competition_external_id"] == "795"


def test_wyscout_wrong_provider_competition_is_rejected() -> None:
    # A real England-shaped match fed through an ESP_LL-declared run.
    eng_match = {**_WYSCOUT_ESP_MATCH, "competitionId": 364}
    with pytest.raises(ScopeMismatchError):
        wyscout_open.parse_match_observations([eng_match], scope=wyscout_open.ESP_LL_SCOPE)


def test_wyscout_wrong_provider_season_is_rejected() -> None:
    wrong_season_match = {**_WYSCOUT_ESP_MATCH, "seasonId": 999999}
    with pytest.raises(ScopeMismatchError):
        wyscout_open.parse_match_observations([wrong_season_match], scope=wyscout_open.ESP_LL_SCOPE)


def test_wyscout_mixed_scope_batch_is_rejected() -> None:
    # Some matches ESP_LL, some ENG_PL, in one batch declared as ESP_LL --
    # must be refused outright, never silently accepted for the matching
    # subset.
    eng_match = {**_WYSCOUT_ESP_MATCH, "wyId": 5002, "competitionId": 364}
    with pytest.raises(ScopeMismatchError):
        wyscout_open.parse_match_observations(
            [_WYSCOUT_ESP_MATCH, eng_match], scope=wyscout_open.ESP_LL_SCOPE
        )


# ---------------------------------------------------------------------------
# StatsBomb ESP_LL scope
# ---------------------------------------------------------------------------


def _statsbomb_esp_match_summary(
    match_id: int = 9101, *, competition_id: int = 11, season_id: int = 1
) -> dict:
    return {
        "match_id": match_id,
        "match_date": "2018-01-01",
        "kick_off": "15:00:00.000",
        "home_team": {"home_team_id": 1, "home_team_name": "Home FC"},
        "away_team": {"away_team_id": 2, "away_team_name": "Away FC"},
        "home_score": 2,
        "away_score": 1,
        "match_status": "available",
        "match_week": 1,
        "stadium": {"name": "Test Stadium"},
        "competition": {
            "competition_id": competition_id,
            "country_name": "Spain",
            "competition_name": "La Liga",
        },
        "season": {"season_id": season_id, "season_name": "2017/2018"},
    }


def _statsbomb_bundle(match_summary: dict) -> statsbomb_open.MatchBundle:
    return statsbomb_open.MatchBundle(
        match_id=match_summary["match_id"],
        match_summary=match_summary,
        events_payload=[],
        lineups_payload=[],
    )


def test_statsbomb_esp_ll_scope_constant_uses_real_provider_native_ids() -> None:
    scope = statsbomb_open.ESP_LL_SCOPE
    assert scope.canonical_competition_code == "ESP_LL"
    assert scope.season_label == "2017/18"
    assert scope.provider_competition_id == 11
    assert scope.provider_season_id == 1
    assert scope.provider_competition_id != scope.canonical_competition_code


def test_statsbomb_esp_ll_scope_emits_correct_canonical_scope_and_native_ids() -> None:
    bundle = _statsbomb_bundle(_statsbomb_esp_match_summary())
    observations = statsbomb_open.parse_match_observations(
        [bundle], scope=statsbomb_open.ESP_LL_SCOPE
    )
    assert observations
    for obs in observations:
        assert obs.entity_identity_hints["season_label"] == "2017/18"
        if "competition_external_id" in obs.entity_identity_hints:
            assert obs.entity_identity_hints["competition_external_id"] == "11"


def test_statsbomb_wrong_provider_competition_is_rejected() -> None:
    bundle = _statsbomb_bundle(_statsbomb_esp_match_summary(competition_id=2))
    with pytest.raises(ScopeMismatchError):
        statsbomb_open.parse_match_observations([bundle], scope=statsbomb_open.ESP_LL_SCOPE)


def test_statsbomb_wrong_provider_season_is_rejected() -> None:
    bundle = _statsbomb_bundle(_statsbomb_esp_match_summary(season_id=999999))
    with pytest.raises(ScopeMismatchError):
        statsbomb_open.parse_match_observations([bundle], scope=statsbomb_open.ESP_LL_SCOPE)


def test_statsbomb_mixed_scope_batch_is_rejected() -> None:
    eng_bundle = _statsbomb_bundle(
        _statsbomb_esp_match_summary(9102, competition_id=2, season_id=27)
    )
    esp_bundle = _statsbomb_bundle(_statsbomb_esp_match_summary())
    with pytest.raises(ScopeMismatchError):
        statsbomb_open.parse_match_observations(
            [esp_bundle, eng_bundle], scope=statsbomb_open.ESP_LL_SCOPE
        )


# ---------------------------------------------------------------------------
# Block 20D.4: season_scope_complete -- a genuinely incomplete real scope
# (StatsBomb's real ESP_LL Open Data scope: 36 of one club's 38 real league
# matches) must never emit player_season/goalkeeper_season facts, since
# those would silently look identical to a real full-season aggregate.
# ---------------------------------------------------------------------------


def test_wyscout_esp_ll_scope_is_declared_season_complete() -> None:
    # Wyscout's real ESP_LL Open Data scope IS a genuinely complete
    # 380/380-match season (docs/BLOCK20_MULTI_SOURCE.md) -- must keep the
    # default True, never suppress its genuinely-supported season facts.
    assert wyscout_open.ESP_LL_SCOPE.season_scope_complete is True


def test_statsbomb_esp_ll_scope_is_declared_season_incomplete() -> None:
    # StatsBomb's real ESP_LL Open Data scope is genuinely only 36 of one
    # club's 38 real league matches -- never a full season for any player.
    assert statsbomb_open.ESP_LL_SCOPE.season_scope_complete is False


def test_statsbomb_default_eng_pl_scope_remains_season_complete() -> None:
    # The certified full ENG_PL 2015/16 scope IS a genuinely complete
    # 380/380-match season -- must be completely unaffected by the ESP_LL
    # fix.
    assert statsbomb_open.DEFAULT_SCOPE.season_scope_complete is True


def _statsbomb_lineup_payload_with_one_starter(
    *, team_id: int = 1, player_id: int = 501, player_name: str = "Test Player"
) -> list[dict]:
    return [
        {
            "team_id": team_id,
            "lineup": [
                {
                    "player_id": player_id,
                    "player_name": player_name,
                    "jersey_number": 9,
                    "cards": [],
                    "positions": [{"position": "Center Forward", "start_reason": "Starting XI"}],
                }
            ],
        }
    ]


def test_statsbomb_incomplete_scope_suppresses_season_level_identities() -> None:
    bundle = statsbomb_open.MatchBundle(
        match_id=9101,
        match_summary=_statsbomb_esp_match_summary(),
        events_payload=[],
        lineups_payload=_statsbomb_lineup_payload_with_one_starter(),
    )
    observations = statsbomb_open.parse_premier_league_season(
        [bundle], scope=statsbomb_open.ESP_LL_SCOPE
    )
    season_granularities = {
        obs.metric_granularity
        for obs in observations
        if obs.metric_granularity in ("player_season", "goalkeeper_season")
    }
    assert season_granularities == set()
    # The equivalent player_appearance/match-level facts for the SAME real
    # participant are still emitted -- only the season-level aggregate is
    # suppressed, nothing else about this scope's real per-match evidence.
    assert any(obs.metric_name == "started" for obs in observations)


def test_statsbomb_complete_scope_still_emits_season_level_identities() -> None:
    # Regression guard: the fix must not accidentally suppress season-level
    # facts for a genuinely complete scope (e.g. the certified ENG_PL
    # baseline).
    bundle = statsbomb_open.MatchBundle(
        match_id=1,
        match_summary=_statsbomb_esp_match_summary(9999, competition_id=2, season_id=27),
        events_payload=[],
        lineups_payload=_statsbomb_lineup_payload_with_one_starter(),
    )
    observations = statsbomb_open.parse_premier_league_season(
        [bundle], scope=statsbomb_open.DEFAULT_SCOPE
    )
    season_granularities = {
        obs.metric_granularity
        for obs in observations
        if obs.metric_granularity in ("player_season", "goalkeeper_season")
    }
    assert "player_season" in season_granularities
