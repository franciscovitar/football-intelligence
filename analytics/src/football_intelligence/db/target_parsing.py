"""Shared, libpq-aware PostgreSQL connection-target parsing.

`db.local_safety.validate_local_database_url` and
`db.production_write_guard.resolve_database_target` both need to answer the
same question -- "which single network target will this connection string
actually reach?" -- and both must answer it identically, or "local" would
mean two different things depending on which caller you ask.

The naive approach, `urllib.parse.urlsplit(database_url).hostname`, is not
sufficient for a PostgreSQL/libpq connection string:

- PostgreSQL's `hostaddr` parameter, when present alongside `host`, is the
  actual network address libpq connects to -- `host` is then only used for
  TLS verification/SNI. A URI like `postgresql://localhost/db?hostaddr=1.2.3.4`
  has an authority hostname of `localhost` but a real network target of
  `1.2.3.4`. `urlsplit` cannot see `hostaddr` at all (it is a query
  parameter, not part of the authority).
- A URI query parameter can itself be named `host` (e.g.
  `postgresql://localhost/db?host=evil.example.com`) and libpq accepts and
  uses it, overriding the authority hostname entirely -- again invisible to
  `urlsplit`.
- `service=`/`servicefile=` parameters point libpq at an external
  `pg_service.conf` entry whose real host/port/dbname are not present in
  the connection string at all.
- A comma-separated multi-host/multi-port DSN (libpq's own multi-target
  failover syntax) does not have one single target to classify.

This module resolves all of that with psycopg's own libpq-aware conninfo
parser (`psycopg.conninfo.conninfo_to_dict`) -- no new dependency, psycopg
is already required by every job in this package.

## Ambient libpq environment variables (`PGHOST`, `PGHOSTADDR`, ...)

`conninfo_to_dict` is a pure string parser: it reflects only what is
literally written in `database_url` and never consults the process
environment (verified empirically -- `conninfo_to_dict("postgresql:///db")`
returns `{"dbname": "db"}` regardless of `PGHOST`). The real libpq
connection attempt this module's callers eventually make is not so
isolated: for any of `host`, `hostaddr`, `port`, `dbname` that is absent
from the connection string, real libpq falls back to the corresponding
`PGHOST`/`PGHOSTADDR`/`PGPORT`/`PGDATABASE` environment variable, in that
exact, unambiguous, documented order, before falling back to its own
compiled-in default (a local Unix-domain socket for `host`).

`parse_database_target` reproduces that exact precedence -- an unset DSN
parameter is filled from its environment variable before classification --
rather than either ignoring the environment (the original bug: a
`postgresql:///db` DSN with `PGHOST=remote.example.com` set would
otherwise be misclassified as an always-local Unix socket, when real libpq
would open a TCP connection to `remote.example.com`) or blanket-rejecting
any DSN whenever a `PG*` variable happens to be set (which would reject
even a genuinely, harmlessly local connection -- exactly what this
repository's own CI does: the `Database` Quality job sets
`PGHOST=localhost`/`PGPORT=5432`/`PGDATABASE=football_intelligence_test`
as ordinary local defaults for tooling like `psql`, and a host-less
`postgresql:///football_intelligence_test` DSN must still classify as
local there). This is not "clever merging" of an unknowable value: libpq's
environment-variable fallback is public, stable, documented behavior, so
reproducing it here keeps this module's answer identical to what libpq
will actually do, which is the whole point.

`PGSERVICE`/`PGSERVICEFILE` are handled differently and remain a hard
`SystemExit`: a service name resolves against an external
`pg_service.conf` file whose contents (host/hostaddr/port/dbname, or even
another `service=`) are not available to this lightweight parser at all --
there is no single environment-variable *value* to incorporate, only a
pointer to an external, unopened file. Even a DSN with no `service=`
param can still trigger a service lookup purely because `PGSERVICE` is set
in the environment, since libpq treats `service` itself as just another
parameter with an environment-variable fallback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict

LOCAL_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# libpq parameters that point at connection details this module cannot see
# or resolve from the DSN string alone -- a `pg_service.conf` entry can
# define an entirely different host/port/dbname than what is visible here.
_EXTERNAL_REFERENCE_PARAMS = ("service",)

# Always fail closed if either is set, regardless of DSN content: PGSERVICE
# can activate an external pg_service.conf lookup that supplies otherwise-
# unset target parameters, and this module has no reliable way to inspect
# that file's contents; PGSERVICEFILE only matters together with an active
# service lookup, but is treated the same conservative way since this
# module cannot prove one is not in play.
_SERVICE_ENV_VARS = ("PGSERVICE", "PGSERVICEFILE")

# libpq's own environment-variable fallback for each target-identity
# parameter, consulted only when the parameter is absent from the
# connection string itself -- the exact, documented precedence order this
# module reproduces, never a heuristic guess.
_TARGET_ENV_VAR_BY_PARAM = {
    "host": "PGHOST",
    "hostaddr": "PGHOSTADDR",
    "port": "PGPORT",
    "dbname": "PGDATABASE",
}


@dataclass(frozen=True, slots=True)
class ParsedDatabaseTarget:
    """The single, unambiguous effective connection target libpq will
    actually use for a given connection string, INCLUDING any ambient
    `PG*` environment-variable fallback libpq itself would apply.

    `effective_host` is `hostaddr` when present (libpq uses it for the real
    network connection; `host` becomes verification/SNI-only in that case),
    otherwise `host`; `None` means a local Unix-domain socket
    (e.g. `postgresql:///dbname` with no relevant environment override),
    which is always local.

    `ambient_env_vars_used` names every `PG*` environment variable (if any)
    that actually supplied a target-identity parameter this connection
    string itself left unset -- empty when the DSN alone fully determines
    the target. Callers with an especially high-stakes write path (a real
    production write) can require this to be empty, so the target used is
    never partly dependent on ambient shell state, only ever on what was
    typed into `--database-url` itself.
    """

    effective_host: str | None
    port: str | None
    dbname: str | None
    is_local: bool
    ambient_env_vars_used: tuple[str, ...]


def _as_str(value: object) -> str | None:
    # `conninfo_to_dict` types values as `str | int` (a numeric-looking
    # keyword=value pair can come back as `int`) -- normalize everything
    # this module handles to `str | None` up front.
    return None if value is None else str(value)


def _resolve_param(explicit: str | None, env_var: str) -> str | None:
    """libpq's real precedence for one target-identity parameter: the
    connection string's own explicit value wins; otherwise the environment
    variable's value (if set); otherwise unset (libpq's own compiled-in
    default applies, e.g. a local socket for `host`)."""

    if explicit is not None:
        return explicit
    from_env = os.environ.get(env_var)
    return from_env if from_env else None


def parse_database_target(database_url: str) -> ParsedDatabaseTarget:
    """Parse `database_url` into its single, unambiguous effective target,
    resolved through the exact same parameter precedence real libpq uses
    (connection string, then the relevant `PG*` environment variable).

    Raises `SystemExit` for: a blank or malformed/unparseable connection
    string; a `service`/`servicefile` reference, or `PGSERVICE`/
    `PGSERVICEFILE` set in the environment (points at external,
    uninspectable connection parameters); or a multi-host/multi-port DSN
    (this repository's real-data jobs only ever target exactly one
    database, so a failover-style multi-target DSN is unsupported here,
    not merely unclassifiable).
    """

    if not database_url or not database_url.strip():
        raise SystemExit("--database-url must not be blank")

    try:
        params = conninfo_to_dict(database_url)
    except ProgrammingError as exc:
        raise SystemExit(
            f"--database-url is not a valid PostgreSQL connection string: {exc}"
        ) from exc

    for param_name in _EXTERNAL_REFERENCE_PARAMS:
        if param_name in params:
            raise SystemExit(
                f"--database-url specifies {param_name!r}, which points at external, "
                "uninspectable connection parameters (a pg_service.conf entry) -- refusing "
                "to guess the real target rather than risk misclassifying it"
            )

    set_service_env_vars = [name for name in _SERVICE_ENV_VARS if os.environ.get(name)]
    if set_service_env_vars:
        raise SystemExit(
            f"{' and '.join(set_service_env_vars)} set in the environment -- a "
            "pg_service.conf entry can supply otherwise-unset host/hostaddr/port/dbname "
            "parameters libpq would use instead of this connection string's own values; "
            "refusing to guess the real target. Unset it, or pass every target parameter "
            "explicitly in --database-url."
        )

    explicit_host = _as_str(params.get("host"))
    explicit_hostaddr = _as_str(params.get("hostaddr"))
    explicit_port = _as_str(params.get("port"))
    explicit_dbname = _as_str(params.get("dbname"))

    for label, value in (
        ("host", explicit_host),
        ("hostaddr", explicit_hostaddr),
        ("port", explicit_port),
    ):
        if value is not None and "," in value:
            raise SystemExit(
                f"--database-url specifies multiple comma-separated {label} values "
                f"({value!r}) -- a multi-host/multi-target DSN is ambiguous and is not "
                "supported by this repository's real-data jobs"
            )

    # Reproduce libpq's real per-parameter precedence: explicit DSN value,
    # else the corresponding PG* environment variable, else unset. Track
    # which environment variables (if any) actually ended up supplying a
    # value, for callers that must require a fully explicit DSN.
    explicit_values = {
        "host": explicit_host,
        "hostaddr": explicit_hostaddr,
        "port": explicit_port,
        "dbname": explicit_dbname,
    }
    ambient_env_vars_used = tuple(
        env_var
        for param, env_var in _TARGET_ENV_VAR_BY_PARAM.items()
        if explicit_values[param] is None and os.environ.get(env_var)
    )

    host = _resolve_param(explicit_host, _TARGET_ENV_VAR_BY_PARAM["host"])
    hostaddr = _resolve_param(explicit_hostaddr, _TARGET_ENV_VAR_BY_PARAM["hostaddr"])
    port = _resolve_param(explicit_port, _TARGET_ENV_VAR_BY_PARAM["port"])
    dbname = _resolve_param(explicit_dbname, _TARGET_ENV_VAR_BY_PARAM["dbname"])

    # libpq: when both `host` and `hostaddr` are supplied (from either the
    # DSN or the environment), `hostaddr` is the actual network address the
    # connection is made to; `host` is then used only for TLS
    # verification/SNI. The effective target for safety classification must
    # follow `hostaddr` whenever it is present.
    effective_host = hostaddr if hostaddr is not None else host

    is_local = effective_host is None or effective_host.lower() in LOCAL_DATABASE_HOSTS

    return ParsedDatabaseTarget(
        effective_host=effective_host,
        port=port,
        dbname=dbname,
        is_local=is_local,
        ambient_env_vars_used=ambient_env_vars_used,
    )
