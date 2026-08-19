"""Focused unit tests for `jobs.audit_statsbomb_adapter.build_report()`'s
identity logic (Block 20D.2 review-fix pass).

These are pure unit tests over small synthetic `NormalizedObservation`
lists (with an empty `bundles` list -- the participation-universe and
independent-event-recount checks that consume `bundles` are not what these
tests target) -- not a real-cache full-season audit run (see
`football-intelligence-audit-statsbomb-adapter` for that). They exist to
prove the audit's own coverage/duplicate detection is genuinely
`metric_granularity`-aware, never inferred from `entity_type` -- the old
`(metric_name, entity_type)` projection could not distinguish
`saves`/`player_match` from `saves`/`goalkeeper_match` (both project to
`entity_type="player"`), so it could certify full adapter-safe coverage
even if one of the two granularities was never actually emitted.
"""

from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.jobs.audit_statsbomb_adapter import build_report

_NOW = datetime(2015, 8, 8, tzinfo=UTC)


def _obs(
    *,
    entity_type: str = "player",
    entity_source_id: str = "9001:101",
    metric_name: str = "saves",
    metric_granularity: str | None,
    value: object = 1,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code="statsbomb-open",
        source_type="objective_structured",
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_source_id=entity_source_id,
        entity_identity_hints={"competition_external_id": "2", "season_label": "2015/16"},
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
    report = build_report([_obs(metric_granularity="player_match")], bundles=[])
    assert ("saves", "goalkeeper_match") in report.safe_identities_with_zero_observations
    assert ("saves", "player_match") not in report.safe_identities_with_zero_observations


def test_b_both_exact_granularities_present_both_count() -> None:
    report = build_report(
        [
            _obs(metric_granularity="player_match"),
            _obs(metric_granularity="goalkeeper_match"),
        ],
        bundles=[],
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
        ],
        bundles=[],
    )
    assert report.duplicate_conflict_count == 0

    # A genuine conflict: identical identity INCLUDING granularity, but a
    # different value -- must still be caught.
    report_with_conflict = build_report(
        [
            _obs(metric_granularity="player_match", value=2),
            _obs(metric_granularity="player_match", value=3),
        ],
        bundles=[],
    )
    assert report_with_conflict.duplicate_conflict_count == 1


def test_d_missing_metric_granularity_is_reported_never_silently_projected() -> None:
    report = build_report([_obs(metric_granularity=None)], bundles=[])
    check = _check(report, "no_missing_metric_granularity")
    assert check.passed is False
    assert "1" in check.detail
    # A None-granularity observation must never be silently counted as
    # evidence for any specific catalog identity.
    assert ("saves", "player_match") in report.safe_identities_with_zero_observations
    assert ("saves", "goalkeeper_match") in report.safe_identities_with_zero_observations


def test_no_missing_metric_granularity_passes_when_all_observations_declare_it() -> None:
    report = build_report([_obs(metric_granularity="player_match")], bundles=[])
    check = _check(report, "no_missing_metric_granularity")
    assert check.passed is True


def test_saves_full_type_set_check_reflects_only_player_match_not_both_granularities() -> None:
    # A real goalkeeper's save is now genuinely emitted at BOTH
    # player_match and goalkeeper_match (same real event, correctly
    # dual-scoped). The audit's own internal save total (checked against
    # the independently-recomputed `saves_full_type_set` from raw events,
    # bundles=[] here so both are 0) must reflect only ONE count per real
    # save -- if it summed every "saves" observation regardless of
    # granularity, adding a second (goalkeeper_match) observation with a
    # DIFFERENT value here would silently corrupt the total instead of
    # being ignored.
    with_only_player_match = build_report(
        [_obs(metric_granularity="player_match", value=0)], bundles=[]
    )
    with_both_granularities = build_report(
        [
            _obs(metric_granularity="player_match", value=0),
            # A goalkeeper_match observation with a deliberately different
            # value than player_match's -- if the audit's save total still
            # included goalkeeper_match, this would change the outcome of
            # the check below; it must not.
            _obs(metric_granularity="goalkeeper_match", value=99),
        ],
        bundles=[],
    )
    check_only_player_match = _check(
        with_only_player_match, "saves_use_full_certified_type_set_not_old_undercount"
    )
    check_with_both = _check(
        with_both_granularities, "saves_use_full_certified_type_set_not_old_undercount"
    )
    assert check_only_player_match.detail == check_with_both.detail
