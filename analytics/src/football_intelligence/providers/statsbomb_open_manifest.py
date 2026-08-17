"""Machine-readable source-snapshot manifest for the pinned StatsBomb Open
Data cache -- local/cache metadata only, never persisted to a database.

Records what was fetched, from where, at which pinned commit, under which
exposure policy, so a later reader (a person or a job) can answer "is this
cache reproducible, complete, and safe to treat as internal-only evidence?"
without re-deriving any of that from the raw files themselves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

PROVIDER_NAME = "StatsBomb Open Data"
UPSTREAM_REPOSITORY = "https://github.com/statsbomb/open-data"
ROLE_HISTORICAL_DEEP = "historical_deep"
EXPOSURE_POLICY_INTERNAL_ONLY = "internal_only"

_MANIFEST_FILENAME = "manifest.json"


@dataclass(frozen=True)
class CachedFileRecord:
    api_path: str
    sha256: str
    byte_size: int


@dataclass(frozen=True)
class SourceSnapshotManifest:
    provider: str
    upstream_repository: str
    pinned_commit_sha: str
    competition_id: int
    season_id: int
    competition_name: str
    season_name: str
    role: str
    exposure_policy: str
    fetched_at: datetime
    expected_match_count: int
    files: tuple[CachedFileRecord, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "upstream_repository": self.upstream_repository,
            "pinned_commit_sha": self.pinned_commit_sha,
            "competition_id": self.competition_id,
            "season_id": self.season_id,
            "competition_name": self.competition_name,
            "season_name": self.season_name,
            "role": self.role,
            "exposure_policy": self.exposure_policy,
            "fetched_at": self.fetched_at.isoformat(),
            "expected_match_count": self.expected_match_count,
            "file_count": len(self.files),
            "files": [
                {"api_path": f.api_path, "sha256": f.sha256, "byte_size": f.byte_size}
                for f in self.files
            ],
        }


def manifest_path(revision_cache_dir: Path) -> Path:
    return revision_cache_dir / _MANIFEST_FILENAME


def write_manifest(revision_cache_dir: Path, manifest: SourceSnapshotManifest) -> Path:
    revision_cache_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_path(revision_cache_dir)
    content = json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n"
    path.write_text(content, encoding="utf-8")
    return path


def read_manifest(revision_cache_dir: Path) -> SourceSnapshotManifest | None:
    path = manifest_path(revision_cache_dir)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return SourceSnapshotManifest(
        provider=data["provider"],
        upstream_repository=data["upstream_repository"],
        pinned_commit_sha=data["pinned_commit_sha"],
        competition_id=data["competition_id"],
        season_id=data["season_id"],
        competition_name=data["competition_name"],
        season_name=data["season_name"],
        role=data["role"],
        exposure_policy=data["exposure_policy"],
        fetched_at=datetime.fromisoformat(data["fetched_at"]),
        expected_match_count=data["expected_match_count"],
        files=tuple(
            CachedFileRecord(
                api_path=item["api_path"], sha256=item["sha256"], byte_size=item["byte_size"]
            )
            for item in data.get("files", [])
        ),
    )
