"""Minimal client for the official Fantasy Premier League (FPL) API.

Public, unauthenticated JSON endpoints under
`https://fantasy.premierleague.com/api/` -- the same origin the Premier
League's own official FPL app and website consume, not a hidden or
reverse-engineered private API. No login, no API key.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

JsonObject = dict[str, Any]


class FplError(RuntimeError):
    """Base provider error."""


class FplHttpError(FplError):
    """HTTP/network error after bounded retries."""


class FplResponseError(FplError):
    """Provider returned an unusable payload."""


class FplElementNotFoundError(FplError):
    """The requested element (player) id does not exist."""


@dataclass(frozen=True)
class FplBootstrapResponse:
    elements: tuple[JsonObject, ...]
    teams: tuple[JsonObject, ...]
    element_types: tuple[JsonObject, ...]
    fetched_at: datetime


@dataclass(frozen=True)
class FplElementSummaryResponse:
    element_id: int
    history_past: tuple[JsonObject, ...]
    fetched_at: datetime


class FplClient:
    """Small synchronous FPL API client for batch jobs."""

    def __init__(
        self,
        *,
        base_url: str = "https://fantasy.premierleague.com/api",
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    def get_bootstrap_static(self) -> FplBootstrapResponse:
        payload = self._get_json("bootstrap-static/")
        fetched_at = datetime.now(UTC)
        return FplBootstrapResponse(
            elements=tuple(_list_of_objects(payload, "elements")),
            teams=tuple(_list_of_objects(payload, "teams")),
            element_types=tuple(_list_of_objects(payload, "element_types")),
            fetched_at=fetched_at,
        )

    def get_element_summary(self, element_id: int) -> FplElementSummaryResponse:
        if element_id <= 0:
            raise ValueError("element_id must be positive")
        payload = self._get_json(f"element-summary/{element_id}/", not_found_element_id=element_id)
        return FplElementSummaryResponse(
            element_id=element_id,
            history_past=tuple(_list_of_objects(payload, "history_past")),
            fetched_at=datetime.now(UTC),
        )

    def _get_json(self, endpoint: str, *, not_found_element_id: int | None = None) -> JsonObject:
        url = f"{self._base_url}/{endpoint}"
        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                body = self._request_once(url)
                return self._decode_payload(body)
            except HTTPError as exc:
                if exc.code == 404 and not_found_element_id is not None:
                    raise FplElementNotFoundError(
                        f"FPL element {not_found_element_id} not found"
                    ) from exc
                last_error = exc
                if exc.code not in retryable_statuses or attempt == self._max_attempts:
                    raise FplHttpError(f"FPL HTTP {exc.code} for {endpoint}") from exc
                time.sleep(float(attempt))
            except (TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise FplHttpError(f"FPL transport error for {endpoint}: {exc}") from exc
                time.sleep(float(attempt))

        raise FplHttpError(f"FPL request failed for {endpoint}: {last_error}")

    def _request_once(self, url: str) -> bytes:
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "football-intelligence/0.1",
            },
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
            body: bytes = response.read()
        return body

    @staticmethod
    def _decode_payload(body: bytes) -> JsonObject:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FplResponseError("FPL returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise FplResponseError("FPL root payload must be an object")
        return decoded


def _list_of_objects(payload: JsonObject, key: str) -> list[JsonObject]:
    value = payload.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
