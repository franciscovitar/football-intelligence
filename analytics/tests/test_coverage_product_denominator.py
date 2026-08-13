from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.coverage_lab.engine import compute_coverage
from football_intelligence.coverage_lab.product_coverage import compute_product_coverage
from football_intelligence.coverage_lab.provider_capabilities import PROVIDER_CAPABILITIES
from football_intelligence.coverage_lab.target_competitions import (
    TARGET_COMPETITION_COUNT,
    build_target_competitions,
)
from football_intelligence.coverage_lab.target_metrics import build_target_metric_catalog

_NOW = datetime(2026, 8, 13, tzinfo=UTC)


def test_adding_a_provider_does_not_change_the_product_denominator() -> None:
    # Block 15 added a 5th provider (football-data-uk) to PROVIDER_CAPABILITIES.
    # The product-level denominator must stay target_metrics x target_competitions
    # regardless of how many providers exist -- computed here with the full,
    # real provider list (5) vs a trimmed one (1), proving the denominator is
    # identical either way.
    target_metrics = build_target_metric_catalog()
    target_competitions = build_target_competitions()
    expected_denominator = len(target_metrics) * len(target_competitions)
    assert expected_denominator == 48 * 10

    full_coverage = compute_coverage(
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        providers=PROVIDER_CAPABILITIES,
        probe_results={},
        token_present_by_provider={},
        calculated_at=_NOW,
    )
    trimmed_coverage = compute_coverage(
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        providers=PROVIDER_CAPABILITIES[:1],
        probe_results={},
        token_present_by_provider={},
        calculated_at=_NOW,
    )

    full_current = compute_product_coverage(
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        coverage_entries=full_coverage,
        freshness_role="current",
    )
    trimmed_current = compute_product_coverage(
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        coverage_entries=trimmed_coverage,
        freshness_role="current",
    )

    assert full_current.denominator == trimmed_current.denominator == expected_denominator


def test_all_ten_target_competitions_remain_modeled_with_the_full_provider_list() -> None:
    target_metrics = build_target_metric_catalog()
    target_competitions = build_target_competitions()
    assert len(target_competitions) == TARGET_COMPETITION_COUNT == 10

    coverage = compute_coverage(
        target_metrics=target_metrics,
        target_competitions=target_competitions,
        providers=PROVIDER_CAPABILITIES,
        probe_results={},
        token_present_by_provider={},
        calculated_at=_NOW,
    )
    competition_codes = {entry.competition_code for entry in coverage}
    assert competition_codes == {competition.code for competition in target_competitions}
    assert len(competition_codes) == 10
