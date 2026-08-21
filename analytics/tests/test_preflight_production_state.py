from __future__ import annotations

from typing import Any

import pytest

from football_intelligence.jobs.preflight_production_state import (
    COMPETITION_CODE,
    SEASON_LABEL,
    build_parser,
    run_preflight,
)


def test_database_url_is_a_required_cli_argument() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_database_url_is_never_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://someone:somewhere@evil.example.com/db")
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_remote_url_is_accepted_without_any_confirmation_flags() -> None:
    """This command is read-only, so a remote target needs no production-write
    confirmation -- unlike the write-capable jobs."""

    args = build_parser().parse_args(
        ["--database-url", "postgresql://user:pass@real-prod-host.example.com/db"]
    )
    assert args.database_url == "postgresql://user:pass@real-prod-host.example.com/db"


def test_parser_accepts_any_scheme_string_scheme_validation_happens_in_main() -> None:
    """`build_parser()` itself does not validate the URL's scheme -- that
    check (`validate_database_url_scheme`, exercised directly in
    `test_production_write_guard.py`) happens in `main()`, after parsing,
    before any connection is attempted."""

    args = build_parser().parse_args(["--database-url", "mysql://user:pass@host/db"])
    assert args.database_url == "mysql://user:pass@host/db"


class _FakeCursor:
    def __init__(self, value: Any) -> None:
        self._value = (value,) if value is not None else None

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._value


class _FakeConnection:
    """A minimal fake standing in for a psycopg connection: every query this
    job could issue against a completely empty (freshly migrated, never
    bootstrapped) database returns "nothing found", and `commit()` raises --
    the preflight must never call it, on any code path."""

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.rolled_back = False

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _FakeCursor:
        self.executed.append(sql)
        normalized = " ".join(sql.split()).lower()
        if "count(*)" in normalized:
            return _FakeCursor(0)
        # every id/scope/timestamp lookup: nothing exists yet
        return _FakeCursor(None)

    def rollback(self) -> None:
        self.rolled_back = True

    def commit(self) -> None:  # pragma: no cover - must never be called
        raise AssertionError("preflight must never commit")


def test_preflight_never_writes_and_reports_expected_shape_against_an_empty_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_connection = _FakeConnection()
    monkeypatch.setattr(
        "football_intelligence.jobs.preflight_production_state.connect",
        lambda database_url: fake_connection,
    )

    report = run_preflight("postgresql://user:pass@real-prod-host.example.com/db")

    assert fake_connection.rolled_back is True
    assert not any(
        keyword in " ".join(sql.split()).lower()
        for sql in fake_connection.executed
        for keyword in ("insert ", "update ", "delete ", "drop ", "truncate ", "alter ")
    )

    assert report["writes_performed"] is False
    assert report["competition_code"] == COMPETITION_CODE
    assert report["season_label"] == SEASON_LABEL
    assert report["target"] == "postgresql://real-prod-host.example.com/db"
    assert report["canonical"]["eng_pl_competition_exists"] is False
    assert report["canonical"]["eng_pl_2025_26_season_exists"] is False
    assert report["v2_product"]["active_team_scope"] is None
    assert report["v2_product"]["active_player_scope"] is None
    assert all(count == 0 for count in report["v2_product"]["view_row_counts"].values())
    assert report["data_mesh"]["source_observations_count"] == 0
    assert report["data_mesh"]["reconciliation_decisions_count"] == 0
    assert report["data_mesh"]["possible_test_smoke_leakage_count"] == 0


def test_preflight_rolls_back_even_when_a_query_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class _RaisingConnection(_FakeConnection):
        def execute(self, sql: str, params: tuple[Any, ...] = ()) -> _FakeCursor:
            raise RuntimeError("simulated query failure")

    fake_connection = _RaisingConnection()
    monkeypatch.setattr(
        "football_intelligence.jobs.preflight_production_state.connect",
        lambda database_url: fake_connection,
    )

    with pytest.raises(RuntimeError):
        run_preflight("postgresql://user:pass@real-prod-host.example.com/db")

    assert fake_connection.rolled_back is True
