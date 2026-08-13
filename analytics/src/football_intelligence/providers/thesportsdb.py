"""Minimal, server-side TheSportsDB v1 Free API client.

Official documented endpoints only (https://www.thesportsdb.com/documentation),
using the published free test key `123`. No website scraping and no
undocumented/hidden endpoints.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

JsonObject = dict[str, Any]

FREE_API_KEY = "123"


class TheSportsDbError(RuntimeError):
    """Base provider error."""


class TheSportsDbHttpError(TheSportsDbError):
    """HTTP/network error after bounded retries."""


class TheSportsDbResponseError(TheSportsDbError):
    """Provider returned an unusable payload."""


@dataclass(frozen=True)
class TheSportsDbResponse:
    endpoint: str
    parameters: Mapping[str, str | int]
    status_code: int
    payload: JsonObject
    fetched_at: datetime


class TheSportsDbClient:
    """Small synchronous TheSportsDB client for bounded batch/PoC jobs.

    Enforces a minimum interval between requests (the free tier is limited to
    30 requests/minute) even though PoC jobs only ever issue a handful of
    calls.
    """

    def __init__(
        self,
        *,
        api_key: str = FREE_API_KEY,
        base_url: str = "https://www.thesportsdb.com/api/v1/json",
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
        min_request_interval_seconds: float = 1.2,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._min_request_interval_seconds = min_request_interval_seconds
        self._last_request_at: float | None = None

    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, str | int] | None = None,
    ) -> TheSportsDbResponse:
        normalized_endpoint = endpoint.strip().strip("/")
        if not normalized_endpoint:
            raise ValueError("endpoint must not be blank")

        params = dict(parameters or {})
        query = urlencode(params)
        url = f"{self._base_url}/{self._api_key}/{normalized_endpoint}"
        if query:
            url = f"{url}?{query}"

        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            self._respect_rate_limit()
            try:
                status_code, body = self._request_once(url)
                payload = self._decode_payload(body)
                return TheSportsDbResponse(
                    endpoint=normalized_endpoint,
                    parameters=params,
                    status_code=status_code,
                    payload=payload,
                    fetched_at=datetime.now(UTC),
                )
            except HTTPError as exc:
                last_error = exc
                if exc.code not in retryable_statuses or attempt == self._max_attempts:
                    raise TheSportsDbHttpError(
                        f"TheSportsDB HTTP {exc.code} for {normalized_endpoint}"
                    ) from exc
                time.sleep(float(attempt))
            except (TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise TheSportsDbHttpError(
                        f"TheSportsDB transport error for {normalized_endpoint}: {exc}"
                    ) from exc
                time.sleep(float(attempt))

        raise TheSportsDbHttpError(
            f"TheSportsDB request failed for {normalized_endpoint}: {last_error}"
        )

    def _respect_rate_limit(self) -> None:
        if self._last_request_at is None:
            self._last_request_at = time.monotonic()
            return
        elapsed = time.monotonic() - self._last_request_at
        remaining = self._min_request_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_at = time.monotonic()

    def _request_once(self, url: str) -> tuple[int, bytes]:
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "football-intelligence/0.1",
            },
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
            status = int(response.status)
            body = response.read()
        return status, body

    @staticmethod
    def _decode_payload(body: bytes) -> JsonObject:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TheSportsDbResponseError("TheSportsDB returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise TheSportsDbResponseError("TheSportsDB root payload must be an object")
        return decoded
