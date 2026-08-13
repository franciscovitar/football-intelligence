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
from collections.abc import Iterable
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


def cluster_match_dates(
    dates: Iterable[date],
    *,
    tolerance_days: int = MATCH_DATE_TOLERANCE_DAYS,
) -> dict[date, date]:
    """Deterministically cluster kickoff dates that fall within tolerance.

    Returns a mapping from every input date to a canonical representative
    date (the earliest date in its cluster). Two dates land in the same
    cluster exactly when a chain of `dates_within_tolerance` steps connects
    them; because the input is sorted before clustering, the result depends
    only on the *set* of dates observed, never on which source or provider
    reported which date first. Dates whose nearest neighbor is outside
    tolerance start (and stay in) their own cluster.
    """

    unique_sorted = sorted(set(dates))
    canonical: dict[date, date] = {}
    cluster_start: date | None = None
    previous: date | None = None
    for current in unique_sorted:
        if (
            cluster_start is None
            or previous is None
            or not dates_within_tolerance(previous, current, tolerance_days=tolerance_days)
        ):
            cluster_start = current
        canonical[current] = cluster_start
        previous = current
    return canonical


@dataclass(frozen=True, slots=True)
class CompetitionMapping:
    source_code: str
    external_id: str
    canonical_code: str
    external_name: str


# Explicit configured mapping (Block 13 5.COMPETITION, deepened Block 15):
# every entry below was verified live against the provider's own API/file
# during implementation -- none is guessed from documentation alone.
#
# football-data.org Free tier ("Tier One") competition codes: a small,
# explicit, reviewable table -- never trusted blindly. The Zero-Cost
# Coverage Lab job only ever treats one of these as actually confirmed for a
# given run after finding its `code` present in that run's live
# `/v4/competitions` response; a mapping present here with no matching live
# entry stays `not_probed`, never fabricated coverage. ARG_LPF (Liga
# Profesional Argentina) and USA_MLS are deliberately absent: football-data.org's
# Free tier does not expose either.
#
# TheSportsDB v1 Free `idLeague` values (Block 15): verified live via
# `lookupleague.php?id=<id>` during implementation -- each entry's returned
# `strLeague`/`strCountry` was checked against the expected competition
# before being added here. `all_leagues.php` and `search_all_leagues.php` on
# the shared Free test key ("123") only ever return a small curated subset,
# not a full searchable catalog, so Argentina/Portugal/Brazil/MLS could not
# be discovered through listing endpoints alone -- their ids were verified
# individually via `lookupleague.php` instead.
#
# Football-Data.co.uk (Block 15): `external_id` is the site's own division
# code, used directly in its published CSV file paths
# (`https://www.football-data.co.uk/mmz4281/<season>/<code>.csv`). Verified
# live: the site publishes results CSVs for these 7 European target
# competitions only -- it does not cover ARG_LPF, BRA_A, or USA_MLS at all,
# so no mapping exists for those three (never fabricated).
COMPETITION_MAPPINGS: tuple[CompetitionMapping, ...] = (
    CompetitionMapping("thesportsdb", "4406", "ARG_LPF", "Argentinian Primera Division"),
    CompetitionMapping("thesportsdb", "4328", "ENG_PL", "English Premier League"),
    CompetitionMapping("thesportsdb", "4335", "ESP_LL", "Spanish La Liga"),
    CompetitionMapping("thesportsdb", "4332", "ITA_SA", "Italian Serie A"),
    CompetitionMapping("thesportsdb", "4331", "GER_BL1", "German Bundesliga"),
    CompetitionMapping("thesportsdb", "4334", "FRA_L1", "French Ligue 1"),
    CompetitionMapping("thesportsdb", "4337", "NED_ED", "Dutch Eredivisie"),
    CompetitionMapping("thesportsdb", "4344", "POR_PL", "Portuguese Primeira Liga"),
    CompetitionMapping("thesportsdb", "4351", "BRA_A", "Brazilian Serie A"),
    CompetitionMapping("thesportsdb", "4346", "USA_MLS", "American Major League Soccer"),
    CompetitionMapping("openligadb", "bl1", "GER_BL1", "1. Fussball-Bundesliga"),
    CompetitionMapping("football-data-org", "PL", "ENG_PL", "Premier League"),
    CompetitionMapping("football-data-org", "PD", "ESP_LL", "Primera Division"),
    CompetitionMapping("football-data-org", "SA", "ITA_SA", "Serie A"),
    CompetitionMapping("football-data-org", "BL1", "GER_BL1", "Bundesliga"),
    CompetitionMapping("football-data-org", "FL1", "FRA_L1", "Ligue 1"),
    CompetitionMapping("football-data-org", "DED", "NED_ED", "Eredivisie"),
    CompetitionMapping("football-data-org", "PPL", "POR_PL", "Primeira Liga"),
    CompetitionMapping("football-data-org", "BSA", "BRA_A", "Campeonato Brasileiro Série A"),
    CompetitionMapping("football-data-uk", "E0", "ENG_PL", "Premier League"),
    CompetitionMapping("football-data-uk", "SP1", "ESP_LL", "Primera Division"),
    CompetitionMapping("football-data-uk", "I1", "ITA_SA", "Serie A"),
    CompetitionMapping("football-data-uk", "D1", "GER_BL1", "Bundesliga"),
    CompetitionMapping("football-data-uk", "F1", "FRA_L1", "Ligue 1"),
    CompetitionMapping("football-data-uk", "N1", "NED_ED", "Eredivisie"),
    CompetitionMapping("football-data-uk", "P1", "POR_PL", "Primeira Liga"),
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
