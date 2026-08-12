"""Deterministic perception aggregation and performance-vs-perception comparison."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from football_intelligence.rating_intelligence.models import (
    EvidenceEvaluation,
    PerceptionSignal,
    PlayerRatingInput,
    PlayerRatingSnapshot,
    RatingEvidence,
    RatingSignal,
)

MODEL_VERSION = "rating-v1.0"
PERFORMANCE_MODEL_VERSION = "meta-v1.0"
PERCEPTION_MODEL_VERSION = "perception-v1.0"

EVIDENCE_WINDOW_DAYS = 180
RECENCY_HALF_LIFE_DAYS = 45.0

MIN_EVIDENCE_COUNT = 4
MIN_SCORED_EVIDENCE_COUNT = 3
MIN_SCORED_SOURCE_COUNT = 2
MIN_PERCEPTION_CONFIDENCE = 0.55
MIN_RATING_CONFIDENCE = 0.50
RATING_GAP_THRESHOLD = 12.0
POLARIZATION_GATE = 60.0

_POSITIVE_RULES: tuple[tuple[str, float], ...] = (
    ("earns praise", 1.00),
    ("wins praise", 1.00),
    ("masterclass", 1.00),
    ("world class", 1.00),
    ("outstanding", 1.00),
    ("brilliant", 1.00),
    ("superb", 1.00),
    ("excellent", 0.90),
    ("shines", 0.90),
    ("impresses", 0.90),
    ("impressed", 0.80),
    ("dominant", 0.80),
    ("remarkable", 0.80),
    ("hero", 0.80),
    ("inspired", 0.70),
    ("key player", 0.65),
)

_NEGATIVE_RULES: tuple[tuple[str, float], ...] = (
    ("costly error", -1.00),
    ("under fire", -0.90),
    ("underperforming", -0.90),
    ("underperforms", -0.90),
    ("disappointing", -0.85),
    ("struggles", -0.85),
    ("struggled", -0.85),
    ("blunder", -1.00),
    ("flop", -1.00),
    ("awful", -1.00),
    ("criticised", -0.75),
    ("criticized", -0.75),
    ("poor", -0.75),
    ("booed", -0.75),
    ("wasteful", -0.70),
    ("mistake", -0.65),
    ("anonymous", -0.60),
    ("dropped", -0.50),
)

_RULES = _POSITIVE_RULES + _NEGATIVE_RULES
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|[\r\n;]+")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class _PerceptionAggregate:
    perception_score: float | None
    perception_confidence: float
    perception_signal: PerceptionSignal
    consensus_score: float | None
    polarization_score: float | None
    evidence_count: int
    scored_evidence_count: int
    source_count: int
    scored_source_count: int
    evaluations: tuple[EvidenceEvaluation, ...]


def calculate_rating_intelligence(
    performance: list[PlayerRatingInput],
    evidence: list[RatingEvidence],
    *,
    calculated_at: datetime | None = None,
) -> tuple[PlayerRatingSnapshot, ...]:
    now = calculated_at or datetime.now(UTC)
    evidence_by_player: dict[int, list[RatingEvidence]] = defaultdict(list)
    for item in evidence:
        evidence_by_player[item.player_id].append(item)

    snapshots: list[PlayerRatingSnapshot] = []
    for player in sorted(performance, key=lambda item: item.player_id):
        aggregate = _aggregate_perception(
            evidence_by_player.get(player.player_id, []),
            now=now,
        )

        rating_gap = (
            None
            if aggregate.perception_score is None
            else player.stable_score - aggregate.perception_score
        )
        polarization = aggregate.polarization_score or 0.0
        rating_confidence = _clamp01(
            min(player.stable_confidence, aggregate.perception_confidence)
            * (1.0 - 0.5 * polarization / 100.0)
        )
        rating_signal = _rating_signal(
            rating_gap=rating_gap,
            rating_confidence=rating_confidence,
            perception_confidence=aggregate.perception_confidence,
            polarization_score=aggregate.polarization_score,
            evidence_count=aggregate.evidence_count,
            scored_evidence_count=aggregate.scored_evidence_count,
            scored_source_count=aggregate.scored_source_count,
        )

        breakdown = tuple(
            {
                "evidence_id": item.evidence_id,
                "source_code": item.source_code,
                "source_kind": item.source_kind,
                "stance_score": round(item.stance_score, 4),
                "stance_confidence": round(item.stance_confidence, 5),
                "recency_weight": round(item.recency_weight, 5),
                "matched_terms": list(item.matched_terms),
                "context": item.context,
            }
            for item in aggregate.evaluations
        )

        snapshots.append(
            PlayerRatingSnapshot(
                player_id=player.player_id,
                player_name=player.player_name,
                scope_key=player.scope_key,
                role=player.role,
                performance_score=round(player.stable_score, 4),
                performance_confidence=round(player.stable_confidence, 5),
                perception_score=(
                    None
                    if aggregate.perception_score is None
                    else round(aggregate.perception_score, 4)
                ),
                perception_confidence=round(aggregate.perception_confidence, 5),
                perception_signal=aggregate.perception_signal,
                rating_gap=None if rating_gap is None else round(rating_gap, 4),
                rating_confidence=round(rating_confidence, 5),
                rating_signal=rating_signal,
                consensus_score=(
                    None
                    if aggregate.consensus_score is None
                    else round(aggregate.consensus_score, 4)
                ),
                polarization_score=(
                    None
                    if aggregate.polarization_score is None
                    else round(aggregate.polarization_score, 4)
                ),
                evidence_count=aggregate.evidence_count,
                scored_evidence_count=aggregate.scored_evidence_count,
                source_count=aggregate.source_count,
                scored_source_count=aggregate.scored_source_count,
                evidence_window_days=EVIDENCE_WINDOW_DAYS,
                evidence_breakdown=breakdown,
                performance_model_version=PERFORMANCE_MODEL_VERSION,
                perception_model_version=PERCEPTION_MODEL_VERSION,
                model_version=MODEL_VERSION,
                calculated_at=now,
            )
        )

    return tuple(snapshots)


def score_evidence_stance(
    evidence: RatingEvidence,
    *,
    now: datetime,
) -> EvidenceEvaluation:
    context = _focus_context(
        title=evidence.title,
        excerpt=evidence.excerpt,
        player_name=evidence.matched_text,
    )
    normalized = _normalize(context)

    hits: list[tuple[str, float]] = []
    for phrase, value in _RULES:
        pattern = rf"(?<!\w){re.escape(phrase)}(?!\w)"
        if re.search(pattern, normalized):
            hits.append((phrase, value))

    if hits:
        denominator = sum(abs(value) for _, value in hits)
        stance_score = _clamp_signed(sum(value for _, value in hits) / denominator)
        stance_confidence = _clamp01(0.50 + 0.15 * len(hits))
    else:
        stance_score = 0.0
        stance_confidence = 0.0

    timestamp = evidence.published_at or evidence.discovered_at
    age_days = max(0.0, (now - timestamp).total_seconds() / 86400.0)
    recency_weight = 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)

    return EvidenceEvaluation(
        evidence_id=evidence.evidence_id,
        source_id=evidence.source_id,
        source_code=evidence.source_code,
        source_kind=evidence.source_kind,
        stance_score=stance_score,
        stance_confidence=stance_confidence,
        recency_weight=recency_weight,
        matched_terms=tuple(phrase for phrase, _ in hits),
        context=context[:400],
    )


def _aggregate_perception(
    evidence: list[RatingEvidence],
    *,
    now: datetime,
) -> _PerceptionAggregate:
    evaluations = tuple(
        score_evidence_stance(item, now=now)
        for item in sorted(evidence, key=lambda item: (item.source_id, item.evidence_id))
    )
    evidence_count = len(evaluations)
    source_count = len({item.source_id for item in evaluations})

    scored = tuple(item for item in evaluations if item.stance_confidence > 0.0)
    scored_evidence_count = len(scored)
    scored_source_count = len({item.source_id for item in scored})

    if not scored or scored_source_count == 0:
        return _PerceptionAggregate(
            perception_score=None,
            perception_confidence=0.0,
            perception_signal="insufficient_evidence",
            consensus_score=None,
            polarization_score=None,
            evidence_count=evidence_count,
            scored_evidence_count=scored_evidence_count,
            source_count=source_count,
            scored_source_count=scored_source_count,
            evaluations=evaluations,
        )

    by_source: dict[int, list[EvidenceEvaluation]] = defaultdict(list)
    for item in scored:
        by_source[item.source_id].append(item)

    balanced: list[tuple[EvidenceEvaluation, float]] = []
    valid_source_count = len(by_source)
    for items in by_source.values():
        raw_weights = [item.recency_weight * item.stance_confidence for item in items]
        denominator = sum(raw_weights)
        if denominator <= 0:
            continue
        for item, raw_weight in zip(items, raw_weights, strict=True):
            balanced.append((item, (raw_weight / denominator) / valid_source_count))

    weight_total = sum(weight for _, weight in balanced)
    if weight_total <= 0:
        return _PerceptionAggregate(
            perception_score=None,
            perception_confidence=0.0,
            perception_signal="insufficient_evidence",
            consensus_score=None,
            polarization_score=None,
            evidence_count=evidence_count,
            scored_evidence_count=scored_evidence_count,
            source_count=source_count,
            scored_source_count=scored_source_count,
            evaluations=evaluations,
        )

    normalized_weights = [(item, weight / weight_total) for item, weight in balanced]
    mean = sum(item.stance_score * weight for item, weight in normalized_weights)
    mean_abs = sum(abs(item.stance_score) * weight for item, weight in normalized_weights)
    variance = sum(
        ((item.stance_score - mean) ** 2) * weight for item, weight in normalized_weights
    )
    polarization_fraction = min(1.0, math.sqrt(max(0.0, variance)))
    polarization_score = 100.0 * polarization_fraction
    consensus_score = 100.0 * mean_abs * (1.0 - polarization_fraction)
    perception_score = _clamp100(50.0 + 50.0 * mean)

    breadth = min(1.0, evidence_count / 8.0)
    source_breadth = min(1.0, scored_source_count / 3.0)
    stance_coverage = min(1.0, scored_evidence_count / max(1.0, float(evidence_count)))
    recency_quality = sum(item.recency_weight * weight for item, weight in normalized_weights)
    perception_confidence = _clamp01(
        0.35 * breadth + 0.30 * source_breadth + 0.20 * stance_coverage + 0.15 * recency_quality
    )

    perception_signal = _perception_signal(
        mean=mean,
        polarization_score=polarization_score,
    )

    return _PerceptionAggregate(
        perception_score=perception_score,
        perception_confidence=perception_confidence,
        perception_signal=perception_signal,
        consensus_score=_clamp100(consensus_score),
        polarization_score=_clamp100(polarization_score),
        evidence_count=evidence_count,
        scored_evidence_count=scored_evidence_count,
        source_count=source_count,
        scored_source_count=scored_source_count,
        evaluations=evaluations,
    )


def _rating_signal(
    *,
    rating_gap: float | None,
    rating_confidence: float,
    perception_confidence: float,
    polarization_score: float | None,
    evidence_count: int,
    scored_evidence_count: int,
    scored_source_count: int,
) -> RatingSignal:
    if (
        rating_gap is None
        or evidence_count < MIN_EVIDENCE_COUNT
        or scored_evidence_count < MIN_SCORED_EVIDENCE_COUNT
        or scored_source_count < MIN_SCORED_SOURCE_COUNT
        or perception_confidence < MIN_PERCEPTION_CONFIDENCE
    ):
        return "insufficient_evidence"

    if (polarization_score or 0.0) >= POLARIZATION_GATE:
        return "polarized"
    if rating_confidence < MIN_RATING_CONFIDENCE:
        return "insufficient_evidence"
    if rating_gap >= RATING_GAP_THRESHOLD:
        return "underrated"
    if rating_gap <= -RATING_GAP_THRESHOLD:
        return "overrated"
    return "aligned"


def _perception_signal(
    *,
    mean: float,
    polarization_score: float,
) -> PerceptionSignal:
    if polarization_score >= 40.0:
        return "mixed"
    if mean >= 0.20:
        return "positive"
    if mean <= -0.20:
        return "negative"
    return "neutral"


def _focus_context(*, title: str, excerpt: str | None, player_name: str) -> str:
    combined = " ".join(part for part in (title, excerpt or "") if part.strip())
    normalized_name = _normalize(player_name)
    selected = [
        segment.strip()
        for segment in _SENTENCE_SPLIT_RE.split(combined)
        if segment.strip() and normalized_name in _normalize(segment)
    ]
    return _SPACE_RE.sub(" ", " ".join(selected) if selected else combined).strip()


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _SPACE_RE.sub(" ", without_marks.casefold().replace("-", " ")).strip()


def _clamp_signed(value: float) -> float:
    return min(1.0, max(-1.0, value))


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def _clamp100(value: float) -> float:
    return min(100.0, max(0.0, value))
