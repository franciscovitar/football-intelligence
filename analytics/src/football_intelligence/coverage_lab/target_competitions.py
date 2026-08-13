"""The 10 target competitions for the Zero-Cost Coverage Lab.

Reuses the existing core-league and World Radar competition catalogs rather
than declaring a third, divergent list: 6 core (scheduled sync) + 4 radar
(World Radar V1) = 10. Coverage must be modeled for all 10 even when a
source's coverage is zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from football_intelligence.config.core_leagues import CORE_LEAGUES
from football_intelligence.config.world_radar_competitions import load_radar_competitions

CompetitionRole = Literal["core", "radar"]

TARGET_COMPETITION_COUNT = 10


@dataclass(frozen=True, slots=True)
class TargetCompetition:
    code: str
    name: str
    role: CompetitionRole


def build_target_competitions() -> tuple[TargetCompetition, ...]:
    core = tuple(
        TargetCompetition(code=league.code, name=league.name, role="core")
        for league in CORE_LEAGUES
    )
    radar = tuple(
        TargetCompetition(code=item.code, name=item.name, role="radar")
        for item in load_radar_competitions()
    )
    return core + radar
