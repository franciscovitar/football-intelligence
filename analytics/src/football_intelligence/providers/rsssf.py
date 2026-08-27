"""Bounded RSSSF acquisition/parser for Argentina Primera Division 2016.

This module is intentionally competition-season specific. RSSSF's Argentina
2016 document contains many competitions and levels on one HTML page; the
parser only accepts the Primera Division championship block from Round 1 up to
(the exclusive) Relegation heading and fails closed unless the historical
structure still matches the empirically verified 242-match tournament.

RSSSF is presentation HTML, not a structured API. The document-specific reuse
notice permits copying the document in whole or part with proper acknowledgement
to the author; see docs/SOURCES.md and the RSSSF ARG_LPF 2016 audit for the
reviewed source/compliance boundary. This module never parses player evidence.
"""

from __future__ import annotations

import hashlib
import html
import re
import time
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RSSSF_ARGENTINA_2016_URL = "https://www.rsssf.org/tablesa/arg2016.html"
RSSSF_ARGENTINA_2016_COMPETITION_ID = "arg2016.html"
RSSSF_ARGENTINA_2016_SEASON_LABEL = "2016"
RSSSF_ARGENTINA_2016_AUTHOR = "Osvaldo José Gorgazzi"

_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
_DATE_RE = re.compile(
    r"^\[(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"(\d{1,2})(?:,)?\s+[^\]]+\]$",
    re.IGNORECASE,
)
_ROUND_RE = re.compile(r"^Round\s+(\d+):$", re.IGNORECASE)
_MATCH_RE = re.compile(
    r"^(?P<home>.+?)\s+(?P<home_score>\d+)\s*-\s*(?P<away_score>\d+)\s+"
    r"(?P<away>.+?)\s+\[(?P<venue>[^\]]+)\](?:\s*.*)?$"
)
_CHARSET_RE = re.compile(r"charset\s*=\s*[\"']?([^;\"'\s]+)", re.IGNORECASE)

RSSSFPhase = Literal[
    "regular_group_1",
    "regular_group_2",
    "regular_intergroup",
    "third_place_playoff",
    "final",
]


class RSSSFError(RuntimeError):
    """Base RSSSF integration error."""


class RSSSFHttpError(RSSSFError):
    """RSSSF transport/HTTP failure."""


class RSSSFSchemaError(RSSSFError):
    """The bounded Argentina 2016 document no longer matches the certified shape."""


@dataclass(frozen=True, slots=True)
class RSSSFMatch:
    external_id: str
    match_date: date
    round_number: int
    phase: RSSSFPhase
    subgroup: str | None
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    venue: str
    source_line: str


@dataclass(frozen=True, slots=True)
class RSSSFArgentina2016Snapshot:
    source_url: str
    fetched_at: datetime
    content_type: str
    decoded_charset: str
    raw_bytes: bytes
    matches: tuple[RSSSFMatch, ...]

    @property
    def raw_sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self.raw_bytes).hexdigest()


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() in {"br", "p", "div", "pre", "h1", "h2", "h3", "h4", "hr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"p", "div", "pre", "h1", "h2", "h3", "h4"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return html.unescape("".join(self._parts)).replace("\r\n", "\n").replace("\r", "\n")


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def _charset_from_content_type(content_type: str) -> str | None:
    match = _CHARSET_RE.search(content_type)
    return match.group(1) if match else None


def _extract_text(raw_bytes: bytes, *, content_type: str) -> tuple[str, str]:
    declared = _charset_from_content_type(content_type)
    candidates = [declared, "utf-8", "windows-1252", "latin-1"]
    tried: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate.casefold() in tried:
            continue
        tried.add(candidate.casefold())
        try:
            decoded = raw_bytes.decode(candidate)
        except (LookupError, UnicodeDecodeError):
            continue
        parser = _TextExtractor()
        parser.feed(decoded)
        text = parser.text()
        if "campeonato de primera division 2016" in _fold(text):
            return text, candidate
    raise RSSSFSchemaError(
        "RSSSF Argentina 2016 HTML could not be decoded with a supported charset "
        "while preserving the Primera Division heading"
    )


def _bounded_primera_lines(text: str) -> list[str]:
    lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    heading_idx = next(
        (
            index
            for index, line in enumerate(lines)
            if "campeonato de primera division 2016" in _fold(line)
        ),
        None,
    )
    if heading_idx is None:
        raise RSSSFSchemaError("RSSSF Argentina 2016 Primera Division heading not found")

    start_idx = next(
        (
            index
            for index in range(heading_idx + 1, len(lines))
            if _fold(lines[index]) == "round 1:"
        ),
        None,
    )
    if start_idx is None:
        raise RSSSFSchemaError("RSSSF Argentina 2016 Round 1 boundary not found")

    end_idx = next(
        (
            index
            for index in range(start_idx + 1, len(lines))
            if _fold(lines[index]) == "relegation"
        ),
        None,
    )
    if end_idx is None:
        raise RSSSFSchemaError("RSSSF Argentina 2016 Relegation boundary not found")

    return lines[start_idx:end_idx]


def _match_external_id(
    *,
    match_date: date,
    round_number: int,
    phase: RSSSFPhase,
    home_team: str,
    away_team: str,
) -> str:
    # Result is deliberately excluded: a later source correction to the score
    # must not manufacture a new provider-local match identity.
    stable_key = f"{match_date.isoformat()}|{round_number}|{phase}|{home_team}|{away_team}"
    digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:20]
    return f"rsssf-arg2016-{digest}"


def _parse_matches(lines: list[str]) -> tuple[RSSSFMatch, ...]:
    current_round: int | None = None
    current_group: str | None = None
    current_date: date | None = None
    final_mode = False
    matches: list[RSSSFMatch] = []

    for line in lines:
        round_match = _ROUND_RE.match(line)
        if round_match:
            current_round = int(round_match.group(1))
            current_group = None
            current_date = None
            final_mode = False
            continue

        if line in {"Group 1", "Group 2", "Intergroup"}:
            current_group = line
            current_date = None
            continue

        if line == "Final" and current_round == 17:
            current_group = "Final"
            current_date = None
            final_mode = True
            continue

        date_match = _DATE_RE.match(line)
        if date_match:
            month_token = date_match.group(1).title()
            current_date = date(2016, _MONTHS[month_token], int(date_match.group(2)))
            continue

        match = _MATCH_RE.match(line)
        if not match:
            continue
        if current_round is None:
            raise RSSSFSchemaError(f"match row appeared before a round header: {line!r}")
        if current_date is None:
            raise RSSSFSchemaError(f"match row appeared without an explicit date: {line!r}")

        if current_round <= 16:
            phase_by_group: dict[str | None, RSSSFPhase] = {
                "Group 1": "regular_group_1",
                "Group 2": "regular_group_2",
                "Intergroup": "regular_intergroup",
            }
            phase = phase_by_group.get(current_group)
            if phase is None:
                raise RSSSFSchemaError(
                    f"regular match row has no accepted subgroup in round {current_round}: {line!r}"
                )
        elif current_round == 17 and final_mode:
            phase = "final"
        elif current_round == 17:
            phase = "third_place_playoff"
        else:
            raise RSSSFSchemaError(f"unexpected Primera Division round {current_round}")

        home_team = match.group("home").strip()
        away_team = match.group("away").strip()
        venue = match.group("venue").strip()
        if not home_team or not away_team or not venue:
            raise RSSSFSchemaError(f"incomplete RSSSF match row: {line!r}")

        matches.append(
            RSSSFMatch(
                external_id=_match_external_id(
                    match_date=current_date,
                    round_number=current_round,
                    phase=phase,
                    home_team=home_team,
                    away_team=away_team,
                ),
                match_date=current_date,
                round_number=current_round,
                phase=phase,
                subgroup=current_group,
                home_team=home_team,
                away_team=away_team,
                home_score=int(match.group("home_score")),
                away_score=int(match.group("away_score")),
                venue=venue,
                source_line=line,
            )
        )

    return tuple(matches)


def _validate_complete_tournament(matches: tuple[RSSSFMatch, ...]) -> None:
    regular = tuple(match for match in matches if match.round_number <= 16)
    round_counts = Counter(match.round_number for match in matches)
    phase_counts = Counter(match.phase for match in matches)
    team_labels = {match.home_team for match in matches} | {match.away_team for match in matches}
    regular_team_counts: Counter[str] = Counter()
    for match in regular:
        regular_team_counts[match.home_team] += 1
        regular_team_counts[match.away_team] += 1

    expected_round_counts = Counter({**{round_number: 15 for round_number in range(1, 17)}, 17: 2})
    expected_phase_counts: Counter[RSSSFPhase] = Counter(
        {
            "regular_group_1": 105,
            "regular_group_2": 105,
            "regular_intergroup": 30,
            "third_place_playoff": 1,
            "final": 1,
        }
    )

    failures: list[str] = []
    if len(matches) != 242:
        failures.append(f"matches={len(matches)} expected=242")
    if len(regular) != 240:
        failures.append(f"regular_matches={len(regular)} expected=240")
    if round_counts != expected_round_counts:
        failures.append(f"round_counts={dict(sorted(round_counts.items()))}")
    if phase_counts != expected_phase_counts:
        failures.append(f"phase_counts={dict(sorted(phase_counts.items()))}")
    if len(team_labels) != 30:
        failures.append(f"team_labels={len(team_labels)} expected=30")
    if set(regular_team_counts.values()) != {16} or len(regular_team_counts) != 30:
        failures.append(
            "regular team match counts are not exactly 16 for each of 30 provider-local labels"
        )
    if len({match.external_id for match in matches}) != 242:
        failures.append("provider-local match ids are not unique")

    round_17 = tuple(match for match in matches if match.round_number == 17)
    if len(round_17) != 2:
        failures.append("round 17 does not contain exactly two matches")
    else:
        third_place = next(
            (match for match in round_17 if match.phase == "third_place_playoff"), None
        )
        final = next((match for match in round_17 if match.phase == "final"), None)
        if third_place is None or third_place.match_date != date(2016, 5, 28):
            failures.append("third-place playoff is not explicitly dated 2016-05-28")
        if final is None or final.match_date != date(2016, 5, 29):
            failures.append("final is not explicitly dated 2016-05-29")

    if failures:
        raise RSSSFSchemaError(
            "RSSSF Argentina 2016 tournament completeness gate failed: " + "; ".join(failures)
        )


def parse_argentina_2016_document(
    raw_bytes: bytes,
    *,
    content_type: str,
    fetched_at: datetime | None = None,
    source_url: str = RSSSF_ARGENTINA_2016_URL,
) -> RSSSFArgentina2016Snapshot:
    """Parse and certify the one reviewed RSSSF Argentina 2016 document."""

    text, decoded_charset = _extract_text(raw_bytes, content_type=content_type)
    matches = _parse_matches(_bounded_primera_lines(text))
    _validate_complete_tournament(matches)
    return RSSSFArgentina2016Snapshot(
        source_url=source_url,
        fetched_at=fetched_at or datetime.now(UTC),
        content_type=content_type,
        decoded_charset=decoded_charset,
        raw_bytes=raw_bytes,
        matches=matches,
    )


class RSSSFArgentina2016Client:
    """Small bounded client for the certified RSSSF Argentina 2016 page."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        max_attempts: int = 4,
        backoff_seconds: float = 1.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds

    def fetch(self) -> RSSSFArgentina2016Snapshot:
        request = Request(
            RSSSF_ARGENTINA_2016_URL,
            method="GET",
            headers={
                "Accept": "text/html,*/*;q=0.8",
                "User-Agent": "football-intelligence/0.1",
            },
        )

        last_error: BaseException | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
                    status = int(response.status)
                    raw_bytes = response.read()
                    content_type = response.headers.get("Content-Type", "")
                if status != 200:
                    raise RSSSFHttpError(f"RSSSF returned HTTP {status}")
                return parse_argentina_2016_document(
                    raw_bytes,
                    content_type=content_type,
                    fetched_at=datetime.now(UTC),
                )
            except HTTPError as exc:
                last_error = exc
                retryable = 500 <= exc.code <= 599
                if not retryable or attempt == self._max_attempts:
                    raise RSSSFHttpError(f"RSSSF returned HTTP {exc.code}") from exc
            except (TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise RSSSFHttpError(f"RSSSF transport error: {exc}") from exc

            if self._backoff_seconds:
                time.sleep(self._backoff_seconds * attempt)

        raise RSSSFHttpError(f"RSSSF request failed: {last_error}")
