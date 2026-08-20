"""Focused tests for the Block 20D.3 overlap audit job: match/team overlap
resolution, the player crosswalk builder's exact-evidence acceptance rule
and ambiguity policy, and the semantic-report's granularity-aware coverage
checks. Uses small synthetic `NormalizedObservation` fixtures -- these tests
never touch real cached data (see the real-cache run captured in the
Block 20D.3 RETURN report for the actual ESP_LL evidence)."""

from __future__ import annotations

from datetime import datetime

import pytest

from football_intelligence.data_mesh.entity_resolution_v2 import (
    build_match_index_v2_from_observations,
    build_team_index_v2_from_observations,
    resolve_player_v2,
)
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.jobs.audit_wyscout_statsbomb_overlap import (
    build_player_crosswalk,
    build_semantic_report,
    collect_player_appearances,
    crosswalk_canonical_key,
    resolve_overlap,
)


def _obs(
    *,
    source_code: str,
    entity_type: str,
    entity_source_id: str,
    hints: dict,
    metric_name: str = "status",
    value: object = "Played",
    metric_granularity: str | None = None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=source_code,
        source_type="objective_structured",
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_source_id=entity_source_id,
        entity_identity_hints=hints,
        metric_name=metric_name,
        value=value,
        observed_at=datetime(2018, 1, 1),
        source_timestamp=None,
        source_reference="test",
        ingestion_run_id=None,
        semantic_version="test-v1",
        metric_granularity=metric_granularity,
    )


_TEAM_NAMES = {"100": "TeamA", "200": "TeamB", "300": "TeamC"}


def _match_obs(
    source_code: str, match_id: str, home_id: str, away_id: str, date: str
) -> NormalizedObservation:
    return _obs(
        source_code=source_code,
        entity_type="match",
        entity_source_id=match_id,
        hints={
            "season_label": "2017/18",
            "match_external_id": match_id,
            "home_team_external_id": home_id,
            "home_team_name": _TEAM_NAMES[home_id],
            "away_team_external_id": away_id,
            "away_team_name": _TEAM_NAMES[away_id],
            "kickoff_date": date,
        },
    )


def _player_obs(
    source_code: str, player_id: str, match_id: str, team_id: str, name: str
) -> NormalizedObservation:
    return _obs(
        source_code=source_code,
        entity_type="player",
        entity_source_id=f"{match_id}:{player_id}",
        hints={
            "season_label": "2017/18",
            "match_external_id": match_id,
            "player_external_id": player_id,
            "player_name": name,
            "team_external_id": team_id,
        },
    )


# ---------------------------------------------------------------------------
# Match overlap (section 7)
# ---------------------------------------------------------------------------


def test_two_source_ids_for_the_same_exact_date_fixture_converge() -> None:
    wyscout = [_match_obs("wyscout-open", "5001", "100", "200", "2018-01-01")]
    statsbomb = [_match_obs("statsbomb-open", "9001", "100", "200", "2018-01-01")]
    _team_index, _match_index, overlap = resolve_overlap(wyscout, statsbomb)
    assert len(overlap.shared_canonical_matches) == 1
    assert overlap.wyscout_only_matches == ()
    assert overlap.statsbomb_only_matches == ()
    assert overlap.date_mismatches == ()


def test_source_only_fixture_stays_source_only() -> None:
    wyscout = [
        _match_obs("wyscout-open", "5001", "100", "200", "2018-01-01"),
        _match_obs("wyscout-open", "5002", "100", "300", "2018-01-08"),
    ]
    statsbomb = [_match_obs("statsbomb-open", "9001", "100", "200", "2018-01-01")]
    _team_index, _match_index, overlap = resolve_overlap(wyscout, statsbomb)
    assert len(overlap.shared_canonical_matches) == 1
    assert len(overlap.wyscout_only_matches) == 1
    assert overlap.statsbomb_only_matches == ()


def test_no_date_tolerance_hack_a_real_date_mismatch_is_reported_not_clustered() -> None:
    # Same real team pair, genuinely different reported dates -- these
    # produce two DIFFERENT canonical match keys (no clustering applied
    # here), and the mismatch is reported explicitly rather than silently
    # reconciled or crashing.
    wyscout = [_match_obs("wyscout-open", "5001", "100", "200", "2018-01-01")]
    statsbomb = [_match_obs("statsbomb-open", "9001", "100", "200", "2018-01-02")]
    _team_index, _match_index, overlap = resolve_overlap(wyscout, statsbomb)
    assert overlap.shared_canonical_matches == ()
    assert len(overlap.date_mismatches) == 1
    assert "wyscout=2018-01-01" in overlap.date_mismatches[0]
    assert "statsbomb=2018-01-02" in overlap.date_mismatches[0]


# ---------------------------------------------------------------------------
# Player crosswalk builder (sections 9-13)
# ---------------------------------------------------------------------------


def _build_indexes(wyscout_matches, statsbomb_matches):
    team_index: dict = {}
    build_team_index_v2_from_observations(
        wyscout_matches, competition_code="ESP_LL", into=team_index
    )
    build_team_index_v2_from_observations(
        statsbomb_matches, competition_code="ESP_LL", into=team_index
    )
    match_index: dict = {}
    build_match_index_v2_from_observations(
        wyscout_matches, competition_code="ESP_LL", team_index=team_index, into=match_index
    )
    build_match_index_v2_from_observations(
        statsbomb_matches, competition_code="ESP_LL", team_index=team_index, into=match_index
    )
    return team_index, match_index


def test_same_match_team_and_exact_name_produces_an_accepted_candidate() -> None:
    wyscout_matches = [_match_obs("wyscout-open", "5001", "100", "200", "2018-01-01")]
    statsbomb_matches = [_match_obs("statsbomb-open", "9001", "100", "200", "2018-01-01")]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    wyscout_players = [_player_obs("wyscout-open", "p1", "5001", "100", "Jordi Alba")]
    statsbomb_players = [_player_obs("statsbomb-open", "s1", "9001", "100", "Jordi Alba")]

    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    crosswalk, report = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=wyscout_report.missing_name_count,
        wyscout_missing_team=wyscout_report.missing_team_count,
        statsbomb_missing_name=statsbomb_report.missing_name_count,
        statsbomb_missing_team=statsbomb_report.missing_team_count,
    )
    assert len(report.accepted_pairs) == 1
    pair = report.accepted_pairs[0]
    assert pair.wyscout_player_id == "p1"
    assert pair.statsbomb_player_id == "s1"

    wyscout_resolution = resolve_player_v2(
        source_code="wyscout-open", provider_player_id="p1", crosswalk=crosswalk
    )
    statsbomb_resolution = resolve_player_v2(
        source_code="statsbomb-open", provider_player_id="s1", crosswalk=crosswalk
    )
    assert wyscout_resolution.status == "resolved"
    assert wyscout_resolution.logical_key == statsbomb_resolution.logical_key


def test_same_name_different_team_produces_no_match() -> None:
    wyscout_matches = [_match_obs("wyscout-open", "5001", "100", "200", "2018-01-01")]
    statsbomb_matches = [_match_obs("statsbomb-open", "9001", "100", "200", "2018-01-01")]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    wyscout_players = [_player_obs("wyscout-open", "p1", "5001", "100", "Jordi Alba")]
    statsbomb_players = [_player_obs("statsbomb-open", "s1", "9001", "200", "Jordi Alba")]

    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    _crosswalk, report = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    assert report.accepted_pairs == ()
    assert report.unresolved_no_exact_name_counterpart == 2


def test_same_team_and_name_but_no_shared_match_produces_no_match() -> None:
    wyscout_matches = [
        _match_obs("wyscout-open", "5001", "100", "200", "2018-01-01"),
        _match_obs("wyscout-open", "5002", "100", "300", "2018-01-08"),
    ]
    statsbomb_matches = [_match_obs("statsbomb-open", "9001", "100", "200", "2018-01-01")]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    # Wyscout evidences this player only in the match with no StatsBomb
    # counterpart at all.
    wyscout_players = [_player_obs("wyscout-open", "p1", "5002", "100", "Jordi Alba")]
    statsbomb_players = [_player_obs("statsbomb-open", "s1", "9001", "100", "Jordi Alba")]

    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    _crosswalk, report = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    assert report.accepted_pairs == ()


def test_missing_name_is_reported_unresolved_not_silently_dropped() -> None:
    wyscout_matches = [_match_obs("wyscout-open", "5001", "100", "200", "2018-01-01")]
    team_index, match_index = _build_indexes(wyscout_matches, [])
    wyscout_players = [
        _obs(
            source_code="wyscout-open",
            entity_type="player",
            entity_source_id="5001:p1",
            hints={
                "season_label": "2017/18",
                "match_external_id": "5001",
                "player_external_id": "p1",
                "team_external_id": "100",
                # no player_name
            },
        )
    ]
    report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    assert report.appearances == ()
    assert report.missing_name_count == 1


def test_one_wyscout_id_matching_multiple_statsbomb_ids_is_unresolved_ambiguous() -> None:
    wyscout_matches = [
        _match_obs("wyscout-open", "5001", "100", "200", "2018-01-01"),
        _match_obs("wyscout-open", "5002", "100", "300", "2018-01-08"),
    ]
    statsbomb_matches = [
        _match_obs("statsbomb-open", "9001", "100", "200", "2018-01-01"),
        _match_obs("statsbomb-open", "9002", "100", "300", "2018-01-08"),
    ]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    wyscout_players = [
        _player_obs("wyscout-open", "p1", "5001", "100", "Jordi Alba"),
        _player_obs("wyscout-open", "p1", "5002", "100", "Jordi Alba"),
    ]
    statsbomb_players = [
        _player_obs("statsbomb-open", "s1", "9001", "100", "Jordi Alba"),
        _player_obs("statsbomb-open", "s2", "9002", "100", "Jordi Alba"),
    ]
    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    _crosswalk, report = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    assert report.accepted_pairs == ()
    assert report.ambiguous_one_to_many == 1


def test_many_wyscout_ids_matching_one_statsbomb_id_is_unresolved_ambiguous() -> None:
    wyscout_matches = [
        _match_obs("wyscout-open", "5001", "100", "200", "2018-01-01"),
        _match_obs("wyscout-open", "5002", "100", "300", "2018-01-08"),
    ]
    statsbomb_matches = [
        _match_obs("statsbomb-open", "9001", "100", "200", "2018-01-01"),
        _match_obs("statsbomb-open", "9002", "100", "300", "2018-01-08"),
    ]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    wyscout_players = [
        _player_obs("wyscout-open", "p1", "5001", "100", "Jordi Alba"),
        _player_obs("wyscout-open", "p2", "5002", "100", "Jordi Alba"),
    ]
    statsbomb_players = [
        _player_obs("statsbomb-open", "s1", "9001", "100", "Jordi Alba"),
        _player_obs("statsbomb-open", "s1", "9002", "100", "Jordi Alba"),
    ]
    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    _crosswalk, report = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    assert report.accepted_pairs == ()
    assert report.ambiguous_many_to_one == 1


def test_repeated_identical_evidence_is_idempotent() -> None:
    wyscout_matches = [_match_obs("wyscout-open", "5001", "100", "200", "2018-01-01")]
    statsbomb_matches = [_match_obs("statsbomb-open", "9001", "100", "200", "2018-01-01")]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    wyscout_players = [_player_obs("wyscout-open", "p1", "5001", "100", "Jordi Alba")]
    statsbomb_players = [_player_obs("statsbomb-open", "s1", "9001", "100", "Jordi Alba")]

    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    _crosswalk1, report1 = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    _crosswalk2, report2 = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    assert report1.accepted_pairs == report2.accepted_pairs
    assert report1.entries_created == report2.entries_created == 2
    assert report1.crosswalk_conflicts == 0


def test_a_pair_evidenced_under_two_team_contexts_is_accepted_with_both_contexts() -> None:
    # Block 20D.3 corrective pass (Option C): a real mid-season-transfer-
    # shaped case is now ACCEPTED -- never silently packed into one
    # team_context_key, never arbitrarily assigned to one club, never
    # dropped -- with one PlayerTeamContextEvidence per resolved team,
    # each carrying exactly the matches that evidence that team.
    wyscout_matches = [
        _match_obs("wyscout-open", "5001", "100", "200", "2017-09-01"),
        _match_obs("wyscout-open", "5002", "300", "100", "2018-03-01"),
    ]
    statsbomb_matches = [
        _match_obs("statsbomb-open", "9001", "100", "200", "2017-09-01"),
        _match_obs("statsbomb-open", "9002", "300", "100", "2018-03-01"),
    ]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    wyscout_players = [
        _player_obs("wyscout-open", "p1", "5001", "100", "Transfer Player"),
        _player_obs("wyscout-open", "p1", "5002", "300", "Transfer Player"),
    ]
    statsbomb_players = [
        _player_obs("statsbomb-open", "s1", "9001", "100", "Transfer Player"),
        _player_obs("statsbomb-open", "s1", "9002", "300", "Transfer Player"),
    ]
    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    crosswalk, report = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    assert len(report.accepted_pairs) == 1
    pair = report.accepted_pairs[0]
    assert pair.wyscout_player_id == "p1"
    assert pair.statsbomb_player_id == "s1"
    assert len(pair.team_context_evidence) == 2
    assert set(pair.team_context_keys) == {"team:ESP_LL:teama", "team:ESP_LL:teamc"}
    assert len(pair.shared_match_keys) == 2  # no evidence dropped

    assert len(report.multi_team_context_accepted_pairs) == 1
    assert "p1" in report.multi_team_context_accepted_pairs[0]
    assert "s1" in report.multi_team_context_accepted_pairs[0]

    wyscout_resolution = resolve_player_v2(
        source_code="wyscout-open", provider_player_id="p1", crosswalk=crosswalk
    )
    statsbomb_resolution = resolve_player_v2(
        source_code="statsbomb-open", provider_player_id="s1", crosswalk=crosswalk
    )
    assert wyscout_resolution.status == "resolved"
    assert wyscout_resolution.logical_key == statsbomb_resolution.logical_key


def test_same_name_and_team_but_no_shared_match_between_the_two_stints_does_not_match() -> None:
    # A player evidenced under the same normalized name and the same single
    # team on both sides, but with zero shared match evidence at all, must
    # never match -- distinct from the transfer case above, which requires
    # at least one genuinely shared match per team context.
    wyscout_matches = [_match_obs("wyscout-open", "5001", "100", "200", "2018-01-01")]
    statsbomb_matches = [_match_obs("statsbomb-open", "9001", "300", "200", "2018-06-01")]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    wyscout_players = [_player_obs("wyscout-open", "p1", "5001", "100", "No Overlap Player")]
    statsbomb_players = [_player_obs("statsbomb-open", "s1", "9001", "300", "No Overlap Player")]

    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    _crosswalk, report = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    assert report.accepted_pairs == ()


def test_inconsistent_name_evidence_across_team_contexts_is_still_unresolved() -> None:
    # Even with the multi-team-context contract accepting transfers, a name
    # disagreement across the pair's evidence must still be rejected --
    # this is a resolution safety gate that does not relax just because
    # team-context multiplicity is now supported.
    wyscout_matches = [
        _match_obs("wyscout-open", "5001", "100", "200", "2017-09-01"),
        _match_obs("wyscout-open", "5002", "300", "100", "2018-03-01"),
    ]
    statsbomb_matches = [
        _match_obs("statsbomb-open", "9001", "100", "200", "2017-09-01"),
        _match_obs("statsbomb-open", "9002", "300", "100", "2018-03-01"),
    ]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    wyscout_players = [
        _player_obs("wyscout-open", "p1", "5001", "100", "Name One"),
        _player_obs("wyscout-open", "p1", "5002", "300", "Name Two"),
    ]
    statsbomb_players = [
        _player_obs("statsbomb-open", "s1", "9001", "100", "Name One"),
        _player_obs("statsbomb-open", "s1", "9002", "300", "Name Two"),
    ]
    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    _crosswalk, report = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    assert report.accepted_pairs == ()
    assert len(report.inconsistent_name_evidence_cases) == 1


# ---------------------------------------------------------------------------
# Crosswalk canonical key (section 4) -- opaque, provider-ref-based, never
# name-only or team-dependent.
# ---------------------------------------------------------------------------


def test_key_is_order_independent_across_provider_refs() -> None:
    key_a = crosswalk_canonical_key(
        competition_code="ESP_LL",
        season_label="2017/18",
        provider_refs=[("wyscout-open", "151"), ("statsbomb-open", "6038")],
    )
    key_b = crosswalk_canonical_key(
        competition_code="ESP_LL",
        season_label="2017/18",
        provider_refs=[("statsbomb-open", "6038"), ("wyscout-open", "151")],
    )
    assert key_a == key_b


def test_key_differs_for_a_different_provider_pair() -> None:
    key_a = crosswalk_canonical_key(
        competition_code="ESP_LL",
        season_label="2017/18",
        provider_refs=[("wyscout-open", "151"), ("statsbomb-open", "6038")],
    )
    key_b = crosswalk_canonical_key(
        competition_code="ESP_LL",
        season_label="2017/18",
        provider_refs=[("wyscout-open", "999"), ("statsbomb-open", "6038")],
    )
    assert key_a != key_b


def test_key_differs_for_a_different_season() -> None:
    key_a = crosswalk_canonical_key(
        competition_code="ESP_LL",
        season_label="2017/18",
        provider_refs=[("wyscout-open", "151"), ("statsbomb-open", "6038")],
    )
    key_b = crosswalk_canonical_key(
        competition_code="ESP_LL",
        season_label="2018/19",
        provider_refs=[("wyscout-open", "151"), ("statsbomb-open", "6038")],
    )
    assert key_a != key_b


def test_key_has_an_explicit_version_prefix() -> None:
    key = crosswalk_canonical_key(
        competition_code="ESP_LL",
        season_label="2017/18",
        provider_refs=[("wyscout-open", "151"), ("statsbomb-open", "6038")],
    )
    assert key.startswith("overlap-player-v2:ESP_LL:2017/18:")


def test_key_digest_is_a_sha256_hex_string_not_a_builtin_hash_or_uuid() -> None:
    key = crosswalk_canonical_key(
        competition_code="ESP_LL",
        season_label="2017/18",
        provider_refs=[("wyscout-open", "151"), ("statsbomb-open", "6038")],
    )
    digest = key.rsplit(":", maxsplit=1)[-1]
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_key_is_deterministic_across_repeated_calls() -> None:
    # A stand-in for cross-process stability -- Python's builtin hash() is
    # salted per-process and would fail this even within one process run if
    # it were used; hashlib.sha256 never varies for the same input.
    refs = [("wyscout-open", "151"), ("statsbomb-open", "6038")]
    keys = {
        crosswalk_canonical_key(
            competition_code="ESP_LL", season_label="2017/18", provider_refs=refs
        )
        for _ in range(5)
    }
    assert len(keys) == 1


# ---------------------------------------------------------------------------
# Crosswalk key hardening: exactly the two-provider Wyscout Open x StatsBomb
# Open equivalence, never an arbitrary provider set (review correction).
# ---------------------------------------------------------------------------


def test_key_rejects_zero_refs() -> None:
    with pytest.raises(ValueError):
        crosswalk_canonical_key(competition_code="ESP_LL", season_label="2017/18", provider_refs=[])


def test_key_rejects_one_ref() -> None:
    with pytest.raises(ValueError):
        crosswalk_canonical_key(
            competition_code="ESP_LL",
            season_label="2017/18",
            provider_refs=[("wyscout-open", "151")],
        )


def test_key_rejects_duplicate_same_ref() -> None:
    with pytest.raises(ValueError):
        crosswalk_canonical_key(
            competition_code="ESP_LL",
            season_label="2017/18",
            provider_refs=[("wyscout-open", "151"), ("wyscout-open", "151")],
        )


def test_key_rejects_two_refs_from_the_same_source() -> None:
    with pytest.raises(ValueError):
        crosswalk_canonical_key(
            competition_code="ESP_LL",
            season_label="2017/18",
            provider_refs=[("wyscout-open", "151"), ("wyscout-open", "999")],
        )


def test_key_rejects_an_unknown_source_code() -> None:
    with pytest.raises(ValueError):
        crosswalk_canonical_key(
            competition_code="ESP_LL",
            season_label="2017/18",
            provider_refs=[("wyscout-open", "151"), ("some-other-provider", "6038")],
        )


def test_key_rejects_a_blank_provider_id() -> None:
    with pytest.raises(ValueError):
        crosswalk_canonical_key(
            competition_code="ESP_LL",
            season_label="2017/18",
            provider_refs=[("wyscout-open", "   "), ("statsbomb-open", "6038")],
        )


def test_key_rejects_three_refs() -> None:
    with pytest.raises(ValueError):
        crosswalk_canonical_key(
            competition_code="ESP_LL",
            season_label="2017/18",
            provider_refs=[
                ("wyscout-open", "151"),
                ("statsbomb-open", "6038"),
                ("statsbomb-open", "9999"),
            ],
        )


# ---------------------------------------------------------------------------
# Atomic pair insertion (review correction) -- exercised end-to-end through
# the real builder's normal (non-conflicting) path. The genuinely
# conflicting path is proven directly against PlayerCrosswalk.would_conflict()
# in tests/test_data_mesh_entity_resolution_v2.py: build_player_crosswalk's
# own upstream ambiguity filtering (one_to_many/many_to_one) already makes a
# same-call registry conflict structurally unreachable, since every accepted
# pair's wyscout_id and statsbomb_id are each guaranteed unique across
# accepted_pairs before the insertion loop ever runs.
# ---------------------------------------------------------------------------


def test_entries_created_reflects_actual_stored_pair_entries_for_a_multi_pair_batch() -> None:
    wyscout_matches = [
        _match_obs("wyscout-open", "5001", "100", "200", "2018-01-01"),
        _match_obs("wyscout-open", "5002", "100", "300", "2018-01-08"),
    ]
    statsbomb_matches = [
        _match_obs("statsbomb-open", "9001", "100", "200", "2018-01-01"),
        _match_obs("statsbomb-open", "9002", "100", "300", "2018-01-08"),
    ]
    team_index, match_index = _build_indexes(wyscout_matches, statsbomb_matches)

    wyscout_players = [
        _player_obs("wyscout-open", "p1", "5001", "100", "Player One"),
        _player_obs("wyscout-open", "p2", "5002", "100", "Player Two"),
    ]
    statsbomb_players = [
        _player_obs("statsbomb-open", "s1", "9001", "100", "Player One"),
        _player_obs("statsbomb-open", "s2", "9002", "100", "Player Two"),
    ]
    wyscout_report = collect_player_appearances(
        wyscout_players, source_code="wyscout-open", team_index=team_index, match_index=match_index
    )
    statsbomb_report = collect_player_appearances(
        statsbomb_players,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    crosswalk, report = build_player_crosswalk(
        wyscout_report.appearances,
        statsbomb_report.appearances,
        wyscout_missing_name=0,
        wyscout_missing_team=0,
        statsbomb_missing_name=0,
        statsbomb_missing_team=0,
    )
    assert len(report.accepted_pairs) == 2
    assert report.entries_created == 2 * len(report.accepted_pairs) == 4
    assert report.crosswalk_conflicts == 0
    assert len(crosswalk.entries) == 4


# ---------------------------------------------------------------------------
# Audit semantic report (section 6 / 17)
# ---------------------------------------------------------------------------


def test_exact_granularity_is_preserved_in_the_semantic_report() -> None:
    observations = [
        _obs(
            source_code="wyscout-open",
            entity_type="player",
            entity_source_id="5001:p1",
            hints={},
            metric_name="goals",
            value=1,
            metric_granularity="player_match",
        )
    ]
    report = build_semantic_report(
        source_code="wyscout-open",
        observations=observations,
        safe_identities={("goals", "player_match")},
    )
    assert ("goals", "player_match") in report.exact_identities_observed
    assert report.missing_granularity_count == 0
    assert report.all_passed


def test_sample_zero_safe_identity_is_reported_not_reclassified_as_unsupported() -> None:
    observations = [
        _obs(
            source_code="wyscout-open",
            entity_type="player",
            entity_source_id="5001:p1",
            hints={},
            metric_name="goals",
            value=1,
            metric_granularity="player_match",
        )
    ]
    report = build_semantic_report(
        source_code="wyscout-open",
        observations=observations,
        safe_identities={("goals", "player_match"), ("saves", "goalkeeper_match")},
    )
    # "saves"/"goalkeeper_match" happened zero times in this tiny sample --
    # reported as sample coverage, never gated as a failure.
    assert ("saves", "goalkeeper_match") in report.safe_identities_zero_observations_this_sample
    assert report.all_passed


def test_unexpected_exact_identity_fails_the_report() -> None:
    observations = [
        _obs(
            source_code="wyscout-open",
            entity_type="player",
            entity_source_id="5001:p1",
            hints={},
            metric_name="unexpected_metric",
            value=1,
            metric_granularity="player_match",
        )
    ]
    report = build_semantic_report(
        source_code="wyscout-open",
        observations=observations,
        safe_identities={("goals", "player_match")},
    )
    assert ("unexpected_metric", "player_match") in report.unexpected_exact_identities
    assert not report.all_passed


def test_missing_metric_granularity_fails_the_report() -> None:
    observations = [
        _obs(
            source_code="wyscout-open",
            entity_type="player",
            entity_source_id="5001:p1",
            hints={},
            metric_name="goals",
            value=1,
            metric_granularity=None,
        )
    ]
    report = build_semantic_report(
        source_code="wyscout-open",
        observations=observations,
        safe_identities={("goals", "player_match")},
    )
    assert report.missing_granularity_count == 1
    assert not report.all_passed
