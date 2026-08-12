from __future__ import annotations

from datetime import UTC, datetime, timedelta

from football_intelligence.rating_intelligence.engine import (
    calculate_rating_intelligence,
    score_evidence_stance,
)
from football_intelligence.rating_intelligence.models import (
    PlayerRatingInput,
    RatingEvidence,
)

NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)


def _evidence(
    evidence_id: int,
    *,
    source_id: int,
    title: str,
    player_id: int = 1,
    days_old: int = 0,
) -> RatingEvidence:
    timestamp = NOW - timedelta(days=days_old)
    return RatingEvidence(
        evidence_id=evidence_id,
        player_id=player_id,
        source_id=source_id,
        source_code=f"source-{source_id}",
        source_kind="media",
        title=title,
        excerpt=None,
        matched_text="Test Forward",
        published_at=timestamp,
        discovered_at=timestamp,
    )


def _performance(score: float = 82.0, confidence: float = 0.90) -> list[PlayerRatingInput]:
    return [
        PlayerRatingInput(
            player_id=1,
            player_name="Test Forward",
            scope_key="core:2026",
            role="forward",
            stable_score=score,
            stable_confidence=confidence,
        )
    ]


def test_stance_scoring_uses_player_focused_football_phrases() -> None:
    positive = score_evidence_stance(
        _evidence(1, source_id=1, title="Test Forward earns praise after superb display"),
        now=NOW,
    )
    negative = score_evidence_stance(
        _evidence(2, source_id=1, title="Test Forward struggles after costly error"),
        now=NOW,
    )

    assert positive.stance_score > 0.9
    assert negative.stance_score < -0.9
    assert positive.stance_confidence > 0.5
    assert negative.stance_confidence > 0.5


def test_rating_marks_strong_performance_against_negative_perception_underrated() -> None:
    evidence = [
        _evidence(1, source_id=1, title="Test Forward struggles in poor display"),
        _evidence(2, source_id=1, title="Test Forward criticised after costly error"),
        _evidence(3, source_id=2, title="Test Forward under fire after blunder"),
        _evidence(4, source_id=2, title="Disappointing run continues for Test Forward"),
    ]

    result = calculate_rating_intelligence(_performance(), evidence, calculated_at=NOW)
    assert len(result) == 1
    snapshot = result[0]
    assert snapshot.rating_signal == "underrated"
    assert snapshot.perception_score is not None and snapshot.perception_score < 20
    assert snapshot.rating_gap is not None and snapshot.rating_gap > 50
    assert snapshot.scored_source_count == 2


def test_single_source_cannot_produce_overrated_or_underrated_label() -> None:
    evidence = [
        _evidence(1, source_id=1, title="Test Forward struggles in poor display"),
        _evidence(2, source_id=1, title="Test Forward under fire after blunder"),
        _evidence(3, source_id=1, title="Test Forward criticised after costly error"),
        _evidence(4, source_id=1, title="Disappointing run continues for Test Forward"),
    ]

    snapshot = calculate_rating_intelligence(
        _performance(),
        evidence,
        calculated_at=NOW,
    )[0]
    assert snapshot.rating_signal == "insufficient_evidence"
    assert snapshot.scored_source_count == 1


def test_opposing_sources_surface_polarization_instead_of_forcing_rating() -> None:
    evidence = [
        _evidence(1, source_id=1, title="Test Forward earns praise after superb display"),
        _evidence(2, source_id=1, title="Outstanding Test Forward shines again"),
        _evidence(3, source_id=2, title="Test Forward struggles in poor display"),
        _evidence(4, source_id=2, title="Test Forward under fire after blunder"),
    ]

    snapshot = calculate_rating_intelligence(
        _performance(),
        evidence,
        calculated_at=NOW,
    )[0]
    assert snapshot.rating_signal == "polarized"
    assert snapshot.polarization_score is not None
    assert snapshot.polarization_score >= 60
    assert snapshot.consensus_score is not None
    assert snapshot.consensus_score < 30


def test_source_balancing_prevents_article_volume_from_dominating_direction() -> None:
    evidence = [
        _evidence(1, source_id=1, title="Test Forward earns praise after superb display"),
        _evidence(2, source_id=1, title="Outstanding Test Forward shines again"),
        _evidence(3, source_id=1, title="Brilliant Test Forward impresses"),
        _evidence(4, source_id=1, title="Excellent Test Forward earns praise"),
        _evidence(5, source_id=2, title="Test Forward under fire after blunder"),
    ]

    snapshot = calculate_rating_intelligence(
        _performance(score=50),
        evidence,
        calculated_at=NOW,
    )[0]
    assert snapshot.perception_score is not None
    assert 40 <= snapshot.perception_score <= 60
