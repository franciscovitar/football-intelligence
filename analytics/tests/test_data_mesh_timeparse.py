from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from football_intelligence.data_mesh.timeparse import (
    calendar_year_season_label,
    normalize_season_label,
    parse_date,
    parse_utc_timestamp,
)


def test_parse_utc_timestamp_handles_z_suffix() -> None:
    assert parse_utc_timestamp("2025-08-22T18:30:00Z") == datetime(2025, 8, 22, 18, 30, tzinfo=UTC)


def test_parse_utc_timestamp_assumes_utc_when_naive() -> None:
    assert parse_utc_timestamp("2025-08-22T18:30:00") == datetime(2025, 8, 22, 18, 30, tzinfo=UTC)


def test_parse_utc_timestamp_can_reject_naive_values() -> None:
    assert parse_utc_timestamp("2025-08-22T18:30:00", assume_utc_if_naive=False) is None


def test_parse_utc_timestamp_rejects_garbage() -> None:
    assert parse_utc_timestamp("not-a-timestamp") is None
    assert parse_utc_timestamp(None) is None


def test_parse_date_roundtrip() -> None:
    assert parse_date("2025-08-22") == date(2025, 8, 22)
    assert parse_date("garbage") is None


def test_normalize_season_label_expands_single_start_year() -> None:
    assert normalize_season_label(2025) == "2025-2026"
    assert normalize_season_label("2025") == "2025-2026"


def test_normalize_season_label_keeps_already_split_label() -> None:
    assert normalize_season_label("2025-2026") == "2025-2026"


def test_explicit_calendar_year_roundtrips_without_becoming_split_season() -> None:
    encoded = calendar_year_season_label(2016)
    assert encoded == "calendar-year:2016"
    assert normalize_season_label(encoded) == "2016"
    assert normalize_season_label("calendar-year:20x6") == ""


def test_calendar_year_encoder_rejects_non_four_digit_year() -> None:
    with pytest.raises(ValueError, match="four-digit year"):
        calendar_year_season_label("16")


def test_normalize_season_label_blank_is_empty_string() -> None:
    assert normalize_season_label(None) == ""
    assert normalize_season_label("") == ""
