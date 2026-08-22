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
        host="localhost",
        hostaddr="203.0.113.5",
        effective_host="203.0.113.5",
        port=None,
        dbname="db",
        is_local=False,
        ambient_env_vars_used=(),
    )


def test_hostaddr_that_is_itself_local_is_accepted() -> None:
    """The inverse case is correctly local: if `hostaddr` genuinely points at
    a loopback address, the connection genuinely reaches this machine,
    regardless of what the unrelated `host` label says."""

    target = parse_database_target("postgresql://real-host.neon.tech/db?hostaddr=127.0.0.1")
    assert target.is_local is True
    assert target.effective_host == "127.0.0.1"


def test_dns_hostname_only_dsn_keeps_host_and_hostaddr_separate() -> None:
    """`host` and `hostaddr` are exposed as two separate fields precisely so
    a caller (the read-only preflight's post-connection check) can tell
    "no hostaddr was ever part of this target" apart from "hostaddr was
    part of this target and happened to match" -- collapsing them into one
    value here would make that distinction impossible to make correctly
    downstream."""

    target = parse_database_target("postgresql://ep-example.neon.tech/db")
    assert target.host == "ep-example.neon.tech"
    assert target.hostaddr is None
    assert target.effective_host == "ep-example.neon.tech"


def test_explicit_host_and_hostaddr_dsn_keeps_both_fields() -> None:
    target = parse_database_target("postgresql://db.example.com/db?hostaddr=203.0.113.10")
    assert target.host == "db.example.com"
    assert target.hostaddr == "203.0.113.10"
    assert target.effective_host == "203.0.113.10"


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
        host="real-prod-host.neon.tech",
        hostaddr=None,
        effective_host="real-prod-host.neon.tech",
        port="5432",
        dbname="football_intelligence",
        is_local=False,
        ambient_env_vars_used=(),
    )


def test_ordinary_remote_url_without_explicit_port_parses_correctly() -> None:
    target = parse_database_target("postgresql://user:pass@real-prod-host.example.com/db")
    assert target.is_local is False
    assert target.effective_host == "real-prod-host.example.com"
    assert target.port is None
    assert target.dbname == "db"


# ---------------------------------------------------------------------------
# Ambient libpq environment variables (PGHOST/PGHOSTADDR/PGPORT/PGDATABASE/
# PGSERVICE/PGSERVICEFILE) -- real libpq consults these for any target
# parameter absent from the connection string itself, before its own
# compiled-in default. `conftest.py`'s autouse fixture clears all of them
# before every test; each test here sets only what it needs.
# ---------------------------------------------------------------------------


# 1. PGHOST=remote + host-less DSN -> NOT classified local
def test_host_less_dsn_with_remote_pghost_is_not_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """A host-less DSN would otherwise be assumed to resolve to a local
    Unix-domain socket -- but real libpq fills the unset `host` parameter
    from `PGHOST` first, so a remote `PGHOST` means a real TCP connection
    to that remote host, not a local socket."""

    monkeypatch.setenv("PGHOST", "remote.example.com")
    target = parse_database_target("postgresql:///db")
    assert target.is_local is False
    assert target.effective_host == "remote.example.com"
    assert target.ambient_env_vars_used == ("PGHOST",)


# 2. PGHOSTADDR=remote + postgresql://localhost/db -> NOT safely local
def test_localhost_dsn_with_remote_pghostaddr_is_not_local(monkeypatch: pytest.MonkeyPatch) -> None:
    """`hostaddr` is absent from the DSN, so real libpq fills it from
    `PGHOSTADDR` -- the real network address reached is the environment
    value, not the DSN's `localhost` label (`host` becomes verification/
    SNI-only once `hostaddr` is known, exactly like the explicit-DSN case)."""

    monkeypatch.setenv("PGHOSTADDR", "203.0.113.9")
    target = parse_database_target("postgresql://localhost/db")
    assert target.is_local is False
    assert target.effective_host == "203.0.113.9"
    assert target.ambient_env_vars_used == ("PGHOSTADDR",)


def test_pghost_that_is_itself_local_does_not_break_a_host_less_local_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact scenario this repository's own Database CI job creates
    (PGHOST=localhost as an ordinary local default for `psql`): a host-less
    DSN must still classify as local, not be blanket-rejected merely
    because *some* PG* variable happens to be set."""

    monkeypatch.setenv("PGHOST", "localhost")
    target = parse_database_target("postgresql:///db")
    assert target.is_local is True
    assert target.effective_host == "localhost"
    assert target.ambient_env_vars_used == ("PGHOST",)


# 3. PGPORT set + DSN without explicit port -> target cannot silently differ
def test_pgport_is_incorporated_when_dsn_omits_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGPORT", "6543")
    target = parse_database_target("postgresql://real-prod-host.example.com/db")
    assert target.port == "6543"
    assert target.ambient_env_vars_used == ("PGPORT",)


def test_explicit_port_in_dsn_wins_over_pgport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGPORT", "6543")
    target = parse_database_target("postgresql://real-prod-host.example.com:5432/db")
    assert target.port == "5432"
    assert target.ambient_env_vars_used == ()


# 4. PGDATABASE set + DSN without explicit dbname -> target cannot silently differ
def test_pgdatabase_is_incorporated_when_dsn_omits_dbname(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGDATABASE", "football_intelligence")
    target = parse_database_target("postgresql://real-prod-host.example.com/")
    assert target.dbname == "football_intelligence"
    assert target.ambient_env_vars_used == ("PGDATABASE",)


def test_explicit_dbname_in_dsn_wins_over_pgdatabase(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGDATABASE", "wrong_db")
    target = parse_database_target("postgresql://real-prod-host.example.com/db")
    assert target.dbname == "db"
    assert target.ambient_env_vars_used == ()


# 5. PGSERVICE set -> fail closed, regardless of DSN content
def test_pgservice_env_var_fails_closed_even_without_service_in_dsn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGSERVICE", "myservice")
    with pytest.raises(SystemExit):
        parse_database_target("postgresql://localhost/db")


def test_pgservicefile_env_var_also_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGSERVICEFILE", "/home/user/.pg_service.conf")
    with pytest.raises(SystemExit):
        parse_database_target("postgresql://localhost/db")


# 6. explicit normal localhost host/port/dbname + no conflicting target
# environment -> local accepted (already covered by
# test_ordinary_local_urls_are_accepted, re-affirmed here with the autouse
# env-clearing fixture explicitly in view)
def test_fully_explicit_local_url_with_clean_environment_is_accepted() -> None:
    target = parse_database_target("postgresql://postgres:postgres@localhost:5432/db")
    assert target.is_local is True
    assert target.ambient_env_vars_used == ()


# 7. normal explicit Neon-like remote host/port/dbname + ordinary SSL
# environment/options -> remote accepted (no ambient target env vars
# involved at all)
def test_remote_url_with_ordinary_ssl_env_is_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PGSSLMODE", "require")
    monkeypatch.setenv("PGCONNECT_TIMEOUT", "10")
    target = parse_database_target(
        "postgresql://prod_user:secret@real-prod-host.neon.tech:5432/football_intelligence"
    )
    assert target.is_local is False
    assert target.ambient_env_vars_used == ()
