from __future__ import annotations

from football_intelligence.providers.wyscout_spatial_v1 import (
    CoordinateParseResult,
    PitchPoint,
    classify_long_pass,
    is_accurate,
    is_pass_into_final_third,
    is_progressive_pass,
    parse_pass_coordinates,
)


def _valid_coordinates(start_x: float, end_x: float, *, y: float = 34.0) -> CoordinateParseResult:
    return CoordinateParseResult(
        start=PitchPoint(start_x, y),
        end=PitchPoint(end_x, y),
        valid=True,
        invalid_reason=None,
    )


def test_progressive_pass_thresholds_are_inclusive() -> None:
    assert is_progressive_pass(PitchPoint(0.0, 34.0), PitchPoint(30.0, 34.0))
    assert not is_progressive_pass(PitchPoint(0.0, 34.0), PitchPoint(29.999, 34.0))

    assert is_progressive_pass(PitchPoint(40.0, 34.0), PitchPoint(55.0, 34.0))
    assert not is_progressive_pass(PitchPoint(40.0, 34.0), PitchPoint(54.999, 34.0))

    assert is_progressive_pass(PitchPoint(60.0, 34.0), PitchPoint(70.0, 34.0))
    assert not is_progressive_pass(PitchPoint(60.0, 34.0), PitchPoint(69.999, 34.0))


def test_progressive_pass_never_counts_opponent_half_to_own_half() -> None:
    assert not is_progressive_pass(PitchPoint(70.0, 34.0), PitchPoint(40.0, 34.0))


def test_final_third_boundary_requires_start_outside() -> None:
    assert is_pass_into_final_third(PitchPoint(69.999, 34.0), PitchPoint(70.0, 34.0))
    assert not is_pass_into_final_third(PitchPoint(70.0, 34.0), PitchPoint(80.0, 34.0))


def test_long_pass_thresholds_are_strict() -> None:
    high_exact = _valid_coordinates(10.0, 35.0)
    high_over = _valid_coordinates(10.0, 35.001)
    assert classify_long_pass(sub_event_name="High pass", coordinates=high_exact) == "not_long"
    assert classify_long_pass(sub_event_name="High pass", coordinates=high_over) == "long"

    ground_exact = _valid_coordinates(10.0, 55.0)
    ground_over = _valid_coordinates(10.0, 55.001)
    assert classify_long_pass(sub_event_name="Simple pass", coordinates=ground_exact) == "not_long"
    assert classify_long_pass(sub_event_name="Simple pass", coordinates=ground_over) == "long"


def test_launch_and_cross_are_classifiable_without_geometry() -> None:
    invalid = CoordinateParseResult(None, None, False, "missing_positions")
    assert classify_long_pass(sub_event_name="Launch", coordinates=invalid) == "long"
    assert classify_long_pass(sub_event_name="Cross", coordinates=invalid) == "not_long"
    assert classify_long_pass(sub_event_name="High pass", coordinates=invalid) == "ambiguous"
    assert classify_long_pass(sub_event_name="Simple pass", coordinates=invalid) == "ambiguous"


def test_zero_zero_endpoint_is_missing_not_a_real_location() -> None:
    parsed = parse_pass_coordinates(
        {
            "positions": [
                {"x": 25, "y": 50},
                {"x": 0, "y": 0},
            ]
        }
    )
    assert not parsed.valid
    assert parsed.start is not None
    assert parsed.end is None
    assert parsed.invalid_reason == "zero_zero_endpoint_sentinel"


def test_start_zero_zero_is_not_rejected() -> None:
    parsed = parse_pass_coordinates(
        {
            "positions": [
                {"x": 0, "y": 0},
                {"x": 20, "y": 50},
            ]
        }
    )
    assert parsed.valid
    assert parsed.start is not None
    assert parsed.end is not None


def test_accuracy_comes_only_from_wyscout_tag_1801() -> None:
    assert is_accurate({"tags": [{"id": 1801}]})
    assert not is_accurate({"tags": [{"id": 1802}]})
    assert not is_accurate({"tags": []})
