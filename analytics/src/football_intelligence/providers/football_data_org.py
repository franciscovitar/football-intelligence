"""Minimal, server-side football-data.org v4 client.

Optional-token source: without `FOOTBALL_DATA_ORG_KEY`, callers must not
probe this provider at all (see `coverage` package -- absence of a token is
reported as `token_required`, never as a failure). Free-tier capabilities
only: competitions, fixtures, results, standings -- no deep player
statistics are claimed.
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

TOKEN_ENV_VAR = "FOOTBALL_DATA_ORG_KEY"


class FootballDataOrgError(RuntimeError):
    """Base provider error."""


class FootballDataOrgHttpError(FootballDataOrgError):
    """HTTP/network error after bounded retries."""


class FootballDataOrgResponseError(FootballDataOrgError):
    """Provider returned an unusable payload."""


@dataclass(frozen=True)
class FootballDataOrgResponse:
    endpoint: str
    parameters: Mapping[str, str | int]
    status_code: int
    payload: JsonObject
    fetched_at: datetime


class FootballDataOrgClient:
    """Small synchronous football-data.org Free-tier client."""

    def __init__(
        self,
        api_token: str,
        *,
        base_url: str = "https://api.football-data.org/v4",
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
    ) -> None:
        if not api_token.strip():
            raise ValueError("api_token must not be blank")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._api_token = api_token
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    def get(
        self,
        endpoint: str,
        parameters: Mapping[str, str | int] | None = None,
    ) -> FootballDataOrgResponse:
        normalized_endpoint = endpoint.strip().strip("/")
        if not normalized_endpoint:
            raise ValueError("endpoint must not be blank")

        params = dict(parameters or {})
        query = urlencode(params)
        url = f"{self._base_url}/{normalized_endpoint}"
        if query:
            url = f"{url}?{query}"

        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                status_code, body = self._request_once(url)
                payload = self._decode_payload(body)
                return FootballDataOrgResponse(
                    endpoint=normalized_endpoint,
                    parameters=params,
                    status_code=status_code,
                    payload=payload,
                    fetched_at=datetime.now(UTC),
                )
            except HTTPError as exc:
                last_error = exc
                if exc.code not in retryable_statuses or attempt == self._max_attempts:
                    raise FootballDataOrgHttpError(
                        f"football-data.org HTTP {exc.code} for {normalized_endpoint}"
                    ) from exc
                time.sleep(float(attempt))
            except (TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise FootballDataOrgHttpError(
                        f"football-data.org transport error for {normalized_endpoint}: {exc}"
                    ) from exc
                time.sleep(float(attempt))

        raise FootballDataOrgHttpError(
            f"football-data.org request failed for {normalized_endpoint}: {last_error}"
        )

    def _request_once(self, url: str) -> tuple[int, bytes]:
        request = Request(
            url,
            method="GET",
            headers={
                "X-Auth-Token": self._api_token,
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
            raise FootballDataOrgResponseError("football-data.org returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise FootballDataOrgResponseError("football-data.org root payload must be an object")
        return decoded
