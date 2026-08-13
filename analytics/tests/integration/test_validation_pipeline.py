from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.db.provider_repository import connect
from football_intelligence.db.validation_repository import (
    ValidationRepository,
    report_from_repository,
)
from football_intelligence.validation.engine import build_report_payload, build_summary_payload


@pytest.mark.integration
def test_validation_run_persists_and_reads_back() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        repository = ValidationRepository(connection)

        # The shipped config must never hard-fail; ELO/stability samples are
        # allowed to be small or empty (informational, not a system error).
        report = report_from_repository(repository)
        assert report.hard_status == "pass"
        assert report.calibration_status in ("pass", "warn", "insufficient_data")

        calculated_at = datetime.now(UTC)
        repository.persist_run(
            model_version=report.model_version,
            hard_status=report.hard_status,
            calibration_status=report.calibration_status,
            summary=build_summary_payload(report),
            report=build_report_payload(report),
            calculated_at=calculated_at,
        )

        latest = repository.latest_run()
        assert latest is not None
        assert latest["model_version"] == report.model_version
        assert latest["hard_status"] == "pass"

        connection.rollback()
