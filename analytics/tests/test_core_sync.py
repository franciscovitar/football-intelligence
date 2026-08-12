from datetime import date

import pytest

from football_intelligence.jobs.sync_core_leagues import (
    _resolve_window,
    check_request_budget,
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


def test_check_request_budget_accepts_default_shape() -> None:
    # 6 leagues * (1 fixture-list + 8 detail) = 54, within the default budget of 60.
    planned = check_request_budget(league_count=6, max_fixtures_per_league=8, request_budget=60)
    assert planned == 54


def test_check_request_budget_rejects_overspend_before_network() -> None:
    # A larger --max-fixtures-per-league must not silently exceed the default budget.
    with pytest.raises(SystemExit):
        check_request_budget(league_count=6, max_fixtures_per_league=20, request_budget=60)
