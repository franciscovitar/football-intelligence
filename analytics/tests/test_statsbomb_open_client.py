from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from football_intelligence.providers.statsbomb_open import (
    DEFAULT_PINNED_REVISION,
    StatsBombOpenDataClient,
    StatsBombOpenDataHttpError,
    StatsBombOpenDataResponseError,
)


class StubClient(StatsBombOpenDataClient):
    def __init__(self, body: object) -> None:
        super().__init__(max_attempts=1)
        self._body = body

    def _request_once(self, url: str) -> tuple[int, bytes]:
        assert url.endswith(f"/open-data/{DEFAULT_PINNED_REVISION}/data/competitions.json")
        return 200, json.dumps(self._body).encode()


def test_client_returns_payload() -> None:
    client = StubClient([{"competition_id": 9}])
    response = client.get("competitions.json")
    assert response.path == "competitions.json"
    assert response.payload == [{"competition_id": 9}]
    assert response.source_revision == DEFAULT_PINNED_REVISION
    assert response.raw_bytes == json.dumps([{"competition_id": 9}]).encode()


def test_client_defaults_to_pinned_revision_not_master() -> None:
    client = StatsBombOpenDataClient(max_attempts=1)
    assert client.source_revision == DEFAULT_PINNED_REVISION
    assert "master" not in client.source_revision


def test_client_never_silently_substitutes_master_for_an_explicit_ref() -> None:
    client = StatsBombOpenDataClient(ref="0123456789abcdef0123456789abcdef01234567", max_attempts=1)
    assert client.source_revision == "0123456789abcdef0123456789abcdef01234567"


def test_client_rejects_blank_ref() -> None:
    with pytest.raises(ValueError):
        StatsBombOpenDataClient(ref="   ")


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


def test_client_retries_bounded_number_of_times_then_raises() -> None:
    call_count = 0

    class FlakyClient(StatsBombOpenDataClient):
        def __init__(self) -> None:
            super().__init__(max_attempts=3)

        def _request_once(self, url: str) -> tuple[int, bytes]:
            nonlocal call_count
            call_count += 1
            raise HTTPError(url, 503, "Service Unavailable", None, None)  # type: ignore[arg-type]

    client = FlakyClient()
    with pytest.raises(StatsBombOpenDataHttpError):
        client.get("competitions.json")
    assert call_count == 3
