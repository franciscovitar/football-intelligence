"""Focused unit tests for `jobs.audit_wyscout_adapter.build_report()`'s
identity logic (Block 20D.2 review-fix pass).

These are pure unit tests over small synthetic `NormalizedObservation`
lists -- not a real-cache full-season audit run (see
`football-intelligence-audit-wyscout-adapter` for that). They exist to
prove the audit's own coverage/duplicate detection is genuinely
`metric_granularity`-aware, never inferred from `entity_type` -- the old
`(metric_name, entity_type)` projection could not distinguish
`saves`/`player_match` from `saves`/`goalkeeper_match` (both project to
`entity_type="player"`), so it could certify full adapter-safe coverage
even if one of the two granularities was never actually emitted.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.jobs import audit_wyscout_adapter
from football_intelligence.jobs.audit_wyscout_adapter import build_report
from football_intelligence.providers.wyscout_open_mapping import WyscoutMetricMapping

_NOW = datetime(2018, 1, 1, tzinfo=UTC)


def _obs(
    *,
    entity_type: str = "player",
    entity_source_id: str = "1001:11",
    metric_name: str = "saves",
    metric_granularity: str | None,
    value: object = 1,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code="wyscout-open",
        source_type="objective_structured",
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_source_id=entity_source_id,
        entity_identity_hints={"competition_external_id": "364", "season_label": "2017/18"},
        metric_name=metric_name,
        value=value,
        observed_at=_NOW,
        source_timestamp=_NOW,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version="test-v1",
        metric_granularity=metric_granularity,  # type: ignore[arg-type]
    )


def _check(report, name: str):  # type: ignore[no-untyped-def]
    return next(c for c in report.checks if c.name == name)


def test_a_player_match_saves_does_not_count_as_goalkeeper_match_evidence() -> None:
    report = build_report([_obs(metric_granularity="player_match")])
    assert ("saves", "goalkeeper_match") in report.safe_identities_with_zero_observations
    assert ("saves", "player_match") not in report.safe_identities_with_zero_observations


def test_b_both_exact_granularities_present_both_count() -> None:
    report = build_report(
        [
            _obs(metric_granularity="player_match"),
            _obs(metric_granularity="goalkeeper_match"),
        ]
    )
    assert ("saves", "player_match") not in report.safe_identities_with_zero_observations
    assert ("saves", "goalkeeper_match") not in report.safe_identities_with_zero_observations


def test_c_duplicate_conflict_identity_includes_metric_granularity() -> None:
    # Same source/entity_type/entity_source_id/metric_name, DIFFERENT
    # granularity, DIFFERENT value -- must never be reported as a
    # conflicting duplicate; these are two genuinely different facts.
    report = build_report(
        [
            _obs(metric_granularity="player_match", value=2),
            _obs(metric_granularity="goalkeeper_match", value=5),
        ]
    )
    assert report.duplicate_conflict_count == 0

    # A genuine conflict: identical identity INCLUDING granularity, but a
    # different value -- must still be caught.
    report_with_conflict = build_report(
        [
            _obs(metric_granularity="player_match", value=2),
            _obs(metric_granularity="player_match", value=3),
        ]
    )
    assert report_with_conflict.duplicate_conflict_count == 1


def test_d_missing_metric_granularity_is_reported_never_silently_projected() -> None:
    report = build_report([_obs(metric_granularity=None)])
    check = _check(report, "no_missing_metric_granularity")
    assert check.passed is False
    assert "1" in check.detail
    # A None-granularity observation must never be silently counted as
    # evidence for any specific catalog identity.
    assert ("saves", "player_match") in report.safe_identities_with_zero_observations
    assert ("saves", "goalkeeper_match") in report.safe_identities_with_zero_observations


def test_no_missing_metric_granularity_passes_when_all_observations_declare_it() -> None:
    report = build_report([_obs(metric_granularity="player_match")])
    check = _check(report, "no_missing_metric_granularity")
    assert check.passed is True


# ---------------------------------------------------------------------------
# Fix 1: all_adapter_safe_identities_observed must actually gate all_passed
# ---------------------------------------------------------------------------

_SMALL_SAFE_SET = (
    WyscoutMetricMapping(
        catalog_key="saves",
        catalog_granularity="player_match",
        classification="DIRECT",
        source_primitive="test",
        derivation_note="test",
    ),
    WyscoutMetricMapping(
        catalog_key="saves",
        catalog_granularity="goalkeeper_match",
        classification="DIRECT",
        source_primitive="test",
        derivation_note="test",
    ),
)


def test_one_missing_safe_identity_fails_the_coverage_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audit_wyscout_adapter, "adapter_safe_mappings", lambda: _SMALL_SAFE_SET)
    # Only player_match emitted -- goalkeeper_match is safe but missing.
    report = build_report([_obs(metric_granularity="player_match")])
    check = _check(report, "all_adapter_safe_identities_observed")
    assert check.passed is False
    assert ("saves", "goalkeeper_match") in report.safe_identities_with_zero_observations
    assert report.all_passed is False


def test_complete_exact_identity_coverage_passes_the_coverage_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audit_wyscout_adapter, "adapter_safe_mappings", lambda: _SMALL_SAFE_SET)
    report = build_report(
        [
            _obs(metric_granularity="player_match"),
            _obs(metric_granularity="goalkeeper_match"),
        ]
    )
    check = _check(report, "all_adapter_safe_identities_observed")
    assert check.passed is True
    assert report.safe_identities_with_zero_observations == ()


# ---------------------------------------------------------------------------
# Fix 2: unexpected identities must be exact-granularity aware
# ---------------------------------------------------------------------------


def test_saves_player_season_is_an_unexpected_exact_identity() -> None:
    # "saves" is never a safe identity at player_season granularity -- only
    # player_match/goalkeeper_match are. entity_type="player" is valid for
    # all three, so the coarser (metric_name, entity_type) check alone
    # cannot catch this.
    report = build_report([_obs(metric_granularity="player_season")])
    assert ("saves", "player_season") in report.unexpected_exact_identities
    check = _check(report, "no_unexpected_exact_identities_emitted")
    assert check.passed is False


def test_saves_player_match_is_not_an_unexpected_exact_identity() -> None:
    report = build_report([_obs(metric_granularity="player_match")])
    assert ("saves", "player_match") not in report.unexpected_exact_identities
    check = _check(report, "no_unexpected_exact_identities_emitted")
    assert check.passed is True


def test_saves_goalkeeper_match_is_not_an_unexpected_exact_identity() -> None:
    report = build_report([_obs(metric_granularity="goalkeeper_match")])
    assert ("saves", "goalkeeper_match") not in report.unexpected_exact_identities
    check = _check(report, "no_unexpected_exact_identities_emitted")
    assert check.passed is True


def test_missing_granularity_is_never_inferred_into_an_exact_identity() -> None:
    # A None-granularity observation must be caught by
    # no_missing_metric_granularity, never silently treated as evidence for
    # (or against) any specific exact identity.
    report = build_report([_obs(metric_granularity=None)])
    assert report.unexpected_exact_identities == ()
    missing_check = _check(report, "no_missing_metric_granularity")
    assert missing_check.passed is False
    unexpected_check = _check(report, "no_unexpected_exact_identities_emitted")
    assert unexpected_check.passed is True
    assert report.all_passed is False
