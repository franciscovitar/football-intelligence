from __future__ import annotations

from datetime import date

from football_intelligence.data_mesh.entity_resolution import (
    cluster_match_dates,
    dates_within_tolerance,
    normalize_team_name,
    resolve_competition,
    resolve_match,
    resolve_player,
    resolve_team,
)


def test_resolve_competition_uses_explicit_configured_mapping() -> None:
    resolution = resolve_competition(source_code="thesportsdb", external_id="4331")
    assert resolution.status == "resolved"
    assert resolution.logical_key == "competition:GER_BL1"


def test_resolve_competition_unmapped_id_is_unresolved() -> None:
    resolution = resolve_competition(source_code="thesportsdb", external_id="999999")
    assert resolution.status == "unresolved"
    assert resolution.logical_key is None


def test_normalize_team_name_handles_cross_language_alias() -> None:
    # "Munich" (English) vs "München" (German) for the same real club.
    assert normalize_team_name("Bayern Munich") == normalize_team_name("FC Bayern München")


def test_normalize_team_name_strips_generic_club_prefixes() -> None:
    assert normalize_team_name("SV Werder Bremen") == normalize_team_name("Werder Bremen")
    assert normalize_team_name("TSG Hoffenheim") == normalize_team_name("Hoffenheim")


def test_different_provider_team_ids_resolve_to_one_logical_entity() -> None:
    # Two different providers, two different entity_source_id values, same
    # real club -- strong deterministic name identity must still converge on
    # a single logical key.
    thesportsdb_team = resolve_team(name="Bayern Munich", competition_code="GER_BL1")
    openligadb_team = resolve_team(name="FC Bayern München", competition_code="GER_BL1")
    assert thesportsdb_team.status == "resolved"
    assert openligadb_team.status == "resolved"
    assert thesportsdb_team.logical_key == openligadb_team.logical_key


def test_resolve_team_blank_name_is_unresolved() -> None:
    resolution = resolve_team(name="   ", competition_code="GER_BL1")
    assert resolution.status == "unresolved"


def test_resolve_match_requires_distinct_resolved_teams_and_date() -> None:
    home = resolve_team(name="Bayern Munich", competition_code="GER_BL1")
    away = resolve_team(name="RB Leipzig", competition_code="GER_BL1")
    resolution = resolve_match(
        competition_code="GER_BL1",
        season_label="2025-2026",
        home_team_key=home.logical_key,
        away_team_key=away.logical_key,
        kickoff_date=date(2025, 8, 22),
    )
    assert resolution.status == "resolved"
    assert resolution.logical_key is not None
    assert resolution.logical_key.startswith("match:GER_BL1:2025-2026:")


def test_resolve_match_same_team_both_sides_is_unresolved() -> None:
    team = resolve_team(name="Bayern Munich", competition_code="GER_BL1")
    resolution = resolve_match(
        competition_code="GER_BL1",
        season_label="2025-2026",
        home_team_key=team.logical_key,
        away_team_key=team.logical_key,
        kickoff_date=date(2025, 8, 22),
    )
    assert resolution.status == "unresolved"


def test_resolve_match_ambiguous_without_team_identity_stays_unresolved() -> None:
    # One side's team identity could not be resolved (e.g. a blank/garbled
    # name) -- the match must stay UNRESOLVED, never guessed.
    resolution = resolve_match(
        competition_code="GER_BL1",
        season_label="2025-2026",
        home_team_key="team:GER_BL1:bayern munchen",
        away_team_key=None,
        kickoff_date=date(2025, 8, 22),
    )
    assert resolution.status == "unresolved"
    assert resolution.logical_key is None


def test_resolve_match_missing_kickoff_date_stays_unresolved() -> None:
    resolution = resolve_match(
        competition_code="GER_BL1",
        season_label="2025-2026",
        home_team_key="team:GER_BL1:bayern munchen",
        away_team_key="team:GER_BL1:leipzig rb",
        kickoff_date=None,
    )
    assert resolution.status == "unresolved"


def test_dates_within_tolerance() -> None:
    assert dates_within_tolerance(date(2025, 8, 22), date(2025, 8, 23))
    assert dates_within_tolerance(date(2025, 8, 22), date(2025, 8, 22))
    assert not dates_within_tolerance(date(2025, 8, 22), date(2025, 8, 25))


def test_cluster_match_dates_merges_dates_within_tolerance() -> None:
    clusters = cluster_match_dates([date(2025, 8, 23), date(2025, 8, 22)])
    # Both dates collapse onto the same canonical (earliest) representative,
    # regardless of the order they were passed in.
    assert clusters[date(2025, 8, 22)] == date(2025, 8, 22)
    assert clusters[date(2025, 8, 23)] == date(2025, 8, 22)


def test_cluster_match_dates_keeps_dates_outside_tolerance_separate() -> None:
    clusters = cluster_match_dates([date(2025, 8, 22), date(2025, 8, 25)])
    assert clusters[date(2025, 8, 22)] == date(2025, 8, 22)
    assert clusters[date(2025, 8, 25)] == date(2025, 8, 25)


def test_resolve_player_is_always_unresolved_in_v0() -> None:
    # Interface/contract only: even with plausible-looking inputs, V0 never
    # auto-resolves a player -- UNRESOLVED is always safer.
    resolution = resolve_player(
        normalized_name="lionel messi",
        date_of_birth=date(1987, 6, 24),
        nationality_code="ARG",
        team_context_key="team:GER_BL1:bayern munchen",
    )
    assert resolution.status == "unresolved"
    assert resolution.logical_key is None
