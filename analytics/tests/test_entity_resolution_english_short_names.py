from __future__ import annotations

import pytest

from football_intelligence.data_mesh.entity_resolution import normalize_team_name

# Every one of the 20 real ENG_PL 2025/26 clubs as reported by
# Football-Data.co.uk (short form, committed in
# `data/real/2025-26/eng_pl_matches.json`) and OpenFootball (official long
# form, committed in `data/real/2025-26/eng_pl_matches_openfootball.json`).
# Both must resolve to the same logical team identity so the two real
# current sources can actually be reconciled, not just coincidentally match
# when a provider happens to use the same string.
_REAL_ENG_PL_NAME_PAIRS = [
    ("Arsenal", "Arsenal FC"),
    ("Aston Villa", "Aston Villa FC"),
    ("Bournemouth", "AFC Bournemouth"),
    ("Brentford", "Brentford FC"),
    ("Brighton", "Brighton & Hove Albion FC"),
    ("Burnley", "Burnley FC"),
    ("Chelsea", "Chelsea FC"),
    ("Crystal Palace", "Crystal Palace FC"),
    ("Everton", "Everton FC"),
    ("Fulham", "Fulham FC"),
    ("Leeds", "Leeds United FC"),
    ("Liverpool", "Liverpool FC"),
    ("Man City", "Manchester City FC"),
    ("Man United", "Manchester United FC"),
    ("Newcastle", "Newcastle United FC"),
    ("Nott'm Forest", "Nottingham Forest FC"),
    ("Sunderland", "Sunderland AFC"),
    ("Tottenham", "Tottenham Hotspur FC"),
    ("West Ham", "West Ham United FC"),
    ("Wolves", "Wolverhampton Wanderers FC"),
]


@pytest.mark.parametrize("short_name,long_name", _REAL_ENG_PL_NAME_PAIRS)
def test_football_data_uk_short_name_matches_openfootball_long_name(
    short_name: str, long_name: str
) -> None:
    assert normalize_team_name(short_name) == normalize_team_name(long_name)


def test_all_twenty_real_clubs_are_distinct_after_normalization() -> None:
    normalized = {normalize_team_name(short) for short, _long in _REAL_ENG_PL_NAME_PAIRS}
    assert len(normalized) == 20


def test_unrelated_clubs_never_accidentally_collide() -> None:
    assert normalize_team_name("Newcastle") != normalize_team_name("Sunderland")
    assert normalize_team_name("Man City") != normalize_team_name("Man United")
    assert normalize_team_name("West Ham") != normalize_team_name("Wolves")
