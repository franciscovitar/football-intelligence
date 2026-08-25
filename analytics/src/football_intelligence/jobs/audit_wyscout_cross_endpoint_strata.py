"""Stratify Wyscout Cross endpoint recovery on source-defined cohorts.

The broad next-event recovery rule failed its control gate. This follow-up lab
therefore tests only cohorts motivated by the observed zero-endpoint source:
inaccurate/blocked crosses and the immediate opponent event subtypes that
actually dominate those rows. No reconstructed endpoint is persisted.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from football_intelligence.jobs.audit_wyscout_cross_endpoint_recovery import (
    Candidate,
    CrossEndpointAuditError,
    Point,
    _accuracy,
    _distance_m,
    _event_end,
    _find_outcome_consistent_candidate,
    _has_zero_zero_endpoint,
    _pct,
    _tag_ids,
)
from football_intelligence.jobs.wyscout_historical_scope import (
    load_scope_inputs,
    scope_config,
    validate_source_scope,
)

BLOCKED_TAG = 2101
HIGH_TAG = 801
LOW_TAG = 802
TARGET_SUB_EVENTS = (
    "Touch",
    "Goalkeeper leaving line",
    "Save attempt",
    "Clearance",
)


class CrossEndpointStrataAuditError(RuntimeError):
    """The stratified lab cannot produce a trustworthy source-backed report."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit source-defined strata for Wyscout Cross endpoint recovery."
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _diagnostics(
    rows: list[tuple[dict[str, Any], Candidate, Point]],
) -> dict[str, Any]:
    errors = [_distance_m(candidate.point, endpoint) for _, candidate, endpoint in rows]
    exact = sum(candidate.point == endpoint for _, candidate, endpoint in rows)
    within_1 = sum(error <= 1.0 for error in errors)
    within_3 = sum(error <= 3.0 for error in errors)
    p95 = _percentile(errors, 0.95)
    return {
        "controls": len(rows),
        "exact": exact,
        "exact_pct": _pct(exact, len(rows)),
        "within_1m": within_1,
        "within_1m_pct": _pct(within_1, len(rows)),
        "within_3m": within_3,
        "within_3m_pct": _pct(within_3, len(rows)),
        "error_m": {
            "median": round(statistics.median(errors), 4) if errors else None,
            "p95": round(p95, 4) if p95 is not None else None,
            "max": round(max(errors), 4) if errors else None,
        },
    }


def _precision_gate(report: dict[str, Any]) -> bool:
    p95 = report["error_m"]["p95"]
    return bool(
        report["controls"] >= 100
        and report["exact_pct"] >= 95.0
        and report["within_3m_pct"] >= 98.0
        and isinstance(p95, int | float)
        and p95 <= 3.0
    )


def _group_events(events_payload: list[Any]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in events_payload:
        if not isinstance(item, dict):
            continue
        match_id = item.get("matchId")
        if isinstance(match_id, int):
            grouped[match_id].append(item)
    return dict(grouped)


def _tag_profile(event: dict[str, Any]) -> tuple[bool | None, bool, str]:
    tags = _tag_ids(event)
    height = "blocked" if BLOCKED_TAG in tags else "high" if HIGH_TAG in tags else "low" if LOW_TAG in tags else "other"
    return _accuracy(event), BLOCKED_TAG in tags, height


def _source_profile(events: list[dict[str, Any]]) -> dict[str, Any]:
    accuracy = Counter()
    height = Counter()
    blocked = 0
    tag_sets = Counter()
    for event in events:
        event_accuracy, is_blocked, height_label = _tag_profile(event)
        accuracy[str(event_accuracy)] += 1
        height[height_label] += 1
        blocked += int(is_blocked)
        tag_sets[tuple(sorted(_tag_ids(event)))] += 1
    return {
        "events": len(events),
        "accuracy": dict(accuracy),
        "blocked": blocked,
        "blocked_pct": _pct(blocked, len(events)),
        "height": dict(height),
        "most_common_tag_sets": [
            {"tags": list(tags), "events": count}
            for tags, count in tag_sets.most_common(12)
        ],
    }


def run_audit(cache_dir: Path) -> dict[str, Any]:
    config = scope_config("ENG_PL")
    matches, events_payload, _, _ = load_scope_inputs(cache_dir, config=config)
    validation = validate_source_scope(
        matches_payload=matches,
        events_payload=events_payload,
        config=config,
    )
    if not validation.passed:
        raise CrossEndpointStrataAuditError("; ".join(validation.failures))

    grouped = _group_events(events_payload)
    known_events: list[dict[str, Any]] = []
    zero_events: list[dict[str, Any]] = []
    known_rows: list[tuple[dict[str, Any], Candidate, Point]] = []
    zero_candidates: list[tuple[dict[str, Any], Candidate]] = []

    for match_events in grouped.values():
        for index, event in enumerate(match_events):
            if event.get("eventName") != "Pass" or event.get("subEventName") != "Cross":
                continue
            endpoint = _event_end(event)
            candidate = _find_outcome_consistent_candidate(match_events, index)
            if endpoint is not None:
                known_events.append(event)
                if candidate is not None and candidate.offset == 1:
                    known_rows.append((event, candidate, endpoint))
            elif _has_zero_zero_endpoint(event):
                zero_events.append(event)
                if candidate is not None and candidate.offset == 1:
                    zero_candidates.append((event, candidate))

    strata: dict[str, list[tuple[dict[str, Any], Candidate, Point]]] = {
        "inaccurate_immediate_opponent": [],
        "inaccurate_blocked_immediate_opponent": [],
        "inaccurate_not_blocked_immediate_opponent": [],
    }
    for sub_event in TARGET_SUB_EVENTS:
        strata[f"inaccurate_immediate_{sub_event}"] = []
        strata[f"inaccurate_blocked_immediate_{sub_event}"] = []
        strata[f"inaccurate_not_blocked_immediate_{sub_event}"] = []

    for event, candidate, endpoint in known_rows:
        if _accuracy(event) is not False or candidate.same_team:
            continue
        blocked = BLOCKED_TAG in _tag_ids(event)
        strata["inaccurate_immediate_opponent"].append((event, candidate, endpoint))
        blocked_key = (
            "inaccurate_blocked_immediate_opponent"
            if blocked
            else "inaccurate_not_blocked_immediate_opponent"
        )
        strata[blocked_key].append((event, candidate, endpoint))
        if candidate.sub_event_name in TARGET_SUB_EVENTS:
            base = f"inaccurate_immediate_{candidate.sub_event_name}"
            strata[base].append((event, candidate, endpoint))
            qualifier = "blocked" if blocked else "not_blocked"
            strata[f"inaccurate_{qualifier}_immediate_{candidate.sub_event_name}"].append(
                (event, candidate, endpoint)
            )

    stratum_reports: dict[str, Any] = {}
    for name, rows in strata.items():
        diagnostics = _diagnostics(rows)
        stratum_reports[name] = {
            **diagnostics,
            "precision_gate_passed": _precision_gate(diagnostics),
        }

    zero_candidate_sub_events = Counter(candidate.sub_event_name for _, candidate in zero_candidates)
    zero_candidate_event_names = Counter(candidate.event_name for _, candidate in zero_candidates)
    zero_blocked_by_sub_event: dict[str, dict[str, int]] = {}
    for sub_event in TARGET_SUB_EVENTS:
        rows = [(event, candidate) for event, candidate in zero_candidates if candidate.sub_event_name == sub_event]
        blocked = sum(BLOCKED_TAG in _tag_ids(event) for event, _ in rows)
        zero_blocked_by_sub_event[sub_event] = {
            "events": len(rows),
            "blocked": blocked,
            "not_blocked": len(rows) - blocked,
        }

    passing_strata = [name for name, report in stratum_reports.items() if report["precision_gate_passed"]]
    return {
        "execution_status": "PASS",
        "methodology_status": "STRATUM_CANDIDATE" if passing_strata else "NO_VALIDATED_STRATUM",
        "scope": {"competition": "ENG_PL", "season": "2017/18"},
        "source": {
            "matches": validation.match_count,
            "events": validation.event_count,
            "known_endpoint_crosses": len(known_events),
            "zero_zero_crosses": len(zero_events),
        },
        "source_profiles": {
            "known_endpoint_crosses": _source_profile(known_events),
            "zero_zero_crosses": _source_profile(zero_events),
        },
        "control_strata": stratum_reports,
        "precision_gate": {
            "minimum_controls": 100,
            "exact_pct_min": 95.0,
            "within_3m_pct_min": 98.0,
            "p95_error_m_max": 3.0,
            "passing_strata": passing_strata,
        },
        "zero_zero_immediate_outcome_consistent_candidates": {
            "available": len(zero_candidates),
            "available_pct": _pct(len(zero_candidates), len(zero_events)),
            "event_names": dict(zero_candidate_event_names.most_common()),
            "sub_event_names": dict(zero_candidate_sub_events.most_common()),
            "blocked_by_target_sub_event": zero_blocked_by_sub_event,
        },
        "warning": (
            "A passing stratum is only a candidate for further methodology review. "
            "This lab does not emit reconstructed endpoints or spatial metrics."
        ),
    }


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = run_audit(args.cache_dir)
    except (
        CrossEndpointAuditError,
        CrossEndpointStrataAuditError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SystemExit(f"WYSCOUT CROSS STRATA AUDIT: FAIL - {exc}") from exc
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
