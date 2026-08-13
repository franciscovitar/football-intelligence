"""Minimal, server-side OpenLigaDB API client.

Public, documented, unauthenticated endpoints only
(https://api.openligadb.de/swagger/index.html).
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


class OpenLigaDbError(RuntimeError):
    """Base provider error."""


class OpenLigaDbHttpError(OpenLigaDbError):
    """HTTP/network error after bounded retries."""


class OpenLigaDbResponseError(OpenLigaDbError):
    """Provider returned an unusable payload."""


@dataclass(frozen=True)
class OpenLigaDbResponse:
    endpoint: str
    status_code: int
    payload: JsonValue
    fetched_at: datetime


class OpenLigaDbClient:
    """Small synchronous OpenLigaDB client for bounded batch/PoC jobs."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.openligadb.de",
        timeout_seconds: float = 20.0,
        max_attempts: int = 3,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts

    def get(self, endpoint: str) -> OpenLigaDbResponse:
        normalized_endpoint = endpoint.strip().strip("/")
        if not normalized_endpoint:
            raise ValueError("endpoint must not be blank")

        url = f"{self._base_url}/{normalized_endpoint}"
        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                status_code, body = self._request_once(url)
                payload = self._decode_payload(body)
                return OpenLigaDbResponse(
                    endpoint=normalized_endpoint,
                    status_code=status_code,
                    payload=payload,
                    fetched_at=datetime.now(UTC),
                )
            except HTTPError as exc:
                last_error = exc
                if exc.code not in retryable_statuses or attempt == self._max_attempts:
                    raise OpenLigaDbHttpError(
                        f"OpenLigaDB HTTP {exc.code} for {normalized_endpoint}"
                    ) from exc
                time.sleep(float(attempt))
            except (TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise OpenLigaDbHttpError(
                        f"OpenLigaDB transport error for {normalized_endpoint}: {exc}"
                    ) from exc
                time.sleep(float(attempt))

        raise OpenLigaDbHttpError(
            f"OpenLigaDB request failed for {normalized_endpoint}: {last_error}"
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
            raise OpenLigaDbResponseError("OpenLigaDB returned invalid JSON") from exc
