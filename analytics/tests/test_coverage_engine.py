from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.coverage_lab.engine import ProbeResult, compute_coverage
from football_intelligence.coverage_lab.models import satisfies_current
from football_intelligence.coverage_lab.provider_capabilities import ProviderCapability
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
_COMPETITION = TargetCompetition(code="GER_BL1", name="Bundesliga", role="core")


def _current_provider(
    *, requires_token: bool = False, token_env_var: str | None = None
) -> ProviderCapability:
    return ProviderCapability(
        provider_code="thesportsdb",
        freshness_role="current",
        requires_token=requires_token,
        token_env_var=token_env_var,
        supported_metrics={"home_score": "full"},
    )


def _historical_provider() -> ProviderCapability:
    return ProviderCapability(
        provider_code="statsbomb-open",
        freshness_role="historical",
        requires_token=False,
        token_env_var=None,
        supported_metrics={"home_score": "full"},
    )


def _compute(provider: ProviderCapability, probe: ProbeResult | None, *, has_token: bool = False):
    probe_results = {} if probe is None else {(provider.provider_code, _COMPETITION.code): probe}
    return compute_coverage(
        target_metrics=[_METRIC],
        target_competitions=[_COMPETITION],
        providers=[provider],
        probe_results=probe_results,
        token_present_by_provider={provider.provider_code: has_token},
        calculated_at=_NOW,
    )[0]


def test_zero_observed_is_missing_not_current_available() -> None:
    # A source that was genuinely probed but returned zero matches must
    # never be reported as covering the metric.
    probe = ProbeResult(
        status="ok", sample_size=5, metric_observed_counts={}, source_reference="ref"
    )
    entry = _compute(_current_provider(), probe)
    assert entry.state == "missing"
    assert entry.observed_count == 0


def test_full_current_coverage_is_current_available() -> None:
    probe = ProbeResult(
        status="ok", sample_size=5, metric_observed_counts={"home_score": 5}, source_reference="ref"
    )
    entry = _compute(_current_provider(), probe)
    assert entry.state == "current_available"
    assert satisfies_current(entry.state)


def test_historical_only_source_never_satisfies_current_query() -> None:
    probe = ProbeResult(
        status="ok",
        sample_size=34,
        metric_observed_counts={"home_score": 34},
        source_reference="ref",
    )
    entry = _compute(_historical_provider(), probe)
    assert entry.state == "historical_only"
    assert not satisfies_current(entry.state)


def test_partial_coverage_stays_partial_not_rounded_up() -> None:
    probe = ProbeResult(
        status="ok",
        sample_size=10,
        metric_observed_counts={"home_score": 4},
        source_reference="ref",
    )
    entry = _compute(_current_provider(), probe)
    assert entry.state == "partial"
    assert not satisfies_current(entry.state)


def test_token_required_when_provider_needs_token_and_none_present() -> None:
    provider = _current_provider(requires_token=True, token_env_var="SOME_TOKEN")
    entry = _compute(provider, probe=None, has_token=False)
    assert entry.state == "token_required"


def test_token_required_is_not_a_failure_state_distinct_from_missing() -> None:
    provider = _current_provider(requires_token=True, token_env_var="SOME_TOKEN")
    without_token = _compute(provider, probe=None, has_token=False)
    with_token_but_zero = _compute(
        provider,
        ProbeResult(status="ok", sample_size=1, metric_observed_counts={}, source_reference="ref"),
        has_token=True,
    )
    assert without_token.state == "token_required"
    assert with_token_but_zero.state == "missing"
    assert without_token.state != with_token_but_zero.state


def test_not_probed_when_no_probe_result_exists() -> None:
    entry = _compute(_current_provider(), probe=None)
    assert entry.state == "not_probed"


def test_unsupported_metric_never_reported_as_missing() -> None:
    provider = ProviderCapability(
        provider_code="openligadb",
        freshness_role="current",
        requires_token=False,
        token_env_var=None,
        supported_metrics={},  # does not structurally support "home_score"
    )
    entry = _compute(provider, probe=None)
    assert entry.state == "unsupported"


def test_probe_error_is_not_probed_not_missing() -> None:
    probe = ProbeResult(
        status="error",
        sample_size=0,
        metric_observed_counts={},
        source_reference=None,
        notes="boom",
    )
    entry = _compute(_current_provider(), probe)
    assert entry.state == "not_probed"


def test_per_metric_sample_size_overrides_probe_level_default() -> None:
    # A deep event metric can be fully covered for its own small bounded
    # sample even while the ProbeResult-level sample_size reflects a much
    # larger, unrelated denominator (e.g. a full published season used for
    # match-level facts sharing the same probe).
    probe = ProbeResult(
        status="ok",
        sample_size=306,
        metric_observed_counts={"home_score": 2},
        metric_sample_sizes={"home_score": 2},
        source_reference="ref",
    )
    entry = _compute(_historical_provider(), probe)
    assert entry.state == "historical_only"
    assert entry.sample_size == 2


def test_compute_coverage_covers_every_provider_competition_metric_combination() -> None:
    metrics = [_METRIC, TargetMetric("away_score", "match", "match", "test-v1")]
    competitions = [
        _COMPETITION,
        TargetCompetition(code="ENG_PL", name="Premier League", role="core"),
    ]
    providers = [_current_provider()]
    entries = compute_coverage(
        target_metrics=metrics,
        target_competitions=competitions,
        providers=providers,
        probe_results={},
        token_present_by_provider={},
        calculated_at=_NOW,
    )
    assert len(entries) == len(metrics) * len(competitions) * len(providers)
