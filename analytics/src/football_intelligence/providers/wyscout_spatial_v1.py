"""Pure spatial primitives for the Wyscout Open Data v1 laboratory.

These helpers implement ``fi-wyscout-spatial-v1.0`` as specified in
``docs/WYSCOUT_SPATIAL_METHODOLOGY_V1.md``. They do not emit canonical
observations and do not write to the database.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

METHODOLOGY_ID = "fi-wyscout-spatial-v1.0"
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
HALFWAY_X_M = PITCH_LENGTH_M / 2.0
FINAL_THIRD_X_M = PITCH_LENGTH_M * 2.0 / 3.0
OPPONENT_GOAL_X_M = PITCH_LENGTH_M
OPPONENT_GOAL_Y_M = PITCH_WIDTH_M / 2.0

ACCURATE_TAG = 1801


@dataclass(frozen=True, slots=True)
class PitchPoint:
    x_m: float
    y_m: float


@dataclass(frozen=True, slots=True)
class CoordinateParseResult:
    start: PitchPoint | None
    end: PitchPoint | None
    valid: bool
    invalid_reason: str | None


LongPassClassification = Literal["long", "not_long", "ambiguous"]


def parse_pass_coordinates(event: dict[str, Any]) -> CoordinateParseResult:
    """Parse Wyscout percentage coordinates into the v1 105 x 68 m frame.

    The empirically observed pass endpoint ``(0, 0)`` is treated as an
    unavailable-location sentinel. A start at ``(0, 0)`` is not rejected:
    only the endpoint sentinel has been verified in the historical source.
    """

    positions = event.get("positions")
    if not isinstance(positions, list) or len(positions) < 2:
        return CoordinateParseResult(None, None, False, "missing_positions")

    start = _parse_percentage_point(positions[0])
    end = _parse_percentage_point(positions[1])
    if start is None or end is None:
        return CoordinateParseResult(None, None, False, "invalid_coordinate")

    raw_end = positions[1]
    if isinstance(raw_end, dict) and raw_end.get("x") == 0 and raw_end.get("y") == 0:
        return CoordinateParseResult(start, None, False, "zero_zero_endpoint_sentinel")

    return CoordinateParseResult(start, end, True, None)


def is_progressive_pass(start: PitchPoint, end: PitchPoint) -> bool:
    """Return whether a valid pass satisfies the Wyscout 30/15/10 m rule."""

    start_own = start.x_m < HALFWAY_X_M
    end_own = end.x_m < HALFWAY_X_M
    if not start_own and end_own:
        return False

    gain = distance_to_opponent_goal(start) - distance_to_opponent_goal(end)
    if gain <= 0.0:
        return False

    if start_own and end_own:
        threshold = 30.0
    elif start_own and not end_own:
        threshold = 15.0
    else:
        threshold = 10.0
    return gain >= threshold


def progressive_goal_distance_gain(start: PitchPoint, end: PitchPoint) -> float:
    """Goal-distance reduction used by the v1 progressive-pass definition."""

    return distance_to_opponent_goal(start) - distance_to_opponent_goal(end)


def is_pass_into_final_third(start: PitchPoint, end: PitchPoint) -> bool:
    """A pass must start outside and end inside/on the final-third boundary."""

    return start.x_m < FINAL_THIRD_X_M and end.x_m >= FINAL_THIRD_X_M


def pass_length_m(start: PitchPoint, end: PitchPoint) -> float:
    return math.hypot(end.x_m - start.x_m, end.y_m - start.y_m)


def classify_long_pass(
    *,
    sub_event_name: str | None,
    coordinates: CoordinateParseResult,
) -> LongPassClassification:
    """Classify one Wyscout ``Pass`` under the conservative v1 rule.

    ``Launch`` is directly a Wyscout long-pass type and therefore remains
    classifiable even when geometry is unavailable. ``Cross`` is directly
    excluded from geometry-based reclassification. ``High pass`` and all
    remaining non-cross historical pass subtypes require valid geometry.
    """

    if sub_event_name == "Launch":
        return "long"
    if sub_event_name == "Cross":
        return "not_long"
    if not coordinates.valid or coordinates.start is None or coordinates.end is None:
        return "ambiguous"

    length = pass_length_m(coordinates.start, coordinates.end)
    if sub_event_name == "High pass":
        return "long" if length > 25.0 else "not_long"
    return "long" if length > 45.0 else "not_long"


def is_accurate(event: dict[str, Any]) -> bool:
    tags = event.get("tags")
    if not isinstance(tags, list):
        return False
    return any(isinstance(tag, dict) and tag.get("id") == ACCURATE_TAG for tag in tags)


def distance_to_opponent_goal(point: PitchPoint) -> float:
    return math.hypot(OPPONENT_GOAL_X_M - point.x_m, OPPONENT_GOAL_Y_M - point.y_m)


def _parse_percentage_point(raw: Any) -> PitchPoint | None:
    if not isinstance(raw, dict):
        return None
    raw_x = raw.get("x")
    raw_y = raw.get("y")
    if not _is_number(raw_x) or not _is_number(raw_y):
        return None
    x_pct = float(raw_x)
    y_pct = float(raw_y)
    if not (0.0 <= x_pct <= 100.0 and 0.0 <= y_pct <= 100.0):
        return None
    return PitchPoint(
        x_m=PITCH_LENGTH_M * x_pct / 100.0,
        y_m=PITCH_WIDTH_M * y_pct / 100.0,
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
