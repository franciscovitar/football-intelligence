"""Conservative spatial derivations for historical Wyscout Open pass events.

The Wyscout Open event files express positions in provider-native percentages and
orient every action so the subject attacks toward x=100.  Football Intelligence
converts those percentages onto an explicit 105 x 68 metre reference pitch only
for derived geometry.  The conversion is an FI methodology choice, not a claim
that the provider recorded physical metres.

Current Wyscout glossary semantics are used for progressive passes and passes
into the final third.  Long-pass reconstruction remains diagnostic-only because
the historical Open Data pass subtype taxonomy does not expose a distinct
"Long Ground" subtype used by the current glossary.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any, Literal

METHODOLOGY_VERSION = "wyscout-spatial-105x68-v1.0"
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
HALF_X_PCT = 50.0
FINAL_THIRD_X_PCT = 200.0 / 3.0
ACCURATE_TAG = 1801
NOT_ACCURATE_TAG = 1802

ProgressiveZone = Literal["own_half", "different_halves", "opponent_half"]


@dataclass(frozen=True, slots=True)
class PitchPoint:
    """One validated provider-native Wyscout percentage coordinate."""

    x_pct: float
    y_pct: float

    @property
    def x_m(self) -> float:
        return self.x_pct * PITCH_LENGTH_M / 100.0

    @property
    def y_m(self) -> float:
        return self.y_pct * PITCH_WIDTH_M / 100.0

    @property
    def distance_to_opponent_goal_m(self) -> float:
        return hypot(PITCH_LENGTH_M - self.x_m, PITCH_WIDTH_M / 2.0 - self.y_m)


@dataclass(frozen=True, slots=True)
class PassGeometry:
    start: PitchPoint
    end: PitchPoint

    @property
    def length_m(self) -> float:
        return hypot(self.end.x_m - self.start.x_m, self.end.y_m - self.start.y_m)

    @property
    def goal_distance_gain_m(self) -> float:
        """How many metres closer the end point is to the opponent goal centre."""

        return self.start.distance_to_opponent_goal_m - self.end.distance_to_opponent_goal_m

    @property
    def is_forward(self) -> bool:
        return self.end.x_pct > self.start.x_pct


@dataclass(frozen=True, slots=True)
class ProgressivePassResult:
    progressive: bool
    zone: ProgressiveZone
    required_gain_m: float
    actual_gain_m: float


def parse_pass_geometry(event: object) -> PassGeometry | None:
    """Return validated start/end geometry for one native ``eventName=Pass`` event.

    Missing, malformed, out-of-range or non-pass positions stay missing.  No
    coordinate is clipped and no sentinel is converted to a real location.
    """

    if not isinstance(event, dict) or event.get("eventName") != "Pass":
        return None
    positions = event.get("positions")
    if not isinstance(positions, list) or len(positions) < 2:
        return None
    start = _parse_point(positions[0])
    end = _parse_point(positions[1])
    if start is None or end is None:
        return None
    return PassGeometry(start=start, end=end)


def classify_progressive_pass(event: object) -> ProgressivePassResult | None:
    """Classify a pass using Wyscout's current 30m / 15m / 10m rule.

    The provider definition also calls this a *forward* pass, so an action must
    move toward x=100 as well as satisfy the goal-distance gain threshold.
    """

    geometry = parse_pass_geometry(event)
    if geometry is None:
        return None
    zone, required_gain = _progressive_zone_and_threshold(geometry)
    actual_gain = geometry.goal_distance_gain_m
    return ProgressivePassResult(
        progressive=geometry.is_forward and actual_gain >= required_gain,
        zone=zone,
        required_gain_m=required_gain,
        actual_gain_m=actual_gain,
    )


def is_pass_into_final_third(event: object) -> bool | None:
    """Whether a pass starts outside and ends inside the attacking final third."""

    geometry = parse_pass_geometry(event)
    if geometry is None:
        return None
    return geometry.start.x_pct < FINAL_THIRD_X_PCT <= geometry.end.x_pct


def pass_success(event: object) -> bool | None:
    """Read Wyscout's mutually exclusive accurate/not-accurate pass tags."""

    if not isinstance(event, dict) or event.get("eventName") != "Pass":
        return None
    tags = event.get("tags")
    if not isinstance(tags, list):
        return None
    tag_ids = {
        item.get("id")
        for item in tags
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    accurate = ACCURATE_TAG in tag_ids
    inaccurate = NOT_ACCURATE_TAG in tag_ids
    if accurate == inaccurate:
        return None
    return accurate


def long_pass_diagnostic_bucket(event: object) -> str | None:
    """Conservative diagnostic bucket for historical long-pass reconstruction.

    Current Wyscout semantics include Launch, High (>25m) and Long Ground (>45m).
    Historical Open Data has Launch/High but no explicit Long Ground subtype, so
    generic >45m pass subtypes are reported as unresolved rather than promoted.
    """

    geometry = parse_pass_geometry(event)
    if geometry is None or not isinstance(event, dict):
        return None
    subtype = event.get("subEventName")
    if subtype == "Launch":
        return "launch"
    if subtype == "High pass":
        return "high_over_25m" if geometry.length_m > 25.0 else "high_at_or_below_25m"
    if geometry.length_m > 45.0:
        return f"unresolved_over_45m:{subtype or 'unknown'}"
    return "not_long_candidate"


def _parse_point(value: Any) -> PitchPoint | None:
    if not isinstance(value, dict):
        return None
    x = _number(value.get("x"))
    y = _number(value.get("y"))
    if x is None or y is None or not (0.0 <= x <= 100.0 and 0.0 <= y <= 100.0):
        return None
    return PitchPoint(x_pct=x, y_pct=y)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _progressive_zone_and_threshold(
    geometry: PassGeometry,
) -> tuple[ProgressiveZone, float]:
    start = geometry.start.x_pct
    end = geometry.end.x_pct
    if start <= HALF_X_PCT and end <= HALF_X_PCT:
        return "own_half", 30.0
    if start >= HALF_X_PCT and end >= HALF_X_PCT:
        return "opponent_half", 10.0
    return "different_halves", 15.0
