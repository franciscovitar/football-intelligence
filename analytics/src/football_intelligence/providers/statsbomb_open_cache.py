"""Local reproducibility cache for the pinned StatsBomb Open Data revision.

StatsBomb/GitHub does not expose a provider-authenticated checksum the way
Figshare does for Wyscout Open Data (`computed_md5`). This module computes
its own SHA-256 of the raw bytes returned by `StatsBombOpenDataClient` and
stores it alongside each cached file purely as **local reproducibility/
integrity metadata** -- it proves the cached bytes on disk are exactly the
bytes this process downloaded from the pinned revision, nothing more. It is
never presented as a provider-authenticated checksum.

Cache layout, one directory per pinned revision so different revisions can
never silently mix:

    <cache_root>/<source_revision>/<api-path>            -- raw bytes as downloaded
    <cache_root>/<source_revision>/<api-path>.sha256      -- hex digest sidecar
    <cache_root>/<source_revision>/manifest.json          -- see `manifest.py`

Corruption policy: if a cached file's sidecar hash does not match the bytes
currently on disk, this raises `StatsBombCacheCorruptionError` immediately.
It never silently re-fetches and never silently reuses corrupt bytes --
"fail loudly" per the Block 20C.2a spec. Deleting the offending file (or the
whole revision directory) and re-running is the recovery path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.providers.statsbomb_open import (
    StatsBombOpenDataClient,
    StatsBombOpenDataError,
)

JsonValue = Any

_SHA256_SUFFIX = ".sha256"


class StatsBombCacheError(RuntimeError):
    """Base cache error."""


class StatsBombCacheCorruptionError(StatsBombCacheError):
    """A cached file's bytes no longer match its stored SHA-256 sidecar."""


@dataclass(frozen=True)
class CachedFetch:
    """One cached (or freshly fetched-and-cached) StatsBomb Open Data file."""

    api_path: str
    local_path: Path
    sha256: str
    byte_size: int
    source_revision: str
    from_cache: bool
    payload: JsonValue


def revision_cache_dir(cache_root: Path, source_revision: str) -> Path:
    return cache_root / source_revision


def fetch_json_cached(
    client: StatsBombOpenDataClient,
    api_path: str,
    *,
    cache_root: Path,
) -> CachedFetch:
    """Return `api_path`'s decoded JSON payload, using the on-disk cache when
    a byte-identical, hash-verified copy already exists for this client's
    pinned `source_revision`. Never fetches `master` -- whatever `ref` the
    client was constructed with is the only revision this ever reads or
    writes."""

    revision_dir = revision_cache_dir(cache_root, client.source_revision)
    local_path = revision_dir / api_path
    sidecar_path = _sidecar_path(local_path)

    if local_path.exists() and sidecar_path.exists():
        raw_bytes = local_path.read_bytes()
        stored_digest = sidecar_path.read_text(encoding="utf-8").strip()
        actual_digest = _sha256_hex(raw_bytes)
        if actual_digest != stored_digest:
            raise StatsBombCacheCorruptionError(
                f"cached file {local_path} failed local SHA-256 verification "
                f"(expected {stored_digest}, got {actual_digest}); this is local "
                "reproducibility/integrity metadata, not a provider-authenticated "
                "checksum, but a mismatch means the cached bytes were altered or "
                "truncated after being written. Delete the file and re-fetch "
                "rather than trusting it."
            )
        return CachedFetch(
            api_path=api_path,
            local_path=local_path,
            sha256=actual_digest,
            byte_size=len(raw_bytes),
            source_revision=client.source_revision,
            from_cache=True,
            payload=json.loads(raw_bytes.decode("utf-8")),
        )

    try:
        response = client.get(api_path)
    except StatsBombOpenDataError as exc:
        raise StatsBombCacheError(
            f"could not fetch {api_path} at pinned revision {client.source_revision}: {exc}"
        ) from exc

    digest = _sha256_hex(response.raw_bytes)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(response.raw_bytes)
    sidecar_path.write_text(digest + "\n", encoding="utf-8")

    return CachedFetch(
        api_path=api_path,
        local_path=local_path,
        sha256=digest,
        byte_size=len(response.raw_bytes),
        source_revision=response.source_revision,
        from_cache=False,
        payload=response.payload,
    )


def _sidecar_path(local_path: Path) -> Path:
    return local_path.with_name(local_path.name + _SHA256_SUFFIX)


def _sha256_hex(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def utcnow() -> datetime:
    return datetime.now(UTC)
