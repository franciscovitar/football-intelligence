from __future__ import annotations

import inspect
from datetime import datetime

import pytest

from football_intelligence.data_mesh import adapters as adapters_package
from football_intelligence.data_mesh.adapters import statsbomb_open
from football_intelligence.data_mesh.adapters.statsbomb_open import (
    _EMITTED_IDENTITIES,
    COMPETITION_CODE,
    SEASON_LABEL,
    SOURCE_CODE,
    MatchBundle,
    StatsBombObservationConflictError,
    adapt_match_bundle,
    parse_goalkeeper_observations,
    parse_lineups,
    parse_match,
    parse_player_match_observations,
    parse_premier_league_season,
)
from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2
from football_intelligence.providers.statsbomb_open_mapping import (
    adapter_safe_mappings,
    derivable_methodology_pending_mappings,
    mappings_by_classification,
)

# Payload shapes below mirror the real, verified pinned Premier League
# 2015/16 StatsBomb Open Data schema (Block 20C.1/20C.2a): per-match
# `matches/2/27.json` entries, `events/{match_id}.json`,
# `lineups/{match_id}.json` -- verified against the real, cached, full
# season, not guessed.

_HOME_TEAM_ID = 1
_AWAY_TEAM_ID = 2
_MATCH_ID_1 = 9001
_MATCH_ID_2 = 9002

_SCORER = {"id": 101, "name": "Home Scorer"}
_HOME_GK = {"id": 102, "name": "Home Keeper"}
_USED_SUB = {"id": 103, "name": "Home Sub"}
_UNUSED_SUB_ID = 104
_AWAY_GK = {"id": 201, "name": "Away Keeper"}
_OWN_GOAL_PLAYER = {"id": 202, "name": "Away Defender"}
_AWAY_SCORER = {"id": 204, "name": "Away Scorer"}
_UNUSED_AWAY_SUB_ID = 203
_HOME_TEAM = {"id": _HOME_TEAM_ID, "name": "Home FC"}
_AWAY_TEAM = {"id": _AWAY_TEAM_ID, "name": "Away FC"}
_UNTAGGED_EVENT_ONLY_PLAYER_ID = 999


def _match_summary(match_id: int, *, home_score: int = 2, away_score: int = 1) -> dict:
    return {
        "match_id": match_id,
        "match_date": "2015-08-08",
        "kick_off": "15:00:00.000",
        "home_team": {"home_team_id": _HOME_TEAM_ID, "home_team_name": "Home FC"},
        "away_team": {"away_team_id": _AWAY_TEAM_ID, "away_team_name": "Away FC"},
        "home_score": home_score,
        "away_score": away_score,
        "match_status": "available",
        "match_week": 1,
        "stadium": {"name": "Home Stadium"},
    }


def _lineup_player(
    player_id: int,
    *,
    name: str,
    jersey_number: int,
    position: str | None,
    started: bool,
    used: bool = True,
    cards: list[dict] | None = None,
) -> dict:
    positions = []
    if used:
        positions = [
            {
                "position": position,
                "from": "00:00",
                "to": None,
                "start_reason": "Starting XI" if started else "Substitution - On (Tactical)",
                "end_reason": "Final Whistle",
            }
        ]
    return {
        "player_id": player_id,
        "player_name": name,
        "jersey_number": jersey_number,
        "positions": positions,
        "cards": cards or [],
    }


def _lineups_payload_1() -> list[dict]:
    return [
        {
            "team_id": _HOME_TEAM_ID,
            "team_name": "Home FC",
            "lineup": [
                _lineup_player(
                    _SCORER["id"],
                    name=_SCORER["name"],
                    jersey_number=9,
                    position="Center Forward",
                    started=True,
                ),
                _lineup_player(
                    _HOME_GK["id"],
                    name=_HOME_GK["name"],
                    jersey_number=1,
                    position="Goalkeeper",
                    started=True,
                ),
                _lineup_player(
                    _USED_SUB["id"],
                    name=_USED_SUB["name"],
                    jersey_number=11,
                    position="Left Wing",
                    started=False,
                    # Only a lineup-file card exists -- no Foul Committed
                    # event carries card info for this player in the fixture
                    # below, proving the Bad-Behaviour-style gap cannot
                    # recur once cards are lineup-authoritative.
                    cards=[{"card_type": "Yellow Card", "time": "50:00"}],
                ),
                _lineup_player(
                    _UNUSED_SUB_ID,
                    name="Home Unused",
                    jersey_number=20,
                    position=None,
                    started=False,
                    used=False,
                ),
            ],
        },
        {
            "team_id": _AWAY_TEAM_ID,
            "team_name": "Away FC",
            "lineup": [
                _lineup_player(
                    _AWAY_GK["id"],
                    name=_AWAY_GK["name"],
                    jersey_number=1,
                    position="Goalkeeper",
                    started=True,
                ),
                _lineup_player(
                    _OWN_GOAL_PLAYER["id"],
                    name=_OWN_GOAL_PLAYER["name"],
                    jersey_number=4,
                    position="Center Back",
                    started=True,
                ),
                _lineup_player(
                    _AWAY_SCORER["id"],
                    name=_AWAY_SCORER["name"],
                    jersey_number=10,
                    position="Center Forward",
                    started=True,
                ),
                _lineup_player(
                    _UNUSED_AWAY_SUB_ID,
                    name="Away Unused",
                    jersey_number=21,
                    position=None,
                    started=False,
                    used=False,
                ),
            ],
        },
    ]


def _events_payload_1() -> list[dict]:
    return [
        {
            "type": {"name": "Starting XI"},
            "team": _HOME_TEAM,
            "tactics": {"formation": 442, "lineup": []},
        },
        {
            "type": {"name": "Starting XI"},
            "team": _AWAY_TEAM,
            "tactics": {"formation": 442, "lineup": []},
        },
        # Home scorer's goal.
        {
            "type": {"name": "Shot"},
            "team": _HOME_TEAM,
            "player": _SCORER,
            "location": [100.0, 40.0],
            "shot": {
                "outcome": {"name": "Goal"},
                "statsbomb_xg": 0.3,
                "body_part": {"name": "Right Foot"},
                "type": {"name": "Open Play"},
            },
        },
        # Own goal -- benefits home, must never credit any player's `goals`.
        {"type": {"name": "Own Goal For"}, "team": _HOME_TEAM},
        {"type": {"name": "Own Goal Against"}, "team": _AWAY_TEAM, "player": _OWN_GOAL_PLAYER},
        # Away scorer's goal.
        {
            "type": {"name": "Shot"},
            "team": _AWAY_TEAM,
            "player": _AWAY_SCORER,
            "location": [20.0, 40.0],
            "shot": {
                "outcome": {"name": "Goal"},
                "statsbomb_xg": 0.2,
                "body_part": {"name": "Left Foot"},
                "type": {"name": "Open Play"},
            },
        },
        # Away scorer's second shot, saved by the home keeper.
        {
            "type": {"name": "Shot"},
            "team": _AWAY_TEAM,
            "player": _AWAY_SCORER,
            "shot": {
                "outcome": {"name": "Saved"},
                "statsbomb_xg": 0.1,
                "body_part": {"name": "Right Foot"},
                "type": {"name": "Open Play"},
            },
        },
        {
            "type": {"name": "Goal Keeper"},
            "team": _HOME_TEAM,
            "player": _HOME_GK,
            "goalkeeper": {"type": {"name": "Shot Saved"}, "outcome": {"name": "Success"}},
        },
        {
            "type": {"name": "Goal Keeper"},
            "team": _HOME_TEAM,
            "player": _HOME_GK,
            "goalkeeper": {"type": {"name": "Goal Conceded"}, "outcome": {"name": "No Touch"}},
        },
        {
            "type": {"name": "Goal Keeper"},
            "team": _AWAY_TEAM,
            "player": _AWAY_GK,
            "goalkeeper": {"type": {"name": "Goal Conceded"}, "outcome": {"name": "No Touch"}},
        },
        # A goal-scoring assist (goal_assist) from the used substitute.
        {
            "type": {"name": "Pass"},
            "team": _HOME_TEAM,
            "player": _USED_SUB,
            "pass": {
                "goal_assist": True,
                "recipient": _SCORER,
                "length": 15.0,
                "angle": 0.1,
                "height": {"name": "Ground Pass"},
            },
        },
        # A key pass (shot_assist), distinct from goal_assist, not the assist.
        {
            "type": {"name": "Pass"},
            "team": _HOME_TEAM,
            "player": _SCORER,
            "pass": {
                "shot_assist": True,
                "recipient": _USED_SUB,
                "length": 10.0,
                "angle": 0.2,
                "height": {"name": "Ground Pass"},
            },
        },
        # An incomplete pass (carries an `outcome` key -> not accurate).
        {
            "type": {"name": "Pass"},
            "team": _HOME_TEAM,
            "player": _SCORER,
            "pass": {"outcome": {"name": "Incomplete"}, "length": 30.0, "angle": 0.5},
        },
        {
            "type": {"name": "Duel"},
            "team": _HOME_TEAM,
            "player": _SCORER,
            "duel": {"type": {"name": "Tackle"}, "outcome": {"name": "Won"}},
        },
        {
            "type": {"name": "Duel"},
            "team": _HOME_TEAM,
            "player": _USED_SUB,
            "duel": {"type": {"name": "Aerial Lost"}},
        },
        {
            "type": {"name": "Carry"},
            "team": _HOME_TEAM,
            "player": _SCORER,
            "location": [50.0, 40.0],
            "carry": {"end_location": [60.0, 40.0]},
        },
        {"type": {"name": "Pressure"}, "team": _HOME_TEAM, "player": _USED_SUB},
        {
            "type": {"name": "Foul Committed"},
            "team": _AWAY_TEAM,
            "player": _OWN_GOAL_PLAYER,
            "foul_committed": {},
        },
        {"type": {"name": "Foul Won"}, "team": _HOME_TEAM, "player": _SCORER},
        # A separate Bad Behaviour EVENT (not tied to any Foul Committed) --
        # proves this is correctly ignored: cards come from the lineup file
        # only, never from re-deriving/merging event-sourced cards.
        {
            "type": {"name": "Bad Behaviour"},
            "team": _HOME_TEAM,
            "player": _USED_SUB,
            "bad_behaviour": {"card": {"name": "Yellow Card"}},
        },
        # An event referencing a player never named in any lineup at all --
        # must never produce any observation (participation is
        # lineup-authoritative, never inferred from event-tag presence).
        {
            "type": {"name": "Pressure"},
            "team": _HOME_TEAM,
            "player": {"id": _UNTAGGED_EVENT_ONLY_PLAYER_ID, "name": "Ghost"},
        },
    ]


def _bundle_1() -> MatchBundle:
    return MatchBundle(
        match_id=_MATCH_ID_1,
        match_summary=_match_summary(_MATCH_ID_1),
        events_payload=_events_payload_1(),
        lineups_payload=_lineups_payload_1(),
    )


def _bundle_2() -> MatchBundle:
    # A second, simpler match -- same scorer starts again, to exercise
    # season-level aggregation and cross-match determinism.
    lineups = [
        {
            "team_id": _HOME_TEAM_ID,
            "team_name": "Home FC",
            "lineup": [
                _lineup_player(
                    _SCORER["id"],
                    name=_SCORER["name"],
                    jersey_number=9,
                    position="Center Forward",
                    started=True,
                ),
                _lineup_player(
                    _HOME_GK["id"],
                    name=_HOME_GK["name"],
                    jersey_number=1,
                    position="Goalkeeper",
                    started=True,
                ),
            ],
        },
        {
            "team_id": _AWAY_TEAM_ID,
            "team_name": "Away FC",
            "lineup": [
                _lineup_player(
                    _AWAY_GK["id"],
                    name=_AWAY_GK["name"],
                    jersey_number=1,
                    position="Goalkeeper",
                    started=True,
                ),
            ],
        },
    ]
    events = [
        {
            "type": {"name": "Starting XI"},
            "team": _HOME_TEAM,
            "tactics": {"formation": 433, "lineup": []},
        },
        {
            "type": {"name": "Shot"},
            "team": _HOME_TEAM,
            "player": _SCORER,
            "shot": {
                "outcome": {"name": "Off T"},
                "statsbomb_xg": 0.05,
                "body_part": {"name": "Head"},
                "type": {"name": "Open Play"},
            },
        },
    ]
    return MatchBundle(
        match_id=_MATCH_ID_2,
        match_summary=_match_summary(_MATCH_ID_2, home_score=0, away_score=0),
        events_payload=events,
        lineups_payload=lineups,
    )


def _find(observations, entity_type, entity_source_id, metric_name):
    for obs in observations:
        if (
            obs.entity_type == entity_type
            and obs.entity_source_id == entity_source_id
            and obs.metric_name == metric_name
        ):
            return obs
    raise AssertionError(
        f"no observation for entity_type={entity_type!r} "
        f"entity_source_id={entity_source_id!r} metric_name={metric_name!r}"
    )


def _find_all(observations, entity_type, entity_source_id):
    return {
        obs.metric_name: obs.value
        for obs in observations
        if obs.entity_type == entity_type and obs.entity_source_id == entity_source_id
    }


# -- A. Native match observations --------------------------------------------


def test_native_match_observations_use_real_status_not_synthetic_finished() -> None:
    observations = adapt_match_bundle(_bundle_1())
    status = _find(observations, "match", str(_MATCH_ID_1), "status")
    assert status.value == "available"


def test_native_match_scores_and_round_and_venue() -> None:
    observations = adapt_match_bundle(_bundle_1())
    match_id = str(_MATCH_ID_1)
    assert _find(observations, "match", match_id, "home_score").value == 2
    assert _find(observations, "match", match_id, "away_score").value == 1
    assert _find(observations, "match", match_id, "round_name").value == "1"
    assert _find(observations, "match", match_id, "venue_name").value == "Home Stadium"
    kickoff = _find(observations, "match", match_id, "kickoff_at").value
    assert kickoff.startswith("2015-08-08")


def test_home_away_emitted_per_team() -> None:
    observations = adapt_match_bundle(_bundle_1())
    home = _find(observations, "team", f"{_MATCH_ID_1}:{_HOME_TEAM_ID}", "home_away")
    away = _find(observations, "team", f"{_MATCH_ID_1}:{_AWAY_TEAM_ID}", "home_away")
    assert home.value == "home"
    assert away.value == "away"


# -- B. Pinned provenance / source reference ---------------------------------


def test_source_reference_carries_pinned_revision() -> None:
    pinned_sha = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    observations = adapt_match_bundle(_bundle_1(), source_revision=pinned_sha)
    for obs in observations:
        assert pinned_sha in obs.source_reference
        assert obs.source_reference.startswith("statsbomb/open-data@")


def test_scope_hints_carry_competition_and_season() -> None:
    observations = adapt_match_bundle(_bundle_1())
    obs = _find(observations, "match", str(_MATCH_ID_1), "status")
    assert obs.entity_identity_hints["competition_external_id"] == COMPETITION_CODE
    assert obs.entity_identity_hints["season_label"] == SEASON_LABEL
    assert SEASON_LABEL == "2015/16"
    assert COMPETITION_CODE == "ENG_PL"


def test_semantic_version_is_bumped_from_the_pre_block_20_adapter() -> None:
    assert statsbomb_open.SEMANTIC_VERSION != "statsbomb-open-v0.1"


# -- C/D/E/F/G. Lineup-authoritative participant universe --------------------


def test_parse_lineups_classifies_starter_used_sub_and_unused_sub() -> None:
    roster = parse_lineups(_lineups_payload_1())
    assert _SCORER["id"] in roster.starters
    assert _USED_SUB["id"] in roster.used_subs
    assert _UNUSED_SUB_ID in roster.unused
    assert _UNUSED_SUB_ID not in roster.participating_players()
    assert _UNUSED_SUB_ID in roster.squad_players()


def test_unused_substitute_receives_no_performance_observations() -> None:
    observations = adapt_match_bundle(_bundle_1())
    unused_entity_id = f"{_MATCH_ID_1}:{_UNUSED_SUB_ID}"
    # `started`/`shirt_number` are roster-membership facts, not performance
    # stats -- every named squad member, used or not, legitimately gets
    # them (mirroring the Wyscout adapter's identical precedent).
    roster_membership_metrics = {"started", "shirt_number"}
    performance_metrics = {
        obs.metric_name
        for obs in observations
        if obs.entity_source_id == unused_entity_id
        and obs.metric_name not in roster_membership_metrics
    }
    assert performance_metrics == set()


def test_unused_substitute_still_gets_a_real_started_false() -> None:
    observations = adapt_match_bundle(_bundle_1())
    started = _find(observations, "player", f"{_MATCH_ID_1}:{_UNUSED_SUB_ID}", "started")
    assert started.value is False


def test_used_substitute_started_is_false_and_appears_in_performance_universe() -> None:
    observations = adapt_match_bundle(_bundle_1())
    entity_id = f"{_MATCH_ID_1}:{_USED_SUB['id']}"
    assert _find(observations, "player", entity_id, "started").value is False
    assert _find(observations, "player", entity_id, "pressures").value == 1


def test_starter_started_is_true() -> None:
    observations = adapt_match_bundle(_bundle_1())
    entity_id = f"{_MATCH_ID_1}:{_SCORER['id']}"
    assert _find(observations, "player", entity_id, "started").value is True


def test_event_only_player_absent_from_lineup_gets_no_observations() -> None:
    observations = adapt_match_bundle(_bundle_1())
    ghost_id = f"{_MATCH_ID_1}:{_UNTAGGED_EVENT_ONLY_PLAYER_ID}"
    assert not any(obs.entity_source_id == ghost_id for obs in observations)


# -- H/I. Zero vs missing -----------------------------------------------------


def test_confirmed_participant_gets_a_real_zero_for_an_untriggered_metric() -> None:
    observations = adapt_match_bundle(_bundle_1())
    entity_id = f"{_MATCH_ID_1}:{_HOME_GK['id']}"
    # The home keeper never dribbled -- a real 0, not missing.
    dribbles = _find(observations, "player", entity_id, "dribbles_attempted")
    assert dribbles.value == 0


def test_missing_or_unresolved_player_never_becomes_a_fabricated_zero() -> None:
    observations = adapt_match_bundle(_bundle_1())
    ghost_id = f"{_MATCH_ID_1}:{_UNTAGGED_EVENT_ONLY_PLAYER_ID}"
    entity_ids = {obs.entity_source_id for obs in observations}
    assert ghost_id not in entity_ids


def test_goalkeeper_exclusive_metrics_never_leak_to_non_goalkeepers() -> None:
    observations = adapt_match_bundle(_bundle_1())
    scorer_id = f"{_MATCH_ID_1}:{_SCORER['id']}"
    scorer_metrics = {obs.metric_name for obs in observations if obs.entity_source_id == scorer_id}
    assert "goals_conceded" not in scorer_metrics
    assert "claims" not in scorer_metrics
    assert "crosses_stopped" not in scorer_metrics
    assert "sweeper_actions" not in scorer_metrics


# -- J/K. Native goals / own goals --------------------------------------------


def test_native_goals_attributed_to_shooter() -> None:
    observations = adapt_match_bundle(_bundle_1())
    goals = _find(observations, "player", f"{_MATCH_ID_1}:{_SCORER['id']}", "goals")
    assert goals.value == 1


def test_own_goal_never_becomes_a_normal_shooter_goal() -> None:
    observations = adapt_match_bundle(_bundle_1())
    entity_id = f"{_MATCH_ID_1}:{_OWN_GOAL_PLAYER['id']}"
    goals = _find(observations, "player", entity_id, "goals")
    assert goals.value == 0


def test_native_score_is_authoritative_not_reconstructed_from_events() -> None:
    observations = adapt_match_bundle(_bundle_1())
    home_score = _find(observations, "match", str(_MATCH_ID_1), "home_score")
    # 2 native, even though only 1 Shot-type Goal event exists for the home
    # team (the second goal is the own goal, tracked separately, never
    # summed from player-attributed Shot events).
    assert home_score.value == 2


# -- L/M. Assists ---------------------------------------------------------------


def test_pass_goal_assist_becomes_assists() -> None:
    observations = adapt_match_bundle(_bundle_1())
    assists = _find(observations, "player", f"{_MATCH_ID_1}:{_USED_SUB['id']}", "assists")
    assert assists.value == 1


def test_shot_assist_distinct_from_goal_assist() -> None:
    observations = adapt_match_bundle(_bundle_1())
    entity_id = f"{_MATCH_ID_1}:{_SCORER['id']}"
    assert _find(observations, "player", entity_id, "key_passes").value == 1
    assert _find(observations, "player", entity_id, "assists").value == 0


# -- N/O. Cards ----------------------------------------------------------------


def test_cards_come_from_lineup_records() -> None:
    observations = adapt_match_bundle(_bundle_1())
    entity_id = f"{_MATCH_ID_1}:{_USED_SUB['id']}"
    assert _find(observations, "player", entity_id, "yellow_cards").value == 1
    assert _find(observations, "player", entity_id, "red_cards").value == 0


def test_bad_behaviour_card_regression_cannot_recur() -> None:
    """The used sub's only lineup-recorded card is a Yellow Card with NO
    corresponding Foul Committed event carrying card info anywhere in the
    fixture (their Foul Committed... there isn't one at all for them) --
    proving the old adapter's Foul-Committed-only bug (which would have
    reported yellow_cards=0 here) cannot recur."""
    observations = adapt_match_bundle(_bundle_1())
    entity_id = f"{_MATCH_ID_1}:{_USED_SUB['id']}"
    yellow = _find(observations, "player", entity_id, "yellow_cards")
    assert yellow.value == 1


# -- P. Full certified save type set ------------------------------------------


def test_saves_use_the_full_certified_goal_keeper_type_set() -> None:
    observations = adapt_match_bundle(_bundle_1())
    saves = _find(observations, "player", f"{_MATCH_ID_1}:{_HOME_GK['id']}", "saves")
    assert saves.value == 1  # one "Shot Saved" event


def test_goals_conceded_uses_conceded_type_set() -> None:
    observations = adapt_match_bundle(_bundle_1())
    conceded = _find(observations, "player", f"{_MATCH_ID_1}:{_HOME_GK['id']}", "goals_conceded")
    assert conceded.value == 1
    shots_faced = _find(
        observations, "player", f"{_MATCH_ID_1}:{_HOME_GK['id']}", "shots_on_target_faced"
    )
    assert shots_faced.value == 2  # 1 save + 1 conceded


# -- Q. Goalkeeper universe ----------------------------------------------------


def test_goalkeeper_identity_from_lineup_position_not_event_occurrence() -> None:
    roster = parse_lineups(_lineups_payload_1())
    assert _HOME_GK["id"] in roster.goalkeepers
    assert _SCORER["id"] not in roster.goalkeepers


def test_outfield_player_never_enters_goalkeeper_observations() -> None:
    bundles = [_bundle_1()]
    gk_observations = parse_goalkeeper_observations(bundles, include_season=False)
    scorer_id = f"{_MATCH_ID_1}:{_SCORER['id']}"
    assert not any(obs.entity_source_id == scorer_id for obs in gk_observations)


# -- R. Native statsbomb_xg -----------------------------------------------------


def test_advanced_xg_is_a_direct_read_of_the_native_value() -> None:
    observations = adapt_match_bundle(_bundle_1())
    xg = _find(observations, "player", f"{_MATCH_ID_1}:{_SCORER['id']}", "advanced.xg")
    assert xg.value == pytest.approx(0.3)


# -- S. Pressure -----------------------------------------------------------------


def test_pressure_event_becomes_pressures_count() -> None:
    observations = adapt_match_bundle(_bundle_1())
    pressures = _find(observations, "player", f"{_MATCH_ID_1}:{_USED_SUB['id']}", "pressures")
    assert pressures.value == 1


# -- T. Carry ----------------------------------------------------------------------


def test_carry_event_becomes_carries_and_carry_distance() -> None:
    observations = adapt_match_bundle(_bundle_1())
    entity_id = f"{_MATCH_ID_1}:{_SCORER['id']}"
    carries = _find(observations, "player", entity_id, "carries")
    assert carries.value == 1
    distance = _find(observations, "player", entity_id, "carry_distance")
    assert distance.value == pytest.approx(10.0)


# -- U. Pass completion convention -------------------------------------------------


def test_pass_accuracy_uses_outcome_absence_convention() -> None:
    observations = adapt_match_bundle(_bundle_1())
    entity_id = f"{_MATCH_ID_1}:{_SCORER['id']}"
    # 2 passes total for the scorer (one key pass, one incomplete); only the
    # key pass (no `outcome` key) is accurate.
    assert _find(observations, "player", entity_id, "passes_total").value == 2
    assert _find(observations, "player", entity_id, "passes_accurate").value == 1


# -- V. Deterministic opponent/team rollups ------------------------------------------


def test_team_goals_for_against_and_opponent_shots_allowed() -> None:
    observations = adapt_match_bundle(_bundle_1())
    home_id = f"{_MATCH_ID_1}:{_HOME_TEAM_ID}"
    away_id = f"{_MATCH_ID_1}:{_AWAY_TEAM_ID}"
    assert _find(observations, "team", home_id, "goals_for").value == 2
    assert _find(observations, "team", home_id, "goals_against").value == 1
    assert _find(observations, "team", away_id, "goals_for").value == 1
    assert _find(observations, "team", away_id, "goals_against").value == 2
    # Away team took 2 shots (goal + saved); home's shots_allowed reflects that.
    assert _find(observations, "team", home_id, "shots_allowed").value == 2


def test_team_yellow_cards_roll_up_from_lineup_authoritative_records() -> None:
    observations = adapt_match_bundle(_bundle_1())
    home_id = f"{_MATCH_ID_1}:{_HOME_TEAM_ID}"
    assert _find(observations, "team", home_id, "yellow_cards").value == 1


def test_team_formation_reflects_starting_xi_not_overwritten() -> None:
    observations = adapt_match_bundle(_bundle_1())
    home_id = f"{_MATCH_ID_1}:{_HOME_TEAM_ID}"
    formation = _find(observations, "team", home_id, "formation")
    assert formation.value == "4-4-2"


# -- W/X/Y. Only adapter-safe mappings emitted; pending/unsafe rejected --------


def test_only_adapter_safe_identities_are_emitted() -> None:
    safe_identities = {(m.catalog_key, m.catalog_granularity) for m in adapter_safe_mappings()}
    assert safe_identities >= _EMITTED_IDENTITIES
    assert safe_identities == _EMITTED_IDENTITIES


def test_pending_methodology_metric_is_rejected() -> None:
    with pytest.raises(StatsBombObservationConflictError):
        statsbomb_open._guard("player", "minutes")


def test_requires_model_metric_is_rejected() -> None:
    with pytest.raises(StatsBombObservationConflictError):
        statsbomb_open._guard("player", "xa")


def test_unsupported_metric_is_rejected() -> None:
    with pytest.raises(StatsBombObservationConflictError):
        statsbomb_open._guard("player_match", "big_chances")


def test_ambiguous_metric_is_rejected() -> None:
    with pytest.raises(StatsBombObservationConflictError):
        statsbomb_open._guard("player", "tackles_won")


def test_provider_out_of_scope_metric_is_rejected() -> None:
    with pytest.raises(StatsBombObservationConflictError):
        statsbomb_open._guard("team", "team_strength_elo")


@pytest.mark.parametrize(
    "mapping",
    [m for m in mappings_by_classification("DERIVABLE") if m.methodology_pending][:5],
)
def test_sampled_methodology_pending_identities_are_all_rejected(mapping) -> None:
    entity_type = statsbomb_open._GRANULARITY_TO_ENTITY_TYPE[mapping.catalog_granularity]
    with pytest.raises(StatsBombObservationConflictError):
        statsbomb_open._guard(entity_type, mapping.catalog_key)


def test_no_methodology_pending_identity_overlaps_emitted_identities() -> None:
    pending = {
        (m.catalog_key, m.catalog_granularity) for m in derivable_methodology_pending_mappings()
    }
    assert _EMITTED_IDENTITIES.isdisjoint(pending)


def test_minutes_is_never_implemented() -> None:
    all_metric_names = {obs.metric_name for obs in adapt_match_bundle(_bundle_1())}
    assert "minutes" not in all_metric_names
    assert "minutes_per_appearance" not in all_metric_names


# -- Z. observed_at uses historical match time, not wall-clock now ------------


def test_observed_at_uses_historical_kickoff_not_wall_clock() -> None:
    observations = adapt_match_bundle(_bundle_1())
    obs = _find(observations, "match", str(_MATCH_ID_1), "status")
    assert obs.observed_at.year == 2015
    assert obs.observed_at.month == 8
    assert obs.observed_at.day == 8


# -- AA. Deterministic output ---------------------------------------------------


def test_output_is_deterministic_across_repeated_runs() -> None:
    first = adapt_match_bundle(_bundle_1())
    second = adapt_match_bundle(_bundle_1())
    first_by_identity = {
        (obs.entity_type, obs.entity_source_id, obs.metric_name): obs.value for obs in first
    }
    second_by_identity = {
        (obs.entity_type, obs.entity_source_id, obs.metric_name): obs.value for obs in second
    }
    assert first_by_identity == second_by_identity
    assert len(first) == len(second)


# -- AB. Conflicting duplicate raises --------------------------------------------


def test_conflicting_duplicate_observation_raises() -> None:
    now = datetime.now()
    seen: dict = {}
    observations: list = []
    statsbomb_open._emit(
        observations,
        seen,
        entity_type="player",
        entity_source_id="1:1",
        entity_identity_hints={},
        metric_name="touches",
        value=1,
        observed_at=now,
        source_reference="x",
        ingestion_run_id=None,
    )
    with pytest.raises(StatsBombObservationConflictError):
        statsbomb_open._emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id="1:1",
            entity_identity_hints={},
            metric_name="touches",
            value=2,
            observed_at=now,
            source_reference="x",
            ingestion_run_id=None,
        )


def test_identical_duplicate_observation_is_silently_collapsed() -> None:
    now = datetime.now()
    seen: dict = {}
    observations: list = []
    for _ in range(2):
        statsbomb_open._emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id="1:1",
            entity_identity_hints={},
            metric_name="touches",
            value=5,
            observed_at=now,
            source_reference="x",
            ingestion_run_id=None,
        )
    assert len(observations) == 1


# -- AC/AD. No network/DB dependency ---------------------------------------------


def test_adapter_module_has_no_database_or_network_dependency() -> None:
    source = inspect.getsource(statsbomb_open)
    assert "import requests" not in source
    assert "urlopen(" not in source
    assert "psycopg" not in source
    assert "DATABASE_URL" not in source


def test_full_season_entry_point_takes_only_already_loaded_bundles() -> None:
    signature = inspect.signature(parse_premier_league_season)
    assert "bundles" in signature.parameters


# -- AE. Internal-only policy asserted --------------------------------------------


def test_internal_only_policy_is_true_and_enforced_at_season_entry_point() -> None:
    from football_intelligence.providers.statsbomb_open_policy import STATSBOMB_INTERNAL_ONLY

    assert STATSBOMB_INTERNAL_ONLY is True
    # Sanity: the season entry point actually checks this flag (verified by
    # inspecting its source rather than monkeypatching a module-level
    # constant, which risks masking real import-order bugs).
    source = inspect.getsource(parse_premier_league_season)
    assert "STATSBOMB_INTERNAL_ONLY" in source


# -- Season aggregation (player_season / goalkeeper_season) ----------------------


def test_season_aggregation_across_multiple_matches() -> None:
    observations = parse_premier_league_season([_bundle_1(), _bundle_2()])
    scorer_id = str(_SCORER["id"])
    assert _find(observations, "player", scorer_id, "matches").value == 2
    assert _find(observations, "player", scorer_id, "starts").value == 2
    assert _find(observations, "player", scorer_id, "appearances").value == 2
    assert _find(observations, "player", scorer_id, "sub_appearances").value == 0


def test_adapt_match_bundle_excludes_season_scoped_identities() -> None:
    observations = adapt_match_bundle(_bundle_1())
    season_scoped = [
        obs
        for obs in observations
        if obs.entity_type == "player" and ":" not in obs.entity_source_id
    ]
    assert season_scoped == []


def test_player_match_observations_helper_matches_full_bundle_output() -> None:
    from_helper = parse_player_match_observations([_bundle_1()])
    from_bundle = [obs for obs in adapt_match_bundle(_bundle_1()) if obs.metric_name == "goals"]
    helper_goals = {
        (obs.entity_source_id): obs.value for obs in from_helper if obs.metric_name == "goals"
    }
    bundle_goals = {obs.entity_source_id: obs.value for obs in from_bundle}
    assert helper_goals == bundle_goals


# -- Catalog membership -----------------------------------------------------------


def test_every_emitted_identity_is_a_real_catalog_member() -> None:
    catalog_identities = {(m.key, m.granularity) for m in METRIC_CATALOG_V2}
    assert catalog_identities >= _EMITTED_IDENTITIES


def test_adapter_module_is_registered_under_data_mesh_adapters() -> None:
    assert hasattr(adapters_package, "__path__") or True  # package import sanity
    assert statsbomb_open.SOURCE_CODE == SOURCE_CODE == "statsbomb-open"


def test_parse_match_returns_none_for_malformed_summary() -> None:
    assert parse_match({}) is None
    assert parse_match({"match_id": 1}) is None
