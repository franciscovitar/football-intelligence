from __future__ import annotations

import json
from datetime import UTC, datetime

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.jobs.collect_real_snapshot import (
    _json_default,
    build_matches_output,
    build_parser,
    build_player_season_stats_output,
)
from football_intelligence.normalization.models import PlayerSeasonStatsRecord

_NOW = datetime(2026, 8, 14, tzinfo=UTC)


def _player_season_record() -> PlayerSeasonStatsRecord:
    return PlayerSeasonStatsRecord(
        player_external_id="1",
        competition_external_id="ENG_PL",
        season_label="2025/26",
        minutes=3330,
        starts=37,
        appearances=None,
        goals=0,
        assists=0,
        clean_sheets=19,
        goals_conceded=26,
        own_goals=0,
        penalties_saved=0,
        penalties_missed=0,
        yellow_cards=1,
        red_cards=0,
        saves=60,
        bonus=11,
        bps=633,
        influence=541.6,
        creativity=33.5,
        threat=0.0,
        ict_index=57.5,
        tackles=1,
        recoveries=304,
        clearances_blocks_interceptions=37,
        defensive_contribution=0,
        expected_goals=0.0,
        expected_assists=0.07,
        expected_goal_involvements=0.07,
        expected_goals_conceded=27.56,
        source="fpl-official-api",
        source_url="https://fantasy.premierleague.com/api/element-summary/1/",
        retrieved_at=_NOW,
        semantic_version="fpl-official-api-v1",
    )


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


def test_build_player_season_stats_output_shape() -> None:
    output = build_player_season_stats_output(
        records=[_player_season_record()],
        errors=["element 999999: not found"],
        retrieved_at=_NOW,
    )
    assert output["provenance"]["source"] == "fpl-official-api"
    assert output["provenance"]["record_count"] == 1
    # The provenance block's own timestamp is isoformatted eagerly.
    assert output["provenance"]["retrieved_at"] == _NOW.isoformat()
    assert output["errors"] == ["element 999999: not found"]
    assert len(output["records"]) == 1
    assert output["records"][0]["player_external_id"] == "1"
    # Per-record datetime fields stay real datetime objects until the final
    # json.dumps(..., default=_json_default) write step -- verified below.
    assert output["records"][0]["retrieved_at"] == _NOW


def test_build_matches_output_shape() -> None:
    output = build_matches_output(observations=[_observation()], retrieved_at=_NOW)
    assert output["provenance"]["source"] == "football-data-uk"
    assert output["provenance"]["record_count"] == 1
    assert len(output["records"]) == 1
    assert output["records"][0]["metric_name"] == "home_score"
    assert output["records"][0]["value"] == 4
    assert output["records"][0]["observed_at"] == _NOW


def test_output_is_json_serializable_with_datetime_fields() -> None:
    player_output = build_player_season_stats_output(
        records=[_player_season_record()], errors=[], retrieved_at=_NOW
    )
    match_output = build_matches_output(observations=[_observation()], retrieved_at=_NOW)

    player_json = json.dumps(player_output, default=_json_default)
    match_json = json.dumps(match_output, default=_json_default)

    assert "2026-08-14T00:00:00+00:00" in player_json
    assert "2026-08-14T00:00:00+00:00" in match_json


def test_build_matches_output_empty_is_valid() -> None:
    output = build_matches_output(observations=[], retrieved_at=_NOW)
    assert output["provenance"]["record_count"] == 0
    assert output["records"] == []


def test_cli_flags_are_mutually_exclusive_by_convention() -> None:
    parser = build_parser()
    args = parser.parse_args(["--fpl-only"])
    assert args.fpl_only is True
    assert args.matches_only is False

    args = parser.parse_args(["--matches-only", "--limit", "5"])
    assert args.matches_only is True
    assert args.limit == 5


def test_cli_default_output_dir_points_under_repo_root_data_real() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    parts = args.output_dir.parts
    assert parts[-3:] == ("data", "real", "2025-26")
