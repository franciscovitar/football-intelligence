from __future__ import annotations

from collections.abc import Iterator

import pytest

# libpq environment variables capable of changing a connection's target
# identity (see db.target_parsing) -- cleared before every test so target-
# resolution tests are hermetic regardless of the shell/CI environment
# pytest happens to run in (e.g. this repository's own Database CI job
# exports PGHOST/PGPORT/PGDATABASE as ordinary local defaults for `psql`).
# Individual tests that need one set do so explicitly via monkeypatch.
_TARGET_IDENTITY_ENV_VARS = (
    "PGHOST",
    "PGHOSTADDR",
    "PGPORT",
    "PGDATABASE",
    "PGSERVICE",
    "PGSERVICEFILE",
)


@pytest.fixture(autouse=True)
def _clear_target_identity_env_vars(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in _TARGET_IDENTITY_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
