from __future__ import annotations

from datetime import UTC, datetime

import pytest

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.jobs.build_real_snapshot_v2 import (
    SUPPORTED_COMPETITION_CODE,
    SUPPORTED_SEASON_LABEL,
    _metric_coverage,
    _observations_by_granularity,
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


def test_cli_defaults_target_eng_pl_2025_26() -> None:
    args = build_parser().parse_args([])
    assert args.competition == SUPPORTED_COMPETITION_CODE
    assert args.season == SUPPORTED_SEASON_LABEL
    assert args.manifest_path.parts[-5:-1] == ("data", "manifests", "real", "ENG_PL")


def test_cli_default_manifest_filename_is_season_scoped() -> None:
    args = build_parser().parse_args([])
    assert args.manifest_path.name == "2025-26.json"


def test_unsupported_competition_or_season_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["build_real_snapshot_v2", "--competition", "GER_BL1"])
    with pytest.raises(SystemExit):
        main()


def test_unsupported_season_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["build_real_snapshot_v2", "--season", "2026/27"])
    with pytest.raises(SystemExit):
        main()


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
    # Dynamic: must equal the live METRIC_CATALOG_V2 size, never a hardcoded
    # number that could silently drift from the real catalog.
    from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2

    assert result["catalog_identity_count"] == len(METRIC_CATALOG_V2)
    assert result["available_current_identity_count"] == 0
    assert (
        result["unavailable_identity_count"] + result["historical_deep_only_identity_count"]
        == (result["catalog_identity_count"])
    )


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
    assert "home_score@match" in result["available_current_identities"]
    assert result["available_current_identity_count"] >= 1


def test_metric_coverage_never_blends_current_and_historical_deep() -> None:
    result = _metric_coverage([])
    assert "available_current_identity_count" in result
    assert "historical_deep_only_identity_count" in result
    # The two must be reported as separate fields, never summed into one
    # opaque percentage.
    assert set(result) >= {
        "available_current_identity_count",
        "historical_deep_only_identity_count",
        "unavailable_identity_count",
    }
