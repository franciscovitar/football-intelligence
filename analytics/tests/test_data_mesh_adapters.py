from __future__ import annotations

from football_intelligence.data_mesh.adapters.openligadb import parse_league_matches
from football_intelligence.data_mesh.adapters.thesportsdb import parse_league_events

# Payload shapes below mirror real responses observed live from each free
# API during Block 13 implementation (trimmed to the fields adapters use).

_THESPORTSDB_PAYLOAD = {
    "events": [
        {
            "idEvent": "2276638",
            "idHomeTeam": "133664",
            "idAwayTeam": "134695",
            "strHomeTeam": "Bayern Munich",
            "strAwayTeam": "RB Leipzig",
            "strLeague": "German Bundesliga",
            "strSeason": "2025-2026",
            "dateEvent": "2025-08-22",
            "strTimestamp": "2025-08-22T18:30:00",
            "strStatus": "FT",
            "intHomeScore": "6",
            "intAwayScore": "0",
        },
        {
            # Not yet played: no score fields reported at all.
            "idEvent": "2276999",
            "idHomeTeam": "133602",
            "idAwayTeam": "134786",
            "strHomeTeam": "Borussia Dortmund",
            "strAwayTeam": "FC Augsburg",
            "strLeague": "German Bundesliga",
            "strSeason": "2025-2026",
            "dateEvent": "2025-08-24",
            "strTimestamp": "2025-08-24T13:30:00",
            "strStatus": "NS",
            "intHomeScore": None,
            "intAwayScore": None,
        },
    ]
}

_OPENLIGADB_PAYLOAD = [
    {
        "matchID": 77256,
        "matchDateTime": "2025-08-22T20:30:00",
        "matchDateTimeUTC": "2025-08-22T18:30:00Z",
        "leagueId": 4821,
        "leagueName": "1. Fussball-Bundesliga 2025/2026",
        "leagueSeason": 2025,
        "leagueShortcut": "bl1",
        "matchIsFinished": True,
        "team1": {"teamId": 40, "teamName": "FC Bayern München", "shortName": "Bayern"},
        "team2": {"teamId": 41, "teamName": "RB Leipzig", "shortName": "Leipzig"},
        "matchResults": [
            {
                "resultName": "Halbzeit",
                "pointsTeam1": 3,
                "pointsTeam2": 0,
                "resultTypeKind": "HalfTime",
            },
            {
                "resultName": "Endergebnis",
                "pointsTeam1": 6,
                "pointsTeam2": 0,
                "resultTypeKind": "After90Minutes",
            },
        ],
    },
    {
        # Scheduled, not finished: no matchResults at all yet.
        "matchID": 77300,
        "matchDateTime": "2025-08-24T15:30:00",
        "matchDateTimeUTC": "2025-08-24T13:30:00Z",
        "leagueId": 4821,
        "leagueName": "1. Fussball-Bundesliga 2025/2026",
        "leagueSeason": 2025,
        "leagueShortcut": "bl1",
        "matchIsFinished": False,
        "team1": {"teamId": 7, "teamName": "Borussia Dortmund", "shortName": "Dortmund"},
        "team2": {"teamId": 5, "teamName": "FC Augsburg", "shortName": "Augsburg"},
        "matchResults": [],
    },
]


def test_thesportsdb_adapter_extracts_scores_when_reported() -> None:
    observations = parse_league_events(
        _THESPORTSDB_PAYLOAD,
        competition_external_id="4331",
        ingestion_run_id=None,
    )
    scores = {
        (obs.entity_source_id, obs.metric_name): obs.value
        for obs in observations
        if obs.entity_type == "match" and obs.metric_name in ("home_score", "away_score")
    }
    assert scores[("2276638", "home_score")] == 6
    assert scores[("2276638", "away_score")] == 0  # a real, reported zero


def test_thesportsdb_adapter_missing_score_produces_no_score_observation() -> None:
    observations = parse_league_events(
        _THESPORTSDB_PAYLOAD,
        competition_external_id="4331",
        ingestion_run_id=None,
    )
    not_played_score_metrics = {
        obs.metric_name
        for obs in observations
        if obs.entity_source_id == "2276999" and obs.metric_name in ("home_score", "away_score")
    }
    # Missing stays missing: no observation row at all, not a fabricated 0.
    assert not_played_score_metrics == set()


def test_thesportsdb_adapter_emits_all_entity_types() -> None:
    observations = parse_league_events(
        _THESPORTSDB_PAYLOAD,
        competition_external_id="4331",
        ingestion_run_id=None,
    )
    entity_types = {obs.entity_type for obs in observations}
    assert entity_types == {"competition", "team", "match"}


def test_openligadb_adapter_extracts_final_result_only() -> None:
    observations = parse_league_matches(
        _OPENLIGADB_PAYLOAD,
        competition_external_id="bl1",
        ingestion_run_id=None,
    )
    scores = {
        (obs.entity_source_id, obs.metric_name): obs.value
        for obs in observations
        if obs.entity_type == "match" and obs.metric_name in ("home_score", "away_score")
    }
    assert scores[("77256", "home_score")] == 6
    assert scores[("77256", "away_score")] == 0


def test_openligadb_adapter_missing_results_produces_no_score_observation() -> None:
    observations = parse_league_matches(
        _OPENLIGADB_PAYLOAD,
        competition_external_id="bl1",
        ingestion_run_id=None,
    )
    unfinished_score_metrics = {
        obs.metric_name
        for obs in observations
        if obs.entity_source_id == "77300" and obs.metric_name in ("home_score", "away_score")
    }
    assert unfinished_score_metrics == set()


def test_openligadb_adapter_source_metric_availability_never_fabricated() -> None:
    # OpenLigaDB's free match feed does not report shots/possession/etc: the
    # adapter must never invent those metrics.
    observations = parse_league_matches(
        _OPENLIGADB_PAYLOAD,
        competition_external_id="bl1",
        ingestion_run_id=None,
    )
    metric_names = {obs.metric_name for obs in observations}
    assert "shots_total" not in metric_names
    assert "possession_pct" not in metric_names
    assert metric_names <= {"name", "status", "home_score", "away_score"}


def test_both_adapters_agree_on_the_same_real_fixture_score() -> None:
    thesportsdb_observations = parse_league_events(
        _THESPORTSDB_PAYLOAD, competition_external_id="4331", ingestion_run_id=None
    )
    openligadb_observations = parse_league_matches(
        _OPENLIGADB_PAYLOAD, competition_external_id="bl1", ingestion_run_id=None
    )
    thesportsdb_home_score = next(
        obs.value
        for obs in thesportsdb_observations
        if obs.entity_source_id == "2276638" and obs.metric_name == "home_score"
    )
    openligadb_home_score = next(
        obs.value
        for obs in openligadb_observations
        if obs.entity_source_id == "77256" and obs.metric_name == "home_score"
    )
    assert thesportsdb_home_score == openligadb_home_score == 6
