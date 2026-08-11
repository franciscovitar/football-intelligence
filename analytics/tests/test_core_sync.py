from datetime import date

import pytest

from football_intelligence.jobs.sync_core_leagues import (
    _resolve_window,
    select_finished_fixture_ids,
)


def test_select_finished_fixture_ids_ignores_non_finished_and_sorts_latest() -> None:
    payload = {
        "response": [
            {"fixture": {"id": 1, "date": "2024-01-01T18:00:00+00:00", "status": {"short": "FT"}}},
            {"fixture": {"id": 2, "date": "2024-01-03T18:00:00+00:00", "status": {"short": "NS"}}},
            {"fixture": {"id": 3, "date": "2024-01-02T18:00:00+00:00", "status": {"short": "FT"}}},
        ]
    }
    assert select_finished_fixture_ids(payload, limit=1) == ["3"]


def test_explicit_window_is_deterministic() -> None:
    start = date(2024, 5, 1)
    end = date(2024, 5, 3)
    assert _resolve_window(explicit_from=start, explicit_to=end, lookback_days=3) == (start, end)


def test_explicit_window_rejects_reverse_dates() -> None:
    with pytest.raises(SystemExit):
        _resolve_window(
            explicit_from=date(2024, 5, 3),
            explicit_to=date(2024, 5, 1),
            lookback_days=3,
        )
