"""Hard-contract audits for persisted Rating and Tactical Intelligence (Block 12 B4 + B5).

These audits never form football opinions; they only check that persisted
rows respect the structural/statistical contract the owning module already
defined (confidence gates, polarization gates, evidence counts, unsupported
tactical claims). A violation here means data was written that the owning
engine's own rules should have rejected: a real bug, not a football
judgment call.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from football_intelligence.rating_intelligence.engine import (
    MIN_EVIDENCE_COUNT,
    MIN_PERCEPTION_CONFIDENCE,
    MIN_RATING_CONFIDENCE,
    MIN_SCORED_EVIDENCE_COUNT,
    MIN_SCORED_SOURCE_COUNT,
    POLARIZATION_GATE,
)

_UNSUPPORTED_TACTICAL_SIGNALS = frozenset(
    {
        "high_press",
        "low_block",
        "mid_block",
        "counterattack",
        "counter_attacking",
        "counterattack_frequency",
        "player_movement_paths",
        "pressing_height",
        "defensive_block_shape",
    }
)

LOW_COVERAGE_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class RatingRow:
    rating_signal: str
    rating_confidence: float
    polarization_score: float | None
    perception_confidence: float
    evidence_count: int
    scored_evidence_count: int
    scored_source_count: int


@dataclass(frozen=True, slots=True)
class RatingAuditResult:
    row_count: int
    violations: tuple[str, ...]
    prevalence: dict[str, int]


def audit_rating_contract(rows: list[RatingRow]) -> RatingAuditResult:
    violations: list[str] = []
    prevalence: Counter[str] = Counter()

    for row in rows:
        prevalence[row.rating_signal] += 1
        if row.rating_signal not in ("underrated", "overrated"):
            continue

        if row.rating_confidence < MIN_RATING_CONFIDENCE:
            violations.append(
                f"{row.rating_signal} row has rating_confidence {row.rating_confidence} "
                f"below gate {MIN_RATING_CONFIDENCE}"
            )
        if (row.polarization_score or 0.0) >= POLARIZATION_GATE:
            violations.append(
                f"{row.rating_signal} row has polarization_score {row.polarization_score} "
                f"at/above gate {POLARIZATION_GATE}"
            )
        if row.evidence_count < MIN_EVIDENCE_COUNT:
            violations.append(
                f"{row.rating_signal} row has evidence_count {row.evidence_count} "
                f"below gate {MIN_EVIDENCE_COUNT}"
            )
        if row.scored_evidence_count < MIN_SCORED_EVIDENCE_COUNT:
            violations.append(
                f"{row.rating_signal} row has scored_evidence_count {row.scored_evidence_count} "
                f"below gate {MIN_SCORED_EVIDENCE_COUNT}"
            )
        if row.scored_source_count < MIN_SCORED_SOURCE_COUNT:
            violations.append(
                f"{row.rating_signal} row has scored_source_count {row.scored_source_count} "
                f"below gate {MIN_SCORED_SOURCE_COUNT}"
            )
        if row.perception_confidence < MIN_PERCEPTION_CONFIDENCE:
            violations.append(
                f"{row.rating_signal} row has perception_confidence {row.perception_confidence} "
                f"below gate {MIN_PERCEPTION_CONFIDENCE}"
            )

    return RatingAuditResult(
        row_count=len(rows), violations=tuple(violations), prevalence=dict(prevalence)
    )


@dataclass(frozen=True, slots=True)
class TacticalRow:
    matches: int
    formation_matches: int
    style_signal: str
    defensive_signal: str
    formation_signal: str
    tactical_confidence: float


@dataclass(frozen=True, slots=True)
class TacticalAuditResult:
    row_count: int
    violations: tuple[str, ...]
    style_signal_prevalence: dict[str, int]
    formation_signal_prevalence: dict[str, int]
    average_formation_coverage: float | None
    average_tactical_confidence: float | None
    low_coverage_count: int


def audit_tactical_contract(rows: list[TacticalRow]) -> TacticalAuditResult:
    violations: list[str] = []
    style_prevalence: Counter[str] = Counter()
    formation_prevalence: Counter[str] = Counter()
    coverages: list[float] = []
    confidences: list[float] = []
    low_coverage_count = 0

    for row in rows:
        style_prevalence[row.style_signal] += 1
        formation_prevalence[row.formation_signal] += 1
        confidences.append(row.tactical_confidence)

        if row.formation_matches > row.matches:
            violations.append("formation_matches exceeds matches")
        if row.style_signal in _UNSUPPORTED_TACTICAL_SIGNALS:
            violations.append(
                f"unsupported tactical claim persisted as style_signal: {row.style_signal}"
            )
        if row.defensive_signal in _UNSUPPORTED_TACTICAL_SIGNALS:
            violations.append(
                f"unsupported tactical claim persisted as defensive_signal: {row.defensive_signal}"
            )

        if row.matches > 0:
            coverage = row.formation_matches / row.matches
            coverages.append(coverage)
            if coverage < LOW_COVERAGE_THRESHOLD:
                low_coverage_count += 1

    return TacticalAuditResult(
        row_count=len(rows),
        violations=tuple(violations),
        style_signal_prevalence=dict(style_prevalence),
        formation_signal_prevalence=dict(formation_prevalence),
        average_formation_coverage=(
            round(sum(coverages) / len(coverages), 4) if coverages else None
        ),
        average_tactical_confidence=(
            round(sum(confidences) / len(confidences), 4) if confidences else None
        ),
        low_coverage_count=low_coverage_count,
    )
