from __future__ import annotations

from football_intelligence.player_analytics.config import FEATURE_METRICS
from football_intelligence.position_profiles import (
    POSITION_FAMILY_SCORE_WEIGHTS,
    classify_position_family,
)
from football_intelligence.position_profiles.config import FINE_POSITION_ALIASES


def test_every_fine_alias_family_is_classified() -> None:
    for token, family in FINE_POSITION_ALIASES.items():
        assert classify_position_family(token) == family
        # Lower-case / surrounding whitespace input should classify the same.
        assert classify_position_family(f" {token.lower()} ") == family


def test_unrecognized_token_falls_back_to_coarse_broad_role() -> None:
    # "D" is not a fine token but is a valid ROLE_ALIASES broad role -- V1
    # could already classify it, so V2 must not silently drop it to None.
    assert classify_position_family("D") == "defender"
    assert classify_position_family("M") == "midfielder"
    assert classify_position_family("F") == "forward"
    assert classify_position_family("G") == "goalkeeper"


def test_unknown_token_returns_none_never_guessed() -> None:
    assert classify_position_family("SWEEPER") is None
    assert classify_position_family(None) is None
    assert classify_position_family("") is None
    assert classify_position_family("   ") is None


def test_goalkeeper_profile_never_includes_shot_or_xg_style_weights() -> None:
    weights = POSITION_FAMILY_SCORE_WEIGHTS["goalkeeper"]
    metric_names = {name for name, _, _ in weights}
    assert metric_names == {"saves"}


def test_centre_back_profile_is_not_dominated_by_shooting_metrics() -> None:
    forward_weights = POSITION_FAMILY_SCORE_WEIGHTS["forward"]
    centre_back_weights = POSITION_FAMILY_SCORE_WEIGHTS["centre_back"]

    shooting_metrics = {"goals", "shots_total", "shots_on_target"}
    forward_metric_names = {name for name, _, _ in forward_weights}
    centre_back_metric_names = {name for name, _, _ in centre_back_weights}

    assert shooting_metrics & forward_metric_names
    assert not (shooting_metrics & centre_back_metric_names)


def test_every_weight_profile_only_uses_wired_feature_metrics() -> None:
    for family, weights in POSITION_FAMILY_SCORE_WEIGHTS.items():
        for metric_name, weight, direction in weights:
            assert metric_name in FEATURE_METRICS, f"{family} uses un-scored metric {metric_name}"
            assert weight > 0
            assert direction in (1, -1)


def test_fullback_wingback_weights_creation_and_carrying_more_than_centre_back() -> None:
    fullback = dict(
        (name, weight) for name, weight, _ in POSITION_FAMILY_SCORE_WEIGHTS["fullback_wingback"]
    )
    centre_back = dict(
        (name, weight) for name, weight, _ in POSITION_FAMILY_SCORE_WEIGHTS["centre_back"]
    )
    assert fullback.get("dribbles_successful", 0.0) > centre_back.get("dribbles_successful", 0.0)
    assert fullback.get("key_passes", 0.0) > centre_back.get("key_passes", 0.0)


def test_all_eight_position_families_have_a_weight_profile() -> None:
    expected = {
        "goalkeeper",
        "centre_back",
        "fullback_wingback",
        "defensive_midfielder",
        "central_midfielder",
        "attacking_midfielder",
        "winger",
        "forward",
    }
    assert set(POSITION_FAMILY_SCORE_WEIGHTS.keys()) == expected
