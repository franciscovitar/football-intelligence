from __future__ import annotations

from football_intelligence.data_mesh.adapters.openligadb import parse_league_matches
from football_intelligence.data_mesh.adapters.thesportsdb import parse_league_events
from football_intelligence.jobs.run_data_mesh_poc import (
    _competition_external_id,
    _coverage_by_source,
    _resolve_and_reconcile,
)

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
    ]
}

_OPENLIGADB_PAYLOAD = [
    {
        "matchID": 77256,
        "matchDateTimeUTC": "2025-08-22T18:30:00Z",
        "leagueName": "1. Fussball-Bundesliga 2025/2026",
        "leagueSeason": 2025,
        "matchIsFinished": True,
        "team1": {"teamId": 40, "teamName": "FC Bayern München"},
        "team2": {"teamId": 41, "teamName": "RB Leipzig"},
        "matchResults": [
            {"pointsTeam1": 6, "pointsTeam2": 0, "resultTypeKind": "After90Minutes"},
        ],
    },
]


def _all_observations() -> list:
    thesportsdb_id = _competition_external_id("thesportsdb")
    openligadb_id = _competition_external_id("openligadb")
    return parse_league_events(
        _THESPORTSDB_PAYLOAD, competition_external_id=thesportsdb_id, ingestion_run_id=None
    ) + parse_league_matches(
        _OPENLIGADB_PAYLOAD, competition_external_id=openligadb_id, ingestion_run_id=None
    )


def test_full_pipeline_resolves_and_reconciles_the_same_real_fixture() -> None:
    observations = _all_observations()
    decisions, meta = _resolve_and_reconcile(observations)

    match_score_decisions = [
        decision
        for decision in decisions
        if decision.entity_type == "match" and decision.metric_name == "home_score"
    ]
    assert len(match_score_decisions) == 1
    decision = match_score_decisions[0]
    # Two independent providers, same real fixture, same score -> agreed.
    assert decision.status == "agreed"
    assert decision.candidate_value == 6
    assert decision.source_count == 2
    assert set(decision.participating_sources) == {"thesportsdb", "openligadb"}
    assert meta["overlap_count"] >= 1
    assert meta["unresolved_observation_count"] == 0


def test_full_pipeline_team_names_converge_to_one_logical_key() -> None:
    observations = _all_observations()
    decisions, _meta = _resolve_and_reconcile(observations)
    team_name_decisions = {
        decision.logical_entity_key: decision
        for decision in decisions
        if decision.entity_type == "team" and decision.metric_name == "name"
    }

    bayern_key = "team:GER_BL1:bayern munchen"
    assert bayern_key in team_name_decisions
    bayern_decision = team_name_decisions[bayern_key]
    # Both providers' raw name spellings ("Bayern Munich" vs "FC Bayern
    # München") resolve to the SAME logical entity -- entity resolution
    # succeeded even though the raw strings still differ. That residual
    # spelling difference is correctly reported as a metric-level conflict,
    # never silently merged into one "winning" spelling.
    assert bayern_decision.source_count == 2
    assert bayern_decision.status == "conflict"
    assert set(bayern_decision.evidence["values_by_source"].values()) == {
        "Bayern Munich",
        "FC Bayern München",
    }

    # "RB Leipzig" is spelled identically by both providers: a genuine
    # agreement, not just a resolved identity.
    leipzig_key = "team:GER_BL1:leipzig rb"
    assert team_name_decisions[leipzig_key].status == "agreed"


def test_coverage_by_source_reflects_what_each_source_actually_reported() -> None:
    observations = _all_observations()
    coverage = _coverage_by_source(observations)
    assert "thesportsdb" in coverage
    assert "openligadb" in coverage
    assert coverage["thesportsdb"]["match.home_score"] == 1
    assert coverage["openligadb"]["match.home_score"] == 1
    # OpenLigaDB's match feed never reports shots -- coverage must not claim it.
    assert "match.shots_total" not in coverage["openligadb"]


def test_competition_external_id_matches_configured_mapping() -> None:
    assert _competition_external_id("thesportsdb") == "4331"
    assert _competition_external_id("openligadb") == "bl1"


def test_full_pipeline_normalizes_status_semantics_into_agreed_is_finished() -> None:
    # TheSportsDB reports "FT" (its own vocabulary); OpenLigaDB reports
    # matchIsFinished=True (its own vocabulary). Both describe the same
    # objective fact for the same real fixture, so after normalization at
    # the adapter boundary they must reconcile as `agreed`, not `conflict`.
    observations = _all_observations()
    decisions, _meta = _resolve_and_reconcile(observations)
    is_finished_decisions = [
        decision
        for decision in decisions
        if decision.entity_type == "match" and decision.metric_name == "is_finished"
    ]
    assert len(is_finished_decisions) == 1
    decision = is_finished_decisions[0]
    assert decision.status == "agreed"
    assert decision.candidate_value is True
    assert set(decision.participating_sources) == {"thesportsdb", "openligadb"}
    # The raw provider strings ("FT" vs a bare boolean) never leak through as
    # the normalized objective value.
    assert set(decision.evidence["values_by_source"].values()) == {True}


def _observations_for_date_offset(*, thesportsdb_date: str, openligadb_date: str) -> list:
    thesportsdb_payload = {
        "events": [
            {
                "idEvent": "3000001",
                "idHomeTeam": "133664",
                "idAwayTeam": "134695",
                "strHomeTeam": "Bayern Munich",
                "strAwayTeam": "RB Leipzig",
                "strLeague": "German Bundesliga",
                "strSeason": "2025-2026",
                "dateEvent": thesportsdb_date,
                "strTimestamp": f"{thesportsdb_date}T18:30:00",
                "strStatus": "FT",
                "intHomeScore": "3",
                "intAwayScore": "1",
            }
        ]
    }
    openligadb_payload = [
        {
            "matchID": 88001,
            "matchDateTimeUTC": f"{openligadb_date}T18:30:00Z",
            "leagueName": "1. Fussball-Bundesliga 2025/2026",
            "leagueSeason": 2025,
            "matchIsFinished": True,
            "team1": {"teamId": 40, "teamName": "FC Bayern München"},
            "team2": {"teamId": 41, "teamName": "RB Leipzig"},
            "matchResults": [
                {"pointsTeam1": 3, "pointsTeam2": 1, "resultTypeKind": "After90Minutes"},
            ],
        }
    ]
    thesportsdb_id = _competition_external_id("thesportsdb")
    openligadb_id = _competition_external_id("openligadb")
    return parse_league_events(
        thesportsdb_payload, competition_external_id=thesportsdb_id, ingestion_run_id=None
    ) + parse_league_matches(
        openligadb_payload, competition_external_id=openligadb_id, ingestion_run_id=None
    )


def test_match_date_tolerance_reconciles_adjacent_dates_as_one_fixture() -> None:
    # Provider A: 2025-08-22. Provider B: 2025-08-23 (1 day later, still
    # within MATCH_DATE_TOLERANCE_DAYS). The real pipeline must converge on
    # ONE logical match identity so their common metric can become `agreed`.
    observations = _observations_for_date_offset(
        thesportsdb_date="2025-08-22", openligadb_date="2025-08-23"
    )
    decisions, meta = _resolve_and_reconcile(observations)
    home_score_decisions = [
        decision
        for decision in decisions
        if decision.entity_type == "match" and decision.metric_name == "home_score"
    ]
    assert len(home_score_decisions) == 1
    decision = home_score_decisions[0]
    assert decision.status == "agreed"
    assert decision.source_count == 2
    assert set(decision.participating_sources) == {"thesportsdb", "openligadb"}
    assert meta["overlap_count"] >= 1


def test_match_date_outside_tolerance_stays_a_distinct_fixture() -> None:
    # Provider A: 2025-08-22. Provider B: 2025-08-25 (3 days later, outside
    # MATCH_DATE_TOLERANCE_DAYS). These must NOT be silently reconciled as
    # the same fixture.
    observations = _observations_for_date_offset(
        thesportsdb_date="2025-08-22", openligadb_date="2025-08-25"
    )
    decisions, _meta = _resolve_and_reconcile(observations)
    home_score_decisions = [
        decision
        for decision in decisions
        if decision.entity_type == "match" and decision.metric_name == "home_score"
    ]
    # Two distinct logical match identities -> two independent single-source
    # decisions, never one merged decision with source_count == 2.
    assert len(home_score_decisions) == 2
    assert {decision.status for decision in home_score_decisions} == {"single_source"}
    assert {decision.source_count for decision in home_score_decisions} == {1}
