"""Shared resolve-then-reconcile orchestration for Data Mesh jobs.

Extracted from the Block 13 Data Mesh PoC job so the Zero-Cost Coverage Lab
job (Block 15) can reconcile TheSportsDB against Football-Data.co.uk using
the exact same entity-resolution/date-tolerance/grouping pipeline as the
original PoC used for TheSportsDB against OpenLigaDB -- one implementation,
not a parallel one, regardless of which sources are being combined.
"""

from __future__ import annotations

import dataclasses
from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any

from football_intelligence.data_mesh.comparability_policy import (
    MetricComparabilityPolicy,
    SourceRef,
    comparability_policy,
)
from football_intelligence.data_mesh.entity_resolution import (
    cluster_match_dates,
    resolve_competition,
    resolve_match,
    resolve_player,
    resolve_team,
)
from football_intelligence.data_mesh.entity_resolution_v2 import (
    PlayerCrosswalk,
    SourceLocalIndexV2,
    build_match_index_v2_from_observations,
    build_team_index_v2_from_observations,
    logical_fact_key,
    resolve_match_v2,
    resolve_player_v2,
    resolve_team_v2,
)
from football_intelligence.data_mesh.models import (
    OBJECTIVE_SOURCE_TYPES,
    EntityResolution,
    EntityType,
    NormalizedObservation,
    ReconciliationDecision,
    ReconciliationStatus,
)
from football_intelligence.data_mesh.reconciliation import MODEL_VERSION_V2, reconcile_metric
from football_intelligence.data_mesh.timeparse import normalize_season_label, parse_date
from football_intelligence.metric_catalog.types import MetricGranularity
from football_intelligence.normalization.models import TeamLineupRecord, TeamMatchStatsRecord

REPORT_EXAMPLE_LIMIT = 10

# (competition_code, season_label, home_team_key, away_team_key) -> per-group
# kickoff-date -> canonical clustered date.
MatchGroupKey = tuple[str, str, str, str]
MatchDateClusters = Mapping[MatchGroupKey, Mapping[date, date]]

# Source-local (source_code, provider-scoped id) -> resolved canonical
# logical key, built once per reconciliation run from the observations that
# actually carry full identity (team `name` rows, match rows) so a
# team-match-scoped stat observation -- which only ever carries a
# provider-scoped team/match id, never a team name or full match identity --
# can resolve deterministically without inventing a second resolution path.
SourceLocalIndex = Mapping[tuple[str, str], str]

# `team.name` is a TEAM-IDENTITY property (one fact per team, ever). Every
# other metric TheSportsDB's event-stats endpoint or Football-Data.co.uk's
# CSV reports for an `entity_type == "team"` observation -- shots, cards,
# fouls, formation, etc. (`TeamMatchStatsRecord`/`TeamLineupRecord` fields)
# -- is a TEAM-MATCH-SCOPED fact: Bayern's `shots_total` against Leipzig and
# Bayern's `shots_total` against Dortmund are two different real facts, not
# two observations of the same one. Grouping both under the bare team
# identity would silently merge them into a false "conflict". Derived from
# the DTOs themselves (never a hand-maintained duplicate list) so it can
# never drift.
_TEAM_ENTITY_LINK_FIELDS = frozenset({"match_external_id", "team_external_id"})


def _team_match_scoped_metric_names() -> frozenset[str]:
    names: set[str] = set()
    for dataclass_type in (TeamMatchStatsRecord, TeamLineupRecord):
        names.update(
            field.name
            for field in dataclasses.fields(dataclass_type)
            if field.name not in _TEAM_ENTITY_LINK_FIELDS
        )
    return frozenset(names)


TEAM_MATCH_SCOPED_METRIC_NAMES: frozenset[str] = _team_match_scoped_metric_names()


def resolve_logical_key(
    observation: NormalizedObservation,
    *,
    match_date_clusters: MatchDateClusters,
    team_index: SourceLocalIndex | None = None,
    match_index: SourceLocalIndex | None = None,
) -> EntityResolution:
    hints = observation.entity_identity_hints

    if observation.entity_type == "competition":
        return resolve_competition(
            source_code=observation.source_code,
            external_id=observation.entity_source_id,
        )

    competition_resolution = resolve_competition(
        source_code=observation.source_code,
        external_id=hints.get("competition_external_id", ""),
    )
    if competition_resolution.status != "resolved" or competition_resolution.logical_key is None:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type=observation.entity_type,
            confidence=0.0,
            reason="competition identity not resolved",
        )
    competition_code = competition_resolution.logical_key.removeprefix("competition:")

    if observation.entity_type == "team":
        if observation.metric_name in TEAM_MATCH_SCOPED_METRIC_NAMES:
            return _resolve_team_match_scoped(
                observation, team_index=team_index or {}, match_index=match_index or {}
            )
        return resolve_team(name=hints.get("name", ""), competition_code=competition_code)

    if observation.entity_type == "match":
        season_label = normalize_season_label(hints.get("season_label", ""))
        home_resolution = resolve_team(
            name=hints.get("home_team_name", ""), competition_code=competition_code
        )
        away_resolution = resolve_team(
            name=hints.get("away_team_name", ""), competition_code=competition_code
        )
        kickoff_date = parse_date(hints.get("kickoff_date"))
        canonical_date = kickoff_date
        if (
            kickoff_date is not None
            and home_resolution.logical_key is not None
            and away_resolution.logical_key is not None
        ):
            group_key = (
                competition_code,
                season_label,
                home_resolution.logical_key,
                away_resolution.logical_key,
            )
            canonical_date = match_date_clusters.get(group_key, {}).get(kickoff_date, kickoff_date)
        return resolve_match(
            competition_code=competition_code,
            season_label=season_label,
            home_team_key=home_resolution.logical_key,
            away_team_key=away_resolution.logical_key,
            kickoff_date=canonical_date,
        )

    return resolve_player(
        normalized_name="",
        date_of_birth=None,
        nationality_code=None,
        team_context_key=None,
    )


def _resolve_team_match_scoped(
    observation: NormalizedObservation,
    *,
    team_index: SourceLocalIndex,
    match_index: SourceLocalIndex,
) -> EntityResolution:
    match_source_id = observation.entity_identity_hints.get("match_external_id", "")
    team_key = team_index.get((observation.source_code, observation.entity_source_id))
    match_key = (
        match_index.get((observation.source_code, match_source_id)) if match_source_id else None
    )

    if team_key is None or match_key is None:
        return EntityResolution(
            status="unresolved",
            logical_key=None,
            entity_type="team",
            confidence=0.0,
            reason=(
                "team-match identity requires both a resolved team and a resolved match "
                "via the source-local (source_code, id) bridging index"
            ),
        )
    return EntityResolution(
        status="resolved",
        logical_key=f"team-match:{match_key}:{team_key}",
        entity_type="team",
        confidence=0.85,
        reason="team+match identity via source-local bridging index",
    )


def build_source_local_indexes(
    observations: list[NormalizedObservation],
    *,
    match_date_clusters: MatchDateClusters,
) -> tuple[SourceLocalIndex, SourceLocalIndex]:
    """Bridge provider-scoped ids to canonical logical keys.

    Built from the observations that already carry full identity -- team
    `name` rows (`entity_source_id` = the provider's own team id) and match
    rows (`entity_source_id` = the provider's own match id, with full
    home/away/date identity hints) -- so a team-match-scoped stat
    observation from the SAME provider, which only ever carries those same
    provider-scoped ids, can resolve without any provider-specific
    resolution logic of its own or any fuzzy/invented matching.
    """

    team_index: dict[tuple[str, str], str] = {}
    match_index: dict[tuple[str, str], str] = {}
    for observation in observations:
        if observation.entity_type == "team" and observation.metric_name == "name":
            resolution = resolve_logical_key(observation, match_date_clusters=match_date_clusters)
            if resolution.status == "resolved" and resolution.logical_key is not None:
                team_index[(observation.source_code, observation.entity_source_id)] = (
                    resolution.logical_key
                )
        elif observation.entity_type == "match":
            resolution = resolve_logical_key(observation, match_date_clusters=match_date_clusters)
            if resolution.status == "resolved" and resolution.logical_key is not None:
                match_index[(observation.source_code, observation.entity_source_id)] = (
                    resolution.logical_key
                )
    return team_index, match_index


def build_match_date_clusters(
    observations: list[NormalizedObservation],
) -> MatchDateClusters:
    """Precompute deterministic kickoff-date clusters per resolved match group.

    `resolve_match()` stays a pure function of its exact inputs (easy to
    test/audit), so tolerance is applied here instead: two providers
    reporting the same real fixture on adjacent dates must still converge on
    one logical match identity, and the canonical date chosen must not
    depend on which provider's observation is processed first.
    """

    dates_by_group: dict[MatchGroupKey, set[date]] = defaultdict(set)
    for observation in observations:
        if observation.entity_type != "match":
            continue
        hints = observation.entity_identity_hints
        competition_resolution = resolve_competition(
            source_code=observation.source_code,
            external_id=hints.get("competition_external_id", ""),
        )
        if (
            competition_resolution.status != "resolved"
            or competition_resolution.logical_key is None
        ):
            continue
        competition_code = competition_resolution.logical_key.removeprefix("competition:")
        season_label = normalize_season_label(hints.get("season_label", ""))
        home_resolution = resolve_team(
            name=hints.get("home_team_name", ""), competition_code=competition_code
        )
        away_resolution = resolve_team(
            name=hints.get("away_team_name", ""), competition_code=competition_code
        )
        kickoff_date = parse_date(hints.get("kickoff_date"))
        if (
            kickoff_date is None
            or home_resolution.logical_key is None
            or away_resolution.logical_key is None
        ):
            continue
        group_key = (
            competition_code,
            season_label,
            home_resolution.logical_key,
            away_resolution.logical_key,
        )
        dates_by_group[group_key].add(kickoff_date)

    return {group_key: cluster_match_dates(dates) for group_key, dates in dates_by_group.items()}


def resolve_and_reconcile(
    observations: list[NormalizedObservation],
) -> tuple[list[ReconciliationDecision], dict[str, Any]]:
    match_date_clusters = build_match_date_clusters(observations)
    team_index, match_index = build_source_local_indexes(
        observations, match_date_clusters=match_date_clusters
    )
    grouped: dict[tuple[str, EntityType, str], list[NormalizedObservation]] = defaultdict(list)
    unresolved_examples: list[dict[str, str]] = []
    resolved_count = 0
    unresolved_count = 0

    for observation in observations:
        resolution = resolve_logical_key(
            observation,
            match_date_clusters=match_date_clusters,
            team_index=team_index,
            match_index=match_index,
        )
        if resolution.status != "resolved" or resolution.logical_key is None:
            unresolved_count += 1
            if len(unresolved_examples) < REPORT_EXAMPLE_LIMIT:
                unresolved_examples.append(
                    {
                        "source_code": observation.source_code,
                        "entity_type": observation.entity_type,
                        "entity_source_id": observation.entity_source_id,
                        "reason": resolution.reason,
                    }
                )
            continue
        resolved_count += 1
        grouped[(resolution.logical_key, observation.entity_type, observation.metric_name)].append(
            observation
        )

    decisions = [
        reconcile_metric(
            items,
            logical_entity_key=key,
            entity_type=entity_type,
            metric_name=metric_name,
        )
        for (key, entity_type, metric_name), items in sorted(grouped.items())
    ]

    overlap_count = sum(1 for decision in decisions if decision.source_count >= 2)

    return decisions, {
        "resolved_observation_count": resolved_count,
        "unresolved_observation_count": unresolved_count,
        "unresolved_identity_examples": unresolved_examples,
        "overlap_count": overlap_count,
    }


def coverage_by_source(observations: list[NormalizedObservation]) -> dict[str, dict[str, int]]:
    coverage: dict[str, dict[str, int]] = defaultdict(dict)
    for observation in observations:
        key = f"{observation.entity_type}.{observation.metric_name}"
        per_source = coverage[observation.source_code]
        per_source[key] = per_source.get(key, 0) + 1
    return dict(coverage)


# ---------------------------------------------------------------------------
# Reconciliation V2 (Block 20D.4) -- purely additive. `resolve_and_
# reconcile()` above (V0) is completely untouched: every existing caller
# (the ENG_PL 2025/26 Football-Data.co.uk x OpenFootball regression, the
# Zero-Cost Coverage Lab) keeps its exact current behavior and MODEL_VERSION.
#
# `resolve_and_reconcile_v2()` is a new, separate entry point for the two
# certified historical/deep providers (Wyscout Open, StatsBomb Open) that
# V0 cannot correctly resolve (neither adapter emits a `team.name`
# observation V0's team bridging requires, and V0's `resolve_player()` is
# an always-UNRESOLVED interface-only contract). It composes the Block
# 20D.2/20D.3 V2 primitives -- id-based team/match indexes, the player
# crosswalk, granularity-safe fact identity -- with the SAME `reconcile_
# metric()` value-comparison core V0 uses; it does not duplicate that
# logic, only supplies V2-specific identity/grouping/gating around it.
# ---------------------------------------------------------------------------

# Fixed, deliberately non-scaling confidence for a decision where no value
# comparison was attempted at all (`not_comparable`/`methodology_pending`).
# Never confused with `reconciliation.CONFLICT_CONFIDENCE` (0.20), which
# asserts the sources WERE compared and genuinely disagree -- these
# decisions assert nothing about agreement or disagreement, only that no
# reviewed policy permits a comparison to be attempted.
_POLICY_GATED_CONFIDENCE = 0.0


def _resolve_fact_key_v2(
    observation: NormalizedObservation,
    *,
    competition_code: str,
    team_index: SourceLocalIndexV2,
    match_index: SourceLocalIndexV2,
    crosswalk: PlayerCrosswalk,
) -> tuple[str | None, str]:
    """Resolves one certified V2 observation's granularity-scoped logical
    fact key via `entity_resolution_v2.logical_fact_key()`, deriving
    whichever of match/team/player identity that specific granularity
    requires -- via `resolve_match_v2()`/`resolve_team_v2()` (id-based V2
    indexes) and `resolve_player_v2()` (the injected `PlayerCrosswalk`),
    never `entity_source_id` parsing and never name-only player matching.
    Returns `(None, reason)` when required context is missing or does not
    resolve -- never a degraded/partial key."""

    granularity = observation.metric_granularity
    if granularity is None:
        return None, "missing metric_granularity"

    hints = observation.entity_identity_hints
    season_label = normalize_season_label(hints.get("season_label", ""))

    match_key: str | None = None
    if granularity in (
        "match",
        "team_match",
        "player_appearance",
        "player_match",
        "goalkeeper_match",
    ):
        match_id = hints.get("match_external_id")
        if match_id:
            match_resolution = resolve_match_v2(
                source_code=observation.source_code,
                provider_match_id=match_id,
                match_index=match_index,
            )
            match_key = match_resolution.logical_key

    team_key: str | None = None
    if granularity in ("team", "team_match"):
        team_id = hints.get("team_external_id")
        if team_id:
            team_resolution = resolve_team_v2(
                source_code=observation.source_code,
                provider_team_id=team_id,
                team_index=team_index,
            )
            team_key = team_resolution.logical_key

    player_key: str | None = None
    if granularity in (
        "player_appearance",
        "player_match",
        "player_season",
        "goalkeeper_match",
        "goalkeeper_season",
    ):
        player_id = hints.get("player_external_id")
        if player_id:
            player_resolution = resolve_player_v2(
                source_code=observation.source_code,
                provider_player_id=player_id,
                crosswalk=crosswalk,
            )
            player_key = player_resolution.logical_key

    fact_key = logical_fact_key(
        metric_granularity=granularity,
        competition_code=competition_code,
        season_label=season_label,
        match_key=match_key,
        team_key=team_key,
        player_key=player_key,
    )
    if fact_key is None:
        return None, (
            f"required V2 identity context unresolved for granularity={granularity!r} "
            f"(match_key={match_key!r}, team_key={team_key!r}, player_key={player_key!r})"
        )
    return fact_key, ""


def _semantic_versions_by_source(
    objective: list[NormalizedObservation],
) -> tuple[dict[str, str], str | None]:
    """Derives one `semantic_version` per `source_code` from a group's
    objective observations. If a single source appears with more than one
    DISTINCT `semantic_version` within the same resolved fact group -- a
    real, if unexpected, batch-inconsistency signal (e.g. observations
    ingested by two different adapter code versions mixed into one run) --
    returns a non-None reason and an unreliable mapping the caller must
    not use, per the requirement to fail closed rather than silently pick
    one version."""

    versions_by_source: dict[str, set[str]] = defaultdict(set)
    for item in objective:
        versions_by_source[item.source_code].add(item.semantic_version)
    inconsistent = {
        source: sorted(versions)
        for source, versions in versions_by_source.items()
        if len(versions) > 1
    }
    if inconsistent:
        return {}, f"inconsistent semantic_version within one source in this group: {inconsistent}"
    return {source: next(iter(versions)) for source, versions in versions_by_source.items()}, None


def _build_policy_gated_decision(
    *,
    logical_entity_key: str,
    entity_type: EntityType,
    metric_name: str,
    metric_granularity: MetricGranularity,
    status: ReconciliationStatus,
    objective: list[NormalizedObservation],
    reason: str,
    policy: MetricComparabilityPolicy | None,
    now: datetime,
) -> ReconciliationDecision:
    """Constructs a `not_comparable`/`methodology_pending` decision directly
    -- WITHOUT calling `reconcile_metric()` -- because no value comparison
    was attempted: a comparability policy blocked it (`not_comparable`), no
    reviewed policy exists yet (`methodology_pending`), the group's
    per-source semantic versions were inconsistent, or the group has more
    than 2 sources (N>2-source semantics are out of scope for Block 20D.4).
    `candidate_value` is always `None` -- equal values across sources never
    substitute for an actual reviewed comparability claim. Raw values and
    full provenance are preserved in `evidence` for audit."""

    values_by_source: dict[str, object] = {item.source_code: item.value for item in objective}
    semantic_versions_by_source = {item.source_code: item.semantic_version for item in objective}
    participating_sources = tuple(sorted(values_by_source))
    evidence: dict[str, object] = {
        "values_by_source": values_by_source,
        "semantic_versions_by_source": semantic_versions_by_source,
        "reason": reason,
        "policy_explicitly_matched": policy is not None,
        "policy_comparison_mode": policy.comparison_mode if policy is not None else None,
        "policy_rationale": policy.rationale if policy is not None else None,
    }
    return ReconciliationDecision(
        logical_entity_key=logical_entity_key,
        entity_type=entity_type,
        metric_name=metric_name,
        candidate_value=None,
        status=status,
        confidence=_POLICY_GATED_CONFIDENCE,
        winning_source_code=None,
        participating_sources=participating_sources,
        source_count=len(participating_sources),
        evidence=evidence,
        model_version=MODEL_VERSION_V2,
        calculated_at=now,
        metric_granularity=metric_granularity,
    )


def resolve_and_reconcile_v2(
    observations: list[NormalizedObservation],
    *,
    competition_code: str,
    crosswalk: PlayerCrosswalk,
    calculated_at: datetime | None = None,
) -> tuple[list[ReconciliationDecision], dict[str, Any]]:
    """Reconciliation V2 entry point (Block 20D.4) for certified V2 adapter
    observations (Wyscout Open, StatsBomb Open) -- granularity-safe,
    id-based V2 entity resolution, an explicitly injected `PlayerCrosswalk`
    (never a global singleton, never name-only resolution), bounded
    cross-source date-tolerance clustering, and a provider-pair +
    semantic-version-scoped comparability policy gate:

    - 1 (or 0) objective source in a resolved fact group -> `reconcile_
      metric()` (`single_source`/`unresolved`) -- a comparability policy is
      never consulted, because no cross-source comparison is being
      attempted at all. A single-source observation is still valid audit
      evidence regardless of whether that metric happens to be
      `not_comparable`/`methodology_pending` for this provider pair.
    - Exactly 2 objective sources -> the comparability policy gates value
      comparison: `exact` -> `reconcile_metric()` (real `agreed`/
      `conflict`); an explicit `not_comparable` policy, an absent policy,
      or inconsistent per-source semantic versions within the group ->
      a policy-gated decision (`not_comparable`/`methodology_pending`,
      `candidate_value=None`), never a value comparison.
    - More than 2 objective sources -> `methodology_pending` unconditionally
      (N>2-source comparison semantics are explicitly out of scope for this
      block -- no policy lookup is attempted).

    A certified observation reaching this function with `metric_
    granularity=None` is treated as a diagnostic failure (counted in
    `missing_metric_granularity_count`, excluded from every group) rather
    than silently folded into a legacy-shaped group -- V2 reconciliation
    never guesses a missing granularity.

    Does not replace or redirect `resolve_and_reconcile()` -- V0 sources
    keep using that entry point, unmodified, with their existing
    `MODEL_VERSION`."""

    now = calculated_at or datetime.now(UTC)

    # Bounded date-tolerance clustering (Block 20D.2's fix, reused
    # unchanged -- no second clustering algorithm): computed once over the
    # whole batch exactly like V0 does, then threaded into the V2 match
    # index below so two providers reporting the same real fixture on
    # adjacent dates still converge on one logical match identity.
    match_date_clusters = build_match_date_clusters(observations)

    team_index: SourceLocalIndexV2 = {}
    build_team_index_v2_from_observations(
        observations, competition_code=competition_code, into=team_index
    )

    match_index: SourceLocalIndexV2 = {}
    build_match_index_v2_from_observations(
        observations,
        competition_code=competition_code,
        team_index=team_index,
        into=match_index,
        match_date_clusters=match_date_clusters,
    )

    grouped: dict[tuple[str, str, MetricGranularity], list[NormalizedObservation]] = defaultdict(
        list
    )
    unresolved_examples: list[dict[str, str]] = []
    resolved_count = 0
    unresolved_count = 0
    missing_granularity_count = 0

    for observation in observations:
        if observation.metric_granularity is None:
            missing_granularity_count += 1
            if len(unresolved_examples) < REPORT_EXAMPLE_LIMIT:
                unresolved_examples.append(
                    {
                        "source_code": observation.source_code,
                        "entity_type": observation.entity_type,
                        "entity_source_id": observation.entity_source_id,
                        "metric_name": observation.metric_name,
                        "reason": "missing metric_granularity for V2 reconciliation",
                    }
                )
            continue

        fact_key, reason = _resolve_fact_key_v2(
            observation,
            competition_code=competition_code,
            team_index=team_index,
            match_index=match_index,
            crosswalk=crosswalk,
        )
        if fact_key is None:
            unresolved_count += 1
            if len(unresolved_examples) < REPORT_EXAMPLE_LIMIT:
                unresolved_examples.append(
                    {
                        "source_code": observation.source_code,
                        "entity_type": observation.entity_type,
                        "entity_source_id": observation.entity_source_id,
                        "metric_name": observation.metric_name,
                        "reason": reason,
                    }
                )
            continue

        resolved_count += 1
        grouped[(fact_key, observation.metric_name, observation.metric_granularity)].append(
            observation
        )

    decisions: list[ReconciliationDecision] = []
    for (fact_key, metric_name, granularity), items in sorted(grouped.items()):
        entity_type = items[0].entity_type
        objective = [item for item in items if item.source_type in OBJECTIVE_SOURCE_TYPES]
        distinct_sources = sorted({item.source_code for item in objective})
        source_count = len(distinct_sources)

        if source_count <= 1:
            # No cross-source comparison is being attempted -- comparability
            # policy is never consulted. `reconcile_metric()` itself already
            # handles both the 1-source (`single_source`) and 0-source
            # (`unresolved`) cases correctly.
            decisions.append(
                reconcile_metric(
                    items,
                    logical_entity_key=fact_key,
                    entity_type=entity_type,
                    metric_name=metric_name,
                    metric_granularity=granularity,
                    model_version=MODEL_VERSION_V2,
                    calculated_at=now,
                )
            )
            continue

        if source_count > 2:
            decisions.append(
                _build_policy_gated_decision(
                    logical_entity_key=fact_key,
                    entity_type=entity_type,
                    metric_name=metric_name,
                    metric_granularity=granularity,
                    status="methodology_pending",
                    objective=objective,
                    reason=(
                        f"{source_count} sources present; N>2-source comparison semantics "
                        "are out of scope for Block 20D.4 (one certified two-provider pair only)"
                    ),
                    policy=None,
                    now=now,
                )
            )
            continue

        # Exactly 2 objective sources: derive canonical (source_code,
        # semantic_version) refs and gate on the reviewed comparability
        # policy for this exact provider-pair/semantic-version/metric.
        semantic_version_by_source, inconsistency_reason = _semantic_versions_by_source(objective)
        if inconsistency_reason is not None:
            decisions.append(
                _build_policy_gated_decision(
                    logical_entity_key=fact_key,
                    entity_type=entity_type,
                    metric_name=metric_name,
                    metric_granularity=granularity,
                    status="methodology_pending",
                    objective=objective,
                    reason=inconsistency_reason,
                    policy=None,
                    now=now,
                )
            )
            continue

        source_a = SourceRef(
            source_code=distinct_sources[0],
            semantic_version=semantic_version_by_source[distinct_sources[0]],
        )
        source_b = SourceRef(
            source_code=distinct_sources[1],
            semantic_version=semantic_version_by_source[distinct_sources[1]],
        )
        policy = comparability_policy(
            source_a, source_b, metric_name=metric_name, metric_granularity=granularity
        )

        if policy is not None and policy.comparison_mode == "exact":
            decisions.append(
                reconcile_metric(
                    items,
                    logical_entity_key=fact_key,
                    entity_type=entity_type,
                    metric_name=metric_name,
                    metric_granularity=granularity,
                    model_version=MODEL_VERSION_V2,
                    calculated_at=now,
                )
            )
            continue

        if policy is not None and policy.comparison_mode == "not_comparable":
            decisions.append(
                _build_policy_gated_decision(
                    logical_entity_key=fact_key,
                    entity_type=entity_type,
                    metric_name=metric_name,
                    metric_granularity=granularity,
                    status="not_comparable",
                    objective=objective,
                    reason=policy.rationale,
                    policy=policy,
                    now=now,
                )
            )
            continue

        # policy is None (no reviewed entry for this exact provider-pair /
        # semantic-version / metric / granularity) OR an explicit
        # methodology_pending entry -- both fail closed identically.
        decisions.append(
            _build_policy_gated_decision(
                logical_entity_key=fact_key,
                entity_type=entity_type,
                metric_name=metric_name,
                metric_granularity=granularity,
                status="methodology_pending",
                objective=objective,
                reason=(
                    policy.rationale
                    if policy is not None
                    else "no reviewed comparability policy for this provider-pair/"
                    "semantic-version/metric/granularity combination"
                ),
                policy=policy,
                now=now,
            )
        )

    return decisions, {
        "resolved_observation_count": resolved_count,
        "unresolved_observation_count": unresolved_count,
        "missing_metric_granularity_count": missing_granularity_count,
        "unresolved_identity_examples": unresolved_examples,
    }
