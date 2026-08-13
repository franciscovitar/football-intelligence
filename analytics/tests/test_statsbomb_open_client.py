from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from football_intelligence.providers.statsbomb_open import (
    StatsBombOpenDataClient,
    StatsBombOpenDataResponseError,
)


class StubClient(StatsBombOpenDataClient):
    def __init__(self, body: object) -> None:
        super().__init__(max_attempts=1)
        self._body = body

    def _request_once(self, url: str) -> tuple[int, bytes]:
        assert url.endswith("/open-data/master/data/competitions.json")
        return 200, json.dumps(self._body).encode()


def test_client_returns_payload() -> None:
    client = StubClient([{"competition_id": 9}])
    response = client.get("competitions.json")
    assert response.path == "competitions.json"
    assert response.payload == [{"competition_id": 9}]


def test_client_rejects_invalid_json() -> None:
    class BrokenClient(StubClient):
        def _request_once(self, url: str) -> tuple[int, bytes]:
            return 200, b"not json"

    client = BrokenClient([])
    with pytest.raises(StatsBombOpenDataResponseError):
        client.get("competitions.json")


def test_get_rejects_blank_path() -> None:
    client = StatsBombOpenDataClient(max_attempts=1)
    with pytest.raises(ValueError):
        client.get("   ")


def test_client_maps_404_to_response_error() -> None:
    class NotFoundClient(StatsBombOpenDataClient):
        def __init__(self) -> None:
            super().__init__(max_attempts=1)

        def _request_once(self, url: str) -> tuple[int, bytes]:
            raise HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]

    client = NotFoundClient()
    with pytest.raises(StatsBombOpenDataResponseError):
        client.get("data/matches/9999/9999.json")
