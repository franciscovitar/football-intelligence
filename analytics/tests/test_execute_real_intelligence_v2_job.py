from __future__ import annotations

import os

import pytest

from football_intelligence.jobs.execute_real_intelligence_v2 import build_parser


def test_database_url_is_a_required_cli_argument() -> None:
    """No `DATABASE_URL` environment fallback exists at all: `--database-url`
    is a required argparse argument, so omitting it is a hard CLI error
    before any job logic (or database connection) ever runs.
    """

    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_database_url_is_never_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://someone:somewhere@evil.example.com/db")
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
    # Confirm the parser truly never falls back to the env var even when set.
    assert os.environ["DATABASE_URL"] == "postgresql://someone:somewhere@evil.example.com/db"


def test_explicit_local_database_url_is_accepted_by_the_parser() -> None:
    args = build_parser().parse_args(
        ["--database-url", "postgresql://postgres:postgres@localhost:5432/db"]
    )
    assert args.database_url == "postgresql://postgres:postgres@localhost:5432/db"
    assert args.allow_remote_write is False
    assert args.confirm_target is None
    assert args.production_write_confirmation is None
    assert args.confirm_database_target is None


def test_localhost_url_with_remote_hostaddr_is_rejected_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "execute_real_intelligence_v2",
            "--database-url",
            "postgresql://localhost/db?hostaddr=203.0.113.5",
        ],
    )
    from football_intelligence.jobs.execute_real_intelligence_v2 import main

    with pytest.raises(SystemExit):
        main()


# ---------------------------------------------------------------------------
# V1 Closure Pass A/B preparation: remote (production) execution requires the
# full explicit production-write confirmation, never a plain remote URL.
# ---------------------------------------------------------------------------


def test_remote_database_url_without_confirmation_is_rejected_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "execute_real_intelligence_v2",
            "--database-url",
            "postgresql://user:pass@real-prod-host.example.com/db",
        ],
    )
    from football_intelligence.jobs.execute_real_intelligence_v2 import main

    with pytest.raises(SystemExit):
        main()


def test_remote_database_url_with_partial_confirmation_is_rejected_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "execute_real_intelligence_v2",
            "--database-url",
            "postgresql://user:pass@real-prod-host.example.com/db",
            "--allow-remote-write",
            "--confirm-target",
            "production",
            # --production-write-confirmation deliberately omitted
        ],
    )
    from football_intelligence.jobs.execute_real_intelligence_v2 import main

    with pytest.raises(SystemExit):
        main()


def test_remote_database_url_with_wrong_database_target_confirmation_is_rejected_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All three generic confirmations correct, but --confirm-database-target
    names a different host -- must still fail closed."""

    monkeypatch.setattr(
        "sys.argv",
        [
            "execute_real_intelligence_v2",
            "--database-url",
            "postgresql://user:pass@real-prod-host.example.com/db",
            "--allow-remote-write",
            "--confirm-target",
            "production",
            "--production-write-confirmation",
            "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE",
            "--confirm-database-target",
            "postgresql://a-different-host.example.com/db",
        ],
    )
    from football_intelligence.jobs.execute_real_intelligence_v2 import main

    with pytest.raises(SystemExit):
        main()
