from __future__ import annotations

from datetime import datetime

import pytest

from football_intelligence.data_mesh.entity_resolution_v2 import (
    IdentityConflictError,
    PlayerCrosswalk,
    PlayerCrosswalkConflictError,
    PlayerCrosswalkEntry,
    PlayerCrosswalkValidationError,
    build_match_index_v2,
    build_match_index_v2_from_observations,
    build_team_index_v2,
    build_team_index_v2_from_observations,
    logical_fact_key,
    resolve_match_v2,
    resolve_player_v2,
    resolve_team_v2,
)
from football_intelligence.data_mesh.models import NormalizedObservation

# ---------------------------------------------------------------------------
# logical_fact_key
# ---------------------------------------------------------------------------


def test_competition_key_only_needs_competition_code() -> None:
    assert logical_fact_key(metric_granularity="competition", competition_code="ENG_PL") == (
        "competition:ENG_PL"
    )


def test_team_key_passes_through_team_key() -> None:
    assert (
        logical_fact_key(
            metric_granularity="team", competition_code="ENG_PL", team_key="team:ENG_PL:arsenal"
        )
        == "team:ENG_PL:arsenal"
    )


def test_match_key_passes_through_match_key() -> None:
    assert (
        logical_fact_key(metric_granularity="match", competition_code="ENG_PL", match_key="match:1")
        == "match:1"
    )


def test_team_match_key_requires_both_match_and_team() -> None:
    assert (
        logical_fact_key(
            metric_granularity="team_match",
            competition_code="ENG_PL",
            match_key="match:1",
            team_key="team:ENG_PL:arsenal",
        )
        == "team-match:match:1:team:ENG_PL:arsenal"
    )
    assert (
        logical_fact_key(
            metric_granularity="team_match", competition_code="ENG_PL", match_key="match:1"
        )
        is None
    )


def test_home_away_the_two_teams_in_one_match_get_different_logical_fact_keys() -> None:
    # Block 20D.2 review-fix pass regression: `home_away` is catalog
    # granularity "team_match" (corrected from the earlier, wrong "match"
    # classification), so the home team's and away team's `home_away` facts
    # -- genuinely different facts about the same real match -- must never
    # collapse onto one bare match-level logical key.
    home_key = logical_fact_key(
        metric_granularity="team_match",
        competition_code="ENG_PL",
        match_key="match:1",
        team_key="team:ENG_PL:arsenal",
    )
    away_key = logical_fact_key(
        metric_granularity="team_match",
        competition_code="ENG_PL",
        match_key="match:1",
        team_key="team:ENG_PL:chelsea",
    )
    assert home_key != away_key
    assert home_key == "team-match:match:1:team:ENG_PL:arsenal"
    assert away_key == "team-match:match:1:team:ENG_PL:chelsea"


def test_player_match_key_scopes_to_the_specific_match() -> None:
    key_match_1 = logical_fact_key(
        metric_granularity="player_match",
        competition_code="ENG_PL",
        match_key="match:1",
        player_key="player:kane",
    )
    key_match_2 = logical_fact_key(
        metric_granularity="player_match",
        competition_code="ENG_PL",
        match_key="match:2",
        player_key="player:kane",
    )
    assert key_match_1 != key_match_2


def test_player_season_key_scopes_to_the_season_not_a_single_match() -> None:
    key_season_1 = logical_fact_key(
        metric_granularity="player_season",
        competition_code="ENG_PL",
        season_label="2015/2016",
        player_key="player:kane",
    )
    key_season_2 = logical_fact_key(
        metric_granularity="player_season",
        competition_code="ENG_PL",
        season_label="2017/2018",
        player_key="player:kane",
    )
    assert key_season_1 != key_season_2
    assert (
        logical_fact_key(
            metric_granularity="player_season", competition_code="ENG_PL", player_key="player:kane"
        )
        is None
    )


def test_player_match_and_goalkeeper_match_never_share_a_fact_key() -> None:
    player_match_key = logical_fact_key(
        metric_granularity="player_match",
        competition_code="ENG_PL",
        match_key="match:1",
        player_key="player:keeper",
    )
    goalkeeper_match_key = logical_fact_key(
        metric_granularity="goalkeeper_match",
        competition_code="ENG_PL",
        match_key="match:1",
        player_key="player:keeper",
    )
    assert player_match_key != goalkeeper_match_key


def test_player_appearance_key_differs_from_player_match_key() -> None:
    appearance_key = logical_fact_key(
        metric_granularity="player_appearance",
        competition_code="ENG_PL",
        match_key="match:1",
        player_key="player:kane",
    )
    match_key = logical_fact_key(
        metric_granularity="player_match",
        competition_code="ENG_PL",
        match_key="match:1",
        player_key="player:kane",
    )
    assert appearance_key != match_key


def test_team_match_never_collapses_into_bare_team_key() -> None:
    team_match_key = logical_fact_key(
        metric_granularity="team_match",
        competition_code="ENG_PL",
        match_key="match:1",
        team_key="team:ENG_PL:arsenal",
    )
    team_key = logical_fact_key(
        metric_granularity="team", competition_code="ENG_PL", team_key="team:ENG_PL:arsenal"
    )
    assert team_match_key != team_key


def test_goalkeeper_season_key_requires_season_and_player() -> None:
    assert (
        logical_fact_key(metric_granularity="goalkeeper_season", competition_code="ENG_PL") is None
    )
    assert (
        logical_fact_key(
            metric_granularity="goalkeeper_season",
            competition_code="ENG_PL",
            season_label="2015/2016",
            player_key="player:keeper",
        )
        == "goalkeeper-season:ENG_PL:2015/2016:player:keeper"
    )


# ---------------------------------------------------------------------------
# logical_fact_key: blank (not just missing) required context (Block 20D.2
# review-fix pass)
# ---------------------------------------------------------------------------


def test_competition_key_rejects_a_blank_competition_code() -> None:
    assert logical_fact_key(metric_granularity="competition", competition_code="   ") is None
    assert logical_fact_key(metric_granularity="competition", competition_code="") is None


def test_team_key_rejects_a_blank_team_key() -> None:
    assert (
        logical_fact_key(metric_granularity="team", competition_code="ENG_PL", team_key="") is None
    )
    assert (
        logical_fact_key(metric_granularity="team", competition_code="ENG_PL", team_key="   ")
        is None
    )


def test_match_key_rejects_a_blank_match_key() -> None:
    assert (
        logical_fact_key(metric_granularity="match", competition_code="ENG_PL", match_key="")
        is None
    )


def test_team_match_key_rejects_a_blank_match_or_team_key() -> None:
    assert (
        logical_fact_key(
            metric_granularity="team_match",
            competition_code="ENG_PL",
            match_key="",
            team_key="team:ENG_PL:arsenal",
        )
        is None
    )
    assert (
        logical_fact_key(
            metric_granularity="team_match",
            competition_code="ENG_PL",
            match_key="match:1",
            team_key="   ",
        )
        is None
    )


def test_player_match_key_rejects_a_blank_player_key() -> None:
    assert (
        logical_fact_key(
            metric_granularity="player_match",
            competition_code="ENG_PL",
            match_key="match:1",
            player_key="",
        )
        is None
    )


def test_player_season_key_rejects_a_blank_season_label() -> None:
    assert (
        logical_fact_key(
            metric_granularity="player_season",
            competition_code="ENG_PL",
            season_label="   ",
            player_key="player:kane",
        )
        is None
    )


def test_goalkeeper_season_key_rejects_a_blank_competition_code() -> None:
    assert (
        logical_fact_key(
            metric_granularity="goalkeeper_season",
            competition_code="   ",
            season_label="2015/2016",
            player_key="player:keeper",
        )
        is None
    )


# ---------------------------------------------------------------------------
# V2 team/match source-local index
# ---------------------------------------------------------------------------


def test_build_team_index_v2_resolves_from_provider_id_to_name_evidence() -> None:
    index = build_team_index_v2(
        source_code="wyscout-open",
        competition_code="ENG_PL",
        team_names_by_provider_id={"1609": "Arsenal", "1611": "Chelsea"},
    )
    resolution = resolve_team_v2(
        source_code="wyscout-open", provider_team_id="1609", team_index=index
    )
    assert resolution.status == "resolved"
    assert resolution.logical_key == "team:ENG_PL:arsenal"


def test_resolve_team_v2_unresolved_without_an_index_entry() -> None:
    resolution = resolve_team_v2(source_code="wyscout-open", provider_team_id="9999", team_index={})
    assert resolution.status == "unresolved"
    assert resolution.logical_key is None


def test_two_different_source_providers_converge_on_the_same_team_index_entity() -> None:
    wyscout_index = build_team_index_v2(
        source_code="wyscout-open",
        competition_code="ESP_LL",
        team_names_by_provider_id={"695": "Atlético Madrid"},
    )
    statsbomb_index = build_team_index_v2(
        source_code="statsbomb-open",
        competition_code="ESP_LL",
        team_names_by_provider_id={"559": "Atletico Madrid"},
    )
    wyscout_resolution = resolve_team_v2(
        source_code="wyscout-open", provider_team_id="695", team_index=wyscout_index
    )
    statsbomb_resolution = resolve_team_v2(
        source_code="statsbomb-open", provider_team_id="559", team_index=statsbomb_index
    )
    assert wyscout_resolution.logical_key == statsbomb_resolution.logical_key


def test_build_team_index_v2_raises_when_a_later_batch_contradicts_an_earlier_one() -> None:
    # Same provider team id, two different names across two evidence
    # batches accumulated into one shared index -- a real data-quality
    # conflict that must never be silently resolved one way or the other.
    index = build_team_index_v2(
        source_code="wyscout-open",
        competition_code="ENG_PL",
        team_names_by_provider_id={"1609": "Arsenal"},
    )
    with pytest.raises(IdentityConflictError):
        build_team_index_v2(
            source_code="wyscout-open",
            competition_code="ENG_PL",
            team_names_by_provider_id={"1609": "Chelsea"},
            into=index,
        )


def test_build_team_index_v2_repeating_the_same_evidence_is_not_a_conflict() -> None:
    index = build_team_index_v2(
        source_code="wyscout-open",
        competition_code="ENG_PL",
        team_names_by_provider_id={"1609": "Arsenal"},
    )
    # Re-observing the same (provider id -> name) evidence in a later batch
    # (e.g. the same team appearing in a second match file) must not raise.
    index = build_team_index_v2(
        source_code="wyscout-open",
        competition_code="ENG_PL",
        team_names_by_provider_id={"1609": "Arsenal"},
        into=index,
    )
    assert index[("wyscout-open", "1609")] == "team:ENG_PL:arsenal"


def test_build_match_index_v2_raises_when_a_later_batch_contradicts_an_earlier_one() -> None:
    index = build_match_index_v2(
        source_code="wyscout-open",
        match_keys_by_provider_id={"2500089": "match:a"},
    )
    with pytest.raises(IdentityConflictError):
        build_match_index_v2(
            source_code="wyscout-open",
            match_keys_by_provider_id={"2500089": "match:b"},
            into=index,
        )


# ---------------------------------------------------------------------------
# Observation-driven V2 index (Block 20D.2 completion pass) -- built purely
# from entity_identity_hints, never from entity_source_id's composite shape.
# ---------------------------------------------------------------------------


def _match_obs(
    *,
    source_code: str = "wyscout-open",
    entity_type: str = "match",
    entity_source_id: str = "5001",
    hints: dict,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=source_code,
        source_type="objective_structured",
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_source_id=entity_source_id,
        entity_identity_hints=hints,
        metric_name="status",
        value="Played",
        observed_at=datetime(2018, 1, 1),
        source_timestamp=None,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version="test-v1",
    )


def test_build_team_index_v2_from_observations_reads_only_hints() -> None:
    # A team-scoped observation whose entity_source_id has no parseable
    # relationship to the provider team id at all -- proving resolution
    # comes purely from entity_identity_hints, never entity_source_id.
    obs = _match_obs(
        entity_type="team",
        entity_source_id="opaque-uuid-not-an-id-pair",
        hints={"team_external_id": "1609", "team_name": "Arsenal", "match_external_id": "5001"},
    )
    index = build_team_index_v2_from_observations([obs], competition_code="ENG_PL")
    resolution = resolve_team_v2(
        source_code="wyscout-open", provider_team_id="1609", team_index=index
    )
    assert resolution.status == "resolved"
    assert resolution.logical_key == "team:ENG_PL:arsenal"


def test_build_team_index_v2_from_observations_reads_home_away_match_hints() -> None:
    obs = _match_obs(
        hints={
            "match_external_id": "5001",
            "home_team_external_id": "1609",
            "home_team_name": "Arsenal",
            "away_team_external_id": "1611",
            "away_team_name": "Chelsea",
            "season_label": "2017/18",
            "kickoff_date": "2018-01-01",
        }
    )
    index = build_team_index_v2_from_observations([obs], competition_code="ENG_PL")
    home = resolve_team_v2(source_code="wyscout-open", provider_team_id="1609", team_index=index)
    away = resolve_team_v2(source_code="wyscout-open", provider_team_id="1611", team_index=index)
    assert home.logical_key == "team:ENG_PL:arsenal"
    assert away.logical_key == "team:ENG_PL:chelsea"


def test_build_team_index_v2_from_observations_raises_on_a_genuine_conflict() -> None:
    first = _match_obs(
        entity_type="team",
        entity_source_id="a",
        hints={"team_external_id": "1609", "team_name": "Arsenal"},
    )
    second = _match_obs(
        entity_type="team",
        entity_source_id="b",
        hints={"team_external_id": "1609", "team_name": "Chelsea"},
    )
    with pytest.raises(IdentityConflictError):
        build_team_index_v2_from_observations([first, second], competition_code="ENG_PL")


def test_build_match_index_v2_from_observations_resolves_using_hints_only() -> None:
    obs = _match_obs(
        entity_source_id="opaque-uuid-not-the-match-id",
        hints={
            "match_external_id": "5001",
            "home_team_external_id": "1609",
            "home_team_name": "Arsenal",
            "away_team_external_id": "1611",
            "away_team_name": "Chelsea",
            "season_label": "2017/18",
            "kickoff_date": "2018-01-01",
        },
    )
    team_index = build_team_index_v2_from_observations([obs], competition_code="ENG_PL")
    match_index = build_match_index_v2_from_observations(
        [obs], competition_code="ENG_PL", team_index=team_index
    )
    resolution = resolve_match_v2(
        source_code="wyscout-open", provider_match_id="5001", match_index=match_index
    )
    assert resolution.status == "resolved"
    assert resolution.logical_key is not None
    assert resolution.logical_key.startswith("match:ENG_PL:2017/18:")


def test_build_match_index_v2_from_observations_falls_back_to_direct_name_resolution() -> None:
    # No pre-built team_index entry at all -- the match hints' own
    # home_team_name/away_team_name must still be enough to resolve.
    obs = _match_obs(
        hints={
            "match_external_id": "5001",
            "home_team_external_id": "1609",
            "home_team_name": "Arsenal",
            "away_team_external_id": "1611",
            "away_team_name": "Chelsea",
            "season_label": "2017/18",
            "kickoff_date": "2018-01-01",
        }
    )
    match_index = build_match_index_v2_from_observations(
        [obs], competition_code="ENG_PL", team_index={}
    )
    resolution = resolve_match_v2(
        source_code="wyscout-open", provider_match_id="5001", match_index=match_index
    )
    assert resolution.status == "resolved"


def test_build_match_index_v2_from_observations_blank_season_label_stays_unresolved() -> None:
    # Block 20D.2 review-fix pass regression: a blank (not merely missing)
    # season_label must never produce an apparently "resolved" match key
    # like "match:ENG_PL::team:...:...".
    obs = _match_obs(
        hints={
            "match_external_id": "5001",
            "home_team_external_id": "1609",
            "home_team_name": "Arsenal",
            "away_team_external_id": "1611",
            "away_team_name": "Chelsea",
            "season_label": "   ",
            "kickoff_date": "2018-01-01",
        }
    )
    match_index = build_match_index_v2_from_observations(
        [obs], competition_code="ENG_PL", team_index={}
    )
    assert match_index == {}
    resolution = resolve_match_v2(
        source_code="wyscout-open", provider_match_id="5001", match_index=match_index
    )
    assert resolution.status == "unresolved"


def test_build_match_index_v2_from_observations_missing_season_label_stays_unresolved() -> None:
    obs = _match_obs(
        hints={
            "match_external_id": "5001",
            "home_team_external_id": "1609",
            "home_team_name": "Arsenal",
            "away_team_external_id": "1611",
            "away_team_name": "Chelsea",
            "kickoff_date": "2018-01-01",
        }
    )
    match_index = build_match_index_v2_from_observations(
        [obs], competition_code="ENG_PL", team_index={}
    )
    assert match_index == {}


def test_build_match_index_v2_from_observations_missing_kickoff_date_stays_unresolved() -> None:
    obs = _match_obs(
        hints={
            "match_external_id": "5001",
            "home_team_external_id": "1609",
            "home_team_name": "Arsenal",
            "away_team_external_id": "1611",
            "away_team_name": "Chelsea",
            "season_label": "2017/18",
        }
    )
    match_index = build_match_index_v2_from_observations(
        [obs], competition_code="ENG_PL", team_index={}
    )
    assert match_index == {}


def test_build_match_index_v2_from_observations_invalid_kickoff_date_stays_unresolved() -> None:
    obs = _match_obs(
        hints={
            "match_external_id": "5001",
            "home_team_external_id": "1609",
            "home_team_name": "Arsenal",
            "away_team_external_id": "1611",
            "away_team_name": "Chelsea",
            "season_label": "2017/18",
            "kickoff_date": "not-a-real-date",
        }
    )
    match_index = build_match_index_v2_from_observations(
        [obs], competition_code="ENG_PL", team_index={}
    )
    assert match_index == {}


def test_build_match_index_v2_from_observations_missing_team_identity_stays_unresolved() -> None:
    # No home/away team ids, names, or a prebuilt team_index entry -- team
    # identity can never be resolved, so the match must stay unresolved too.
    obs = _match_obs(
        hints={
            "match_external_id": "5001",
            "season_label": "2017/18",
            "kickoff_date": "2018-01-01",
        }
    )
    match_index = build_match_index_v2_from_observations(
        [obs], competition_code="ENG_PL", team_index={}
    )
    assert match_index == {}


def test_resolve_match_v2_unresolved_without_an_index_entry() -> None:
    resolution = resolve_match_v2(
        source_code="wyscout-open", provider_match_id="9999", match_index={}
    )
    assert resolution.status == "unresolved"
    assert resolution.logical_key is None


def test_real_wyscout_adapter_output_resolves_end_to_end_via_hints_only() -> None:
    # Integration proof: feed the CERTIFIED Wyscout adapter's real output
    # (with a teams_payload supplied) straight into the V2 index builders --
    # no test-only shortcuts, no entity_source_id parsing anywhere.
    from football_intelligence.data_mesh.adapters.wyscout_open import (
        parse_match_observations,
        parse_team_match_observations,
    )

    matches_payload = [
        {
            "wyId": 5001,
            "competitionId": 364,
            "seasonId": 181150,
            "dateutc": "2018-01-01 15:00:00",
            "status": "Played",
            "gameweek": 1,
            "venue": "Test Arena",
            "teamsData": {
                "1609": {"side": "home", "score": 2, "formation": {}},
                "1611": {"side": "away", "score": 1, "formation": {}},
            },
        }
    ]
    teams_payload = [
        {"wyId": 1609, "name": "Arsenal"},
        {"wyId": 1611, "name": "Chelsea"},
    ]
    match_observations = parse_match_observations(matches_payload, teams_payload)
    team_match_observations = parse_team_match_observations(matches_payload, [], [], teams_payload)
    all_observations = match_observations + team_match_observations

    team_index = build_team_index_v2_from_observations(all_observations, competition_code="ENG_PL")
    match_index = build_match_index_v2_from_observations(
        match_observations, competition_code="ENG_PL", team_index=team_index
    )

    home = resolve_team_v2(
        source_code="wyscout-open", provider_team_id="1609", team_index=team_index
    )
    away = resolve_team_v2(
        source_code="wyscout-open", provider_team_id="1611", team_index=team_index
    )
    match = resolve_match_v2(
        source_code="wyscout-open", provider_match_id="5001", match_index=match_index
    )
    assert home.logical_key == "team:ENG_PL:arsenal"
    assert away.logical_key == "team:ENG_PL:chelsea"
    assert match.status == "resolved"


# ---------------------------------------------------------------------------
# Player crosswalk contract
# ---------------------------------------------------------------------------


def test_resolve_player_v2_unresolved_without_any_crosswalk_entry() -> None:
    resolution = resolve_player_v2(
        source_code="wyscout-open", provider_player_id="123", crosswalk=PlayerCrosswalk()
    )
    assert resolution.status == "unresolved"
    assert resolution.logical_key is None


def _valid_entry(
    *,
    provider_player_id: str = "123",
    canonical_player_key: str = "player:messi",
    shared_match_keys: tuple[str, ...] = ("match:1",),
    team_context_key: str = "team:ESP_LL:barcelona",
) -> PlayerCrosswalkEntry:
    return PlayerCrosswalkEntry(
        source_code="wyscout-open",
        provider_player_id=provider_player_id,
        canonical_player_key=canonical_player_key,
        normalized_name_used="lionel messi",
        team_context_key=team_context_key,
        shared_match_keys=shared_match_keys,
    )


def test_resolve_player_v2_resolved_with_an_explicit_validated_entry() -> None:
    crosswalk = PlayerCrosswalk()
    crosswalk.add(_valid_entry())
    resolution = resolve_player_v2(
        source_code="wyscout-open", provider_player_id="123", crosswalk=crosswalk
    )
    assert resolution.status == "resolved"
    assert resolution.logical_key == "player:messi"
    assert resolution.confidence > 0.0


def test_resolve_player_v2_same_name_without_a_crosswalk_entry_stays_unresolved() -> None:
    # A matching name alone must never be enough -- only an explicit,
    # validated crosswalk entry resolves a player.
    crosswalk = PlayerCrosswalk()
    crosswalk.add(_valid_entry())
    resolution = resolve_player_v2(
        source_code="statsbomb-open", provider_player_id="999", crosswalk=crosswalk
    )
    assert resolution.status == "unresolved"


def test_player_crosswalk_rejects_a_conflicting_entry_for_the_same_provider_id() -> None:
    crosswalk = PlayerCrosswalk()
    crosswalk.add(_valid_entry())
    with pytest.raises(PlayerCrosswalkConflictError):
        crosswalk.add(_valid_entry(canonical_player_key="player:someone-else"))


def test_player_crosswalk_re_adding_a_different_entry_for_the_same_key_is_rejected() -> None:
    # Same (source_code, provider_player_id) AND same canonical_player_key,
    # but different supporting evidence (a different shared-match set) --
    # this must never silently overwrite the already-stored evidence.
    crosswalk = PlayerCrosswalk()
    crosswalk.add(_valid_entry(shared_match_keys=("match:1",)))
    with pytest.raises(PlayerCrosswalkConflictError):
        crosswalk.add(_valid_entry(shared_match_keys=("match:1", "match:2")))


def test_player_crosswalk_re_adding_the_same_entry_is_idempotent() -> None:
    crosswalk = PlayerCrosswalk()
    entry = _valid_entry()
    crosswalk.add(entry)
    crosswalk.add(entry)
    assert len(crosswalk.entries) == 1

    # An equal-but-distinct object (not the same instance) must also be
    # accepted as an idempotent no-op, not just literal object identity.
    crosswalk.add(_valid_entry())
    assert len(crosswalk.entries) == 1


def test_more_shared_match_evidence_yields_higher_confidence() -> None:
    crosswalk = PlayerCrosswalk()
    crosswalk.add(
        _valid_entry(
            provider_player_id="1",
            canonical_player_key="player:one-match",
            shared_match_keys=("match:1",),
        )
    )
    crosswalk.add(
        _valid_entry(
            provider_player_id="2",
            canonical_player_key="player:many-matches",
            shared_match_keys=("match:1", "match:2", "match:3", "match:4", "match:5"),
        )
    )
    one_match = resolve_player_v2(
        source_code="wyscout-open", provider_player_id="1", crosswalk=crosswalk
    )
    many_matches = resolve_player_v2(
        source_code="wyscout-open", provider_player_id="2", crosswalk=crosswalk
    )
    assert many_matches.confidence > one_match.confidence


# ---------------------------------------------------------------------------
# Player crosswalk validation bar (Block 20D.2 review-fix pass)
# ---------------------------------------------------------------------------


def test_zero_shared_matches_is_rejected_at_construction() -> None:
    with pytest.raises(PlayerCrosswalkValidationError):
        _valid_entry(shared_match_keys=())


def test_blank_shared_match_key_is_rejected_at_construction() -> None:
    with pytest.raises(PlayerCrosswalkValidationError):
        _valid_entry(shared_match_keys=("   ",))


def test_missing_team_context_is_rejected_at_construction() -> None:
    with pytest.raises(PlayerCrosswalkValidationError):
        _valid_entry(team_context_key="")


def test_blank_normalized_name_is_rejected_at_construction() -> None:
    with pytest.raises(PlayerCrosswalkValidationError):
        PlayerCrosswalkEntry(
            source_code="wyscout-open",
            provider_player_id="123",
            canonical_player_key="player:messi",
            normalized_name_used="   ",
            team_context_key="team:ESP_LL:barcelona",
            shared_match_keys=("match:1",),
        )


def test_a_zero_evidence_entry_can_never_exist_to_be_resolved() -> None:
    # The validation bar is enforced at construction, not just at add()/
    # resolve() time -- an invalid entry can never enter the crosswalk in
    # the first place, so it can never resolve with positive confidence.
    crosswalk = PlayerCrosswalk()
    with pytest.raises(PlayerCrosswalkValidationError):
        crosswalk.add(_valid_entry(shared_match_keys=()))
    resolution = resolve_player_v2(
        source_code="wyscout-open", provider_player_id="123", crosswalk=crosswalk
    )
    assert resolution.status == "unresolved"
    assert not crosswalk.entries


def test_one_valid_shared_match_resolves() -> None:
    crosswalk = PlayerCrosswalk()
    crosswalk.add(_valid_entry(shared_match_keys=("match:1",)))
    resolution = resolve_player_v2(
        source_code="wyscout-open", provider_player_id="123", crosswalk=crosswalk
    )
    assert resolution.status == "resolved"
    assert resolution.confidence > 0.0
