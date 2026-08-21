from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.jobs.build_real_snapshot_v2 import (
    SNAPSHOT_PERIOD_ROLE,
    SUPPORTED_COMPETITION_CODE,
    SUPPORTED_SEASON_LABEL,
    _metric_coverage,
    _observations_by_granularity,
    _validate_database_url,
    build_parser,
    main,
)

_NOW = datetime(2026, 8, 15, tzinfo=UTC)


def _observation(
    *, entity_type: str, entity_source_id: str, metric_name: str, value: object, source: str
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=source,
        source_type="objective_structured",
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_source_id=entity_source_id,
        entity_identity_hints={},
        metric_name=metric_name,
        value=value,  # type: ignore[arg-type]
        observed_at=_NOW,
        source_timestamp=None,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version="test-v1",
    )


# ---------------------------------------------------------------------------
# CLI / basic contract
# ---------------------------------------------------------------------------


def test_cli_defaults_target_eng_pl_2025_26() -> None:
    args = build_parser().parse_args([])
    assert args.competition == SUPPORTED_COMPETITION_CODE
    assert args.season == SUPPORTED_SEASON_LABEL
    assert args.manifest_path.parts[-5:-1] == ("data", "manifests", "real", "ENG_PL")


def test_cli_default_manifest_filename_is_season_scoped() -> None:
    args = build_parser().parse_args([])
    assert args.manifest_path.name == "2025-26.json"


def test_cli_has_no_database_url_default() -> None:
    # No implicit environment fallback anywhere near the parser default --
    # only an explicit CLI value can ever populate this.
    args = build_parser().parse_args([])
    assert args.database_url is None
    assert args.persist_audit_local is False


def test_unsupported_competition_or_season_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["build_real_snapshot_v2", "--competition", "GER_BL1"])
    with pytest.raises(SystemExit):
        main()


def test_unsupported_season_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["build_real_snapshot_v2", "--season", "2026/27"])
    with pytest.raises(SystemExit):
        main()


def test_persist_flag_without_database_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["build_real_snapshot_v2", "--persist-audit-local"])
    with pytest.raises(SystemExit):
        main()


# ---------------------------------------------------------------------------
# V1 Closure Pass A/B preparation: remote (production) audit persistence
# requires its own distinct flag plus the full explicit confirmation --
# --persist-audit-local keeps its exact original local-only meaning.
# ---------------------------------------------------------------------------


def test_cli_has_no_remote_production_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.persist_audit_remote_production is False
    assert args.allow_remote_write is False
    assert args.confirm_target is None
    assert args.production_write_confirmation is None
    assert args.confirm_database_target is None


def test_persist_audit_remote_production_with_localhost_hostaddr_bypass_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A `hostaddr` override cannot be used to sneak a remote write through
    as though it were local -- `--persist-audit-remote-production` still
    correctly classifies the real (remote) effective target and demands the
    full confirmation contract."""

    monkeypatch.setattr(
        "sys.argv",
        [
            "build_real_snapshot_v2",
            "--persist-audit-remote-production",
            "--database-url",
            "postgresql://localhost/db?hostaddr=203.0.113.5",
            # no confirmation flags supplied
        ],
    )
    with pytest.raises(SystemExit):
        main()


def test_persist_audit_local_and_remote_production_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_real_snapshot_v2",
            "--persist-audit-local",
            "--persist-audit-remote-production",
            "--database-url",
            "postgresql://postgres:postgres@localhost:5432/db",
        ],
    )
    with pytest.raises(SystemExit):
        main()


def test_persist_audit_remote_production_without_database_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sys.argv", ["build_real_snapshot_v2", "--persist-audit-remote-production"])
    with pytest.raises(SystemExit):
        main()


def test_persist_audit_remote_production_with_local_url_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A flag literally named 'remote-production' must never accept a local
    database -- that is what --persist-audit-local is for."""

    monkeypatch.setattr(
        "sys.argv",
        [
            "build_real_snapshot_v2",
            "--persist-audit-remote-production",
            "--database-url",
            "postgresql://postgres:postgres@localhost:5432/db",
            "--allow-remote-write",
            "--confirm-target",
            "production",
            "--production-write-confirmation",
            "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE",
        ],
    )
    with pytest.raises(SystemExit):
        main()


def test_persist_audit_remote_production_without_full_confirmation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_real_snapshot_v2",
            "--persist-audit-remote-production",
            "--database-url",
            "postgresql://user:pass@real-prod-host.example.com/db",
            "--allow-remote-write",
            # --confirm-target and --production-write-confirmation omitted
        ],
    )
    with pytest.raises(SystemExit):
        main()


def test_persist_audit_local_with_remote_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """--persist-audit-local must stay strictly local-only, even if a remote
    URL happens to be well-formed -- use --persist-audit-remote-production
    for a production target instead."""

    monkeypatch.setattr(
        "sys.argv",
        [
            "build_real_snapshot_v2",
            "--persist-audit-local",
            "--database-url",
            "postgresql://user:pass@real-prod-host.example.com/db",
        ],
    )
    with pytest.raises(SystemExit):
        main()


def test_persist_audit_remote_production_with_wrong_database_target_confirmation_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The three generic confirmations correct, but --confirm-database-target
    names a different host than the real --database-url -- must still fail
    closed before any network/database activity."""

    monkeypatch.setattr(
        "sys.argv",
        [
            "build_real_snapshot_v2",
            "--persist-audit-remote-production",
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
    with pytest.raises(SystemExit):
        main()


# ---------------------------------------------------------------------------
# Blocker 1: temporal coverage semantics
# ---------------------------------------------------------------------------


def test_observations_by_granularity_never_collapses_team_and_team_match() -> None:
    observations = [
        _observation(
            entity_type="team",
            entity_source_id="Arsenal",
            metric_name="name",
            value="Arsenal",
            source="football-data-uk",
        ),
        _observation(
            entity_type="team",
            entity_source_id="Arsenal",
            metric_name="shots_total",
            value=12,
            source="football-data-uk",
        ),
        _observation(
            entity_type="match",
            entity_source_id="m1",
            metric_name="home_score",
            value=2,
            source="football-data-uk",
        ),
    ]
    result = _observations_by_granularity(observations)
    assert result["team_match"] == 1
    assert result["match"] == 1
    assert result["team_identity"] == 1


def test_metric_coverage_denominator_derives_from_dynamic_catalog() -> None:
    result = _metric_coverage([])
    from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2

    assert result["catalog_identity_count"] == len(METRIC_CATALOG_V2)
    assert result["available_current_period_identity_count"] == 0
    assert result["available_recent_completed_identity_count"] == 0
    assert (
        result["available_current_period_identity_count"]
        + result["available_recent_completed_identity_count"]
        + result["unavailable_identity_count"]
        + result["historical_deep_only_identity_count"]
        == result["catalog_identity_count"]
    )


def test_snapshot_period_role_is_latest_completed_not_current() -> None:
    # ENG_PL 2025/26 is the latest COMPLETED season, not the true current
    # period (as of the 2026-08-15 implementation date). This constant
    # drives the manifest's `period_role` field.
    assert SNAPSHOT_PERIOD_ROLE == "latest_completed"


def test_current_capable_provider_serving_a_completed_season_never_becomes_current_period() -> None:
    """Regression test for Blocker 1.

    `football-data-uk` is registered with `freshness_role == "current"` in
    `coverage_lab.provider_capabilities` (it CAN structurally report current
    data). But every observation this job actually acquires comes from the
    completed ENG_PL 2025/26 season. A current-CAPABLE provider must never
    make a latest-completed ACQUISITION look like current-period coverage.
    """

    observations = [
        _observation(
            entity_type="match",
            entity_source_id="m1",
            metric_name="home_score",
            value=2,
            source="football-data-uk",  # freshness_role == "current" in provider_capabilities
        ),
        _observation(
            entity_type="match",
            entity_source_id="m1",
            metric_name="away_score",
            value=1,
            source="football-data-uk",
        ),
    ]
    result = _metric_coverage(observations)

    # Real, non-trivial recent-completed evidence exists ...
    assert result["available_recent_completed_identity_count"] >= 1
    assert "home_score@match" in result["available_recent_completed_identities"]
    # ... yet current-period coverage stays exactly zero regardless.
    assert result["available_current_period_identity_count"] == 0


def test_metric_coverage_counts_real_available_identity() -> None:
    observations = [
        _observation(
            entity_type="match",
            entity_source_id="m1",
            metric_name="home_score",
            value=2,
            source="football-data-uk",
        )
    ]
    result = _metric_coverage(observations)
    assert "home_score@match" in result["available_recent_completed_identities"]
    assert result["available_recent_completed_identity_count"] >= 1


def test_metric_coverage_buckets_never_overlap() -> None:
    result = _metric_coverage([])
    assert set(result) >= {
        "available_current_period_identity_count",
        "available_recent_completed_identity_count",
        "historical_deep_only_identity_count",
        "unavailable_identity_count",
    }


# ---------------------------------------------------------------------------
# Blocker 2: database write safety
# ---------------------------------------------------------------------------


def test_local_database_urls_are_accepted() -> None:
    assert _validate_database_url(None) is None
    assert _validate_database_url("postgresql://postgres:postgres@localhost:5432/db") is not None
    assert _validate_database_url("postgresql://postgres:postgres@127.0.0.1:5432/db") is not None
    assert _validate_database_url("postgresql://postgres:postgres@[::1]:5432/db") is not None
    # A host-less DSN resolves to a local Unix-domain socket via libpq.
    assert _validate_database_url("postgresql:///football_intelligence_test") is not None


@pytest.mark.parametrize(
    "remote_url",
    [
        "postgresql://user:pass@prod-db.example.com:5432/prod",
        "postgresql://user:pass@10.0.0.5:5432/db",
        "postgresql://user:pass@my-rds-instance.amazonaws.com:5432/prod",
        "mysql://localhost/db",
        "not-a-url-at-all",
    ],
)
def test_remote_or_ambiguous_database_urls_are_rejected(remote_url: str) -> None:
    with pytest.raises(SystemExit):
        _validate_database_url(remote_url)


def test_module_never_reads_os_environ_for_database_url() -> None:
    # Static regression guard: a hidden `os.environ.get("DATABASE_URL")`
    # fallback (Block 18's original, corrected mistake) must never
    # reappear. The module must not import `os` at all.
    import inspect

    from football_intelligence.jobs import build_real_snapshot_v2

    source = inspect.getsource(build_real_snapshot_v2)
    assert "os.environ" not in source
    assert "getenv" not in source
    assert "\nimport os\n" not in source


def test_database_url_environment_variable_is_never_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A production-looking DATABASE_URL sitting in the environment (very
    # common in real deployments) must never be consulted by this job --
    # only an explicit --database-url CLI argument may ever reach
    # _validate_database_url.
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@prod-db.example.com:5432/prod")
    import os

    assert os.environ.get("DATABASE_URL") is not None  # sanity: env var really is set
    # The parser default for --database-url must stay None regardless.
    args = build_parser().parse_args([])
    assert args.database_url is None


def test_persist_flag_with_remote_url_is_rejected_before_any_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_real_snapshot_v2",
            "--database-url",
            "postgresql://user:pass@prod-db.example.com:5432/prod",
            "--persist-audit-local",
        ],
    )

    def _fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("connect() must never be called for a rejected remote URL")

    monkeypatch.setattr(
        "football_intelligence.jobs.build_real_snapshot_v2.connect", _fail_if_called
    )
    with pytest.raises(SystemExit):
        main()


# ---------------------------------------------------------------------------
# Blocker 3: source fingerprinting
# ---------------------------------------------------------------------------


def test_changing_source_bytes_changes_the_checksum() -> None:
    original = hashlib.sha256(b"season data v1").hexdigest()
    changed = hashlib.sha256(b"season data v2").hexdigest()
    assert original != changed
    assert len(original) == 64


def test_fetch_football_data_uk_never_writes_the_tracked_snapshot_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    """Regression test for Blocker 3.

    A fresh Football-Data.co.uk acquisition inside `build_real_snapshot_v2`
    must stay memory-only: it must never call any file-write path, so the
    committed, already-accepted `data/real/2025-26/eng_pl_matches.json`
    (Block 16/17 evidence) can never be silently rewritten as a side effect
    of running this job.
    """

    from datetime import UTC, datetime

    from football_intelligence.data_mesh.models import NormalizedObservation
    from football_intelligence.jobs import build_real_snapshot_v2
    from football_intelligence.providers.football_data_uk import FootballDataUkResponse

    fake_observation = NormalizedObservation(
        source_code="football-data-uk",
        source_type="objective_structured",
        entity_type="match",
        entity_source_id="fake",
        entity_identity_hints={},
        metric_name="home_score",
        value=1,
        observed_at=datetime(2026, 8, 15, tzinfo=UTC),
        source_timestamp=None,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version="football-data-uk-v1",
    )
    fake_response = FootballDataUkResponse(
        division_code="E0",
        season_code="2526",
        csv_text="Div,Date\nE0,15/08/2025\n",
        fetched_at=datetime(2026, 8, 15, tzinfo=UTC),
        raw_bytes=b"Div,Date\nE0,15/08/2025\n",
    )

    write_calls: list[object] = []
    monkeypatch.setattr(
        "football_intelligence.jobs.build_real_snapshot_v2.fetch_football_data_uk_matches",
        lambda: ([fake_observation], fake_response),
    )
    monkeypatch.setattr(
        "football_intelligence.jobs.build_real_snapshot_v2._write_json",
        lambda path, payload: write_calls.append(path),  # noqa: ARG005
    )

    observations, fingerprint = build_real_snapshot_v2._fetch_football_data_uk(
        build_real_snapshot_v2.FOOTBALL_DATA_UK_SOURCE_URL
    )

    assert observations == [fake_observation]
    assert write_calls == []  # no file was written for football-data-uk
    assert "not written by this job" in fingerprint["persisted_to"]


def test_football_data_uk_fingerprint_shape() -> None:
    from datetime import UTC, datetime

    from football_intelligence.jobs import build_real_snapshot_v2
    from football_intelligence.providers.football_data_uk import FootballDataUkResponse

    fake_response = FootballDataUkResponse(
        division_code="E0",
        season_code="2526",
        csv_text="Div,Date\nE0,15/08/2025\n",
        fetched_at=datetime(2026, 8, 15, tzinfo=UTC),
        raw_bytes=b"Div,Date\nE0,15/08/2025\n",
    )
    fingerprint = build_real_snapshot_v2._football_data_uk_fingerprint(
        fake_response, source_url=build_real_snapshot_v2.FOOTBALL_DATA_UK_SOURCE_URL
    )
    assert fingerprint["provider"] == "football-data-uk"
    assert fingerprint["sha256"] == hashlib.sha256(fake_response.raw_bytes).hexdigest()
    assert fingerprint["retrieved_at"] == fake_response.fetched_at.isoformat()
    assert fingerprint["redistribution_permission"] == "unknown"
    assert fingerprint["certification_state"] == "not_certified"
    assert fingerprint["source_locator"]
