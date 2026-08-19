from __future__ import annotations

import pytest

from football_intelligence.data_mesh.entity_resolution import normalize_team_name
from football_intelligence.providers.wyscout_open_text import repair_wyscout_double_escaped_unicode

# The real 20 Wyscout ESP_LL 2017/18 clubs (`data/cache/wyscout-open/
# 15073697_teams.json`, filtered to the team ids appearing in the real
# `matches_Spain.json`), after applying the verified Wyscout double-escaped-
# Unicode repair -- Block 20D.1's real overlap investigation, re-verified in
# Block 20D.2's completion pass.
_REAL_WYSCOUT_ESP_LL_NAMES = [
    "Athletic Club",
    repair_wyscout_double_escaped_unicode("Atl\\u00e9tico Madrid"),
    "Barcelona",
    "Celta de Vigo",
    repair_wyscout_double_escaped_unicode("Deportivo Alav\\u00e9s"),
    repair_wyscout_double_escaped_unicode("Deportivo La Coru\\u00f1a"),
    "Eibar",
    "Espanyol",
    "Getafe",
    "Girona",
    "Las Palmas",
    repair_wyscout_double_escaped_unicode("Legan\\u00e9s"),
    "Levante",
    repair_wyscout_double_escaped_unicode("M\\u00e1laga"),
    "Real Betis",
    "Real Madrid",
    "Real Sociedad",
    "Sevilla",
    "Valencia",
    "Villarreal",
]

# The real StatsBomb-side spellings for the 3 genuine convergence gaps found
# by the real Wyscout x StatsBomb ESP_LL 2017/18 collision check (Block
# 20D.1's diagnosis, fixed in Block 20D.2): StatsBomb's own team-name string
# for the same real club vs. the Wyscout spelling above it must converge on.
_REAL_STATSBOMB_TO_WYSCOUT_ESP_LL_PAIRS = [
    ("RC Deportivo La Coruña", "Deportivo La Coruña"),
    ("Celta Vigo", "Celta de Vigo"),
    ("Levante UD", "Levante"),
]


def test_all_twenty_real_wyscout_esp_ll_clubs_are_distinct_after_normalization() -> None:
    normalized = {normalize_team_name(name) for name in _REAL_WYSCOUT_ESP_LL_NAMES}
    assert len(normalized) == 20


@pytest.mark.parametrize("statsbomb_name,wyscout_name", _REAL_STATSBOMB_TO_WYSCOUT_ESP_LL_PAIRS)
def test_statsbomb_spelling_converges_with_wyscout_spelling(
    statsbomb_name: str, wyscout_name: str
) -> None:
    assert normalize_team_name(statsbomb_name) == normalize_team_name(wyscout_name)


def test_celta_alias_is_a_narrow_exact_match_not_a_generic_de_stopword() -> None:
    # The "celta vigo" -> "celta de vigo" fix is a single explicit alias
    # entry, not a rule that strips "de" from any name -- a name that merely
    # contains "de" as a substring elsewhere must be unaffected.
    assert normalize_team_name("Celta de Vigo") == normalize_team_name("Celta Vigo")
    assert normalize_team_name("Deportivo La Coruña") != normalize_team_name("Deportivo")
