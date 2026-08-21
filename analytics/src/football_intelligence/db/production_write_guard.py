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

## Why three separate signals, not one flag

A single `--production` boolean is too easy to pass by habit or by copying
a command from shell history. `resolve_database_target()` requires ALL of
the following at once before a remote URL is ever accepted:

1. `--allow-remote-write` -- a plain opt-in switch.
2. `--confirm-target production` -- must equal the literal string
   `"production"`, so a copy-pasted `--confirm-target staging` (or a typo)
   still fails closed.
3. `--production-write-confirmation` -- must equal the exact, fixed
   `PRODUCTION_WRITE_CONFIRMATION_PHRASE` below, typed deliberately on the
   command line.

None of these three is a secret or a credential -- they are friction, not
authentication. The real access boundary is still "you must already
possess the real `--database-url`, which is never read from a `DATABASE_URL`
environment variable by any of these jobs." This module never reads any
environment variable itself.

A local target (`localhost`/`127.0.0.1`/`::1`, or a host-less DSN resolving
to a local Unix socket) is always accepted, exactly like
`validate_local_database_url`, regardless of these three flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from football_intelligence.db.local_safety import (
    LOCAL_DATABASE_HOSTS,
    LOCAL_DATABASE_SCHEMES,
)

REQUIRED_CONFIRM_TARGET = "production"

PRODUCTION_WRITE_CONFIRMATION_PHRASE = "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE"


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    """A validated connection target: either a local instance, or a remote
    instance that passed the full explicit production-write confirmation.
    `is_local` lets a caller report which path was taken (e.g. in a
    machine-readable report) without re-parsing or re-logging the URL."""

    database_url: str
    is_local: bool
    host: str | None


def resolve_database_target(
    database_url: str | None,
    *,
    allow_remote_write: bool = False,
    confirm_target: str | None = None,
    production_write_confirmation: str | None = None,
) -> DatabaseTarget | None:
    """Resolve `--database-url` to a validated connection target.

    Returns `None` when `database_url` is `None` (nothing to resolve --
    callers decide what "no URL supplied" means for them). Raises
    `SystemExit` for a malformed URL, or for a remote URL missing any of the
    three required confirmation signals. Never consults an environment
    variable.
    """

    if database_url is None:
        return None

    parsed = urlsplit(database_url)
    if parsed.scheme not in LOCAL_DATABASE_SCHEMES:
        raise SystemExit(
            f"--database-url must be a postgresql:// URL; refusing ambiguous scheme "
            f"{parsed.scheme!r}"
        )

    hostname = parsed.hostname
    is_local = hostname is None or hostname.lower() in LOCAL_DATABASE_HOSTS
    if is_local:
        return DatabaseTarget(database_url=database_url, is_local=True, host=hostname)

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
    if missing:
        raise SystemExit(
            f"--database-url host {hostname!r} is not local. Writing to a remote/production "
            "database requires ALL of the following, none of which were fully satisfied: "
            f"{', '.join(missing)}. A generic DATABASE_URL environment variable is never read "
            "automatically by this job, and no single flag alone unlocks a remote write."
        )

    return DatabaseTarget(database_url=database_url, is_local=False, host=hostname)


def validate_database_url_scheme(database_url: str) -> str:
    """Reject a malformed/non-PostgreSQL URL before any connection is
    attempted, without restricting which host it may target. For read-only
    tooling (the production preflight) that must be able to inspect a
    remote database without requiring write-confirmation flags it has no
    use for."""

    if not database_url.strip():
        raise SystemExit("--database-url must not be blank")
    parsed = urlsplit(database_url)
    if parsed.scheme not in LOCAL_DATABASE_SCHEMES:
        raise SystemExit(
            f"--database-url must be a postgresql:// URL; refusing ambiguous scheme "
            f"{parsed.scheme!r}"
        )
    return database_url


def safe_target_description(database_url: str) -> str:
    """A safe, credential-free description of a database URL's target for
    logs/reports: scheme + host (+ port) + database name only -- never the
    user, password, or query string (which can carry connection secrets
    such as `sslmode`/pooler tokens on some providers)."""

    parsed = urlsplit(database_url)
    host = parsed.hostname or "(local socket)"
    port = f":{parsed.port}" if parsed.port else ""
    dbname = parsed.path.lstrip("/") or "(default)"
    return f"{parsed.scheme}://{host}{port}/{dbname}"
