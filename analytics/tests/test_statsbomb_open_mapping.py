from __future__ import annotations

import pytest

from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2
from football_intelligence.providers.statsbomb_open_mapping import (
    STATSBOMB_METRIC_MAPPINGS,
    STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS,
    StatsBombMetricMapping,
    adapter_safe_mappings,
    derivable_methodology_pending_mappings,
    derivable_ready_mappings,
    mappings_by_classification,
    validate_full_catalog_coverage,
    validate_mappings,
)

_CATALOG_IDENTITIES = {(m.key, m.granularity) for m in METRIC_CATALOG_V2}


def test_all_194_catalog_identities_are_accounted_for() -> None:
    mapped = {(m.catalog_key, m.catalog_granularity) for m in STATSBOMB_METRIC_MAPPINGS}
    out_of_scope = {
        (m.catalog_key, m.catalog_granularity) for m in STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS
    }
    assert len(_CATALOG_IDENTITIES) == 194
    assert mapped | out_of_scope == _CATALOG_IDENTITIES


def test_mapping_and_out_of_scope_are_disjoint() -> None:
    mapped = {(m.catalog_key, m.catalog_granularity) for m in STATSBOMB_METRIC_MAPPINGS}
    out_of_scope = {
        (m.catalog_key, m.catalog_granularity) for m in STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS
    }
    assert mapped.isdisjoint(out_of_scope)


def test_every_mapping_identity_exists_in_the_real_metric_catalog() -> None:
    for mapping in STATSBOMB_METRIC_MAPPINGS:
        identity = (mapping.catalog_key, mapping.catalog_granularity)
        assert identity in _CATALOG_IDENTITIES, f"{identity} is not a real catalog identity"


def test_duplicate_mapping_identity_is_rejected() -> None:
    duplicated = STATSBOMB_METRIC_MAPPINGS + (STATSBOMB_METRIC_MAPPINGS[0],)
    with pytest.raises(AssertionError, match="duplicate"):
        validate_mappings(duplicated)


def test_out_of_scope_entry_also_present_in_mappings_is_rejected() -> None:
    conflicting = StatsBombMetricMapping(
        catalog_key=STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS[0].catalog_key,
        catalog_granularity=STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS[0].catalog_granularity,
        classification="DIRECT",
        source_primitive="n/a",
        derivation_note="n/a",
    )
    with pytest.raises(AssertionError, match="both"):
        validate_full_catalog_coverage(
            STATSBOMB_METRIC_MAPPINGS + (conflicting,), STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS
        )


def test_missing_identity_is_rejected() -> None:
    truncated = STATSBOMB_METRIC_MAPPINGS[1:]
    with pytest.raises(AssertionError, match="not accounted for"):
        validate_full_catalog_coverage(truncated, STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS)


def test_adapter_safe_subset_is_only_direct_and_derivable_ready() -> None:
    safe = adapter_safe_mappings()
    assert len(safe) > 0
    for mapping in safe:
        assert mapping.classification in ("DIRECT", "DERIVABLE")
        if mapping.classification == "DERIVABLE":
            assert mapping.methodology_pending is False


def test_adapter_safe_subset_excludes_pending_and_unsafe_classifications() -> None:
    safe_identities = {(m.catalog_key, m.catalog_granularity) for m in adapter_safe_mappings()}
    for mapping in derivable_methodology_pending_mappings():
        assert (mapping.catalog_key, mapping.catalog_granularity) not in safe_identities
    for mapping in mappings_by_classification("REQUIRES_MODEL"):
        assert (mapping.catalog_key, mapping.catalog_granularity) not in safe_identities
    for mapping in mappings_by_classification("UNSUPPORTED"):
        assert (mapping.catalog_key, mapping.catalog_granularity) not in safe_identities
    for mapping in mappings_by_classification("AMBIGUOUS"):
        assert (mapping.catalog_key, mapping.catalog_granularity) not in safe_identities


def test_provider_out_of_scope_metrics_excluded_from_adapter_safe_subset() -> None:
    safe_identities = {(m.catalog_key, m.catalog_granularity) for m in adapter_safe_mappings()}
    for entry in STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS:
        assert (entry.catalog_key, entry.catalog_granularity) not in safe_identities


def test_derivable_ready_and_pending_partition_all_derivable_entries() -> None:
    derivable = mappings_by_classification("DERIVABLE")
    ready = derivable_ready_mappings()
    pending = derivable_methodology_pending_mappings()
    assert len(ready) + len(pending) == len(derivable)
    assert set(ready).isdisjoint(set(pending))


def test_methodology_pending_only_meaningful_for_derivable() -> None:
    for mapping in STATSBOMB_METRIC_MAPPINGS:
        if mapping.methodology_pending:
            assert mapping.classification == "DERIVABLE"


def _find(catalog_key: str, granularity: str) -> StatsBombMetricMapping:
    for mapping in STATSBOMB_METRIC_MAPPINGS:
        if mapping.catalog_key == catalog_key and mapping.catalog_granularity == granularity:
            return mapping
    raise AssertionError(f"no mapping for ({catalog_key}, {granularity})")


def test_native_xg_is_classified_direct_and_labelled_provider_native() -> None:
    mapping = _find("advanced.xg", "player_match")
    assert mapping.classification == "DIRECT"
    assert "provider-native" in mapping.derivation_note.lower() or (
        "provider-native" in mapping.caveats.lower()
    )
    assert "statsbomb_xg" in mapping.source_primitive


def test_xa_is_not_derived_since_no_native_xa_field_exists() -> None:
    mapping = _find("xa", "player_match")
    assert mapping.classification == "REQUIRES_MODEL"


def test_assists_is_direct_from_native_goal_assist_field() -> None:
    mapping = _find("assists", "player_match")
    assert mapping.classification == "DIRECT"
    assert "goal_assist" in mapping.source_primitive


def test_cards_use_the_lineup_file_not_foul_committed_alone() -> None:
    yellow = _find("yellow_cards", "player_match")
    assert yellow.classification == "DIRECT"
    assert "lineups" in yellow.source_primitive
    assert "Bad Behaviour" in yellow.caveats or "bad behaviour" in yellow.caveats.lower()


def test_saves_classification_uses_the_full_verified_saved_type_set() -> None:
    mapping = _find("saves", "player_match")
    assert mapping.classification == "DIRECT"
    assert "Shot Saved Off Target" in mapping.source_primitive
    assert "Penalty Saved" in mapping.source_primitive


def test_minutes_is_methodology_pending_not_derivable_ready() -> None:
    mapping = _find("minutes", "player_appearance")
    assert mapping.classification == "DERIVABLE"
    assert mapping.methodology_pending is True


def test_minutes_is_excluded_from_adapter_safe_subset() -> None:
    safe_identities = {(m.catalog_key, m.catalog_granularity) for m in adapter_safe_mappings()}
    assert ("minutes", "player_appearance") not in safe_identities


def test_carries_is_direct_unlike_wyscouts_unsupported_classification() -> None:
    mapping = _find("carries", "player_match")
    assert mapping.classification == "DIRECT"


def test_pressures_is_direct_unlike_wyscouts_requires_model_classification() -> None:
    mapping = _find("pressures", "player_match")
    assert mapping.classification == "DIRECT"


def test_provider_out_of_scope_metrics_are_provider_agnostic_engine_outputs() -> None:
    keys = {m.catalog_key for m in STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS}
    assert keys == {
        "league_strength",
        "team_strength_elo",
        "opponent_strength",
        "minutes_confidence",
    }


def test_classification_counts_are_stable_regression() -> None:
    # Regression guard: catches accidental reclassification drift. Update
    # deliberately (with a documented reason) if the underlying evidence
    # changes, never silently.
    assert len(mappings_by_classification("DIRECT")) == 65
    assert len(mappings_by_classification("DERIVABLE")) == 93
    assert len(mappings_by_classification("REQUIRES_MODEL")) == 15
    assert len(mappings_by_classification("UNSUPPORTED")) == 12
    assert len(mappings_by_classification("AMBIGUOUS")) == 5
    assert len(derivable_ready_mappings()) == 45
    assert len(derivable_methodology_pending_mappings()) == 48
    assert len(adapter_safe_mappings()) == 110
