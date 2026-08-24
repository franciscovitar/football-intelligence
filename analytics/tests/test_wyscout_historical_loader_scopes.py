from __future__ import annotations

import pytest

from football_intelligence.jobs.load_wyscout_historical import (
    ScopedDatabaseCounts,
    WyscoutHistoricalLoadError,
    _validate_scoped_invariants,
    build_parser,
)
from football_intelligence.jobs.wyscout_historical_scope import (
    scope_config,
    supported_competition_codes,
)


def test_loader_defaults_to_england_and_accepts_all_verified_core_leagues() -> None:
    parser = build_parser()
    default_args = parser.parse_args(
        [
            "--database-url",
            "postgresql://postgres:postgres@localhost/test",
            "--report",
            "report.json",
        ]
    )
    assert default_args.competition == "ENG_PL"

    supported = set(supported_competition_codes())
    assert supported == {"ENG_PL", "ESP_LL", "FRA_L1", "GER_BL1", "ITA_SA"}
    for competition_code in supported:
        args = parser.parse_args(
            [
                "--competition",
                competition_code,
                "--database-url",
                "postgresql://postgres:postgres@localhost/test",
                "--report",
                "report.json",
            ]
        )
        assert args.competition == competition_code


def test_scope_configs_match_real_five_league_evidence() -> None:
    expected = {
        "ENG_PL": (364, 181150, 380, 20),
        "ESP_LL": (795, 181144, 380, 20),
        "FRA_L1": (412, 181189, 380, 20),
        "GER_BL1": (426, 181137, 306, 18),
        "ITA_SA": (524, 181248, 380, 20),
    }

    for competition_code, (
        provider_competition_id,
        provider_season_id,
        match_count,
        team_count,
    ) in expected.items():
        config = scope_config(competition_code)
        assert config.scope.provider_competition_id == provider_competition_id
        assert config.scope.provider_season_id == provider_season_id
        assert config.spec.expected_match_count == match_count
        assert config.spec.expected_team_count == team_count


def test_generic_invariants_accept_bundesliga_shape_and_exact_batch_counts() -> None:
    counts = ScopedDatabaseCounts(
        matches=306,
        teams=18,
        players=472,
        player_appearances=8501,
        player_match_stats=8501,
        team_match_stats=612,
        source_observations=336265,
    )

    _validate_scoped_invariants(
        counts,
        expected_matches=306,
        expected_teams=18,
        expected_players=472,
        expected_player_appearances=8501,
        expected_player_match_stats=8501,
        expected_team_match_stats=612,
        expected_source_observations=336265,
    )


def test_generic_invariants_fail_closed_on_scope_mismatch() -> None:
    counts = ScopedDatabaseCounts(
        matches=306,
        teams=18,
        players=472,
        player_appearances=8501,
        player_match_stats=8501,
        team_match_stats=612,
        source_observations=336265,
    )

    with pytest.raises(WyscoutHistoricalLoadError, match="expected 380 matches"):
        _validate_scoped_invariants(
            counts,
            expected_matches=380,
            expected_teams=18,
            expected_players=472,
            expected_player_appearances=8501,
            expected_player_match_stats=8501,
            expected_team_match_stats=612,
            expected_source_observations=336265,
        )
