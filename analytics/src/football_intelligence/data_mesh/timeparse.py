"""Shared timestamp/season parsing helpers for data mesh source adapters."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

_CALENDAR_YEAR_PREFIX = "calendar-year:"


def parse_utc_timestamp(value: Any, *, assume_utc_if_naive: bool = True) -> datetime | None:
    """Parse an ISO-ish timestamp string, normalizing to UTC.

    Some providers omit an explicit timezone offset for timestamps that are
    otherwise UTC in practice; `assume_utc_if_naive` documents that choice at
    each call site instead of hiding it.
    """

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC) if assume_utc_if_naive else None
    return parsed.astimezone(UTC)


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def calendar_year_season_label(year: int | str) -> str:
    """Encode an explicit calendar-year season without losing its semantics.

    Data Mesh historically interprets a bare four-digit season label as the
    *start year* of a split-year season (`2025` -> `2025-2026`). Calendar-year
    competitions therefore need an explicit marker at the adapter boundary so
    downstream generic resolution can distinguish the two cases without a
    provider-specific conditional.
    """

    text = str(year).strip()
    if not (text.isdigit() and len(text) == 4):
        raise ValueError("calendar year season must be a four-digit year")
    return f"{_CALENDAR_YEAR_PREFIX}{text}"


def normalize_season_label(value: Any) -> str:
    """Canonicalize split-year, start-year and explicit calendar-year labels.

    - `2025` remains the historical start-year convention and becomes
      `2025-2026`;
    - `2025-2026` passes through unchanged;
    - `calendar-year:2016` becomes canonical `2016`, preserving a competition
      whose whole season is genuinely scoped to one calendar year.

    The explicit calendar-year marker exists to avoid silently converting a
    short/calendar competition into a nonexistent split-year season.
    """

    if isinstance(value, int):
        return f"{value}-{value + 1}"
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.startswith(_CALENDAR_YEAR_PREFIX):
            year = text.removeprefix(_CALENDAR_YEAR_PREFIX)
            return year if year.isdigit() and len(year) == 4 else ""
        if text.isdigit() and len(text) == 4:
            year = int(text)
            return f"{year}-{year + 1}"
        return text
    return ""
