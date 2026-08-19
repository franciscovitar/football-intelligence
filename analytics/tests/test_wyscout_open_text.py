from __future__ import annotations

from football_intelligence.providers.wyscout_open_text import (
    repair_wyscout_double_escaped_unicode,
)


def test_repairs_double_escaped_e_acute() -> None:
    assert repair_wyscout_double_escaped_unicode("Atl\\u00e9tico Madrid") == "Atlético Madrid"


def test_repairs_double_escaped_a_acute() -> None:
    assert repair_wyscout_double_escaped_unicode("M\\u00e1laga") == "Málaga"


def test_ascii_text_stays_unchanged() -> None:
    assert repair_wyscout_double_escaped_unicode("Manchester City") == "Manchester City"


def test_already_correctly_decoded_unicode_stays_unchanged() -> None:
    # A real accented character (not the literal backslash-u pattern) must
    # never be touched -- this proves the repair is not a blanket
    # transliteration/normalization pass.
    assert repair_wyscout_double_escaped_unicode("Atlético Madrid") == "Atlético Madrid"
    assert repair_wyscout_double_escaped_unicode("Málaga") == "Málaga"


def test_repairs_player_name_field() -> None:
    assert repair_wyscout_double_escaped_unicode("Juan Jos\\u00e9") == "Juan José"


def test_repairs_deportivo_la_coruna() -> None:
    assert (
        repair_wyscout_double_escaped_unicode("Deportivo La Coru\\u00f1a") == "Deportivo La Coruña"
    )


def test_repairs_multiple_occurrences_in_one_string() -> None:
    assert (
        repair_wyscout_double_escaped_unicode("Legan\\u00e9s vs Alav\\u00e9s")
        == "Leganés vs Alavés"
    )


def test_empty_string_stays_empty() -> None:
    assert repair_wyscout_double_escaped_unicode("") == ""


def test_string_with_a_real_unrelated_backslash_is_left_alone() -> None:
    # A literal backslash NOT followed by "u" + 4 hex digits must never be
    # touched -- proves the pattern is narrow, not a generic backslash
    # stripper.
    text = "C:\\Users\\team"
    assert repair_wyscout_double_escaped_unicode(text) == text
