"""Minimal client for Football-Data.co.uk's published results CSV files.

This is structured file ingestion, not HTML scraping: every file fetched
here is one of the site's own explicitly published, directly-linked
downloadable CSV files
(`https://www.football-data.co.uk/mmz4281/<season>/<division>.csv`), never a
presentation webpage. No authentication, no hidden endpoints, no parsing of
rendered HTML.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class FootballDataUkError(RuntimeError):
    """Base provider error."""


class FootballDataUkHttpError(FootballDataUkError):
    """HTTP/network error."""


class FootballDataUkNotFoundError(FootballDataUkError):
    """The requested season/division file does not exist (yet)."""


@dataclass(frozen=True)
class FootballDataUkResponse:
    division_code: str
    season_code: str
    csv_text: str
    fetched_at: datetime
    # The exact bytes as received over the wire, before any decoding --
    # the correct input for a source-integrity checksum (SHA-256 of a
    # re-encoded `csv_text` would not necessarily match the real download,
    # e.g. if a BOM was stripped during decoding).
    raw_bytes: bytes


class FootballDataUkClient:
    """Small synchronous client for the site's published CSV files."""

    def __init__(
        self,
        *,
        base_url: str = "https://www.football-data.co.uk/mmz4281",
        timeout_seconds: float = 20.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    def get_results_csv(self, *, division_code: str, season_code: str) -> FootballDataUkResponse:
        if not division_code.strip():
            raise ValueError("division_code must not be blank")
        if not season_code.strip():
            raise ValueError("season_code must not be blank")

        url = f"{self._base_url}/{season_code}/{division_code}.csv"
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "text/csv",
                "User-Agent": "football-intelligence/0.1",
            },
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                status = int(response.status)
                body = response.read()
        except HTTPError as exc:
            # 404 is the obvious "not published" signal. Verified live during
            # implementation: a season/division combination with no
            # published file also commonly responds 300 ("Multiple
            # Choices" -- an ambiguous-redirect page urllib does not follow
            # automatically), never a genuine transient outage -- both mean
            # the same thing here and must both trigger the caller's
            # season-fallback path, not a hard stop.
            if exc.code in (404, 300):
                raise FootballDataUkNotFoundError(
                    f"no {season_code}/{division_code}.csv published (HTTP {exc.code})"
                ) from exc
            raise FootballDataUkHttpError(
                f"Football-Data.co.uk HTTP {exc.code} for {season_code}/{division_code}.csv"
            ) from exc
        except (TimeoutError, URLError) as exc:
            raise FootballDataUkHttpError(
                f"Football-Data.co.uk transport error for {season_code}/{division_code}.csv: {exc}"
            ) from exc

        if status != 200:
            raise FootballDataUkHttpError(
                f"Football-Data.co.uk HTTP {status} for {season_code}/{division_code}.csv"
            )

        try:
            csv_text = body.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise FootballDataUkError("Football-Data.co.uk returned undecodable content") from exc

        # A season/division combination with no published file redirects to
        # an HTML page (200 OK) rather than 404ing -- detect that instead of
        # silently treating an error page as real match data.
        stripped = csv_text.lstrip()
        if not stripped or not stripped.split("\n", 1)[0].strip().startswith(("Div", "﻿Div")):
            raise FootballDataUkNotFoundError(
                f"{season_code}/{division_code}.csv did not return CSV content "
                "(likely not published yet)"
            )

        return FootballDataUkResponse(
            division_code=division_code,
            season_code=season_code,
            csv_text=csv_text,
            fetched_at=datetime.now(UTC),
            raw_bytes=body,
        )
