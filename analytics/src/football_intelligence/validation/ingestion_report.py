"""Ingestion cost/freshness observability summary (Block 12 B6).

This is observability, not exact billing: it reports request counts and run
outcomes already recorded in `ingestion.ingestion_runs` for a recent window.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class IngestionRunRow:
    job_name: str
    status: str
    request_count: int
    started_at: datetime


@dataclass(frozen=True, slots=True)
class JobIngestionSummary:
    job_name: str
    run_count: int
    total_requests: int
    max_requests_per_run: int
    succeeded_count: int
    failed_or_partial_count: int
    last_success_at: str | None


def summarize_ingestion(rows: list[IngestionRunRow]) -> tuple[JobIngestionSummary, ...]:
    by_job: dict[str, list[IngestionRunRow]] = defaultdict(list)
    for row in rows:
        by_job[row.job_name].append(row)

    summaries: list[JobIngestionSummary] = []
    for job_name in sorted(by_job):
        job_rows = by_job[job_name]
        succeeded = [row for row in job_rows if row.status == "succeeded"]
        failed_or_partial = [row for row in job_rows if row.status != "succeeded"]
        last_success = max((row.started_at for row in succeeded), default=None)
        summaries.append(
            JobIngestionSummary(
                job_name=job_name,
                run_count=len(job_rows),
                total_requests=sum(row.request_count for row in job_rows),
                max_requests_per_run=max((row.request_count for row in job_rows), default=0),
                succeeded_count=len(succeeded),
                failed_or_partial_count=len(failed_or_partial),
                last_success_at=last_success.isoformat() if last_success else None,
            )
        )
    return tuple(summaries)
