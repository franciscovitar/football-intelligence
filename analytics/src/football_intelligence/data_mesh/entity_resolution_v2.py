"""Entity Resolution V2 additions (Block 20D.2).

`entity_resolution.py` (V0/Block 13) resolves competition/team/match/player
identity using conventions two certified real historical providers --
Wyscout Open and StatsBomb Open -- no longer follow: team identity depended
on a non-catalog `entity_type == "team", metric_name == "name"` observation
neither certified adapter emits (identity now lives only in
`entity_identity_hints`), and nothing in V0 preserves Metric Catalog V2
`metric_granularity`, so the same `metric_name` at two different
granularities (`saves`/player_match vs `saves`/goalkeeper_match) could not
be told apart once entity resolution collapsed both to `entity_type ==
"player"`. See `docs/ENTITY_RESOLUTION_V2.md` for the full evidence trail
(Block 20D.1's audit, the real Wyscout x StatsBomb Spain/La Liga 2017/18
overlap it discovered, and Block 20D.2's fixes).

This module is purely additive: every V0 function in `entity_resolution.py`
keeps its exact existing behavior (the Football-Data.co.uk x OpenFootball
ENG_PL 2025/26 baseline this repository already depends on is untouched).
V2 capabilities live here, and are opt-in for callers that have the richer
identity a certified V2 adapter actually provides.

## What's here

- `logical_fact_key()`: builds the correctly match/season-scoped logical
  fact identity for every Metric Catalog granularity, so a `player_match`
  fact from one match can never collapse into a `player_match` fact from a
  different match (or a `player_season` fact) just because both resolved to
  the same player.
- `resolve_team_v2()` / `resolve_match_v2()` /
  `build_team_index_v2_from_observations()` /
  `build_match_index_v2_from_observations()`: strong-evidence team/match
  resolution that does not require a `team.name` observation. Both
  certified adapters now emit explicit `team_external_id`/`team_name`,
  `home_team_external_id`/`home_team_name`,
  `away_team_external_id`/`away_team_name`, and `match_external_id` hints
  (Block 20D.2 completion pass) -- these functions read only
  `entity_identity_hints`, never `entity_source_id`'s composite
  `"{match_id}:{team_id}"` shape, satisfying the identity-hint contract's
  explicit-hints-over-colon-splitting preference. `build_team_index_v2()` /
  `build_match_index_v2()` remain as lower-level primitives for a caller
  that already has id-to-name evidence from elsewhere (e.g. a provider's
  separate teams/players reference file) -- they never touch
  `entity_source_id` either.
- `PlayerTeamContextEvidence` / `PlayerCrosswalkEntry` / `PlayerCrosswalk` /
  `resolve_player_v2()`: the deterministic player-identity crosswalk
  **contract**. Block 20D.3's real Wyscout x StatsBomb overlap work builds
  real entries; this block defines what a valid entry must contain and how
  lookup/conflict behaves. Without a validated entry, a player stays
  UNRESOLVED, exactly like V0's `resolve_player()`. One
  `PlayerCrosswalkEntry` supports N>=1 `PlayerTeamContextEvidence` team
  contexts for the same real (source_code, provider_player_id) -- Block
  20D.3's Option C redesign, which replaced an earlier single-team-context
  shape once real evidence (4 genuine mid-season transfers in the ESP_LL
  2017/18 overlap) proved one team per entry was insufficient. The
  registry key stays `(source_code, provider_player_id)`: one provider
  player id still resolves to exactly one player identity, never one
  identity per club.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from football_intelligence.data_mesh.entity_resolution import resolve_match, resolve_team
from football_intelligence.data_mesh.models import EntityResolution, NormalizedObservation
from football_intelligence.data_mesh.timeparse import normalize_season_label, parse_date
from football_intelligence.metric_catalog.types import MetricGranularity

# ---------------------------------------------------------------------------
# Granularity-safe logical fact identities
# ---------------------------------------------------------------------------


def _blank(value: str | None) -> bool:
    """True for `None`, `""`, or a whitespace-only string -- the single
    definition of "missing" every required-context check below shares, so a
    silently blank hint (a real risk once hints come from real, sometimes
    incomplete, provider payloads) can never be mistaken for present
    context."""

    return value is None or not value.strip()


def logical_fact_key(
    *,
    metric_granularity: MetricGranularity,
    competition_code: str,
    season_label: str | None = None,
    match_key: str | None = None,
    team_key: str | None = None,
    player_key: str | None = None,
) -> str | None:
    """Builds the logical fact identity for one observation's metric,
    correctly scoped for its Metric Catalog granularity.

    Returns `None` -- never a degraded/partial key -- when a piece of
    context that granularity requires is missing OR blank (an empty or
    whitespace-only string is treated exactly like `None`; a blank hint is
    exactly as unusable as a missing one). The **essential invariant** this
    enforces: facts from different matches, different seasons, or different
    granularities can never collapse into the same key merely because they
    share an entity or a metric name.

    `match_key`/`team_key` are expected to already be fully-qualified V0/V2
    logical keys (e.g. `"match:ENG_PL:2015/16:team:ENG_PL:arsenal:team:ENG_PL:chelsea:2015-08-09"`,
    `"team:ENG_PL:arsenal"`) -- this function does not itself resolve them.
    """

    if metric_granularity == "competition":
        if _blank(competition_code):
            return None
        return f"competition:{competition_code}"

    if metric_granularity == "team":
        if _blank(team_key):
            return None
        return team_key

    if metric_granularity == "match":
        if _blank(match_key):
            return None
        return match_key

    if metric_granularity == "team_match":
        if _blank(match_key) or _blank(team_key):
            return None
        return f"team-match:{match_key}:{team_key}"

    if metric_granularity == "player_appearance":
        if _blank(match_key) or _blank(player_key):
            return None
        return f"player-appearance:{match_key}:{player_key}"

    if metric_granularity == "player_match":
        if _blank(match_key) or _blank(player_key):
            return None
        return f"player-match:{match_key}:{player_key}"

    if metric_granularity == "player_season":
        if _blank(competition_code) or _blank(season_label) or _blank(player_key):
            return None
        return f"player-season:{competition_code}:{season_label}:{player_key}"

    if metric_granularity == "goalkeeper_match":
        if _blank(match_key) or _blank(player_key):
            return None
        return f"goalkeeper-match:{match_key}:{player_key}"

    if metric_granularity == "goalkeeper_season":
        if _blank(competition_code) or _blank(season_label) or _blank(player_key):
            return None
        return f"goalkeeper-season:{competition_code}:{season_label}:{player_key}"

    return None


# ---------------------------------------------------------------------------
# Team / match source-local index V2
# ---------------------------------------------------------------------------

# (source_code, provider_entity_id) -> resolved logical key, exactly like
# V0's `SourceLocalIndex` in `data_mesh/pipeline.py`.
SourceLocalIndexV2 = dict[tuple[str, str], str]


class IdentityConflictError(RuntimeError):
    """The same (source_code, provider_id) resolved to two different logical
    entities within one run -- never silently picked one."""


def _index_put(
    index: SourceLocalIndexV2, *, source_code: str, provider_id: str, logical_key: str
) -> None:
    existing_key = (source_code, provider_id)
    if existing_key in index and index[existing_key] != logical_key:
        raise IdentityConflictError(
            f"{source_code}:{provider_id} already resolved to {index[existing_key]!r}, "
            f"cannot also resolve to {logical_key!r} -- refusing to silently pick one"
        )
    index[existing_key] = logical_key


def build_team_index_v2(
    *,
    source_code: str,
    competition_code: str,
    team_names_by_provider_id: Mapping[str, str],
    into: SourceLocalIndexV2 | None = None,
) -> SourceLocalIndexV2:
    """Builds a `(source_code, provider_team_id) -> team logical key` index
    from strong evidence -- a provider-native team id mapped to that team's
    real name -- without requiring a `team.name` `NormalizedObservation`.

    `team_names_by_provider_id` is evidence the caller has already
    established (e.g. from a provider's own teams/players reference file,
    or -- for the certified Wyscout/StatsBomb adapters specifically -- from
    the guaranteed `"{match_id}:{team_id}"` composite `entity_source_id`
    shape those adapters emit, cross-referenced against the match-level
    `home_team_id`/`away_team_id` + team name each adapter's own upstream
    payload carries).

    Pass `into` to accumulate evidence from multiple batches (e.g. one call
    per fixture file) into a single shared index -- this is what makes a
    genuine identity conflict (the same provider team id evidenced under two
    different names across batches, a real data-quality signal) detectable
    at all: a single batch's own `Mapping` can never contain a duplicate key
    by construction. Raises `IdentityConflictError` the moment such a
    conflict is found -- never silently picks one.
    """

    index: SourceLocalIndexV2 = into if into is not None else {}
    for provider_id, name in team_names_by_provider_id.items():
        resolution = resolve_team(name=name, competition_code=competition_code)
        if resolution.status != "resolved" or resolution.logical_key is None:
            continue
        _index_put(
            index,
            source_code=source_code,
            provider_id=provider_id,
            logical_key=resolution.logical_key,
        )
    return index


def build_match_index_v2(
    *,
    source_code: str,
    match_keys_by_provider_id: Mapping[str, str],
    into: SourceLocalIndexV2 | None = None,
) -> SourceLocalIndexV2:
    """Builds a `(source_code, provider_match_id) -> match logical key`
    index from already-resolved match logical keys (e.g. the output of
    `data_mesh.pipeline.resolve_logical_key` for each real match
    observation). Pass `into` to accumulate across multiple batches, exactly
    like `build_team_index_v2`. Raises `IdentityConflictError` on a genuine
    conflict."""

    index: SourceLocalIndexV2 = into if into is not None else {}
    for provider_id, match_key in match_keys_by_provider_id.items():
        _index_put(index, source_code=source_code, provider_id=provider_id, logical_key=match_key)
    return index


def build_team_index_v2_from_observations(
    observations: Iterable[NormalizedObservation],
    *,
    competition_code: str,
    into: SourceLocalIndexV2 | None = None,
) -> SourceLocalIndexV2:
    """Builds a `(source_code, provider_team_id) -> team logical key` index
    directly from real `NormalizedObservation.entity_identity_hints` --
    `team_external_id`/`team_name` (team_match-scoped and `home_away`
    observations) and `home_team_external_id`/`home_team_name` +
    `away_team_external_id`/`away_team_name` (match-scoped observations).

    This is the primary V2 mechanism for the certified Wyscout/StatsBomb
    adapters (Block 20D.2 completion pass): it reads only
    `entity_identity_hints`, never `entity_source_id`'s composite
    `"{match_id}:{team_id}"` shape. Raises `IdentityConflictError` the
    moment the same `(source_code, provider_team_id)` is evidenced under
    two different names -- never silently picks one.
    """

    index: SourceLocalIndexV2 = into if into is not None else {}
    for obs in observations:
        hints = obs.entity_identity_hints
        for id_key, name_key in (
            ("team_external_id", "team_name"),
            ("home_team_external_id", "home_team_name"),
            ("away_team_external_id", "away_team_name"),
        ):
            provider_id = hints.get(id_key)
            name = hints.get(name_key)
            if not provider_id or not name:
                continue
            resolution = resolve_team(name=name, competition_code=competition_code)
            if resolution.status != "resolved" or resolution.logical_key is None:
                continue
            _index_put(
                index,
                source_code=obs.source_code,
                provider_id=provider_id,
                logical_key=resolution.logical_key,
            )
    return index


def build_match_index_v2_from_observations(
    observations: Iterable[NormalizedObservation],
    *,
    competition_code: str,
    team_index: SourceLocalIndexV2,
    into: SourceLocalIndexV2 | None = None,
) -> SourceLocalIndexV2:
    """Builds a `(source_code, provider_match_id) -> match logical key`
    index directly from real match-scoped observations' `entity_identity_
    hints` -- `match_external_id`, `home_team_external_id`/
    `away_team_external_id` (resolved via `team_index`, falling back to a
    direct name resolution when the index has no entry but the hint itself
    carries a name), `season_label`, and `kickoff_date`. Reuses V0's own
    pure `resolve_match()` -- never a second match-identity algorithm.
    Never touches `entity_source_id`. Raises `IdentityConflictError` on a
    genuine conflict.

    Each observation's raw `kickoff_date` hint is passed to `resolve_match()`
    as-is. Cross-source day-level date-tolerance canonicalization
    (`cluster_match_dates()`/`build_match_date_clusters()` in
    `data_mesh/pipeline.py`, the correct existing bounded-clustering
    primitive fixed in Block 20D.2) is NOT applied here -- wiring it in
    would require re-deriving the exact same `(competition_code,
    season_label, home_team_key, away_team_key)` grouping
    `build_match_date_clusters()` computes internally from `resolve_team()`
    name resolution, and this function's team resolution can instead come
    from the id-based `team_index`; getting that grouping to agree exactly
    without becoming a second, parallel clustering algorithm is real
    integration work, not a one-line change. Left as an explicit, known gap
    for Block 20D.4's pipeline/Reconciliation V2 wiring rather than risking
    a subtly-wrong clustering reimplementation here."""

    index: SourceLocalIndexV2 = into if into is not None else {}
    for obs in observations:
        if obs.entity_type != "match":
            continue
        hints = obs.entity_identity_hints
        match_id = hints.get("match_external_id")
        if not match_id:
            continue

        home_id = hints.get("home_team_external_id")
        home_key = team_index.get((obs.source_code, home_id)) if home_id else None
        if home_key is None and hints.get("home_team_name"):
            home_resolution = resolve_team(
                name=hints["home_team_name"], competition_code=competition_code
            )
            home_key = home_resolution.logical_key if home_resolution.status == "resolved" else None

        away_id = hints.get("away_team_external_id")
        away_key = team_index.get((obs.source_code, away_id)) if away_id else None
        if away_key is None and hints.get("away_team_name"):
            away_resolution = resolve_team(
                name=hints["away_team_name"], competition_code=competition_code
            )
            away_key = away_resolution.logical_key if away_resolution.status == "resolved" else None

        kickoff_date = parse_date(hints.get("kickoff_date"))
        season_label = normalize_season_label(hints.get("season_label", ""))
        # V0's `resolve_match()` does not itself guard against a blank
        # `season_label` (it would otherwise silently embed "" into an
        # apparently "resolved" logical key, e.g.
        # "match:ENG_PL::team:...:team:...:2018-05-13") -- guarded here,
        # at the V2 boundary, rather than changing V0's pure function.
        if _blank(season_label):
            continue
        resolution = resolve_match(
            competition_code=competition_code,
            season_label=season_label,
            home_team_key=home_key,
            away_team_key=away_key,
            kickoff_date=kickoff_date,
        )
        if resolution.status != "resolved" or resolution.logical_key is None:
            continue
        _index_put(
            index,
            source_code=obs.source_code,
            provider_id=match_id,
            logical_key=resolution.logical_key,
        )
    return index


def resolve_team_v2(
    *,
    source_code: str,
    provider_team_id: str,
    team_index: SourceLocalIndexV2,
) -> EntityResolution:
    """Resolves a certified V2 adapter's team-scoped observation using the
    V2 source-local index -- never the V0 `entity_type=="team",
    metric_name=="name"` bridging pattern, which certified adapters do not
    emit."""

    logical_key = team_index.get((source_code, provider_team_id))
    if logical_key is None:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type="team",
            confidence=0.0,
            reason="no V2 team-index entry for this (source_code, provider_team_id)",
        )
    return EntityResolution(
        status="resolved",
        logical_key=logical_key,
        entity_type="team",
        confidence=0.90,
        reason="V2 source-local team index",
    )


def resolve_match_v2(
    *,
    source_code: str,
    provider_match_id: str,
    match_index: SourceLocalIndexV2,
) -> EntityResolution:
    """Resolves a certified V2 adapter's match-scoped observation using the
    V2 source-local match index."""

    logical_key = match_index.get((source_code, provider_match_id))
    if logical_key is None:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type="match",
            confidence=0.0,
            reason="no V2 match-index entry for this (source_code, provider_match_id)",
        )
    return EntityResolution(
        status="resolved",
        logical_key=logical_key,
        entity_type="match",
        confidence=0.90,
        reason="V2 source-local match index",
    )


# ---------------------------------------------------------------------------
# Player crosswalk -- CONTRACT ONLY (Block 20D.2). No entries populated here.
# ---------------------------------------------------------------------------


class PlayerCrosswalkValidationError(ValueError):
    """A `PlayerCrosswalkEntry` or `PlayerTeamContextEvidence` was
    constructed without meeting the documented minimum evidence bar --
    never silently accepted with weaker evidence than the contract
    requires."""


def _require_non_blank(value: str, field_name: str, *, owner: str = "PlayerCrosswalkEntry") -> None:
    if not isinstance(value, str) or not value.strip():
        raise PlayerCrosswalkValidationError(
            f"{owner}.{field_name} must be a non-blank string, got {value!r}"
        )


@dataclass(frozen=True, slots=True)
class PlayerTeamContextEvidence:
    """One resolved team context a provider player id was evidenced under,
    plus the exact real shared matches that specific evidence rests on.

    A `PlayerCrosswalkEntry` holds one or more of these: exactly one for a
    player who never changed clubs within the overlap scope, more than one
    for a genuine mid-season transfer -- Block 20D.3's real diagnosed cases
    (Guidetti Celta Vigo->Alavés, Gálvez Eibar->Las Palmas, Moyà Atlético
    Madrid->Real Sociedad, Fuego Espanyol->Villarreal). Each context's own
    `shared_match_keys` are the matches that specifically evidence THAT
    team context -- never the pair's full match list -- so the match->team
    relationship is explicit and never positionally inferred.
    """

    team_context_key: str
    shared_match_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_blank(
            self.team_context_key, "team_context_key", owner="PlayerTeamContextEvidence"
        )
        if not self.shared_match_keys:
            raise PlayerCrosswalkValidationError(
                "PlayerTeamContextEvidence requires at least one non-blank shared_match_key "
                "-- a team context with zero match evidence is never valid"
            )
        seen: set[str] = set()
        for match_key in self.shared_match_keys:
            if not isinstance(match_key, str) or not match_key.strip():
                raise PlayerCrosswalkValidationError(
                    "PlayerTeamContextEvidence.shared_match_keys must contain only non-blank "
                    f"strings, got {match_key!r}"
                )
            if match_key in seen:
                # Fail fast rather than silently deduplicating: a duplicate
                # match key inside one team context means the caller's own
                # evidence-collection logic double-counted a match, a real
                # bug worth surfacing rather than masking.
                raise PlayerCrosswalkValidationError(
                    f"PlayerTeamContextEvidence.shared_match_keys contains a duplicate match "
                    f"key {match_key!r}"
                )
            seen.add(match_key)
        if self.shared_match_keys != tuple(sorted(self.shared_match_keys)):
            # Same contract style as PlayerCrosswalkEntry.team_context_evidence's
            # ordering check below: fail fast on a non-canonical order rather
            # than silently sorting inside this immutable object. Without
            # this, two logically identical evidence objects built from the
            # same real matches in a different collection order would
            # compare unequal (`("match:a", "match:b") != ("match:b",
            # "match:a")`), weakening `PlayerCrosswalk.add()`'s exact-
            # idempotence -- the same real pair could be rejected as a
            # spurious conflict merely because a caller enumerated its
            # matches in a different order.
            raise PlayerCrosswalkValidationError(
                "PlayerTeamContextEvidence.shared_match_keys must be in canonical ascending "
                "order -- callers must sort deterministically before construction, never rely "
                "on implicit collection order"
            )


@dataclass(frozen=True, slots=True)
class PlayerCrosswalkEntry:
    """One deterministic (source_code, provider_player_id) -> canonical
    logical player key link, with the audit evidence backing it.

    A crosswalk entry is never generated from name similarity alone. The
    minimum bar (Block 20D.1's design conclusion, exercised for real in
    Block 20D.3) is enforced here, at construction time, not merely
    documented: resolved team context + an exact deterministic normalized
    player name + at least one genuinely shared resolved match per team
    context. An entry that does not meet this bar cannot be constructed at
    all -- it is rejected immediately with `PlayerCrosswalkValidationError`,
    never stored and never later resolved with positive confidence.

    `team_context_evidence` supports N>=1 team contexts for the SAME real
    person (Block 20D.3's Option C): a genuine mid-season transfer produces
    more than one `PlayerTeamContextEvidence`, never a second registry
    entry and never a forced single-team choice that would silently drop
    or mis-attribute evidence. Contexts must be in canonical ascending
    `team_context_key` order (callers sort deterministically before
    constructing an entry -- this is validated, never silently re-sorted),
    contain no duplicate team context, and no shared match key may appear
    under two different team contexts (a single real match can never
    evidence one player under two different teams for the same provider
    pair).
    """

    source_code: str
    provider_player_id: str
    canonical_player_key: str
    normalized_name_used: str
    team_context_evidence: tuple[PlayerTeamContextEvidence, ...]
    corroborating_nationality: str | None = None
    corroborating_position: str | None = None

    def __post_init__(self) -> None:
        _require_non_blank(self.source_code, "source_code")
        _require_non_blank(self.provider_player_id, "provider_player_id")
        _require_non_blank(self.canonical_player_key, "canonical_player_key")
        _require_non_blank(self.normalized_name_used, "normalized_name_used")
        if not self.team_context_evidence:
            raise PlayerCrosswalkValidationError(
                "PlayerCrosswalkEntry requires at least one team_context_evidence entry "
                "-- an entry with zero team-context evidence is never valid"
            )
        for evidence in self.team_context_evidence:
            if not isinstance(evidence, PlayerTeamContextEvidence):
                raise PlayerCrosswalkValidationError(
                    "PlayerCrosswalkEntry.team_context_evidence must contain only "
                    f"PlayerTeamContextEvidence instances, got {evidence!r}"
                )
        team_keys = [evidence.team_context_key for evidence in self.team_context_evidence]
        if team_keys != sorted(team_keys):
            raise PlayerCrosswalkValidationError(
                "PlayerCrosswalkEntry.team_context_evidence must be in canonical ascending "
                "team_context_key order -- callers must sort deterministically before "
                "constructing an entry, never rely on implicit insertion order"
            )
        if len(set(team_keys)) != len(team_keys):
            raise PlayerCrosswalkValidationError(
                "PlayerCrosswalkEntry.team_context_evidence contains a duplicate "
                "team_context_key -- each team context must appear at most once"
            )
        match_to_team: dict[str, str] = {}
        for evidence in self.team_context_evidence:
            for match_key in evidence.shared_match_keys:
                existing_team = match_to_team.get(match_key)
                if existing_team is not None and existing_team != evidence.team_context_key:
                    raise PlayerCrosswalkValidationError(
                        f"shared match key {match_key!r} is claimed by more than one team "
                        f"context ({existing_team!r} and {evidence.team_context_key!r}) -- a "
                        "single real match can never evidence one player under two different "
                        "teams for the same provider pair"
                    )
                match_to_team[match_key] = evidence.team_context_key

    @property
    def team_context_keys(self) -> tuple[str, ...]:
        return tuple(evidence.team_context_key for evidence in self.team_context_evidence)

    @property
    def shared_match_keys(self) -> tuple[str, ...]:
        """Deterministic union of every context's matches, sorted. Derived
        from `team_context_evidence` alone -- never a second stored source
        of truth -- and never double-counted (a match key can belong to at
        most one context, enforced in `__post_init__`)."""

        result: set[str] = set()
        for evidence in self.team_context_evidence:
            result.update(evidence.shared_match_keys)
        return tuple(sorted(result))

    @property
    def shared_match_count(self) -> int:
        return len(self.shared_match_keys)


class PlayerCrosswalkConflictError(RuntimeError):
    """Two crosswalk entries disagree about a (source_code,
    provider_player_id)'s canonical player, OR the same key was re-added
    with different evidence -- never silently picked one, never silently
    overwritten with weaker/different evidence."""


@dataclass
class PlayerCrosswalk:
    """A small, in-memory, pure crosswalk registry. Not a database table --
    Block 20D.2 defines the contract; a future block decides how (or
    whether) entries are persisted.

    `entries` is keyed by `(source_code, provider_player_id)`. Only ever
    populated by explicit, validated `PlayerCrosswalkEntry` objects the
    caller constructed -- this class never invents or infers one. Re-adding
    an entry for a key that already has one is an idempotent no-op ONLY
    when the new entry is exactly equal to the existing one (every field,
    not just `canonical_player_key`) -- prefer this simple exact-identity
    contract over a merge policy until a real Block 20D.3 need justifies
    one."""

    entries: dict[tuple[str, str], PlayerCrosswalkEntry] = field(default_factory=dict)

    def add(self, entry: PlayerCrosswalkEntry) -> None:
        key = (entry.source_code, entry.provider_player_id)
        existing = self.entries.get(key)
        if existing is not None and existing != entry:
            raise PlayerCrosswalkConflictError(
                f"{key} already has a crosswalk entry with different evidence "
                f"({existing!r}); refusing to silently overwrite it with {entry!r} "
                f"-- add() only accepts an exact repeat of already-stored evidence"
            )
        self.entries[key] = entry

    def would_conflict(self, entry: PlayerCrosswalkEntry) -> bool:
        """Pure preflight: True if `add(entry)` would raise
        `PlayerCrosswalkConflictError` right now -- never mutates the
        registry. Lets a caller that must insert more than one related
        entry atomically (e.g. both sides of a validated two-provider
        pair) check every entry first and only commit if none would
        conflict, rather than adding some and discovering a conflict on a
        later one, which would leave a one-sided entry for a pair that
        failed validation as a whole."""

        key = (entry.source_code, entry.provider_player_id)
        existing = self.entries.get(key)
        return existing is not None and existing != entry

    def lookup(self, *, source_code: str, provider_player_id: str) -> PlayerCrosswalkEntry | None:
        return self.entries.get((source_code, provider_player_id))


def resolve_player_v2(
    *,
    source_code: str,
    provider_player_id: str,
    crosswalk: PlayerCrosswalk,
) -> EntityResolution:
    """Resolves a player using ONLY a validated crosswalk entry. No name-only
    global resolution is ever performed here -- `player:<normalized-name>`
    is never constructed as a canonical identity by this function. Without a
    matching crosswalk entry, the player stays UNRESOLVED, exactly like V0's
    `resolve_player()`."""

    entry = crosswalk.lookup(source_code=source_code, provider_player_id=provider_player_id)
    if entry is None:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type="player",
            confidence=0.0,
            reason="no validated crosswalk entry for this (source_code, provider_player_id)",
        )
    # Confidence scales modestly with corroborating shared-match evidence --
    # a single shared match is the minimum bar (Block 20D.1's conclusion),
    # never zero evidence, and repeated shared matches raise confidence
    # without ever reaching V0's `agreed`-tier ceiling on their own.
    confidence = min(0.85, 0.55 + 0.10 * max(0, entry.shared_match_count - 1))
    return EntityResolution(
        status="resolved",
        logical_key=entry.canonical_player_key,
        entity_type="player",
        confidence=confidence,
        reason=f"validated player crosswalk entry ({entry.shared_match_count} shared match(es))",
    )
