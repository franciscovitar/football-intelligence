"""Validated metadata and integrity checks for static source snapshots.

Football Intelligence deliberately accepts curated/static datasets as first-class
source evidence. This module defines the provider-independent intake contract used
before an adapter is allowed to normalize a downloaded snapshot.

It does not decide whether a source is legally/product-approved. Source review and
promotion remain separate gates. The manifest only proves *what artifact was used*,
*where it came from*, *when it was acquired*, and *whether the local cached bytes
still match the recorded checksum*.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, cast

SnapshotDataGrain = Literal[
    "competition",
    "team",
    "match",
    "team_match",
    "player_profile",
    "player_appearance",
    "player_match",
    "player_season",
    "goalkeeper_match",
    "goalkeeper_season",
    "event",
]

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_GRAINS: frozenset[str] = frozenset(
    {
        "competition",
        "team",
        "match",
        "team_match",
        "player_profile",
        "player_appearance",
        "player_match",
        "player_season",
        "goalkeeper_match",
        "goalkeeper_season",
        "event",
    }
)
_HASH_CHUNK_SIZE = 1024 * 1024


class StaticSnapshotManifestError(ValueError):
    """A snapshot manifest is malformed or violates the intake contract."""


@dataclass(frozen=True, slots=True)
class SnapshotFile:
    """One immutable file in a locally cached static snapshot."""

    path: str
    sha256: str
    byte_size: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise StaticSnapshotManifestError("SnapshotFile.path must be a non-blank string")
        candidate = Path(self.path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise StaticSnapshotManifestError(
                f"SnapshotFile.path must be a safe relative path, got {self.path!r}"
            )
        if not _SHA256_RE.fullmatch(self.sha256):
            raise StaticSnapshotManifestError(
                f"SnapshotFile.sha256 must be a lowercase 64-character SHA-256 digest, "
                f"got {self.sha256!r}"
            )
        if self.byte_size is not None and self.byte_size < 0:
            raise StaticSnapshotManifestError("SnapshotFile.byte_size cannot be negative")


@dataclass(frozen=True, slots=True)
class StaticSnapshotManifest:
    """Provider-independent provenance contract for one frozen source snapshot."""

    snapshot_id: str
    source_code: str
    acquired_at: datetime
    source_reference: str
    competition_codes: tuple[str, ...]
    season_labels: tuple[str, ...]
    data_grains: tuple[SnapshotDataGrain, ...]
    files: tuple[SnapshotFile, ...]
    notes: str | None = None

    def __post_init__(self) -> None:
        for field_name, value in (
            ("snapshot_id", self.snapshot_id),
            ("source_code", self.source_code),
            ("source_reference", self.source_reference),
        ):
            if not isinstance(value, str) or not value.strip():
                raise StaticSnapshotManifestError(f"{field_name} must be a non-blank string")

        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise StaticSnapshotManifestError("acquired_at must be timezone-aware")

        _validate_sorted_unique_non_blank(self.competition_codes, "competition_codes")
        _validate_sorted_unique_non_blank(self.season_labels, "season_labels")
        if not self.data_grains:
            raise StaticSnapshotManifestError("data_grains must contain at least one grain")
        if tuple(sorted(self.data_grains)) != self.data_grains:
            raise StaticSnapshotManifestError("data_grains must be in canonical ascending order")
        if len(set(self.data_grains)) != len(self.data_grains):
            raise StaticSnapshotManifestError("data_grains must not contain duplicates")
        unknown_grains = set(self.data_grains) - _ALLOWED_GRAINS
        if unknown_grains:
            raise StaticSnapshotManifestError(
                f"data_grains contains unsupported values: {sorted(unknown_grains)!r}"
            )

        if not self.files:
            raise StaticSnapshotManifestError("files must contain at least one snapshot file")
        file_paths = tuple(file.path for file in self.files)
        if tuple(sorted(file_paths)) != file_paths:
            raise StaticSnapshotManifestError("files must be sorted by path")
        if len(set(file_paths)) != len(file_paths):
            raise StaticSnapshotManifestError("files must not contain duplicate paths")


@dataclass(frozen=True, slots=True)
class SnapshotFileVerification:
    path: str
    exists: bool
    checksum_matches: bool
    byte_size_matches: bool | None

    @property
    def passed(self) -> bool:
        return self.exists and self.checksum_matches and self.byte_size_matches is not False


@dataclass(frozen=True, slots=True)
class StaticSnapshotVerificationReport:
    snapshot_id: str
    source_code: str
    files: tuple[SnapshotFileVerification, ...]

    @property
    def passed(self) -> bool:
        return bool(self.files) and all(file.passed for file in self.files)


def load_static_snapshot_manifest(path: Path) -> StaticSnapshotManifest:
    """Load and validate one JSON manifest without touching snapshot data files."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise StaticSnapshotManifestError("manifest root must be a JSON object")
    return static_snapshot_manifest_from_dict(cast(dict[str, Any], payload))


def static_snapshot_manifest_from_dict(payload: dict[str, Any]) -> StaticSnapshotManifest:
    """Construct a validated manifest from already-parsed JSON data."""

    expected_keys = {
        "snapshot_id",
        "source_code",
        "acquired_at",
        "source_reference",
        "competition_codes",
        "season_labels",
        "data_grains",
        "files",
        "notes",
    }
    unknown = set(payload) - expected_keys
    if unknown:
        raise StaticSnapshotManifestError(f"manifest contains unknown fields: {sorted(unknown)!r}")

    acquired_at_raw = _required_string(payload, "acquired_at")
    try:
        acquired_at = datetime.fromisoformat(acquired_at_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise StaticSnapshotManifestError(
            f"acquired_at must be ISO-8601, got {acquired_at_raw!r}"
        ) from exc

    files_raw = payload.get("files")
    if not isinstance(files_raw, list):
        raise StaticSnapshotManifestError("files must be a JSON array")
    files: list[SnapshotFile] = []
    for index, raw in enumerate(files_raw):
        if not isinstance(raw, dict):
            raise StaticSnapshotManifestError(f"files[{index}] must be a JSON object")
        raw_dict = cast(dict[str, Any], raw)
        unknown_file_keys = set(raw_dict) - {"path", "sha256", "byte_size"}
        if unknown_file_keys:
            raise StaticSnapshotManifestError(
                f"files[{index}] contains unknown fields: {sorted(unknown_file_keys)!r}"
            )
        byte_size_raw = raw_dict.get("byte_size")
        if byte_size_raw is not None and (
            not isinstance(byte_size_raw, int) or isinstance(byte_size_raw, bool)
        ):
            raise StaticSnapshotManifestError(f"files[{index}].byte_size must be an integer")
        files.append(
            SnapshotFile(
                path=_required_string(raw_dict, "path"),
                sha256=_required_string(raw_dict, "sha256"),
                byte_size=byte_size_raw,
            )
        )

    grains_raw = _required_string_list(payload, "data_grains")
    unknown_grains = set(grains_raw) - _ALLOWED_GRAINS
    if unknown_grains:
        raise StaticSnapshotManifestError(
            f"data_grains contains unsupported values: {sorted(unknown_grains)!r}"
        )
    grains = cast(tuple[SnapshotDataGrain, ...], tuple(grains_raw))

    notes_raw = payload.get("notes")
    if notes_raw is not None and not isinstance(notes_raw, str):
        raise StaticSnapshotManifestError("notes must be a string or null")

    return StaticSnapshotManifest(
        snapshot_id=_required_string(payload, "snapshot_id"),
        source_code=_required_string(payload, "source_code"),
        acquired_at=acquired_at,
        source_reference=_required_string(payload, "source_reference"),
        competition_codes=tuple(_required_string_list(payload, "competition_codes")),
        season_labels=tuple(_required_string_list(payload, "season_labels")),
        data_grains=grains,
        files=tuple(files),
        notes=notes_raw,
    )


def verify_static_snapshot_files(
    manifest: StaticSnapshotManifest, *, base_dir: Path
) -> StaticSnapshotVerificationReport:
    """Verify local cached snapshot bytes against the manifest without mutation.

    Files are hashed incrementally so multi-gigabyte snapshots never need to be
    loaded into memory solely to prove integrity.
    """

    results: list[SnapshotFileVerification] = []
    for expected in manifest.files:
        path = base_dir / expected.path
        if not path.is_file():
            results.append(
                SnapshotFileVerification(
                    path=expected.path,
                    exists=False,
                    checksum_matches=False,
                    byte_size_matches=None,
                )
            )
            continue
        actual_size = path.stat().st_size
        results.append(
            SnapshotFileVerification(
                path=expected.path,
                exists=True,
                checksum_matches=_sha256_file(path) == expected.sha256,
                byte_size_matches=(
                    None if expected.byte_size is None else actual_size == expected.byte_size
                ),
            )
        )
    return StaticSnapshotVerificationReport(
        snapshot_id=manifest.snapshot_id,
        source_code=manifest.source_code,
        files=tuple(results),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sorted_unique_non_blank(values: tuple[str, ...], field_name: str) -> None:
    if not values:
        raise StaticSnapshotManifestError(f"{field_name} must contain at least one value")
    if tuple(sorted(values)) != values:
        raise StaticSnapshotManifestError(f"{field_name} must be in canonical ascending order")
    if len(set(values)) != len(values):
        raise StaticSnapshotManifestError(f"{field_name} must not contain duplicates")
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise StaticSnapshotManifestError(f"{field_name} must contain only non-blank strings")


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StaticSnapshotManifestError(f"{key} must be a non-blank string")
    return value


def _required_string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise StaticSnapshotManifestError(f"{key} must be a JSON array")
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise StaticSnapshotManifestError(f"{key}[{index}] must be a non-blank string")
        result.append(item)
    return result
