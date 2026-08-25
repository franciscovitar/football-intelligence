"""Pure spatial primitives for the Wyscout Open Data v1 laboratory.

These helpers implement the currently audited Football Intelligence Wyscout
spatial methodology. They do not emit canonical observations and do not write
to the database.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

METHODOLOGY_ID = "fi-wyscout-spatial-v1.1"
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
HALFWAY_X_M = PITCH_LENGTH_M / 2.0
FINAL_THIRD_X_M = PITCH_LENGTH_M * 2.0 / 3.0
OPPONENT_GOAL_X_M = PITCH_LENGTH_M
OPPONENT_GOAL_Y_M = PITCH_WIDTH_M / 2.0

ACCURATE_TAG = 1801

# Historical Open Data subevents do not expose the current Long Ground subtype
# independently. Keep the fallback narrow: Simple pass is the generic historical
# pass subtype, while Wyscout explicitly documents that Smart pass can also be a
# long ground pass. Cross, Hand pass and Head pass are distinct pass concepts and
# must never become long-ground passes solely because their geometry exceeds 45 m.
_GROUND_LONG_CANDIDATE_SUBEVENTS = frozenset({"Simple pass", "Smart pass"})
_EXPLICIT_NON_LONG_SUBEVENTS = frozenset({"Cross", "Hand pass", "Head pass"})


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
    """Classify a historical Wyscout ``Pass`` conservatively.

    Current Wyscout semantics define long passes as Launch, High (>25 m), or
    Long Ground (>45 m). Historical Open Data has Launch and High pass but no
    dedicated Long Ground subtype. ``Simple pass`` and ``Smart pass`` are the
    only historical subtypes v1.1 permits to become long-ground passes from
    geometry. Cross, Hand pass and Head pass remain distinct non-long concepts.
    Unknown subtypes stay ambiguous instead of inheriting ground semantics.
    """

    if sub_event_name == "Launch":
        return "long"
    if sub_event_name in _EXPLICIT_NON_LONG_SUBEVENTS:
        return "not_long"

    if sub_event_name == "High pass":
        if not coordinates.valid or coordinates.start is None or coordinates.end is None:
            return "ambiguous"
        return "long" if pass_length_m(coordinates.start, coordinates.end) > 25.0 else "not_long"

    if sub_event_name in _GROUND_LONG_CANDIDATE_SUBEVENTS:
        if not coordinates.valid or coordinates.start is None or coordinates.end is None:
            return "ambiguous"
        return "long" if pass_length_m(coordinates.start, coordinates.end) > 45.0 else "not_long"

    return "ambiguous"


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
    x_pct = _finite_float(raw.get("x"))
    y_pct = _finite_float(raw.get("y"))
    if x_pct is None or y_pct is None:
        return None
    if not (0.0 <= x_pct <= 100.0 and 0.0 <= y_pct <= 100.0):
        return None
    return PitchPoint(
        x_m=PITCH_LENGTH_M * x_pct / 100.0,
        y_m=PITCH_WIDTH_M * y_pct / 100.0,
    )


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None
