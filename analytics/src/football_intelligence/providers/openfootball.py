"""Minimal client for OpenFootball's published season JSON files.

This is structured file ingestion, not HTML scraping: every file fetched
here is one of the `openfootball/football.json` GitHub repository's own
directly-linked raw JSON files
(`https://raw.githubusercontent.com/openfootball/football.json/master/<season>/en.1.json`),
never a presentation webpage. No authentication, no hidden endpoints. The
repository dedicates its schema, data and scripts to the public domain
(CC0 -- see `docs/REAL_DATA_SOURCE_AUDIT_V2.md` for the verified license
text and date).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenFootballError(RuntimeError):
    """Base provider error."""


class OpenFootballHttpError(OpenFootballError):
    """HTTP/network error."""


class OpenFootballNotFoundError(OpenFootballError):
    """The requested season/competition file does not exist (yet)."""


@dataclass(frozen=True)
class OpenFootballResponse:
    competition_file: str
    season_code: str
    payload: dict[str, Any]
    fetched_at: datetime
    # The exact bytes as received over the wire, before JSON parsing -- the
    # correct input for a source-integrity checksum. The upstream URL points
    # at mutable `master`, so this content hash (not a fixed commit) is the
    # snapshot's real integrity anchor.
    raw_bytes: bytes


class OpenFootballClient:
    """Small synchronous client for the repository's published season JSON files."""

    def __init__(
        self,
        *,
        base_url: str = "https://raw.githubusercontent.com/openfootball/football.json/master",
        timeout_seconds: float = 20.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_season_json(self, *, competition_file: str, season_code: str) -> OpenFootballResponse:
        if not competition_file.strip():
            raise ValueError("competition_file must not be blank")
        if not season_code.strip():
            raise ValueError("season_code must not be blank")

        url = f"{self._base_url}/{season_code}/{competition_file}"
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "football-intelligence/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                status = int(response.status)
                body = response.read()
        except HTTPError as exc:
            if exc.code == 404:
                raise OpenFootballNotFoundError(
                    f"no {season_code}/{competition_file} published (HTTP 404)"
                ) from exc
            raise OpenFootballHttpError(
                f"OpenFootball HTTP {exc.code} for {season_code}/{competition_file}"
            ) from exc
        except (TimeoutError, URLError) as exc:
            raise OpenFootballHttpError(
                f"OpenFootball transport error for {season_code}/{competition_file}: {exc}"
            ) from exc

        if status != 200:
            raise OpenFootballHttpError(
                f"OpenFootball HTTP {status} for {season_code}/{competition_file}"
            )

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenFootballError("OpenFootball returned undecodable/invalid JSON") from exc

        if not isinstance(payload, dict) or "matches" not in payload:
            raise OpenFootballError(
                f"OpenFootball payload for {season_code}/{competition_file} "
                "did not contain the expected 'matches' shape"
            )

        return OpenFootballResponse(
            competition_file=competition_file,
            season_code=season_code,
            payload=payload,
            fetched_at=datetime.now(UTC),
            raw_bytes=body,
        )
