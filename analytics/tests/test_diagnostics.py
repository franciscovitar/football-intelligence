from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.diagnostics import (
    PlayerDiagnosticInputs,
    TeamDiagnosticInputs,
    evaluate_player_diagnostics,
    evaluate_team_diagnostics,
)
from football_intelligence.diagnostics.rules_player import (
    breakout_signal,
    finishing_overperformance,
    finishing_underperformance,
    high_volume_low_quality_shooting,
    overrated,
    underrated,
)
from football_intelligence.diagnostics.rules_team import (
    creation_problem,
    defensive_process_strong,
    defensive_process_weak,
    few_but_high_quality_chances_allowed,
    high_volume_low_quality_allowed,
    regression_risk,
    results_above_process,
    results_below_process,
    sterile_possession,
)
from football_intelligence.meta_analytics.models import PlayerMetaSnapshot
from football_intelligence.rating_intelligence.models import PlayerRatingSnapshot
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


def _meta_snapshot(**overrides: object) -> PlayerMetaSnapshot:
    defaults: dict[str, object] = dict(
        player_id=1,
        player_name="Breakout Player",
        scope_key="core:2025",
        role="forward",
        performance_score=70.0,
        performance_confidence=0.8,
        form_score=75.0,
        form_confidence=0.7,
        stable_score=68.0,
        stable_confidence=0.72,
        expectation_score=50.0,
        expectation_confidence=0.6,
        surprise_delta=18.0,
        surprise_signal="surprise",
        trend_delta=10.0,
        trend_confidence=0.65,
        trend_signal="rising",
        watchlist_score=85.0,
        watchlist_signal="breakout",
        history_seasons=1,
        baseline_evidence=(),
        trend_evidence={},
        source_model_version="player-v1.0",
        model_version="meta-v1.0",
        calculated_at=_NOW,
    )
    defaults.update(overrides)
    return PlayerMetaSnapshot(**defaults)  # type: ignore[arg-type]


def _rating_snapshot(**overrides: object) -> PlayerRatingSnapshot:
    defaults: dict[str, object] = dict(
        player_id=1,
        player_name="Rated Player",
        scope_key="core:2025",
        role="forward",
        performance_score=80.0,
        performance_confidence=0.8,
        perception_score=60.0,
        perception_confidence=0.7,
        perception_signal="neutral",
        rating_gap=20.0,
        rating_confidence=0.65,
        rating_signal="underrated",
        consensus_score=50.0,
        polarization_score=10.0,
        evidence_count=6,
        scored_evidence_count=5,
        source_count=3,
        scored_source_count=3,
        evidence_window_days=180,
        evidence_breakdown=(),
        performance_model_version="meta-v1.0",
        perception_model_version="perception-v1.0",
        model_version="rating-v1.0",
        calculated_at=_NOW,
    )
    defaults.update(overrides)
    return PlayerRatingSnapshot(**defaults)  # type: ignore[arg-type]


# -- finishing_underperformance / finishing_overperformance -------------------


def test_finishing_underperformance_fires_on_real_gap() -> None:
    finding = finishing_underperformance(
        player_id=1,
        player_name="Misfiring Striker",
        comparison_group="role:forward",
        window="season",
        goals=3.0,
        goals_percentile=25.0,
        xg=8.0,
        xg_percentile=80.0,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is not None
    assert finding.diagnostic_code == "finishing_underperformance"
    assert finding.entity_type == "player"
    assert finding.severity in ("notable", "high")


def test_finishing_underperformance_returns_none_without_xg() -> None:
    # Missing xG must never be silently treated as 0 -- no fabricated verdict.
    finding = finishing_underperformance(
        player_id=1,
        player_name="No xG Data",
        comparison_group="role:forward",
        window="season",
        goals=3.0,
        goals_percentile=25.0,
        xg=None,
        xg_percentile=None,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is None


def test_finishing_overperformance_fires_on_real_gap() -> None:
    finding = finishing_overperformance(
        player_id=2,
        player_name="Clinical Striker",
        comparison_group="role:forward",
        window="season",
        goals=10.0,
        goals_percentile=90.0,
        xg=4.0,
        xg_percentile=40.0,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is not None
    assert finding.diagnostic_code == "finishing_overperformance"


def test_finishing_overperformance_returns_none_when_aligned() -> None:
    finding = finishing_overperformance(
        player_id=2,
        player_name="Aligned Striker",
        comparison_group="role:forward",
        window="season",
        goals=5.0,
        goals_percentile=55.0,
        xg=5.0,
        xg_percentile=50.0,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is None


# -- high_volume_low_quality_shooting ------------------------------------------


def test_high_volume_low_quality_shooting_fires() -> None:
    finding = high_volume_low_quality_shooting(
        player_id=3,
        player_name="Volume Shooter",
        comparison_group="role:forward",
        window="season",
        shots_percentile=90.0,
        shot_accuracy_percentile=10.0,
        confidence=0.6,
        computed_at=_NOW,
    )
    assert finding is not None
    assert finding.diagnostic_code == "high_volume_low_quality_shooting"


def test_high_volume_low_quality_shooting_none_without_accuracy_data() -> None:
    finding = high_volume_low_quality_shooting(
        player_id=3,
        player_name="No Accuracy Data",
        comparison_group="role:forward",
        window="season",
        shots_percentile=90.0,
        shot_accuracy_percentile=None,
        confidence=0.6,
        computed_at=_NOW,
    )
    assert finding is None


# -- breakout_signal ------------------------------------------------------------


def test_breakout_signal_wraps_meta_analytics_verdict() -> None:
    finding = breakout_signal(_meta_snapshot(), computed_at=_NOW)
    assert finding is not None
    assert finding.diagnostic_code == "breakout_signal"
    assert finding.confidence == 0.72  # exact stable_confidence, not recomputed


def test_breakout_signal_none_when_not_breakout() -> None:
    finding = breakout_signal(_meta_snapshot(watchlist_signal="monitor"), computed_at=_NOW)
    assert finding is None


def test_breakout_signal_none_without_snapshot() -> None:
    assert breakout_signal(None, computed_at=_NOW) is None


# -- underrated / overrated ------------------------------------------------------


def test_underrated_wraps_rating_intelligence_verdict() -> None:
    finding = underrated(_rating_snapshot(), computed_at=_NOW)
    assert finding is not None
    assert finding.diagnostic_code == "underrated"
    assert finding.confidence == 0.65


def test_underrated_none_when_aligned() -> None:
    finding = underrated(
        _rating_snapshot(rating_signal="aligned", rating_gap=2.0), computed_at=_NOW
    )
    assert finding is None


def test_overrated_wraps_rating_intelligence_verdict() -> None:
    finding = overrated(
        _rating_snapshot(rating_signal="overrated", rating_gap=-22.0), computed_at=_NOW
    )
    assert finding is not None
    assert finding.diagnostic_code == "overrated"


def test_overrated_none_when_insufficient_evidence() -> None:
    finding = overrated(
        _rating_snapshot(rating_signal="insufficient_evidence", rating_gap=None), computed_at=_NOW
    )
    assert finding is None


# -- results_above_process / results_below_process (team, wrapped) --------------


def test_results_above_process_wraps_team_score() -> None:
    finding = results_above_process(_team_score(), computed_at=_NOW)
    assert finding is not None
    assert finding.diagnostic_code == "results_above_process"
    assert finding.confidence == 0.75  # exact TeamScore.confidence, not recomputed


def test_results_above_process_none_when_aligned() -> None:
    finding = results_above_process(
        _team_score(results_process_signal="results_aligned"), computed_at=_NOW
    )
    assert finding is None


def test_results_below_process_wraps_team_score() -> None:
    finding = results_below_process(
        _team_score(results_process_signal="results_below_process", results_process_delta=-18.0),
        computed_at=_NOW,
    )
    assert finding is not None
    assert finding.diagnostic_code == "results_below_process"


def test_results_below_process_none_when_above() -> None:
    assert results_below_process(_team_score(), computed_at=_NOW) is None


# -- creation_problem / defensive_process_weak (team, wrapped flags) ------------


def test_creation_problem_wraps_existing_flag() -> None:
    finding = creation_problem(
        _team_score(diagnostics={"signals": ["creation_issue"], "metric_coverage": 0.8}),
        computed_at=_NOW,
    )
    assert finding is not None
    assert finding.diagnostic_code == "creation_problem"


def test_creation_problem_none_without_flag() -> None:
    finding = creation_problem(_team_score(), computed_at=_NOW)
    assert finding is None


def test_defensive_process_weak_wraps_existing_flag() -> None:
    finding = defensive_process_weak(
        _team_score(diagnostics={"signals": ["defensive_process_issue"], "metric_coverage": 0.8}),
        computed_at=_NOW,
    )
    assert finding is not None
    assert finding.diagnostic_code == "defensive_process_weak"


def test_defensive_process_weak_none_without_flag() -> None:
    assert defensive_process_weak(_team_score(), computed_at=_NOW) is None


# -- defensive_process_strong (team, new threshold) ------------------------------


def test_defensive_process_strong_fires_above_threshold() -> None:
    strong_score = _team_score(
        dimension_scores={
            "chance_generation": 50.0,
            "defense": 80.0,
            "control": 55.0,
            "finishing_proxy": 40.0,
            "process": 60.0,
            "results": 50.0,
        }
    )
    finding = defensive_process_strong(strong_score, computed_at=_NOW)
    assert finding is not None
    assert finding.diagnostic_code == "defensive_process_strong"


def test_defensive_process_strong_none_below_threshold() -> None:
    assert defensive_process_strong(_team_score(), computed_at=_NOW) is None


def test_defensive_process_strong_none_when_defense_missing() -> None:
    missing_defense = _team_score(
        dimension_scores={
            "chance_generation": 50.0,
            "control": 55.0,
            "finishing_proxy": 40.0,
            "process": 60.0,
            "results": 50.0,
        }
    )
    assert defensive_process_strong(missing_defense, computed_at=_NOW) is None


# -- regression_risk (team) ------------------------------------------------------


def test_regression_risk_fires_with_high_delta_and_low_confidence() -> None:
    risky_score = _team_score(results_process_delta=35.0, confidence=0.3)
    finding = regression_risk(risky_score, computed_at=_NOW)
    assert finding is not None
    assert finding.diagnostic_code == "regression_risk"
    assert finding.severity == "high"


def test_regression_risk_none_when_confidence_is_high() -> None:
    confident_score = _team_score(results_process_delta=35.0, confidence=0.9)
    assert regression_risk(confident_score, computed_at=_NOW) is None


def test_regression_risk_none_when_delta_is_small() -> None:
    aligned_score = _team_score(results_process_delta=5.0, confidence=0.2)
    assert regression_risk(aligned_score, computed_at=_NOW) is None


# -- sterile_possession (team) ---------------------------------------------------


def test_sterile_possession_fires() -> None:
    finding = sterile_possession(
        team_id=1,
        team_name="Possession FC",
        comparison_group="competition:ENG_PL:2025",
        window="season",
        possession_percentile=80.0,
        chance_generation_percentile=15.0,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is not None
    assert finding.diagnostic_code == "sterile_possession"


def test_sterile_possession_none_without_data() -> None:
    finding = sterile_possession(
        team_id=1,
        team_name="Possession FC",
        comparison_group="competition:ENG_PL:2025",
        window="season",
        possession_percentile=80.0,
        chance_generation_percentile=None,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is None


# -- few_but_high_quality_chances_allowed / high_volume_low_quality_allowed -----


def test_few_but_high_quality_chances_allowed_fires() -> None:
    finding = few_but_high_quality_chances_allowed(
        team_id=1,
        team_name="Compact FC",
        comparison_group="competition:ENG_PL:2025",
        window="season",
        shots_total_against_percentile=80.0,
        shots_on_target_against_percentile=20.0,
        xga_percentile=None,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is not None
    assert finding.diagnostic_code == "few_but_high_quality_chances_allowed"


def test_few_but_high_quality_chances_allowed_none_without_xg_data() -> None:
    # Expected, correct case for the real ENG_PL 2025/26 snapshot (no team xG).
    finding = few_but_high_quality_chances_allowed(
        team_id=1,
        team_name="Compact FC",
        comparison_group="competition:ENG_PL:2025",
        window="season",
        shots_total_against_percentile=80.0,
        shots_on_target_against_percentile=None,
        xga_percentile=None,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is None


def test_high_volume_low_quality_allowed_fires() -> None:
    finding = high_volume_low_quality_allowed(
        team_id=1,
        team_name="Leaky FC",
        comparison_group="competition:ENG_PL:2025",
        window="season",
        shots_total_against_percentile=15.0,
        shots_on_target_against_percentile=90.0,
        xga_percentile=None,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is not None
    assert finding.diagnostic_code == "high_volume_low_quality_allowed"


def test_high_volume_low_quality_allowed_none_without_data() -> None:
    finding = high_volume_low_quality_allowed(
        team_id=1,
        team_name="Leaky FC",
        comparison_group="competition:ENG_PL:2025",
        window="season",
        shots_total_against_percentile=None,
        shots_on_target_against_percentile=None,
        xga_percentile=None,
        confidence=0.7,
        computed_at=_NOW,
    )
    assert finding is None


# -- orchestrators ----------------------------------------------------------------


def test_evaluate_player_diagnostics_returns_only_real_evidence() -> None:
    inputs = PlayerDiagnosticInputs(
        player_id=1,
        player_name="Multi Signal Player",
        comparison_group="role:forward",
        window="season",
        confidence=0.7,
        goals=3.0,
        goals_percentile=20.0,
        xg=9.0,
        xg_percentile=85.0,
        meta_snapshot=_meta_snapshot(),
        rating_snapshot=_rating_snapshot(),
    )
    findings = evaluate_player_diagnostics(inputs, computed_at=_NOW)
    codes = {finding.diagnostic_code for finding in findings}
    assert "finishing_underperformance" in codes
    assert "breakout_signal" in codes
    assert "underrated" in codes
    assert "finishing_overperformance" not in codes


def test_evaluate_player_diagnostics_empty_tuple_is_valid_with_no_evidence() -> None:
    inputs = PlayerDiagnosticInputs(
        player_id=99,
        player_name="No Evidence Player",
        comparison_group="role:forward",
        window="season",
        confidence=0.5,
    )
    assert evaluate_player_diagnostics(inputs, computed_at=_NOW) == ()


def test_evaluate_team_diagnostics_returns_only_real_evidence() -> None:
    inputs = TeamDiagnosticInputs(
        team_id=1,
        team_name="Test United",
        comparison_group="competition:ENG_PL:2025",
        window="season",
        confidence=0.75,
        possession_percentile=80.0,
        chance_generation_percentile=10.0,
        score=_team_score(),
    )
    findings = evaluate_team_diagnostics(inputs, computed_at=_NOW)
    codes = {finding.diagnostic_code for finding in findings}
    assert "sterile_possession" in codes
    assert "results_above_process" in codes
    assert "regression_risk" not in codes


def test_evaluate_team_diagnostics_empty_tuple_is_valid_with_no_evidence() -> None:
    inputs = TeamDiagnosticInputs(
        team_id=2,
        team_name="No Evidence FC",
        comparison_group="competition:ENG_PL:2025",
        window="season",
        confidence=0.5,
    )
    assert evaluate_team_diagnostics(inputs, computed_at=_NOW) == ()


def test_no_rule_fabricates_a_verdict_from_missing_required_input() -> None:
    # Cross-cutting guard: every rule that depends on xG/percentile evidence
    # must return None rather than treat missing evidence as 0/neutral.
    assert (
        finishing_underperformance(
            player_id=1,
            player_name="X",
            comparison_group="role:forward",
            window="season",
            goals=0.0,
            goals_percentile=0.0,
            xg=None,
            xg_percentile=None,
            confidence=0.7,
            computed_at=_NOW,
        )
        is None
    )
    assert (
        finishing_overperformance(
            player_id=1,
            player_name="X",
            comparison_group="role:forward",
            window="season",
            goals=0.0,
            goals_percentile=0.0,
            xg=None,
            xg_percentile=None,
            confidence=0.7,
            computed_at=_NOW,
        )
        is None
    )
