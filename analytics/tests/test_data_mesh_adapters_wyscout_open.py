from __future__ import annotations

import inspect
from datetime import datetime
from typing import Any

import pytest

from football_intelligence.data_mesh import adapters as adapters_package
from football_intelligence.data_mesh.adapters import wyscout_open
from football_intelligence.data_mesh.adapters.wyscout_open import (
    _EMITTED_IDENTITIES,
    COMPETITION_CODE,
    SEASON_LABEL,
    SOURCE_CODE,
    WyscoutObservationConflictError,
    _emit,
    parse_england_season,
    parse_goalkeeper_observations,
    parse_match_observations,
    parse_participation_observations,
    parse_player_match_observations,
    parse_team_match_observations,
)
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2
from football_intelligence.providers.wyscout_open_mapping import adapter_safe_mappings

# Payload shapes mirror the real, verified Wyscout Open ENG_PL 2017/18
# schema (Block 20B.1/20B.2a): teamsData[*].{side,score,formation}, flat
# events with eventName/subEventName/tags/positions, players.json role.code2.

_PLAYERS_PAYLOAD = [
    {"wyId": 11, "role": {"code2": "GK"}},
    {"wyId": 12, "role": {"code2": "DF"}},
    {"wyId": 13, "role": {"code2": "FW"}},
    {"wyId": 14, "role": {"code2": "MD"}},
    {"wyId": 15, "role": {"code2": "MD"}},
    {"wyId": 21, "role": {"code2": "DF"}},
    {"wyId": 22, "role": {"code2": "GK"}},
    {"wyId": 23, "role": {"code2": "FW"}},
    {"wyId": 31, "role": {"code2": "FW"}},
]

_MATCH_1 = {
    "wyId": 1001,
    "dateutc": "2018-01-01 15:00:00",
    "status": "Played",
    "gameweek": 1,
    "venue": "Test Arena",
    "teamsData": {
        "100": {
            "side": "home",
            "score": 2,
            "formation": {
                "lineup": [{"playerId": 11}, {"playerId": 12}, {"playerId": 13}],
                "bench": [{"playerId": 14}, {"playerId": 15}],
                "substitutions": [{"playerIn": 15, "playerOut": 12, "minute": 60}],
            },
        },
        "200": {
            "side": "away",
            "score": 1,
            "formation": {
                "lineup": [{"playerId": 21}, {"playerId": 22}],
                "bench": [{"playerId": 23}],
                # Verified real quirk: zero substitutions can be encoded as
                # the literal string "null" instead of an empty list.
                "substitutions": "null",
            },
        },
    },
}

_EVENTS_1 = [
    # Team A (13) scores twice.
    {
        "matchId": 1001,
        "eventName": "Shot",
        "subEventName": "Shot",
        "playerId": 13,
        "teamId": 100,
        "tags": [{"id": 101}, {"id": 1801}, {"id": 402}],
    },
    {
        "matchId": 1001,
        "eventName": "Shot",
        "subEventName": "Shot",
        "playerId": 13,
        "teamId": 100,
        "tags": [{"id": 101}, {"id": 1801}, {"id": 403}],
    },
    # Team B (21) scores once.
    {
        "matchId": 1001,
        "eventName": "Shot",
        "subEventName": "Shot",
        "playerId": 21,
        "teamId": 200,
        "tags": [{"id": 101}, {"id": 1801}],
    },
    # A completed pass by 12 (subbed off later), with an assist tag.
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 12,
        "teamId": 100,
        "tags": [{"id": 1801}, {"id": 301}],
    },
    # The substitute (15) touches the ball after coming on.
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 15,
        "teamId": 100,
        "tags": [{"id": 1801}],
    },
    # Team A's keeper (11) makes a genuine save.
    {
        "matchId": 1001,
        "eventName": "Save attempt",
        "subEventName": "Save attempt",
        "playerId": 11,
        "teamId": 100,
        "tags": [{"id": 1801}],
    },
    # Team B's keeper (22) concedes both of Team A's goals via failed saves.
    {
        "matchId": 1001,
        "eventName": "Save attempt",
        "subEventName": "Save attempt",
        "playerId": 22,
        "teamId": 200,
        "tags": [{"id": 101}, {"id": 1802}],
    },
    {
        "matchId": 1001,
        "eventName": "Save attempt",
        "subEventName": "Save attempt",
        "playerId": 22,
        "teamId": 200,
        "tags": [{"id": 101}, {"id": 1802}],
    },
    # A duel between the two forwards.
    {
        "matchId": 1001,
        "eventName": "Duel",
        "subEventName": "Air duel",
        "playerId": 13,
        "teamId": 100,
        "tags": [{"id": 703}],
    },
    # A corner for team A (team-level fact, no playerId semantics needed).
    {
        "matchId": 1001,
        "eventName": "Free Kick",
        "subEventName": "Corner",
        "playerId": 12,
        "teamId": 100,
        "tags": [],
    },
    # Sentinel playerId 0 must never be treated as a real player.
    {
        "matchId": 1001,
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 0,
        "teamId": 100,
        "tags": [{"id": 1801}],
    },
]

# Match 2 reproduces the real, verified source-quality exception (Block
# 20B.2a: match wyId 2499781): a goal exists in the native scoreline with
# NO corresponding shot-type event for the scoring team -- only the
# conceding goalkeeper's failed Save attempt carries the Goal tag.
_MATCH_2 = {
    "wyId": 1002,
    "dateutc": "2018-01-08 15:00:00",
    "status": "Played",
    "gameweek": 2,
    "venue": "Test Arena 2",
    "teamsData": {
        "100": {
            "side": "home",
            "score": 0,
            "formation": {"lineup": [{"playerId": 11}], "bench": [], "substitutions": []},
        },
        "300": {
            "side": "away",
            "score": 1,
            "formation": {"lineup": [{"playerId": 31}], "bench": [], "substitutions": []},
        },
    },
}

_EVENTS_2 = [
    {
        "matchId": 1002,
        "eventName": "Save attempt",
        "subEventName": "Save attempt",
        "playerId": 11,
        "teamId": 100,
        "tags": [{"id": 101}, {"id": 1802}],
    },
]

_MATCHES_PAYLOAD = [_MATCH_1, _MATCH_2]
_EVENTS_PAYLOAD = _EVENTS_1 + _EVENTS_2

_CATALOG_KEYS = {metric.key for metric in METRIC_CATALOG_V2}
_SAFE_IDENTITIES = {(m.catalog_key, m.catalog_granularity) for m in adapter_safe_mappings()}


def _find(observations, entity_type, entity_source_id, metric_name):
    matches = [
        o
        for o in observations
        if o.entity_type == entity_type
        and o.entity_source_id == entity_source_id
        and o.metric_name == metric_name
    ]
    assert len(matches) == 1, (
        f"expected exactly one ({entity_type}, {entity_source_id}, {metric_name}), "
        f"found {len(matches)}"
    )
    return matches[0]


def _find_all(observations, entity_type, entity_source_id, metric_name):
    return [
        o
        for o in observations
        if o.entity_type == entity_type
        and o.entity_source_id == entity_source_id
        and o.metric_name == metric_name
    ]


# -- A. Direct match observations --------------------------------------------


def test_direct_match_observations() -> None:
    observations = parse_match_observations(_MATCHES_PAYLOAD)

    match_obs = {o.metric_name: o.value for o in observations if o.entity_source_id == "1001"}
    assert match_obs["home_score"] == 2
    assert match_obs["away_score"] == 1
    assert match_obs["status"] == "Played"
    assert match_obs["kickoff_at"] == "2018-01-01T15:00:00+00:00"
    assert match_obs["round_name"] == "1"
    assert match_obs["venue_name"] == "Test Arena"

    for obs in observations:
        assert obs.source_code == SOURCE_CODE
        assert obs.entity_identity_hints["competition_external_id"] == COMPETITION_CODE
        assert obs.entity_identity_hints["season_label"] == SEASON_LABEL

    home_away = {o.entity_source_id: o.value for o in observations if o.metric_name == "home_away"}
    assert home_away["1001:100"] == "home"
    assert home_away["1001:200"] == "away"


# -- B. Player event aggregation ----------------------------------------------


def test_player_event_aggregation() -> None:
    observations = parse_player_match_observations(_MATCHES_PAYLOAD, _EVENTS_PAYLOAD)

    assert _find(observations, "player", "1001:13", "goals").value == 2
    assert _find(observations, "player", "1001:13", "shots_total").value == 2
    assert _find(observations, "player", "1001:13", "shots_on_target").value == 2
    assert _find(observations, "player", "1001:13", "headed_shots").value == 1
    assert _find(observations, "player", "1001:13", "aerial_duels").value == 1
    assert _find(observations, "player", "1001:13", "aerial_duels_won").value == 1
    assert _find(observations, "player", "1001:13", "aerial_duel_win_pct").value == 100.0

    assert _find(observations, "player", "1001:21", "goals").value == 1

    assert _find(observations, "player", "1001:12", "passes_total").value == 1
    assert _find(observations, "player", "1001:12", "passes_accurate").value == 1
    assert _find(observations, "player", "1001:12", "assists").value == 1
    assert _find(observations, "player", "1001:12", "pass_completion_pct").value == 100.0

    # A player with zero shots gets no shots_on_target_pct (undefined ratio,
    # never a fabricated 0%/None).
    assert _find_all(observations, "player", "1001:12", "shots_on_target_pct") == []


def test_sentinel_player_id_0_never_produces_an_observation() -> None:
    observations = parse_player_match_observations(_MATCHES_PAYLOAD, _EVENTS_PAYLOAD)
    assert all(not o.entity_source_id.endswith(":0") for o in observations)
    assert all(o.entity_source_id != "0" for o in observations)


# -- C. Team / opponent aggregation -------------------------------------------


def test_team_and_opponent_aggregation() -> None:
    observations = parse_team_match_observations(
        _MATCHES_PAYLOAD, _EVENTS_PAYLOAD, _PLAYERS_PAYLOAD
    )

    assert _find(observations, "team", "1001:100", "goals_for").value == 2
    assert _find(observations, "team", "1001:100", "goals_against").value == 1
    assert _find(observations, "team", "1001:200", "goals_for").value == 1
    assert _find(observations, "team", "1001:200", "goals_against").value == 2

    assert _find(observations, "team", "1001:100", "shots_total").value == 2
    assert _find(observations, "team", "1001:200", "shots_total").value == 1
    # Team A's shots_allowed must equal team B's own shots_total (opponent
    # cross-reference within the same match).
    assert _find(observations, "team", "1001:100", "shots_allowed").value == 1
    assert _find(observations, "team", "1001:200", "shots_allowed").value == 2

    assert _find(observations, "team", "1001:100", "corners").value == 1
    assert _find(observations, "team", "1001:200", "corners").value == 0

    # goalkeeper_saves sums the team's GK-role player(s) saves for the match.
    assert _find(observations, "team", "1001:100", "goalkeeper_saves").value == 1
    assert _find(observations, "team", "1001:200", "goalkeeper_saves").value == 0


# -- D/E. starts / sub_appearances / appearances, unused bench excluded ------


def test_participation_starts_appearances_and_sub_appearances() -> None:
    observations = parse_participation_observations(_MATCHES_PAYLOAD)

    started = {o.entity_source_id: o.value for o in observations if o.metric_name == "started"}
    assert started["1001:11"] is True
    assert started["1001:12"] is True
    assert started["1001:14"] is False  # unused bench
    assert started["1001:15"] is False  # bench, but later subbed in

    season = {(o.entity_source_id, o.metric_name): o.value for o in observations}
    # Player 12 started and was subbed off: 1 match, 1 start, 1 appearance, 0 sub_appearances.
    assert season[("12", "matches")] == 1
    assert season[("12", "starts")] == 1
    assert season[("12", "appearances")] == 1
    assert season[("12", "sub_appearances")] == 0
    # Player 15 came on as a substitute: appearance but not a start.
    assert season[("15", "starts")] == 0
    assert season[("15", "appearances")] == 1
    assert season[("15", "sub_appearances")] == 1
    # Player 14 was an unused bench player: counted in the squad ("matches")
    # but never an appearance.
    assert season[("14", "matches")] == 1
    assert season[("14", "appearances")] == 0
    assert season[("14", "sub_appearances")] == 0


def test_unused_bench_player_receives_no_player_match_performance_observation() -> None:
    observations = parse_player_match_observations(_MATCHES_PAYLOAD, _EVENTS_PAYLOAD)
    assert _find_all(observations, "player", "1001:14", "touches") == []
    assert _find_all(observations, "player", "1001:14", "goals") == []


# -- F. Substitutions literal "null" ------------------------------------------


def test_substitutions_literal_null_is_treated_as_no_substitutions() -> None:
    # Team 200's substitutions field is the literal string "null" (real
    # source quirk) -- this must not raise and must not fabricate a
    # substitute appearance for team 200's bench player (23).
    observations = parse_participation_observations(_MATCHES_PAYLOAD)
    season = {(o.entity_source_id, o.metric_name): o.value for o in observations}
    assert season[("23", "appearances")] == 0
    assert season[("23", "matches")] == 1


# -- H/I/J. Goal reconciliation -----------------------------------------------


def test_player_goal_attribution_from_event_tags() -> None:
    observations = parse_player_match_observations(_MATCHES_PAYLOAD, _EVENTS_PAYLOAD)
    assert _find(observations, "player", "1001:13", "goals").value == 2
    assert _find(observations, "player", "1001:21", "goals").value == 1


def test_native_team_score_authoritative_over_event_derived_reconstruction() -> None:
    team_observations = parse_team_match_observations(
        _MATCHES_PAYLOAD, _EVENTS_PAYLOAD, _PLAYERS_PAYLOAD
    )
    # Match 2: native score says team 300 scored 1, even though the event
    # stream contains no shot-type event for team 300 at all (only the
    # conceding keeper's failed Save attempt) -- goals_for must come from
    # teamsData[*].score, never from summing shot/goal-tagged events.
    assert _find(team_observations, "team", "1002:300", "goals_for").value == 1
    assert _find(team_observations, "team", "1002:100", "goals_against").value == 1

    player_observations = parse_player_match_observations(_MATCHES_PAYLOAD, _EVENTS_PAYLOAD)
    # No player was ever tagged with this goal -- team 300's only
    # participant (31) gets a real, zero-filled `goals=0`, never a
    # fabricated 1.
    assert _find(player_observations, "player", "1002:31", "goals").value == 0


def test_missing_scorer_never_causes_invented_attribution() -> None:
    player_observations = parse_player_match_observations(_MATCHES_PAYLOAD, _EVENTS_PAYLOAD)
    scorers_in_match_2 = [
        o
        for o in player_observations
        if o.entity_source_id.startswith("1002:") and o.metric_name == "goals" and o.value > 0
    ]
    assert scorers_in_match_2 == []


# -- K. Goalkeeper identification from players.json role.code2 == "GK" ------


def test_goalkeeper_metrics_are_scoped_by_players_json_role() -> None:
    observations = parse_goalkeeper_observations(
        _MATCHES_PAYLOAD, _EVENTS_PAYLOAD, _PLAYERS_PAYLOAD
    )
    # goalkeeper_match-exclusive identities are only emitted for players
    # confirmed as GK by players.json role.code2 (11, 22) -- never for
    # outfield players (12, 13, 21), even if they were somehow tagged on a
    # save-type event.
    assert _find(observations, "player", "1001:22", "goals_conceded").value == 2
    assert _find(observations, "player", "1001:22", "clean_sheets").value is False
    # Team A (11's team) conceded 1 goal (team B's player 21 scored) -- not
    # a clean sheet either.
    assert _find(observations, "player", "1001:11", "goals_conceded").value == 1
    assert _find(observations, "player", "1001:11", "clean_sheets").value is False
    assert _find_all(observations, "player", "1001:13", "goals_conceded") == []
    assert _find_all(observations, "player", "1001:21", "goals_conceded") == []


def test_saves_is_a_general_player_match_metric_not_goalkeeper_exclusive() -> None:
    # `saves` (player_match) is zero-filled for every confirmed-participating
    # player, matching the existing StatsBomb Open Data adapter's
    # `_COUNT_METRIC_NAMES` precedent -- it is not restricted to confirmed
    # goalkeepers at this granularity (an outfield player genuinely has 0
    # saves, a real zero, not "not applicable").
    observations = parse_player_match_observations(_MATCHES_PAYLOAD, _EVENTS_PAYLOAD)
    assert _find(observations, "player", "1001:11", "saves").value == 1
    assert _find(observations, "player", "1001:21", "saves").value == 0


def test_goalkeeper_identity_never_inferred_from_shirt_number_or_event_type() -> None:
    # Passing an empty players_payload means no player is ever recognized as
    # a goalkeeper -- proving identity comes exclusively from
    # players.json role.code2, never from any in-match signal (e.g. having
    # made a save).
    observations = parse_goalkeeper_observations(_MATCHES_PAYLOAD, _EVENTS_PAYLOAD, [])
    assert observations == []


# -- L. Zero vs missing -------------------------------------------------------


def test_zero_is_only_emitted_for_a_confirmed_participating_player() -> None:
    observations = parse_player_match_observations(_MATCHES_PAYLOAD, _EVENTS_PAYLOAD)
    # Player 14 never participated (unused bench) -- no observation at all,
    # not a fabricated zero.
    assert _find_all(observations, "player", "1001:14", "shots_total") == []
    # Player 21 participated but took no shots -- a real, legitimate zero.
    assert _find(observations, "player", "1001:21", "shots_off_target").value == 0


# -- M/N. Emission scope -------------------------------------------------------


def test_emitted_identities_are_a_subset_of_adapter_safe_mappings() -> None:
    assert _EMITTED_IDENTITIES <= _SAFE_IDENTITIES


@pytest.mark.parametrize(
    ("metric_name", "entity_type"),
    [
        ("advanced.xg", "player"),  # REQUIRES_MODEL
        ("tackles", "player"),  # AMBIGUOUS
        ("progressive_passes", "player"),  # DERIVABLE_METHODOLOGY_PENDING
        ("carries", "player"),  # UNSUPPORTED
        ("league_strength", "competition"),  # provider-out-of-scope
    ],
)
def test_non_safe_identities_can_never_be_emitted(metric_name: str, entity_type: str) -> None:
    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, str, str, str], Any] = {}
    with pytest.raises(WyscoutObservationConflictError):
        _emit(
            observations,
            seen,
            entity_type=entity_type,  # type: ignore[arg-type]
            entity_source_id="1",
            entity_identity_hints={},
            metric_name=metric_name,
            value=1,
            observed_at=datetime(2018, 1, 1),
            source_reference="test",
            ingestion_run_id=None,
        )
    assert observations == []


def test_full_adapter_run_emits_nothing_outside_the_safe_scope() -> None:
    observations = parse_england_season(
        matches_payload=_MATCHES_PAYLOAD,
        events_payload=_EVENTS_PAYLOAD,
        players_payload=_PLAYERS_PAYLOAD,
    )
    for obs in observations:
        # Every observation's (metric_name, entity_type) must correspond to
        # a real adapter-safe catalog identity.
        assert obs.metric_name in {key for key, _ in _EMITTED_IDENTITIES}


# -- O. Determinism ------------------------------------------------------------


def test_deterministic_output_across_repeated_runs() -> None:
    first = parse_england_season(
        matches_payload=_MATCHES_PAYLOAD,
        events_payload=_EVENTS_PAYLOAD,
        players_payload=_PLAYERS_PAYLOAD,
    )
    second = parse_england_season(
        matches_payload=_MATCHES_PAYLOAD,
        events_payload=_EVENTS_PAYLOAD,
        players_payload=_PLAYERS_PAYLOAD,
    )
    key = lambda obs: (obs.entity_type, obs.entity_source_id, obs.metric_name, obs.value)  # noqa: E731
    assert sorted(map(key, first)) == sorted(map(key, second))


# -- P. Duplicate / conflict detection ----------------------------------------


def test_identical_duplicate_observation_is_silently_deduplicated() -> None:
    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, str, str, str], Any] = {}
    kwargs: dict[str, Any] = dict(
        entity_type="player",
        entity_source_id="1",
        entity_identity_hints={},
        metric_name="goals",
        value=1,
        observed_at=datetime(2018, 1, 1),
        source_reference="test",
        ingestion_run_id=None,
    )
    _emit(observations, seen, **kwargs)
    _emit(observations, seen, **kwargs)
    assert len(observations) == 1


def test_conflicting_duplicate_observation_raises() -> None:
    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, str, str, str], Any] = {}
    base: dict[str, Any] = dict(
        entity_type="player",
        entity_source_id="1",
        entity_identity_hints={},
        metric_name="goals",
        observed_at=datetime(2018, 1, 1),
        source_reference="test",
        ingestion_run_id=None,
    )
    _emit(observations, seen, value=1, **base)
    with pytest.raises(WyscoutObservationConflictError):
        _emit(observations, seen, value=2, **base)


# -- Q. Emitted metric names exist in Metric Catalog V2 -----------------------


def test_every_emitted_metric_name_exists_in_metric_catalog_v2() -> None:
    observations = parse_england_season(
        matches_payload=_MATCHES_PAYLOAD,
        events_payload=_EVENTS_PAYLOAD,
        players_payload=_PLAYERS_PAYLOAD,
    )
    for obs in observations:
        assert obs.metric_name in _CATALOG_KEYS


# -- R. No DB / network dependency --------------------------------------------


def test_adapter_module_has_no_database_or_network_dependency() -> None:
    source = inspect.getsource(wyscout_open)
    assert "DATABASE_URL" not in source
    assert "psycopg" not in source
    assert "football_intelligence.db" not in source
    assert "urlopen" not in source
    assert "import requests" not in source
    assert "WyscoutOpenDataClient(" not in source


def test_adapter_module_lives_under_data_mesh_adapters() -> None:
    assert wyscout_open.__name__.startswith(adapters_package.__name__)
