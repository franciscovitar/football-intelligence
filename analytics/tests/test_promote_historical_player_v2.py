from __future__ import annotations

import argparse
from collections import Counter

import pytest

from football_intelligence.db.production_write_guard import (
    PRODUCTION_WRITE_CONFIRMATION_PHRASE,
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


def test_prewrite_state_accepts_only_fresh_or_certified_complete() -> None:
    validate_prewrite_state(
        PrewriteState(
            season_exists=False,
            matches=0,
            teams=0,
            players=0,
            player_appearances=0,
            player_match_stats=0,
            team_match_stats=0,
            source_observations=0,
            player_v2_rows=0,
        )
    )
    validate_prewrite_state(
        PrewriteState(
            season_exists=True,
            matches=EXPECTED_MATCHES,
            teams=EXPECTED_TEAMS,
            players=EXPECTED_PLAYERS,
            player_appearances=EXPECTED_PLAYER_APPEARANCES,
            player_match_stats=EXPECTED_PLAYER_MATCH_STATS,
            team_match_stats=EXPECTED_TEAM_MATCH_STATS,
            source_observations=EXPECTED_SOURCE_OBSERVATIONS,
            player_v2_rows=EXPECTED_SCORE_SNAPSHOTS,
        )
    )

    with pytest.raises(HistoricalPlayerPromotionError, match="partial state"):
        validate_prewrite_state(
            PrewriteState(
                season_exists=True,
                matches=1,
                teams=2,
                players=0,
                player_appearances=0,
                player_match_stats=0,
                team_match_stats=0,
                source_observations=0,
                player_v2_rows=0,
            )
        )


def test_player_v2_invariants_match_certified_runtime() -> None:
    validate_player_v2_invariants(
        score_count=EXPECTED_SCORE_SNAPSHOTS,
        feature_count=EXPECTED_FEATURE_SNAPSHOTS,
        evidence_states=Counter(EXPECTED_EVIDENCE_STATES),
        snapshot_counts={
            "scores": EXPECTED_SCORE_SNAPSHOTS,
            "features": EXPECTED_FEATURE_SNAPSHOTS,
        },
        product_counts={
            "season_players": 512,
            "season_players_450_min": 385,
            "performance_ready": 385,
            "ranking_candidates": 0,
            "overall_scores": 0,
        },
    )


def test_player_v2_invariants_reject_changed_counts() -> None:
    with pytest.raises(HistoricalPlayerPromotionError, match="runtime counts"):
        validate_player_v2_invariants(
            score_count=EXPECTED_SCORE_SNAPSHOTS - 1,
            feature_count=EXPECTED_FEATURE_SNAPSHOTS,
            evidence_states=Counter(EXPECTED_EVIDENCE_STATES),
            snapshot_counts={
                "scores": EXPECTED_SCORE_SNAPSHOTS,
                "features": EXPECTED_FEATURE_SNAPSHOTS,
            },
            product_counts={
                "season_players": 512,
                "season_players_450_min": 385,
                "performance_ready": 385,
                "ranking_candidates": 0,
                "overall_scores": 0,
            },
        )
