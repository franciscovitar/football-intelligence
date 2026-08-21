"""Block 20D.4: provider-pair + semantic-version-scoped comparability
policy registry."""

from __future__ import annotations

import pytest

from football_intelligence.data_mesh.adapters.statsbomb_open import (
    SEMANTIC_VERSION as STATSBOMB_SEMANTIC_VERSION,
)
from football_intelligence.data_mesh.adapters.statsbomb_open import (
    SOURCE_CODE as STATSBOMB_SOURCE_CODE,
)
from football_intelligence.data_mesh.adapters.wyscout_open import (
    SEMANTIC_VERSION as WYSCOUT_SEMANTIC_VERSION,
)
from football_intelligence.data_mesh.adapters.wyscout_open import SOURCE_CODE as WYSCOUT_SOURCE_CODE
from football_intelligence.data_mesh.comparability_policy import (
    MetricComparabilityPolicy,
    SourceRef,
    canonical_source_refs,
    comparability_policy,
)

_WYSCOUT = SourceRef(source_code=WYSCOUT_SOURCE_CODE, semantic_version=WYSCOUT_SEMANTIC_VERSION)
_STATSBOMB = SourceRef(
    source_code=STATSBOMB_SOURCE_CODE, semantic_version=STATSBOMB_SEMANTIC_VERSION
)


def test_canonical_source_refs_is_deterministic_regardless_of_input_order() -> None:
    forward = canonical_source_refs(_WYSCOUT, _STATSBOMB)
    reversed_order = canonical_source_refs(_STATSBOMB, _WYSCOUT)
    assert forward == reversed_order
    assert forward[0].source_code < forward[1].source_code


def test_exact_policy_lookup_for_the_certified_pair() -> None:
    policy = comparability_policy(
        _WYSCOUT, _STATSBOMB, metric_name="home_score", metric_granularity="match"
    )
    assert policy is not None
    assert policy.comparison_mode == "exact"
    assert policy.rationale.strip() != ""


def test_lookup_is_order_independent() -> None:
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


def test_changed_adapter_semantic_version_no_longer_matches() -> None:
    bumped_wyscout = SourceRef(
        source_code=WYSCOUT_SOURCE_CODE, semantic_version="wyscout-open-v0.99"
    )
    policy = comparability_policy(
        bumped_wyscout, _STATSBOMB, metric_name="home_score", metric_granularity="match"
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
