from __future__ import annotations

from football_intelligence.data_mesh.adapters.thesportsdb import parse_event_stats, parse_lineup

_EVENT_STATS_PAYLOAD = {
    "eventstats": [
        {
            "idStatistic": "1",
            "idEvent": "2475153",
            "strStat": "Shots on Goal",
            "intHome": "10",
            "intAway": "3",
        },
        {
            "idStatistic": "2",
            "idEvent": "2475153",
            "strStat": "Shots off Goal",
            "intHome": "22",
            "intAway": "4",
        },
        {
            "idStatistic": "3",
            "idEvent": "2475153",
            "strStat": "Total Shots",
            "intHome": "39",
            "intAway": "8",
        },
        {
            "idStatistic": "4",
            "idEvent": "2475153",
            "strStat": "Blocked Shots",
            "intHome": "7",
            "intAway": "1",
        },
        {
            "idStatistic": "5",
            "idEvent": "2475153",
            "strStat": "Shots insidebox",
            "intHome": "27",
            "intAway": "5",
        },
    ]
}


def _parse() -> list:
    return parse_event_stats(
        _EVENT_STATS_PAYLOAD,
        match_id="2475153",
        competition_external_id="4331",
        home_team_external_id="home1",
        away_team_external_id="away1",
        ingestion_run_id=None,
    )


def test_shots_on_goal_maps_to_shots_on_target() -> None:
    observations = _parse()
    values = {
        (o.entity_source_id, o.value) for o in observations if o.metric_name == "shots_on_target"
    }
    assert values == {("home1", 10), ("away1", 3)}


def test_total_shots_maps_to_shots_total() -> None:
    observations = _parse()
    values = {(o.entity_source_id, o.value) for o in observations if o.metric_name == "shots_total"}
    assert values == {("home1", 39), ("away1", 8)}


def test_blocked_shots_maps_to_blocked_shots() -> None:
    observations = _parse()
    values = {
        (o.entity_source_id, o.value) for o in observations if o.metric_name == "blocked_shots"
    }
    assert values == {("home1", 7), ("away1", 1)}


def test_shots_insidebox_maps_to_shots_inside_box() -> None:
    observations = _parse()
    values = {
        (o.entity_source_id, o.value) for o in observations if o.metric_name == "shots_inside_box"
    }
    assert values == {("home1", 27), ("away1", 5)}


def test_shots_off_goal_never_becomes_shots_outside_box() -> None:
    # "Shots off Goal" (off-target) and `shots_outside_box` (outside the
    # penalty area) are different classifications -- this field must never
    # be silently mapped into an existing metric it does not actually match.
    observations = _parse()
    metric_names = {o.metric_name for o in observations}
    assert "shots_outside_box" not in metric_names
    # Only the 4 verified fields are ever emitted for a 5-row payload.
    assert metric_names == {"shots_on_target", "shots_total", "blocked_shots", "shots_inside_box"}


def test_event_stats_all_home_values_are_present_no_fabrication() -> None:
    # Every mapped stat has a real reported value for both teams -- nothing
    # is invented when the endpoint actually returned a row for it.
    observations = _parse()
    assert len(observations) == 8  # 4 metrics x 2 teams


_LINEUP_PAYLOAD = {
    "lineup": [
        {
            "idLineup": "1",
            "idEvent": "2475153",
            "strPosition": "Goalkeeper",
            "strHome": "No",
            "strSubstitute": "No",
            "intSquadNumber": None,
            "idPlayer": "111",
            "strPlayer": "Player One",
            "idTeam": "133655",
            "strTeam": "Wolfsburg",
        },
        {
            "idLineup": "2",
            "idEvent": "2475153",
            "strPosition": "Right-Back",
            "strHome": "No",
            "strSubstitute": "Yes",
            "intSquadNumber": "7",
            "idPlayer": "222",
            "strPlayer": "Player Two",
            "idTeam": "133655",
            "strTeam": "Wolfsburg",
        },
    ]
}


def test_lineup_returns_at_most_five_rows_worth_of_players() -> None:
    # The Free endpoint itself caps at 5 rows; this fixture proves the
    # adapter faithfully passes through whatever bounded sample it receives
    # without trying to pad or infer a full squad.
    observations = parse_lineup(
        _LINEUP_PAYLOAD, match_id="2475153", competition_external_id="4331", ingestion_run_id=None
    )
    player_ids = {o.entity_source_id for o in observations}
    assert player_ids == {"111", "222"}


def test_lineup_shirt_number_missing_stays_missing_not_zero() -> None:
    # Player One's intSquadNumber is null -- no shirt_number observation at
    # all, never a fabricated 0. Player Two's is "7" -- a real reported
    # value, captured as 7.
    observations = parse_lineup(
        _LINEUP_PAYLOAD, match_id="2475153", competition_external_id="4331", ingestion_run_id=None
    )
    shirt_numbers = {
        o.entity_source_id: o.value for o in observations if o.metric_name == "shirt_number"
    }
    assert shirt_numbers == {"222": 7}
    assert "111" not in shirt_numbers


def test_lineup_started_reflects_substitute_flag() -> None:
    observations = parse_lineup(
        _LINEUP_PAYLOAD, match_id="2475153", competition_external_id="4331", ingestion_run_id=None
    )
    started = {o.entity_source_id: o.value for o in observations if o.metric_name == "started"}
    assert started == {"111": True, "222": False}
