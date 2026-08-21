from __future__ import annotations

import pytest

from football_intelligence.db.production_write_guard import (
    PRODUCTION_WRITE_CONFIRMATION_PHRASE,
    DatabaseTarget,
    resolve_database_target,
    safe_target_description,
    validate_database_url_scheme,
)

_LOCAL_URL = "postgresql://postgres:postgres@localhost:5432/db"
_REMOTE_URL = "postgresql://prod_user:secret@real-prod-host.neon.tech:5432/football_intelligence"


# ---------------------------------------------------------------------------
# resolve_database_target -- local passthrough
# ---------------------------------------------------------------------------


def test_none_passes_through_unresolved() -> None:
    assert resolve_database_target(None) is None


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
def test_local_urls_are_always_accepted_with_no_confirmation(url: str) -> None:
    target = resolve_database_target(url)
    assert target is not None
    assert target.is_local is True
    assert target.database_url == url


def test_malformed_scheme_is_rejected() -> None:
    with pytest.raises(SystemExit):
        resolve_database_target("mysql://postgres:postgres@localhost:5432/db")


# ---------------------------------------------------------------------------
# resolve_database_target -- remote requires the full explicit contract
# ---------------------------------------------------------------------------


def test_remote_url_with_no_confirmation_is_rejected() -> None:
    with pytest.raises(SystemExit):
        resolve_database_target(_REMOTE_URL)


def test_remote_url_with_only_allow_remote_write_is_rejected() -> None:
    with pytest.raises(SystemExit):
        resolve_database_target(_REMOTE_URL, allow_remote_write=True)


def test_remote_url_with_allow_and_confirm_target_but_no_phrase_is_rejected() -> None:
    with pytest.raises(SystemExit):
        resolve_database_target(
            _REMOTE_URL,
            allow_remote_write=True,
            confirm_target="production",
        )


def test_remote_url_with_wrong_confirm_target_is_rejected() -> None:
    with pytest.raises(SystemExit):
        resolve_database_target(
            _REMOTE_URL,
            allow_remote_write=True,
            confirm_target="staging",
            production_write_confirmation=PRODUCTION_WRITE_CONFIRMATION_PHRASE,
        )


def test_remote_url_with_wrong_phrase_is_rejected() -> None:
    with pytest.raises(SystemExit):
        resolve_database_target(
            _REMOTE_URL,
            allow_remote_write=True,
            confirm_target="production",
            production_write_confirmation="close enough",
        )


def test_remote_url_with_all_three_confirmations_is_accepted() -> None:
    target = resolve_database_target(
        _REMOTE_URL,
        allow_remote_write=True,
        confirm_target="production",
        production_write_confirmation=PRODUCTION_WRITE_CONFIRMATION_PHRASE,
    )
    assert target == DatabaseTarget(
        database_url=_REMOTE_URL, is_local=False, host="real-prod-host.neon.tech"
    )


# ---------------------------------------------------------------------------
# validate_database_url_scheme -- read-only preflight's lighter check
# ---------------------------------------------------------------------------


def test_scheme_validator_accepts_local_and_remote_postgres_urls() -> None:
    assert validate_database_url_scheme(_LOCAL_URL) == _LOCAL_URL
    assert validate_database_url_scheme(_REMOTE_URL) == _REMOTE_URL


def test_scheme_validator_rejects_non_postgres_scheme() -> None:
    with pytest.raises(SystemExit):
        validate_database_url_scheme("mysql://user:pass@host/db")


def test_scheme_validator_rejects_blank_url() -> None:
    with pytest.raises(SystemExit):
        validate_database_url_scheme("   ")


# ---------------------------------------------------------------------------
# safe_target_description -- never leaks credentials
# ---------------------------------------------------------------------------


def test_safe_target_description_omits_user_and_password() -> None:
    description = safe_target_description(_REMOTE_URL)
    assert description == "postgresql://real-prod-host.neon.tech:5432/football_intelligence"
    assert "prod_user" not in description
    assert "secret" not in description


def test_safe_target_description_handles_query_string_secrets() -> None:
    url = "postgresql://user:hunter2@host.example.com:5432/db?sslmode=require&token=abc123"
    description = safe_target_description(url)
    assert "hunter2" not in description
    assert "abc123" not in description
    assert description == "postgresql://host.example.com:5432/db"


def test_safe_target_description_handles_host_less_local_socket_dsn() -> None:
    description = safe_target_description("postgresql:///football_intelligence_test")
    assert description == "postgresql://(local socket)/football_intelligence_test"
