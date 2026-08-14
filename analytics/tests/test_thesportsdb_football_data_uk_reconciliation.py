from __future__ import annotations

from football_intelligence.data_mesh.adapters.football_data_uk import parse_results_csv
from football_intelligence.data_mesh.adapters.thesportsdb import parse_league_events
from football_intelligence.data_mesh.pipeline import resolve_and_reconcile

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

_FOOTBALL_DATA_UK_CSV = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR\n"
    "D1,22/08/2025,18:30,Bayern Munich,RB Leipzig,6,0,H,20,5,12,2,8,10,7,3,1,2,0,0\n"
)


def _combined_observations() -> list:
    thesportsdb_observations = parse_league_events(
        _THESPORTSDB_PAYLOAD, competition_external_id="4331", ingestion_run_id=None
    )
    fd_uk_observations = parse_results_csv(
        _FOOTBALL_DATA_UK_CSV, division_code="D1", season_code="2526", ingestion_run_id=None
    )
    return thesportsdb_observations + fd_uk_observations


def test_matching_team_names_across_providers_resolve_to_one_logical_identity() -> None:
    # TheSportsDB and Football-Data.co.uk both report "Bayern Munich"/
    # "RB Leipzig" -- different providers, same raw spelling this time, but
    # the important thing is they go through the SAME entity-resolution
    # pipeline (not a bespoke comparison), converging on one logical team.
    decisions, meta = resolve_and_reconcile(_combined_observations())
    team_decisions = {
        decision.logical_entity_key: decision
        for decision in decisions
        if decision.entity_type == "team" and decision.metric_name == "name"
    }
    bayern_key = "team:GER_BL1:bayern munchen"
    assert bayern_key in team_decisions
    assert bayern_key.startswith("team:GER_BL1:")
    assert meta["unresolved_observation_count"] == 0


def test_home_score_agrees_across_thesportsdb_and_football_data_uk() -> None:
    decisions, meta = resolve_and_reconcile(_combined_observations())
    home_score_decisions = [
        decision
        for decision in decisions
        if decision.entity_type == "match" and decision.metric_name == "home_score"
    ]
    assert len(home_score_decisions) == 1
    decision = home_score_decisions[0]
    assert decision.status == "agreed"
    assert decision.candidate_value == 6
    assert set(decision.participating_sources) == {"thesportsdb", "football-data-uk"}
    assert meta["overlap_count"] >= 1


def test_shots_total_is_single_source_when_only_football_data_uk_reports_it() -> None:
    # TheSportsDB's season-events probe never reports team-level shots (only
    # its event-stats endpoint does, which this fixture does not include) --
    # so this metric is real evidence from exactly one source, correctly
    # `single_source`, never fabricated as an agreement.
    decisions, _meta = resolve_and_reconcile(_combined_observations())
    shots_decisions = [
        decision
        for decision in decisions
        if decision.entity_type == "team" and decision.metric_name == "shots_total"
    ]
    # One decision per team (Bayern Munich, RB Leipzig) -- both single_source
    # since only football-data-uk reports team-level shots in this fixture.
    assert len(shots_decisions) == 2
    assert all(decision.status == "single_source" for decision in shots_decisions)
    assert all(
        decision.participating_sources == ("football-data-uk",) for decision in shots_decisions
    )
