from __future__ import annotations

import pytest

from football_intelligence.db.local_safety import validate_local_database_url


def test_none_passes_through_unvalidated() -> None:
    assert validate_local_database_url(None) is None


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://postgres:postgres@localhost:5432/db",
        "postgresql://postgres:postgres@127.0.0.1:5432/db",
        "postgresql://postgres:postgres@[::1]:5432/db",
        "postgres://postgres:postgres@localhost:5432/db",
        "postgresql:///football_intelligence_test",
    ],
)
def test_local_urls_are_accepted(url: str) -> None:
    assert validate_local_database_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@evil.example.com:5432/db",
        "postgresql://user:pass@10.0.0.5:5432/db",
        "mysql://postgres:postgres@localhost:5432/db",
        "postgresql://postgres:postgres@somehost/db",
    ],
)
def test_remote_or_ambiguous_urls_are_rejected(url: str) -> None:
    with pytest.raises(SystemExit):
        validate_local_database_url(url)
