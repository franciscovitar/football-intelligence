from __future__ import annotations

import gzip
import json

from football_intelligence.ingestion.raw_store import LocalRawStore


def test_raw_store_is_deterministic_and_replayable(tmp_path) -> None:
    store = LocalRawStore(tmp_path)
    payload = {"response": [{"id": 1}], "errors": []}

    first = store.put(
        endpoint="fixtures",
        parameters={"league": 39, "season": 2025},
        payload=payload,
    )
    second = store.put(
        endpoint="fixtures",
        parameters={"season": 2025, "league": 39},
        payload=payload,
    )

    assert first == second
    raw_path = tmp_path / first.storage_path
    decoded = json.loads(gzip.decompress(raw_path.read_bytes()).decode())
    assert decoded == payload
