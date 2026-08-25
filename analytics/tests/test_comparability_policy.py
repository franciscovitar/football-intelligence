"""Block 20D.4: provider-pair + semantic-version-scoped comparability
policy registry.

The certified `wyscout-open`/`statsbomb-open` version strings used below
are deliberately hard-coded LITERALS, never imported from either adapter's
live `SEMANTIC_VERSION` constant. This is the whole point of the review
fix this file protects: the registry's own pinned versions
(`comparability_policy.WYSCOUT_CERTIFIED_POLICY_VERSION`/
`STATSBOMB_CERTIFIED_POLICY_VERSION`) must never move just because an
adapter is bumped, so this test file's own expectations must not move
either -- if both the registry and this file derived their expectations
from the same live import, a future adapter bump could silently keep every
assertion here green while the real, underlying contract broke. Hard-
coding both independently means a real regression is caught by an actual
mismatch, not hidden by two sides drifting together."""

from __future__ import annotations

import pytest

from football_intelligence.data_mesh.adapters.statsbomb_open import (
    SEMANTIC_VERSION as STATSBOMB_LIVE_SEMANTIC_VERSION,
)
from football_intelligence.data_mesh.adapters.statsbomb_open import (
    SOURCE_CODE as STATSBOMB_SOURCE_CODE,
)
from football_intelligence.data_mesh.adapters.wyscout_open import (
    SEMANTIC_VERSION as WYSCOUT_LIVE_SEMANTIC_VERSION,
)
from football_intelligence.data_mesh.adapters.wyscout_open import SOURCE_CODE as WYSCOUT_SOURCE_CODE
from football_intelligence.data_mesh.comparability_policy import (
    STATSBOMB_CERTIFIED_POLICY_VERSION,
    WYSCOUT_CERTIFIED_POLICY_VERSION,
    MetricComparabilityPolicy,
    SourceRef,
    canonical_source_refs,
    comparability_policy,
)

# Hard-coded literals -- the exact certified versions the real ESP_LL
# 2017/18 comparability evidence was gathered against. Deliberately NOT
# `comparability_policy.WYSCOUT_CERTIFIED_POLICY_VERSION` and NOT either
# adapter's live `SEMANTIC_VERSION` -- see module docstring.
_CERTIFIED_WYSCOUT_VERSION = "wyscout-open-v0.4"
_CERTIFIED_STATSBOMB_VERSION = "statsbomb-open-v0.4"

_WYSCOUT = SourceRef(source_code=WYSCOUT_SOURCE_CODE, semantic_version=_CERTIFIED_WYSCOUT_VERSION)
_STATSBOMB = SourceRef(
    source_code=STATSBOMB_SOURCE_CODE, semantic_version=_CERTIFIED_STATSBOMB_VERSION
)


def test_registry_pins_match_the_hard_coded_certified_literals_here() -> None:
    # Guards against the registry's own pins silently drifting away from
    # what this test file independently believes is certified.
    assert WYSCOUT_CERTIFIED_POLICY_VERSION == _CERTIFIED_WYSCOUT_VERSION
    assert STATSBOMB_CERTIFIED_POLICY_VERSION == _CERTIFIED_STATSBOMB_VERSION


def test_live_adapter_versions_currently_match_the_certified_pins() -> None:
    # Diagnostic-only (explicitly permitted): today, the live adapter
    # SEMANTIC_VERSION constants happen to equal the certified pins. This
    # is NOT what the registry itself relies on (it never imports these
    # live constants) -- it is an early-warning check that fails the
    # moment someone bumps an adapter without a deliberate re-
    # certification pass, so the drift is caught here rather than
    # discovered only via silent methodology_pending fallback in
    # production.
    assert WYSCOUT_LIVE_SEMANTIC_VERSION == WYSCOUT_CERTIFIED_POLICY_VERSION
    assert STATSBOMB_LIVE_SEMANTIC_VERSION == STATSBOMB_CERTIFIED_POLICY_VERSION


def test_canonical_source_refs_is_deterministic_regardless_of_input_order() -> None:
    forward = canonical_source_refs(_WYSCOUT, _STATSBOMB)
    reversed_order = canonical_source_refs(_STATSBOMB, _WYSCOUT)
    assert forward == reversed_order
    assert forward[0].source_code < forward[1].source_code


def test_certified_pair_exact_policy_resolves_for_home_score() -> None:
    # wyscout-open-v0.4 + statsbomb-open-v0.4 -> current policies match.
    policy = comparability_policy(
        _WYSCOUT, _STATSBOMB, metric_name="home_score", metric_granularity="match"
    )
    assert policy is not None
    assert policy.comparison_mode == "exact"
    assert policy.rationale.strip() != ""


def test_reversed_certified_order_still_matches() -> None:
    # Passing (StatsBomb, Wyscout) instead of (Wyscout, StatsBomb) must
    # resolve to the identical policy -- lookup canonicalizes internally.
    forward = comparability_policy(
        _WYSCOUT, _STATSBOMB, metric_name="home_score", metric_granularity="match"
    )
    reversed_lookup = comparability_policy(
        _STATSBOMB, _WYSCOUT, metric_name="home_score", metric_granularity="match"
    )
    assert forward is not None
    assert forward == reversed_lookup


def test_future_wyscout_version_bump_no_longer_matches() -> None:
    # wyscout-open-v0.5 + statsbomb-open-v0.4 (real, certified StatsBomb
    # side, only Wyscout bumped) -> no old policy match, methodology_pending
    # territory (this module returns None; the orchestrator maps that to
    # methodology_pending).
    future_wyscout = SourceRef(
        source_code=WYSCOUT_SOURCE_CODE, semantic_version="wyscout-open-v0.5"
    )
    policy = comparability_policy(
        future_wyscout, _STATSBOMB, metric_name="home_score", metric_granularity="match"
    )
    assert policy is None


def test_future_statsbomb_version_bump_no_longer_matches() -> None:
    # wyscout-open-v0.4 (real, certified Wyscout side) + statsbomb-open-v0.5
    # -> no old policy match.
    future_statsbomb = SourceRef(
        source_code=STATSBOMB_SOURCE_CODE, semantic_version="statsbomb-open-v0.5"
    )
    policy = comparability_policy(
        _WYSCOUT, future_statsbomb, metric_name="home_score", metric_granularity="match"
    )
    assert policy is None


def test_both_sources_future_bumped_no_longer_matches() -> None:
    # wyscout-open-v0.5 + statsbomb-open-v0.5 -> no old policy match.
    future_wyscout = SourceRef(
        source_code=WYSCOUT_SOURCE_CODE, semantic_version="wyscout-open-v0.5"
    )
    future_statsbomb = SourceRef(
        source_code=STATSBOMB_SOURCE_CODE, semantic_version="statsbomb-open-v0.5"
    )
    policy = comparability_policy(
        future_wyscout, future_statsbomb, metric_name="home_score", metric_granularity="match"
    )
    assert policy is None


def test_lookup_is_order_independent_for_a_second_identity() -> None:
    forward = comparability_policy(
        _WYSCOUT, _STATSBOMB, metric_name="goals", metric_granularity="player_match"
    )
    reversed_lookup = comparability_policy(
        _STATSBOMB, _WYSCOUT, metric_name="goals", metric_granularity="player_match"
    )
    assert forward is not None
    assert forward == reversed_lookup


def test_explicit_not_comparable_lookup() -> None:
    policy = comparability_policy(
        _WYSCOUT, _STATSBOMB, metric_name="passes_total", metric_granularity="team_match"
    )
    assert policy is not None
    assert policy.comparison_mode == "not_comparable"


def test_absent_identity_is_none_never_exact() -> None:
    policy = comparability_policy(
        _WYSCOUT, _STATSBOMB, metric_name="assists", metric_granularity="player_match"
    )
    # `assists` was empirically found to have 25 real-agreement candidates
    # deferred to 20D.5 -- it must NOT have been silently seeded as exact.
    assert policy is None


def test_unknown_provider_pair_is_none() -> None:
    unknown_source = SourceRef(source_code="some-future-provider", semantic_version="v1.0")
    policy = comparability_policy(
        _WYSCOUT, unknown_source, metric_name="home_score", metric_granularity="match"
    )
    assert policy is None


def test_policy_requires_exactly_two_distinct_source_refs() -> None:
    with pytest.raises(ValueError):
        MetricComparabilityPolicy(
            source_refs=(_WYSCOUT, _WYSCOUT),
            metric_name="home_score",
            metric_granularity="match",
            comparison_mode="exact",
            rationale="invalid: same source twice",
        )


def test_policy_requires_canonical_order() -> None:
    canonical = canonical_source_refs(_WYSCOUT, _STATSBOMB)
    non_canonical = (canonical[1], canonical[0])
    with pytest.raises(ValueError):
        MetricComparabilityPolicy(
            source_refs=non_canonical,
            metric_name="home_score",
            metric_granularity="match",
            comparison_mode="exact",
            rationale="invalid: not canonically ordered",
        )


def test_policy_requires_non_blank_rationale() -> None:
    with pytest.raises(ValueError):
        MetricComparabilityPolicy(
            source_refs=canonical_source_refs(_WYSCOUT, _STATSBOMB),
            metric_name="home_score",
            metric_granularity="match",
            comparison_mode="exact",
            rationale="   ",
        )
