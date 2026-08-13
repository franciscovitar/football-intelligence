from __future__ import annotations

from football_intelligence.coverage_lab.target_competitions import (
    TARGET_COMPETITION_COUNT,
    build_target_competitions,
)


def test_exactly_ten_target_competitions() -> None:
    competitions = build_target_competitions()
    assert len(competitions) == TARGET_COMPETITION_COUNT == 10


def test_six_core_and_four_radar() -> None:
    competitions = build_target_competitions()
    core = [item for item in competitions if item.role == "core"]
    radar = [item for item in competitions if item.role == "radar"]
    assert len(core) == 6
    assert len(radar) == 4


def test_competition_codes_are_unique() -> None:
    competitions = build_target_competitions()
    codes = [item.code for item in competitions]
    assert len(codes) == len(set(codes))


def test_includes_expected_core_and_radar_codes() -> None:
    codes = {item.code for item in build_target_competitions()}
    assert {"ARG_LPF", "ENG_PL", "ESP_LL", "ITA_SA", "GER_BL1", "FRA_L1"} <= codes
    assert {"NED_ED", "POR_PL", "BRA_A", "USA_MLS"} <= codes
