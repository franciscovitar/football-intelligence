from __future__ import annotations

from datetime import UTC, datetime

import pytest

from football_intelligence.meta_analytics.engine import calculate_meta_analytics
from football_intelligence.meta_analytics.models import PlayerScoreEvidence


def _evidence(
    *,
    period: int,
    window: str = "season",
    score: float,
    confidence: float = 0.8,
    role: str = "forward",
    player_id: int = 1,
) -> PlayerScoreEvidence:
    scope = "core:2024" if period == 0 else f"core:{2024 - period}"
    return PlayerScoreEvidence(
        player_id=player_id,
        player_name=f"Player {player_id}",
        scope_key=scope,
        period_index=period,
        window=window,
        role=role,
        overall_score=score,
        confidence=confidence,
        model_version="player-v1.0",
    )


def _snapshot(items: list[PlayerScoreEvidence]):
    result = calculate_meta_analytics(
        items,
        current_scope_key="core:2024",
        calculated_at=datetime(2024, 8, 1, tzinfo=UTC),
    )
    assert len(result) == 1
    return result[0]


def test_stable_weights_current_more_than_old_history() -> None:
    snapshot = _snapshot(
        [
            _evidence(period=0, score=90),
            _evidence(period=1, score=50),
            _evidence(period=2, score=50),
        ]
    )
    assert snapshot.stable_score > 65


def test_low_confidence_history_has_less_influence() -> None:
    high = _snapshot([_evidence(period=0, score=80), _evidence(period=1, score=20, confidence=0.9)])
    low = _snapshot([_evidence(period=0, score=80), _evidence(period=1, score=20, confidence=0.1)])
    assert low.stable_score > high.stable_score


def test_role_change_does_not_contaminate_expectation() -> None:
    snapshot = _snapshot(
        [
            _evidence(period=0, score=80, role="forward"),
            _evidence(period=1, score=20, role="midfielder"),
        ]
    )
    assert snapshot.expectation_score is None
    assert snapshot.history_seasons == 0


@pytest.mark.parametrize(
    ("history", "current", "signal"),
    [(60, 80, "surprise"), (80, 60, "disappointment")],
)
def test_surprise_thresholds(history: float, current: float, signal: str) -> None:
    snapshot = _snapshot([_evidence(period=0, score=current), _evidence(period=1, score=history)])
    assert snapshot.surprise_signal == signal


def test_low_confidence_marks_surprise_as_insufficient_evidence() -> None:
    snapshot = _snapshot(
        [
            _evidence(period=0, score=90, confidence=0.2),
            _evidence(period=1, score=50, confidence=0.2),
        ]
    )
    assert snapshot.surprise_signal == "insufficient_evidence"


def test_missing_history_keeps_stable_score() -> None:
    snapshot = _snapshot([_evidence(period=0, score=75)])
    assert snapshot.stable_score == pytest.approx(75)
    assert snapshot.expectation_score is None
    assert snapshot.surprise_signal == "insufficient_history"


def test_rising_and_falling_trends() -> None:
    rising = _snapshot(
        [
            _evidence(period=0, window="season", score=60),
            _evidence(period=0, window="last_10", score=60),
            _evidence(period=0, window="last_5", score=75),
            _evidence(period=0, window="last_3", score=80),
        ]
    )
    falling = _snapshot(
        [
            _evidence(period=0, window="season", score=80),
            _evidence(period=0, window="last_10", score=80),
            _evidence(period=0, window="last_5", score=65),
            _evidence(period=0, window="last_3", score=60),
        ]
    )
    assert rising.trend_signal == "rising"
    assert falling.trend_signal == "falling"


def test_watchlist_breakout_requires_surprise_trend_and_quality() -> None:
    snapshot = _snapshot(
        [
            _evidence(period=0, window="season", score=82),
            _evidence(period=0, window="last_10", score=70),
            _evidence(period=0, window="last_5", score=90),
            _evidence(period=0, window="last_3", score=92),
            _evidence(period=1, score=60),
        ]
    )
    assert snapshot.watchlist_signal == "breakout"
    assert snapshot.watchlist_score > 55


def test_form_is_not_stable() -> None:
    snapshot = _snapshot(
        [
            _evidence(period=0, window="season", score=70),
            _evidence(period=0, window="last_5", score=95),
            _evidence(period=1, score=65),
        ]
    )
    assert snapshot.form_score == 95
    assert snapshot.stable_score != snapshot.form_score


def test_tied_current_without_history_is_deterministic() -> None:
    first = _snapshot([_evidence(period=0, score=70)])
    second = _snapshot([_evidence(period=0, score=70)])
    assert first.stable_score == second.stable_score
    assert first.watchlist_score == second.watchlist_score
