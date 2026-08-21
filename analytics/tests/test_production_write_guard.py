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
_REMOTE_TARGET_DESCRIPTION = "postgresql://real-prod-host.neon.tech:5432/football_intelligence"


def _fully_confirmed(**overrides: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "allow_remote_write": True,
        "confirm_target": "production",
        "production_write_confirmation": PRODUCTION_WRITE_CONFIRMATION_PHRASE,
        "confirm_database_target": _REMOTE_TARGET_DESCRIPTION,
    }
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# resolve_database_target -- local passthrough (no confirmation required)
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


def test_localhost_with_remote_hostaddr_is_never_accepted_as_local() -> None:
    """The same effective-target resolution `db.target_parsing` provides is
    what `resolve_database_target` relies on -- a `hostaddr` override must
    be caught here too, not merely in the lower-level parser's own tests."""

    with pytest.raises(SystemExit):
        # No confirmations supplied: if this were misclassified as local it
        # would be silently accepted; instead it must hit the remote path
        # and fail closed for lack of confirmation.
        resolve_database_target("postgresql://localhost/db?hostaddr=203.0.113.5")


# ---------------------------------------------------------------------------
# resolve_database_target -- remote requires the full explicit 4-part contract
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
        resolve_database_target(_REMOTE_URL, **_fully_confirmed(confirm_target="staging"))


def test_remote_url_with_wrong_phrase_is_rejected() -> None:
    with pytest.raises(SystemExit):
        resolve_database_target(
            _REMOTE_URL, **_fully_confirmed(production_write_confirmation="close enough")
        )


# ---------------------------------------------------------------------------
# 7-11: exact --confirm-database-target confirmation
# ---------------------------------------------------------------------------


def test_correct_generic_confirmations_but_missing_database_target_is_rejected() -> None:
    """7. All three generic confirmations correct, but
    `confirm_database_target` omitted -- must still reject the remote
    write. Proving "I intend to write to production" is not the same as
    proving "I intend to write to *this* production database."""

    with pytest.raises(SystemExit):
        resolve_database_target(
            _REMOTE_URL,
            allow_remote_write=True,
            confirm_target="production",
            production_write_confirmation=PRODUCTION_WRITE_CONFIRMATION_PHRASE,
        )


def test_database_target_confirmation_for_a_different_host_is_rejected() -> None:
    """8. A `confirm_database_target` that names a different, real-looking
    production host/db must be rejected -- it is not this connection's
    target."""

    with pytest.raises(SystemExit):
        resolve_database_target(
            _REMOTE_URL,
            **_fully_confirmed(
                confirm_database_target="postgresql://a-different-host.neon.tech:5432/other_db"
            ),
        )


def test_database_target_confirmation_for_a_different_dbname_is_rejected() -> None:
    """8b. Same host, different database name -- still a different target,
    still rejected."""

    with pytest.raises(SystemExit):
        resolve_database_target(
            _REMOTE_URL,
            **_fully_confirmed(
                confirm_database_target="postgresql://real-prod-host.neon.tech:5432/wrong_db"
            ),
        )


def test_exact_confirmed_target_is_accepted() -> None:
    """9. All four confirmations, with `confirm_database_target` exactly
    matching the parsed target -> accepted."""

    target = resolve_database_target(_REMOTE_URL, **_fully_confirmed())
    assert target == DatabaseTarget(
        database_url=_REMOTE_URL,
        is_local=False,
        host="real-prod-host.neon.tech",
        safe_description=_REMOTE_TARGET_DESCRIPTION,
    )


def test_changing_dsn_while_retaining_old_confirmed_target_is_rejected() -> None:
    """10. The DSN now points at a different host/db, but the copied
    `--confirm-database-target` value still names the OLD target -- this
    must fail closed, not silently accept the stale confirmation."""

    new_remote_url = "postgresql://prod_user:secret@a-new-prod-host.neon.tech:5432/other_db"
    with pytest.raises(SystemExit):
        resolve_database_target(
            new_remote_url,
            **_fully_confirmed(),  # still names the OLD target
        )


def test_local_invocation_does_not_require_database_target_confirmation() -> None:
    """Local invocation should not require the remote target confirmation at
    all -- confirming a target is only meaningful for the remote/production
    write path."""

    target = resolve_database_target(_LOCAL_URL)
    assert target is not None
    assert target.is_local is True


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


def test_scheme_validator_rejects_hostaddr_ambiguity_too() -> None:
    """The read-only preflight path shares the exact same underlying parser
    -- it doesn't classify local/remote, but a genuinely ambiguous DSN is
    still rejected before any connection is attempted."""

    with pytest.raises(SystemExit):
        validate_database_url_scheme("postgresql://host/db?service=myservice")


# ---------------------------------------------------------------------------
# safe_target_description -- never leaks credentials; 11. and 6.
# ---------------------------------------------------------------------------


def test_safe_target_description_omits_user_and_password() -> None:
    description = safe_target_description(_REMOTE_URL)
    assert description == _REMOTE_TARGET_DESCRIPTION
    assert "prod_user" not in description
    assert "secret" not in description


def test_safe_target_description_handles_query_string_secrets() -> None:
    """11. `password`/`sslpassword` are real libpq query parameters --
    both must be absent from the safe description."""

    url = "postgresql://user:hunter2@host.example.com:5432/db?sslmode=require&password=hunter3"
    description = safe_target_description(url)
    assert "hunter2" not in description
    assert "hunter3" not in description
    assert "sslmode" not in description
    assert description == "postgresql://host.example.com:5432/db"


def test_safe_target_description_handles_host_less_local_socket_dsn() -> None:
    description = safe_target_description("postgresql:///football_intelligence_test")
    assert description == "postgresql://(local socket)/football_intelligence_test"


def test_safe_target_description_reflects_effective_hostaddr_not_authority_host() -> None:
    """`safe_target_description` must never disagree with what
    `resolve_database_target`/`parse_database_target` actually validated --
    it reports the real effective host (`hostaddr`), never the
    possibly-misleading authority `host`."""

    description = safe_target_description("postgresql://localhost/db?hostaddr=203.0.113.5")
    assert description == "postgresql://203.0.113.5/db"


def test_database_target_resolution_safe_description_matches_standalone_function() -> None:
    """6. `DatabaseTarget.safe_description` (computed inside
    `resolve_database_target`) cannot disagree with a standalone
    `safe_target_description()` call on the same URL."""

    target = resolve_database_target(_REMOTE_URL, **_fully_confirmed())
    assert target is not None
    assert target.safe_description == safe_target_description(_REMOTE_URL)
