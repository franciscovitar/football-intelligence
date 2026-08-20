"""Block 20D.3: real Wyscout Open x StatsBomb Open ESP_LL 2017/18 overlap
enablement audit.

Loads already-cached real source material for both certified adapters
(no network requests of its own), emits real `NormalizedObservation`s for
the ESP_LL/La Liga 2017/18 scope via the Block 20D.3-generalized adapters,
runs Spain-specific empirical semantic checks, resolves the real
match/team overlap through Block 20D.2's Entity Resolution V2 contract
(`entity_identity_hints` only -- never `entity_source_id` parsing), builds
the first REAL deterministic `PlayerCrosswalk` population from that
overlap evidence, and reports an inventory of the exact
`(metric_name, metric_granularity)` identities observed by both adapters
within the shared-match scope.

This job performs NO database writes, NO canonical promotion, and NO
Reconciliation V2 semantics (grouping, tolerances, comparability) -- those
remain Block 20D.4's job. `STATSBOMB_INTERNAL_ONLY` is asserted, never
bypassed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters import statsbomb_open, wyscout_open
from football_intelligence.data_mesh.entity_resolution_v2 import (
    IdentityConflictError,
    PlayerCrosswalk,
    PlayerCrosswalkConflictError,
    PlayerCrosswalkEntry,
    PlayerCrosswalkValidationError,
    PlayerTeamContextEvidence,
    SourceLocalIndexV2,
    build_match_index_v2_from_observations,
    build_team_index_v2_from_observations,
    resolve_match_v2,
    resolve_player_v2,
    resolve_team_v2,
)
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.data_mesh.player_name_normalization import normalize_player_name
from football_intelligence.jobs.audit_wyscout_metric_mapping import _find_cached_file
from football_intelligence.providers.statsbomb_open import DEFAULT_PINNED_REVISION
from football_intelligence.providers.statsbomb_open_mapping import (
    adapter_safe_mappings as statsbomb_adapter_safe_mappings,
)
from football_intelligence.providers.statsbomb_open_policy import STATSBOMB_INTERNAL_ONLY
from football_intelligence.providers.wyscout_open_mapping import (
    adapter_safe_mappings as wyscout_adapter_safe_mappings,
)
from football_intelligence.providers.wyscout_open_text import (
    repair_wyscout_double_escaped_unicode,
)

CANONICAL_COMPETITION_CODE = "ESP_LL"
CANONICAL_SEASON_LABEL = "2017/18"

DEFAULT_WYSCOUT_CACHE_DIR = Path("data/cache/wyscout-open")
DEFAULT_STATSBOMB_CACHE_ROOT = Path("data/cache/statsbomb-open")

_KNOWN_WYSCOUT_ONLY_BARCELONA_FIXTURES = frozenset(
    {"2018-03-10", "2018-05-13"}
)  # Malaga vs Barcelona, Levante vs Barcelona -- real, verified (Block 20D.1)


class OverlapAuditError(RuntimeError):
    """The overlap audit could not complete a required step."""


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    detail: str


# ---------------------------------------------------------------------------
# Loading (local-only, reuses existing cache/extraction mechanisms)
# ---------------------------------------------------------------------------


def load_wyscout_esp_ll(cache_dir: Path) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    """Loads the already-extracted real Wyscout ESP_LL matches/events plus
    the shared teams.json/players.json reference files. Never downloads;
    raises if the expected already-cached files are missing."""

    matches_path = _find_cached_file(cache_dir, "matches_Spain.json")
    events_path = _find_cached_file(cache_dir, "events_Spain.json")
    players_path = _find_cached_file(cache_dir, "*players.json")
    teams_path = _find_cached_file(cache_dir, "*teams.json")
    matches_payload = json.loads(matches_path.read_text(encoding="utf-8"))
    events_payload = json.loads(events_path.read_text(encoding="utf-8"))
    players_payload = json.loads(players_path.read_text(encoding="utf-8"))
    teams_payload = json.loads(teams_path.read_text(encoding="utf-8"))
    return matches_payload, events_payload, players_payload, teams_payload


def load_statsbomb_esp_ll(
    cache_root: Path, *, source_revision: str = DEFAULT_PINNED_REVISION
) -> list[statsbomb_open.MatchBundle]:
    """Loads the already-cached real StatsBomb ESP_LL (competition_id=11,
    season_id=1) match summary + events + lineups for every match. Never
    downloads; raises if the expected already-cached files are missing."""

    scope = statsbomb_open.ESP_LL_SCOPE
    revision_dir = cache_root / source_revision
    matches_path = (
        revision_dir / f"matches/{scope.provider_competition_id}/{scope.provider_season_id}.json"
    )
    if not matches_path.exists():
        raise OverlapAuditError(
            f"required cached file missing: {matches_path} -- run "
            "football-intelligence-fetch-statsbomb-open --competition-id "
            f"{scope.provider_competition_id} --season-id {scope.provider_season_id} first "
            "(this audit performs no network requests of its own)"
        )
    matches_payload = json.loads(matches_path.read_text(encoding="utf-8"))
    if not isinstance(matches_payload, list):
        raise OverlapAuditError("cached ESP_LL match list payload is structurally unusable")

    bundles: list[statsbomb_open.MatchBundle] = []
    for item in matches_payload:
        if not isinstance(item, dict):
            continue
        match_id = item.get("match_id")
        if not isinstance(match_id, int):
            continue
        events_path = revision_dir / f"events/{match_id}.json"
        lineups_path = revision_dir / f"lineups/{match_id}.json"
        if not events_path.exists() or not lineups_path.exists():
            raise OverlapAuditError(
                f"required cached file missing for match {match_id} -- run the fetch job first"
            )
        bundles.append(
            statsbomb_open.MatchBundle(
                match_id=match_id,
                match_summary=item,
                events_payload=json.loads(events_path.read_text(encoding="utf-8")),
                lineups_payload=json.loads(lineups_path.read_text(encoding="utf-8")),
            )
        )
    return bundles


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def wyscout_full_names_by_id(players_payload: list[Any]) -> dict[str, str]:
    """Real Wyscout `players.json` full legal name (`firstName` + `lastName`,
    e.g. "Lionel Andres Messi Cuccittini") keyed by provider player id, for
    the crosswalk join ONLY -- the certified adapter's own `player_name`
    hint (`shortName`, e.g. "L. Messi") is correct for its already-certified
    purpose but is the wrong representation to join against StatsBomb's
    full-name convention. Repairs Wyscout's verified double-JSON-escaped
    Unicode defect at this provider boundary before any generic
    normalization -- the same discipline the certified adapter itself
    applies to every other Wyscout text field."""

    names: dict[str, str] = {}
    for entry in players_payload:
        if not isinstance(entry, dict):
            continue
        player_id = entry.get("wyId")
        if player_id is None:
            continue
        first_name = repair_wyscout_double_escaped_unicode(str(entry.get("firstName") or ""))
        last_name = repair_wyscout_double_escaped_unicode(str(entry.get("lastName") or ""))
        full_name = " ".join(part for part in (first_name, last_name) if part).strip()
        if full_name:
            names[str(player_id)] = full_name
    return names


def emit_wyscout_esp_ll(cache_dir: Path) -> tuple[list[NormalizedObservation], dict[str, str]]:
    matches_payload, events_payload, players_payload, teams_payload = load_wyscout_esp_ll(cache_dir)
    observations = wyscout_open.parse_england_season(
        matches_payload=matches_payload,
        events_payload=events_payload,
        players_payload=players_payload,
        teams_payload=teams_payload,
        scope=wyscout_open.ESP_LL_SCOPE,
    )
    return observations, wyscout_full_names_by_id(players_payload)


def emit_statsbomb_esp_ll(
    cache_root: Path, *, source_revision: str = DEFAULT_PINNED_REVISION
) -> list[NormalizedObservation]:
    if not STATSBOMB_INTERNAL_ONLY:
        raise AssertionError(
            "STATSBOMB_INTERNAL_ONLY was flipped to False without an explicit product/legal "
            "decision -- this overlap audit refuses to build observations under that state "
            "change unreviewed."
        )
    bundles = load_statsbomb_esp_ll(cache_root, source_revision=source_revision)
    return statsbomb_open.parse_premier_league_season(
        bundles, source_revision=source_revision, scope=statsbomb_open.ESP_LL_SCOPE
    )


# ---------------------------------------------------------------------------
# Spain-scope empirical semantic checks (section 6)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSemanticReport:
    source_code: str
    total_observations: int
    distinct_matches: int
    distinct_teams: int
    exact_identities_observed: tuple[tuple[str, str], ...]
    safe_identities_zero_observations_this_sample: tuple[tuple[str, str], ...]
    unexpected_exact_identities: tuple[tuple[str, str], ...]
    missing_granularity_count: int
    duplicate_conflict_count: int
    checks: tuple[VerificationCheck, ...]

    @property
    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)


def _numeric_suffix(entity_source_id: str) -> str:
    return entity_source_id.rsplit(":", maxsplit=1)[-1]


def build_semantic_report(
    *,
    source_code: str,
    observations: list[NormalizedObservation],
    safe_identities: set[tuple[str, str]],
) -> SourceSemanticReport:
    """Empirical semantic re-certification over a real (possibly small)
    Spain-scope sample -- never reinterprets "zero observations this
    sample" as "provider does not support this metric" (section 6): that
    set is reported, not gated on, for either provider in THIS job. Only
    genuine correctness signals (duplicate conflicts, missing granularity,
    unexpected exact identities) gate `all_passed`."""

    matches_seen: set[str] = set()
    teams_seen: set[str] = set()
    observed_identities: set[tuple[str, str]] = set()
    missing_granularity_count = 0
    seen_identity_values: dict[tuple[str, str, str, str, str | None], Any] = {}
    duplicate_conflicts = 0

    for obs in observations:
        if obs.entity_type == "match":
            matches_seen.add(obs.entity_source_id)
        elif obs.entity_type == "team":
            teams_seen.add(_numeric_suffix(obs.entity_source_id))

        identity_key = (
            obs.source_code,
            obs.entity_type,
            obs.entity_source_id,
            obs.metric_name,
            obs.metric_granularity,
        )
        if identity_key in seen_identity_values:
            if seen_identity_values[identity_key] != obs.value:
                duplicate_conflicts += 1
        else:
            seen_identity_values[identity_key] = obs.value

        if obs.metric_granularity is None:
            missing_granularity_count += 1
        else:
            observed_identities.add((obs.metric_name, obs.metric_granularity))

    unexpected_exact_identities = tuple(sorted(observed_identities - safe_identities))
    zero_observation_identities = tuple(sorted(safe_identities - observed_identities))
    exact_identities_observed = tuple(sorted(observed_identities & safe_identities))

    checks = (
        VerificationCheck(
            "no_missing_metric_granularity",
            missing_granularity_count == 0,
            f"found {missing_granularity_count} observations with metric_granularity=None",
        ),
        VerificationCheck(
            "no_conflicting_duplicate_observations",
            duplicate_conflicts == 0,
            f"found {duplicate_conflicts} conflicting duplicate identities",
        ),
        VerificationCheck(
            "no_unexpected_exact_identities_emitted",
            not unexpected_exact_identities,
            f"found {len(unexpected_exact_identities)} unexpected (metric_name, "
            f"metric_granularity) pairs: {unexpected_exact_identities[:10]}",
        ),
    )

    return SourceSemanticReport(
        source_code=source_code,
        total_observations=len(observations),
        distinct_matches=len(matches_seen),
        distinct_teams=len(teams_seen),
        exact_identities_observed=exact_identities_observed,
        safe_identities_zero_observations_this_sample=zero_observation_identities,
        unexpected_exact_identities=unexpected_exact_identities,
        missing_granularity_count=missing_granularity_count,
        duplicate_conflict_count=duplicate_conflicts,
        checks=checks,
    )


# ---------------------------------------------------------------------------
# Team / match overlap resolution (section 7) -- Entity Resolution V2 only,
# never entity_source_id parsing.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchOverlapReport:
    shared_canonical_matches: tuple[str, ...]
    date_mismatches: tuple[str, ...]
    wyscout_only_matches: tuple[str, ...]
    statsbomb_only_matches: tuple[str, ...]
    wyscout_only_barcelona_dates: tuple[str, ...]
    team_convergence: tuple[str, ...]
    wyscout_resolved_team_count: int
    statsbomb_resolved_team_count: int


def _match_home_away(
    observations: list[NormalizedObservation], *, source_code: str, team_index: SourceLocalIndexV2
) -> dict[str, tuple[str | None, str | None, str | None]]:
    """provider_match_id -> (home_team_key, away_team_key, kickoff_date)
    built directly from real match-scoped `entity_identity_hints`, resolving
    team ids via the already-built V2 `team_index` -- never
    `entity_source_id`."""

    result: dict[str, tuple[str | None, str | None, str | None]] = {}
    for obs in observations:
        if obs.entity_type != "match":
            continue
        hints = obs.entity_identity_hints
        match_id = hints.get("match_external_id")
        if not match_id or match_id in result:
            continue
        home_id = hints.get("home_team_external_id")
        away_id = hints.get("away_team_external_id")
        home_key = (
            resolve_team_v2(
                source_code=source_code, provider_team_id=home_id, team_index=team_index
            ).logical_key
            if home_id
            else None
        )
        away_key = (
            resolve_team_v2(
                source_code=source_code, provider_team_id=away_id, team_index=team_index
            ).logical_key
            if away_id
            else None
        )
        result[match_id] = (home_key, away_key, hints.get("kickoff_date"))
    return result


def resolve_overlap(
    wyscout_observations: list[NormalizedObservation],
    statsbomb_observations: list[NormalizedObservation],
) -> tuple[SourceLocalIndexV2, SourceLocalIndexV2, MatchOverlapReport]:
    team_index: SourceLocalIndexV2 = {}
    build_team_index_v2_from_observations(
        wyscout_observations, competition_code=CANONICAL_COMPETITION_CODE, into=team_index
    )
    build_team_index_v2_from_observations(
        statsbomb_observations, competition_code=CANONICAL_COMPETITION_CODE, into=team_index
    )

    match_index: SourceLocalIndexV2 = {}
    build_match_index_v2_from_observations(
        wyscout_observations,
        competition_code=CANONICAL_COMPETITION_CODE,
        team_index=team_index,
        into=match_index,
    )
    build_match_index_v2_from_observations(
        statsbomb_observations,
        competition_code=CANONICAL_COMPETITION_CODE,
        team_index=team_index,
        into=match_index,
    )

    wyscout_canonical_matches = {
        v for (source, _pid), v in match_index.items() if source == "wyscout-open"
    }
    statsbomb_canonical_matches = {
        v for (source, _pid), v in match_index.items() if source == "statsbomb-open"
    }
    shared = wyscout_canonical_matches & statsbomb_canonical_matches
    wyscout_only = wyscout_canonical_matches - statsbomb_canonical_matches
    statsbomb_only = statsbomb_canonical_matches - wyscout_canonical_matches

    # Date-mismatch detection: same real fixture (same resolved home/away
    # team pair), different resolved dates -- deliberately NOT covered by
    # the naive canonical-key intersection above, since a genuine date
    # mismatch produces two DIFFERENT canonical match keys for what would
    # be the same real fixture. No cross-source date-tolerance clustering
    # is applied here (deferred to Block 20D.4, per Block 20D.2's own
    # documented boundary) -- this only DETECTS and reports a mismatch,
    # never silently reconciles one.
    wyscout_pairs = _match_home_away(
        wyscout_observations, source_code="wyscout-open", team_index=team_index
    )
    statsbomb_pairs = _match_home_away(
        statsbomb_observations, source_code="statsbomb-open", team_index=team_index
    )
    wyscout_by_team_pair: dict[tuple[str, str], str | None] = {
        (home, away): date
        for home, away, date in wyscout_pairs.values()
        if home is not None and away is not None
    }
    statsbomb_by_team_pair: dict[tuple[str, str], str | None] = {
        (home, away): date
        for home, away, date in statsbomb_pairs.values()
        if home is not None and away is not None
    }
    date_mismatches: list[str] = []
    for pair, wy_date in wyscout_by_team_pair.items():
        sb_date = statsbomb_by_team_pair.get(pair)
        if sb_date is not None and wy_date is not None and sb_date != wy_date:
            date_mismatches.append(f"{pair[0]} vs {pair[1]}: wyscout={wy_date} statsbomb={sb_date}")

    # The two real, verified Wyscout-only Barcelona away fixtures this
    # overlap is known to be missing from the StatsBomb open-data scope
    # (Block 20D.1) -- reported for cross-reference, never assumed if the
    # real resolved evidence disagrees.
    wyscout_only_dates = {
        date for _home, _away, date in wyscout_pairs.values() if date is not None
    } - {date for _home, _away, date in statsbomb_pairs.values() if date is not None}
    wyscout_only_barcelona_dates = tuple(
        sorted(wyscout_only_dates & _KNOWN_WYSCOUT_ONLY_BARCELONA_FIXTURES)
    )

    wyscout_resolved_teams = {k for (s, _pid), k in team_index.items() if s == "wyscout-open"}
    statsbomb_resolved_teams = {k for (s, _pid), k in team_index.items() if s == "statsbomb-open"}
    team_convergence = tuple(sorted(wyscout_resolved_teams & statsbomb_resolved_teams))

    report = MatchOverlapReport(
        shared_canonical_matches=tuple(sorted(shared)),
        date_mismatches=tuple(sorted(date_mismatches)),
        wyscout_only_matches=tuple(sorted(wyscout_only)),
        statsbomb_only_matches=tuple(sorted(statsbomb_only)),
        wyscout_only_barcelona_dates=wyscout_only_barcelona_dates,
        team_convergence=team_convergence,
        wyscout_resolved_team_count=len(wyscout_resolved_teams),
        statsbomb_resolved_team_count=len(statsbomb_resolved_teams),
    )
    return team_index, match_index, report


# ---------------------------------------------------------------------------
# Player-name-normalized appearance evidence (sections 8-9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayerAppearance:
    provider_player_id: str
    player_name: str
    normalized_name: str
    match_key: str
    team_key: str


@dataclass(frozen=True)
class AppearanceCollectionReport:
    appearances: tuple[PlayerAppearance, ...]
    missing_name_count: int
    missing_team_count: int
    unresolved_match_count: int
    unresolved_team_count: int


def collect_player_appearances(
    observations: list[NormalizedObservation],
    *,
    source_code: str,
    team_index: SourceLocalIndexV2,
    match_index: SourceLocalIndexV2,
    full_name_by_player_id: dict[str, str] | None = None,
) -> AppearanceCollectionReport:
    """Collects one appearance per real (provider_player_id, match) pair
    evidenced by `entity_type == "player"` observations, resolved to their
    real canonical match/team context via V2 -- never from name similarity,
    never from `entity_source_id`.

    `full_name_by_player_id`, when given, overrides the adapter's own
    `player_name` hint for this source -- used only for Wyscout, whose
    certified hint carries a short display name ("L. Messi") while
    StatsBomb's carries the full legal name ("Lionel Andres Messi
    Cuccittini"); an exact-name join needs both sides in the same real
    convention, sourced directly from each provider's own raw data, never
    from a fuzzy/partial-name equivalence rule."""

    seen: set[tuple[str, str]] = set()
    appearances: list[PlayerAppearance] = []
    missing_name = 0
    missing_team = 0
    unresolved_match = 0
    unresolved_team = 0

    for obs in observations:
        if obs.entity_type != "player":
            continue
        hints = obs.entity_identity_hints
        player_id = hints.get("player_external_id")
        match_id = hints.get("match_external_id")
        team_id = hints.get("team_external_id")
        name = hints.get("player_name")
        if full_name_by_player_id is not None and player_id is not None:
            name = full_name_by_player_id.get(player_id, name)
        if not player_id or not match_id:
            continue
        dedup_key = (player_id, match_id)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        if not name:
            missing_name += 1
            continue
        if not team_id:
            missing_team += 1
            continue

        match_resolution = resolve_match_v2(
            source_code=source_code, provider_match_id=match_id, match_index=match_index
        )
        if match_resolution.logical_key is None:
            unresolved_match += 1
            continue
        team_resolution = resolve_team_v2(
            source_code=source_code, provider_team_id=team_id, team_index=team_index
        )
        if team_resolution.logical_key is None:
            unresolved_team += 1
            continue

        normalized = normalize_player_name(name)
        if not normalized:
            missing_name += 1
            continue

        appearances.append(
            PlayerAppearance(
                provider_player_id=player_id,
                player_name=name,
                normalized_name=normalized,
                match_key=match_resolution.logical_key,
                team_key=team_resolution.logical_key,
            )
        )

    return AppearanceCollectionReport(
        appearances=tuple(appearances),
        missing_name_count=missing_name,
        missing_team_count=missing_team,
        unresolved_match_count=unresolved_match,
        unresolved_team_count=unresolved_team,
    )


# ---------------------------------------------------------------------------
# Player crosswalk builder (sections 9-13) -- exact match+team+name evidence
# only. No fuzzy/name-only resolution.
# ---------------------------------------------------------------------------


CROSSWALK_KEY_PREFIX = "overlap-player-v2"


def crosswalk_canonical_key(
    *,
    competition_code: str,
    season_label: str,
    provider_refs: Iterable[tuple[str, str]],
) -> str:
    """Deterministic, opaque, EXPLICITLY overlap-scoped logical player key.

    THIS IS NOT A GLOBAL CANONICAL PLAYER ID. It identifies one validated
    two-provider (Wyscout Open, StatsBomb Open) crosswalk pair within this
    single certified competition/season overlap only -- never a
    `football.players` production id, never persisted, never user-facing.
    A future canonical-promotion decision must map these provider refs to
    an independent football-player identity rather than treating this
    overlap key as production identity.

    `digest` is a SHA-256 hex digest (stdlib `hashlib`, deterministic
    across processes -- unlike the built-in `hash()`, and never a random
    UUID) of the canonically ordered (sorted by `(source_code,
    provider_player_id)`), pipe-delimited provider refs the pair was
    actually validated against. Team context and normalized-name
    formatting deliberately do NOT participate: a validated mid-season
    transfer (a real player evidenced under more than one resolved team
    context -- e.g. Guidetti's Celta Vigo -> Alavés move) must resolve to
    the exact same key regardless of which team(s) back the evidence, and
    a cosmetic name-normalization change must never silently mint a new
    identity for an otherwise-identical validated provider pair. Sorting
    the refs first also makes the key caller-order-independent: the same
    validated pair produces the same key regardless of which provider is
    passed first."""

    ordered_refs = sorted(provider_refs)
    if not ordered_refs:
        raise ValueError("crosswalk_canonical_key requires at least one provider ref")
    payload = "|".join(
        f"{source_code}:{provider_player_id}" for source_code, provider_player_id in ordered_refs
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{CROSSWALK_KEY_PREFIX}:{competition_code}:{season_label}:{digest}"


@dataclass(frozen=True)
class CandidatePair:
    wyscout_player_id: str
    statsbomb_player_id: str
    normalized_name: str
    team_context_evidence: tuple[PlayerTeamContextEvidence, ...]

    @property
    def team_context_keys(self) -> tuple[str, ...]:
        return tuple(evidence.team_context_key for evidence in self.team_context_evidence)

    @property
    def shared_match_keys(self) -> tuple[str, ...]:
        result: set[str] = set()
        for evidence in self.team_context_evidence:
            result.update(evidence.shared_match_keys)
        return tuple(sorted(result))

    @property
    def is_multi_team_context(self) -> bool:
        return len(self.team_context_evidence) > 1


@dataclass(frozen=True)
class CrosswalkBuildReport:
    wyscout_distinct_player_ids: int
    statsbomb_distinct_player_ids: int
    accepted_pairs: tuple[CandidatePair, ...]
    entries_created: int
    pairs_by_shared_match_count: dict[int, int]
    unresolved_missing_name: int
    unresolved_missing_team: int
    unresolved_no_exact_name_counterpart: int
    ambiguous_one_to_many: int
    ambiguous_many_to_one: int
    duplicate_name_collision_cases: int
    # Section 11 (Block 20D.3 corrective pass): these are now ACCEPTED,
    # genuinely multi-team-context pairs -- e.g. a real mid-season transfer
    # -- reported for audit visibility, never excluded. Renamed from the
    # earlier `multi_team_context_cases` (which reported EXCLUDED pairs)
    # to make that reversal explicit rather than silently repurposing the
    # old field.
    multi_team_context_accepted_pairs: tuple[str, ...]
    inconsistent_name_evidence_cases: tuple[str, ...]
    crosswalk_conflicts: int
    resolution_success_count: int


def _appearance_index(
    appearances: tuple[PlayerAppearance, ...],
) -> dict[tuple[str, str, str], set[str]]:
    index: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for appearance in appearances:
        key = (appearance.match_key, appearance.team_key, appearance.normalized_name)
        index[key].add(appearance.provider_player_id)
    return index


def build_player_crosswalk(
    wyscout_appearances: tuple[PlayerAppearance, ...],
    statsbomb_appearances: tuple[PlayerAppearance, ...],
    *,
    wyscout_missing_name: int,
    wyscout_missing_team: int,
    statsbomb_missing_name: int,
    statsbomb_missing_team: int,
) -> tuple[PlayerCrosswalk, CrosswalkBuildReport]:
    wyscout_index = _appearance_index(wyscout_appearances)
    statsbomb_index = _appearance_index(statsbomb_appearances)

    shared_keys = wyscout_index.keys() & statsbomb_index.keys()
    no_exact_name_counterpart = len((wyscout_index.keys() | statsbomb_index.keys()) - shared_keys)

    duplicate_name_collision_cases = 0
    # (wyscout_id, statsbomb_id) -> list[(match_key, team_key, normalized_name)]
    pair_evidence: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
    for key in shared_keys:
        wyscout_ids = wyscout_index[key]
        statsbomb_ids = statsbomb_index[key]
        if len(wyscout_ids) > 1 or len(statsbomb_ids) > 1:
            # Two+ real players share the same (match, team, normalized
            # name) slot on at least one side -- genuinely ambiguous,
            # never guessed.
            duplicate_name_collision_cases += 1
            continue
        wyscout_id = next(iter(wyscout_ids))
        statsbomb_id = next(iter(statsbomb_ids))
        pair_evidence[(wyscout_id, statsbomb_id)].append(key)

    wyscout_to_statsbomb: dict[str, set[str]] = defaultdict(set)
    statsbomb_to_wyscout: dict[str, set[str]] = defaultdict(set)
    for wyscout_id, statsbomb_id in pair_evidence:
        wyscout_to_statsbomb[wyscout_id].add(statsbomb_id)
        statsbomb_to_wyscout[statsbomb_id].add(wyscout_id)

    ambiguous_wyscout_ids = {
        pid for pid, counterparts in wyscout_to_statsbomb.items() if len(counterparts) > 1
    }
    ambiguous_statsbomb_ids = {
        pid for pid, counterparts in statsbomb_to_wyscout.items() if len(counterparts) > 1
    }

    multi_team_context_accepted_pairs: list[str] = []
    inconsistent_name_evidence_cases: list[str] = []
    accepted_pairs: list[CandidatePair] = []
    pairs_by_shared_match_count: dict[int, int] = defaultdict(int)

    for (wyscout_id, statsbomb_id), evidence in pair_evidence.items():
        if wyscout_id in ambiguous_wyscout_ids or statsbomb_id in ambiguous_statsbomb_ids:
            continue

        # Name-collision safety gate (section 8): the exact normalized name
        # must be identical across every shared (match, team) slot this
        # provider pair was evidenced under -- regardless of how many team
        # contexts follow, a name disagreement is never resolved, only
        # reported. Normalized name still does NOT participate in
        # `canonical_player_key` (section 4) -- this check is a resolution
        # safety gate, not an identity definition.
        names = {name for _match_key, _team_key, name in evidence}
        if len(names) > 1:
            inconsistent_name_evidence_cases.append(
                f"wyscout:{wyscout_id} statsbomb:{statsbomb_id} names={sorted(names)}"
            )
            continue
        normalized_name = next(iter(names))

        # Section 5/6: aggregate by team_context_key -> its own shared
        # matches. No web-transfer knowledge, no chronology inference --
        # this is purely the real, already-validated (match, team, name)
        # evidence grouped by team. A player who never changed clubs
        # within the overlap scope gets exactly one team context; a real
        # mid-season transfer (verified in the Block 20D.3 diagnosis:
        # Guidetti, Gálvez, Moyà, Fuego) gets more than one, and is now
        # ACCEPTED rather than excluded.
        matches_by_team: dict[str, set[str]] = defaultdict(set)
        for match_key, team_key, _name in evidence:
            matches_by_team[team_key].add(match_key)

        team_context_evidence = tuple(
            PlayerTeamContextEvidence(
                team_context_key=team_key,
                shared_match_keys=tuple(sorted(matches_by_team[team_key])),
            )
            for team_key in sorted(matches_by_team)
        )

        pair = CandidatePair(
            wyscout_player_id=wyscout_id,
            statsbomb_player_id=statsbomb_id,
            normalized_name=normalized_name,
            team_context_evidence=team_context_evidence,
        )
        accepted_pairs.append(pair)
        pairs_by_shared_match_count[len(pair.shared_match_keys)] += 1
        if pair.is_multi_team_context:
            teams = list(pair.team_context_keys)
            multi_team_context_accepted_pairs.append(
                f"wyscout:{wyscout_id} statsbomb:{statsbomb_id} teams={teams}"
            )

    crosswalk = PlayerCrosswalk()
    crosswalk_conflicts = 0
    entries_created = 0
    for pair in accepted_pairs:
        canonical_key = crosswalk_canonical_key(
            competition_code=CANONICAL_COMPETITION_CODE,
            season_label=CANONICAL_SEASON_LABEL,
            provider_refs=(
                ("wyscout-open", pair.wyscout_player_id),
                ("statsbomb-open", pair.statsbomb_player_id),
            ),
        )
        try:
            crosswalk.add(
                PlayerCrosswalkEntry(
                    source_code="wyscout-open",
                    provider_player_id=pair.wyscout_player_id,
                    canonical_player_key=canonical_key,
                    normalized_name_used=pair.normalized_name,
                    team_context_evidence=pair.team_context_evidence,
                )
            )
            entries_created += 1
            crosswalk.add(
                PlayerCrosswalkEntry(
                    source_code="statsbomb-open",
                    provider_player_id=pair.statsbomb_player_id,
                    canonical_player_key=canonical_key,
                    normalized_name_used=pair.normalized_name,
                    team_context_evidence=pair.team_context_evidence,
                )
            )
            entries_created += 1
        except (PlayerCrosswalkConflictError, PlayerCrosswalkValidationError):
            crosswalk_conflicts += 1

    resolution_success_count = 0
    for pair in accepted_pairs:
        wyscout_resolution = resolve_player_v2(
            source_code="wyscout-open",
            provider_player_id=pair.wyscout_player_id,
            crosswalk=crosswalk,
        )
        statsbomb_resolution = resolve_player_v2(
            source_code="statsbomb-open",
            provider_player_id=pair.statsbomb_player_id,
            crosswalk=crosswalk,
        )
        if (
            wyscout_resolution.status == "resolved"
            and wyscout_resolution.logical_key == statsbomb_resolution.logical_key
        ):
            resolution_success_count += 1

    report = CrosswalkBuildReport(
        wyscout_distinct_player_ids=len({a.provider_player_id for a in wyscout_appearances}),
        statsbomb_distinct_player_ids=len({a.provider_player_id for a in statsbomb_appearances}),
        accepted_pairs=tuple(accepted_pairs),
        entries_created=entries_created,
        pairs_by_shared_match_count=dict(pairs_by_shared_match_count),
        unresolved_missing_name=wyscout_missing_name + statsbomb_missing_name,
        unresolved_missing_team=wyscout_missing_team + statsbomb_missing_team,
        unresolved_no_exact_name_counterpart=no_exact_name_counterpart,
        ambiguous_one_to_many=len(ambiguous_wyscout_ids),
        ambiguous_many_to_one=len(ambiguous_statsbomb_ids),
        duplicate_name_collision_cases=duplicate_name_collision_cases,
        multi_team_context_accepted_pairs=tuple(sorted(multi_team_context_accepted_pairs)),
        inconsistent_name_evidence_cases=tuple(sorted(inconsistent_name_evidence_cases)),
        crosswalk_conflicts=crosswalk_conflicts,
        resolution_success_count=resolution_success_count,
    )
    return crosswalk, report


# ---------------------------------------------------------------------------
# Overlapping exact metric-identity inventory (section 15) -- INVENTORY
# ONLY. No comparability claim, no value comparison, no reconciliation.
# ---------------------------------------------------------------------------


def compute_overlapping_metric_inventory(
    *,
    wyscout_observations: list[NormalizedObservation],
    statsbomb_observations: list[NormalizedObservation],
    shared_match_keys: frozenset[str],
    match_index: SourceLocalIndexV2,
) -> tuple[tuple[str, str], ...]:
    def _identities_in_shared_scope(
        observations: list[NormalizedObservation], source_code: str
    ) -> set[tuple[str, str]]:
        identities: set[tuple[str, str]] = set()
        for obs in observations:
            match_id = obs.entity_identity_hints.get("match_external_id")
            if match_id is None:
                continue
            resolution = resolve_match_v2(
                source_code=source_code, provider_match_id=match_id, match_index=match_index
            )
            if resolution.logical_key in shared_match_keys and obs.metric_granularity is not None:
                identities.add((obs.metric_name, obs.metric_granularity))
        return identities

    wyscout_identities = _identities_in_shared_scope(wyscout_observations, "wyscout-open")
    statsbomb_identities = _identities_in_shared_scope(statsbomb_observations, "statsbomb-open")
    return tuple(sorted(wyscout_identities & statsbomb_identities))


# ---------------------------------------------------------------------------
# Report assembly (section 14) and CLI
# ---------------------------------------------------------------------------


def _sample(items: tuple[Any, ...], limit: int = 10) -> list[Any]:
    return list(items[:limit])


def run_overlap_audit(
    *,
    wyscout_cache_dir: Path = DEFAULT_WYSCOUT_CACHE_DIR,
    statsbomb_cache_root: Path = DEFAULT_STATSBOMB_CACHE_ROOT,
    statsbomb_source_revision: str = DEFAULT_PINNED_REVISION,
) -> dict[str, Any]:
    wyscout_observations, wyscout_full_names = emit_wyscout_esp_ll(wyscout_cache_dir)
    statsbomb_observations = emit_statsbomb_esp_ll(
        statsbomb_cache_root, source_revision=statsbomb_source_revision
    )

    wyscout_safe_identities: set[tuple[str, str]] = {
        (m.catalog_key, str(m.catalog_granularity)) for m in wyscout_adapter_safe_mappings()
    }
    statsbomb_safe_identities: set[tuple[str, str]] = {
        (m.catalog_key, str(m.catalog_granularity)) for m in statsbomb_adapter_safe_mappings()
    }
    wyscout_semantic = build_semantic_report(
        source_code="wyscout-open",
        observations=wyscout_observations,
        safe_identities=wyscout_safe_identities,
    )
    statsbomb_semantic = build_semantic_report(
        source_code="statsbomb-open",
        observations=statsbomb_observations,
        safe_identities=statsbomb_safe_identities,
    )

    try:
        team_index, match_index, overlap = resolve_overlap(
            wyscout_observations, statsbomb_observations
        )
    except IdentityConflictError as exc:
        raise OverlapAuditError(
            f"V2 identity conflict while resolving the real overlap: {exc}"
        ) from exc

    wyscout_appearance_report = collect_player_appearances(
        wyscout_observations,
        source_code="wyscout-open",
        team_index=team_index,
        match_index=match_index,
        full_name_by_player_id=wyscout_full_names,
    )
    statsbomb_appearance_report = collect_player_appearances(
        statsbomb_observations,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    crosswalk, crosswalk_report = build_player_crosswalk(
        wyscout_appearance_report.appearances,
        statsbomb_appearance_report.appearances,
        wyscout_missing_name=wyscout_appearance_report.missing_name_count,
        wyscout_missing_team=wyscout_appearance_report.missing_team_count,
        statsbomb_missing_name=statsbomb_appearance_report.missing_name_count,
        statsbomb_missing_team=statsbomb_appearance_report.missing_team_count,
    )

    metric_inventory = compute_overlapping_metric_inventory(
        wyscout_observations=wyscout_observations,
        statsbomb_observations=statsbomb_observations,
        shared_match_keys=frozenset(overlap.shared_canonical_matches),
        match_index=match_index,
    )

    accepted_sample = [
        {
            "wyscout_player_id": pair.wyscout_player_id,
            "statsbomb_player_id": pair.statsbomb_player_id,
            "normalized_name": pair.normalized_name,
            "team_context_keys": list(pair.team_context_keys),
            "shared_match_count": len(pair.shared_match_keys),
        }
        for pair in _sample(crosswalk_report.accepted_pairs)
    ]

    report: dict[str, Any] = {
        "source_scope": {
            "canonical_competition_code": CANONICAL_COMPETITION_CODE,
            "canonical_season_label": CANONICAL_SEASON_LABEL,
            "wyscout_provider_competition_id": wyscout_open.ESP_LL_SCOPE.provider_competition_id,
            "wyscout_provider_season_id": wyscout_open.ESP_LL_SCOPE.provider_season_id,
            "statsbomb_provider_competition_id": (
                statsbomb_open.ESP_LL_SCOPE.provider_competition_id
            ),
            "statsbomb_provider_season_id": statsbomb_open.ESP_LL_SCOPE.provider_season_id,
            "statsbomb_internal_only": STATSBOMB_INTERNAL_ONLY,
        },
        "source_counts": {
            "wyscout_total_observations": wyscout_semantic.total_observations,
            "wyscout_distinct_matches": wyscout_semantic.distinct_matches,
            "wyscout_distinct_teams": wyscout_semantic.distinct_teams,
            "statsbomb_total_observations": statsbomb_semantic.total_observations,
            "statsbomb_distinct_matches": statsbomb_semantic.distinct_matches,
            "statsbomb_distinct_teams": statsbomb_semantic.distinct_teams,
        },
        "semantic_recertification": {
            "wyscout_all_passed": wyscout_semantic.all_passed,
            "wyscout_exact_identities_observed": len(wyscout_semantic.exact_identities_observed),
            "wyscout_safe_identities_zero_observations_this_sample": len(
                wyscout_semantic.safe_identities_zero_observations_this_sample
            ),
            "wyscout_unexpected_exact_identities": list(
                wyscout_semantic.unexpected_exact_identities
            ),
            "statsbomb_all_passed": statsbomb_semantic.all_passed,
            "statsbomb_exact_identities_observed": len(
                statsbomb_semantic.exact_identities_observed
            ),
            "statsbomb_safe_identities_zero_observations_this_sample": len(
                statsbomb_semantic.safe_identities_zero_observations_this_sample
            ),
            "statsbomb_unexpected_exact_identities": list(
                statsbomb_semantic.unexpected_exact_identities
            ),
        },
        "match_overlap": {
            "wyscout_match_count": wyscout_semantic.distinct_matches,
            "statsbomb_match_count": statsbomb_semantic.distinct_matches,
            "shared_canonical_match_count": len(overlap.shared_canonical_matches),
            "date_mismatches": list(overlap.date_mismatches),
            "wyscout_only_match_count": len(overlap.wyscout_only_matches),
            "statsbomb_only_match_count": len(overlap.statsbomb_only_matches),
            "wyscout_only_known_barcelona_dates": list(overlap.wyscout_only_barcelona_dates),
        },
        "team_resolution": {
            "wyscout_resolved_team_count": overlap.wyscout_resolved_team_count,
            "statsbomb_resolved_team_count": overlap.statsbomb_resolved_team_count,
            "converged_team_count": len(overlap.team_convergence),
        },
        "player_crosswalk": {
            "wyscout_distinct_player_ids_evidenced": crosswalk_report.wyscout_distinct_player_ids,
            "statsbomb_distinct_player_ids_evidenced": (
                crosswalk_report.statsbomb_distinct_player_ids
            ),
            "accepted_pairs": len(crosswalk_report.accepted_pairs),
            "entries_created": crosswalk_report.entries_created,
            "pairs_by_shared_match_count": crosswalk_report.pairs_by_shared_match_count,
            "unresolved_missing_name": crosswalk_report.unresolved_missing_name,
            "unresolved_missing_team": crosswalk_report.unresolved_missing_team,
            "unresolved_no_exact_name_counterpart": (
                crosswalk_report.unresolved_no_exact_name_counterpart
            ),
            "ambiguous_one_to_many": crosswalk_report.ambiguous_one_to_many,
            "ambiguous_many_to_one": crosswalk_report.ambiguous_many_to_one,
            "duplicate_name_collision_cases": crosswalk_report.duplicate_name_collision_cases,
            "multi_team_context_accepted_pairs": list(
                crosswalk_report.multi_team_context_accepted_pairs
            ),
            "inconsistent_name_evidence_cases": list(
                crosswalk_report.inconsistent_name_evidence_cases
            ),
            "crosswalk_conflicts": crosswalk_report.crosswalk_conflicts,
            "resolution_success_count": crosswalk_report.resolution_success_count,
        },
        "overlapping_exact_metric_identities": {
            "count": len(metric_inventory),
            "identities": [list(identity) for identity in metric_inventory],
        },
        "evidence": {
            "accepted_pairs_sample": accepted_sample,
            "multi_team_context_accepted_pairs_sample": _sample(
                crosswalk_report.multi_team_context_accepted_pairs
            ),
            "duplicate_name_collision_case_count": crosswalk_report.duplicate_name_collision_cases,
        },
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 20D.3: real Wyscout Open x StatsBomb Open ESP_LL 2017/18 overlap "
            "audit. Local-only (no network requests, no DB writes, no canonical "
            "promotion)."
        )
    )
    parser.add_argument("--wyscout-cache-dir", type=Path, default=DEFAULT_WYSCOUT_CACHE_DIR)
    parser.add_argument("--statsbomb-cache-root", type=Path, default=DEFAULT_STATSBOMB_CACHE_ROOT)
    parser.add_argument("--statsbomb-source-revision", type=str, default=DEFAULT_PINNED_REVISION)
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional path to also write the JSON report (an ignored cache/temp path only).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = run_overlap_audit(
            wyscout_cache_dir=args.wyscout_cache_dir,
            statsbomb_cache_root=args.statsbomb_cache_root,
            statsbomb_source_revision=args.statsbomb_source_revision,
        )
    except OverlapAuditError as exc:
        print(f"OVERLAP AUDIT: FAIL - {exc}")
        raise SystemExit(1) from exc

    print(json.dumps(report, indent=2, sort_keys=False))
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")
        print(f"report written: {args.report}")


if __name__ == "__main__":
    main()
