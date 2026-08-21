"""Shared explicit-opt-in contract for jobs that may write to a REMOTE
(production) PostgreSQL database, layered on top of -- never a replacement
for -- `db.local_safety.validate_local_database_url`'s strict local-only
rule.

`validate_local_database_url` stays exactly as it was: it always rejects any
non-local host, unconditionally, for callers that must never accept a
remote database under any circumstances. This module is for the narrow,
separate case of a job whose whole purpose (V1 Closure Pass A) is to
eventually write certified evidence to the real production database, but
only after a human has explicitly, unmistakably said so.

Both this module and `db.local_safety` resolve the actual connection target
through the same primitive, `db.target_parsing.parse_database_target` --
never `urllib.parse.urlsplit`, which cannot see libpq routing parameters
such as `hostaddr` or a query-string `host=` override (see
`target_parsing`'s module docstring for the full rationale). "Local" means
exactly the same thing to every caller in this repository.

## Why FOUR separate signals, not one flag

A single `--production` boolean is too easy to pass by habit or by copying
a command from shell history. `resolve_database_target()` requires ALL of
the following at once before a remote URL is ever accepted:

1. `--allow-remote-write` -- a plain opt-in switch.
2. `--confirm-target production` -- must equal the literal string
   `"production"`, so a copy-pasted `--confirm-target staging` (or a typo)
   still fails closed.
3. `--production-write-confirmation` -- must equal the exact, fixed
   `PRODUCTION_WRITE_CONFIRMATION_PHRASE` below, typed deliberately on the
   command line. This proves "I intend to write to production."
4. `--confirm-database-target` -- must equal the exact
   `safe_target_description()` of the parsed `--database-url`
   (`postgresql://<host>[:<port>]/<dbname>`, no username/password/query
   string). This proves "I intend to write to *this* production database" --
   signal 3 alone would still pass unchanged if the DSN were later edited to
   point at a different host or database while a stale copied confirmation
   phrase was left in place. Copying the exact target string forces a human
   to look at, and re-affirm, the real target every time it changes.

None of these four is a secret or a credential -- they are friction, not
authentication. The real access boundary is still "you must already
possess the real `--database-url`, which is never read from a `DATABASE_URL`
environment variable by any of these jobs." This module never reads any
environment variable itself.

## A remote write additionally requires a FULLY explicit target

Beyond the four signals above, a remote target is also rejected if
`db.target_parsing.parse_database_target` had to fall back to any ambient
`PG*` environment variable for host/hostaddr/port/dbname
(`ParsedDatabaseTarget.ambient_env_vars_used`), or if `port`/`dbname` are
still unset even after that fallback (meaning libpq's own compiled-in
default would apply silently). A one-time production write must never
depend on ambient shell state at all -- every target parameter must be
typed explicitly into `--database-url` itself. (Local classification and
the read-only preflight remain libpq-accurate and environment-aware, as
`target_parsing`'s own docstring explains -- this extra restriction applies
only to the remote-write confirmation path, where the stakes are highest.)

A local target (`localhost`/`127.0.0.1`/`::1`, or a host-less DSN resolving
to a local Unix socket) is always accepted, exactly like
`validate_local_database_url`, regardless of any of the above -- local
invocation never requires any of it.
"""

from __future__ import annotations

from dataclasses import dataclass

from football_intelligence.db.target_parsing import ParsedDatabaseTarget, parse_database_target

REQUIRED_CONFIRM_TARGET = "production"

PRODUCTION_WRITE_CONFIRMATION_PHRASE = "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE"


def _describe(target: ParsedDatabaseTarget) -> str:
    host = target.effective_host or "(local socket)"
    port = f":{target.port}" if target.port else ""
    dbname = target.dbname or "(default)"
    return f"postgresql://{host}{port}/{dbname}"


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    """A validated connection target: either a local instance, or a remote
    instance that passed the full explicit production-write confirmation.
    `is_local` lets a caller report which path was taken (e.g. in a
    machine-readable report) without re-parsing or re-logging the URL.
    `safe_description` is the exact same credential-free string
    `safe_target_description()` would compute for this URL -- it cannot
    disagree, because both are derived from the same parsed target."""

    database_url: str
    is_local: bool
    host: str | None
    safe_description: str


def resolve_database_target(
    database_url: str | None,
    *,
    allow_remote_write: bool = False,
    confirm_target: str | None = None,
    production_write_confirmation: str | None = None,
    confirm_database_target: str | None = None,
) -> DatabaseTarget | None:
    """Resolve `--database-url` to a validated connection target.

    Returns `None` when `database_url` is `None` (nothing to resolve --
    callers decide what "no URL supplied" means for them). Raises
    `SystemExit` for a malformed/ambiguous URL (see `target_parsing`), or
    for a remote URL missing any of the four required confirmation signals.
    Never consults an environment variable.
    """

    if database_url is None:
        return None

    parsed = parse_database_target(database_url)
    safe_description = _describe(parsed)

    if parsed.is_local:
        return DatabaseTarget(
            database_url=database_url,
            is_local=True,
            host=parsed.effective_host,
            safe_description=safe_description,
        )

    missing: list[str] = []
    if not allow_remote_write:
        missing.append("--allow-remote-write")
    if confirm_target != REQUIRED_CONFIRM_TARGET:
        missing.append(f"--confirm-target {REQUIRED_CONFIRM_TARGET!r}")
    if production_write_confirmation != PRODUCTION_WRITE_CONFIRMATION_PHRASE:
        missing.append(
            "--production-write-confirmation matching the exact required phrase "
            "(see PRODUCTION_WRITE_CONFIRMATION_PHRASE)"
        )
    if confirm_database_target != safe_description:
        missing.append(
            f"--confirm-database-target exactly matching the real parsed target "
            f"{safe_description!r} (run the read-only preflight first and copy its "
            "reported target deliberately -- a stale confirmation from a different "
            "host/database is rejected, not silently accepted)"
        )
    if parsed.ambient_env_vars_used:
        missing.append(
            "--database-url must not rely on ambient environment variables for its "
            f"target ({', '.join(parsed.ambient_env_vars_used)} currently supply part of "
            "it) -- a production write requires every target parameter (host/hostaddr, "
            "port, dbname) typed explicitly into --database-url itself, never inherited "
            "from the shell environment"
        )
    if parsed.port is None:
        missing.append(
            "--database-url must specify an explicit port (e.g. :5432) for a production "
            "write -- an implicit default port is not deterministic enough for this "
            "confirmation"
        )
    if parsed.dbname is None:
        missing.append(
            "--database-url must specify an explicit database name for a production write"
        )
    if missing:
        raise SystemExit(
            f"--database-url target {safe_description!r} is not local. Writing to a "
            "remote/production database requires ALL of the following, none of which were "
            f"fully satisfied: {', '.join(missing)}. A generic DATABASE_URL environment "
            "variable is never read automatically by this job, and no single flag alone "
            "unlocks a remote write."
        )

    return DatabaseTarget(
        database_url=database_url,
        is_local=False,
        host=parsed.effective_host,
        safe_description=safe_description,
    )


def validate_database_url_scheme(database_url: str) -> str:
    """Validate `database_url` parses to exactly one unambiguous PostgreSQL
    target, without restricting which host it may target. For read-only
    tooling (the production preflight) that must be able to inspect a
    remote database without requiring write-confirmation flags it has no
    use for. Raises `SystemExit` under the same conditions as
    `db.target_parsing.parse_database_target`."""

    parse_database_target(database_url)
    return database_url


def safe_target_description(database_url: str) -> str:
    """A safe, credential-free description of a database URL's real
    effective target for logs/reports: `postgresql://<host>[:<port>]/<dbname>`
    only -- never the user, password, or query string (which can carry
    connection secrets such as `sslmode`/pooler tokens on some providers).
    Always derived from the same `parse_database_target()` resolution
    `resolve_database_target()` uses, so it can never disagree with what was
    actually validated."""

    return _describe(parse_database_target(database_url))
