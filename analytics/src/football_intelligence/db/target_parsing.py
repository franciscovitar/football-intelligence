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
is already required by every job in this package -- and fails closed
(`SystemExit`) on anything it cannot reduce to exactly one unambiguous
target.
"""

from __future__ import annotations

from dataclasses import dataclass

from psycopg import ProgrammingError
from psycopg.conninfo import conninfo_to_dict

LOCAL_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# libpq parameters that point at connection details this module cannot see
# or resolve from the DSN string alone -- a `pg_service.conf` entry can
# define an entirely different host/port/dbname than what is visible here.
_EXTERNAL_REFERENCE_PARAMS = ("service",)


@dataclass(frozen=True, slots=True)
class ParsedDatabaseTarget:
    """The single, unambiguous effective connection target libpq will
    actually use for a given connection string.

    `effective_host` is `hostaddr` when present (libpq uses it for the real
    network connection; `host` becomes verification/SNI-only in that case),
    otherwise `host`; `None` means a local Unix-domain socket
    (e.g. `postgresql:///dbname`), which is always local.
    """

    effective_host: str | None
    port: str | None
    dbname: str | None
    is_local: bool


def parse_database_target(database_url: str) -> ParsedDatabaseTarget:
    """Parse `database_url` into its single, unambiguous effective target.

    Raises `SystemExit` for: a blank or malformed/unparseable connection
    string; a `service`/`servicefile` reference (points at external,
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

    # `conninfo_to_dict` types values as `str | int` (a numeric-looking
    # keyword=value pair can come back as `int`) -- normalize everything
    # this module handles to `str | None` up front.
    def _as_str(value: object) -> str | None:
        return None if value is None else str(value)

    host = _as_str(params.get("host"))
    hostaddr = _as_str(params.get("hostaddr"))
    port = _as_str(params.get("port"))
    dbname = _as_str(params.get("dbname"))

    for label, value in (("host", host), ("hostaddr", hostaddr), ("port", port)):
        if value is not None and "," in value:
            raise SystemExit(
                f"--database-url specifies multiple comma-separated {label} values "
                f"({value!r}) -- a multi-host/multi-target DSN is ambiguous and is not "
                "supported by this repository's real-data jobs"
            )

    # libpq: when both `host` and `hostaddr` are supplied, `hostaddr` is the
    # actual network address the connection is made to; `host` is then used
    # only for TLS verification/SNI. The effective target for safety
    # classification must follow `hostaddr` whenever it is present.
    effective_host = hostaddr if hostaddr is not None else host

    is_local = effective_host is None or effective_host.lower() in LOCAL_DATABASE_HOSTS

    return ParsedDatabaseTarget(
        effective_host=effective_host,
        port=port,
        dbname=dbname,
        is_local=is_local,
    )
