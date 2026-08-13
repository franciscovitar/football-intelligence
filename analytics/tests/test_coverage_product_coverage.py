from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.coverage_lab.models import CoverageEntry, CoverageState, FreshnessRole
from football_intelligence.coverage_lab.product_coverage import compute_product_coverage
from football_intelligence.coverage_lab.target_competitions import TargetCompetition
from football_intelligence.coverage_lab.target_metrics import TargetMetric

_NOW = datetime(2026, 8, 13, tzinfo=UTC)

_METRIC = TargetMetric(
    metric_name="home_score",
    granularity="match",
    domain="match",
    semantic_version="test-v1",
    importance="critical",
)
_OTHER_METRIC = TargetMetric(
    metric_name="away_score", granularity="match", domain="match", semantic_version="test-v1"
)
_COMPETITION = TargetCompetition(code="GER_BL1", name="Bundesliga", role="core")


def _entry(
    *,
    provider_code: str,
    freshness_role: FreshnessRole,
    state: CoverageState,
    metric: TargetMetric = _METRIC,
    competition: TargetCompetition = _COMPETITION,
) -> CoverageEntry:
    return CoverageEntry(
        provider_code=provider_code,
        competition_code=competition.code,
        metric_name=metric.metric_name,
        granularity=metric.granularity,
        entity_type="match",
        freshness_role=freshness_role,
        state=state,
        sample_size=1,
        observed_count=1,
        source_reference=None,
        last_checked_at=_NOW,
    )


def test_one_provider_covers_metric_another_unsupported_product_metric_is_covered() -> None:
    entries = [
        _entry(provider_code="thesportsdb", freshness_role="current", state="current_available"),
        _entry(provider_code="openligadb", freshness_role="current", state="unsupported"),
    ]
    result = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=entries,
        freshness_role="current",
    )
    assert result.numerator == 1
    assert result.denominator == 1
    assert result.gap_keys == ()
    assert result.critical_gap_keys == ()


def test_one_provider_covers_metric_another_token_required_product_metric_is_covered() -> None:
    entries = [
        _entry(provider_code="thesportsdb", freshness_role="current", state="current_available"),
        _entry(provider_code="football-data-org", freshness_role="current", state="token_required"),
    ]
    result = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=entries,
        freshness_role="current",
    )
    assert result.numerator == 1
    assert result.denominator == 1


def test_adding_unsupported_current_provider_never_changes_numerator_or_denominator() -> None:
    baseline_entries = [
        _entry(provider_code="thesportsdb", freshness_role="current", state="current_available")
    ]
    baseline = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=baseline_entries,
        freshness_role="current",
    )

    extended_entries = [
        *baseline_entries,
        _entry(provider_code="brand-new-provider", freshness_role="current", state="unsupported"),
    ]
    extended = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=extended_entries,
        freshness_role="current",
    )

    assert extended.numerator == baseline.numerator == 1
    assert extended.denominator == baseline.denominator == 1


def test_no_current_provider_covers_metric_is_a_product_level_critical_gap() -> None:
    entries = [
        _entry(provider_code="thesportsdb", freshness_role="current", state="missing"),
        _entry(provider_code="openligadb", freshness_role="current", state="unsupported"),
    ]
    result = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=entries,
        freshness_role="current",
    )
    assert result.numerator == 0
    assert result.gap_keys == ("GER_BL1:match:home_score",)
    assert result.critical_gap_keys == ("GER_BL1:match:home_score",)


def test_historical_only_provider_does_not_satisfy_current_gap() -> None:
    entries = [
        _entry(
            provider_code="statsbomb-open", freshness_role="historical", state="historical_only"
        ),
    ]
    result = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=entries,
        freshness_role="current",
    )
    assert result.numerator == 0
    assert result.gap_keys == ("GER_BL1:match:home_score",)

    historical_result = compute_product_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        coverage_entries=entries,
        freshness_role="historical",
    )
    assert historical_result.numerator == 1


def test_denominator_is_target_metrics_times_competitions_independent_of_provider_count() -> None:
    metrics = [_METRIC, _OTHER_METRIC]
    competitions = [
        _COMPETITION,
        TargetCompetition(code="ENG_PL", name="Premier League", role="core"),
    ]
    many_provider_entries = [
        _entry(
            provider_code=f"provider-{index}",
            metric=metric,
            competition=competition,
            freshness_role="current",
            state="unsupported",
        )
        for index in range(5)
        for metric in metrics
        for competition in competitions
    ]

    result = compute_product_coverage(
        target_metrics=metrics,
        target_competitions=competitions,
        coverage_entries=many_provider_entries,
        freshness_role="current",
    )

    assert result.denominator == len(metrics) * len(competitions) == 4
