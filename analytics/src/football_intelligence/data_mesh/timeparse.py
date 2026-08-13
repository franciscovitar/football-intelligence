"""Shared timestamp/season parsing helpers for data mesh source adapters."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any


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


def normalize_season_label(value: Any) -> str:
    """Canonicalize a season label so split-year and single-year sources align.

    `2025` (a provider's season start year) becomes `2025-2026`; an
    already-split label such as `2025-2026` passes through unchanged.
    """

    if isinstance(value, int):
        return f"{value}-{value + 1}"
    if isinstance(value, str) and value.strip():
        text = value.strip()
        if text.isdigit() and len(text) == 4:
            year = int(text)
            return f"{year}-{year + 1}"
        return text
    return ""
