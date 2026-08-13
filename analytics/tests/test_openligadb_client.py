from __future__ import annotations

import json

import pytest

from football_intelligence.providers.openligadb import OpenLigaDbClient, OpenLigaDbResponseError


class StubClient(OpenLigaDbClient):
    def __init__(self, body: object) -> None:
        super().__init__(max_attempts=1)
        self._body = body

    def _request_once(self, url: str) -> tuple[int, bytes]:
        assert url == "https://api.openligadb.de/getmatchdata/bl1/2025"
        return 200, json.dumps(self._body).encode()


def test_client_returns_array_payload_unchanged() -> None:
    client = StubClient([{"matchID": 1}, {"matchID": 2}])
    response = client.get("getmatchdata/bl1/2025")
    assert response.endpoint == "getmatchdata/bl1/2025"
    assert response.payload == [{"matchID": 1}, {"matchID": 2}]


def test_client_rejects_invalid_json() -> None:
    class BrokenClient(StubClient):
        def _request_once(self, url: str) -> tuple[int, bytes]:
            return 200, b"not json"

    client = BrokenClient([])
    with pytest.raises(OpenLigaDbResponseError):
        client.get("getmatchdata/bl1/2025")


def test_get_rejects_blank_endpoint() -> None:
    client = OpenLigaDbClient(max_attempts=1)
    with pytest.raises(ValueError):
        client.get("   ")
