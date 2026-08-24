from __future__ import annotations

import pytest

from football_intelligence.providers.wyscout_open_scopes import (
    CORE_LEAGUE_SPECS,
    WyscoutCoreLeagueSpec,
    WyscoutScopeEvidenceError,
    infer_provider_scope_ids,
    roster_player_ids,
    team_ids,
    verify_published_scope_counts,
)


def _spec(
    *,
    matches: int = 2,
    events: int = 2,
    players: int = 4,
    teams: int = 2,
) -> WyscoutCoreLeagueSpec:
    return WyscoutCoreLeagueSpec(
        competition_code="TEST_LEAGUE",
        source_file_label="Test",
        expected_match_count=matches,
        expected_event_count=events,
        expected_roster_player_count=players,
        expected_team_count=teams,
    )


def _match(
    match_id: int,
    *,
    competition_id: int = 123,
    season_id: int = 456,
    home_team_id: int = 10,
    away_team_id: int = 20,
    home_players: tuple[int, int] = (1, 2),
    away_players: tuple[int, int] = (3, 4),
) -> dict:
    return {
        "wyId": match_id,
        "competitionId": competition_id,
        "seasonId": season_id,
        "teamsData": {
            str(home_team_id): {
                "teamId": home_team_id,
                "formation": {
                    "lineup": [{"playerId": home_players[0]}],
                    "bench": [{"playerId": home_players[1]}],
                },
            },
            str(away_team_id): {
                "teamId": away_team_id,
                "formation": {
                    "lineup": [{"playerId": away_players[0]}],
                    "bench": [{"playerId": away_players[1]}],
                },
            },
        },
    }


def test_core_league_specs_match_published_five_league_totals() -> None:
    assert sum(spec.expected_match_count for spec in CORE_LEAGUE_SPECS) == 1_826
    assert sum(spec.expected_event_count for spec in CORE_LEAGUE_SPECS) == 3_071_395
    assert {spec.competition_code for spec in CORE_LEAGUE_SPECS} == {
        "ENG_PL",
        "ESP_LL",
        "FRA_L1",
        "GER_BL1",
        "ITA_SA",
    }


def test_infer_provider_scope_ids_requires_one_real_native_scope() -> None:
    matches = [_match(1), _match(2)]

    result = infer_provider_scope_ids(matches, spec=_spec())

    assert result.competition_id == 123
    assert result.season_id == 456


def test_infer_provider_scope_ids_rejects_mixed_competitions() -> None:
    matches = [_match(1), _match(2, competition_id=999)]

    with pytest.raises(WyscoutScopeEvidenceError, match="exactly one provider competitionId"):
        infer_provider_scope_ids(matches, spec=_spec())


def test_infer_provider_scope_ids_rejects_wrong_match_count() -> None:
    with pytest.raises(WyscoutScopeEvidenceError, match="expected 2 matches, got 1"):
        infer_provider_scope_ids([_match(1)], spec=_spec())


def test_roster_player_ids_preserves_unused_bench_players_and_ignores_sentinel() -> None:
    match = _match(1)
    match["teamsData"]["10"]["formation"]["bench"].append({"playerId": 0})

    assert roster_player_ids([match]) == frozenset({1, 2, 3, 4})


def test_team_ids_supports_native_team_id_or_teams_data_key() -> None:
    match = _match(1)
    del match["teamsData"]["20"]["teamId"]

    assert team_ids([match]) == frozenset({10, 20})


def test_verify_published_scope_counts_reports_each_dimension_without_inventing_values() -> None:
    spec = _spec(matches=2, events=2, players=4, teams=2)
    matches = [_match(1), _match(2)]
    events = [{"matchId": 1}, {"matchId": 2}]

    assert verify_published_scope_counts(
        matches_payload=matches,
        events_payload=events,
        spec=spec,
    ) == ()

    failures = verify_published_scope_counts(
        matches_payload=matches[:1],
        events_payload=events[:1],
        spec=spec,
    )
    assert "matches expected=2 actual=1" in failures
    assert "events expected=2 actual=1" in failures
