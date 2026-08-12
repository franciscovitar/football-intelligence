from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from football_intelligence.player_analytics.engine import (
    MODEL_VERSION,
    calculate_player_analytics,
)
from football_intelligence.player_analytics.models import PlayerObservation


def _observation(
    *,
    player_id: int,
    name: str,
    days_ago: int,
    position: str,
    goals: float | None = None,
    assists: float | None = None,
    shots_total: float | None = None,
    shots_on_target: float | None = None,
    passes_total: float | None = None,
    key_passes: float | None = None,
    tackles: float | None = None,
    blocks: float | None = None,
    interceptions: float | None = None,
    dribbles_successful: float | None = None,
    duels_won: float | None = None,
    fouls_drawn: float | None = None,
    fouls_committed: float | None = None,
    saves: float | None = None,
    possession_pct: float = 50.0,
    minutes: int = 90,
) -> PlayerObservation:
    return PlayerObservation(
        player_id=player_id,
        player_name=name,
        match_id=1000 + player_id * 10 + days_ago,
        kickoff_at=datetime(2024, 5, 30, tzinfo=UTC) - timedelta(days=days_ago),
        team_id=player_id,
        minutes=minutes,
        listed_position=position,
        possession_pct=possession_pct,
        stats={
            "goals": goals,
            "assists": assists,
            "shots_total": shots_total,
            "shots_on_target": shots_on_target,
            "passes_total": passes_total,
            "key_passes": key_passes,
            "tackles": tackles,
            "blocks": blocks,
            "interceptions": interceptions,
            "dribbles_successful": dribbles_successful,
            "duels_won": duels_won,
            "fouls_drawn": fouls_drawn,
            "fouls_committed": fouls_committed,
            "saves": saves,
        },
    )


def test_forward_with_stronger_output_scores_above_peer() -> None:
    observations: list[PlayerObservation] = []
    for days_ago in (1, 8, 15, 22, 29):
        observations.extend(
            [
                _observation(
                    player_id=1,
                    name="High Output Forward",
                    days_ago=days_ago,
                    position="F",
                    goals=1,
                    assists=1,
                    shots_total=5,
                    shots_on_target=3,
                    key_passes=2,
                    dribbles_successful=2,
                    fouls_drawn=2,
                ),
                _observation(
                    player_id=2,
                    name="Low Output Forward",
                    days_ago=days_ago,
                    position="F",
                    goals=None,
                    assists=None,
                    shots_total=1,
                    shots_on_target=None,
                    key_passes=None,
                    dribbles_successful=None,
                    fouls_drawn=1,
                ),
            ]
        )

    result = calculate_player_analytics(
        observations,
        scope_key="test:2024",
        calculated_at=datetime(2024, 6, 1, tzinfo=UTC),
    )

    season_scores = {
        score.player_id: score
        for score in result.scores
        if score.window == "season" and score.role == "forward"
    }
    assert season_scores[1].overall_score > season_scores[2].overall_score
    assert season_scores[1].confidence > 0
    assert season_scores[1].model_version == MODEL_VERSION


def test_null_sparse_event_counts_are_zero_for_valid_appearances() -> None:
    observations = [
        _observation(
            player_id=1,
            name="No Goal Forward",
            days_ago=1,
            position="F",
            goals=None,
            shots_total=None,
            shots_on_target=None,
        ),
        _observation(
            player_id=2,
            name="Scoring Forward",
            days_ago=1,
            position="F",
            goals=1,
            shots_total=2,
            shots_on_target=1,
        ),
    ]

    result = calculate_player_analytics(
        observations,
        scope_key="test:zero-semantics",
        calculated_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    goal_features = {
        feature.player_id: feature
        for feature in result.features
        if feature.window == "season" and feature.metric_name == "goals"
    }

    assert goal_features[1].raw_per90 == pytest.approx(0.0)
    assert goal_features[2].raw_per90 == pytest.approx(1.0)


def test_role_is_minutes_weighted_across_appearances() -> None:
    observations = [
        _observation(
            player_id=9,
            name="Hybrid",
            days_ago=1,
            position="M",
            minutes=90,
        ),
        _observation(
            player_id=9,
            name="Hybrid",
            days_ago=8,
            position="F",
            minutes=30,
        ),
    ]

    result = calculate_player_analytics(
        observations,
        scope_key="test:roles",
        calculated_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    season = next(score for score in result.scores if score.window == "season")

    assert season.role == "midfielder"
    assert season.role_confidence == pytest.approx(0.75)


def test_recent_windows_use_recency_weighting() -> None:
    observations = [
        _observation(
            player_id=1,
            name="Recently Hot",
            days_ago=1,
            position="F",
            goals=2,
            shots_total=5,
            shots_on_target=3,
        ),
        _observation(
            player_id=1,
            name="Recently Hot",
            days_ago=8,
            position="F",
            goals=0,
            shots_total=2,
            shots_on_target=1,
        ),
        _observation(
            player_id=2,
            name="Recently Cold",
            days_ago=1,
            position="F",
            goals=0,
            shots_total=2,
            shots_on_target=1,
        ),
        _observation(
            player_id=2,
            name="Recently Cold",
            days_ago=8,
            position="F",
            goals=2,
            shots_total=5,
            shots_on_target=3,
        ),
    ]

    result = calculate_player_analytics(
        observations,
        scope_key="test:form",
        calculated_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    form_scores = {
        score.player_id: score.overall_score for score in result.scores if score.window == "last_5"
    }

    assert form_scores[1] > form_scores[2]


def test_defensive_context_adjustment_rewards_same_actions_with_less_opportunity() -> None:
    observations = [
        _observation(
            player_id=1,
            name="High Possession Defender",
            days_ago=1,
            position="D",
            tackles=3,
            interceptions=2,
            blocks=1,
            duels_won=5,
            possession_pct=70,
        ),
        _observation(
            player_id=2,
            name="Low Possession Defender",
            days_ago=1,
            position="D",
            tackles=3,
            interceptions=2,
            blocks=1,
            duels_won=5,
            possession_pct=30,
        ),
    ]

    result = calculate_player_analytics(
        observations,
        scope_key="test:context",
        calculated_at=datetime(2024, 6, 1, tzinfo=UTC),
    )
    tackle_features = {
        feature.player_id: feature
        for feature in result.features
        if feature.window == "season" and feature.metric_name == "tackles"
    }

    assert tackle_features[1].raw_per90 == pytest.approx(tackle_features[2].raw_per90)
    assert tackle_features[1].adjusted_per90 > tackle_features[2].adjusted_per90
