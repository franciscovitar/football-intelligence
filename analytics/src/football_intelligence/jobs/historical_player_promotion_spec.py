"""Certified per-league invariants for Wyscout historical Player V2 promotion.

These numbers are not inferred during a production write. They are pinned from
independent ephemeral-PostgreSQL evidence runs over the official Wyscout Open
2017/18 bytes and the repository's current Player V2 engine.
"""

from __future__ import annotations

from dataclasses import dataclass

SEASON_LABEL = "2017/18"


@dataclass(frozen=True, slots=True)
class HistoricalPlayerPromotionSpec:
    competition_code: str
    matches: int
    teams: int
    players: int
    player_appearances: int
    player_match_stats: int
    team_match_stats: int
    source_observations: int
    score_snapshots: int
    feature_snapshots: int
    season_players: int
    season_players_450_min: int
    performance_ready: int
    evidence_states: tuple[tuple[str, int], ...]

    @property
    def scope_key(self) -> str:
        return f"competition:{self.competition_code}:{SEASON_LABEL}"

    @property
    def evidence_state_counts(self) -> dict[str, int]:
        return dict(self.evidence_states)


_SPECS: tuple[HistoricalPlayerPromotionSpec, ...] = (
    HistoricalPlayerPromotionSpec(
        competition_code="ENG_PL",
        matches=380,
        teams=20,
        players=515,
        player_appearances=10_443,
        player_match_stats=10_443,
        team_match_stats=760,
        source_observations=412_609,
        score_snapshots=2_048,
        feature_snapshots=26_841,
        season_players=512,
        season_players_450_min=385,
        performance_ready=385,
        evidence_states=(("insufficient_data", 1_754), ("partial", 294)),
    ),
    HistoricalPlayerPromotionSpec(
        competition_code="ESP_LL",
        matches=380,
        teams=20,
        players=557,
        player_appearances=10_555,
        player_match_stats=10_555,
        team_match_stats=760,
        source_observations=416_407,
        score_snapshots=2_224,
        feature_snapshots=29_008,
        season_players=556,
        season_players_450_min=415,
        performance_ready=415,
        evidence_states=(("insufficient_data", 1_880), ("partial", 344)),
    ),
    HistoricalPlayerPromotionSpec(
        competition_code="FRA_L1",
        matches=380,
        teams=20,
        players=542,
        player_appearances=10_515,
        player_match_stats=10_515,
        team_match_stats=760,
        source_observations=415_230,
        score_snapshots=2_148,
        feature_snapshots=28_007,
        season_players=537,
        season_players_450_min=395,
        performance_ready=395,
        evidence_states=(("insufficient_data", 1_822), ("partial", 326)),
    ),
    HistoricalPlayerPromotionSpec(
        competition_code="GER_BL1",
        matches=306,
        teams=18,
        players=472,
        player_appearances=8_501,
        player_match_stats=8_501,
        team_match_stats=612,
        source_observations=336_265,
        score_snapshots=1_888,
        feature_snapshots=24_786,
        season_players=472,
        season_players_450_min=349,
        performance_ready=349,
        evidence_states=(("insufficient_data", 1_596), ("partial", 292)),
    ),
    HistoricalPlayerPromotionSpec(
        competition_code="ITA_SA",
        matches=380,
        teams=20,
        players=534,
        player_appearances=10_573,
        player_match_stats=10_573,
        team_match_stats=760,
        source_observations=420_506,
        score_snapshots=2_132,
        feature_snapshots=27_872,
        season_players=533,
        season_players_450_min=403,
        performance_ready=403,
        evidence_states=(("insufficient_data", 1_774), ("partial", 358)),
    ),
)

_SPEC_BY_COMPETITION = {spec.competition_code: spec for spec in _SPECS}


def supported_promotion_competitions() -> tuple[str, ...]:
    return tuple(_SPEC_BY_COMPETITION)


def historical_player_promotion_spec(competition_code: str) -> HistoricalPlayerPromotionSpec:
    try:
        return _SPEC_BY_COMPETITION[competition_code]
    except KeyError as exc:
        raise KeyError(f"unsupported historical promotion competition {competition_code!r}") from exc
