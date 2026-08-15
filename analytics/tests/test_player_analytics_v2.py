from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from football_intelligence.metric_catalog import METRIC_CATALOG_V2
from football_intelligence.player_analytics import engine as engine_v1
from football_intelligence.player_analytics.catalog_v2 import (
    CATALOG_BY_IDENTITY,
    GOALKEEPER_MATCH_CATALOG,
    GOALKEEPER_SEASON_CATALOG,
    PLAYER_MATCH_CATALOG,
    PLAYER_SEASON_CATALOG,
    index_catalog_by_identity,
    season_catalog_for_observation,
)
from football_intelligence.player_analytics.engine_v2 import (
    MIN_RANKING_CONFIDENCE,
    MODEL_VERSION,
    PERCENTILE_MINUTES_BY_WINDOW,
    WeightedScoreEvidence,
    _compose_overall,
    _weighted_percentile_score,
    calculate_player_analytics_v2,
    calculate_player_analytics_v2_result,
    classify_results_vs_process,
    rank_by_confidence_gated_score,
)
from football_intelligence.player_analytics.models import (
    GoalkeeperSeasonObservation,
    PlayerFeature,
    PlayerObservation,
    PlayerSeasonObservation,
)
from football_intelligence.statistical_engine import derive_available_metrics

_NOW = datetime(2026, 8, 14, tzinfo=UTC)


def _observation(
    *,
    player_id: int,
    player_name: str,
    match_id: int,
    minutes: int,
    listed_position: str,
    stats: dict[str, float | None],
) -> PlayerObservation:
    return PlayerObservation(
        player_id=player_id,
        player_name=player_name,
        match_id=match_id,
        kickoff_at=datetime(2026, 1, match_id, tzinfo=UTC),
        team_id=1,
        minutes=minutes,
        listed_position=listed_position,
        possession_pct=50.0,
        stats=stats,
    )


def test_confidence_gated_ranking_scenario_verbatim() -> None:
    # Player A: score 96, confidence 94% (well above the gate), 2183 minutes.
    # Player B: score 98, confidence 31% (below the 40% gate), 238 minutes.
    # B's raw score is higher, but B must not outrank A.
    entries = [(96.0, 0.94, 2183), (98.0, 0.31, 238)]
    ranking = rank_by_confidence_gated_score(entries)
    assert ranking == (0, 1)


def test_ranking_gate_threshold_is_documented_and_applied() -> None:
    assert MIN_RANKING_CONFIDENCE == 0.40
    # Two entries both above the gate: higher score wins normally.
    entries = [(70.0, 0.50, 1000), (80.0, 0.55, 1000)]
    assert rank_by_confidence_gated_score(entries) == (1, 0)
    # Two entries both below the gate: still ordered, but the tier boundary
    # means neither can beat an eligible peer -- verified alongside one.
    entries_mixed = [(99.0, 0.10, 100), (60.0, 0.50, 900)]
    assert rank_by_confidence_gated_score(entries_mixed) == (1, 0)


def test_results_vs_process_returns_insufficient_data_without_expected_output() -> None:
    signal = classify_results_vs_process(
        raw_output=10.0,
        output_percentile=80.0,
        expected_output=None,
        expected_output_percentile=None,
    )
    assert signal == "insufficient_data"


def test_results_vs_process_uses_direct_residual_without_percentiles() -> None:
    signal = classify_results_vs_process(
        raw_output=10.0,
        output_percentile=80.0,
        expected_output=6.0,
        expected_output_percentile=None,
    )
    assert signal == "results_above_process"


def test_results_above_process_when_output_percentile_far_exceeds_expected() -> None:
    signal = classify_results_vs_process(
        raw_output=15.0,
        output_percentile=90.0,
        expected_output=6.0,
        expected_output_percentile=60.0,
    )
    assert signal == "results_above_process"


def test_results_below_process_when_output_percentile_far_trails_expected() -> None:
    signal = classify_results_vs_process(
        raw_output=2.0,
        output_percentile=30.0,
        expected_output=10.0,
        expected_output_percentile=75.0,
    )
    assert signal == "results_below_process"


def test_results_aligned_within_threshold() -> None:
    signal = classify_results_vs_process(
        raw_output=8.0,
        output_percentile=55.0,
        expected_output=7.5,
        expected_output_percentile=50.0,
    )
    assert signal == "aligned"


def test_partial_weight_is_not_renormalized_to_a_full_profile_score() -> None:
    feature = PlayerFeature(
        player_id=1,
        player_name="Evidence Player",
        scope_key="core:test",
        window="season",
        role="forward",
        metric_name="goals",
        minutes=900,
        appearances=10,
        raw_per90=1.0,
        adjusted_per90=1.0,
        percentile=100.0,
        reference_sample_size=20,
        model_version="player-v1.0",
        calculated_at=_NOW,
    )
    evidence = _weighted_percentile_score(
        {"goals": feature},
        (("goals", 0.25, 1), ("npxg", 0.75, 1)),
        core_metrics=frozenset({"goals"}),
    )
    assert evidence.score is None
    assert evidence.evidence_weight_available == 0.25
    assert evidence.evidence_weight_required == 1.0
    assert evidence.evidence_coverage_pct == 25.0
    assert evidence.evidence_state == "insufficient_data"


def test_missing_core_metric_is_insufficient_even_with_other_weight() -> None:
    feature = PlayerFeature(
        player_id=1,
        player_name="Evidence Player",
        scope_key="core:test",
        window="season",
        role="forward",
        metric_name="goals",
        minutes=900,
        appearances=10,
        raw_per90=1.0,
        adjusted_per90=1.0,
        percentile=90.0,
        reference_sample_size=20,
        model_version="player-v1.0",
        calculated_at=_NOW,
    )
    evidence = _weighted_percentile_score(
        {"goals": feature},
        (("goals", 0.7, 1), ("npxg", 0.3, 1)),
        core_metrics=frozenset({"goals", "npxg"}),
    )
    assert evidence.evidence_coverage_pct == 70.0
    assert evidence.evidence_state == "insufficient_data"
    assert evidence.score is None


def test_complete_profile_is_ready_and_has_a_numeric_score() -> None:
    goals = PlayerFeature(
        player_id=1,
        player_name="Evidence Player",
        scope_key="core:test",
        window="season",
        role="forward",
        metric_name="goals",
        minutes=900,
        appearances=10,
        raw_per90=1.0,
        adjusted_per90=1.0,
        percentile=90.0,
        reference_sample_size=20,
        model_version="player-v1.0",
        calculated_at=_NOW,
    )
    npxg = dataclasses.replace(
        goals,
        metric_name="npxg",
        raw_per90=0.7,
        adjusted_per90=0.7,
        percentile=70.0,
    )
    evidence = _weighted_percentile_score(
        {"goals": goals, "npxg": npxg},
        (("goals", 0.25, 1), ("npxg", 0.75, 1)),
        core_metrics=frozenset({"goals", "npxg"}),
    )
    assert evidence.evidence_coverage_pct == 100.0
    assert evidence.evidence_state == "ready"
    assert evidence.score == 75.0


def _midfield_population() -> list[PlayerObservation]:
    observations: list[PlayerObservation] = []
    # A creative attacking midfielder: high key_passes, goals, dribbles.
    for match_id in range(1, 6):
        observations.append(
            _observation(
                player_id=1,
                player_name="Creator One",
                match_id=match_id,
                minutes=90,
                listed_position="CAM",
                stats={
                    "goals": 1,
                    "assists": 1,
                    "shots_total": 3,
                    "shots_on_target": 2,
                    "passes_total": 40,
                    "key_passes": 3,
                    "tackles": 1,
                    "blocks": 0,
                    "interceptions": 1,
                    "dribbles_successful": 3,
                    "duels_won": 4,
                    "fouls_drawn": 2,
                    "fouls_committed": 1,
                    "saves": None,
                },
            )
        )
    # A defensive-minded central midfielder: low creation, high defending.
    for match_id in range(1, 6):
        observations.append(
            _observation(
                player_id=2,
                player_name="Anchor Two",
                match_id=match_id,
                minutes=90,
                listed_position="CDM",
                stats={
                    "goals": 0,
                    "assists": 0,
                    "shots_total": 0,
                    "shots_on_target": 0,
                    "passes_total": 60,
                    "key_passes": 0,
                    "tackles": 5,
                    "blocks": 2,
                    "interceptions": 4,
                    "dribbles_successful": 0,
                    "duels_won": 6,
                    "fouls_drawn": 1,
                    "fouls_committed": 2,
                    "saves": None,
                },
            )
        )
    # A neutral third midfielder to give the coarse "midfielder" population
    # more than 2 members (both fine families collapse into the same broad
    # role for V1 percentile computation).
    for match_id in range(1, 6):
        observations.append(
            _observation(
                player_id=3,
                player_name="Neutral Three",
                match_id=match_id,
                minutes=90,
                listed_position="CM",
                stats={
                    "goals": 0,
                    "assists": 1,
                    "shots_total": 1,
                    "shots_on_target": 0,
                    "passes_total": 50,
                    "key_passes": 1,
                    "tackles": 2,
                    "blocks": 1,
                    "interceptions": 2,
                    "dribbles_successful": 1,
                    "duels_won": 3,
                    "fouls_drawn": 1,
                    "fouls_committed": 1,
                    "saves": None,
                },
            )
        )
    return observations


def test_v2_model_version_is_distinguishable_from_v1() -> None:
    observations = _midfield_population()
    v1_result = engine_v1.calculate_player_analytics(
        observations, scope_key="core:test", calculated_at=_NOW
    )
    v2_scores = calculate_player_analytics_v2(
        observations, scope_key="core:test", calculated_at=_NOW
    )

    assert MODEL_VERSION == "player-v2.0"
    assert engine_v1.MODEL_VERSION == "player-v1.0"
    assert all(score.model_version == "player-v2.0" for score in v2_scores)
    assert all(score.model_version == "player-v1.0" for score in v1_result.scores)


def test_v2_exposes_both_coarse_role_and_fine_position_family() -> None:
    observations = _midfield_population()
    v2_scores = calculate_player_analytics_v2(
        observations, scope_key="core:test", calculated_at=_NOW
    )
    season_scores = {score.player_id: score for score in v2_scores if score.window == "season"}

    assert season_scores[1].role == "midfielder"
    assert season_scores[1].position_family == "attacking_midfielder"
    assert season_scores[2].role == "midfielder"
    assert season_scores[2].position_family == "defensive_midfielder"
    assert season_scores[1].evidence_state == "partial"
    assert 0.0 < season_scores[1].evidence_coverage_pct < 100.0
    assert season_scores[1].evidence_weight_available < season_scores[1].evidence_weight_required
    assert "key_passes" in season_scores[1].evidence_metrics_required
    assert season_scores[1].overall_score is None


def test_v2_overall_score_differs_from_v1_when_family_weights_differ() -> None:
    # V1's own role recognition only understands broad tokens (G/D/M/F), so
    # this replicates V2's internal broad-token rewrite to get a like-for-like
    # V1 baseline that actually classifies and scores these fine-token
    # players, matching what `calculate_player_analytics_v2` does internally.
    broad_observations = [
        dataclasses.replace(observation, listed_position="M")
        for observation in _midfield_population()
    ]
    v1_result = engine_v1.calculate_player_analytics(
        broad_observations, scope_key="core:test", calculated_at=_NOW
    )
    v2_scores = calculate_player_analytics_v2(
        _midfield_population(), scope_key="core:test", calculated_at=_NOW
    )

    v1_creator = next(
        score for score in v1_result.scores if score.player_id == 1 and score.window == "season"
    )
    v2_creator = next(
        score for score in v2_scores if score.player_id == 1 and score.window == "season"
    )
    # The current observation schema cannot supply the complete intended V2
    # attacking-midfielder profile. V2 must not substitute the available V1
    # score or publish a partial recombination as complete.
    assert v2_creator.evidence_state == "partial"
    assert v2_creator.overall_score is None
    assert v1_creator.overall_score is not None


def test_v2_reports_insufficient_data_when_only_the_coarse_broad_role_is_known() -> None:
    # "D" is a bare broad-role token (the kind API-Football's fixture payload
    # actually exposes, per docs/PLAYER_ANALYTICS.md) -- V1 classifies it
    # fine (coarse "defender"), but it is not one of the 8 fine position
    # families, so `classify_position_family` falls back to the broad
    # "defender" string, which is not a POSITION_FAMILY_SCORE_WEIGHTS key.
    observations = [
        _observation(
            player_id=9,
            player_name="Broad Role Defender",
            match_id=match_id,
            minutes=90,
            listed_position="D",
            stats={
                "goals": 0,
                "assists": 0,
                "shots_total": 1,
                "shots_on_target": 0,
                "passes_total": 40,
                "key_passes": 1,
                "tackles": 3,
                "blocks": 1,
                "interceptions": 2,
                "dribbles_successful": 1,
                "duels_won": 2,
                "fouls_drawn": 1,
                "fouls_committed": 1,
                "saves": None,
            },
        )
        for match_id in range(1, 4)
    ]
    v1_result = engine_v1.calculate_player_analytics(
        observations, scope_key="core:test", calculated_at=_NOW
    )
    v2_scores = calculate_player_analytics_v2(
        observations, scope_key="core:test", calculated_at=_NOW
    )
    assert v1_result.scores  # sanity: V1 did classify and score this player
    assert v2_scores
    assert all(score.position_family == "defender" for score in v2_scores)
    # No fine weight profile applies to the broad "defender" fallback. V2
    # reports the gap explicitly and never substitutes the V1 score.
    for score in v2_scores:
        assert score.overall_score is None
        assert score.evidence_state == "insufficient_data"
        assert score.evidence_coverage_pct == 0.0


def test_catalog_metric_outside_v1_flows_to_feature_and_percentile() -> None:
    observations = [
        _observation(
            player_id=player_id,
            player_name=f"Progressor {player_id}",
            match_id=match_id,
            minutes=90,
            listed_position="CM",
            stats={"progressive_passes": value},
        )
        for player_id, value in ((1, 3.0), (2, 9.0))
        for match_id in range(1, 6)
    ]
    result = calculate_player_analytics_v2_result(
        observations, scope_key="core:test", calculated_at=_NOW
    )
    season = {
        feature.player_id: feature
        for feature in result.features
        if feature.window == "season" and feature.metric_name == "progressive_passes"
    }
    assert set(season) == {1, 2}
    assert season[1].per90_value == 3.0
    assert season[2].percentile == 100.0
    assert season[2].comparison_group.endswith(":central_midfielder")


def test_catalog_dimensions_accept_xa_progression_and_aerial_inputs() -> None:
    common = {
        "xa": 0.4,
        "key_passes": 2.0,
        "shot_creating_actions": 3.0,
        "passes_into_box": 2.0,
        "expected_threat_created": 0.3,
        "progressive_passes": 5.0,
        "progressive_carries": 4.0,
        "passes_into_final_third": 6.0,
        "carries_into_final_third": 3.0,
        "aerial_duels_won": 4.0,
        "aerial_duels": 5.0,
    }
    observations = [
        _observation(
            player_id=player_id,
            player_name=f"Complete {player_id}",
            match_id=match_id,
            minutes=90,
            listed_position="CM",
            stats={name: value * multiplier for name, value in common.items()},
        )
        for player_id, multiplier in ((1, 1.0), (2, 2.0))
        for match_id in range(1, 6)
    ]
    result = calculate_player_analytics_v2_result(
        observations, scope_key="core:test", calculated_at=_NOW
    )
    score = next(item for item in result.scores if item.player_id == 2 and item.window == "season")
    assert score.dimension_evidence["creation"].evidence_state == "ready"
    assert score.dimension_evidence["creation"].score is not None
    assert score.dimension_evidence["progression"].evidence_state == "ready"
    assert score.dimension_evidence["aerial"].evidence_state == "ready"


def test_derived_registry_is_safe_and_requires_all_inputs() -> None:
    values, versions = derive_available_metrics({"goals": 8.0, "advanced.xg": 5.5})
    assert values["goals_minus_xg"] == 2.5
    assert versions["goals_minus_xg"] == "derived-v2.0"

    zero, _ = derive_available_metrics(
        {"advanced.xg": 1.0, "shots_total": 0.0, "passes_accurate": 0.0, "passes_total": 0.0}
    )
    assert "xg_per_shot" not in zero
    assert "pass_completion_pct" not in zero

    missing, _ = derive_available_metrics({"goals": 2.0})
    assert "goals_minus_xg" not in missing


def test_derived_feature_requires_aligned_observation_coverage() -> None:
    observations = [
        _observation(
            player_id=1,
            player_name="Incomplete Inputs",
            match_id=1,
            minutes=90,
            listed_position="ST",
            stats={"goals": 1.0, "xg": None},
        ),
        _observation(
            player_id=1,
            player_name="Incomplete Inputs",
            match_id=2,
            minutes=90,
            listed_position="ST",
            stats={"goals": None, "xg": 0.5},
        ),
    ]
    result = calculate_player_analytics_v2_result(
        observations, scope_key="core:test", calculated_at=_NOW
    )
    season_metrics = {
        feature.metric_name for feature in result.features if feature.window == "season"
    }
    assert "goals_minus_xg" not in season_metrics


def test_goalkeeper_workload_is_not_a_quality_metric_and_goals_prevented_is() -> None:
    observations = [
        _observation(
            player_id=player_id,
            player_name=f"Keeper {player_id}",
            match_id=match_id,
            minutes=90,
            listed_position="GK",
            stats={
                "saves": saves,
                "shots_on_target_faced": faced,
                "psxg": psxg,
                "goals_conceded": 2.0,
                "crosses_stopped": 2.0,
                "sweeper_actions": 2.0,
                "distribution_accuracy_pct": 80.0,
            },
        )
        for player_id, saves, faced, psxg in ((1, 5.0, 10.0, 2.0), (2, 10.0, 20.0, 4.0))
        for match_id in range(1, 6)
    ]
    result = calculate_player_analytics_v2_result(
        observations, scope_key="core:test", calculated_at=_NOW
    )
    scores = {
        item.player_id: item.dimension_evidence["goalkeeping"].score
        for item in result.scores
        if item.window == "season"
    }
    # Keeper 2 faces twice the workload at the same save rate; workload itself
    # is absent from the profile, while the better goals-prevented result helps.
    assert (
        "shots_on_target_faced"
        not in result.scores[0].dimension_evidence["goalkeeping"].evidence_metrics_expected
    )
    assert scores[2] is not None and scores[1] is not None
    assert scores[2] > scores[1]


def test_overall_is_composed_from_position_relevant_dimensions() -> None:
    def ready(value: float) -> WeightedScoreEvidence:
        return WeightedScoreEvidence(value, 1.0, 1.0, 100.0, "ready", (), (), (), ())

    dimensions = {
        name: ready(50.0)
        for name in (
            "performance",
            "underlying_performance",
            "finishing",
            "shot_generation",
            "creation",
            "progression",
            "passing",
            "one_v_one",
            "defence",
            "ball_winning",
            "aerial",
            "goalkeeping",
        )
    }
    dimensions["finishing"] = ready(100.0)
    forward = _compose_overall(dimensions, "forward")
    assert forward.score == 65.0

    # Defence is not part of the forward Overall profile.
    dimensions["defence"] = ready(0.0)
    assert _compose_overall(dimensions, "forward").score == forward.score


def test_percentile_population_excludes_tiny_samples_without_dropping_values() -> None:
    eligible_observations = [
        _observation(
            player_id=player_id,
            player_name=f"Eligible {player_id}",
            match_id=match_id,
            minutes=90,
            listed_position="CM",
            stats={"progressive_passes": per_match},
        )
        for player_id, per_match in ((1, 2.0), (2, 4.0))
        for match_id in range(1, 6)
    ]
    tiny_outlier = _observation(
        player_id=3,
        player_name="Tiny Outlier",
        match_id=6,
        minutes=20,
        listed_position="CM",
        stats={"progressive_passes": 100.0},
    )

    baseline = calculate_player_analytics_v2_result(
        eligible_observations, scope_key="core:test", calculated_at=_NOW
    )
    result = calculate_player_analytics_v2_result(
        [*eligible_observations, tiny_outlier],
        scope_key="core:test",
        calculated_at=_NOW,
    )
    baseline_season = {
        feature.player_id: feature
        for feature in baseline.features
        if feature.window == "season" and feature.metric_name == "progressive_passes"
    }
    season = {
        feature.player_id: feature
        for feature in result.features
        if feature.window == "season" and feature.metric_name == "progressive_passes"
    }

    assert PERCENTILE_MINUTES_BY_WINDOW == {
        "last_3": 90,
        "last_5": 180,
        "last_10": 270,
        "season": 450,
    }
    assert season[1].percentile == baseline_season[1].percentile == 0.0
    assert season[2].percentile == baseline_season[2].percentile == 100.0
    assert season[1].percentile_state == "ready"
    assert season[1].reference_sample_size == 2
    assert season[3].raw_value == 100.0
    assert season[3].per90_value == 450.0
    assert season[3].percentile is None
    assert season[3].percentile_state == "insufficient_sample"
    assert season[3].reference_sample_size == 2

    eligible_score = next(
        score for score in result.scores if score.player_id == 1 and score.window == "season"
    )
    assert eligible_score.confidence < 1.0
    assert season[1].percentile_state == "ready"


def test_short_window_uses_window_appropriate_percentile_minimum() -> None:
    observations = [
        _observation(
            player_id=player_id,
            player_name=f"Short Window {player_id}",
            match_id=match_id,
            minutes=30,
            listed_position="CM",
            stats={"progressive_passes": float(player_id)},
        )
        for player_id in (1, 2)
        for match_id in range(1, 4)
    ]
    result = calculate_player_analytics_v2_result(
        observations, scope_key="core:test", calculated_at=_NOW
    )
    features = [
        feature
        for feature in result.features
        if feature.window == "last_3" and feature.metric_name == "progressive_passes"
    ]
    assert all(feature.minutes == 90 for feature in features)
    assert all(feature.percentile_state == "ready" for feature in features)
    assert all(feature.percentile is not None for feature in features)


def test_catalog_identity_preserves_equal_keys_across_grains() -> None:
    player_match = PLAYER_MATCH_CATALOG["goals"][1]
    player_season = dataclasses.replace(player_match, granularity="player_season")
    indexed = index_catalog_by_identity((player_match, player_season))

    assert len(CATALOG_BY_IDENTITY) == len(METRIC_CATALOG_V2)
    assert indexed[("player_match", "goals")].granularity == "player_match"
    assert indexed[("player_season", "goals")].granularity == "player_season"


def test_match_engine_rejects_season_observations_and_ignores_season_definitions() -> None:
    match_observation = _observation(
        player_id=1,
        player_name="Match Only",
        match_id=1,
        minutes=90,
        listed_position="CM",
        stats={"appearances": 12.0, "starts": 10.0},
    )
    result = calculate_player_analytics_v2_result(
        [match_observation], scope_key="core:test", calculated_at=_NOW
    )
    assert not {"appearances", "starts", "minutes_per_appearance"} & {
        feature.metric_name for feature in result.features
    }
    assert "appearances" in PLAYER_SEASON_CATALOG
    assert "appearances" not in PLAYER_MATCH_CATALOG

    season_observation = PlayerSeasonObservation(
        player_id=1,
        player_name="Season Only",
        season_id=1,
        season_label="2025/26",
        team_id=1,
        minutes=900,
        appearances=12,
        listed_position="CM",
        stats={"appearances": 12.0},
    )
    with pytest.raises(TypeError, match="only PlayerObservation"):
        calculate_player_analytics_v2_result(  # type: ignore[arg-type]
            [season_observation], scope_key="core:test", calculated_at=_NOW
        )


def test_goalkeeper_match_metadata_never_uses_goalkeeper_season_definition() -> None:
    observation = _observation(
        player_id=1,
        player_name="Match Keeper",
        match_id=1,
        minutes=90,
        listed_position="GK",
        stats={"clean_sheets": 1.0},
    )
    result = calculate_player_analytics_v2_result(
        [observation], scope_key="core:test", calculated_at=_NOW
    )
    feature = next(item for item in result.features if item.metric_name == "clean_sheets")

    assert feature.metric_granularity == "goalkeeper_match"
    assert feature.metric_unit == "boolean"
    assert GOALKEEPER_MATCH_CATALOG["clean_sheets"][1].unit == "boolean"
    assert GOALKEEPER_SEASON_CATALOG["clean_sheets"][1].unit == "count"


def test_explicit_season_contract_keeps_player_and_goalkeeper_grains_separate() -> None:
    player_season = PlayerSeasonObservation(
        player_id=1,
        player_name="Season Player",
        season_id=1,
        season_label="2025/26",
        team_id=1,
        minutes=900,
        appearances=12,
        listed_position="CM",
        stats={"appearances": 12.0},
    )
    goalkeeper_season = GoalkeeperSeasonObservation(
        player_id=2,
        player_name="Season Keeper",
        season_id=1,
        season_label="2025/26",
        team_id=1,
        minutes=900,
        appearances=10,
        stats={"save_pct": 75.0},
    )

    player_catalog = season_catalog_for_observation(player_season)
    goalkeeper_catalog = season_catalog_for_observation(goalkeeper_season)
    assert player_catalog["appearances"][0] == "player_season"
    assert goalkeeper_catalog["save_pct"][0] == "goalkeeper_season"
    assert GOALKEEPER_MATCH_CATALOG["save_pct"][0] == "goalkeeper_match"
