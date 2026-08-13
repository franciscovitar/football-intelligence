from __future__ import annotations

from football_intelligence.data_mesh.adapters.football_data_uk import parse_results_csv

_CSV_TEXT = (
    "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,Referee,"
    "HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR,B365H,B365D,B365A\n"
    "E0,15/08/2025,20:00,Liverpool,Bournemouth,4,2,H,1,0,H,A Taylor,"
    "19,10,10,3,7,10,6,7,1,2,0,0,1.30,6.00,8.50\n"
)


def test_full_time_goals_map_to_home_away_score() -> None:
    observations = parse_results_csv(
        _CSV_TEXT, division_code="E0", season_code="2526", ingestion_run_id=None
    )
    match_observations = {o.metric_name: o.value for o in observations if o.entity_type == "match"}
    assert match_observations["home_score"] == 4
    assert match_observations["away_score"] == 2
    assert match_observations["status"] == "finished"


def test_shots_and_cards_map_to_team_metrics() -> None:
    observations = parse_results_csv(
        _CSV_TEXT, division_code="E0", season_code="2526", ingestion_run_id=None
    )
    liverpool = {
        o.metric_name: o.value
        for o in observations
        if o.entity_type == "team" and o.entity_source_id == "Liverpool"
    }
    assert liverpool["shots_total"] == 19
    assert liverpool["shots_on_target"] == 10
    assert liverpool["fouls"] == 7
    assert liverpool["corners"] == 6
    assert liverpool["yellow_cards"] == 1
    assert liverpool["red_cards"] == 0  # a genuine reported zero, not missing


def test_odds_columns_never_become_objective_metrics() -> None:
    observations = parse_results_csv(
        _CSV_TEXT, division_code="E0", season_code="2526", ingestion_run_id=None
    )
    metric_names = {o.metric_name for o in observations}
    assert not any("365" in name.lower() or "odds" in name.lower() for name in metric_names)
    # Only the documented, mapped metric names ever appear.
    assert metric_names <= {
        "name",
        "status",
        "home_score",
        "away_score",
        "shots_total",
        "shots_on_target",
        "fouls",
        "corners",
        "yellow_cards",
        "red_cards",
    }


def test_missing_column_stays_missing_not_fabricated() -> None:
    # This file has no HO/AO (offsides) columns at all -- the site simply
    # does not publish them for this division/season, so `offsides` must
    # never appear as an observation, missing rather than a guessed value.
    observations = parse_results_csv(
        _CSV_TEXT, division_code="E0", season_code="2526", ingestion_run_id=None
    )
    assert not any(o.metric_name == "offsides" for o in observations)


def test_blank_stat_cell_is_missing_not_zero() -> None:
    csv_with_blank = (
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR\n"
        "E0,15/08/2025,20:00,Liverpool,Bournemouth,4,2,H,,10,10,3,7,10,6,7,1,2,0,0\n"
    )
    observations = parse_results_csv(
        csv_with_blank, division_code="E0", season_code="2526", ingestion_run_id=None
    )
    liverpool_shots = [
        o
        for o in observations
        if o.entity_type == "team"
        and o.entity_source_id == "Liverpool"
        and o.metric_name == "shots_total"
    ]
    assert liverpool_shots == []


def test_serie_a_shots_carry_a_distinct_semantic_version() -> None:
    # Football-Data.co.uk documents a different underlying source
    # (Gazzetta.it) for Italian match statistics than for most other
    # leagues -- Serie A shot metrics must be tagged distinctly so they are
    # never blindly treated as directly comparable to another league's.
    csv_text = _CSV_TEXT.replace("E0,", "I1,")
    observations = parse_results_csv(
        csv_text, division_code="I1", season_code="2526", ingestion_run_id=None
    )
    shots = [o for o in observations if o.metric_name == "shots_total"]
    assert shots
    assert all(o.semantic_version == "football-data-uk-shots-ITA-v1" for o in shots)

    fouls = [o for o in observations if o.metric_name == "fouls"]
    assert all(o.semantic_version == "football-data-uk-v1" for o in fouls)


def test_match_entity_source_id_is_deterministic_composite_key() -> None:
    # The site publishes no numeric match id -- the synthetic key must be
    # fully reproducible from the same real published fields.
    first = parse_results_csv(
        _CSV_TEXT, division_code="E0", season_code="2526", ingestion_run_id=None
    )
    second = parse_results_csv(
        _CSV_TEXT, division_code="E0", season_code="2526", ingestion_run_id=None
    )
    first_match_id = next(o.entity_source_id for o in first if o.entity_type == "match")
    second_match_id = next(o.entity_source_id for o in second if o.entity_type == "match")
    assert first_match_id == second_match_id
    assert "Liverpool" in first_match_id
    assert "Bournemouth" in first_match_id
