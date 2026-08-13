from __future__ import annotations

from football_intelligence.data_mesh.adapters.football_data_org import (
    parse_competitions,
    parse_matches,
)

_COMPETITIONS_PAYLOAD = {
    "competitions": [
        {"id": 2021, "name": "Premier League", "code": "PL"},
        {"id": 2014, "name": "Primera Division", "code": "PD"},
    ]
}

_MATCHES_PAYLOAD = {
    "matches": [
        {
            "id": 12345,
            "utcDate": "2025-08-22T18:30:00Z",
            "status": "FINISHED",
            "homeTeam": {"name": "Sample United"},
            "awayTeam": {"name": "Sample City"},
            "score": {"fullTime": {"home": 2, "away": 1}},
        },
        {
            "id": 12346,
            "utcDate": "2025-08-23T15:00:00Z",
            "status": "SCHEDULED",
            "homeTeam": {"name": "Sample Town"},
            "awayTeam": {"name": "Sample Rovers"},
            "score": {"fullTime": {"home": None, "away": None}},
        },
    ]
}


def test_parse_competitions_extracts_name_observations() -> None:
    observations = parse_competitions(_COMPETITIONS_PAYLOAD, ingestion_run_id=None)
    names = {obs.entity_source_id: obs.value for obs in observations}
    assert names["2021"] == "Premier League"
    assert names["2014"] == "Primera Division"


def test_parse_matches_extracts_scores_for_finished_match() -> None:
    observations = parse_matches(_MATCHES_PAYLOAD, competition_code="ENG_PL", ingestion_run_id=None)
    finished = {
        obs.metric_name: obs.value for obs in observations if obs.entity_source_id == "12345"
    }
    assert finished["status"] == "finished"
    assert finished["home_score"] == 2
    assert finished["away_score"] == 1


def test_parse_matches_scheduled_match_has_no_score_observation() -> None:
    observations = parse_matches(_MATCHES_PAYLOAD, competition_code="ENG_PL", ingestion_run_id=None)
    scheduled_metrics = {obs.metric_name for obs in observations if obs.entity_source_id == "12346"}
    assert scheduled_metrics == {"status"}
    assert "home_score" not in scheduled_metrics
