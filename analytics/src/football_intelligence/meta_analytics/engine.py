"""Expectation, stable level, trend, and watchlist calculations."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from football_intelligence.meta_analytics.models import (
    PlayerMetaSnapshot,
    PlayerScoreEvidence,
)

MODEL_VERSION = "meta-v1.0"
SOURCE_MODEL_VERSION = "player-v1.0"

_STABLE_RECENCY = {0: 1.0, 1: 0.60, 2: 0.36, 3: 0.216}
_EXPECTATION_RECENCY = {1: 1.0, 2: 0.60, 3: 0.36}


def calculate_meta_analytics(
    evidence: list[PlayerScoreEvidence],
    *,
    current_scope_key: str,
    calculated_at: datetime | None = None,
) -> tuple[PlayerMetaSnapshot, ...]:
    """Build one current meta snapshot per player with current season evidence."""
    now = calculated_at or datetime.now(UTC)
    grouped: dict[int, list[PlayerScoreEvidence]] = defaultdict(list)
    for item in evidence:
        grouped[item.player_id].append(item)

    snapshots: list[PlayerMetaSnapshot] = []
    for player_id in sorted(grouped):
        items = grouped[player_id]
        current = next(
            (
                item
                for item in items
                if item.period_index == 0
                and item.scope_key == current_scope_key
                and item.window == "season"
            ),
            None,
        )
        if current is None:
            continue

        current_windows = {
            item.window: item
            for item in items
            if item.period_index == 0
            and item.scope_key == current_scope_key
            and item.role == current.role
        }
        histories = sorted(
            (
                item
                for item in items
                if 1 <= item.period_index <= 3
                and item.window == "season"
                and item.role == current.role
            ),
            key=lambda item: item.period_index,
        )

        stable_inputs = [current, *histories]
        stable_score = _weighted_score(
            stable_inputs,
            lambda item: _STABLE_RECENCY[item.period_index] * item.confidence,
        )
        weighted_input_confidence = _weighted_score(
            stable_inputs,
            lambda item: _STABLE_RECENCY[item.period_index],
            value=lambda item: item.confidence,
        )
        stable_confidence = _clamp01(
            weighted_input_confidence * min(1.0, 0.7 + 0.1 * len(stable_inputs))
        )

        expectation_score: float | None
        expectation_confidence: float | None
        surprise_delta: float | None
        if histories:
            expectation_score = _weighted_score(
                histories,
                lambda item: _EXPECTATION_RECENCY[item.period_index] * item.confidence,
            )
            history_confidence = _weighted_score(
                histories,
                lambda item: _EXPECTATION_RECENCY[item.period_index],
                value=lambda item: item.confidence,
            )
            expectation_confidence = _clamp01(
                history_confidence * min(1.0, 0.7 + 0.1 * len(histories))
            )
            surprise_delta = current.overall_score - expectation_score
            surprise_signal = _surprise_signal(
                surprise_delta,
                performance_confidence=current.confidence,
                expectation_confidence=expectation_confidence,
            )
        else:
            expectation_score = None
            expectation_confidence = None
            surprise_delta = None
            surprise_signal = "insufficient_history"

        trend_delta, trend_confidence, trend_signal, trend_evidence = _trend(current_windows)

        usable_surprise = (
            surprise_delta if surprise_signal in {"surprise", "disappointment", "aligned"} else None
        )
        usable_trend = trend_delta if trend_signal in {"rising", "falling", "stable"} else None

        positive_surprise = _clamp(max(0.0, usable_surprise or 0.0) * 4.0)
        positive_trend = _clamp(max(0.0, usable_trend or 0.0) * 5.0)
        watchlist_score = _clamp(
            0.45 * stable_score + 0.35 * positive_surprise + 0.20 * positive_trend
        )
        watchlist_signal = _watchlist_signal(
            stable_score=stable_score,
            surprise_delta=usable_surprise,
            trend_delta=usable_trend,
            watchlist_score=watchlist_score,
        )

        form = current_windows.get("last_5")
        baseline_evidence = tuple(
            {
                "scope_key": item.scope_key,
                "period_index": item.period_index,
                "role": item.role,
                "score": round(item.overall_score, 4),
                "confidence": round(item.confidence, 5),
                "recency_weight": _EXPECTATION_RECENCY[item.period_index],
            }
            for item in histories
        )

        snapshots.append(
            PlayerMetaSnapshot(
                player_id=current.player_id,
                player_name=current.player_name,
                scope_key=current_scope_key,
                role=current.role,
                performance_score=round(current.overall_score, 4),
                performance_confidence=round(current.confidence, 5),
                form_score=None if form is None else round(form.overall_score, 4),
                form_confidence=None if form is None else round(form.confidence, 5),
                stable_score=round(stable_score, 4),
                stable_confidence=round(stable_confidence, 5),
                expectation_score=None
                if expectation_score is None
                else round(expectation_score, 4),
                expectation_confidence=None
                if expectation_confidence is None
                else round(expectation_confidence, 5),
                surprise_delta=None if surprise_delta is None else round(surprise_delta, 4),
                surprise_signal=surprise_signal,
                trend_delta=None if trend_delta is None else round(trend_delta, 4),
                trend_confidence=None if trend_confidence is None else round(trend_confidence, 5),
                trend_signal=trend_signal,
                watchlist_score=round(watchlist_score, 4),
                watchlist_signal=watchlist_signal,
                history_seasons=len(histories),
                baseline_evidence=baseline_evidence,
                trend_evidence=trend_evidence,
                source_model_version=current.model_version,
                model_version=MODEL_VERSION,
                calculated_at=now,
            )
        )

    return tuple(snapshots)


def _weighted_score(
    items: list[PlayerScoreEvidence],
    weight: Callable[[PlayerScoreEvidence], float],
    *,
    value: Callable[[PlayerScoreEvidence], float] | None = None,
) -> float:
    value_fn = value or (lambda item: item.overall_score)
    weighted = [(float(weight(item)), float(value_fn(item))) for item in items]
    denominator = sum(item_weight for item_weight, _ in weighted)
    if denominator <= 0:
        raise ValueError("weighted score requires positive total weight")
    return sum(item_weight * item_value for item_weight, item_value in weighted) / denominator


def _surprise_signal(
    delta: float,
    *,
    performance_confidence: float,
    expectation_confidence: float,
) -> str:
    if performance_confidence < 0.35 or expectation_confidence < 0.35:
        return "insufficient_evidence"
    if delta >= 12:
        return "surprise"
    if delta <= -12:
        return "disappointment"
    return "aligned"


def _trend(
    windows: dict[str, PlayerScoreEvidence],
) -> tuple[float | None, float | None, str, dict[str, Any]]:
    pairs: list[tuple[str, float, float, float]] = []

    last_3 = windows.get("last_3")
    last_10 = windows.get("last_10")
    if last_3 is not None and last_10 is not None:
        pairs.append(
            (
                "short_delta",
                last_3.overall_score - last_10.overall_score,
                min(last_3.confidence, last_10.confidence),
                0.60,
            )
        )

    last_5 = windows.get("last_5")
    season = windows.get("season")
    if last_5 is not None and season is not None:
        pairs.append(
            (
                "form_delta",
                last_5.overall_score - season.overall_score,
                min(last_5.confidence, season.confidence),
                0.40,
            )
        )

    evidence = {
        "windows": {
            key: {
                "score": round(item.overall_score, 4),
                "confidence": round(item.confidence, 5),
                "role": item.role,
            }
            for key, item in sorted(windows.items())
            if key in {"season", "last_3", "last_5", "last_10"}
        },
        "pairs": [
            {
                "name": name,
                "delta": round(delta, 4),
                "pair_confidence": round(pair_confidence, 5),
                "base_weight": base_weight,
            }
            for name, delta, pair_confidence, base_weight in pairs
        ],
    }

    if not pairs:
        return None, None, "insufficient_data", evidence

    weighted_denominator = sum(base * confidence for _, _, confidence, base in pairs)
    base_denominator = sum(base for _, _, _, base in pairs)
    if weighted_denominator <= 0 or base_denominator <= 0:
        return None, 0.0, "insufficient_evidence", evidence

    trend_delta = (
        sum(delta * base * confidence for _, delta, confidence, base in pairs)
        / weighted_denominator
    )
    trend_confidence = sum(base * confidence for _, _, confidence, base in pairs) / base_denominator

    if trend_confidence < 0.30:
        signal = "insufficient_evidence"
    elif trend_delta >= 8:
        signal = "rising"
    elif trend_delta <= -8:
        signal = "falling"
    else:
        signal = "stable"

    return trend_delta, _clamp01(trend_confidence), signal, evidence


def _watchlist_signal(
    *,
    stable_score: float,
    surprise_delta: float | None,
    trend_delta: float | None,
    watchlist_score: float,
) -> str:
    surprise = surprise_delta or 0.0
    trend = trend_delta or 0.0
    if surprise >= 12 and trend >= 6 and stable_score >= 55:
        return "breakout"
    if surprise >= 12 and stable_score >= 55:
        return "outperforming"
    if trend >= 8 and stable_score >= 55:
        return "rising"
    if watchlist_score >= 55 and stable_score >= 55:
        return "monitor"
    return "none"


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))
