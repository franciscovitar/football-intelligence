from __future__ import annotations

from typing import Any

import pytest

from football_intelligence.jobs.preflight_production_state import (
    COMPETITION_CODE,
    SEASON_LABEL,
    build_parser,
    run_preflight,
)

_REMOTE_URL = "postgresql://user:pass@real-prod-host.example.com/db"


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

    args = build_parser().parse_args(["--database-url", _REMOTE_URL])
    assert args.database_url == _REMOTE_URL


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


class _FakeConnectionInfo:
    """Stands in for psycopg's `Connection.info` (`PQhost`/`PQhostaddr`/
    `PQdb`) -- pure client-side metadata, never a query. Defaults to
    exactly matching `_REMOTE_URL`'s parsed target."""

    def __init__(self, *, host: str = "real-prod-host.example.com", dbname: str = "db") -> None:
        self.host = host
        self.hostaddr = ""  # empty when the connection was made by hostname, not hostaddr
        self.dbname = dbname


class _FakeConnection:
    """A minimal fake standing in for a psycopg connection: every query this
    job could issue against a completely empty (freshly migrated, never
    bootstrapped) database returns "nothing found", and `commit()` raises --
    the preflight must never call it, on any code path."""

    def __init__(self, *, info: _FakeConnectionInfo | None = None) -> None:
        self.executed: list[str] = []
        self.rolled_back = False
        self.info = info if info is not None else _FakeConnectionInfo()

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


def test_transaction_is_set_read_only_as_the_very_first_sql_statement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """13. Before any inspection query runs, PostgreSQL itself is told to
    put the transaction in READ ONLY mode -- proven here by asserting it is
    literally the first SQL statement executed (the post-connection target
    verification that now runs just before it issues no SQL at all -- see
    the module's own comment on `connection.info` being pure client-side
    metadata)."""

    fake_connection = _FakeConnection()
    monkeypatch.setattr(
        "football_intelligence.jobs.preflight_production_state.connect",
        lambda database_url: fake_connection,
    )

    run_preflight(_REMOTE_URL)

    assert fake_connection.executed[0] == "SET TRANSACTION READ ONLY"


def test_preflight_never_writes_and_reports_expected_shape_against_an_empty_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_connection = _FakeConnection()
    monkeypatch.setattr(
        "football_intelligence.jobs.preflight_production_state.connect",
        lambda database_url: fake_connection,
    )

    report = run_preflight(_REMOTE_URL)

    # 14. inspection then rolls back -- never commits, on the success path.
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
    assert report["ambient_env_vars_used"] == []
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
        run_preflight(_REMOTE_URL)

    assert fake_connection.rolled_back is True


# ---------------------------------------------------------------------------
# 10. Post-connection verification: the printed target cannot disagree with
# what libpq actually connected to.
# ---------------------------------------------------------------------------


def test_preflight_raises_when_connected_host_disagrees_with_validated_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_connection = _FakeConnection(
        info=_FakeConnectionInfo(host="a-completely-different-host.example.com", dbname="db")
    )
    monkeypatch.setattr(
        "football_intelligence.jobs.preflight_production_state.connect",
        lambda database_url: fake_connection,
    )

    with pytest.raises(RuntimeError, match="Post-connection verification failed"):
        run_preflight(_REMOTE_URL)

    # Never even reaches SET TRANSACTION READ ONLY -- the mismatch is fatal
    # before any SQL is sent.
    assert fake_connection.executed == []
    assert fake_connection.rolled_back is True


def test_preflight_raises_when_connected_dbname_disagrees_with_validated_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_connection = _FakeConnection(
        info=_FakeConnectionInfo(host="real-prod-host.example.com", dbname="a_different_db")
    )
    monkeypatch.setattr(
        "football_intelligence.jobs.preflight_production_state.connect",
        lambda database_url: fake_connection,
    )

    with pytest.raises(RuntimeError, match="Post-connection verification failed"):
        run_preflight(_REMOTE_URL)


def test_preflight_skips_post_connect_check_for_a_local_socket_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local Unix-socket connection's PQhost() returns a socket directory
    path, not "localhost" -- comparing it would be a false-positive trap,
    so the check is skipped entirely for a local target."""

    fake_connection = _FakeConnection(
        info=_FakeConnectionInfo(host="/var/run/postgresql", dbname="football_intelligence_test")
    )
    monkeypatch.setattr(
        "football_intelligence.jobs.preflight_production_state.connect",
        lambda database_url: fake_connection,
    )

    report = run_preflight("postgresql:///football_intelligence_test")
    assert report["target"] == "postgresql://(local socket)/football_intelligence_test"


# ---------------------------------------------------------------------------
# Ambient environment variables are reported, never silently hidden.
# ---------------------------------------------------------------------------


def test_preflight_reports_ambient_env_vars_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGDATABASE", "db")
    fake_connection = _FakeConnection(
        info=_FakeConnectionInfo(host="real-prod-host.example.com", dbname="db")
    )
    monkeypatch.setattr(
        "football_intelligence.jobs.preflight_production_state.connect",
        lambda database_url: fake_connection,
    )

    report = run_preflight("postgresql://real-prod-host.example.com/")

    assert report["ambient_env_vars_used"] == ["PGDATABASE"]
    assert report["target"] == "postgresql://real-prod-host.example.com/db"
