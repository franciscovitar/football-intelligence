"""Audit whether Wyscout's next event can recover missing Cross endpoints.

This is a read-only laboratory. It validates deterministic next-touch candidate
rules against Cross events whose source endpoint is already known before
reporting what those rules would recover for the historical ``(0, 0)`` Cross
endpoint sentinel. It never emits canonical observations or changes Player V2.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football_intelligence.jobs.wyscout_historical_scope import (
    load_scope_inputs,
    scope_config,
    validate_source_scope,
)

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
MAX_LOOKAHEAD_EVENTS = 8
MAX_DELTA_SECONDS = 5.0
ACCURATE_TAG = 1801
INACCURATE_TAG = 1802


class CrossEndpointAuditError(RuntimeError):
    """The lab cannot produce a trustworthy report from the cached source."""


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class Candidate:
    point: Point
    offset: int
    delta_seconds: float
    event_name: str
    sub_event_name: str
    same_team: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit Wyscout Cross endpoint recovery from subsequent event starts."
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _point(value: Any) -> Point | None:
    if not isinstance(value, dict):
        return None
    x = _number(value.get("x"))
    y = _number(value.get("y"))
    if x is None or y is None or not (0.0 <= x <= 100.0 and 0.0 <= y <= 100.0):
        return None
    return Point(x=x, y=y)


def _event_start(event: dict[str, Any]) -> Point | None:
    positions = event.get("positions")
    if not isinstance(positions, list) or not positions:
        return None
    point = _point(positions[0])
    if point == Point(0.0, 0.0):
        return None
    return point


def _event_end(event: dict[str, Any]) -> Point | None:
    positions = event.get("positions")
    if not isinstance(positions, list) or len(positions) < 2:
        return None
    point = _point(positions[1])
    if point == Point(0.0, 0.0):
        return None
    return point


def _has_zero_zero_endpoint(event: dict[str, Any]) -> bool:
    positions = event.get("positions")
    if not isinstance(positions, list) or len(positions) < 2:
        return False
    return _point(positions[1]) == Point(0.0, 0.0)


def _tag_ids(event: dict[str, Any]) -> set[int]:
    tags = event.get("tags")
    if not isinstance(tags, list):
        return set()
    result: set[int] = set()
    for item in tags:
        if not isinstance(item, dict):
            continue
        tag_id = item.get("id")
        if isinstance(tag_id, int):
            result.add(tag_id)
    return result


def _accuracy(event: dict[str, Any]) -> bool | None:
    tags = _tag_ids(event)
    accurate = ACCURATE_TAG in tags
    inaccurate = INACCURATE_TAG in tags
    if accurate == inaccurate:
        return None
    return accurate


def _rotate_opponent_point(point: Point) -> Point:
    return Point(x=100.0 - point.x, y=100.0 - point.y)


def _distance_m(first: Point, second: Point) -> float:
    dx = (first.x - second.x) * PITCH_LENGTH_M / 100.0
    dy = (first.y - second.y) * PITCH_WIDTH_M / 100.0
    return math.hypot(dx, dy)


def _event_sec(event: dict[str, Any]) -> float | None:
    return _number(event.get("eventSec"))


def _candidate_from_event(
    pass_event: dict[str, Any],
    candidate_event: dict[str, Any],
    *,
    offset: int,
) -> Candidate | None:
    passer_team = pass_event.get("teamId")
    candidate_team = candidate_event.get("teamId")
    if not isinstance(passer_team, int) or not isinstance(candidate_team, int):
        return None
    start = _event_start(candidate_event)
    if start is None:
        return None
    pass_sec = _event_sec(pass_event)
    candidate_sec = _event_sec(candidate_event)
    if pass_sec is None or candidate_sec is None:
        return None
    delta = candidate_sec - pass_sec
    if delta < -1e-6 or delta > MAX_DELTA_SECONDS:
        return None
    same_team = candidate_team == passer_team
    point = start if same_team else _rotate_opponent_point(start)
    return Candidate(
        point=point,
        offset=offset,
        delta_seconds=delta,
        event_name=str(candidate_event.get("eventName") or ""),
        sub_event_name=str(candidate_event.get("subEventName") or ""),
        same_team=same_team,
    )


def _find_first_spatial_candidate(
    events: list[dict[str, Any]], index: int
) -> Candidate | None:
    source = events[index]
    period = source.get("matchPeriod")
    for offset in range(1, MAX_LOOKAHEAD_EVENTS + 1):
        candidate_index = index + offset
        if candidate_index >= len(events):
            break
        candidate_event = events[candidate_index]
        if candidate_event.get("matchPeriod") != period:
            break
        candidate = _candidate_from_event(source, candidate_event, offset=offset)
        if candidate is not None:
            return candidate
    return None


def _find_outcome_consistent_candidate(
    events: list[dict[str, Any]], index: int
) -> Candidate | None:
    source = events[index]
    accurate = _accuracy(source)
    if accurate is None:
        return None
    period = source.get("matchPeriod")
    for offset in range(1, MAX_LOOKAHEAD_EVENTS + 1):
        candidate_index = index + offset
        if candidate_index >= len(events):
            break
        candidate_event = events[candidate_index]
        if candidate_event.get("matchPeriod") != period:
            break
        candidate = _candidate_from_event(source, candidate_event, offset=offset)
        if candidate is None:
            continue
        if candidate.same_team == accurate:
            return candidate
    return None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 4) if denominator else 0.0


def _candidate_diagnostics(
    controls: list[tuple[dict[str, Any], Candidate | None, Point]],
) -> dict[str, Any]:
    candidates = [
        (event, candidate, endpoint)
        for event, candidate, endpoint in controls
        if candidate
    ]
    errors = [_distance_m(candidate.point, endpoint) for _, candidate, endpoint in candidates]
    event_names = Counter(candidate.event_name for _, candidate, _ in candidates)
    sub_events = Counter(candidate.sub_event_name for _, candidate, _ in candidates)
    offsets = Counter(candidate.offset for _, candidate, _ in candidates)
    accurate_controls = [item for item in candidates if _accuracy(item[0]) is True]
    inaccurate_controls = [item for item in candidates if _accuracy(item[0]) is False]
    exact_match = sum(
        candidate.point == endpoint for _, candidate, endpoint in candidates
    )
    return {
        "controls": len(controls),
        "candidate_available": len(candidates),
        "candidate_available_pct": _pct(len(candidates), len(controls)),
        "exact_coordinate_match": exact_match,
        "exact_coordinate_match_pct": _pct(exact_match, len(candidates)),
        "within_1m": sum(error <= 1.0 for error in errors),
        "within_1m_pct": _pct(sum(error <= 1.0 for error in errors), len(errors)),
        "within_3m": sum(error <= 3.0 for error in errors),
        "within_3m_pct": _pct(sum(error <= 3.0 for error in errors), len(errors)),
        "within_5m": sum(error <= 5.0 for error in errors),
        "within_5m_pct": _pct(sum(error <= 5.0 for error in errors), len(errors)),
        "error_m": {
            "median": round(statistics.median(errors), 4) if errors else None,
            "p95": None if not errors else round(_percentile(errors, 0.95) or 0.0, 4),
            "p99": None if not errors else round(_percentile(errors, 0.99) or 0.0, 4),
            "max": round(max(errors), 4) if errors else None,
        },
        "candidate_offsets": dict(sorted(offsets.items())),
        "candidate_event_names": dict(event_names.most_common(12)),
        "candidate_sub_event_names": dict(sub_events.most_common(20)),
        "accurate_controls_with_candidate": len(accurate_controls),
        "inaccurate_controls_with_candidate": len(inaccurate_controls),
    }


def _recovery_diagnostics(
    rows: list[tuple[dict[str, Any], Candidate | None]],
) -> dict[str, Any]:
    candidates = [(event, candidate) for event, candidate in rows if candidate]
    event_names = Counter(candidate.event_name for _, candidate in candidates)
    sub_events = Counter(candidate.sub_event_name for _, candidate in candidates)
    offsets = Counter(candidate.offset for _, candidate in candidates)
    accurate = sum(_accuracy(event) is True for event, _ in candidates)
    inaccurate = sum(_accuracy(event) is False for event, _ in candidates)
    deltas = [candidate.delta_seconds for _, candidate in candidates]
    return {
        "missing_crosses": len(rows),
        "candidate_available": len(candidates),
        "candidate_available_pct": _pct(len(candidates), len(rows)),
        "accurate": accurate,
        "inaccurate": inaccurate,
        "candidate_offsets": dict(sorted(offsets.items())),
        "candidate_event_names": dict(event_names.most_common(12)),
        "candidate_sub_event_names": dict(sub_events.most_common(20)),
        "delta_seconds": {
            "median": round(statistics.median(deltas), 4) if deltas else None,
            "p95": None if not deltas else round(_percentile(deltas, 0.95) or 0.0, 4),
            "max": round(max(deltas), 4) if deltas else None,
        },
    }


def _group_events(events_payload: list[Any]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in events_payload:
        if not isinstance(item, dict):
            continue
        match_id = item.get("matchId")
        if isinstance(match_id, int):
            grouped[match_id].append(item)
    return dict(grouped)


def run_audit(cache_dir: Path) -> dict[str, Any]:
    config = scope_config("ENG_PL")
    matches, events_payload, _, _ = load_scope_inputs(cache_dir, config=config)
    source_validation = validate_source_scope(
        matches_payload=matches,
        events_payload=events_payload,
        config=config,
    )
    if not source_validation.passed:
        raise CrossEndpointAuditError("; ".join(source_validation.failures))

    grouped = _group_events(events_payload)
    cross_events = 0
    cross_controls = 0
    missing_crosses = 0
    invalid_outcome_tags = 0
    immediate_controls: list[tuple[dict[str, Any], Candidate | None, Point]] = []
    outcome_controls: list[tuple[dict[str, Any], Candidate | None, Point]] = []
    immediate_missing: list[tuple[dict[str, Any], Candidate | None]] = []
    outcome_missing: list[tuple[dict[str, Any], Candidate | None]] = []

    for match_events in grouped.values():
        for index, event in enumerate(match_events):
            if event.get("eventName") != "Pass" or event.get("subEventName") != "Cross":
                continue
            cross_events += 1
            if _accuracy(event) is None:
                invalid_outcome_tags += 1
            endpoint = _event_end(event)
            if endpoint is not None:
                cross_controls += 1
                immediate_controls.append(
                    (event, _find_first_spatial_candidate(match_events, index), endpoint)
                )
                outcome_controls.append(
                    (event, _find_outcome_consistent_candidate(match_events, index), endpoint)
                )
            elif _has_zero_zero_endpoint(event):
                missing_crosses += 1
                immediate_missing.append(
                    (event, _find_first_spatial_candidate(match_events, index))
                )
                outcome_missing.append(
                    (event, _find_outcome_consistent_candidate(match_events, index))
                )

    immediate_report = _candidate_diagnostics(immediate_controls)
    outcome_report = _candidate_diagnostics(outcome_controls)
    gate = {
        "candidate_available_pct_min": 95.0,
        "within_3m_pct_min": 95.0,
        "median_error_m_max": 1.0,
        "p95_error_m_max": 3.0,
    }
    observed_median = outcome_report["error_m"]["median"]
    observed_p95 = outcome_report["error_m"]["p95"]
    gate_passed = bool(
        outcome_report["candidate_available_pct"] >= gate["candidate_available_pct_min"]
        and outcome_report["within_3m_pct"] >= gate["within_3m_pct_min"]
        and isinstance(observed_median, int | float)
        and observed_median <= gate["median_error_m_max"]
        and isinstance(observed_p95, int | float)
        and observed_p95 <= gate["p95_error_m_max"]
    )

    return {
        "execution_status": "PASS",
        "scope": {"competition": "ENG_PL", "season": "2017/18"},
        "methodology_status": "RECOVERY_CANDIDATE" if gate_passed else "NOT_VALIDATED",
        "source": {
            "matches": source_validation.match_count,
            "events": source_validation.event_count,
            "cross_events": cross_events,
            "cross_controls_with_source_endpoint": cross_controls,
            "cross_zero_zero_endpoints": missing_crosses,
            "crosses_with_invalid_outcome_tags": invalid_outcome_tags,
        },
        "rules": {
            "first_spatial_event": immediate_report,
            "first_outcome_consistent_spatial_event": outcome_report,
        },
        "validation_gate": {**gate, "passed": gate_passed},
        "zero_zero_cross_recovery_candidate": {
            "first_spatial_event": _recovery_diagnostics(immediate_missing),
            "first_outcome_consistent_spatial_event": _recovery_diagnostics(outcome_missing),
            "warning": (
                "Candidate endpoints are laboratory evidence only. They must not be emitted as "
                "canonical spatial metrics unless the control validation gate passes and the "
                "resulting progressive/final-third methodology is separately promoted."
            ),
        },
    }


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = run_audit(args.cache_dir)
    except (CrossEndpointAuditError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"WYSCOUT CROSS ENDPOINT AUDIT: FAIL - {exc}") from exc
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
