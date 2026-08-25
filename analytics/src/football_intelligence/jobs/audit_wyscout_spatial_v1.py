"""Empirical ENG_PL 2017/18 audit for ``fi-wyscout-spatial-v1.0``.

This laboratory reads only the already-cached official Wyscout Open Data
source. It never writes PostgreSQL and never emits canonical observations.
The purpose is to measure coverage, zero-vs-missing behavior, distributions,
and taxonomy risks before any spatial metric is activated in Player V2.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from football_intelligence.jobs.audit_wyscout_metric_mapping import (
    DEFAULT_CACHE_DIR,
    WyscoutMappingAuditError,
    load_cached_source,
)
from football_intelligence.providers.wyscout_spatial_v1 import (
    METHODOLOGY_ID,
    classify_long_pass,
    is_accurate,
    is_pass_into_final_third,
    is_progressive_pass,
    parse_pass_coordinates,
    pass_length_m,
)

EXPECTED_MATCH_COUNT = 380
EXPECTED_PASS_COUNT = 328657
ACCURATE_TAG = 1801
NOT_ACCURATE_TAG = 1802
_SENTINEL_PLAYER_ID = 0


@dataclass(slots=True)
class PlayerMatchSpatialAudit:
    passes_total: int = 0
    passes_accurate: int = 0
    progressive_passes: int = 0
    passes_into_final_third: int = 0
    long_passes: int = 0
    long_passes_accurate: int = 0
    progressive_ambiguous: bool = False
    final_third_ambiguous: bool = False
    long_ambiguous: bool = False
    invalid_pass_coordinates: int = 0


@dataclass(slots=True)
class SubEventLengthAudit:
    events: int = 0
    valid_geometry: int = 0
    over_25m: int = 0
    over_45m: int = 0
    lengths_m: list[float] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class MetricCoverage:
    ready: int
    missing: int
    true_zero: int
    positive: int

    @property
    def ready_pct(self) -> float:
        total = self.ready + self.missing
        return _pct(self.ready, total)


class WyscoutSpatialAuditError(RuntimeError):
    """The real-source spatial audit could not complete safely."""


def audit_spatial_v1(*, matches_payload: list[Any], events_payload: list[Any]) -> dict[str, Any]:
    if len(matches_payload) != EXPECTED_MATCH_COUNT:
        raise WyscoutSpatialAuditError(
            f"expected {EXPECTED_MATCH_COUNT} ENG_PL matches, got {len(matches_payload)}"
        )

    participating_pairs = _participating_player_matches(matches_payload)
    if not participating_pairs:
        raise WyscoutSpatialAuditError("no participating player-match identities found")

    player_match: dict[tuple[int, int], PlayerMatchSpatialAudit] = {
        pair: PlayerMatchSpatialAudit() for pair in participating_pairs
    }
    invalid_coordinate_reasons: Counter[str] = Counter()
    sub_event_lengths: dict[str, SubEventLengthAudit] = defaultdict(SubEventLengthAudit)
    orphan_passes = 0
    sentinel_actor_passes = 0
    pass_outcome_tag_errors = 0
    pass_count = 0
    valid_geometry_count = 0
    long_direct_launches = 0
    cross_events = 0

    for raw_event in events_payload:
        if not isinstance(raw_event, dict) or raw_event.get("eventName") != "Pass":
            continue
        pass_count += 1

        match_id = raw_event.get("matchId")
        player_id = raw_event.get("playerId")
        if not isinstance(match_id, int) or not isinstance(player_id, int):
            orphan_passes += 1
            continue
        if player_id == _SENTINEL_PLAYER_ID:
            sentinel_actor_passes += 1
            continue

        state = player_match.get((match_id, player_id))
        if state is None:
            orphan_passes += 1
            continue

        state.passes_total += 1
        accurate = is_accurate(raw_event)
        if accurate:
            state.passes_accurate += 1

        tags = raw_event.get("tags")
        tag_ids = {
            tag.get("id") for tag in tags if isinstance(tag, dict)
        } if isinstance(tags, list) else set()
        if (ACCURATE_TAG in tag_ids) == (NOT_ACCURATE_TAG in tag_ids):
            pass_outcome_tag_errors += 1

        sub_event_name_raw = raw_event.get("subEventName")
        sub_event_name = sub_event_name_raw if isinstance(sub_event_name_raw, str) else None
        sub_label = sub_event_name or "<missing>"
        sub_audit = sub_event_lengths[sub_label]
        sub_audit.events += 1

        coordinates = parse_pass_coordinates(raw_event)
        if coordinates.valid and coordinates.start is not None and coordinates.end is not None:
            valid_geometry_count += 1
            length = pass_length_m(coordinates.start, coordinates.end)
            sub_audit.valid_geometry += 1
            sub_audit.lengths_m.append(length)
            if length > 25.0:
                sub_audit.over_25m += 1
            if length > 45.0:
                sub_audit.over_45m += 1

            if is_progressive_pass(coordinates.start, coordinates.end):
                state.progressive_passes += 1
            if is_pass_into_final_third(coordinates.start, coordinates.end):
                state.passes_into_final_third += 1
        else:
            state.invalid_pass_coordinates += 1
            state.progressive_ambiguous = True
            state.final_third_ambiguous = True
            invalid_coordinate_reasons[coordinates.invalid_reason or "unknown"] += 1

        long_class = classify_long_pass(
            sub_event_name=sub_event_name,
            coordinates=coordinates,
        )
        if sub_event_name == "Launch":
            long_direct_launches += 1
        if sub_event_name == "Cross":
            cross_events += 1
        if long_class == "long":
            state.long_passes += 1
            if accurate:
                state.long_passes_accurate += 1
        elif long_class == "ambiguous":
            state.long_ambiguous = True

    if pass_count != EXPECTED_PASS_COUNT:
        raise WyscoutSpatialAuditError(
            f"expected {EXPECTED_PASS_COUNT} ENG_PL Pass events, got {pass_count}"
        )

    invariant_failures = _invariant_failures(player_match)
    season_rows = _aggregate_player_seasons(player_match)

    pm_progressive = _coverage(
        player_match.values(),
        value_attr="progressive_passes",
        missing_attr="progressive_ambiguous",
    )
    pm_final_third = _coverage(
        player_match.values(),
        value_attr="passes_into_final_third",
        missing_attr="final_third_ambiguous",
    )
    pm_long = _coverage(
        player_match.values(),
        value_attr="long_passes_accurate",
        missing_attr="long_ambiguous",
    )

    season_progressive = _season_coverage(
        season_rows,
        value_key="progressive_passes",
        missing_key="progressive_missing",
    )
    season_final_third = _season_coverage(
        season_rows,
        value_key="passes_into_final_third",
        missing_key="final_third_missing",
    )
    season_long = _season_coverage(
        season_rows,
        value_key="long_passes_accurate",
        missing_key="long_missing",
    )

    ready_spatial_seasons = [
        row
        for row in season_rows.values()
        if not row["progressive_missing"]
        and not row["final_third_missing"]
        and not row["long_missing"]
    ]
    passing_input_proxy = [row for row in ready_spatial_seasons if row["passes_total"] > 0]

    non_ground_named_candidates = sum(
        sub_event_lengths[name].over_45m for name in ("Hand pass", "Head pass")
    )
    structural_failures: list[str] = []
    if orphan_passes:
        structural_failures.append(f"orphan_passes={orphan_passes}")
    if sentinel_actor_passes:
        structural_failures.append(f"sentinel_actor_passes={sentinel_actor_passes}")
    if pass_outcome_tag_errors:
        structural_failures.append(f"pass_outcome_tag_errors={pass_outcome_tag_errors}")
    structural_failures.extend(invariant_failures)

    return {
        "execution_status": "PASS" if not structural_failures else "FAIL",
        "promotion_status": "REVIEW_REQUIRED",
        "methodology_id": METHODOLOGY_ID,
        "scope": {"competition": "ENG_PL", "season": "2017/18"},
        "source_invariants": {
            "matches": len(matches_payload),
            "passes": pass_count,
            "participating_player_matches": len(player_match),
            "participating_players": len({player_id for _, player_id in player_match}),
            "orphan_passes": orphan_passes,
            "sentinel_actor_passes": sentinel_actor_passes,
            "pass_outcome_tag_errors": pass_outcome_tag_errors,
            "structural_failures": structural_failures,
        },
        "coordinate_quality": {
            "valid_geometry": valid_geometry_count,
            "invalid_geometry": pass_count - valid_geometry_count,
            "valid_geometry_pct": _pct(valid_geometry_count, pass_count),
            "invalid_reasons": dict(sorted(invalid_coordinate_reasons.items())),
        },
        "metric_totals_ready_only": {
            "progressive_passes": sum(
                state.progressive_passes
                for state in player_match.values()
                if not state.progressive_ambiguous
            ),
            "passes_into_final_third": sum(
                state.passes_into_final_third
                for state in player_match.values()
                if not state.final_third_ambiguous
            ),
            "long_passes": sum(
                state.long_passes for state in player_match.values() if not state.long_ambiguous
            ),
            "long_passes_accurate": sum(
                state.long_passes_accurate
                for state in player_match.values()
                if not state.long_ambiguous
            ),
            "direct_launch_events": long_direct_launches,
            "cross_events_excluded_from_long_geometry": cross_events,
        },
        "player_match_coverage": {
            "progressive_passes": _coverage_dict(pm_progressive),
            "passes_into_final_third": _coverage_dict(pm_final_third),
            "long_passes_accurate": _coverage_dict(pm_long),
        },
        "player_season_coverage": {
            "progressive_passes": _coverage_dict(season_progressive),
            "passes_into_final_third": _coverage_dict(season_final_third),
            "long_passes_accurate": _coverage_dict(season_long),
        },
        "player_match_distributions_ready_only": {
            "progressive_passes": _distribution(
                [
                    state.progressive_passes
                    for state in player_match.values()
                    if not state.progressive_ambiguous
                ]
            ),
            "passes_into_final_third": _distribution(
                [
                    state.passes_into_final_third
                    for state in player_match.values()
                    if not state.final_third_ambiguous
                ]
            ),
            "long_passes_accurate": _distribution(
                [
                    state.long_passes_accurate
                    for state in player_match.values()
                    if not state.long_ambiguous
                ]
            ),
        },
        "player_season_distributions_ready_only": {
            "progressive_passes": _distribution(
                [
                    int(row["progressive_passes"])
                    for row in season_rows.values()
                    if not row["progressive_missing"]
                ]
            ),
            "passes_into_final_third": _distribution(
                [
                    int(row["passes_into_final_third"])
                    for row in season_rows.values()
                    if not row["final_third_missing"]
                ]
            ),
            "long_passes_accurate": _distribution(
                [
                    int(row["long_passes_accurate"])
                    for row in season_rows.values()
                    if not row["long_missing"]
                ]
            ),
        },
        "pass_sub_event_length_audit": {
            name: {
                "events": audit.events,
                "valid_geometry": audit.valid_geometry,
                "valid_geometry_pct": _pct(audit.valid_geometry, audit.events),
                "over_25m": audit.over_25m,
                "over_45m": audit.over_45m,
                "length_distribution_m": _distribution(audit.lengths_m),
            }
            for name, audit in sorted(sub_event_lengths.items())
        },
        "taxonomy_review_signals": {
            "hand_or_head_passes_over_45m": non_ground_named_candidates,
            "note": (
                "Hand/Head pass >45m candidates require semantic review because v1's historical "
                "fallback treats every non-High/non-Launch/non-Cross subtype as ground-like."
            ),
        },
        "player_v2_passing_evidence_input_proxy": {
            "player_seasons": len(season_rows),
            "all_three_spatial_inputs_ready": len(ready_spatial_seasons),
            "all_three_spatial_inputs_ready_pct": _pct(len(ready_spatial_seasons), len(season_rows)),
            "all_three_spatial_plus_pass_completion_denominator": len(passing_input_proxy),
            "all_three_spatial_plus_pass_completion_denominator_pct": _pct(
                len(passing_input_proxy), len(season_rows)
            ),
            "warning": (
                "This is only input-readiness. It is not a Player V2 dimension-state result: "
                "minutes, windows, reference cohorts and percentile eligibility are not run here."
            ),
        },
    }


def _participating_player_matches(matches_payload: list[Any]) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        match_id = match.get("wyId")
        teams_data = match.get("teamsData")
        if not isinstance(match_id, int) or not isinstance(teams_data, dict):
            continue
        for team_entry in teams_data.values():
            if not isinstance(team_entry, dict):
                continue
            formation = team_entry.get("formation")
            if not isinstance(formation, dict):
                continue
            starters = _player_ids(formation.get("lineup"))
            bench = _player_ids(formation.get("bench"))
            substituted_in: set[int] = set()
            substitutions = formation.get("substitutions")
            if isinstance(substitutions, list):
                for substitution in substitutions:
                    if not isinstance(substitution, dict):
                        continue
                    player_in = substitution.get("playerIn")
                    if isinstance(player_in, int) and player_in != _SENTINEL_PLAYER_ID:
                        substituted_in.add(player_in)
            for player_id in starters | (bench & substituted_in):
                result.add((match_id, player_id))
    return result


def _player_ids(raw_entries: Any) -> set[int]:
    if not isinstance(raw_entries, list):
        return set()
    result: set[int] = set()
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        player_id = entry.get("playerId")
        if isinstance(player_id, int) and player_id != _SENTINEL_PLAYER_ID:
            result.add(player_id)
    return result


def _aggregate_player_seasons(
    player_match: dict[tuple[int, int], PlayerMatchSpatialAudit],
) -> dict[int, dict[str, int | bool]]:
    result: dict[int, dict[str, int | bool]] = {}
    for (_match_id, player_id), state in player_match.items():
        row = result.setdefault(
            player_id,
            {
                "matches": 0,
                "passes_total": 0,
                "passes_accurate": 0,
                "progressive_passes": 0,
                "passes_into_final_third": 0,
                "long_passes": 0,
                "long_passes_accurate": 0,
                "progressive_missing": False,
                "final_third_missing": False,
                "long_missing": False,
            },
        )
        row["matches"] = int(row["matches"]) + 1
        row["passes_total"] = int(row["passes_total"]) + state.passes_total
        row["passes_accurate"] = int(row["passes_accurate"]) + state.passes_accurate
        row["progressive_passes"] = (
            int(row["progressive_passes"]) + state.progressive_passes
        )
        row["passes_into_final_third"] = (
            int(row["passes_into_final_third"]) + state.passes_into_final_third
        )
        row["long_passes"] = int(row["long_passes"]) + state.long_passes
        row["long_passes_accurate"] = (
            int(row["long_passes_accurate"]) + state.long_passes_accurate
        )
        row["progressive_missing"] = bool(row["progressive_missing"]) or state.progressive_ambiguous
        row["final_third_missing"] = bool(row["final_third_missing"]) or state.final_third_ambiguous
        row["long_missing"] = bool(row["long_missing"]) or state.long_ambiguous
    return result


def _invariant_failures(
    player_match: dict[tuple[int, int], PlayerMatchSpatialAudit],
) -> list[str]:
    failures: list[str] = []
    for pair, state in player_match.items():
        if state.passes_accurate > state.passes_total:
            failures.append(f"{pair}: passes_accurate>passes_total")
        if state.progressive_passes > state.passes_total:
            failures.append(f"{pair}: progressive_passes>passes_total")
        if state.passes_into_final_third > state.passes_total:
            failures.append(f"{pair}: final_third>passes_total")
        if state.long_passes > state.passes_total:
            failures.append(f"{pair}: long_passes>passes_total")
        if state.long_passes_accurate > state.long_passes:
            failures.append(f"{pair}: long_accurate>long_total")
        if len(failures) >= 25:
            break
    return failures


def _coverage(
    states: Any,
    *,
    value_attr: str,
    missing_attr: str,
) -> MetricCoverage:
    ready = missing = true_zero = positive = 0
    for state in states:
        if bool(getattr(state, missing_attr)):
            missing += 1
            continue
        ready += 1
        value = int(getattr(state, value_attr))
        if value == 0:
            true_zero += 1
        else:
            positive += 1
    return MetricCoverage(ready=ready, missing=missing, true_zero=true_zero, positive=positive)


def _season_coverage(
    rows: dict[int, dict[str, int | bool]],
    *,
    value_key: str,
    missing_key: str,
) -> MetricCoverage:
    ready = missing = true_zero = positive = 0
    for row in rows.values():
        if bool(row[missing_key]):
            missing += 1
            continue
        ready += 1
        value = int(row[value_key])
        if value == 0:
            true_zero += 1
        else:
            positive += 1
    return MetricCoverage(ready=ready, missing=missing, true_zero=true_zero, positive=positive)


def _coverage_dict(coverage: MetricCoverage) -> dict[str, int | float]:
    return {
        "ready": coverage.ready,
        "missing": coverage.missing,
        "ready_pct": coverage.ready_pct,
        "true_zero": coverage.true_zero,
        "positive": coverage.positive,
    }


def _distribution(values: list[int] | list[float]) -> dict[str, int | float | None]:
    if not values:
        return {
            "n": 0,
            "min": None,
            "p01": None,
            "p05": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p95": None,
            "p99": None,
            "max": None,
            "mean": None,
        }
    ordered = sorted(float(value) for value in values)
    return {
        "n": len(ordered),
        "min": _round(ordered[0]),
        "p01": _round(_percentile(ordered, 0.01)),
        "p05": _round(_percentile(ordered, 0.05)),
        "p25": _round(_percentile(ordered, 0.25)),
        "median": _round(_percentile(ordered, 0.50)),
        "p75": _round(_percentile(ordered, 0.75)),
        "p95": _round(_percentile(ordered, 0.95)),
        "p99": _round(_percentile(ordered, 0.99)),
        "max": _round(ordered[-1]),
        "mean": _round(sum(ordered) / len(ordered)),
    }


def _percentile(ordered: list[float], q: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _round(value: float) -> float:
    return round(value, 4)


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 4) if denominator else 0.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit fi-wyscout-spatial-v1.0 against the real cached Wyscout "
            "ENG_PL 2017/18 source. No database writes."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        matches_payload, events_payload, _tag_labels = load_cached_source(args.cache_dir)
        report = audit_spatial_v1(
            matches_payload=matches_payload,
            events_payload=events_payload,
        )
    except (WyscoutMappingAuditError, WyscoutSpatialAuditError, OSError, json.JSONDecodeError) as exc:
        print(f"WYSCOUT SPATIAL V1 AUDIT: FAIL - {exc}")
        raise SystemExit(1) from exc

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"REPORT: {args.report}")
    if report["execution_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
