from __future__ import annotations

import json

import pytest

from football_intelligence.providers.football_data_org import (
    FootballDataOrgClient,
    FootballDataOrgResponseError,
)


class StubClient(FootballDataOrgClient):
    def __init__(self, body: dict[str, object]) -> None:
        super().__init__("test-token", max_attempts=1)
        self._body = body

    def _request_once(self, url: str) -> tuple[int, bytes]:
        assert "test-token" not in url
        assert url.endswith("/v4/competitions")
        return 200, json.dumps(self._body).encode()


def test_client_returns_payload_without_leaking_token_in_url() -> None:
    client = StubClient({"competitions": []})
    response = client.get("competitions")
    assert response.payload == {"competitions": []}


def test_client_rejects_blank_token() -> None:
    with pytest.raises(ValueError):
        FootballDataOrgClient("   ")


def test_client_rejects_non_object_payload() -> None:
    class ListPayloadClient(StubClient):
        def _request_once(self, url: str) -> tuple[int, bytes]:
            return 200, json.dumps([1, 2, 3]).encode()

    client = ListPayloadClient({})
    with pytest.raises(FootballDataOrgResponseError):
        client.get("competitions")


def test_get_rejects_blank_endpoint() -> None:
    client = FootballDataOrgClient("test-token", max_attempts=1)
    with pytest.raises(ValueError):
        client.get("   ")
