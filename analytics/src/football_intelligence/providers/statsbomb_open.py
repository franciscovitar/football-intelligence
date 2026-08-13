"""Minimal, server-side StatsBomb Open Data client.

StatsBomb Open Data (https://github.com/statsbomb/open-data) is a public,
official repository of static JSON files published by StatsBomb for
historical/deep event data research. This client only reads the raw files
StatsBomb publishes for that purpose -- no scraping, no authentication, no
hidden endpoints.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

JsonValue = Any


class StatsBombOpenDataError(RuntimeError):
    """Base provider error."""


class StatsBombOpenDataHttpError(StatsBombOpenDataError):
    """HTTP/network error after bounded retries."""


class StatsBombOpenDataResponseError(StatsBombOpenDataError):
    """Provider returned an unusable payload."""


@dataclass(frozen=True)
class StatsBombOpenDataResponse:
    path: str
    status_code: int
    payload: JsonValue
    fetched_at: datetime


class StatsBombOpenDataClient:
    """Small synchronous client for the StatsBomb Open Data static JSON files."""

    def __init__(
        self,
        *,
        base_url: str = "https://raw.githubusercontent.com/statsbomb/open-data/master/data",
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    def get(self, path: str) -> StatsBombOpenDataResponse:
        normalized_path = path.strip().strip("/")
        if not normalized_path:
            raise ValueError("path must not be blank")

        url = f"{self._base_url}/{normalized_path}"
        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                status_code, body = self._request_once(url)
                payload = self._decode_payload(body)
                return StatsBombOpenDataResponse(
                    path=normalized_path,
                    status_code=status_code,
                    payload=payload,
                    fetched_at=datetime.now(UTC),
                )
            except HTTPError as exc:
                last_error = exc
                if exc.code == 404:
                    raise StatsBombOpenDataResponseError(
                        f"StatsBomb Open Data has no file at {normalized_path}"
                    ) from exc
                if exc.code not in retryable_statuses or attempt == self._max_attempts:
                    raise StatsBombOpenDataHttpError(
                        f"StatsBomb Open Data HTTP {exc.code} for {normalized_path}"
                    ) from exc
                time.sleep(float(attempt))
            except (TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise StatsBombOpenDataHttpError(
                        f"StatsBomb Open Data transport error for {normalized_path}: {exc}"
                    ) from exc
                time.sleep(float(attempt))

        raise StatsBombOpenDataHttpError(
            f"StatsBomb Open Data request failed for {normalized_path}: {last_error}"
        )

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
    def _decode_payload(body: bytes) -> JsonValue:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StatsBombOpenDataResponseError(
                "StatsBomb Open Data returned invalid JSON"
            ) from exc
