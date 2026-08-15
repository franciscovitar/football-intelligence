from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.team_analytics.engine_v2 import (
    classify_chance_quality_allowed,
    extract_team_issue_signals,
)
from football_intelligence.team_analytics.models import TeamScore

_NOW = datetime(2026, 8, 14, tzinfo=UTC)


def _team_score(**overrides: object) -> TeamScore:
    defaults: dict[str, object] = dict(
        team_id=1,
        team_name="Test United",
        competition_id=1,
        season_id=1,
        scope_key="competition:ENG_PL:2025",
        window="season",
        matches=10,
        overall_score=62.0,
        confidence=0.75,
        dimension_scores={
            "chance_generation": 70.0,
            "defense": 30.0,
            "control": 55.0,
            "finishing_proxy": 20.0,
            "process": 58.0,
            "results": 68.0,
        },
        results_process_delta=15.0,
        results_process_signal="results_above_process",
        diagnostics={
            "signals": ["finishing_issue", "results_above_process"],
            "metric_coverage": 0.9,
        },
        reference_sample_size=12,
        current_elo=1550.0,
        elo_change_last_5=20.0,
        model_version="team-v1.0",
        calculated_at=_NOW,
    )
    defaults.update(overrides)
    return TeamScore(**defaults)  # type: ignore[arg-type]


def test_extract_team_issue_signals_reshapes_without_recomputing() -> None:
    score = _team_score()
    signals = extract_team_issue_signals(score)

    assert len(signals) == 2
    codes = {signal.signal_code for signal in signals}
    assert codes == {"finishing_issue", "results_above_process"}
    for signal in signals:
        assert signal.results_process_delta == 15.0
        assert signal.confidence == 0.75
        assert signal.model_version == "team-v1.0"
        assert signal.team_id == 1
        assert signal.supporting_metrics["overall_score"] == 62.0
        assert signal.supporting_metrics["dimension_finishing_proxy"] == 20.0
        assert signal.supporting_metrics["metric_coverage"] == 0.9


def test_extract_team_issue_signals_empty_when_no_signals_present() -> None:
    score = _team_score(
        results_process_signal="results_aligned",
        diagnostics={"signals": [], "metric_coverage": 0.9},
    )
    assert extract_team_issue_signals(score) == ()


def test_chance_quality_allowed_few_but_high_quality() -> None:
    # Few shots allowed (high volume percentile = good) but the ones allowed
    # are dangerous (low quality percentile = bad).
    signal = classify_chance_quality_allowed(
        shots_total_against_percentile=80.0,
        shots_on_target_against_percentile=20.0,
    )
    assert signal == "few_but_high_quality_chances_allowed"


def test_chance_quality_allowed_high_volume_low_quality() -> None:
    # Many shots allowed (low volume percentile = bad) but they are mostly
    # harmless (high quality percentile = good).
    signal = classify_chance_quality_allowed(
        shots_total_against_percentile=15.0,
        shots_on_target_against_percentile=90.0,
    )
    assert signal == "high_volume_low_quality_allowed"


def test_chance_quality_allowed_prefers_xga_over_shots_on_target() -> None:
    signal = classify_chance_quality_allowed(
        shots_total_against_percentile=80.0,
        shots_on_target_against_percentile=80.0,  # would not trigger alone
        xga_percentile=20.0,  # xGA takes precedence and does trigger
    )
    assert signal == "few_but_high_quality_chances_allowed"


def test_chance_quality_allowed_insufficient_data_without_volume_percentile() -> None:
    signal = classify_chance_quality_allowed(
        shots_total_against_percentile=None,
        shots_on_target_against_percentile=20.0,
    )
    assert signal == "insufficient_data"


def test_chance_quality_allowed_insufficient_data_without_any_quality_percentile() -> None:
    # This is the expected, correct case for the real ENG_PL 2025/26
    # snapshot, which has no team-level xG and no shots-on-target-against
    # granularity from the current zero-cost sources.
    signal = classify_chance_quality_allowed(
        shots_total_against_percentile=80.0,
        shots_on_target_against_percentile=None,
        xga_percentile=None,
    )
    assert signal == "insufficient_data"


def test_chance_quality_allowed_insufficient_data_when_no_strong_pattern() -> None:
    signal = classify_chance_quality_allowed(
        shots_total_against_percentile=55.0,
        shots_on_target_against_percentile=50.0,
    )
    assert signal == "insufficient_data"
