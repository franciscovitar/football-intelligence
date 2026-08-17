from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from football_intelligence.providers.statsbomb_open_manifest import (
    EXPOSURE_POLICY_INTERNAL_ONLY,
    ROLE_HISTORICAL_DEEP,
    CachedFileRecord,
    SourceSnapshotManifest,
    read_manifest,
    write_manifest,
)


def _sample_manifest() -> SourceSnapshotManifest:
    return SourceSnapshotManifest(
        provider="StatsBomb Open Data",
        upstream_repository="https://github.com/statsbomb/open-data",
        pinned_commit_sha="b0bc9f22dd77c206ddedc1d742893b3bbe64baec",
        competition_id=2,
        season_id=27,
        competition_name="Premier League",
        season_name="2015/2016",
        role=ROLE_HISTORICAL_DEEP,
        exposure_policy=EXPOSURE_POLICY_INTERNAL_ONLY,
        fetched_at=datetime(2026, 8, 17, tzinfo=UTC),
        expected_match_count=380,
        files=(CachedFileRecord(api_path="competitions.json", sha256="abc123", byte_size=34887),),
    )


def test_write_then_read_manifest_round_trips(tmp_path: Path) -> None:
    manifest = _sample_manifest()
    path = write_manifest(tmp_path, manifest)
    assert path.exists()

    loaded = read_manifest(tmp_path)
    assert loaded is not None
    assert loaded.pinned_commit_sha == manifest.pinned_commit_sha
    assert loaded.competition_id == 2
    assert loaded.season_id == 27
    assert loaded.expected_match_count == 380
    assert loaded.exposure_policy == EXPOSURE_POLICY_INTERNAL_ONLY
    assert loaded.role == ROLE_HISTORICAL_DEEP
    assert len(loaded.files) == 1
    assert loaded.files[0].api_path == "competitions.json"


def test_read_manifest_returns_none_when_absent(tmp_path: Path) -> None:
    assert read_manifest(tmp_path) is None


def test_manifest_records_exposure_policy_as_internal_only_by_default() -> None:
    manifest = _sample_manifest()
    assert manifest.exposure_policy == "internal_only"
