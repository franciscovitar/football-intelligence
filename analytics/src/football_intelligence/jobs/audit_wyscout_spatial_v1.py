"""Empirical ENG_PL 2017/18 audit for the Wyscout spatial v1 methodology.

This laboratory reads only the cached official Wyscout Open Data source. It
never writes PostgreSQL and never emits canonical observations. Its purpose is
to measure coverage, zero-vs-missing behavior, distributions and taxonomy risks
before any spatial metric is activated in Player V2.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from football_intelligence.jobs.audit_wyscout_metric_mapping import (
    DEFAULT_CACHE_DIR,
    WyscoutMappingAuditError,
    load_cached_source,
)
from football_intelligence.normalization.wyscout_historical import _derive_appearances
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
_RECOGNIZED_LONG_SUBEVENTS = frozenset(
    {
        "Launch",
        "High pass",
        "Simple pass",
        "Smart pass",
        "Cross",
        "Hand pass",
        "Head pass",
    }
)
_EXPLICIT_NON_LONG_SUBEVENTS = ("Cross", "Hand pass", "Head pass")


@dataclass(slots=True)
class PlayerMatchSpatialAudit:
    passes_total: int = 0
    passes_accurate: int = 0
    progressive_passes: int = 0
    passes_into_final_third: int = 0
    long_passes: int = 0
    long_passes_accurate: int = 0
    progressive_missing: bool = False
    final_third_missing: bool = False
    long_missing: bool = False


@dataclass(slots=True)
class PlayerSeasonSpatialAudit:
    matches: int = 0
    passes_total: int = 0
    passes_accurate: int = 0
    progressive_passes: int = 0
    passes_into_final_third: int = 0
    long_passes: int = 0
    long_passes_accurate: int = 0
    progressive_missing: bool = False
    final_third_missing: bool = False
    long_missing: bool = False


@dataclass(slots=True)
class SubEventLengthAudit:
    events: int = 0
    valid_geometry: int = 0
    invalid_geometry: int = 0
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
        return _pct(self.ready, self.ready + self.missing)


class WyscoutSpatialAuditError(RuntimeError):
    """The real-source spatial audit could not complete safely."""


def audit_spatial_v1(*, matches_payload: list[Any], events_payload: list[Any]) -> dict[str, Any]:
    if len(matches_payload) != EXPECTED_MATCH_COUNT:
        raise WyscoutSpatialAuditError(
            f"expected {EXPECTED_MATCH_COUNT} ENG_PL matches, got {len(matches_payload)}"
        )

    # Reuse the certified historical normalization's exact participation universe:
    # starters plus bench players explicitly substituted in. Passes outside this
    # universe are reported as source-quality anomalies and are never attributed.
    participating_pairs = set(_derive_appearances(matches_payload))
    if not participating_pairs:
        raise WyscoutSpatialAuditError("no canonical participating player-match identities found")

    player_match = {pair: PlayerMatchSpatialAudit() for pair in participating_pairs}
    invalid_coordinate_reasons: Counter[str] = Counter()
    invalid_geometry_by_sub_event: Counter[str] = Counter()
    sub_event_lengths: dict[str, SubEventLengthAudit] = defaultdict(SubEventLengthAudit)

    pass_count = 0
    attributable_passes = 0
    valid_geometry_count = 0
    missing_identity_passes = 0
    sentinel_actor_passes = 0
    outside_canonical_participation_passes = 0
    pass_outcome_tag_errors = 0

    for raw_event in events_payload:
        if not isinstance(raw_event, dict) or raw_event.get("eventName") != "Pass":
            continue
        pass_count += 1

        match_id = raw_event.get("matchId")
        player_id = raw_event.get("playerId")
        if not isinstance(match_id, int) or not isinstance(player_id, int):
            missing_identity_passes += 1
            continue
        if player_id == _SENTINEL_PLAYER_ID:
            sentinel_actor_passes += 1
            continue

        state = player_match.get((match_id, player_id))
        if state is None:
            outside_canonical_participation_passes += 1
            continue

        attributable_passes += 1
        state.passes_total += 1
        accurate = is_accurate(raw_event)
        if accurate:
            state.passes_accurate += 1

        tag_ids = _tag_ids(raw_event)
        if (ACCURATE_TAG in tag_ids) == (NOT_ACCURATE_TAG in tag_ids):
            pass_outcome_tag_errors += 1

        sub_event_name = _sub_event_name(raw_event)
        sub_label = sub_event_name or "<missing>"
        sub_audit = sub_event_lengths[sub_label]
        sub_audit.events += 1

        coordinates = parse_pass_coordinates(raw_event)
        if coordinates.valid and coordinates.start is not None and coordinates.end is not None:
            valid_geometry_count += 1
            sub_audit.valid_geometry += 1
            length = pass_length_m(coordinates.start, coordinates.end)
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
            sub_audit.invalid_geometry += 1
            state.progressive_missing = True
            state.final_third_missing = True
            reason = coordinates.invalid_reason or "unknown"
            invalid_coordinate_reasons[reason] += 1
            invalid_geometry_by_sub_event[sub_label] += 1

        long_class = classify_long_pass(
            sub_event_name=sub_event_name,
            coordinates=coordinates,
        )
        if long_class == "long":
            state.long_passes += 1
            if accurate:
                state.long_passes_accurate += 1
        elif long_class == "ambiguous":
            state.long_missing = True

    if pass_count != EXPECTED_PASS_COUNT:
        raise WyscoutSpatialAuditError(
            f"expected {EXPECTED_PASS_COUNT} ENG_PL Pass events, got {pass_count}"
        )

    invalid_geometry_count = attributable_passes - valid_geometry_count
    season_rows = _aggregate_player_seasons(player_match)
    invariant_failures = _invariant_failures(player_match)
    accounting_failures = _accounting_failures(
        pass_count=pass_count,
        attributable_passes=attributable_passes,
        valid_geometry_count=valid_geometry_count,
        invalid_geometry_count=invalid_geometry_count,
        missing_identity_passes=missing_identity_passes,
        sentinel_actor_passes=sentinel_actor_passes,
        outside_canonical_participation_passes=outside_canonical_participation_passes,
        player_match=player_match,
    )

    structural_failures = [*invariant_failures, *accounting_failures]
    if pass_outcome_tag_errors:
        structural_failures.append(f"pass_outcome_tag_errors={pass_outcome_tag_errors}")

    pm_progressive = _coverage(
        player_match.values(),
        value_attr="progressive_passes",
        missing_attr="progressive_missing",
    )
    pm_final_third = _coverage(
        player_match.values(),
        value_attr="passes_into_final_third",
        missing_attr="final_third_missing",
    )
    pm_long = _coverage(
        player_match.values(),
        value_attr="long_passes_accurate",
        missing_attr="long_missing",
    )
    season_progressive = _coverage(
        season_rows.values(),
        value_attr="progressive_passes",
        missing_attr="progressive_missing",
    )
    season_final_third = _coverage(
        season_rows.values(),
        value_attr="passes_into_final_third",
        missing_attr="final_third_missing",
    )
    season_long = _coverage(
        season_rows.values(),
        value_attr="long_passes_accurate",
        missing_attr="long_missing",
    )

    all_spatial_ready = [
        row
        for row in season_rows.values()
        if not row.progressive_missing and not row.final_third_missing and not row.long_missing
    ]
    passing_proxy = [row for row in all_spatial_ready if row.passes_total > 0]

    observed_sub_events = set(sub_event_lengths)
    unknown_long_semantics = sorted(observed_sub_events - _RECOGNIZED_LONG_SUBEVENTS)
    explicit_non_long_over_45m = {
        name: sub_event_lengths[name].over_45m
        for name in _EXPLICIT_NON_LONG_SUBEVENTS
        if name in sub_event_lengths
    }

    return {
        "execution_status": "PASS" if not structural_failures else "FAIL",
        "promotion_status": "REVIEW_REQUIRED",
        "methodology_id": METHODOLOGY_ID,
        "scope": {"competition": "ENG_PL", "season": "2017/18"},
        "source_invariants": {
            "matches": len(matches_payload),
            "passes": pass_count,
            "canonical_participating_player_matches": len(player_match),
            "canonical_participating_players": len({player_id for _, player_id in player_match}),
            "pass_outcome_tag_errors": pass_outcome_tag_errors,
            "structural_failures": structural_failures,
        },
        "source_quality_exclusions": {
            "missing_identity_passes": missing_identity_passes,
            "sentinel_actor_passes": sentinel_actor_passes,
            "outside_canonical_participation_passes": outside_canonical_participation_passes,
            "excluded_passes_total": (
                missing_identity_passes
                + sentinel_actor_passes
                + outside_canonical_participation_passes
            ),
            "policy": (
                "reported but not attributed; matches certified historical participation semantics"
            ),
        },
        "coordinate_quality_attributable_passes": {
            "attributable_passes": attributable_passes,
            "valid_geometry": valid_geometry_count,
            "invalid_geometry": invalid_geometry_count,
            "valid_geometry_pct": _pct(valid_geometry_count, attributable_passes),
            "invalid_reasons": dict(sorted(invalid_coordinate_reasons.items())),
            "invalid_geometry_by_sub_event": dict(sorted(invalid_geometry_by_sub_event.items())),
        },
        "metric_totals_ready_only": {
            "progressive_passes": _ready_sum(
                player_match.values(),
                value_attr="progressive_passes",
                missing_attr="progressive_missing",
            ),
            "passes_into_final_third": _ready_sum(
                player_match.values(),
                value_attr="passes_into_final_third",
                missing_attr="final_third_missing",
            ),
            "long_passes": _ready_sum(
                player_match.values(),
                value_attr="long_passes",
                missing_attr="long_missing",
            ),
            "long_passes_accurate": _ready_sum(
                player_match.values(),
                value_attr="long_passes_accurate",
                missing_attr="long_missing",
            ),
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
            "progressive_passes": _ready_distribution(
                player_match.values(),
                value_attr="progressive_passes",
                missing_attr="progressive_missing",
            ),
            "passes_into_final_third": _ready_distribution(
                player_match.values(),
                value_attr="passes_into_final_third",
                missing_attr="final_third_missing",
            ),
            "long_passes_accurate": _ready_distribution(
                player_match.values(),
                value_attr="long_passes_accurate",
                missing_attr="long_missing",
            ),
        },
        "player_season_distributions_ready_only": {
            "progressive_passes": _ready_distribution(
                season_rows.values(),
                value_attr="progressive_passes",
                missing_attr="progressive_missing",
            ),
            "passes_into_final_third": _ready_distribution(
                season_rows.values(),
                value_attr="passes_into_final_third",
                missing_attr="final_third_missing",
            ),
            "long_passes_accurate": _ready_distribution(
                season_rows.values(),
                value_attr="long_passes_accurate",
                missing_attr="long_missing",
            ),
        },
        "pass_sub_event_length_audit": {
            name: {
                "events": audit.events,
                "valid_geometry": audit.valid_geometry,
                "invalid_geometry": audit.invalid_geometry,
                "valid_geometry_pct": _pct(audit.valid_geometry, audit.events),
                "over_25m": audit.over_25m,
                "over_45m": audit.over_45m,
                "length_distribution_m": _distribution(audit.lengths_m),
            }
            for name, audit in sorted(sub_event_lengths.items())
        },
        "taxonomy_review_signals": {
            "observed_sub_event_names": sorted(observed_sub_events),
            "unknown_long_semantics": unknown_long_semantics,
            "explicit_non_long_subtypes_over_45m": explicit_non_long_over_45m,
            "policy": (
                "Launch=long; High>25m=long; Simple/Smart>45m=long ground; "
                "Cross/Hand/Head=not long; unknown=missing"
            ),
        },
        "player_v2_passing_evidence_input_proxy": {
            "player_seasons": len(season_rows),
            "all_three_spatial_inputs_ready": len(all_spatial_ready),
            "all_three_spatial_inputs_ready_pct": _pct(len(all_spatial_ready), len(season_rows)),
            "all_three_spatial_plus_pass_completion_denominator": len(passing_proxy),
            "all_three_spatial_plus_pass_completion_denominator_pct": _pct(
                len(passing_proxy), len(season_rows)
            ),
            "warning": (
                "Input readiness only; Player V2 minutes, windows, cohorts and percentiles "
                "are not executed here."
            ),
        },
    }


def _tag_ids(event: dict[str, Any]) -> set[int]:
    tags = event.get("tags")
    if not isinstance(tags, list):
        return set()
    return {
        int(tag["id"]) for tag in tags if isinstance(tag, dict) and isinstance(tag.get("id"), int)
    }


def _sub_event_name(event: dict[str, Any]) -> str | None:
    value = event.get("subEventName")
    return value if isinstance(value, str) and value else None


def _aggregate_player_seasons(
    player_match: dict[tuple[int, int], PlayerMatchSpatialAudit],
) -> dict[int, PlayerSeasonSpatialAudit]:
    result: dict[int, PlayerSeasonSpatialAudit] = {}
    for (_match_id, player_id), state in player_match.items():
        row = result.setdefault(player_id, PlayerSeasonSpatialAudit())
        row.matches += 1
        row.passes_total += state.passes_total
        row.passes_accurate += state.passes_accurate
        row.progressive_passes += state.progressive_passes
        row.passes_into_final_third += state.passes_into_final_third
        row.long_passes += state.long_passes
        row.long_passes_accurate += state.long_passes_accurate
        row.progressive_missing = row.progressive_missing or state.progressive_missing
        row.final_third_missing = row.final_third_missing or state.final_third_missing
        row.long_missing = row.long_missing or state.long_missing
    return result


def _invariant_failures(
    player_match: dict[tuple[int, int], PlayerMatchSpatialAudit],
) -> list[str]:
    failures: list[str] = []
    for key, state in player_match.items():
        if state.passes_accurate > state.passes_total:
            failures.append(f"passes_accurate_gt_total:{key}")
        if state.progressive_passes > state.passes_total:
            failures.append(f"progressive_gt_passes:{key}")
        if state.passes_into_final_third > state.passes_total:
            failures.append(f"final_third_gt_passes:{key}")
        if state.long_passes > state.passes_total:
            failures.append(f"long_gt_passes:{key}")
        if state.long_passes_accurate > state.long_passes:
            failures.append(f"accurate_long_gt_long:{key}")
    return failures[:25]


def _accounting_failures(
    *,
    pass_count: int,
    attributable_passes: int,
    valid_geometry_count: int,
    invalid_geometry_count: int,
    missing_identity_passes: int,
    sentinel_actor_passes: int,
    outside_canonical_participation_passes: int,
    player_match: dict[tuple[int, int], PlayerMatchSpatialAudit],
) -> list[str]:
    failures: list[str] = []
    excluded = missing_identity_passes + sentinel_actor_passes + outside_canonical_participation_passes
    if attributable_passes + excluded != pass_count:
        failures.append("raw_pass_accounting_mismatch")
    if valid_geometry_count + invalid_geometry_count != attributable_passes:
        failures.append("coordinate_accounting_mismatch")
    if sum(state.passes_total for state in player_match.values()) != attributable_passes:
        failures.append("player_match_pass_accounting_mismatch")
    return failures


def _coverage(
    states: Iterable[object],
    *,
    value_attr: str,
    missing_attr: str,
) -> MetricCoverage:
    ready = missing = true_zero = positive = 0
    for state in states:
        is_missing = bool(getattr(state, missing_attr))
        value = int(getattr(state, value_attr))
        if is_missing:
            missing += 1
            continue
        ready += 1
        if value == 0:
            true_zero += 1
        else:
            positive += 1
    return MetricCoverage(ready=ready, missing=missing, true_zero=true_zero, positive=positive)


def _coverage_dict(value: MetricCoverage) -> dict[str, int | float]:
    return {
        "ready": value.ready,
        "missing": value.missing,
        "true_zero": value.true_zero,
        "positive": value.positive,
        "ready_pct": value.ready_pct,
    }


def _ready_sum(
    states: Iterable[object],
    *,
    value_attr: str,
    missing_attr: str,
) -> int:
    return sum(
        int(getattr(state, value_attr))
        for state in states
        if not bool(getattr(state, missing_attr))
    )


def _ready_distribution(
    states: Iterable[object],
    *,
    value_attr: str,
    missing_attr: str,
) -> dict[str, int | float | None]:
    values = [
        int(getattr(state, value_attr))
        for state in states
        if not bool(getattr(state, missing_attr))
    ]
    return _distribution(values)


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
        "min": round(ordered[0], 4),
        "p01": _quantile(ordered, 0.01),
        "p05": _quantile(ordered, 0.05),
        "p25": _quantile(ordered, 0.25),
        "median": _quantile(ordered, 0.50),
        "p75": _quantile(ordered, 0.75),
        "p95": _quantile(ordered, 0.95),
        "p99": _quantile(ordered, 0.99),
        "max": round(ordered[-1], 4),
        "mean": round(sum(ordered) / len(ordered), 4),
    }


def _quantile(values: list[float], q: float) -> float:
    if len(values) == 1:
        return round(values[0], 4)
    position = (len(values) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(values[lower], 4)
    weight = position - lower
    value = values[lower] * (1.0 - weight) + values[upper] * weight
    return round(value, 4)


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 4) if denominator else 0.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit fi-wyscout-spatial-v1 against cached official ENG_PL 2017/18 data; "
            "never writes canonical evidence."
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
    except (
        WyscoutMappingAuditError,
        WyscoutSpatialAuditError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(f"WYSCOUT SPATIAL V1 AUDIT: FAIL - {exc}")
        raise SystemExit(1) from exc

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"REPORT: {args.report}")
    if report["execution_status"] != "PASS":
        raise SystemExit(1)
