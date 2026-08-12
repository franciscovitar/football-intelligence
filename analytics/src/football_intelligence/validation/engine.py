"""Block 12 V1 Validation orchestration: hard gates + informative calibration.

`hard_status` is "fail" only for real contract/config violations (a bug).
`calibration_status` is informative: "insufficient_data" is never treated as
a system error, and neither status triggers automatic weight changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from football_intelligence.validation.calibration import (
    EloBacktestResult,
    StabilityResult,
    calculate_elo_backtest,
    calculate_player_stability,
)
from football_intelligence.validation.config_checks import check_config_invariants
from football_intelligence.validation.contracts import (
    RatingAuditResult,
    RatingRow,
    TacticalAuditResult,
    TacticalRow,
    audit_rating_contract,
    audit_tactical_contract,
)
from football_intelligence.validation.ingestion_report import (
    IngestionRunRow,
    JobIngestionSummary,
    summarize_ingestion,
)

MODEL_VERSION = "validation-v1.0"


@dataclass(frozen=True, slots=True)
class ValidationReport:
    model_version: str
    hard_status: str
    calibration_status: str
    config_violations: tuple[str, ...]
    elo: EloBacktestResult
    stability: tuple[StabilityResult, ...]
    rating_audit: RatingAuditResult
    tactical_audit: TacticalAuditResult
    ingestion: tuple[JobIngestionSummary, ...]
    calculated_at: datetime


def run_validation(
    *,
    elo_rows: list[tuple[float, float]],
    stability_pairs_by_role: dict[str, list[tuple[float, float]]],
    rating_rows: list[RatingRow],
    tactical_rows: list[TacticalRow],
    ingestion_rows: list[IngestionRunRow],
    calculated_at: datetime | None = None,
) -> ValidationReport:
    now = calculated_at or datetime.now(UTC)

    config_violations = tuple(check_config_invariants())
    rating_audit = audit_rating_contract(rating_rows)
    tactical_audit = audit_tactical_contract(tactical_rows)

    hard_violations = (*config_violations, *rating_audit.violations, *tactical_audit.violations)
    hard_status = "fail" if hard_violations else "pass"

    elo = calculate_elo_backtest(elo_rows)
    stability = calculate_player_stability(stability_pairs_by_role)
    ingestion = summarize_ingestion(ingestion_rows)

    return ValidationReport(
        model_version=MODEL_VERSION,
        hard_status=hard_status,
        calibration_status=elo.status,
        config_violations=config_violations,
        elo=elo,
        stability=stability,
        rating_audit=rating_audit,
        tactical_audit=tactical_audit,
        ingestion=ingestion,
        calculated_at=now,
    )


def build_report_payload(report: ValidationReport) -> dict[str, Any]:
    return {
        "model_version": report.model_version,
        "hard_status": report.hard_status,
        "calibration_status": report.calibration_status,
        "calculated_at": report.calculated_at.isoformat(),
        "config_violations": list(report.config_violations),
        "elo": {
            "sample_size": report.elo.sample_size,
            "status": report.elo.status,
            "brier_score": report.elo.brier_score,
            "baseline_brier_score": report.elo.baseline_brier_score,
            "skill_vs_baseline": report.elo.skill_vs_baseline,
            "average_prediction": report.elo.average_prediction,
            "average_outcome": report.elo.average_outcome,
            "calibration_bins": list(report.elo.calibration_bins),
        },
        "player_stability": [
            {
                "role": item.role,
                "sample_size": item.sample_size,
                "status": item.status,
                "spearman_correlation": item.spearman_correlation,
            }
            for item in report.stability
        ],
        "rating_contract": {
            "row_count": report.rating_audit.row_count,
            "violations": list(report.rating_audit.violations),
            "prevalence": report.rating_audit.prevalence,
        },
        "tactical_contract": {
            "row_count": report.tactical_audit.row_count,
            "violations": list(report.tactical_audit.violations),
            "style_signal_prevalence": report.tactical_audit.style_signal_prevalence,
            "formation_signal_prevalence": report.tactical_audit.formation_signal_prevalence,
            "average_formation_coverage": report.tactical_audit.average_formation_coverage,
            "average_tactical_confidence": report.tactical_audit.average_tactical_confidence,
            "low_coverage_count": report.tactical_audit.low_coverage_count,
        },
        "ingestion": [
            {
                "job_name": item.job_name,
                "run_count": item.run_count,
                "total_requests": item.total_requests,
                "max_requests_per_run": item.max_requests_per_run,
                "succeeded_count": item.succeeded_count,
                "failed_or_partial_count": item.failed_or_partial_count,
                "last_success_at": item.last_success_at,
            }
            for item in report.ingestion
        ],
    }


def build_summary_payload(report: ValidationReport) -> dict[str, Any]:
    return {
        "hard_status": report.hard_status,
        "calibration_status": report.calibration_status,
        "config_violation_count": len(report.config_violations),
        "elo_sample_size": report.elo.sample_size,
        "elo_skill_vs_baseline": report.elo.skill_vs_baseline,
        "player_stability_measured_roles": [
            item.role for item in report.stability if item.status == "measured"
        ],
        "rating_prevalence": report.rating_audit.prevalence,
        "tactical_low_coverage_count": report.tactical_audit.low_coverage_count,
        "ingestion_jobs": [item.job_name for item in report.ingestion],
    }
