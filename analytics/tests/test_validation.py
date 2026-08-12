from __future__ import annotations

import pytest

from football_intelligence.rating_intelligence.engine import (
    MIN_RATING_CONFIDENCE,
    POLARIZATION_GATE,
)
from football_intelligence.validation.calibration import (
    ELO_MIN_SAMPLE_SIZE,
    STABILITY_MIN_SAMPLE_SIZE,
    calculate_elo_backtest,
    calculate_player_stability,
)
from football_intelligence.validation.config_checks import (
    check_config_invariants,
    check_player_analytics_config,
    check_team_analytics_config,
)
from football_intelligence.validation.contracts import (
    RatingRow,
    TacticalRow,
    audit_rating_contract,
    audit_tactical_contract,
)
from football_intelligence.validation.ingestion_report import IngestionRunRow, summarize_ingestion


def test_current_player_and_team_config_pass_invariants() -> None:
    # Regression guard: the shipped weight config must always satisfy its own contract.
    assert check_player_analytics_config() == []
    assert check_team_analytics_config() == []
    assert check_config_invariants() == []


def test_check_player_analytics_config_detects_bad_weight_sum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from football_intelligence.player_analytics import config as player_config

    monkeypatch.setitem(
        player_config.ROLE_SCORE_WEIGHTS,
        "forward",
        (("goals", 0.5, 1),),  # does not sum to 1
    )
    violations = check_player_analytics_config()
    assert any("forward" in item and "sum to" in item for item in violations)


def test_check_team_analytics_config_detects_unknown_direction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from football_intelligence.team_analytics import config as team_config

    monkeypatch.setitem(team_config.CONTROL_WEIGHTS, "possession_pct", -0.1)
    violations = check_team_analytics_config()
    assert any("CONTROL_WEIGHTS" in item for item in violations)


def test_elo_backtest_insufficient_sample() -> None:
    rows = [(0.5, 1.0)] * (ELO_MIN_SAMPLE_SIZE - 1)
    result = calculate_elo_backtest(rows)
    assert result.status == "insufficient_data"
    assert result.brier_score is None


def test_elo_backtest_known_brier_baseline_and_skill() -> None:
    # A perfectly calibrated model: expected always equals actual.
    perfect_rows = [(1.0, 1.0)] * ELO_MIN_SAMPLE_SIZE
    result = calculate_elo_backtest(perfect_rows)
    assert result.status == "pass"
    assert result.brier_score == 0.0
    assert result.baseline_brier_score == pytest.approx(0.25)
    assert result.skill_vs_baseline == pytest.approx(1.0)


def test_elo_backtest_warn_when_worse_than_baseline() -> None:
    # Always predicting the opposite of the actual result: worse than the 0.5 baseline.
    bad_rows = [(1.0, 0.0)] * ELO_MIN_SAMPLE_SIZE
    result = calculate_elo_backtest(bad_rows)
    assert result.status == "warn"
    assert result.skill_vs_baseline is not None
    assert result.skill_vs_baseline < 0


def test_player_stability_insufficient_sample() -> None:
    pairs_by_role = {"forward": [(50.0, 52.0)] * (STABILITY_MIN_SAMPLE_SIZE - 1)}
    results = calculate_player_stability(pairs_by_role)
    assert results[0].status == "insufficient_data"
    assert results[0].spearman_correlation is None


def test_player_stability_perfect_rank_correlation() -> None:
    pairs = [(float(i), float(i)) for i in range(STABILITY_MIN_SAMPLE_SIZE)]
    results = calculate_player_stability({"forward": pairs})
    assert results[0].status == "measured"
    assert results[0].spearman_correlation == pytest.approx(1.0)


def test_player_stability_inverse_rank_correlation() -> None:
    n = STABILITY_MIN_SAMPLE_SIZE
    pairs = [(float(i), float(n - i)) for i in range(n)]
    results = calculate_player_stability({"forward": pairs})
    assert results[0].spearman_correlation == pytest.approx(-1.0)


def test_audit_rating_contract_passes_for_valid_rows() -> None:
    rows = [
        RatingRow(
            rating_signal="underrated",
            rating_confidence=MIN_RATING_CONFIDENCE,
            polarization_score=POLARIZATION_GATE - 1,
            perception_confidence=0.9,
            evidence_count=10,
            scored_evidence_count=8,
            scored_source_count=3,
        )
    ]
    result = audit_rating_contract(rows)
    assert result.violations == ()
    assert result.prevalence == {"underrated": 1}


def test_audit_rating_contract_detects_confidence_violation() -> None:
    rows = [
        RatingRow(
            rating_signal="overrated",
            rating_confidence=MIN_RATING_CONFIDENCE - 0.01,
            polarization_score=0.0,
            perception_confidence=0.9,
            evidence_count=10,
            scored_evidence_count=8,
            scored_source_count=3,
        )
    ]
    result = audit_rating_contract(rows)
    assert len(result.violations) == 1
    assert "rating_confidence" in result.violations[0]


def test_audit_rating_contract_detects_polarization_violation() -> None:
    rows = [
        RatingRow(
            rating_signal="underrated",
            rating_confidence=0.9,
            polarization_score=POLARIZATION_GATE,
            perception_confidence=0.9,
            evidence_count=10,
            scored_evidence_count=8,
            scored_source_count=3,
        )
    ]
    result = audit_rating_contract(rows)
    assert any("polarization_score" in item for item in result.violations)


def test_audit_tactical_contract_detects_unsupported_signal() -> None:
    rows = [
        TacticalRow(
            matches=10,
            formation_matches=8,
            style_signal="high_press",
            defensive_signal="balanced",
            formation_signal="stable",
            tactical_confidence=0.8,
        )
    ]
    result = audit_tactical_contract(rows)
    assert any("high_press" in item for item in result.violations)


def test_audit_tactical_contract_reports_low_coverage_not_a_violation() -> None:
    rows = [
        TacticalRow(
            matches=10,
            formation_matches=1,
            style_signal="balanced",
            defensive_signal="balanced",
            formation_signal="limited_evidence",
            tactical_confidence=0.2,
        )
    ]
    result = audit_tactical_contract(rows)
    assert result.violations == ()
    assert result.low_coverage_count == 1


def test_summarize_ingestion_groups_by_job() -> None:
    from datetime import UTC, datetime

    rows = [
        IngestionRunRow(
            job_name="core-league-sync",
            status="succeeded",
            request_count=10,
            started_at=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        IngestionRunRow(
            job_name="core-league-sync",
            status="failed",
            request_count=5,
            started_at=datetime(2024, 1, 2, tzinfo=UTC),
        ),
        IngestionRunRow(
            job_name="world-radar",
            status="succeeded",
            request_count=12,
            started_at=datetime(2024, 1, 3, tzinfo=UTC),
        ),
    ]
    summaries = summarize_ingestion(rows)
    by_job = {item.job_name: item for item in summaries}
    assert by_job["core-league-sync"].run_count == 2
    assert by_job["core-league-sync"].failed_or_partial_count == 1
    assert by_job["world-radar"].succeeded_count == 1
