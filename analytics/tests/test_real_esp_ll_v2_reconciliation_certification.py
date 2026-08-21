"""Block 20D.4: real Wyscout Open x StatsBomb Open ESP_LL 2017/18
`resolve_and_reconcile_v2()` end-to-end certification.

Reuses the exact Block 20D.3 certified real-cache loading/emission/overlap-
resolution/crosswalk-building functions from `jobs.audit_wyscout_
statsbomb_overlap` (never a second implementation of that logic) and feeds
the real combined observation set through the new V2 reconciliation
orchestrator. No network requests, no database connection, no `football.*`/
`intelligence.*` writes -- `resolve_and_reconcile_v2()` is a pure in-memory
function, exactly like V0's `resolve_and_reconcile()`.

Requires the real cached Wyscout/StatsBomb ESP_LL 2017/18 source material
Block 20B.2b/20C.2b/20D.3 already certified against, found in the sibling
worktrees where those blocks originally downloaded and cached it (this
worktree itself carries no cache -- consistent with `.gitignore`d
`data/cache/`). Skips cleanly, never fabricates a result, when those
sibling worktrees are not present in the current environment (e.g. CI,
which does not check out sibling branches as worktrees)."""

from __future__ import annotations

from pathlib import Path

import pytest

from football_intelligence.data_mesh.entity_resolution_v2 import resolve_player_v2
from football_intelligence.data_mesh.pipeline import resolve_and_reconcile_v2
from football_intelligence.data_mesh.reconciliation import MODEL_VERSION_V2
from football_intelligence.jobs.audit_wyscout_statsbomb_overlap import (
    CANONICAL_COMPETITION_CODE,
    build_player_crosswalk,
    collect_player_appearances,
    emit_statsbomb_esp_ll,
    emit_wyscout_esp_ll,
    resolve_overlap,
)
from football_intelligence.providers.statsbomb_open_policy import STATSBOMB_INTERNAL_ONLY

_WORKTREES_ROOT = Path(__file__).resolve().parents[3]
_WYSCOUT_CACHE_DIR = (
    _WORKTREES_ROOT / "block20-multi-source" / "analytics" / "data" / "cache" / "wyscout-open"
)
_STATSBOMB_CACHE_ROOT = (
    _WORKTREES_ROOT / "block20d3-rich-overlap" / "analytics" / "data" / "cache" / "statsbomb-open"
)
_STATSBOMB_REVISION = "b0bc9f22dd77c206ddedc1d742893b3bbe64baec"

_KNOWN_TRANSFER_TEAM_CONTEXT_COUNTS = 2  # every one of the 4 real transfers has exactly 2 contexts

# The 12 identities with an explicit `not_comparable` policy for
# wyscout-open x statsbomb-open (Block 20D.4) -- must NEVER show
# `agreed`/`conflict` in a real run.
_NOT_COMPARABLE_IDENTITIES = {
    ("touches", "player_match"),
    ("duels_total", "player_match"),
    ("ground_duels", "player_match"),
    ("passes_total", "player_match"),
    ("passes_accurate", "player_match"),
    ("pass_completion_pct", "player_match"),
    ("passes_total", "team_match"),
    ("passes_accurate", "team_match"),
    ("pass_accuracy_pct", "team_match"),
    ("offsides", "team_match"),
    ("passes", "goalkeeper_match"),
    ("distribution_accuracy_pct", "goalkeeper_match"),
}

# The 10 identities with an explicit `exact` policy (Block 20D.4).
_EXACT_IDENTITIES = {
    ("home_score", "match"),
    ("away_score", "match"),
    ("round_name", "match"),
    ("started", "player_appearance"),
    ("goals", "player_match"),
    ("non_penalty_goals", "player_match"),
    ("goals_for", "team_match"),
    ("goals_against", "team_match"),
    ("home_away", "team_match"),
    ("clean_sheets", "goalkeeper_match"),
}


def _caches_present() -> bool:
    wyscout_matches = _WYSCOUT_CACHE_DIR / "extracted" / "14464622_matches" / "matches_Spain.json"
    statsbomb_matches = _STATSBOMB_CACHE_ROOT / _STATSBOMB_REVISION / "matches" / "11" / "1.json"
    return wyscout_matches.exists() and statsbomb_matches.exists()


pytestmark = pytest.mark.skipif(
    not _caches_present(),
    reason=(
        "real cached Wyscout/StatsBomb ESP_LL 2017/18 source material not found in the "
        "expected sibling worktrees (block20-multi-source, block20d3-rich-overlap) -- "
        "this environment does not have them checked out"
    ),
)


def _load_real_batch() -> tuple[list, list, dict]:  # noqa: ANN001 -- test-local convenience typing
    wyscout_observations, wyscout_full_names = emit_wyscout_esp_ll(_WYSCOUT_CACHE_DIR)
    statsbomb_observations = emit_statsbomb_esp_ll(
        _STATSBOMB_CACHE_ROOT, source_revision=_STATSBOMB_REVISION
    )
    return wyscout_observations, statsbomb_observations, wyscout_full_names


def test_real_esp_ll_v2_certification() -> None:
    assert STATSBOMB_INTERNAL_ONLY is True

    wyscout_observations, statsbomb_observations, wyscout_full_names = _load_real_batch()

    team_index, match_index, overlap = resolve_overlap(wyscout_observations, statsbomb_observations)
    assert len(overlap.shared_canonical_matches) == 36
    assert len(overlap.date_mismatches) == 0
    assert len(overlap.team_convergence) == 20

    wyscout_appearances = collect_player_appearances(
        wyscout_observations,
        source_code="wyscout-open",
        team_index=team_index,
        match_index=match_index,
        full_name_by_player_id=wyscout_full_names,
    )
    statsbomb_appearances = collect_player_appearances(
        statsbomb_observations,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    crosswalk, crosswalk_report = build_player_crosswalk(
        wyscout_appearances.appearances,
        statsbomb_appearances.appearances,
        wyscout_missing_name=wyscout_appearances.missing_name_count,
        wyscout_missing_team=wyscout_appearances.missing_team_count,
        statsbomb_missing_name=statsbomb_appearances.missing_name_count,
        statsbomb_missing_team=statsbomb_appearances.missing_team_count,
    )
    assert len(crosswalk_report.accepted_pairs) == 434
    assert crosswalk_report.entries_created == 868
    assert crosswalk_report.resolution_success_count == 434
    assert crosswalk_report.crosswalk_conflicts == 0

    # The 4 real, certified mid-season transfers each carry exactly 2 team
    # contexts and both provider ids resolve to the identical canonical key.
    transfer_pairs = [
        pair for pair in crosswalk_report.accepted_pairs if pair.is_multi_team_context
    ]
    assert len(transfer_pairs) == 4
    for pair in transfer_pairs:
        assert len(pair.team_context_evidence) == _KNOWN_TRANSFER_TEAM_CONTEXT_COUNTS
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
        assert wyscout_resolution.status == "resolved"
        assert wyscout_resolution.logical_key == statsbomb_resolution.logical_key

    all_observations = wyscout_observations + statsbomb_observations
    decisions, meta = resolve_and_reconcile_v2(
        all_observations, competition_code=CANONICAL_COMPETITION_CODE, crosswalk=crosswalk
    )
    assert decisions, "expected real decisions from the certified ESP_LL overlap"

    # No cross-granularity collapse: saves/player_match and
    # saves/goalkeeper_match must both be present as DISTINCT decision
    # groups (distinct logical_entity_key), never merged.
    saves_decisions = [d for d in decisions if d.metric_name == "saves"]
    saves_granularities = {d.metric_granularity for d in saves_decisions}
    assert {"player_match", "goalkeeper_match"} <= saves_granularities
    saves_keys_by_granularity: dict[str, set[str]] = {}
    for decision in saves_decisions:
        saves_keys_by_granularity.setdefault(decision.metric_granularity, set()).add(
            decision.logical_entity_key
        )
    assert saves_keys_by_granularity["player_match"].isdisjoint(
        saves_keys_by_granularity["goalkeeper_match"]
    )

    # Every decision's model_version is the V2 constant -- never conflated
    # with V0's MODEL_VERSION.
    assert all(d.model_version == MODEL_VERSION_V2 for d in decisions)

    # The 10 exact-policy identities produced real value comparisons
    # (agreed/conflict/single_source -- never not_comparable/
    # methodology_pending, since a reviewed exact policy exists for them).
    exact_decisions = [
        d for d in decisions if (d.metric_name, d.metric_granularity) in _EXACT_IDENTITIES
    ]
    assert exact_decisions
    assert all(d.status in ("agreed", "conflict", "single_source") for d in exact_decisions)
    two_source_exact = [d for d in exact_decisions if d.source_count == 2]
    assert two_source_exact, "expected at least one real 2-source exact-policy decision"
    assert any(d.status == "agreed" for d in two_source_exact)

    # The 12 not_comparable-policy identities NEVER emit agreed/conflict
    # for a real 2-source group.
    not_comparable_decisions = [
        d for d in decisions if (d.metric_name, d.metric_granularity) in _NOT_COMPARABLE_IDENTITIES
    ]
    two_source_not_comparable = [d for d in not_comparable_decisions if d.source_count == 2]
    assert two_source_not_comparable, "expected at least one real 2-source not_comparable decision"
    assert all(d.status == "not_comparable" for d in two_source_not_comparable)
    assert all(d.candidate_value is None for d in two_source_not_comparable)

    # Every other real 2-source group (the deferred-tolerance and thin-
    # evidence identities) fails closed to methodology_pending -- never a
    # silent agreed/conflict outside the two reviewed sets above.
    two_source_other = [
        d
        for d in decisions
        if d.source_count == 2
        and (d.metric_name, d.metric_granularity) not in _EXACT_IDENTITIES
        and (d.metric_name, d.metric_granularity) not in _NOT_COMPARABLE_IDENTITIES
    ]
    assert two_source_other
    assert all(d.status == "methodology_pending" for d in two_source_other)
    assert all(d.candidate_value is None for d in two_source_other)

    # Single-source groups remain single_source regardless of pairwise
    # policy (matches present on only one side of the real overlap, e.g.
    # the 344 Wyscout-only ESP_LL matches outside the 36-match overlap).
    single_source_decisions = [d for d in decisions if d.source_count == 1]
    assert single_source_decisions
    assert all(d.status == "single_source" for d in single_source_decisions)

    # StatsBomb never became a canonical-eligible/product-facing artifact:
    # every decision's provenance is auditable in `participating_sources`,
    # and nothing in this function touches football.*/intelligence.* (a
    # pure in-memory call, no DB import, no DATABASE_URL).
    statsbomb_participating = [d for d in decisions if "statsbomb-open" in d.participating_sources]
    assert statsbomb_participating

    # Block 20D.4 correctness fix: StatsBomb's real ESP_LL Open Data scope
    # is genuinely only 36 of one club's 38 real league matches -- never a
    # full season for any player. `AdapterScope.season_scope_complete`
    # (StatsBomb ESP_LL_SCOPE only) must suppress ALL of its player_season/
    # goalkeeper_season emission, so every real season-level decision here
    # is Wyscout-only (its genuinely complete 380-match ESP_LL season),
    # never a StatsBomb partial-window aggregate silently indistinguishable
    # from a real season total.
    season_decisions = [
        d for d in decisions if d.metric_granularity in ("player_season", "goalkeeper_season")
    ]
    assert season_decisions, "expected real season-level decisions from Wyscout's complete scope"
    assert all(d.source_count == 1 for d in season_decisions)
    assert all(d.participating_sources == ("wyscout-open",) for d in season_decisions)
    assert not any("statsbomb-open" in d.participating_sources for d in season_decisions)


def test_real_esp_ll_v2_certification_pinned_status_counts() -> None:
    """Pins the exact real status/source_count breakdown observed against
    the certified full ESP_LL cache (Wyscout 380 matches + StatsBomb 36
    matches, all granularities) -- a regression baseline in the same style
    as `test_real_snapshot_v2_reconciliation_regression.py`'s pinned ENG_PL
    2025/26 counts. Two internal-consistency identities, verified by
    construction, not merely observed: every real 2-source `agreed` count
    sums exactly across the 10 exact-policy identities (no exact-policy
    decision ever resolves to anything but `agreed`/`conflict` in this real
    sample, and nothing outside the 10 ever contributes to `agreed` here);
    every real 2-source `not_comparable` count sums exactly across the 12
    not_comparable-policy identities -- zero leakage either direction."""

    wyscout_observations, statsbomb_observations, wyscout_full_names = _load_real_batch()
    team_index, match_index, overlap = resolve_overlap(wyscout_observations, statsbomb_observations)
    wyscout_appearances = collect_player_appearances(
        wyscout_observations,
        source_code="wyscout-open",
        team_index=team_index,
        match_index=match_index,
        full_name_by_player_id=wyscout_full_names,
    )
    statsbomb_appearances = collect_player_appearances(
        statsbomb_observations,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    crosswalk, _report = build_player_crosswalk(
        wyscout_appearances.appearances,
        statsbomb_appearances.appearances,
        wyscout_missing_name=wyscout_appearances.missing_name_count,
        wyscout_missing_team=wyscout_appearances.missing_team_count,
        statsbomb_missing_name=statsbomb_appearances.missing_name_count,
        statsbomb_missing_team=statsbomb_appearances.missing_team_count,
    )
    decisions, _meta = resolve_and_reconcile_v2(
        wyscout_observations + statsbomb_observations,
        competition_code=CANONICAL_COMPETITION_CODE,
        crosswalk=crosswalk,
    )

    assert len(wyscout_observations) == 416_407
    # StatsBomb's own emitted total dropped from the pre-fix 63,063 --
    # the exact size of the (now-suppressed) player_season/
    # goalkeeper_season observation set for this genuinely incomplete
    # scope, never faked as zero or extrapolated.
    assert len(statsbomb_observations) == 61_247

    assert len(decisions) == 403_291
    single_source = [d for d in decisions if d.source_count == 1]
    two_source_agreed = [d for d in decisions if d.source_count == 2 and d.status == "agreed"]
    two_source_not_comparable = [
        d for d in decisions if d.source_count == 2 and d.status == "not_comparable"
    ]
    two_source_pending = [
        d for d in decisions if d.source_count == 2 and d.status == "methodology_pending"
    ]
    assert len(single_source) == 369_153
    assert len(two_source_agreed) == 3_664
    assert len(two_source_not_comparable) == 6_376
    assert len(two_source_pending) == 24_098

    # Zero leakage: every real 2-source `agreed` decision is one of the 10
    # exact-policy identities, and every real 2-source `not_comparable`
    # decision is one of the 12 not_comparable-policy identities.
    assert all(
        (d.metric_name, d.metric_granularity) in _EXACT_IDENTITIES for d in two_source_agreed
    )
    assert all(
        (d.metric_name, d.metric_granularity) in _NOT_COMPARABLE_IDENTITIES
        for d in two_source_not_comparable
    )


def test_real_esp_ll_v2_certification_is_idempotent() -> None:
    wyscout_observations, statsbomb_observations, wyscout_full_names = _load_real_batch()
    team_index, match_index, overlap = resolve_overlap(wyscout_observations, statsbomb_observations)
    wyscout_appearances = collect_player_appearances(
        wyscout_observations,
        source_code="wyscout-open",
        team_index=team_index,
        match_index=match_index,
        full_name_by_player_id=wyscout_full_names,
    )
    statsbomb_appearances = collect_player_appearances(
        statsbomb_observations,
        source_code="statsbomb-open",
        team_index=team_index,
        match_index=match_index,
    )
    crosswalk, _report = build_player_crosswalk(
        wyscout_appearances.appearances,
        statsbomb_appearances.appearances,
        wyscout_missing_name=wyscout_appearances.missing_name_count,
        wyscout_missing_team=wyscout_appearances.missing_team_count,
        statsbomb_missing_name=statsbomb_appearances.missing_name_count,
        statsbomb_missing_team=statsbomb_appearances.missing_team_count,
    )
    all_observations = wyscout_observations + statsbomb_observations

    decisions_first, meta_first = resolve_and_reconcile_v2(
        all_observations, competition_code=CANONICAL_COMPETITION_CODE, crosswalk=crosswalk
    )
    decisions_second, meta_second = resolve_and_reconcile_v2(
        all_observations, competition_code=CANONICAL_COMPETITION_CODE, crosswalk=crosswalk
    )

    def _without_wall_clock(decisions: list) -> list[tuple]:  # noqa: ANN001
        return sorted(
            (
                d.logical_entity_key,
                d.entity_type,
                d.metric_name,
                d.metric_granularity,
                d.candidate_value,
                d.status,
                d.confidence,
                d.winning_source_code,
                d.participating_sources,
                d.source_count,
                d.model_version,
            )
            for d in decisions
        )

    assert _without_wall_clock(decisions_first) == _without_wall_clock(decisions_second)
    assert meta_first == meta_second
