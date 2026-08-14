"""Product-level, multi-source union coverage.

`engine.compute_coverage` answers a *provider* question: can THIS ONE
provider supply this metric, for this competition, right now? That is real
evidence, but it is the wrong denominator for the *product* question this
module answers: can Football Intelligence cover this metric, for this
competition, from ANY free current source? Adding another provider must
never make the product-level answer worse merely by growing a
provider-count-scaled denominator -- the denominator here is always the
fixed target catalog (target metrics x target competitions), independent of
how many providers exist.

A requirement is satisfied when AT LEAST ONE provider of the relevant
freshness role has a satisfying state for that exact (competition, metric,
granularity) triple. A `historical` provider can never satisfy a `current`
requirement, and vice versa, because the union is computed separately per
freshness role over only that role's coverage entries.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from football_intelligence.coverage_lab.models import CoverageEntry, FreshnessRole
from football_intelligence.coverage_lab.target_competitions import TargetCompetition
from football_intelligence.coverage_lab.target_metrics import CRITICAL_METRIC_NAMES, TargetMetric

# Precedence mirrors `models.CURRENT_SATISFYING_STATES` for the current role.
# For the historical role, only a source explicitly marked historical/deep
# can ever satisfy a historical requirement -- `current_available` never
# counts here, exactly as `historical_only` never counts toward current.
_SATISFYING_STATES: dict[FreshnessRole, frozenset[str]] = {
    "current": frozenset({"current_available"}),
    "historical": frozenset({"historical_only"}),
}


@dataclass(frozen=True, slots=True)
class ProductCoverageResult:
    numerator: int
    denominator: int
    gap_keys: tuple[str, ...]
    critical_gap_keys: tuple[str, ...]


def _requirement_gap_key(competition_code: str, metric: TargetMetric) -> str:
    return f"{competition_code}:{metric.granularity}:{metric.metric_name}"


def compute_product_coverage(
    *,
    target_metrics: Sequence[TargetMetric],
    target_competitions: Sequence[TargetCompetition],
    coverage_entries: Sequence[CoverageEntry],
    freshness_role: FreshnessRole,
) -> ProductCoverageResult:
    satisfying_states = _SATISFYING_STATES[freshness_role]

    entries_by_requirement: dict[tuple[str, str, str], list[CoverageEntry]] = defaultdict(list)
    for entry in coverage_entries:
        if entry.freshness_role != freshness_role:
            continue
        key = (entry.competition_code, entry.granularity, entry.metric_name)
        entries_by_requirement[key].append(entry)

    numerator = 0
    gap_keys: list[str] = []
    critical_gap_keys: list[str] = []

    for competition in target_competitions:
        for metric in target_metrics:
            key = (competition.code, metric.granularity, metric.metric_name)
            entries = entries_by_requirement.get(key, ())
            satisfied = any(entry.state in satisfying_states for entry in entries)
            if satisfied:
                numerator += 1
                continue

            gap_key = _requirement_gap_key(competition.code, metric)
            gap_keys.append(gap_key)
            if freshness_role == "current" and metric.metric_name in CRITICAL_METRIC_NAMES:
                critical_gap_keys.append(gap_key)

    return ProductCoverageResult(
        numerator=numerator,
        denominator=len(target_metrics) * len(target_competitions),
        gap_keys=tuple(sorted(gap_keys)),
        critical_gap_keys=tuple(sorted(critical_gap_keys)),
    )


def compute_recent_season_coverage(
    *,
    target_metrics: Sequence[TargetMetric],
    target_competitions: Sequence[TargetCompetition],
    coverage_entries: Sequence[CoverageEntry],
) -> ProductCoverageResult:
    """Union coverage from `previous_season` evidence only.

    Real, useful signal that a `current`-role provider's probe verified the
    latest *completed* season -- but this must never be confused with, or
    silently folded into, `compute_product_coverage(freshness_role="current")`'s
    numerator. Reported as its own separate fraction so a competition whose
    only current-role evidence is a year-old season stays visibly distinct
    from one with genuinely current-period evidence.
    """

    entries_by_requirement: dict[tuple[str, str, str], list[CoverageEntry]] = defaultdict(list)
    for entry in coverage_entries:
        if entry.freshness_role != "current":
            continue
        key = (entry.competition_code, entry.granularity, entry.metric_name)
        entries_by_requirement[key].append(entry)

    numerator = 0
    gap_keys: list[str] = []

    for competition in target_competitions:
        for metric in target_metrics:
            key = (competition.code, metric.granularity, metric.metric_name)
            entries = entries_by_requirement.get(key, ())
            satisfied = any(entry.state == "previous_season" for entry in entries)
            if satisfied:
                numerator += 1
            else:
                gap_keys.append(_requirement_gap_key(competition.code, metric))

    return ProductCoverageResult(
        numerator=numerator,
        denominator=len(target_metrics) * len(target_competitions),
        gap_keys=tuple(sorted(gap_keys)),
        critical_gap_keys=(),
    )
