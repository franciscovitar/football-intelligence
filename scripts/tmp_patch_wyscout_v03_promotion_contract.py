from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


promoter = "analytics/src/football_intelligence/jobs/promote_historical_player_v2.py"
replace_once(
    promoter,
    '''from football_intelligence.jobs.historical_player_promotion_spec import (
    SEASON_LABEL,
    HistoricalPlayerPromotionSpec,
    historical_player_promotion_spec,
    supported_promotion_competitions,
)
''',
    '''from football_intelligence.jobs.historical_player_promotion_spec import (
    SEASON_LABEL,
    HistoricalPlayerPromotionSpec,
    certified_predecessor_promotion_specs,
    historical_player_promotion_spec,
    supported_promotion_competitions,
)
''',
)
replace_once(
    promoter,
    '''def validate_prewrite_state(
    state: PrewriteState,
    *,
    spec: HistoricalPlayerPromotionSpec = _DEFAULT_SPEC,
) -> None:
    if state.is_fresh or state.is_certified_complete_for(spec):
        return
    raise HistoricalPlayerPromotionError(
        f"historical production scope {spec.scope_key} is neither fresh nor certified complete; "
        f"refusing unexpected partial state: {state}"
    )
''',
    '''def validate_prewrite_state(
    state: PrewriteState,
    *,
    spec: HistoricalPlayerPromotionSpec = _DEFAULT_SPEC,
) -> None:
    if state.is_fresh or state.is_certified_complete_for(spec):
        return
    if any(
        state.is_certified_complete_for(predecessor)
        for predecessor in certified_predecessor_promotion_specs(spec.competition_code)
    ):
        return
    raise HistoricalPlayerPromotionError(
        f"historical production scope {spec.scope_key} is neither fresh, current certified, "
        f"nor an explicitly certified predecessor; refusing unexpected partial state: {state}"
    )
''',
)

tests = "analytics/tests/test_promote_historical_player_v2.py"
replace_once(
    tests,
    '''from football_intelligence.jobs.historical_player_promotion_spec import (
    historical_player_promotion_spec,
    supported_promotion_competitions,
)
''',
    '''from football_intelligence.jobs.historical_player_promotion_spec import (
    certified_predecessor_promotion_specs,
    historical_player_promotion_spec,
    supported_promotion_competitions,
)
''',
)
replace_once(
    tests,
    '''def test_pinned_non_england_specs_match_observed_runtime_fingerprints() -> None:
''',
    '''def test_england_v03_spec_and_v02_predecessor_are_exactly_pinned() -> None:
    current = historical_player_promotion_spec("ENG_PL")
    assert (
        current.matches,
        current.teams,
        current.players,
        current.player_appearances,
        current.source_observations,
        current.score_snapshots,
        current.feature_snapshots,
        current.season_players,
        current.season_players_450_min,
        current.performance_ready,
    ) == (380, 20, 515, 10_443, 422_877, 2_048, 38_737, 512, 385, 385)
    assert current.evidence_state_counts == {"insufficient_data": 1_754, "partial": 294}

    predecessors = certified_predecessor_promotion_specs("ENG_PL")
    assert len(predecessors) == 1
    predecessor = predecessors[0]
    assert (
        predecessor.matches,
        predecessor.teams,
        predecessor.players,
        predecessor.player_appearances,
        predecessor.source_observations,
        predecessor.score_snapshots,
        predecessor.feature_snapshots,
        predecessor.season_players,
        predecessor.season_players_450_min,
        predecessor.performance_ready,
    ) == (380, 20, 515, 10_443, 412_609, 2_048, 26_841, 512, 385, 385)
    assert predecessor.evidence_state_counts == current.evidence_state_counts


def test_pinned_non_england_specs_match_observed_runtime_fingerprints() -> None:
''',
)
replace_once(
    tests,
    '''def test_prewrite_state_does_not_accept_another_leagues_complete_shape() -> None:
''',
    '''def test_prewrite_state_accepts_only_exact_certified_england_v02_predecessor() -> None:
    predecessor = certified_predecessor_promotion_specs("ENG_PL")[0]
    predecessor_state = PrewriteState(
        season_exists=True,
        matches=predecessor.matches,
        teams=predecessor.teams,
        players=predecessor.players,
        player_appearances=predecessor.player_appearances,
        player_match_stats=predecessor.player_match_stats,
        team_match_stats=predecessor.team_match_stats,
        source_observations=predecessor.source_observations,
        player_v2_rows=predecessor.score_snapshots,
        player_v2_feature_rows=predecessor.feature_snapshots,
    )
    validate_prewrite_state(predecessor_state, spec=historical_player_promotion_spec("ENG_PL"))

    with pytest.raises(HistoricalPlayerPromotionError, match="partial state"):
        validate_prewrite_state(
            PrewriteState(
                season_exists=True,
                matches=predecessor.matches,
                teams=predecessor.teams,
                players=predecessor.players,
                player_appearances=predecessor.player_appearances,
                player_match_stats=predecessor.player_match_stats,
                team_match_stats=predecessor.team_match_stats,
                source_observations=predecessor.source_observations,
                player_v2_rows=predecessor.score_snapshots,
                player_v2_feature_rows=predecessor.feature_snapshots - 1,
            ),
            spec=historical_player_promotion_spec("ENG_PL"),
        )

    assert certified_predecessor_promotion_specs("ESP_LL") == ()
    assert certified_predecessor_promotion_specs("FRA_L1") == ()
    assert certified_predecessor_promotion_specs("GER_BL1") == ()
    assert certified_predecessor_promotion_specs("ITA_SA") == ()


def test_prewrite_state_does_not_accept_another_leagues_complete_shape() -> None:
''',
)
