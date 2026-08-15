from __future__ import annotations

import json
from datetime import UTC, datetime

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.jobs.collect_real_snapshot import (
    _json_default,
    build_matches_output,
    build_parser,
)

_NOW = datetime(2026, 8, 14, tzinfo=UTC)


def _observation() -> NormalizedObservation:
    return NormalizedObservation(
        source_code="football-data-uk",
        source_type="objective_structured",
        entity_type="match",
        entity_source_id="E0:2025-08-15:Liverpool:Bournemouth",
        entity_identity_hints={"home_team_name": "Liverpool", "away_team_name": "Bournemouth"},
        metric_name="home_score",
        value=4,
        observed_at=_NOW,
        source_timestamp=None,
        source_reference="mmz4281/2526/E0.csv",
        ingestion_run_id=None,
        semantic_version="football-data-uk-v1",
    )


def test_build_matches_output_is_real_scoped_and_compliance_tagged() -> None:
    output = build_matches_output(observations=[_observation()], retrieved_at=_NOW)
    assert output["provenance"]["source"] == "football-data-uk"
    assert output["provenance"]["record_count"] == 1
    assert output["provenance"]["automated_collection"] == "yes"
    assert output["provenance"]["redistribution_permission"] == "unknown"
    assert output["provenance"]["certification_state"] == "not_certified"
    assert output["scope"]["player_coverage"] == "unavailable"
    assert output["records"][0]["metric_name"] == "home_score"


def test_output_is_json_serializable_with_datetime_fields() -> None:
    output = build_matches_output(observations=[_observation()], retrieved_at=_NOW)
    assert "2026-08-14T00:00:00+00:00" in json.dumps(output, default=_json_default)


def test_build_matches_output_empty_is_valid() -> None:
    output = build_matches_output(observations=[], retrieved_at=_NOW)
    assert output["provenance"]["record_count"] == 0
    assert output["records"] == []


def test_cli_has_no_fpl_automation_flags() -> None:
    parser = build_parser()
    option_strings = {option for action in parser._actions for option in action.option_strings}
    assert "--fpl-only" not in option_strings
    assert "--limit" not in option_strings


def test_cli_default_output_dir_points_under_repo_root_data_real() -> None:
    args = build_parser().parse_args([])
    assert args.output_dir.parts[-3:] == ("data", "real", "2025-26")
