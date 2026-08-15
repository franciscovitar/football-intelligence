from __future__ import annotations

from football_intelligence.data_mesh.adapters.football_data_uk import parse_results_csv
from football_intelligence.data_mesh.adapters.openfootball import parse_season_matches
from football_intelligence.data_mesh.pipeline import resolve_and_reconcile

_OPENFOOTBALL_PAYLOAD = {
    "name": "English Premier League 2025/26",
    "matches": [
        {
            "round": "Matchday 1",
            "date": "2025-08-15",
            "team1": "Liverpool FC",
            "team2": "AFC Bournemouth",
            "score": {"ft": [4, 2], "ht": [1, 0]},
        }
    ],
}

_FOOTBALL_DATA_UK_CSV = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR\n"
    "E0,15/08/2025,20:00,Liverpool,Bournemouth,4,2,H,20,5,12,2,8,10,7,3,1,2,0,0\n"
)


def _combined_observations() -> list:
    fduk_observations = parse_results_csv(
        _FOOTBALL_DATA_UK_CSV, division_code="E0", season_code="2526", ingestion_run_id=None
    )
    openfootball_observations = parse_season_matches(
        _OPENFOOTBALL_PAYLOAD,
        competition_external_id="en.1.json",
        season_label="2025-2026",
        source_reference="2025-26/en.1.json",
        ingestion_run_id=None,
    )
    return fduk_observations + openfootball_observations


def test_short_and_long_club_names_resolve_to_one_logical_team() -> None:
    decisions, meta = resolve_and_reconcile(_combined_observations())
    team_decisions = {
        decision.logical_entity_key
        for decision in decisions
        if decision.entity_type == "team" and decision.metric_name == "name"
    }
    assert "team:ENG_PL:bournemouth" in team_decisions
    assert meta["unresolved_observation_count"] == 0


def test_home_and_away_score_agree_across_both_real_sources() -> None:
    decisions, _meta = resolve_and_reconcile(_combined_observations())
    home_score = next(
        d for d in decisions if d.entity_type == "match" and d.metric_name == "home_score"
    )
    away_score = next(
        d for d in decisions if d.entity_type == "match" and d.metric_name == "away_score"
    )
    assert home_score.status == "agreed"
    assert home_score.candidate_value == 4
    assert set(home_score.participating_sources) == {"football-data-uk", "openfootball"}
    assert away_score.status == "agreed"
    assert away_score.candidate_value == 2


def test_team_name_string_mismatch_is_a_real_conflict_not_hidden() -> None:
    # Both sources agree on IDENTITY (same logical team) but report
    # different exact strings ("Bournemouth" vs "AFC Bournemouth") for the
    # `name` metric itself -- real, honest evidence of a naming difference,
    # never silently picked/averaged away.
    decisions, _meta = resolve_and_reconcile(_combined_observations())
    name_decision = next(
        d
        for d in decisions
        if d.entity_type == "team"
        and d.metric_name == "name"
        and d.logical_entity_key == "team:ENG_PL:bournemouth"
    )
    assert name_decision.status == "conflict"
    assert name_decision.evidence["values_by_source"] == {
        "football-data-uk": "Bournemouth",
        "openfootball": "AFC Bournemouth",
    }


def test_team_match_shots_is_single_source_openfootball_never_reports_stats() -> None:
    decisions, _meta = resolve_and_reconcile(_combined_observations())
    shots_decisions = [
        d for d in decisions if d.entity_type == "team" and d.metric_name == "shots_total"
    ]
    assert len(shots_decisions) == 2
    assert all(d.status == "single_source" for d in shots_decisions)
    assert all(d.participating_sources == ("football-data-uk",) for d in shots_decisions)
