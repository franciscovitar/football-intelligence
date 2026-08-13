from __future__ import annotations

from football_intelligence.data_mesh.adapters.statsbomb_open import (
    find_competition_season,
    parse_match_events,
    parse_match_list,
)

# Payload shapes below mirror real StatsBomb Open Data responses, verified
# live (Bundesliga 2023/24, competition_id=9, season_id=281) during Block 14
# implementation.

_COMPETITIONS_PAYLOAD = [
    {
        "competition_id": 9,
        "season_id": 281,
        "country_name": "Germany",
        "competition_name": "1. Bundesliga",
        "competition_gender": "male",
        "season_name": "2023/2024",
    },
    {
        "competition_id": 135,
        "season_id": 281,
        "country_name": "Germany",
        "competition_name": "Frauen Bundesliga",
        "competition_gender": "female",
        "season_name": "2023/2024",
    },
]

_MATCH_LIST_PAYLOAD = [
    {
        "match_id": 3895292,
        "match_date": "2024-04-06",
        "competition": {"competition_name": "1. Bundesliga"},
        "home_team": {"home_team_id": 190, "home_team_name": "Union Berlin"},
        "away_team": {"away_team_id": 904, "away_team_name": "Bayer Leverkusen"},
        "home_score": 0,
        "away_score": 5,
    }
]

_HOME_PLAYER = {"id": 8221, "name": "Jonathan Tah"}
_SHOOTER = {"id": 11391, "name": "Borja Iglesias Quintas"}
_TEAM = {"id": 904, "name": "Bayer Leverkusen"}

_EVENTS_PAYLOAD = [
    {
        "type": {"name": "Starting XI"},
        "team": _TEAM,
        "tactics": {
            "formation": 442,
            "lineup": [
                {"player": _SHOOTER, "position": {"name": "Center Forward"}, "jersey_number": 9},
                {"player": _HOME_PLAYER, "position": {"name": "Center Back"}, "jersey_number": 4},
            ],
        },
    },
    {
        "type": {"name": "Pass"},
        "team": _TEAM,
        "player": _HOME_PLAYER,
        "pass": {"shot_assist": True, "assisted_shot_id": "shot-1"},
    },
    {
        "type": {"name": "Shot"},
        "team": _TEAM,
        "player": _SHOOTER,
        "shot": {
            "statsbomb_xg": 0.084877156,
            "outcome": {"name": "Off T"},
        },
    },
    {
        "type": {"name": "Foul Committed"},
        "team": _TEAM,
        "player": _HOME_PLAYER,
        "foul_committed": {"card": {"name": "Yellow Card"}},
    },
]


def test_find_competition_season_matches_exact_name_and_gender() -> None:
    result = find_competition_season(
        _COMPETITIONS_PAYLOAD, competition_name="1. Bundesliga", season_name="2023/2024"
    )
    assert result == (9, 281)


def test_find_competition_season_returns_none_when_absent() -> None:
    result = find_competition_season(
        _COMPETITIONS_PAYLOAD, competition_name="Premier League", season_name="2023/2024"
    )
    assert result is None


def test_parse_match_list_extracts_scores_and_names() -> None:
    observations = parse_match_list(
        _MATCH_LIST_PAYLOAD,
        competition_code="GER_BL1",
        season_label="2023/2024",
        ingestion_run_id=None,
    )
    scores = {
        obs.metric_name: obs.value
        for obs in observations
        if obs.entity_type == "match" and obs.metric_name in ("home_score", "away_score", "status")
    }
    assert scores["home_score"] == 0
    assert scores["away_score"] == 5
    # StatsBomb Open Data only ever publishes completed historical matches.
    assert scores["status"] == "finished"


def test_parse_match_events_only_derives_supported_metrics() -> None:
    observations = parse_match_events(
        _EVENTS_PAYLOAD, match_id="3895292", competition_code="GER_BL1", ingestion_run_id=None
    )
    metric_names = {obs.metric_name for obs in observations}
    # Never fabricated: no minutes, no assists, no xA, no passes_accurate
    # derived from a payload shape that doesn't support it here.
    assert "minutes" not in metric_names
    assert "assists" not in metric_names
    assert "advanced.xa" not in metric_names


def test_statsbomb_xg_is_captured_when_present() -> None:
    observations = parse_match_events(
        _EVENTS_PAYLOAD, match_id="3895292", competition_code="GER_BL1", ingestion_run_id=None
    )
    xg_obs = next(
        obs
        for obs in observations
        if obs.metric_name == "advanced.xg" and obs.entity_source_id == "3895292:11391"
    )
    assert xg_obs.value == 0.0849


def test_unsupported_metric_stays_missing_never_fabricated() -> None:
    # This adapter never derives "duels_won" or "passes" xA-style advanced
    # metrics -- they must never appear as observations, not even as zero.
    observations = parse_match_events(
        _EVENTS_PAYLOAD, match_id="3895292", competition_code="GER_BL1", ingestion_run_id=None
    )
    metric_names = {obs.metric_name for obs in observations}
    assert "duels_won" not in metric_names
    assert "duels_total" not in metric_names


def test_appeared_player_gets_real_zero_not_missing_for_untriggered_metrics() -> None:
    # Jonathan Tah appeared (Foul Committed, Pass) but never took a shot:
    # shots_total must be a real, explicit 0 for him, not simply absent.
    observations = parse_match_events(
        _EVENTS_PAYLOAD, match_id="3895292", competition_code="GER_BL1", ingestion_run_id=None
    )
    tah_shots = next(
        obs
        for obs in observations
        if obs.entity_source_id == "3895292:8221" and obs.metric_name == "shots_total"
    )
    assert tah_shots.value == 0


def test_player_never_appearing_in_events_has_no_observations() -> None:
    observations = parse_match_events(
        _EVENTS_PAYLOAD, match_id="3895292", competition_code="GER_BL1", ingestion_run_id=None
    )
    entity_ids = {obs.entity_source_id for obs in observations}
    assert "3895292:999999" not in entity_ids


def test_yellow_card_derived_from_foul_committed() -> None:
    observations = parse_match_events(
        _EVENTS_PAYLOAD, match_id="3895292", competition_code="GER_BL1", ingestion_run_id=None
    )
    yellow = next(
        obs
        for obs in observations
        if obs.entity_source_id == "3895292:8221" and obs.metric_name == "yellow_cards"
    )
    assert yellow.value == 1


def test_starting_xi_produces_formation_and_started_flags() -> None:
    observations = parse_match_events(
        _EVENTS_PAYLOAD, match_id="3895292", competition_code="GER_BL1", ingestion_run_id=None
    )
    formation = next(obs for obs in observations if obs.metric_name == "formation")
    assert formation.value == "4-4-2"

    started_true = next(
        obs
        for obs in observations
        if obs.entity_source_id == "3895292:11391" and obs.metric_name == "started"
    )
    assert started_true.value is True
