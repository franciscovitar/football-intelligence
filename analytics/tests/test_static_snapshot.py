from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from football_intelligence.ingestion.static_snapshot import (
    StaticSnapshotManifestError,
    static_snapshot_manifest_from_dict,
    verify_static_snapshot_files,
)


def _manifest_payload(*, sha256: str, byte_size: int | None = None) -> dict[str, object]:
    return {
        "snapshot_id": "example-2025-26-v1",
        "source_code": "example-static",
        "acquired_at": "2026-08-23T22:30:00-03:00",
        "source_reference": "https://example.test/dataset",
        "competition_codes": ["ENG_PL"],
        "season_labels": ["2025/26"],
        "data_grains": ["player_profile", "player_season"],
        "files": [
            {
                "path": "players.csv",
                "sha256": sha256,
                "byte_size": byte_size,
            }
        ],
        "notes": "Test-only static snapshot.",
    }


def test_manifest_verifies_cached_bytes(tmp_path: Path) -> None:
    payload = b"player_id,name\n1,Example Player\n"
    path = tmp_path / "players.csv"
    path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    manifest = static_snapshot_manifest_from_dict(
        _manifest_payload(sha256=digest, byte_size=len(payload))
    )
    report = verify_static_snapshot_files(manifest, base_dir=tmp_path)

    assert report.passed
    assert report.files[0].exists
    assert report.files[0].checksum_matches
    assert report.files[0].byte_size_matches is True


def test_manifest_rejects_path_traversal() -> None:
    payload = _manifest_payload(sha256="a" * 64)
    files = payload["files"]
    assert isinstance(files, list)
    assert isinstance(files[0], dict)
    files[0]["path"] = "../players.csv"

    with pytest.raises(StaticSnapshotManifestError, match="safe relative path"):
        static_snapshot_manifest_from_dict(payload)


def test_manifest_rejects_timezone_naive_acquisition_time() -> None:
    payload = _manifest_payload(sha256="a" * 64)
    payload["acquired_at"] = "2026-08-23T22:30:00"

    with pytest.raises(StaticSnapshotManifestError, match="timezone-aware"):
        static_snapshot_manifest_from_dict(payload)


def test_checksum_mismatch_fails_verification(tmp_path: Path) -> None:
    path = tmp_path / "players.csv"
    path.write_text("changed", encoding="utf-8")
    manifest = static_snapshot_manifest_from_dict(_manifest_payload(sha256="a" * 64))

    report = verify_static_snapshot_files(manifest, base_dir=tmp_path)

    assert not report.passed
    assert report.files[0].exists
    assert not report.files[0].checksum_matches


def test_manifest_requires_canonical_sorted_scope_values() -> None:
    payload = _manifest_payload(sha256="a" * 64)
    payload["competition_codes"] = ["ESP_LL", "ENG_PL"]

    with pytest.raises(StaticSnapshotManifestError, match="canonical ascending order"):
        static_snapshot_manifest_from_dict(payload)
