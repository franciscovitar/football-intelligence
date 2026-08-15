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
