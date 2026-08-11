"""Coverage summaries used to decide which metrics are safe for later models."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from football_intelligence.normalization.models import (
    PlayerMatchStatsRecord,
    TeamMatchStatsRecord,
)

CoverageReport = dict[str, dict[str, int | float | str]]


def build_normalized_coverage(
    *,
    team_stats: tuple[TeamMatchStatsRecord, ...],
    player_stats: tuple[PlayerMatchStatsRecord, ...],
) -> dict[str, CoverageReport]:
    return {
        "team_match_stats": _coverage_for_records(team_stats, TeamMatchStatsRecord),
        "player_match_stats": _coverage_for_records(player_stats, PlayerMatchStatsRecord),
    }


def _coverage_for_records(
    records: tuple[Any, ...],
    record_type: type[Any],
) -> CoverageReport:
    identity_fields = {
        "match_external_id",
        "team_external_id",
        "player_external_id",
    }
    result: CoverageReport = {}
    sample_size = len(records)

    for field in fields(record_type):
        if field.name in identity_fields:
            continue
        non_null_count = sum(getattr(record, field.name) is not None for record in records)
        result[field.name] = {
            "availability": _availability(sample_size, non_null_count),
            "sample_size": sample_size,
            "non_null_count": non_null_count,
            "coverage_pct": round(
                (non_null_count / sample_size * 100.0) if sample_size else 0.0,
                2,
            ),
        }
    return result


def _availability(sample_size: int, non_null_count: int) -> str:
    if sample_size == 0:
        return "unknown"
    if non_null_count == 0:
        return "unavailable"
    if non_null_count == sample_size:
        return "available"
    return "partial"
