from __future__ import annotations

import pytest

from football_intelligence.db.local_safety import validate_local_database_url


def test_none_passes_through_unvalidated() -> None:
    assert validate_local_database_url(None) is None


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:postgres@localhost:5432/db",
        "postgresql://postgres:postgres@127.0.0.1:5432/db",
        "postgresql://postgres:postgres@[::1]:5432/db",
        "postgres://postgres:postgres@localhost:5432/db",
        "postgresql:///football_intelligence_test",
    ],
)
def test_local_urls_are_accepted(url: str) -> None:
    assert validate_local_database_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@evil.example.com:5432/db",
        "postgresql://user:pass@10.0.0.5:5432/db",
        "mysql://postgres:postgres@localhost:5432/db",
        "postgresql://postgres:postgres@somehost/db",
    ],
)
def test_remote_or_ambiguous_urls_are_rejected(url: str) -> None:
    with pytest.raises(SystemExit):
        validate_local_database_url(url)


# ---------------------------------------------------------------------------
# 12. validate_local_database_url() also rejects the hostaddr/query
# override case -- the same effective-target resolution
# db.production_write_guard.resolve_database_target relies on
# (db.target_parsing.parse_database_target), so "local" cannot mean two
# different things depending on which caller asks.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost/db?hostaddr=203.0.113.5",
        "postgresql://localhost/db?host=evil.example.com",
        "postgresql:///db?host=evil.example.com",
    ],
)
def test_hostaddr_or_query_host_override_bypass_is_rejected(url: str) -> None:
    with pytest.raises(SystemExit):
        validate_local_database_url(url)


def test_hostaddr_that_is_itself_local_is_still_accepted() -> None:
    assert (
        validate_local_database_url("postgresql://real-host.example.com/db?hostaddr=127.0.0.1")
        is not None
    )


# ---------------------------------------------------------------------------
# Ambient libpq environment variables must also never let a genuinely
# remote target through as "local" here -- the same regression the
# hostaddr/query-host cases above cover, but for PG* environment fallback
# instead of DSN query-string tricks. `conftest.py`'s autouse fixture
# clears all relevant PG* vars before every test.
# ---------------------------------------------------------------------------


def test_host_less_dsn_with_remote_pghost_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGHOST", "remote.example.com")
    with pytest.raises(SystemExit):
        validate_local_database_url("postgresql:///db")


def test_localhost_dsn_with_remote_pghostaddr_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.9")
    with pytest.raises(SystemExit):
        validate_local_database_url("postgresql://localhost/db")


def test_host_less_dsn_with_local_pghost_is_still_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression guard: a benign PGHOST=localhost (this repository's own
    Database CI job sets exactly this) must not turn into a false
    rejection merely because some PG* variable is present."""

    monkeypatch.setenv("PGHOST", "localhost")
    assert validate_local_database_url("postgresql:///db") is not None
