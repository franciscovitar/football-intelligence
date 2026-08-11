"""Minimal, server-side API-Football v3 client.

The client owns provider-specific HTTP behavior so provider details do not leak into
normalization, persistence, analytics, or the web application.
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


class ApiFootballError(RuntimeError):
    """Base provider error."""


class ApiFootballHttpError(ApiFootballError):
    """HTTP/network error after bounded retries."""


class ApiFootballResponseError(ApiFootballError):
    """Provider returned an API-level error payload."""


@dataclass(frozen=True)
class ApiFootballResponse:
    """Decoded API response plus transport metadata used for traceability."""

    endpoint: str
    parameters: Mapping[str, str | int]
    status_code: int
    headers: Mapping[str, str]
    payload: JsonObject
    fetched_at: datetime

    @property
    def request_count_remaining(self) -> int | None:
        return _first_int_header(
            self.headers,
            "x-ratelimit-requests-remaining",
            "x-ratelimit-remaining",
        )

    @property
    def request_limit(self) -> int | None:
        return _first_int_header(
            self.headers,
            "x-ratelimit-requests-limit",
            "x-ratelimit-limit",
        )


def _first_int_header(headers: Mapping[str, str], *names: str) -> int | None:
    lowered = {key.lower(): value for key, value in headers.items()}
    for name in names:
        value = lowered.get(name)
        if value is None:
            continue
        try:
            return int(value)
        except ValueError:
            continue
    return None


class ApiFootballClient:
    """Small synchronous API-Football client for batch jobs."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://v3.football.api-sports.io",
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be blank")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, str | int] | None = None,
    ) -> ApiFootballResponse:
        normalized_endpoint = endpoint.strip("/")
        if not normalized_endpoint:
            raise ValueError("endpoint must not be blank")

        params = dict(parameters or {})
        query = urlencode(params)
        url = f"{self._base_url}/{normalized_endpoint}"
        if query:
            url = f"{url}?{query}"

        retryable_statuses = {429, 499, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                status_code, headers, body = self._request_once(url)
                payload = self._decode_payload(body)
                self._raise_for_provider_errors(payload)
                return ApiFootballResponse(
                    endpoint=normalized_endpoint,
                    parameters=params,
                    status_code=status_code,
                    headers=headers,
                    payload=payload,
                    fetched_at=datetime.now(UTC),
                )
            except HTTPError as exc:
                last_error = exc
                if exc.code not in retryable_statuses or attempt == self._max_attempts:
                    raise ApiFootballHttpError(
                        f"API-Football HTTP {exc.code} for {normalized_endpoint}"
                    ) from exc
                self._sleep_before_retry(attempt, exc.headers.get("Retry-After"))
            except (TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise ApiFootballHttpError(
                        f"API-Football transport error for {normalized_endpoint}: {exc}"
                    ) from exc
                self._sleep_before_retry(attempt, None)

        raise ApiFootballHttpError(
            f"API-Football request failed for {normalized_endpoint}: {last_error}"
        )

    def _request_once(self, url: str) -> tuple[int, dict[str, str], bytes]:
        request = Request(
            url,
            method="GET",
            headers={
                "x-apisports-key": self._api_key,
                "Accept": "application/json",
                "User-Agent": "football-intelligence/0.1",
            },
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
            status = int(response.status)
            headers = {key.lower(): value for key, value in response.headers.items()}
            body = response.read()
        return status, headers, body

    @staticmethod
    def _decode_payload(body: bytes) -> JsonObject:
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiFootballResponseError("API-Football returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ApiFootballResponseError("API-Football root payload must be an object")
        return decoded

    @staticmethod
    def _raise_for_provider_errors(payload: JsonObject) -> None:
        errors = payload.get("errors")
        if errors in (None, [], {}):
            return
        raise ApiFootballResponseError(f"API-Football returned errors: {errors!r}")

    @staticmethod
    def _sleep_before_retry(attempt: int, retry_after: str | None) -> None:
        if retry_after:
            try:
                delay = min(float(retry_after), 10.0)
            except ValueError:
                delay = float(attempt)
        else:
            delay = float(attempt)
        time.sleep(delay)
