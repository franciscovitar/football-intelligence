from __future__ import annotations

from football_intelligence.providers.wyscout_spatial_v1 import (
    CoordinateParseResult,
    PitchPoint,
    classify_long_pass,
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


def test_progressive_thresholds_are_inclusive_but_not_promoted_by_helper_existence() -> None:
    assert is_progressive_pass(PitchPoint(0.0, 34.0), PitchPoint(30.0, 34.0))
    assert not is_progressive_pass(PitchPoint(0.0, 34.0), PitchPoint(29.999, 34.0))
    assert is_progressive_pass(PitchPoint(40.0, 34.0), PitchPoint(55.0, 34.0))
    assert is_progressive_pass(PitchPoint(60.0, 34.0), PitchPoint(70.0, 34.0))
    assert not is_progressive_pass(PitchPoint(70.0, 34.0), PitchPoint(40.0, 34.0))


def test_final_third_boundary_requires_start_outside() -> None:
    assert is_pass_into_final_third(PitchPoint(69.999, 34.0), PitchPoint(70.0, 34.0))
    assert not is_pass_into_final_third(PitchPoint(70.0, 34.0), PitchPoint(80.0, 34.0))


def test_long_pass_v1_1_uses_conservative_historical_taxonomy() -> None:
    high_exact = _valid_coordinates(10.0, 35.0)
    high_over = _valid_coordinates(10.0, 35.001)
    assert classify_long_pass(sub_event_name="High pass", coordinates=high_exact) == "not_long"
    assert classify_long_pass(sub_event_name="High pass", coordinates=high_over) == "long"

    ground_over = _valid_coordinates(10.0, 55.001)
    assert classify_long_pass(sub_event_name="Simple pass", coordinates=ground_over) == "long"
    assert classify_long_pass(sub_event_name="Smart pass", coordinates=ground_over) == "long"

    very_long = _valid_coordinates(0.0, 100.0)
    for subtype in ("Cross", "Hand pass", "Head pass"):
        assert classify_long_pass(sub_event_name=subtype, coordinates=very_long) == "not_long"


def test_long_pass_missing_semantics_do_not_impute_geometry() -> None:
    invalid = CoordinateParseResult(None, None, False, "missing_positions")
    assert classify_long_pass(sub_event_name="Launch", coordinates=invalid) == "long"
    assert classify_long_pass(sub_event_name="Cross", coordinates=invalid) == "not_long"
    assert classify_long_pass(sub_event_name="Hand pass", coordinates=invalid) == "not_long"
    assert classify_long_pass(sub_event_name="Head pass", coordinates=invalid) == "not_long"
    assert classify_long_pass(sub_event_name="High pass", coordinates=invalid) == "ambiguous"
    assert classify_long_pass(sub_event_name="Simple pass", coordinates=invalid) == "ambiguous"
    assert classify_long_pass(sub_event_name="Smart pass", coordinates=invalid) == "ambiguous"
    assert classify_long_pass(sub_event_name="Unknown pass", coordinates=invalid) == "ambiguous"


def test_zero_zero_endpoint_is_missing_not_a_real_location() -> None:
    parsed = parse_pass_coordinates({"positions": [{"x": 25, "y": 50}, {"x": 0, "y": 0}]})
    assert not parsed.valid
    assert parsed.start is not None
    assert parsed.end is None
    assert parsed.invalid_reason == "zero_zero_endpoint_sentinel"
