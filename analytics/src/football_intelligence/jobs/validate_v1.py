"""Run Block 12 V1 Validation: hard gates + informative calibration evidence.

Exits non-zero only on a real hard failure (config/contract violation) or a
system error. An `insufficient_data` calibration status is never treated as
a failure.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from football_intelligence.db.provider_repository import connect
from football_intelligence.db.validation_repository import (
    ValidationRepository,
    report_from_repository,
)
from football_intelligence.validation.engine import build_report_payload, build_summary_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Block 12 V1 Validation (hard gates + informative calibration)"
    )
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")

    with connect(database_url) as connection:
        repository = ValidationRepository(connection)
        report = report_from_repository(repository)
        repository.persist_run(
            model_version=report.model_version,
            hard_status=report.hard_status,
            calibration_status=report.calibration_status,
            summary=build_summary_payload(report),
            report=build_report_payload(report),
            calculated_at=report.calculated_at,
        )
        connection.commit()

    payload = build_report_payload(report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"V1 VALIDATION: hard_status={report.hard_status} "
        f"calibration_status={report.calibration_status} "
        f"elo_sample={report.elo.sample_size}"
    )
    print(f"REPORT: {args.report}")

    if report.hard_status != "pass":
        violation_count = (
            len(report.config_violations)
            + len(report.rating_audit.violations)
            + len(report.tactical_audit.violations)
        )
        raise SystemExit(f"V1 VALIDATION: FAIL ({violation_count} hard violations; see report)")


if __name__ == "__main__":
    main()
