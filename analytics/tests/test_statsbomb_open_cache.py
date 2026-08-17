from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from football_intelligence.providers.statsbomb_open import StatsBombOpenDataClient
from football_intelligence.providers.statsbomb_open_cache import (
    StatsBombCacheCorruptionError,
    fetch_json_cached,
    revision_cache_dir,
)

_REF = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"


class StubClient(StatsBombOpenDataClient):
    def __init__(self, bodies: dict[str, object]) -> None:
        super().__init__(ref=_REF, max_attempts=1)
        self._bodies = bodies
        self.request_count = 0

    def _request_once(self, url: str) -> tuple[int, bytes]:
        self.request_count += 1
        for path, body in self._bodies.items():
            if url.endswith(path):
                return 200, json.dumps(body).encode()
        raise AssertionError(f"unexpected url: {url}")


def test_fetch_writes_cache_and_sha256_sidecar(tmp_path: Path) -> None:
    client = StubClient({"competitions.json": [{"competition_id": 9}]})
    fetch = fetch_json_cached(client, "competitions.json", cache_root=tmp_path)

    assert fetch.payload == [{"competition_id": 9}]
    assert fetch.from_cache is False
    assert fetch.source_revision == _REF

    revision_dir = revision_cache_dir(tmp_path, _REF)
    cached_file = revision_dir / "competitions.json"
    sidecar = revision_dir / "competitions.json.sha256"
    assert cached_file.exists()
    assert sidecar.exists()
    expected_digest = hashlib.sha256(cached_file.read_bytes()).hexdigest()
    assert sidecar.read_text(encoding="utf-8").strip() == expected_digest
    assert fetch.sha256 == expected_digest


def test_second_fetch_reuses_cache_without_a_network_call(tmp_path: Path) -> None:
    client = StubClient({"competitions.json": [{"competition_id": 9}]})
    fetch_json_cached(client, "competitions.json", cache_root=tmp_path)
    assert client.request_count == 1

    second = fetch_json_cached(client, "competitions.json", cache_root=tmp_path)
    assert client.request_count == 1  # no new network call
    assert second.from_cache is True
    assert second.payload == [{"competition_id": 9}]


def test_corrupted_cache_fails_loudly_instead_of_silently_refetching(tmp_path: Path) -> None:
    client = StubClient({"competitions.json": [{"competition_id": 9}]})
    fetch_json_cached(client, "competitions.json", cache_root=tmp_path)

    revision_dir = revision_cache_dir(tmp_path, _REF)
    cached_file = revision_dir / "competitions.json"
    cached_file.write_bytes(b"corrupted, does not match the stored sha256 sidecar")

    with pytest.raises(StatsBombCacheCorruptionError):
        fetch_json_cached(client, "competitions.json", cache_root=tmp_path)
    # No silent re-fetch happened as part of raising the corruption error.
    assert client.request_count == 1


def test_different_pinned_revisions_never_share_a_cache_directory(tmp_path: Path) -> None:
    client_a = StubClient({"competitions.json": [{"competition_id": 1}]})
    client_b = StatsBombOpenDataClientForRefB({"competitions.json": [{"competition_id": 2}]})

    fetch_a = fetch_json_cached(client_a, "competitions.json", cache_root=tmp_path)
    fetch_b = fetch_json_cached(client_b, "competitions.json", cache_root=tmp_path)

    assert fetch_a.local_path != fetch_b.local_path
    assert fetch_a.payload == [{"competition_id": 1}]
    assert fetch_b.payload == [{"competition_id": 2}]


class StatsBombOpenDataClientForRefB(StatsBombOpenDataClient):
    def __init__(self, bodies: dict[str, object]) -> None:
        super().__init__(ref="cafebabecafebabecafebabecafebabecafebabe", max_attempts=1)
        self._bodies = bodies

    def _request_once(self, url: str) -> tuple[int, bytes]:
        for path, body in self._bodies.items():
            if url.endswith(path):
                return 200, json.dumps(body).encode()
        raise AssertionError(f"unexpected url: {url}")
