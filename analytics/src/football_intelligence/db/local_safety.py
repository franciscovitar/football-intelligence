"""Shared local-only PostgreSQL URL validation for jobs that write real data.

Extracted from `jobs/build_real_snapshot_v2.py` (Block 18) so every job that
connects to a database enforces the exact same rule: a bare `DATABASE_URL`
environment variable is never read automatically, and only an explicit
`--database-url` naming a clearly local instance is ever accepted. See
`docs/REAL_DATA_SNAPSHOT_V2.md`'s "Database safety" section for the full
rationale and `docs/REAL_DATA_SNAPSHOT_V2.md:331-334`'s explicit handoff
asking future DB-connecting jobs to reuse this pattern.
"""

from __future__ import annotations

from urllib.parse import urlsplit

LOCAL_DATABASE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
LOCAL_DATABASE_SCHEMES = frozenset({"postgresql", "postgres"})


def validate_local_database_url(database_url: str | None) -> str | None:
    """Reject anything that is not clearly a local PostgreSQL instance.

    Called for any optional database read or write path -- a surprising
    remote connection is refused by default, before any socket is opened. A
    `DATABASE_URL` environment variable is never consulted here; only an
    explicit `--database-url` CLI value should ever reach this function.
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
    # No host component (e.g. `postgresql:///dbname`) resolves to a local
    # Unix-domain socket via libpq -- never a remote connection.
    if hostname is not None and hostname.lower() not in LOCAL_DATABASE_HOSTS:
        raise SystemExit(
            f"--database-url host {hostname!r} is not a recognized local database "
            "(localhost/127.0.0.1/::1). Refusing to connect to a remote/ambiguous "
            "database -- a generic DATABASE_URL environment variable is never read "
            "automatically by this job."
        )
    return database_url
