from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.coverage_lab.engine import ProbeResult, compute_coverage
from football_intelligence.coverage_lab.product_coverage import (
    compute_product_coverage,
    compute_recent_season_coverage,
)
from football_intelligence.coverage_lab.provider_capabilities import ProviderCapability
from football_intelligence.coverage_lab.target_competitions import TargetCompetition
from football_intelligence.coverage_lab.target_metrics import TargetMetric

_NOW = datetime(2026, 8, 13, tzinfo=UTC)
_METRIC = TargetMetric("home_score", "match", "match", "test-v1", importance="critical")
_METRIC_KEY = (_METRIC.metric_name, _METRIC.granularity)
_COMPETITION = TargetCompetition(code="GER_BL1", name="Bundesliga", role="core")


def _provider() -> ProviderCapability:
    return ProviderCapability(
        provider_code="football-data-uk",
        freshness_role="current",
        requires_token=False,
        token_env_var=None,
        supported_metrics={_METRIC_KEY: "full"},
    )


def _coverage(*, is_current_period: bool) -> list:
    probe = ProbeResult(
        status="ok",
        sample_size=1,
        metric_observed_counts={_METRIC_KEY: 1},
        source_reference="ref",
        is_current_period=is_current_period,
    )
    return compute_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        providers=[_provider()],
        probe_results={(_provider().provider_code, _COMPETITION.code): probe},
        token_present_by_provider={},
        calculated_at=_NOW,
    )


def test_football_data_uk_fallback_to_older_season_does_not_increase_current_numerator() -> None:
    # Simulates the newer (true current) season file being unavailable, so
    # the job fell back to the older one -- real evidence, but the product
    # CURRENT numerator must stay 0, not be inflated by the fallback.
    fallback_coverage = _coverage(is_current_period=False)
    current_result = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=fallback_coverage,
        freshness_role="current",
    )
    assert current_result.numerator == 0
    assert current_result.denominator == 1


def test_football_data_uk_true_current_season_does_increase_current_numerator() -> None:
    # The contrasting case: the newer (true current) season file WAS found,
    # so this requirement genuinely satisfies current coverage.
    current_season_coverage = _coverage(is_current_period=True)
    current_result = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=current_season_coverage,
        freshness_role="current",
    )
    assert current_result.numerator == 1


def test_previous_season_evidence_remains_visible_in_recent_season_coverage() -> None:
    # Previous-season evidence is never discarded -- it shows up as its own
    # separate, honestly-labeled fraction instead of being folded into (or
    # dropped from) the current-coverage answer.
    fallback_coverage = _coverage(is_current_period=False)
    recent_result = compute_recent_season_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=fallback_coverage,
    )
    assert recent_result.numerator == 1
    assert recent_result.denominator == 1

    current_result = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=fallback_coverage,
        freshness_role="current",
    )
    assert current_result.numerator == 0


def test_denominator_is_unaffected_by_previous_season_state() -> None:
    # Adding the `previous_season` state must never change the fixed
    # target-catalog denominator (127 metrics x 10 competitions in the real
    # catalog since Block 16's Metric Catalog V2, was 48 x 10 before; 1 x 1
    # here) for either the current or recent-season view.
    for is_current_period in (True, False):
        coverage = _coverage(is_current_period=is_current_period)
        current_result = compute_product_coverage(
            target_metrics=[_METRIC],
            target_competitions=[_COMPETITION],
            coverage_entries=coverage,
            freshness_role="current",
        )
        recent_result = compute_recent_season_coverage(
            target_metrics=[_METRIC],
            target_competitions=[_COMPETITION],
            coverage_entries=coverage,
        )
        assert current_result.denominator == 1
        assert recent_result.denominator == 1
