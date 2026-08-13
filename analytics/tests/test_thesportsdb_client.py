from __future__ import annotations

import json

import pytest

from football_intelligence.providers.thesportsdb import (
    TheSportsDbClient,
    TheSportsDbResponseError,
)


class StubClient(TheSportsDbClient):
    def __init__(self, body: dict[str, object], *, sleep_calls: list[float] | None = None) -> None:
        super().__init__(max_attempts=1, min_request_interval_seconds=0.0)
        self._body = body
        self._sleep_calls = sleep_calls if sleep_calls is not None else []

    def _request_once(self, url: str) -> tuple[int, bytes]:
        assert url.startswith("https://www.thesportsdb.com/api/v1/json/123/")
        return 200, json.dumps(self._body).encode()


def test_client_builds_expected_endpoint_and_parameters() -> None:
    client = StubClient({"events": []})
    response = client.get("eventsseason.php", {"id": "4331", "s": "2025-2026"})
    assert response.endpoint == "eventsseason.php"
    assert response.parameters == {"id": "4331", "s": "2025-2026"}
    assert response.payload == {"events": []}


def test_client_rejects_non_object_payload() -> None:
    class ListPayloadClient(StubClient):
        def _request_once(self, url: str) -> tuple[int, bytes]:
            return 200, json.dumps([1, 2, 3]).encode()

    client = ListPayloadClient({})
    with pytest.raises(TheSportsDbResponseError):
        client.get("eventsseason.php", {"id": "4331"})


def test_client_rate_limits_between_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda seconds: sleeps.append(seconds))

    client = TheSportsDbClient(max_attempts=1, min_request_interval_seconds=1.0)

    calls = {"n": 0}

    def fake_request_once(url: str) -> tuple[int, bytes]:
        calls["n"] += 1
        return 200, json.dumps({"events": []}).encode()

    monkeypatch.setattr(client, "_request_once", fake_request_once)
    monkeypatch.setattr("time.monotonic", iter([0.0, 0.1, 0.1, 0.1]).__next__)

    client.get("eventsseason.php", {"id": "4331"})
    client.get("eventsseason.php", {"id": "4331"})

    assert calls["n"] == 2
    assert len(sleeps) == 1
    assert sleeps[0] > 0
