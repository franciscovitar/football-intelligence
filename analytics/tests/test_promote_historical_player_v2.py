from __future__ import annotations

import argparse
from collections import Counter

import pytest

from football_intelligence.db.production_write_guard import (
    PRODUCTION_WRITE_CONFIRMATION_PHRASE,
)
from football_intelligence.jobs.historical_player_promotion_spec import (
    certified_predecessor_promotion_specs,
    historical_player_promotion_spec,
    supported_promotion_competitions,
)
from football_intelligence.jobs.promote_historical_player_v2 import (
    EXPECTED_EVIDENCE_STATES,
    EXPECTED_FEATURE_SNAPSHOTS,
    EXPECTED_MATCHES,
    EXPECTED_PLAYER_APPEARANCES,
    EXPECTED_PLAYER_MATCH_STATS,
    EXPECTED_PLAYERS,
    EXPECTED_SCORE_SNAPSHOTS,
    EXPECTED_SOURCE_OBSERVATIONS,
    EXPECTED_TEAM_MATCH_STATS,
    EXPECTED_TEAMS,
    HistoricalPlayerPromotionError,
    PrewriteState,
    build_parser,
    resolve_target,
    validate_player_v2_invariants,
    validate_prewrite_state,
)


def _args(database_url: str, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "database_url": database_url,
        "allow_remote_write": False,
        "confirm_target": None,
        "production_write_confirmation": None,
        "confirm_database_target": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _complete_state(competition: str) -> PrewriteState:
    spec = historical_player_promotion_spec(competition)
    return PrewriteState(
        season_exists=True,
        matches=spec.matches,
        teams=spec.teams,
        players=spec.players,
        player_appearances=spec.player_appearances,
        player_match_stats=spec.player_match_stats,
        team_match_stats=spec.team_match_stats,
        source_observations=spec.source_observations,
        player_v2_rows=spec.score_snapshots,
        player_v2_feature_rows=spec.feature_snapshots,
    )


def test_parser_defaults_to_england_and_accepts_all_certified_scopes() -> None:
    parser = build_parser()
    default = parser.parse_args(
        [
            "--database-url",
            "postgresql://postgres:postgres@localhost/test",
            "--report",
            "report.json",
        ]
    )
    assert default.competition == "ENG_PL"
    assert set(supported_promotion_competitions()) == {
        "ENG_PL",
        "ESP_LL",
        "FRA_L1",
        "GER_BL1",
        "ITA_SA",
    }

    for competition in supported_promotion_competitions():
        parsed = parser.parse_args(
            [
                "--competition",
                competition,
                "--database-url",
                "postgresql://postgres:postgres@localhost/test",
                "--report",
                "report.json",
            ]
        )
        assert parsed.competition == competition


def test_local_target_needs_no_production_confirmation() -> None:
    target = resolve_target(_args("postgresql://postgres:postgres@localhost:5432/football_test"))
    assert target.is_local is True
    assert target.safe_description == "postgresql://localhost:5432/football_test"


def test_remote_target_fails_closed_without_all_confirmations() -> None:
    with pytest.raises(SystemExit, match="requires ALL"):
        resolve_target(_args("postgresql://user:secret@db.example.com:5432/football"))


def test_remote_target_accepts_exact_quadruple_confirmation() -> None:
    target = resolve_target(
        _args(
            "postgresql://user:secret@db.example.com:5432/football",
            allow_remote_write=True,
            confirm_target="production",
            production_write_confirmation=PRODUCTION_WRITE_CONFIRMATION_PHRASE,
            confirm_database_target="postgresql://db.example.com:5432/football",
        )
    )
    assert target.is_local is False
    assert target.safe_description == "postgresql://db.example.com:5432/football"


def test_england_backward_compatible_aliases_match_pinned_spec() -> None:
    spec = historical_player_promotion_spec("ENG_PL")
    assert spec.matches == EXPECTED_MATCHES
    assert spec.teams == EXPECTED_TEAMS
    assert spec.players == EXPECTED_PLAYERS
    assert spec.player_appearances == EXPECTED_PLAYER_APPEARANCES
    assert spec.player_match_stats == EXPECTED_PLAYER_MATCH_STATS
    assert spec.team_match_stats == EXPECTED_TEAM_MATCH_STATS
    assert spec.source_observations == EXPECTED_SOURCE_OBSERVATIONS
    assert spec.score_snapshots == EXPECTED_SCORE_SNAPSHOTS
    assert spec.feature_snapshots == EXPECTED_FEATURE_SNAPSHOTS
    assert spec.evidence_state_counts == EXPECTED_EVIDENCE_STATES


def test_england_v05_spec_and_certified_predecessors_are_exactly_pinned() -> None:
    current = historical_player_promotion_spec("ENG_PL")
    assert (
        current.matches,
        current.teams,
        current.players,
        current.player_appearances,
        current.source_observations,
        current.score_snapshots,
        current.feature_snapshots,
        current.season_players,
        current.season_players_450_min,
        current.performance_ready,
    ) == (380, 20, 515, 10_443, 433_126, 2_048, 40_513, 512, 385, 385)
    assert current.evidence_state_counts == {"insufficient_data": 1_754, "partial": 294}

    predecessors = certified_predecessor_promotion_specs("ENG_PL")
    assert [(item.source_observations, item.feature_snapshots) for item in predecessors] == [
        (412_609, 26_841),
        (422_877, 38_737),
    ]
    assert all(item.evidence_state_counts == current.evidence_state_counts for item in predecessors)


def test_pinned_non_england_specs_match_observed_runtime_fingerprints() -> None:
    expected = {
        "ESP_LL": (380, 20, 557, 10_555, 437_170, 2_224, 43_881, 556, 415, 415),
        "FRA_L1": (380, 20, 542, 10_515, 435_814, 2_148, 42_300, 537, 395, 395),
        "GER_BL1": (306, 18, 472, 8_501, 352_942, 1_888, 37_413, 472, 349, 349),
        "ITA_SA": (380, 20, 534, 10_573, 441_225, 2_132, 41_996, 533, 403, 403),
    }
    for competition, values in expected.items():
        spec = historical_player_promotion_spec(competition)
        assert (
            spec.matches,
            spec.teams,
            spec.players,
            spec.player_appearances,
            spec.source_observations,
            spec.score_snapshots,
            spec.feature_snapshots,
            spec.season_players,
            spec.season_players_450_min,
            spec.performance_ready,
        ) == values
        assert spec.player_match_stats == spec.player_appearances
        assert spec.team_match_stats == spec.matches * 2
        assert sum(spec.evidence_state_counts.values()) == spec.score_snapshots


def test_prewrite_state_accepts_only_fresh_or_matching_certified_scope() -> None:
    fresh = PrewriteState(
        season_exists=False,
        matches=0,
        teams=0,
        players=0,
        player_appearances=0,
        player_match_stats=0,
        team_match_stats=0,
        source_observations=0,
        player_v2_rows=0,
        player_v2_feature_rows=0,
    )
    validate_prewrite_state(fresh, spec=historical_player_promotion_spec("GER_BL1"))

    for competition in supported_promotion_competitions():
        validate_prewrite_state(
            _complete_state(competition),
            spec=historical_player_promotion_spec(competition),
        )

    with pytest.raises(HistoricalPlayerPromotionError, match="partial state"):
        validate_prewrite_state(
            PrewriteState(
                season_exists=True,
                matches=306,
                teams=18,
                players=472,
                player_appearances=8_501,
                player_match_stats=8_501,
                team_match_stats=612,
                source_observations=336_265,
                player_v2_rows=1_888,
                player_v2_feature_rows=24_785,
            ),
            spec=historical_player_promotion_spec("GER_BL1"),
        )


def test_prewrite_state_accepts_only_exact_certified_england_predecessor() -> None:
    predecessor = certified_predecessor_promotion_specs("ENG_PL")[0]
    predecessor_state = PrewriteState(
        season_exists=True,
        matches=predecessor.matches,
        teams=predecessor.teams,
        players=predecessor.players,
        player_appearances=predecessor.player_appearances,
        player_match_stats=predecessor.player_match_stats,
        team_match_stats=predecessor.team_match_stats,
        source_observations=predecessor.source_observations,
        player_v2_rows=predecessor.score_snapshots,
        player_v2_feature_rows=predecessor.feature_snapshots,
    )
    validate_prewrite_state(predecessor_state, spec=historical_player_promotion_spec("ENG_PL"))

    with pytest.raises(HistoricalPlayerPromotionError, match="partial state"):
        validate_prewrite_state(
            PrewriteState(
                season_exists=True,
                matches=predecessor.matches,
                teams=predecessor.teams,
                players=predecessor.players,
                player_appearances=predecessor.player_appearances,
                player_match_stats=predecessor.player_match_stats,
                team_match_stats=predecessor.team_match_stats,
                source_observations=predecessor.source_observations,
                player_v2_rows=predecessor.score_snapshots,
                player_v2_feature_rows=predecessor.feature_snapshots - 1,
            ),
            spec=historical_player_promotion_spec("ENG_PL"),
        )

    expected_non_eng_predecessors = {
        "ESP_LL": (416_407, 29_008),
        "FRA_L1": (415_230, 28_007),
        "GER_BL1": (336_265, 24_786),
        "ITA_SA": (420_506, 27_872),
    }
    for competition, expected in expected_non_eng_predecessors.items():
        predecessors = certified_predecessor_promotion_specs(competition)
        assert len(predecessors) == 1
        predecessor = predecessors[0]
        assert (predecessor.source_observations, predecessor.feature_snapshots) == expected
        validate_prewrite_state(
            predecessor_state := PrewriteState(
                season_exists=True,
                matches=predecessor.matches,
                teams=predecessor.teams,
                players=predecessor.players,
                player_appearances=predecessor.player_appearances,
                player_match_stats=predecessor.player_match_stats,
                team_match_stats=predecessor.team_match_stats,
                source_observations=predecessor.source_observations,
                player_v2_rows=predecessor.score_snapshots,
                player_v2_feature_rows=predecessor.feature_snapshots,
            ),
            spec=historical_player_promotion_spec(competition),
        )
        with pytest.raises(HistoricalPlayerPromotionError, match="partial state"):
            validate_prewrite_state(
                PrewriteState(
                    season_exists=True,
                    matches=predecessor_state.matches,
                    teams=predecessor_state.teams,
                    players=predecessor_state.players,
                    player_appearances=predecessor_state.player_appearances,
                    player_match_stats=predecessor_state.player_match_stats,
                    team_match_stats=predecessor_state.team_match_stats,
                    source_observations=predecessor_state.source_observations,
                    player_v2_rows=predecessor_state.player_v2_rows,
                    player_v2_feature_rows=predecessor_state.player_v2_feature_rows - 1,
                ),
                spec=historical_player_promotion_spec(competition),
            )


def test_prewrite_state_does_not_accept_another_leagues_complete_shape() -> None:
    with pytest.raises(HistoricalPlayerPromotionError, match="partial state"):
        validate_prewrite_state(
            _complete_state("FRA_L1"),
            spec=historical_player_promotion_spec("ESP_LL"),
        )


def test_player_v2_invariants_match_every_certified_runtime() -> None:
    for competition in supported_promotion_competitions():
        spec = historical_player_promotion_spec(competition)
        validate_player_v2_invariants(
            score_count=spec.score_snapshots,
            feature_count=spec.feature_snapshots,
            evidence_states=Counter(spec.evidence_state_counts),
            snapshot_counts={
                "scores": spec.score_snapshots,
                "features": spec.feature_snapshots,
            },
            product_counts={
                "season_players": spec.season_players,
                "season_players_450_min": spec.season_players_450_min,
                "performance_ready": spec.performance_ready,
                "ranking_candidates": 0,
                "overall_scores": 0,
            },
            spec=spec,
        )


def test_player_v2_invariants_reject_changed_counts() -> None:
    spec = historical_player_promotion_spec("ITA_SA")
    with pytest.raises(HistoricalPlayerPromotionError, match="runtime counts"):
        validate_player_v2_invariants(
            score_count=spec.score_snapshots - 1,
            feature_count=spec.feature_snapshots,
            evidence_states=Counter(spec.evidence_state_counts),
            snapshot_counts={
                "scores": spec.score_snapshots,
                "features": spec.feature_snapshots,
            },
            product_counts={
                "season_players": spec.season_players,
                "season_players_450_min": spec.season_players_450_min,
                "performance_ready": spec.performance_ready,
                "ranking_candidates": 0,
                "overall_scores": 0,
            },
            spec=spec,
        )
