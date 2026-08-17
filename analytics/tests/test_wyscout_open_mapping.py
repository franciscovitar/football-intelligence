from __future__ import annotations

import inspect

import pytest

from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2
from football_intelligence.providers import wyscout_open_mapping
from football_intelligence.providers.wyscout_open_mapping import (
    WYSCOUT_METRIC_MAPPINGS,
    WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS,
    WyscoutMetricMapping,
    WyscoutProviderOutOfScopeMetric,
    adapter_safe_mappings,
    derivable_methodology_pending_mappings,
    derivable_ready_mappings,
    mappings_by_classification,
    validate_full_catalog_coverage,
    validate_mappings,
)

_CATALOG_IDENTITIES = {(metric.key, metric.granularity) for metric in METRIC_CATALOG_V2}
_VALID_CLASSIFICATIONS = {"DIRECT", "DERIVABLE", "REQUIRES_MODEL", "UNSUPPORTED", "AMBIGUOUS"}


def _find(key: str, granularity: str) -> WyscoutMetricMapping:
    for mapping in WYSCOUT_METRIC_MAPPINGS:
        if mapping.catalog_key == key and mapping.catalog_granularity == granularity:
            return mapping
    raise AssertionError(f"no mapping for ({key!r}, {granularity!r})")


# -- Identity/catalog integrity -------------------------------------------


def test_every_mapping_identity_exists_in_metric_catalog_v2() -> None:
    for mapping in WYSCOUT_METRIC_MAPPINGS:
        assert (mapping.catalog_key, mapping.catalog_granularity) in _CATALOG_IDENTITIES


def test_no_duplicate_mapping_identities() -> None:
    identities = [(m.catalog_key, m.catalog_granularity) for m in WYSCOUT_METRIC_MAPPINGS]
    assert len(identities) == len(set(identities))


def test_validate_mappings_rejects_duplicate_identity() -> None:
    duplicated = (
        WyscoutMetricMapping(
            catalog_key="goals",
            catalog_granularity="player_match",
            classification="DIRECT",
            source_primitive="x",
            derivation_note="y",
        ),
        WyscoutMetricMapping(
            catalog_key="goals",
            catalog_granularity="player_match",
            classification="DIRECT",
            source_primitive="x",
            derivation_note="y",
        ),
    )
    with pytest.raises(AssertionError, match="duplicate"):
        validate_mappings(duplicated)


def test_validate_mappings_rejects_identity_absent_from_catalog() -> None:
    invented = (
        WyscoutMetricMapping(
            catalog_key="this_metric_does_not_exist",
            catalog_granularity="player_match",
            classification="DIRECT",
            source_primitive="x",
            derivation_note="y",
        ),
    )
    with pytest.raises(AssertionError, match="absent from METRIC_CATALOG_V2"):
        validate_mappings(invented)


def test_validate_mappings_accepts_a_real_unique_mapping() -> None:
    valid = (
        WyscoutMetricMapping(
            catalog_key="goals",
            catalog_granularity="player_match",
            classification="DIRECT",
            source_primitive="x",
            derivation_note="y",
        ),
    )
    validate_mappings(valid)  # must not raise


def test_every_mapping_has_a_valid_classification() -> None:
    for mapping in WYSCOUT_METRIC_MAPPINGS:
        assert mapping.classification in _VALID_CLASSIFICATIONS


def test_mappings_by_classification_partitions_all_entries() -> None:
    total = sum(len(mappings_by_classification(c)) for c in _VALID_CLASSIFICATIONS)
    assert total == len(WYSCOUT_METRIC_MAPPINGS)


# -- Direct metric classification -------------------------------------------


@pytest.mark.parametrize(
    ("key", "granularity"),
    [
        ("goals", "player_match"),
        ("assists", "player_match"),
        ("shots_total", "player_match"),
        ("shots_on_target", "player_match"),
        ("passes_total", "player_match"),
        ("passes_accurate", "player_match"),
        ("key_passes", "player_match"),
        ("duels_total", "player_match"),
        ("duels_won", "player_match"),
        ("interceptions", "player_match"),
        ("clearances", "player_match"),
        ("yellow_cards", "player_match"),
        ("saves", "player_match"),
        ("corners", "team_match"),
        ("goals_for", "team_match"),
    ],
)
def test_direct_metrics_are_classified_direct(key: str, granularity: str) -> None:
    assert _find(key, granularity).classification == "DIRECT"


# -- Derivable metric classification -----------------------------------------


@pytest.mark.parametrize(
    ("key", "granularity"),
    [
        ("pass_completion_pct", "player_match"),
        ("goal_contributions", "player_match"),
        ("duel_win_pct", "player_match"),
        ("progressive_passes", "player_match"),
        ("minutes", "player_appearance"),
        ("shots_on_target", "team_match"),
    ],
)
def test_derivable_metrics_are_classified_derivable(key: str, granularity: str) -> None:
    assert _find(key, granularity).classification == "DERIVABLE"


def test_derivable_spatial_metrics_disclose_pending_methodology() -> None:
    spatial_keys = [
        ("progressive_passes", "player_match"),
        ("passes_into_box", "player_match"),
        ("shots_inside_box", "player_match"),
    ]
    for key, granularity in spatial_keys:
        mapping = _find(key, granularity)
        assert mapping.classification == "DERIVABLE"
        assert "pending" in mapping.derivation_note.lower()


# -- xG must be REQUIRES_MODEL, never a direct shot mapping -----------------


@pytest.mark.parametrize(
    ("key", "granularity"),
    [
        ("advanced.xg", "player_match"),
        ("npxg", "player_match"),
        ("xa", "player_match"),
        ("xg", "team_match"),
        ("xga", "team_match"),
    ],
)
def test_expected_goals_family_requires_model(key: str, granularity: str) -> None:
    assert _find(key, granularity).classification == "REQUIRES_MODEL"


def test_no_expected_goals_metric_is_ever_classified_direct_or_derivable() -> None:
    for mapping in WYSCOUT_METRIC_MAPPINGS:
        if "xg" in mapping.catalog_key.lower() or mapping.catalog_key in {"xa", "npxga"}:
            assert mapping.classification in {"REQUIRES_MODEL", "UNSUPPORTED", "AMBIGUOUS"}, (
                f"{mapping.catalog_key} ({mapping.catalog_granularity}) must never be "
                "DIRECT/DERIVABLE from raw Wyscout shot events"
            )


# -- Unsupported metrics stay unsupported ------------------------------------


@pytest.mark.parametrize(
    ("key", "granularity"),
    [
        ("captain", "player_appearance"),
        ("shirt_number", "player_appearance"),
        ("listed_position", "player_appearance"),
        ("blocks", "player_match"),
        ("fouls_drawn", "player_match"),
        ("carries", "player_match"),
        ("formation", "team_match"),
    ],
)
def test_unsupported_metrics_are_classified_unsupported(key: str, granularity: str) -> None:
    assert _find(key, granularity).classification == "UNSUPPORTED"


# -- Ambiguous metrics are never silently forced into DIRECT/DERIVABLE ------


@pytest.mark.parametrize(
    ("key", "granularity"),
    [
        ("tackles", "player_match"),
        ("dribbles_attempted", "player_match"),
        ("dispossessed", "player_match"),
        ("big_chances", "player_match"),
    ],
)
def test_ambiguous_metrics_are_never_forced_into_direct_or_derivable(
    key: str, granularity: str
) -> None:
    assert _find(key, granularity).classification == "AMBIGUOUS"


# -- No DB / network dependency -----------------------------------------------


def test_mapping_module_has_no_database_or_network_dependency() -> None:
    source = inspect.getsource(wyscout_open_mapping)
    assert "DATABASE_URL" not in source
    assert "psycopg" not in source
    assert "football_intelligence.db" not in source
    assert "urlopen" not in source
    assert "requests" not in source


# -- Full 194/194 catalog accounting (Block 20B.2a final pass) --------------


def test_provider_mapping_and_out_of_scope_together_account_for_every_catalog_identity() -> None:
    mapped_ids = {(m.catalog_key, m.catalog_granularity) for m in WYSCOUT_METRIC_MAPPINGS}
    out_of_scope_ids = {
        (m.catalog_key, m.catalog_granularity) for m in WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS
    }
    assert mapped_ids | out_of_scope_ids == _CATALOG_IDENTITIES


def test_provider_mapping_and_out_of_scope_are_disjoint() -> None:
    mapped_ids = {(m.catalog_key, m.catalog_granularity) for m in WYSCOUT_METRIC_MAPPINGS}
    out_of_scope_ids = {
        (m.catalog_key, m.catalog_granularity) for m in WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS
    }
    assert mapped_ids.isdisjoint(out_of_scope_ids)


def test_provider_mapping_totals_190() -> None:
    assert len(WYSCOUT_METRIC_MAPPINGS) == 190


def test_provider_out_of_scope_totals_4() -> None:
    assert len(WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS) == 4


def test_catalog_totals_194() -> None:
    assert len(_CATALOG_IDENTITIES) == 194


@pytest.mark.parametrize(
    ("classification", "expected_count"),
    [
        ("DIRECT", 43),
        ("DERIVABLE", 67),
        ("REQUIRES_MODEL", 35),
        ("UNSUPPORTED", 25),
        ("AMBIGUOUS", 20),
    ],
)
def test_classification_totals_match_final_accounting(
    classification: str, expected_count: int
) -> None:
    assert len(mappings_by_classification(classification)) == expected_count  # type: ignore[arg-type]


def test_derivable_ready_and_pending_totals_match_final_accounting() -> None:
    assert len(derivable_ready_mappings()) == 34
    assert len(derivable_methodology_pending_mappings()) == 33
    assert len(derivable_ready_mappings()) + len(derivable_methodology_pending_mappings()) == len(
        mappings_by_classification("DERIVABLE")
    )


def test_adapter_safe_subset_totals_77() -> None:
    safe = adapter_safe_mappings()
    assert len(safe) == 77
    assert all(m.classification == "DIRECT" or not m.methodology_pending for m in safe)
    assert all(m.classification in {"DIRECT", "DERIVABLE"} for m in safe)


def test_adapter_safe_subset_never_includes_methodology_pending_entries() -> None:
    safe_ids = {(m.catalog_key, m.catalog_granularity) for m in adapter_safe_mappings()}
    pending_ids = {
        (m.catalog_key, m.catalog_granularity) for m in derivable_methodology_pending_mappings()
    }
    assert safe_ids.isdisjoint(pending_ids)


@pytest.mark.parametrize(
    "key",
    ["home_score", "away_score", "home_away", "status", "kickoff_at", "round_name", "venue_name"],
)
def test_new_match_identities_exist_and_are_direct(key: str) -> None:
    mapping = _find(key, "match")
    assert mapping.classification == "DIRECT"


@pytest.mark.parametrize(
    ("key", "granularity"),
    [
        ("league_strength", "competition"),
        ("team_strength_elo", "team"),
        ("opponent_strength", "team_match"),
        ("minutes_confidence", "player_season"),
    ],
)
def test_internal_engine_identities_are_not_falsely_mapped_as_provider_metrics(
    key: str, granularity: str
) -> None:
    mapped_ids = {(m.catalog_key, m.catalog_granularity) for m in WYSCOUT_METRIC_MAPPINGS}
    assert (key, granularity) not in mapped_ids
    out_of_scope_ids = {
        (m.catalog_key, m.catalog_granularity) for m in WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS
    }
    assert (key, granularity) in out_of_scope_ids


def test_out_of_scope_entries_carry_a_concise_non_blank_reason() -> None:
    for entry in WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS:
        assert entry.reason.strip()


def test_validate_full_catalog_coverage_detects_a_missing_identity() -> None:
    incomplete_mappings = tuple(m for m in WYSCOUT_METRIC_MAPPINGS if m.catalog_key != "home_score")
    with pytest.raises(AssertionError, match="not accounted for"):
        validate_full_catalog_coverage(incomplete_mappings, WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS)


def test_validate_full_catalog_coverage_detects_overlap_between_mapping_and_out_of_scope() -> None:
    conflicting_out_of_scope = (
        WyscoutProviderOutOfScopeMetric(
            catalog_key="goals",
            catalog_granularity="player_match",
            reason="deliberately conflicting for this test",
        ),
    )
    with pytest.raises(AssertionError, match="both"):
        validate_full_catalog_coverage(WYSCOUT_METRIC_MAPPINGS, conflicting_out_of_scope)


def test_new_derivable_pending_team_identities_exist() -> None:
    for key in ("formation_stability", "lineup_stability"):
        mapping = _find(key, "team")
        assert mapping.classification == "DERIVABLE"
        assert mapping.methodology_pending is True


def test_new_requires_model_identities_exist() -> None:
    for key in (
        "non_penalty_goals_minus_npxg",
        "pressure_success_pct",
        "successful_pressures",
        "xa_per90",
    ):
        mapping = _find(key, "player_match")
        assert mapping.classification == "REQUIRES_MODEL"


def test_new_unsupported_identity_exists() -> None:
    mapping = _find("positional_peer_group", "player_season")
    assert mapping.classification == "UNSUPPORTED"


def test_methodology_pending_only_set_on_derivable_entries() -> None:
    for mapping in WYSCOUT_METRIC_MAPPINGS:
        if mapping.methodology_pending:
            assert mapping.classification == "DERIVABLE"
