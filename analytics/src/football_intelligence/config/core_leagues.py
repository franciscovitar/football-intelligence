"""Core competition catalog for scheduled synchronization."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CoreLeague:
    code: str
    provider_league_id: int
    name: str


CORE_LEAGUES: tuple[CoreLeague, ...] = (
    CoreLeague("ARG_LPF", 128, "Liga Profesional"),
    CoreLeague("ENG_PL", 39, "Premier League"),
    CoreLeague("ESP_LL", 140, "LaLiga"),
    CoreLeague("ITA_SA", 135, "Serie A"),
    CoreLeague("GER_BL1", 78, "Bundesliga"),
    CoreLeague("FRA_L1", 61, "Ligue 1"),
)


def league_by_code(code: str) -> CoreLeague:
    for league in CORE_LEAGUES:
        if league.code == code:
            return league
    raise KeyError(code)
