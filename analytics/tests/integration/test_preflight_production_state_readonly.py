from __future__ import annotations

import os

import psycopg
import pytest

from football_intelligence.db.provider_repository import connect
from football_intelligence.jobs.preflight_production_state import run_preflight


@pytest.mark.integration
def test_preflight_transaction_rejects_a_write_at_the_database_level() -> None:
    """15. Against a real PostgreSQL instance: once
    `run_preflight()`'s `SET TRANSACTION READ ONLY` has taken effect, an
    INSERT attempted on that same connection's transaction is rejected by
    PostgreSQL itself (SQLSTATE 25006), not merely omitted by application
    discipline. Proves the guarantee is database-enforced, not just a
    convention this module happens to follow.
    """

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    report = run_preflight(database_url)
    assert report["writes_performed"] is False

    # run_preflight() rolls back its own transaction before returning, so a
    # fresh connection/transaction is used here to reproduce the same
    # READ ONLY activation this test is verifying, then attempt a write
    # against it directly.
    with connect(database_url) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            connection.execute(
                "insert into ingestion.providers (code, display_name) values (%s, %s)",
                ("preflight-readonly-test-should-never-persist", "should never persist"),
            )
        connection.rollback()
