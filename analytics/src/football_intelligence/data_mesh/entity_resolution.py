"""Conservative, deterministic entity resolution for the multi-source data mesh.

No fuzzy/similarity-threshold matching and no LLM resolution for objective
data. When identity cannot be established from strong, explicit evidence, the
result is UNRESOLVED -- never a guessed link.

Resolved logical keys are PoC-scoped identifiers (`team:...`, `match:...`).
They deliberately do not point at `football.teams`/`football.matches` rows:
V0 must not auto-link into the production canonical graph.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from football_intelligence.data_mesh.models import EntityResolution

_SPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]")

# Generic corporate-entity-type tokens that differ between providers for the
# same real club (e.g. "FC Bayern München" vs "Bayern Munich"). Stripping
# them is a deterministic transformation, not a similarity heuristic: it is
# applied identically regardless of which two names are being compared.
_TEAM_STOPWORDS = frozenset({"fc", "sc", "sv", "tsg", "vfb", "vfl", "bsc", "spvgg", "ev"})

# Known cross-language spelling variants for the same city/club. This is an
# explicit, reviewable alias table -- not a fuzzy/edit-distance guess.
_TEAM_TOKEN_ALIASES: dict[str, str] = {
    "munich": "munchen",
}

MATCH_DATE_TOLERANCE_DAYS = 1


def normalize_team_name(raw: str) -> str:
    decomposed = unicodedata.normalize("NFKD", raw)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = without_marks.casefold()
    cleaned = _NON_ALNUM_RE.sub(" ", lowered)
    tokens = [token for token in _SPACE_RE.split(cleaned) if token]
    significant = [
        _TEAM_TOKEN_ALIASES.get(token, token)
        for token in tokens
        if token not in _TEAM_STOPWORDS and not token.isdigit()
    ]
    return " ".join(sorted(significant))


def dates_within_tolerance(
    a: date,
    b: date,
    *,
    tolerance_days: int = MATCH_DATE_TOLERANCE_DAYS,
) -> bool:
    return abs((a - b).days) <= tolerance_days


@dataclass(frozen=True, slots=True)
class CompetitionMapping:
    source_code: str
    external_id: str
    canonical_code: str
    external_name: str


# Explicit configured mapping (Block 13 5.COMPETITION): PoC scope is the
# Bundesliga overlap between the two free sources.
COMPETITION_MAPPINGS: tuple[CompetitionMapping, ...] = (
    CompetitionMapping("thesportsdb", "4331", "GER_BL1", "German Bundesliga"),
    CompetitionMapping("openligadb", "bl1", "GER_BL1", "1. Fussball-Bundesliga"),
)


def resolve_competition(*, source_code: str, external_id: str) -> EntityResolution:
    for mapping in COMPETITION_MAPPINGS:
        if mapping.source_code == source_code and mapping.external_id == external_id:
            return EntityResolution(
                status="resolved",
                logical_key=f"competition:{mapping.canonical_code}",
                entity_type="competition",
                confidence=1.0,
                reason="explicit configured mapping",
            )
    return EntityResolution(
        status="unresolved",
        logical_key=None,
        entity_type="competition",
        confidence=0.0,
        reason=f"no configured mapping for {source_code}:{external_id}",
    )


def resolve_team(*, name: str, competition_code: str) -> EntityResolution:
    normalized = normalize_team_name(name)
    if not normalized:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type="team",
            confidence=0.0,
            reason="blank/unusable team name",
        )
    return EntityResolution(
        status="resolved",
        logical_key=f"team:{competition_code}:{normalized}",
        entity_type="team",
        confidence=0.90,
        reason="deterministic normalized-name identity",
    )


def resolve_match(
    *,
    competition_code: str,
    season_label: str,
    home_team_key: str | None,
    away_team_key: str | None,
    kickoff_date: date | None,
) -> EntityResolution:
    if not home_team_key or not away_team_key:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type="match",
            confidence=0.0,
            reason="home/away team identity not resolved",
        )
    if home_team_key == away_team_key:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type="match",
            confidence=0.0,
            reason="home and away team identity must be distinct",
        )
    if kickoff_date is None:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type="match",
            confidence=0.0,
            reason="kickoff date not available",
        )

    logical_key = (
        f"match:{competition_code}:{season_label}:{home_team_key}:{away_team_key}:"
        f"{kickoff_date.isoformat()}"
    )
    return EntityResolution(
        status="resolved",
        logical_key=logical_key,
        entity_type="match",
        confidence=0.90,
        reason="competition+teams+date identity",
    )


def resolve_player(
    *,
    normalized_name: str,
    date_of_birth: date | None,
    nationality_code: str | None,
    team_context_key: str | None,
) -> EntityResolution:
    """V0 interface/contract only.

    Strong player identity (normalized name + date of birth + team context)
    is a real future capability, but no source in this PoC supplies
    corroborated player-level identity, so V0 never auto-resolves a player.
    UNRESOLVED is always safer than an incorrect link.
    """

    del normalized_name, date_of_birth, nationality_code, team_context_key
    return EntityResolution(
        status="unresolved",
        logical_key=None,
        entity_type="player",
        confidence=0.0,
        reason="player entity resolution is an interface-only contract in V0",
    )
