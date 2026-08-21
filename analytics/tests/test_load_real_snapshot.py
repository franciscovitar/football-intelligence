from __future__ import annotations

import os

import pytest

from football_intelligence.db.production_write_guard import PRODUCTION_WRITE_CONFIRMATION_PHRASE
from football_intelligence.jobs.load_real_snapshot import build_parser


def test_database_url_is_a_required_cli_argument() -> None:
    """No `DATABASE_URL` environment fallback exists at all: `--database-url`
    is a required argparse argument, so omitting it is a hard CLI error
    before any job logic (or database connection) ever runs. This closes the
    prior inconsistency where this loader alone accepted a bare
    `os.environ.get("DATABASE_URL")` fallback.
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


def test_remote_database_url_without_confirmation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["load_real_snapshot", "--database-url", "postgresql://user:pass@prod.example.com/db"],
    )
    from football_intelligence.jobs.load_real_snapshot import main

    with pytest.raises(SystemExit):
        main()


def test_remote_database_url_with_full_confirmation_passes_target_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full confirmation resolves the target successfully (the job then
    proceeds to actually connect, which this unit test does not exercise --
    covered by the shared `db.production_write_guard` tests instead)."""

    from football_intelligence.db.production_write_guard import resolve_database_target

    target = resolve_database_target(
        "postgresql://user:pass@prod.example.com/db",
        allow_remote_write=True,
        confirm_target="production",
        production_write_confirmation=PRODUCTION_WRITE_CONFIRMATION_PHRASE,
    )
    assert target is not None
    assert target.is_local is False
