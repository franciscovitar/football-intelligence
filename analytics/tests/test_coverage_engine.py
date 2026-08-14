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
_METRIC_KEY = (_METRIC.metric_name, _METRIC.granularity)
_COMPETITION = TargetCompetition(code="GER_BL1", name="Bundesliga", role="core")


def _current_provider(
    *, requires_token: bool = False, token_env_var: str | None = None
) -> ProviderCapability:
    return ProviderCapability(
        provider_code="thesportsdb",
        freshness_role="current",
        requires_token=requires_token,
        token_env_var=token_env_var,
        supported_metrics={_METRIC_KEY: "full"},
    )


def _historical_provider() -> ProviderCapability:
    return ProviderCapability(
        provider_code="statsbomb-open",
        freshness_role="historical",
        requires_token=False,
        token_env_var=None,
        supported_metrics={_METRIC_KEY: "full"},
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
        status="ok",
        sample_size=5,
        metric_observed_counts={_METRIC_KEY: 5},
        source_reference="ref",
    )
    entry = _compute(_current_provider(), probe)
    assert entry.state == "current_available"
    assert satisfies_current(entry.state)


def test_historical_only_source_never_satisfies_current_query() -> None:
    probe = ProbeResult(
        status="ok",
        sample_size=34,
        metric_observed_counts={_METRIC_KEY: 34},
        source_reference="ref",
    )
    entry = _compute(_historical_provider(), probe)
    assert entry.state == "historical_only"
    assert not satisfies_current(entry.state)


def test_partial_coverage_stays_partial_not_rounded_up() -> None:
    probe = ProbeResult(
        status="ok",
        sample_size=10,
        metric_observed_counts={_METRIC_KEY: 4},
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
        metric_observed_counts={_METRIC_KEY: 2},
        metric_sample_sizes={_METRIC_KEY: 2},
        source_reference="ref",
    )
    entry = _compute(_historical_provider(), probe)
    assert entry.state == "historical_only"
    assert entry.sample_size == 2


def test_current_provider_with_current_period_evidence_satisfies_current() -> None:
    # A `current`-role provider whose probe verified the TRUE current
    # season/period (is_current_period=True, the default) can reach
    # current_available -- the ordinary, unremarkable case.
    probe = ProbeResult(
        status="ok",
        sample_size=5,
        metric_observed_counts={_METRIC_KEY: 5},
        source_reference="ref",
        is_current_period=True,
    )
    entry = _compute(_current_provider(), probe)
    assert entry.state == "current_available"
    assert satisfies_current(entry.state)


def test_current_provider_with_previous_season_evidence_never_satisfies_current() -> None:
    # Real, complete evidence -- but verified only for the latest completed
    # season (e.g. a season file that had not been published yet, so the
    # job fell back to the prior one), not the true current period. Must
    # report `previous_season`, never `current_available`, no matter how
    # complete the sample is.
    probe = ProbeResult(
        status="ok",
        sample_size=5,
        metric_observed_counts={_METRIC_KEY: 5},
        source_reference="ref",
        is_current_period=False,
    )
    entry = _compute(_current_provider(), probe)
    assert entry.state == "previous_season"
    assert not satisfies_current(entry.state)


def test_previous_season_state_reported_even_when_probe_is_only_partial() -> None:
    # Temporal freshness (current vs previous period) and completeness
    # (full vs partial sample) are orthogonal -- previous-season evidence
    # stays `previous_season` regardless of how much of that prior sample
    # was actually observed, never silently promoted to plain `partial`.
    probe = ProbeResult(
        status="ok",
        sample_size=10,
        metric_observed_counts={_METRIC_KEY: 4},
        source_reference="ref",
        is_current_period=False,
    )
    entry = _compute(_current_provider(), probe)
    assert entry.state == "previous_season"


def test_historical_provider_is_never_affected_by_is_current_period() -> None:
    # `is_current_period` only matters for `current`-role providers.
    # StatsBomb's historical role must still map to historical_only exactly
    # as before, whatever `is_current_period` happens to be set to.
    probe = ProbeResult(
        status="ok",
        sample_size=5,
        metric_observed_counts={_METRIC_KEY: 5},
        source_reference="ref",
        is_current_period=False,
    )
    entry = _compute(_historical_provider(), probe)
    assert entry.state == "historical_only"
    assert not satisfies_current(entry.state)


def test_metric_name_at_two_granularities_does_not_collide() -> None:
    # "shots_total" legitimately exists at both "team" and "player_match"
    # granularity. A provider that only supports the team-level one must
    # never be credited with the player-level one, and vice versa.
    team_metric = TargetMetric("shots_total", "team", "team_stats", "test-v1")
    player_metric = TargetMetric("shots_total", "player_match", "player_stats", "test-v1")
    provider = ProviderCapability(
        provider_code="thesportsdb",
        freshness_role="current",
        requires_token=False,
        token_env_var=None,
        supported_metrics={("shots_total", "team"): "full"},
    )
    probe = ProbeResult(
        status="ok",
        sample_size=2,
        metric_observed_counts={("shots_total", "team"): 2, ("shots_total", "player_match"): 2},
        source_reference="ref",
    )
    entries = compute_coverage(
        target_metrics=[team_metric, player_metric],
        target_competitions=[_COMPETITION],
        providers=[provider],
        probe_results={(provider.provider_code, _COMPETITION.code): probe},
        token_present_by_provider={},
        calculated_at=_NOW,
    )
    by_granularity = {entry.granularity: entry.state for entry in entries}
    assert by_granularity["team"] == "current_available"
    assert by_granularity["player_match"] == "unsupported"


def test_lineup_capped_reliability_stays_partial_even_when_fully_observed() -> None:
    # TheSportsDB's Free lineup endpoint is permanently capped at 5 rows, so
    # `provider_capabilities` marks it "partial" reliability regardless of
    # any single probe's ratio -- even a probe where observed_count equals
    # sample_size (this bounded sample was fully captured) must never be
    # reported as `current_available`, because a 5-row sample can never
    # prove a complete lineup.
    metric = TargetMetric("listed_position", "player_appearance", "appearance", "test-v1")
    provider = ProviderCapability(
        provider_code="thesportsdb",
        freshness_role="current",
        requires_token=False,
        token_env_var=None,
        supported_metrics={("listed_position", "player_appearance"): "partial"},
    )
    probe = ProbeResult(
        status="ok",
        sample_size=5,
        metric_observed_counts={("listed_position", "player_appearance"): 5},
        source_reference="ref",
    )
    entries = compute_coverage(
        target_metrics=[metric],
        target_competitions=[_COMPETITION],
        providers=[provider],
        probe_results={(provider.provider_code, _COMPETITION.code): probe},
        token_present_by_provider={},
        calculated_at=_NOW,
    )
    assert entries[0].state == "partial"
    assert not satisfies_current(entries[0].state)


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
