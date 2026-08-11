from __future__ import annotations

import json

import pytest

from football_intelligence.providers.api_football import (
    ApiFootballClient,
    ApiFootballResponseError,
)


class StubClient(ApiFootballClient):
    def __init__(self, body: dict[str, object]) -> None:
        super().__init__("test-key", max_attempts=1)
        self._body = body

    def _request_once(self, url: str) -> tuple[int, dict[str, str], bytes]:
        assert "x-apisports-key" not in url
        return (
            200,
            {
                "x-ratelimit-requests-remaining": "97",
                "x-ratelimit-requests-limit": "100",
            },
            json.dumps(self._body).encode(),
        )


def test_client_exposes_quota_without_leaking_key() -> None:
    client = StubClient(
        {
            "get": "fixtures",
            "errors": [],
            "results": 0,
            "paging": {"current": 1, "total": 1},
            "response": [],
        }
    )

    response = client.get("fixtures", {"league": 39, "season": 2025})

    assert response.request_count_remaining == 97
    assert response.request_limit == 100
    assert response.parameters == {"league": 39, "season": 2025}


def test_client_rejects_provider_level_errors() -> None:
    client = StubClient({"errors": {"token": "invalid"}})

    with pytest.raises(ApiFootballResponseError, match="returned errors"):
        client.get("fixtures")
