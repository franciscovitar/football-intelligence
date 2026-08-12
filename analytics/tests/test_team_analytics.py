from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from football_intelligence.team_analytics.engine import (
    MODEL_VERSION,
    calculate_elo_history,
    calculate_team_analytics,
)
from football_intelligence.team_analytics.models import TeamObservation


def _observation(
    *,
    team_id: int,
    opponent_id: int,
    match_id: int,
    days_ago: int,
    goals_for: int,
    goals_against: int,
    is_home: bool,
    competition_id: int = 1,
    season_id: int = 10,
    shots_total: float | None = 10,
    shots_on_target: float | None = 4,
    shots_inside_box: float | None = 6,
    corners: float | None = 5,
    shots_total_against: float | None = 8,
    shots_on_target_against: float | None = 3,
    shots_inside_box_against: float | None = 4,
    possession: float | None = 55,
    passes_total: float | None = 500,
    passes_accurate: float | None = 425,
    opponent_passes: float | None = 400,
) -> TeamObservation:
    return TeamObservation(
        competition_id=competition_id,
        competition_code=f"COMP_{competition_id}",
        competition_name=f"Competition {competition_id}",
        season_id=season_id,
        season_label="2024",
        team_id=team_id,
        team_name=f"Team {team_id}",
        opponent_team_id=opponent_id,
        match_id=match_id,
        kickoff_at=datetime(2024, 6, 1, tzinfo=UTC) - timedelta(days=days_ago),
        is_home=is_home,
        goals_for=goals_for,
        goals_against=goals_against,
        stats={
            "shots_total_for": shots_total,
            "shots_on_target_for": shots_on_target,
            "shots_inside_box_for": shots_inside_box,
            "corners_for": corners,
            "shots_total_against": shots_total_against,
            "shots_on_target_against": shots_on_target_against,
            "shots_inside_box_against": shots_inside_box_against,
            "possession_pct": possession,
            "passes_total": passes_total,
            "passes_accurate": passes_accurate,
            "opponent_passes_total": opponent_passes,
        },
    )


def _match(
    *,
    home_id: int,
    away_id: int,
    match_id: int,
    days_ago: int,
    home_goals: int,
    away_goals: int,
    competition_id: int = 1,
    season_id: int = 10,
) -> list[TeamObservation]:
    return [
        _observation(
            team_id=home_id,
            opponent_id=away_id,
            match_id=match_id,
            days_ago=days_ago,
            goals_for=home_goals,
            goals_against=away_goals,
            is_home=True,
            competition_id=competition_id,
            season_id=season_id,
        ),
        _observation(
            team_id=away_id,
            opponent_id=home_id,
            match_id=match_id,
            days_ago=days_ago,
            goals_for=away_goals,
            goals_against=home_goals,
            is_home=False,
            competition_id=competition_id,
            season_id=season_id,
        ),
    ]


def _score(result: object, team_id: int, window: str = "season"):  # type: ignore[no-untyped-def]
    return next(
        score
        for score in result.scores  # type: ignore[attr-defined]
        if score.team_id == team_id and score.window == window
    )


def test_dominant_process_team_ranks_above_weak_process_team() -> None:
    observations: list[TeamObservation] = []
    for index in range(5):
        observations.extend(
            [
                _observation(
                    team_id=1,
                    opponent_id=2,
                    match_id=100 + index,
                    days_ago=index * 7,
                    goals_for=2,
                    goals_against=0,
                    is_home=True,
                    shots_total=18,
                    shots_on_target=8,
                    shots_inside_box=12,
                    corners=8,
                    shots_total_against=5,
                    shots_on_target_against=1,
                    shots_inside_box_against=2,
                    possession=65,
                    passes_total=650,
                    passes_accurate=585,
                    opponent_passes=300,
                ),
                _observation(
                    team_id=2,
                    opponent_id=1,
                    match_id=100 + index,
                    days_ago=index * 7,
                    goals_for=0,
                    goals_against=2,
                    is_home=False,
                    shots_total=5,
                    shots_on_target=1,
                    shots_inside_box=2,
                    corners=2,
                    shots_total_against=18,
                    shots_on_target_against=8,
                    shots_inside_box_against=12,
                    possession=35,
                    passes_total=300,
                    passes_accurate=210,
                    opponent_passes=650,
                ),
            ]
        )

    result = calculate_team_analytics(
        observations,
        scope_key="competition:COMP_1:2024",
        competition_id=1,
        season_id=10,
        calculated_at=datetime(2024, 6, 2, tzinfo=UTC),
    )

    strong = _score(result, 1)
    weak = _score(result, 2)
    assert strong.dimension_scores["process"] > weak.dimension_scores["process"]
    assert strong.overall_score > weak.overall_score
    assert strong.model_version == MODEL_VERSION


@pytest.mark.parametrize(
    ("team_id", "expected_signal"),
    [(1, "finishing_issue"), (2, "creation_issue")],
)
def test_creation_and_finishing_diagnostics(team_id: int, expected_signal: str) -> None:
    observations: list[TeamObservation] = []
    for index in range(5):
        observations.extend(
            [
                _observation(
                    team_id=1,
                    opponent_id=2,
                    match_id=200 + index,
                    days_ago=index,
                    goals_for=0,
                    goals_against=1,
                    is_home=True,
                    shots_total=20,
                    shots_on_target=8,
                    shots_inside_box=13,
                    corners=9,
                ),
                _observation(
                    team_id=2,
                    opponent_id=1,
                    match_id=200 + index,
                    days_ago=index,
                    goals_for=2,
                    goals_against=0,
                    is_home=False,
                    shots_total=5,
                    shots_on_target=2,
                    shots_inside_box=3,
                    corners=2,
                ),
                _observation(
                    team_id=3,
                    opponent_id=4,
                    match_id=300 + index,
                    days_ago=index,
                    goals_for=1,
                    goals_against=1,
                    is_home=True,
                    shots_total=10,
                    shots_on_target=4,
                    shots_inside_box=6,
                    corners=5,
                ),
                _observation(
                    team_id=4,
                    opponent_id=3,
                    match_id=300 + index,
                    days_ago=index,
                    goals_for=1,
                    goals_against=1,
                    is_home=False,
                    shots_total=10,
                    shots_on_target=4,
                    shots_inside_box=6,
                    corners=5,
                ),
            ]
        )
    result = calculate_team_analytics(
        observations,
        scope_key="competition:COMP_1:2024",
        competition_id=1,
        season_id=10,
    )
    assert expected_signal in _score(result, team_id).diagnostics["signals"]


def test_results_process_diagnostics_use_neutral_language_codes() -> None:
    observations: list[TeamObservation] = []
    for index in range(5):
        observations.extend(
            [
                _observation(
                    team_id=1,
                    opponent_id=2,
                    match_id=400 + index,
                    days_ago=index,
                    goals_for=0,
                    goals_against=2,
                    is_home=True,
                    shots_total=18,
                    shots_on_target=7,
                    shots_inside_box=12,
                    corners=8,
                    shots_total_against=5,
                    shots_on_target_against=1,
                    shots_inside_box_against=2,
                    possession=65,
                ),
                _observation(
                    team_id=2,
                    opponent_id=1,
                    match_id=400 + index,
                    days_ago=index,
                    goals_for=2,
                    goals_against=0,
                    is_home=False,
                    shots_total=5,
                    shots_on_target=2,
                    shots_inside_box=3,
                    corners=2,
                    shots_total_against=18,
                    shots_on_target_against=7,
                    shots_inside_box_against=12,
                    possession=35,
                ),
            ]
        )
    result = calculate_team_analytics(
        observations,
        scope_key="competition:COMP_1:2024",
        competition_id=1,
        season_id=10,
    )
    assert _score(result, 1).results_process_signal == "results_below_process"
    assert _score(result, 2).results_process_signal == "results_above_process"


def test_missing_stats_are_not_zero_and_reduce_confidence() -> None:
    observations = [
        _observation(
            team_id=1,
            opponent_id=2,
            match_id=500,
            days_ago=1,
            goals_for=1,
            goals_against=0,
            is_home=True,
        ),
        _observation(
            team_id=2,
            opponent_id=1,
            match_id=500,
            days_ago=1,
            goals_for=0,
            goals_against=1,
            is_home=False,
            shots_on_target=None,
            shots_inside_box=None,
            corners=None,
            shots_on_target_against=None,
            shots_inside_box_against=None,
            possession=None,
            passes_total=None,
            passes_accurate=None,
            opponent_passes=None,
        ),
    ]
    result = calculate_team_analytics(
        observations,
        scope_key="competition:COMP_1:2024",
        competition_id=1,
        season_id=10,
    )
    assert _score(result, 2).confidence < _score(result, 1).confidence
    assert not any(
        feature.team_id == 2 and feature.metric_name == "shots_on_target_for"
        for feature in result.features
    )


def test_recency_weighting_changes_last_five_signal() -> None:
    observations: list[TeamObservation] = []
    for team_id, recent_shots, old_shots in ((1, 20, 2), (2, 2, 20)):
        observations.extend(
            [
                _observation(
                    team_id=team_id,
                    opponent_id=3 - team_id,
                    match_id=600 + team_id,
                    days_ago=1,
                    goals_for=1,
                    goals_against=1,
                    is_home=team_id == 1,
                    shots_total=recent_shots,
                    shots_on_target=recent_shots / 2,
                    shots_inside_box=recent_shots / 2,
                    corners=recent_shots / 3,
                ),
                _observation(
                    team_id=team_id,
                    opponent_id=3 - team_id,
                    match_id=610 + team_id,
                    days_ago=30,
                    goals_for=1,
                    goals_against=1,
                    is_home=team_id != 1,
                    shots_total=old_shots,
                    shots_on_target=old_shots / 2,
                    shots_inside_box=old_shots / 2,
                    corners=old_shots / 3,
                ),
            ]
        )
    result = calculate_team_analytics(
        observations,
        scope_key="competition:COMP_1:2024",
        competition_id=1,
        season_id=10,
    )
    assert (
        _score(result, 1, "last_5").dimension_scores["chance_generation"]
        > _score(result, 2, "last_5").dimension_scores["chance_generation"]
    )


def test_tied_percentiles_use_deterministic_midrank() -> None:
    observations = _match(
        home_id=1,
        away_id=2,
        match_id=700,
        days_ago=1,
        home_goals=1,
        away_goals=1,
    )
    result = calculate_team_analytics(
        observations,
        scope_key="competition:COMP_1:2024",
        competition_id=1,
        season_id=10,
    )
    shot_features = [
        feature
        for feature in result.features
        if feature.window == "season" and feature.metric_name == "shots_total_for"
    ]
    assert [feature.percentile for feature in shot_features] == [50.0, 50.0]


def test_elo_is_deterministic_applies_home_advantage_and_draw_update() -> None:
    observations = _match(
        home_id=1,
        away_id=2,
        match_id=800,
        days_ago=1,
        home_goals=1,
        away_goals=1,
    )
    first = calculate_elo_history(observations)
    second = calculate_elo_history(observations)
    home = next(item for item in first if item.team_id == 1)
    assert home.expected_result == pytest.approx(0.585499)
    assert home.actual_result == 0.5
    assert home.post_match_rating == pytest.approx(1498.29)
    assert [item.post_match_rating for item in first] == [item.post_match_rating for item in second]


def test_elo_remains_available_without_detailed_team_stats() -> None:
    observations = _match(
        home_id=1,
        away_id=2,
        match_id=850,
        days_ago=1,
        home_goals=1,
        away_goals=0,
    )
    observations = [
        TeamObservation(
            competition_id=item.competition_id,
            competition_code=item.competition_code,
            competition_name=item.competition_name,
            season_id=item.season_id,
            season_label=item.season_label,
            team_id=item.team_id,
            team_name=item.team_name,
            opponent_team_id=item.opponent_team_id,
            match_id=item.match_id,
            kickoff_at=item.kickoff_at,
            is_home=item.is_home,
            goals_for=item.goals_for,
            goals_against=item.goals_against,
            stats={name: None for name in item.stats},
        )
        for item in observations
    ]
    result = calculate_team_analytics(
        observations,
        scope_key="competition:COMP_1:2024",
        competition_id=1,
        season_id=10,
    )
    assert result.scores == ()
    assert len(result.elo_history) == 2


def test_elo_keeps_competitions_isolated_and_orders_equal_kickoffs_by_match_id() -> None:
    observations = []
    observations.extend(
        _match(
            home_id=1,
            away_id=2,
            match_id=10,
            days_ago=1,
            home_goals=2,
            away_goals=0,
            competition_id=1,
            season_id=10,
        )
    )
    observations.extend(
        _match(
            home_id=1,
            away_id=2,
            match_id=20,
            days_ago=1,
            home_goals=0,
            away_goals=1,
            competition_id=1,
            season_id=10,
        )
    )
    observations.extend(
        _match(
            home_id=1,
            away_id=2,
            match_id=30,
            days_ago=1,
            home_goals=1,
            away_goals=0,
            competition_id=2,
            season_id=20,
        )
    )
    history = calculate_elo_history(observations)
    context_one = [item for item in history if item.competition_id == 1 and item.team_id == 1]
    context_two_first = next(
        item for item in history if item.competition_id == 2 and item.team_id == 1
    )
    assert context_one[1].pre_match_rating == pytest.approx(context_one[0].post_match_rating)
    assert context_two_first.pre_match_rating == 1500.0
