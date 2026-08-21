"""Shared local-only PostgreSQL URL validation for jobs that write real data.

Extracted from `jobs/build_real_snapshot_v2.py` (Block 18) so every job that
connects to a database enforces the exact same rule: a bare `DATABASE_URL`
environment variable is never read automatically, and only an explicit
`--database-url` naming a clearly local instance is ever accepted. See
`docs/REAL_DATA_SNAPSHOT_V2.md`'s "Database safety" section for the full
rationale and `docs/REAL_DATA_SNAPSHOT_V2.md:331-334`'s explicit handoff
asking future DB-connecting jobs to reuse this pattern.

`validate_local_database_url` NEVER accepts a remote database -- that
invariant is unchanged. Its implementation now delegates to
`db.target_parsing.parse_database_target`, the same libpq-aware effective-
target resolver `db.production_write_guard.resolve_database_target` uses,
so "local" cannot mean two different things depending on which caller asks
(a `postgresql://localhost/db?hostaddr=<remote>` DSN, for example, must be
rejected here exactly as it is there -- `urllib.parse.urlsplit` alone
cannot see `hostaddr` at all).
"""

from __future__ import annotations

from football_intelligence.db.target_parsing import (
    LOCAL_DATABASE_HOSTS as LOCAL_DATABASE_HOSTS,
)
from football_intelligence.db.target_parsing import parse_database_target

# Re-exported for backward compatibility with any existing importer; no
# longer used internally (parse_database_target rejects a non-PostgreSQL
# connection string itself, via psycopg's own conninfo parser).
LOCAL_DATABASE_SCHEMES = frozenset({"postgresql", "postgres"})


def validate_local_database_url(database_url: str | None) -> str | None:
    """Reject anything that is not clearly, unambiguously a local PostgreSQL
    instance.

    Called for any optional database read or write path -- a surprising
    remote connection is refused by default, before any socket is opened. A
    `DATABASE_URL` environment variable is never consulted here; only an
    explicit `--database-url` CLI value should ever reach this function.
    """

    if database_url is None:
        return None
    target = parse_database_target(database_url)
    if not target.is_local:
        raise SystemExit(
            f"--database-url effective host {target.effective_host!r} is not a recognized "
            "local database (localhost/127.0.0.1/::1). Refusing to connect to a "
            "remote/ambiguous database -- a generic DATABASE_URL environment variable is "
            "never read automatically by this job."
        )
    return database_url
