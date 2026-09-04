from __future__ import annotations

from football_intelligence.providers.wyscout_spatial_metrics import (
    FINAL_THIRD_X_PCT,
    METHODOLOGY_VERSION,
    classify_progressive_pass,
    is_pass_into_final_third,
    long_pass_diagnostic_bucket,
    parse_pass_geometry,
    pass_success,
)


def _pass(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    subtype: str = "Simple pass",
    tags: tuple[int, ...] = (1801,),
) -> dict[str, object]:
    return {
        "eventName": "Pass",
        "subEventName": subtype,
        "positions": [
            {"x": start[0], "y": start[1]},
            {"x": end[0], "y": end[1]},
        ],
        "tags": [{"id": tag} for tag in tags],
    }


def test_methodology_is_explicitly_versioned() -> None:
    assert METHODOLOGY_VERSION == "wyscout-spatial-105x68-v1.0"


def test_progressive_pass_uses_30m_threshold_inside_own_half() -> None:
    result = classify_progressive_pass(_pass((10, 50), (40, 50)))

    assert result is not None
    assert result.zone == "own_half"
    assert result.required_gain_m == 30.0
    assert result.actual_gain_m > 30.0
    assert result.progressive is True


def test_progressive_pass_rejects_subthreshold_own_half_gain() -> None:
    result = classify_progressive_pass(_pass((20, 50), (45, 50)))

    assert result is not None
    assert result.actual_gain_m < 30.0
    assert result.progressive is False


def test_progressive_pass_uses_15m_threshold_across_halves() -> None:
    result = classify_progressive_pass(_pass((45, 50), (60, 50)))

    assert result is not None
    assert result.zone == "different_halves"
    assert result.required_gain_m == 15.0
    assert result.progressive is True


def test_progressive_pass_uses_10m_threshold_inside_opponent_half() -> None:
    result = classify_progressive_pass(_pass((60, 50), (70, 50)))

    assert result is not None
    assert result.zone == "opponent_half"
    assert result.required_gain_m == 10.0
    assert result.progressive is True


def test_backward_pass_never_becomes_progressive_from_lateral_geometry() -> None:
    result = classify_progressive_pass(_pass((80, 0), (79, 50)))

    assert result is not None
    assert result.actual_gain_m > 0
    assert result.progressive is False


def test_pass_into_final_third_requires_crossing_boundary() -> None:
    crossing = _pass((60, 50), (70, 50))
    already_inside = _pass((70, 50), (80, 50))
    stays_outside = _pass((50, 50), (60, 50))

    assert FINAL_THIRD_X_PCT > 66
    assert is_pass_into_final_third(crossing) is True
    assert is_pass_into_final_third(already_inside) is False
    assert is_pass_into_final_third(stays_outside) is False


def test_non_pass_and_invalid_coordinates_stay_missing() -> None:
    non_pass = _pass((20, 50), (60, 50)) | {"eventName": "Duel"}
    out_of_bounds = _pass((20, 50), (101, 50))
    missing_end = _pass((20, 50), (60, 50)) | {"positions": [{"x": 20, "y": 50}]}

    assert parse_pass_geometry(non_pass) is None
    assert parse_pass_geometry(out_of_bounds) is None
    assert parse_pass_geometry(missing_end) is None
    assert classify_progressive_pass(out_of_bounds) is None
    assert is_pass_into_final_third(missing_end) is None


def test_pass_success_fails_closed_on_ambiguous_tags() -> None:
    assert pass_success(_pass((20, 50), (60, 50), tags=(1801,))) is True
    assert pass_success(_pass((20, 50), (60, 50), tags=(1802,))) is False
    assert pass_success(_pass((20, 50), (60, 50), tags=())) is None
    assert pass_success(_pass((20, 50), (60, 50), tags=(1801, 1802))) is None


def test_long_pass_diagnostic_does_not_promote_unknown_ground_semantics() -> None:
    launch = _pass((10, 50), (60, 50), subtype="Launch")
    high = _pass((10, 50), (40, 50), subtype="High pass")
    simple_long = _pass((10, 50), (60, 50), subtype="Simple pass")

    assert long_pass_diagnostic_bucket(launch) == "launch"
    assert long_pass_diagnostic_bucket(high) == "high_over_25m"
    assert long_pass_diagnostic_bucket(simple_long) == "unresolved_over_45m:Simple pass"
