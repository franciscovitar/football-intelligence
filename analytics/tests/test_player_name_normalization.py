from __future__ import annotations

from football_intelligence.data_mesh.player_name_normalization import normalize_player_name


def test_accents_are_folded() -> None:
    assert normalize_player_name("Gerard Deulofeu") == normalize_player_name("Gérard Deulofeu")
    assert normalize_player_name("Jose Angel") == normalize_player_name("José Ángel")


def test_punctuation_is_normalized() -> None:
    assert normalize_player_name("O'Brien") == normalize_player_name("O Brien")
    assert normalize_player_name("Jean-Paul") == normalize_player_name("Jean Paul")
    assert normalize_player_name("J. Alba") == normalize_player_name("J Alba")
    assert normalize_player_name("Alba, Jordi") == normalize_player_name("Alba Jordi")


def test_whitespace_and_case_are_normalized() -> None:
    assert normalize_player_name("  Jordi   Alba ") == normalize_player_name("jordi alba")
    assert normalize_player_name("JORDI ALBA") == normalize_player_name("jordi alba")


def test_blank_input_returns_empty_string() -> None:
    assert normalize_player_name("") == ""
    assert normalize_player_name("   ") == ""


def test_token_order_is_preserved_not_sorted() -> None:
    # Unlike team-name normalization, player-name tokens are never
    # reordered -- "Jordi Alba" and "Alba Jordi" are not asserted equal
    # here because they are NOT the same deterministic normalization
    # (order is real identity-bearing information for a person's name).
    assert normalize_player_name("Jordi Alba") != normalize_player_name("Alba Jordi")


def test_different_real_names_never_collapse_to_the_same_value() -> None:
    # No fuzzy/edit-distance equivalence: genuinely different names must
    # never normalize to the same string.
    assert normalize_player_name("Jordi Alba") != normalize_player_name("Jordi Albo")
    assert normalize_player_name("Gerard Deulofeu") != normalize_player_name("Gerard Deulofe")


def test_real_wyscout_and_statsbomb_name_conventions_converge_when_genuinely_the_same_player() -> (
    None
):
    # Real-shape sanity check (not encoded as an alias -- both sides
    # already share the same underlying characters once accents/case are
    # normalized).
    assert normalize_player_name("Jordi Alba Ramos") == normalize_player_name("jordi alba ramos")
