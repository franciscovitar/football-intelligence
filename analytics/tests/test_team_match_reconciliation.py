from __future__ import annotations

from football_intelligence.data_mesh.adapters.football_data_uk import parse_results_csv
from football_intelligence.data_mesh.adapters.thesportsdb import (
    parse_event_stats,
    parse_league_events,
)
from football_intelligence.data_mesh.pipeline import resolve_and_reconcile

_BAYERN_ID = "133664"
_LEIPZIG_ID = "134695"
_DORTMUND_ID = "133639"
_MATCH_A_ID = "2276638"  # Bayern (home) vs Leipzig
_MATCH_B_ID = "2276999"  # Bayern (home) vs Dortmund

_THESPORTSDB_SEASON_PAYLOAD = {
    "events": [
        {
            "idEvent": _MATCH_A_ID,
            "idHomeTeam": _BAYERN_ID,
            "idAwayTeam": _LEIPZIG_ID,
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
            "idEvent": _MATCH_B_ID,
            "idHomeTeam": _BAYERN_ID,
            "idAwayTeam": _DORTMUND_ID,
            "strHomeTeam": "Bayern Munich",
            "strAwayTeam": "Borussia Dortmund",
            "strLeague": "German Bundesliga",
            "strSeason": "2025-2026",
            "dateEvent": "2025-08-29",
            "strTimestamp": "2025-08-29T18:30:00",
            "strStatus": "FT",
            "intHomeScore": "2",
            "intAwayScore": "1",
        },
    ]
}

_EVENT_STATS_MATCH_A = {
    "eventstats": [
        {
            "idStatistic": "1",
            "idEvent": _MATCH_A_ID,
            "strStat": "Total Shots",
            "intHome": "20",
            "intAway": "5",
        },
    ]
}
_EVENT_STATS_MATCH_B = {
    "eventstats": [
        {
            "idStatistic": "2",
            "idEvent": _MATCH_B_ID,
            "strStat": "Total Shots",
            "intHome": "11",
            "intAway": "9",
        },
    ]
}

_FD_UK_CSV_AGREE = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR\n"
    "D1,22/08/2025,18:30,Bayern Munich,RB Leipzig,6,0,H,20,5,12,2,8,10,7,3,1,2,0,0\n"
)
_FD_UK_CSV_CONFLICT = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR\n"
    "D1,22/08/2025,18:30,Bayern Munich,RB Leipzig,6,0,H,17,5,12,2,8,10,7,3,1,2,0,0\n"
)

_BAYERN_TEAM_KEY_SUFFIX = ":team:GER_BL1:bayern munchen"


def _season_events() -> list:
    return parse_league_events(
        _THESPORTSDB_SEASON_PAYLOAD, competition_external_id="4331", ingestion_run_id=None
    )


def _event_stats_a() -> list:
    return parse_event_stats(
        _EVENT_STATS_MATCH_A,
        match_id=_MATCH_A_ID,
        competition_external_id="4331",
        home_team_external_id=_BAYERN_ID,
        away_team_external_id=_LEIPZIG_ID,
        ingestion_run_id=None,
    )


def _event_stats_b() -> list:
    return parse_event_stats(
        _EVENT_STATS_MATCH_B,
        match_id=_MATCH_B_ID,
        competition_external_id="4331",
        home_team_external_id=_BAYERN_ID,
        away_team_external_id=_DORTMUND_ID,
        ingestion_run_id=None,
    )


def _bayern_shots_decisions(decisions: list) -> list:
    return [
        d
        for d in decisions
        if d.entity_type == "team"
        and d.metric_name == "shots_total"
        and d.logical_entity_key.endswith(_BAYERN_TEAM_KEY_SUFFIX)
    ]


def test_same_team_two_different_matches_produce_two_separate_decisions() -> None:
    # Bayern's shots_total against Leipzig (20) and against Dortmund (11) are
    # two different real facts, not two observations of the same fact -- they
    # must never collide into one logical key just because it's the same team.
    observations = _season_events() + _event_stats_a() + _event_stats_b()
    decisions, _meta = resolve_and_reconcile(observations)
    bayern_shots = _bayern_shots_decisions(decisions)
    assert len(bayern_shots) == 2
    keys = {d.logical_entity_key for d in bayern_shots}
    assert len(keys) == 2  # genuinely distinct logical keys, one per match
    values = {d.candidate_value for d in bayern_shots}
    assert values == {20, 11}


def test_thesportsdb_event_stats_resolve_via_source_local_bridging_index() -> None:
    # Event-stat observations only ever carry a provider team/match id, never
    # a team name -- they must resolve through the (source_code, id) bridging
    # index built from the season-event observations, not become permanently
    # unresolved for lacking a `name` hint of their own.
    observations = _season_events() + _event_stats_a()
    decisions, meta = resolve_and_reconcile(observations)
    assert meta["unresolved_observation_count"] == 0
    assert len(_bayern_shots_decisions(decisions)) == 1


def test_same_match_same_value_across_sources_agrees() -> None:
    observations = (
        _season_events()
        + _event_stats_a()
        + parse_results_csv(
            _FD_UK_CSV_AGREE, division_code="D1", season_code="2526", ingestion_run_id=None
        )
    )
    decisions, _meta = resolve_and_reconcile(observations)
    bayern_shots = _bayern_shots_decisions(decisions)
    assert len(bayern_shots) == 1
    decision = bayern_shots[0]
    assert decision.status == "agreed"
    assert decision.candidate_value == 20
    assert set(decision.participating_sources) == {"thesportsdb", "football-data-uk"}


def test_same_match_different_value_across_sources_conflicts_never_averaged() -> None:
    observations = (
        _season_events()
        + _event_stats_a()
        + parse_results_csv(
            _FD_UK_CSV_CONFLICT, division_code="D1", season_code="2526", ingestion_run_id=None
        )
    )
    decisions, _meta = resolve_and_reconcile(observations)
    bayern_shots = _bayern_shots_decisions(decisions)
    assert len(bayern_shots) == 1
    decision = bayern_shots[0]
    assert decision.status == "conflict"
    # Never averaged (e.g. never 18.5): candidate_value stays unset without
    # an explicit priority rule, and both raw values remain in the evidence.
    assert decision.candidate_value is None
    assert set(decision.evidence["values_by_source"].values()) == {20, 17}


def test_same_team_different_matches_never_compared_against_each_other() -> None:
    # Match A (agree, 20 vs 20) and Match B (thesportsdb only, 11) must
    # never be mixed into a single decision for Bayern -- Match A stays
    # `agreed`, Match B stays `single_source`, independently.
    observations = (
        _season_events()
        + _event_stats_a()
        + _event_stats_b()
        + parse_results_csv(
            _FD_UK_CSV_AGREE, division_code="D1", season_code="2526", ingestion_run_id=None
        )
    )
    decisions, _meta = resolve_and_reconcile(observations)
    bayern_shots = {d.logical_entity_key: d for d in _bayern_shots_decisions(decisions)}
    assert len(bayern_shots) == 2
    statuses = {d.status for d in bayern_shots.values()}
    assert statuses == {"agreed", "single_source"}


def test_team_name_stays_a_single_team_scoped_decision_across_matches() -> None:
    # team.name is a team-identity property, not match-scoped: Bayern
    # appearing in two matches must still resolve to exactly one `name`
    # decision, never a "team-match:"-prefixed key.
    decisions, _meta = resolve_and_reconcile(_season_events())
    bayern_name_decisions = [
        d
        for d in decisions
        if d.entity_type == "team"
        and d.metric_name == "name"
        and d.logical_entity_key == "team:GER_BL1:bayern munchen"
    ]
    assert len(bayern_name_decisions) == 1
    assert not bayern_name_decisions[0].logical_entity_key.startswith("team-match:")
