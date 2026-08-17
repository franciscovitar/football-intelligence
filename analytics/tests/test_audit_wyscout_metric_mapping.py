from __future__ import annotations

import csv
import inspect
import json
import zipfile
from pathlib import Path

import pytest

from football_intelligence.jobs import audit_wyscout_metric_mapping as audit_job
from football_intelligence.jobs.audit_wyscout_metric_mapping import (
    _EXPECTED_TAG_LABELS,
    WyscoutMappingAuditError,
    _find_cached_file,
    load_cached_source,
    run_audit,
    verify_source_primitives,
)

_ALL_EXPECTED_LABELS = dict(_EXPECTED_TAG_LABELS)


def _by_name(checks: tuple, name: str):  # type: ignore[type-arg]
    for check in checks:
        if check.name == name:
            return check
    raise AssertionError(f"no check named {name!r}")


# -- Tag-id semantic lookup ---------------------------------------------------


def test_correct_tag_labels_all_pass() -> None:
    checks = verify_source_primitives(
        matches_payload=[], events_payload=[], tag_labels=_ALL_EXPECTED_LABELS
    )
    for tag_id in _ALL_EXPECTED_LABELS:
        check = _by_name(checks, f"tag_label_{tag_id}")
        assert check.passed, check.detail


def test_wrong_tag_label_is_flagged_not_silently_accepted() -> None:
    corrupted = dict(_ALL_EXPECTED_LABELS)
    corrupted[1801] = "not accurate"  # deliberately swapped with 1802's real label
    checks = verify_source_primitives(matches_payload=[], events_payload=[], tag_labels=corrupted)
    check = _by_name(checks, "tag_label_1801")
    assert check.passed is False


def test_missing_tag_label_is_flagged_not_silently_accepted() -> None:
    missing = {k: v for k, v in _ALL_EXPECTED_LABELS.items() if k != 1801}
    checks = verify_source_primitives(matches_payload=[], events_payload=[], tag_labels=missing)
    check = _by_name(checks, "tag_label_1801")
    assert check.passed is False
    assert "None" in check.detail


# -- Unknown source event/tag is never silently mapped -----------------------


def test_missing_required_event_name_is_flagged() -> None:
    events = [{"eventName": "Pass", "subEventName": "Simple pass", "tags": []}]
    checks = verify_source_primitives(
        matches_payload=[], events_payload=events, tag_labels=_ALL_EXPECTED_LABELS
    )
    check = _by_name(checks, "eventName_vocabulary")
    assert check.passed is False
    assert "Shot" in check.detail


def test_card_tag_outside_foul_event_is_flagged() -> None:
    events = [
        {"eventName": "Pass", "subEventName": "Simple pass", "tags": [{"id": 1702}]},
    ]
    checks = verify_source_primitives(
        matches_payload=[], events_payload=events, tag_labels=_ALL_EXPECTED_LABELS
    )
    check = _by_name(checks, "card_tags_never_appear_outside_foul_events")
    assert check.passed is False
    assert "1" in check.detail


def test_clearance_tag_actually_observed_is_flagged() -> None:
    events = [
        {"eventName": "Others on the ball", "subEventName": "Clearance", "tags": [{"id": 1501}]}
    ]
    checks = verify_source_primitives(
        matches_payload=[], events_payload=events, tag_labels=_ALL_EXPECTED_LABELS
    )
    check = _by_name(checks, "clearance_tag_never_observed")
    assert check.passed is False


def test_unexpected_roster_entry_key_is_flagged() -> None:
    matches = [
        {
            "wyId": 1,
            "teamsData": {
                "100": {
                    "formation": {
                        "lineup": [{"playerId": 1, "position": "GK"}],  # unexpected 'position' key
                        "bench": [],
                        "substitutions": [],
                    }
                }
            },
        }
    ]
    checks = verify_source_primitives(
        matches_payload=matches, events_payload=[], tag_labels=_ALL_EXPECTED_LABELS
    )
    check = _by_name(checks, "roster_entries_never_carry_position_captain_or_shirt_number")
    assert check.passed is False
    assert "position" in check.detail


def test_unexpected_formation_shape_key_is_flagged() -> None:
    matches = [
        {
            "wyId": 1,
            "teamsData": {
                "100": {
                    "formation": {
                        "lineup": [],
                        "bench": [],
                        "substitutions": [],
                        "shape": "4-4-2",  # unexpected key
                    }
                }
            },
        }
    ]
    checks = verify_source_primitives(
        matches_payload=matches, events_payload=[], tag_labels=_ALL_EXPECTED_LABELS
    )
    check = _by_name(checks, "formation_never_carries_a_shape_label")
    assert check.passed is False
    assert "shape" in check.detail


# -- Local cache loading (offline, deterministic) -----------------------------


def test_find_cached_file_raises_clear_error_when_nothing_matches(tmp_path: Path) -> None:
    with pytest.raises(WyscoutMappingAuditError, match="run the Block 20B.1 probe"):
        _find_cached_file(tmp_path, "*matches_England.json")


def test_find_cached_file_raises_clear_error_when_ambiguous(tmp_path: Path) -> None:
    (tmp_path / "a_players.json").write_text("[]", encoding="utf-8")
    (tmp_path / "b_players.json").write_text("[]", encoding="utf-8")
    with pytest.raises(WyscoutMappingAuditError, match="ambiguous"):
        _find_cached_file(tmp_path, "*players.json")


def test_load_cached_source_raises_when_cache_dir_is_empty(tmp_path: Path) -> None:
    with pytest.raises(WyscoutMappingAuditError):
        load_cached_source(tmp_path)


def _write_synthetic_cache(cache_dir: Path) -> None:
    extracted_matches = cache_dir / "extracted" / "1_matches"
    extracted_events = cache_dir / "extracted" / "2_events"
    extracted_matches.mkdir(parents=True)
    extracted_events.mkdir(parents=True)

    matches_payload = [
        {
            "wyId": 1,
            "teamsData": {
                "100": {
                    "score": 1,
                    "formation": {
                        "lineup": [
                            {
                                "playerId": 11,
                                "ownGoals": "0",
                                "redCards": "0",
                                "goals": "0",
                                "yellowCards": "0",
                            }
                        ],
                        "bench": [],
                        "substitutions": [],
                    },
                },
                "200": {
                    "score": 0,
                    "formation": {"lineup": [], "bench": [], "substitutions": "null"},
                },
            },
        }
    ]
    events_payload = [
        {
            "eventName": "Pass",
            "subEventName": "Simple pass",
            "playerId": 11,
            "tags": [{"id": 1801}],
        },
        {
            "eventName": "Shot",
            "subEventName": "Shot",
            "playerId": 11,
            "tags": [{"id": 1801}, {"id": 101}],
        },
        {"eventName": "Duel", "subEventName": "Air duel", "playerId": 11, "tags": [{"id": 703}]},
        {"eventName": "Foul", "subEventName": "Foul", "playerId": 11, "tags": [{"id": 1702}]},
        {"eventName": "Free Kick", "subEventName": "Penalty", "playerId": 11, "tags": []},
        {
            "eventName": "Save attempt",
            "subEventName": "Save attempt",
            "playerId": 11,
            "tags": [{"id": 1801}],
        },
        {"eventName": "Offside", "subEventName": "", "playerId": 11, "tags": []},
        {
            "eventName": "Others on the ball",
            "subEventName": "Clearance",
            "playerId": 11,
            "tags": [],
        },
    ]
    (extracted_matches / "matches_England.json").write_text(
        json.dumps(matches_payload), encoding="utf-8"
    )
    (extracted_events / "events_England.json").write_text(
        json.dumps(events_payload), encoding="utf-8"
    )

    with open(cache_dir / "1_tags2name.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Tag", "Label", "Description"])
        for tag_id, label in _ALL_EXPECTED_LABELS.items():
            writer.writerow([tag_id, label, label])


def test_run_audit_loads_and_evaluates_synthetic_cache_offline(tmp_path: Path) -> None:
    _write_synthetic_cache(tmp_path)

    report = run_audit(cache_dir=tmp_path)

    assert len(report.checks) > 0
    assert sum(report.classification_counts.values()) > 0
    # Small synthetic sample can't match the real ENG_PL 2017/18 exact
    # counts, so the report is correctly NOT all-passed -- but the
    # structural/vocabulary checks that don't depend on scale still pass.
    assert _by_name(report.checks, "eventName_vocabulary").passed
    assert _by_name(report.checks, "tag_label_1801").passed
    assert _by_name(report.checks, "match_count").passed is False


def test_run_audit_extracts_from_zip_when_only_the_archive_is_cached(tmp_path: Path) -> None:
    matches_payload = [{"wyId": 1, "teamsData": {}}]
    zip_path = tmp_path / "1_matches.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("matches_England.json", json.dumps(matches_payload))
        archive.writestr("matches_Spain.json", json.dumps([]))

    events_dir = tmp_path / "extracted" / "2_events"
    events_dir.mkdir(parents=True)
    (events_dir / "events_England.json").write_text("[]", encoding="utf-8")

    with open(tmp_path / "1_tags2name.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Tag", "Label", "Description"])

    matches, events, tags = load_cached_source(tmp_path)
    assert matches == matches_payload
    assert events == []
    assert tags == {}


# -- No DB / network dependency -----------------------------------------------


def test_audit_job_has_no_database_or_network_dependency() -> None:
    source = inspect.getsource(audit_job)
    assert "DATABASE_URL" not in source
    assert "psycopg" not in source
    assert "football_intelligence.db" not in source
    assert "urlopen" not in source
    assert "WyscoutOpenDataClient" not in source
