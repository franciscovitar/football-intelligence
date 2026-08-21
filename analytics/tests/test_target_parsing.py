from __future__ import annotations

import pytest

from football_intelligence.db.target_parsing import ParsedDatabaseTarget, parse_database_target

# ---------------------------------------------------------------------------
# 1. Normal localhost URL -> local accepted
# ---------------------------------------------------------------------------


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
def test_ordinary_local_urls_are_accepted(url: str) -> None:
    target = parse_database_target(url)
    assert target.is_local is True


# ---------------------------------------------------------------------------
# 2. localhost URL + remote hostaddr override -> MUST NOT be accepted as local
# ---------------------------------------------------------------------------


def test_localhost_with_remote_hostaddr_is_not_local() -> None:
    """libpq uses `hostaddr` as the real network address when both `host`
    and `hostaddr` are supplied -- `host` becomes verification/SNI-only.
    An authority hostname of `localhost` must never launder a real remote
    `hostaddr` into a local classification."""

    target = parse_database_target("postgresql://localhost/db?hostaddr=203.0.113.5")
    assert target == ParsedDatabaseTarget(
        effective_host="203.0.113.5", port=None, dbname="db", is_local=False
    )


def test_hostaddr_that_is_itself_local_is_accepted() -> None:
    """The inverse case is correctly local: if `hostaddr` genuinely points at
    a loopback address, the connection genuinely reaches this machine,
    regardless of what the unrelated `host` label says."""

    target = parse_database_target("postgresql://real-host.neon.tech/db?hostaddr=127.0.0.1")
    assert target.is_local is True
    assert target.effective_host == "127.0.0.1"


# ---------------------------------------------------------------------------
# 3. localhost URL + query host override -> MUST NOT be accepted as local
# ---------------------------------------------------------------------------


def test_query_string_host_override_is_not_local() -> None:
    """A URI query parameter literally named `host=` overrides the authority
    hostname for libpq -- invisible to `urllib.parse.urlsplit`, which only
    ever looks at the authority component."""

    target = parse_database_target("postgresql://localhost/db?host=evil.example.com")
    assert target.is_local is False
    assert target.effective_host == "evil.example.com"


def test_host_less_dsn_with_query_host_override_is_not_local() -> None:
    target = parse_database_target("postgresql:///db?host=evil.example.com")
    assert target.is_local is False
    assert target.effective_host == "evil.example.com"


# ---------------------------------------------------------------------------
# 4. Ambiguous/multi-host target -> fail closed if unsupported
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://localhost,otherhost.example.com/db",
        "postgresql://localhost:5432,otherhost.example.com:5432/db",
        "postgresql://localhost/db?hostaddr=127.0.0.1,203.0.113.5",
    ],
)
def test_multi_host_or_multi_hostaddr_dsn_is_rejected(url: str) -> None:
    with pytest.raises(SystemExit):
        parse_database_target(url)


def test_service_reference_is_rejected() -> None:
    """`service=` points at an external `pg_service.conf` entry whose real
    host/port/dbname are not present in the connection string at all --
    this module cannot resolve, and must not guess, the real target."""

    with pytest.raises(SystemExit):
        parse_database_target("postgresql://localhost/db?service=myservice")


def test_blank_url_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_database_target("   ")


def test_non_postgres_scheme_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_database_target("mysql://user:pass@localhost:5432/db")


def test_garbage_input_is_rejected() -> None:
    with pytest.raises(SystemExit):
        parse_database_target("not a connection string !!")


# ---------------------------------------------------------------------------
# 5. Normal single-host remote Neon-like URL + sslmode -> parses as remote
# ---------------------------------------------------------------------------


def test_ordinary_remote_neon_style_url_with_sslmode_parses_correctly() -> None:
    target = parse_database_target(
        "postgresql://prod_user:secret@real-prod-host.neon.tech:5432/"
        "football_intelligence?sslmode=require&channel_binding=require"
    )
    assert target == ParsedDatabaseTarget(
        effective_host="real-prod-host.neon.tech",
        port="5432",
        dbname="football_intelligence",
        is_local=False,
    )


def test_ordinary_remote_url_without_explicit_port_parses_correctly() -> None:
    target = parse_database_target("postgresql://user:pass@real-prod-host.example.com/db")
    assert target.is_local is False
    assert target.effective_host == "real-prod-host.example.com"
    assert target.port is None
    assert target.dbname == "db"
