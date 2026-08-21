"""Provider-pair, semantic-version-scoped metric comparability policy (Block 20D.4).

Block 20D.3's real Wyscout Open x StatsBomb Open ESP_LL 2017/18 overlap
inventory found 65 exact `(metric_name, metric_granularity)` identities both
adapters emit -- but "the same catalog identity" does not by itself prove
"the same real-world measurement". A dedicated real-data comparability audit
(diagnosis-only, not committed) measured actual value agreement across the
36 shared matches / 434 crosswalk-resolved player pairs and found three
genuinely different situations even among identically-named, identically-
granular metrics:

- Some identities agree exactly on every real paired entity, backed by
  strong semantic evidence in `docs/WYSCOUT_METRIC_MAPPING.md` /
  `docs/STATSBOMB_METRIC_MAPPING.md` (native score fields, explicitly
  verified goal-reconciliation rules, lineup-file-authoritative
  participation) -- these are `exact`.
- Some identities disagree on the overwhelming majority of real paired
  entities, with a large and/or systematically one-directional magnitude
  (e.g. `passes_total`/`passes_accurate` -- a real sampled pair was 253 vs
  291 passes for the same team in the same match) -- a genuine, known
  provider-methodology divergence, not a data defect. These are
  `not_comparable`.
- Everything else -- including the 25 identities that showed high-but-not-
  perfect empirical agreement (a real numeric-tolerance reconciliation
  question explicitly deferred to Block 20D.5), 6 rare-discipline-event
  identities (`penalties_attempted`, `penalty_goals`, `penalties_missed`,
  `red_cards`, `second_yellow_cards`) whose 100% empirical agreement rested
  on only 1-6 real positive examples in this sample (too thin to certify
  `exact` even though nothing contradicts it), and representational (not
  factual) mismatches like `status`'s vocabulary or `kickoff_at`'s
  timezone offset -- is `methodology_pending`: real evidence review has not
  yet produced (or has not yet had enough real evidence to produce) a
  reviewed policy.

## Why this is scoped by provider PAIR, not just metric identity

Comparability is a claim about how two *specific* providers' event-log
methodologies relate to each other for one metric -- it says nothing about
a third provider's methodology. A policy entry here is only ever consulted
for the exact `(source_code, semantic_version)` pair it was reviewed
against; a different provider pair (even one that also emits the identical
catalog identity) has zero entries and therefore fails closed to
`methodology_pending` by construction, never by a runtime "is this the
right pair" check that could be forgotten.

## Why this is ALSO scoped by each source's `semantic_version`

An adapter's `SEMANTIC_VERSION` bump (e.g. Wyscout `v0.1 -> v0.2`, Block
20D.2's micro-audit pass) means observable emission semantics changed. A
comparability policy reviewed against `wyscout-open-v0.2`/
`statsbomb-open-v0.4`'s real output says nothing about whether a future
`wyscout-open-v0.3` still agrees the same way -- so every entry is keyed on
the exact semantic versions its evidence was gathered against.

**Those versions are pinned LITERAL string constants
(`WYSCOUT_CERTIFIED_POLICY_VERSION`, `STATSBOMB_CERTIFIED_POLICY_VERSION`
below), never imported/aliased from either adapter's live `SEMANTIC_
VERSION` constant.** Building the registry's own `SourceRef`s from a live
import would be exactly backwards: re-importing this module after a future
adapter version bump would silently carry the OLD, already-reviewed
policies forward onto the NEW, never-reviewed version -- the opposite of
what "semantic-version-scoped" is supposed to guarantee. Pinning literals
instead means the registry never moves on its own: a real observation's
own `semantic_version` (read from the observation itself at reconciliation
time -- see `pipeline.resolve_and_reconcile_v2()`'s `_semantic_versions_
by_source()`) is what changes the moment an adapter is bumped, and it
simply stops matching these fixed pins -- falling through to `methodology_
pending` -- until a human explicitly reviews the new version's real output
and updates the pin as a deliberate, reviewed action. The live `SEMANTIC_
VERSION` constants may still be imported elsewhere (e.g. a test asserting
the current pin still matches, as an early warning the moment someone
bumps a version without re-certifying) but must never feed the registry
itself.

## What this module deliberately does NOT do

No numeric tolerance, no `tolerated_agreement` status, no averaging, no
approximate-disagreement winner selection, no N>2-provider comparison
semantics, no inference from one provider pair to another. All of that is
explicitly deferred to Block 20D.5 or later -- see each identity's
`rationale` below for why it is or is not certified `exact` here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from football_intelligence.data_mesh.adapters.statsbomb_open import (
    SOURCE_CODE as STATSBOMB_OPEN_SOURCE_CODE,
)
from football_intelligence.data_mesh.adapters.wyscout_open import (
    SOURCE_CODE as WYSCOUT_OPEN_SOURCE_CODE,
)
from football_intelligence.metric_catalog.types import MetricGranularity

ComparisonMode = Literal["exact", "not_comparable", "methodology_pending"]

# Pinned evidence versions (Block 20D.4) -- the EXACT certified adapter
# semantic versions the real ESP_LL 2017/18 comparability evidence below was
# gathered against. Deliberately literal string constants, NEVER imported
# from either adapter's live `SEMANTIC_VERSION` -- see this module's
# docstring ("Why this is ALSO scoped by each source's semantic_version")
# for why a live import here would be exactly backwards. Only an explicit,
# reviewed future re-certification may change these two lines.
WYSCOUT_CERTIFIED_POLICY_VERSION = "wyscout-open-v0.2"
STATSBOMB_CERTIFIED_POLICY_VERSION = "statsbomb-open-v0.4"


@dataclass(frozen=True, slots=True, order=True)
class SourceRef:
    """One participating source's identity for policy purposes: which
    provider, at exactly which certified emission semantics. Ordered
    (`order=True`) by `(source_code, semantic_version)` so two `SourceRef`
    tuples naturally sort into one canonical order regardless of which
    order a caller discovered/passed them in."""

    source_code: str
    semantic_version: str


@dataclass(frozen=True, slots=True)
class MetricComparabilityPolicy:
    source_refs: tuple[SourceRef, SourceRef]
    metric_name: str
    metric_granularity: MetricGranularity
    comparison_mode: ComparisonMode
    rationale: str

    def __post_init__(self) -> None:
        if len(self.source_refs) != 2:
            raise ValueError(
                f"MetricComparabilityPolicy requires exactly 2 source_refs, got "
                f"{len(self.source_refs)}"
            )
        if self.source_refs[0].source_code == self.source_refs[1].source_code:
            raise ValueError(
                "MetricComparabilityPolicy.source_refs must be two DIFFERENT sources, got "
                f"the same source_code twice: {self.source_refs[0].source_code!r}"
            )
        if tuple(sorted(self.source_refs)) != self.source_refs:
            raise ValueError(
                "MetricComparabilityPolicy.source_refs must already be in canonical "
                "ascending (source_code, semantic_version) order -- callers must sort "
                "deterministically before construction, never rely on implicit order"
            )
        if not self.rationale.strip():
            raise ValueError(
                "MetricComparabilityPolicy.rationale must be a non-blank evidence string "
                "-- every policy entry must record why, never a bare mode value"
            )


def canonical_source_refs(a: SourceRef, b: SourceRef) -> tuple[SourceRef, SourceRef]:
    """Deterministic ordering for a pair of `SourceRef`s -- same convention
    already used by `jobs.audit_wyscout_statsbomb_overlap.
    crosswalk_canonical_key()` (sort, then use), applied one level up to
    the pair of sources itself rather than a pair of provider ids. Passing
    `(a, b)` or `(b, a)` always produces the identical result."""

    ordered = tuple(sorted((a, b)))
    return (ordered[0], ordered[1])


def _policy(
    *,
    source_a: SourceRef,
    source_b: SourceRef,
    metric_name: str,
    metric_granularity: MetricGranularity,
    comparison_mode: ComparisonMode,
    rationale: str,
) -> MetricComparabilityPolicy:
    return MetricComparabilityPolicy(
        source_refs=canonical_source_refs(source_a, source_b),
        metric_name=metric_name,
        metric_granularity=metric_granularity,
        comparison_mode=comparison_mode,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# The one certified provider pair for Block 20D.4: Wyscout Open x StatsBomb
# Open, at exactly the PINNED certified semantic versions the real ESP_LL
# 2017/18 evidence below was gathered against. Built from the literal
# WYSCOUT_CERTIFIED_POLICY_VERSION / STATSBOMB_CERTIFIED_POLICY_VERSION
# constants above -- NOT from either adapter's live SEMANTIC_VERSION -- so a
# future adapter version bump does nothing to these two lines; only a real
# observation's own (now-different) semantic_version stops matching them,
# falling through to methodology_pending until an explicit re-certification
# updates the pins.
# ---------------------------------------------------------------------------

_WYSCOUT_OPEN = SourceRef(
    source_code=WYSCOUT_OPEN_SOURCE_CODE, semantic_version=WYSCOUT_CERTIFIED_POLICY_VERSION
)
_STATSBOMB_OPEN = SourceRef(
    source_code=STATSBOMB_OPEN_SOURCE_CODE, semantic_version=STATSBOMB_CERTIFIED_POLICY_VERSION
)

# EXACT (10) -- real 100% agreement across every paired entity in the
# certified 36-match ESP_LL 2017/18 overlap, AND independent semantic
# evidence (native/authoritative source fields, or an explicitly verified
# and stress-tested derivation) beyond the empirical count alone. See this
# module's docstring for the full evidentiary standard.
_EXACT_ENTRIES: tuple[MetricComparabilityPolicy, ...] = (
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="home_score",
        metric_granularity="match",
        comparison_mode="exact",
        rationale=(
            "Native match-score field on both sides (never summed from player-tagged "
            "goal events per docs/BLOCK20_MULTI_SOURCE.md) -- 36/36 real paired matches "
            "agree exactly, 27/36 genuinely nonzero, full 0-6 scoreline diversity."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="away_score",
        metric_granularity="match",
        comparison_mode="exact",
        rationale=(
            "Same native-score evidence as home_score. 36/36 real paired matches agree "
            "exactly, 26/36 genuinely nonzero."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="round_name",
        metric_granularity="match",
        comparison_mode="exact",
        rationale=(
            "Both providers read an explicit native matchday/round field. Maximally "
            "strong real evidence: all 36 real paired values are pairwise distinct "
            "(matchdays 1-38, zero collisions) -- the opposite of a coincidental match."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="started",
        metric_granularity="player_appearance",
        comparison_mode="exact",
        rationale=(
            "Both certified adapters independently derive participation from each "
            "provider's own verified lineup/bench/substitution structure, not event-tag "
            "presence. 1284/1284 real paired entities agree exactly, 61.1% genuinely "
            "true -- well-exercised, not degenerate."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="goals",
        metric_granularity="player_match",
        comparison_mode="exact",
        rationale=(
            "The most heavily scrutinized metric in both mapping docs -- an explicit "
            "goal-reconciliation rule stress-tested against a real edge case (Wyscout "
            "match wyId 2499781, the no-shot-event goal). 992/992 real paired entities "
            "agree exactly, 92 genuinely nonzero -- not a sparse coincidence."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="non_penalty_goals",
        metric_granularity="player_match",
        comparison_mode="exact",
        rationale=(
            "992/992 real paired entities agree exactly with 89 independently genuine "
            "nonzero cases -- judged on its own real value evidence, not merely "
            "inferred from goals/penalty_goals composition (penalty_goals itself is "
            "NOT certified exact here, for thin-evidence reasons; non_penalty_goals' "
            "own evidence stands independently)."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="goals_for",
        metric_granularity="team_match",
        comparison_mode="exact",
        rationale=(
            "Same native-score evidence chain as home_score/away_score, aggregated per "
            "team. 72/72 real paired entities agree exactly, 53/72 genuinely nonzero."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="goals_against",
        metric_granularity="team_match",
        comparison_mode="exact",
        rationale=(
            "Same native-score evidence chain. 72/72 real paired entities agree "
            "exactly, 53/72 genuinely nonzero."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="home_away",
        metric_granularity="team_match",
        comparison_mode="exact",
        rationale=(
            "Structurally definitional (fixture home/away designation), not event-"
            "derived on either side. 72/72 real paired entities agree exactly, "
            "perfectly balanced 36 home / 36 away."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="clean_sheets",
        metric_granularity="goalkeeper_match",
        comparison_mode="exact",
        rationale=(
            "Deterministic derivation from the already-certified-exact goals_against "
            "== 0, computed the same way on both sides. 72/72 real paired entities "
            "agree exactly, 26.4% genuinely true -- not degenerate."
        ),
    ),
)

# NOT_COMPARABLE (12) -- real, substantial, and/or systematically one-
# directional disagreement across the certified overlap indicating the two
# providers measure genuinely different things under the same catalog
# name, not a tolerance-fixable gap. Never averaged, never a chosen winner.
_NOT_COMPARABLE_ENTRIES: tuple[MetricComparabilityPolicy, ...] = (
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="touches",
        metric_granularity="player_match",
        comparison_mode="not_comparable",
        rationale=(
            "Near-total real disagreement (3/992 exact agreement, mean|diff| ~78, "
            "range [1,220]) -- the two providers evidently count fundamentally "
            "different touch-event scopes under this name."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="duels_total",
        metric_granularity="player_match",
        comparison_mode="not_comparable",
        rationale=(
            "5.9% real exact agreement, mean|diff| ~12, and EVERY real disagreement is "
            "one-directional (Wyscout always higher) -- a systematic duel-counting "
            "methodology divergence, not random noise."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="ground_duels",
        metric_granularity="player_match",
        comparison_mode="not_comparable",
        rationale="Same one-directional duel-methodology divergence as duels_total (7.1% agree).",
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="passes_total",
        metric_granularity="player_match",
        comparison_mode="not_comparable",
        rationale=(
            "13.5% real exact agreement, mean|diff| ~5.2 -- the known, documented "
            "StatsBomb-vs-Wyscout pass-counting scope divergence (differing treatment "
            "of throw-ins/goal-kicks/short sequences at the event-log level)."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="passes_accurate",
        metric_granularity="player_match",
        comparison_mode="not_comparable",
        rationale="Same pass-counting-scope family as passes_total (17.9% agreement).",
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="pass_completion_pct",
        metric_granularity="player_match",
        comparison_mode="not_comparable",
        rationale="Inherits the passes_total/passes_accurate divergence (9.2% agreement).",
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="passes_total",
        metric_granularity="team_match",
        comparison_mode="not_comparable",
        rationale=(
            "The headline real case: 0/72 exact agreement, mean|diff| ~58 -- a real "
            "sampled pair was 253 vs 291 passes for the same team in the same match."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="passes_accurate",
        metric_granularity="team_match",
        comparison_mode="not_comparable",
        rationale="Same team-level pass-counting divergence (0/72 agreement, mean|diff| ~34).",
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="pass_accuracy_pct",
        metric_granularity="team_match",
        comparison_mode="not_comparable",
        rationale="Inherits the team-level passes_total/passes_accurate divergence (0/72 agree).",
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="offsides",
        metric_granularity="team_match",
        comparison_mode="not_comparable",
        rationale=(
            "12.5% real exact agreement, and every real disagreement is one-directional "
            "-- a systematic offside-tagging convention divergence."
        ),
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="passes",
        metric_granularity="goalkeeper_match",
        comparison_mode="not_comparable",
        rationale="Same passes-scope divergence as the outfield passes_total family (1.4% agree).",
    ),
    _policy(
        source_a=_WYSCOUT_OPEN,
        source_b=_STATSBOMB_OPEN,
        metric_name="distribution_accuracy_pct",
        metric_granularity="goalkeeper_match",
        comparison_mode="not_comparable",
        rationale="Inherits the goalkeeper passes-scope divergence (2.8% agree, large outliers).",
    ),
)

_POLICIES: dict[
    tuple[tuple[SourceRef, SourceRef], str, MetricGranularity], MetricComparabilityPolicy
] = {
    (entry.source_refs, entry.metric_name, entry.metric_granularity): entry
    for entry in (*_EXACT_ENTRIES, *_NOT_COMPARABLE_ENTRIES)
}


def comparability_policy(
    source_a: SourceRef,
    source_b: SourceRef,
    *,
    metric_name: str,
    metric_granularity: MetricGranularity,
) -> MetricComparabilityPolicy | None:
    """Looks up the reviewed comparability policy for exactly this provider
    pair (at exactly these certified semantic versions), this metric, and
    this granularity. `source_a`/`source_b` may be passed in either order --
    the lookup canonicalizes before consulting the registry.

    Returns `None` when no reviewed entry exists: an unlisted metric, an
    unknown/uncertified provider pair, or a provider pair whose semantic
    version(s) no longer match what any entry was reviewed against (e.g.
    after either adapter's `SEMANTIC_VERSION` is bumped). The caller (the
    V2 reconciliation orchestrator) must treat `None` as `methodology_
    pending`, never as `exact` -- this function has no "assume comparable
    by default" branch."""

    key = (canonical_source_refs(source_a, source_b), metric_name, metric_granularity)
    return _POLICIES.get(key)
