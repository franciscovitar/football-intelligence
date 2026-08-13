"""Real backtest and rank-stability measurement (Block 12 B2 + B3).

Elo calibration is measured against real `analytics.team_elo_history`
ground truth (expected vs actual result) using Brier score against a
neutral 0.5 baseline, plus an Expected Calibration Error (ECE) across
prediction bins. Player stability measures rank correlation between
season and last-10 windows; it is a stability/coverage signal, not a claim
of predictive accuracy. None of this adjusts model weights automatically;
ECE is informative only and never a hard gate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ELO_MIN_SAMPLE_SIZE = 50
STABILITY_MIN_SAMPLE_SIZE = 20

_BIN_EDGES: tuple[float, ...] = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0001)


@dataclass(frozen=True, slots=True)
class EloBacktestResult:
    sample_size: int
    status: str
    brier_score: float | None
    baseline_brier_score: float | None
    skill_vs_baseline: float | None
    average_prediction: float | None
    average_outcome: float | None
    calibration_bins: tuple[dict[str, float | int], ...]
    calibration_error: float | None


def calculate_elo_backtest(rows: list[tuple[float, float]]) -> EloBacktestResult:
    """`rows` is a list of (expected_result, actual_result) pairs."""

    sample_size = len(rows)
    if sample_size < ELO_MIN_SAMPLE_SIZE:
        return EloBacktestResult(
            sample_size=sample_size,
            status="insufficient_data",
            brier_score=None,
            baseline_brier_score=None,
            skill_vs_baseline=None,
            average_prediction=None,
            average_outcome=None,
            calibration_bins=(),
            calibration_error=None,
        )

    brier = sum((expected - actual) ** 2 for expected, actual in rows) / sample_size
    baseline = sum((0.5 - actual) ** 2 for _, actual in rows) / sample_size
    skill = (1.0 - (brier / baseline)) if baseline > 0 else 0.0
    average_prediction = sum(expected for expected, _ in rows) / sample_size
    average_outcome = sum(actual for _, actual in rows) / sample_size
    status = "pass" if skill > 0 else "warn"
    calibration_bins = _calibration_bins(rows)
    calibration_error = _expected_calibration_error(calibration_bins, total_sample_size=sample_size)

    return EloBacktestResult(
        sample_size=sample_size,
        status=status,
        brier_score=round(brier, 6),
        baseline_brier_score=round(baseline, 6),
        skill_vs_baseline=round(skill, 6),
        average_prediction=round(average_prediction, 6),
        average_outcome=round(average_outcome, 6),
        calibration_bins=calibration_bins,
        calibration_error=round(calibration_error, 6),
    )


def _calibration_bins(rows: list[tuple[float, float]]) -> tuple[dict[str, float | int], ...]:
    bins: list[dict[str, float | int]] = []
    for lower, upper in zip(_BIN_EDGES[:-1], _BIN_EDGES[1:], strict=False):
        bucket = [(expected, actual) for expected, actual in rows if lower <= expected < upper]
        if not bucket:
            continue
        avg_expected = sum(expected for expected, _ in bucket) / len(bucket)
        avg_actual = sum(actual for _, actual in bucket) / len(bucket)
        absolute_error = abs(avg_expected - avg_actual)
        bins.append(
            {
                "range_low": lower,
                "range_high": min(upper, 1.0),
                "sample_size": len(bucket),
                "average_prediction": round(avg_expected, 4),
                "average_outcome": round(avg_actual, 4),
                "absolute_error": round(absolute_error, 4),
            }
        )
    return tuple(bins)


def _expected_calibration_error(
    bins: tuple[dict[str, float | int], ...],
    *,
    total_sample_size: int,
) -> float:
    """ECE = sum((bin_size / total) * abs(bin_average_prediction - bin_average_outcome))."""

    if total_sample_size <= 0:
        return 0.0
    return sum(
        (float(bin_item["sample_size"]) / total_sample_size) * float(bin_item["absolute_error"])
        for bin_item in bins
    )


@dataclass(frozen=True, slots=True)
class StabilityResult:
    role: str
    sample_size: int
    status: str
    spearman_correlation: float | None


def calculate_player_stability(
    pairs_by_role: dict[str, list[tuple[float, float]]],
) -> tuple[StabilityResult, ...]:
    results: list[StabilityResult] = []
    for role in sorted(pairs_by_role):
        pairs = pairs_by_role[role]
        sample_size = len(pairs)
        if sample_size < STABILITY_MIN_SAMPLE_SIZE:
            results.append(
                StabilityResult(
                    role=role,
                    sample_size=sample_size,
                    status="insufficient_data",
                    spearman_correlation=None,
                )
            )
            continue

        season_values = [item[0] for item in pairs]
        recent_values = [item[1] for item in pairs]
        correlation = _spearman(season_values, recent_values)
        results.append(
            StabilityResult(
                role=role,
                sample_size=sample_size,
                status="measured",
                spearman_correlation=round(correlation, 4),
            )
        )
    return tuple(results)


def _spearman(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    rank_x = _ranks(x)
    rank_y = _ranks(y)
    mean_rx = sum(rank_x) / n
    mean_ry = sum(rank_y) / n
    numerator = sum((rx - mean_rx) * (ry - mean_ry) for rx, ry in zip(rank_x, rank_y, strict=True))
    denom_x = math.sqrt(sum((rx - mean_rx) ** 2 for rx in rank_x))
    denom_y = math.sqrt(sum((ry - mean_ry) ** 2 for ry in rank_y))
    if denom_x == 0 or denom_y == 0:
        return 0.0
    return numerator / (denom_x * denom_y)


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks
