"""Audit metric-specific exactness for Wyscout passes into the final third.

This read-only ENG_PL 2017/18 laboratory tests one conservative refinement:
a Pass whose start is already inside the attacking final third is exactly
non-qualifying even when its endpoint is unavailable. No endpoint is imputed,
no canonical observation is emitted, and PostgreSQL is never written.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from football_intelligence.jobs.wyscout_historical_scope import (
    load_scope_inputs,
    scope_config,
    validate_source_scope,
)
from football_intelligence.normalization.wyscout_historical import _derive_appearances
from football_intelligence.providers.wyscout_spatial_v1 import (
    FINAL_THIRD_X_M,
    classify_long_pass,
    is_accurate,
    is_pass_into_final_third,
    parse_pass_coordinates,
)

EXPECTED_PASS_COUNT = 328_657
SENTINEL_PLAYER_ID = 0
PASS_COMPLETION_WEIGHT = 25
FINAL_THIRD_WEIGHT = 25
LONG_ACCURATE_WEIGHT = 20
PASSING_MIN_EVIDENCE_WEIGHT = 60

FinalThirdClassification = Literal[
    "into_final_third",
    "not_into_final_third",
    "ambiguous",
]


class WyscoutFinalThirdAuditError(RuntimeError):
    """The final-third exactness lab cannot complete safely."""


@dataclass(slots=True)
class PlayerMatchState:
    passes_total: int = 0
    passes_accurate: int = 0
    passes_into_final_third: int = 0
    long_passes_accurate: int = 0
    final_third_missing: bool = False
    long_missing: bool = False


@dataclass(slots=True)
class PlayerSeasonState:
    minutes: int = 0
    passes_total: int = 0
    passes_accurate: int = 0
    passes_into_final_third: int = 0
    long_passes_accurate: int = 0
    final_third_missing: bool = False
    long_missing: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit exact Wyscout pass-into-final-third coverage without "
            "endpoint imputation."
        )
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def classify_pass_into_final_third_exact(event: dict[str, Any]) -> FinalThirdClassification:
    """Classify only when the available source evidence makes the result exact."""

    coordinates = parse_pass_coordinates(event)
    start = coordinates.start
    if start is None:
        return "ambiguous"

    # Wyscout's metric requires the pass to START outside the final third.
    # Therefore an already-inside start is a provable negative independent of
    # the endpoint. This is classification from observed start evidence, not
    # endpoint recovery or imputation.
    if start.x_m >= FINAL_THIRD_X_M:
        return "not_into_final_third"

    if coordinates.valid and coordinates.end is not None:
        return (
            "into_final_third"
            if is_pass_into_final_third(start, coordinates.end)
            else "not_into_final_third"
        )

    return "ambiguous"


def _sub_event(event: dict[str, Any]) -> str:
    value = event.get("subEventName")
    return value if isinstance(value, str) and value else "<missing>"


def _pct(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 4) if denominator else 0.0


def _coverage(
    states: Sequence[PlayerMatchState | PlayerSeasonState],
) -> dict[str, Any]:
    ready = [state for state in states if not state.final_third_missing]
    positive = sum(state.passes_into_final_third > 0 for state in ready)
    true_zero = sum(state.passes_into_final_third == 0 for state in ready)
    return {
        "ready": len(ready),
        "missing": len(states) - len(ready),
        "ready_pct": _pct(len(ready), len(states)),
        "positive": positive,
        "true_zero": true_zero,
    }


def run_audit(cache_dir: Path) -> dict[str, Any]:
    config = scope_config("ENG_PL")
    matches, events_payload, _players, _teams = load_scope_inputs(cache_dir, config=config)
    validation = validate_source_scope(
        matches_payload=matches,
        events_payload=events_payload,
        config=config,
    )
    if not validation.passed:
        raise WyscoutFinalThirdAuditError("; ".join(validation.failures))

    appearances = _derive_appearances(matches)
    player_match = {key: PlayerMatchState() for key in appearances}

    pass_count = 0
    attributable_passes = 0
    excluded_sentinel = 0
    excluded_outside_participation = 0
    invalid_geometry = 0
    invalid_by_sub_event: Counter[str] = Counter()
    recovered_exact_negative = 0
    recovered_by_sub_event: Counter[str] = Counter()
    unresolved_invalid = 0
    unresolved_by_sub_event: Counter[str] = Counter()
    start_zone_for_invalid: Counter[str] = Counter()

    for raw_event in events_payload:
        if not isinstance(raw_event, dict) or raw_event.get("eventName") != "Pass":
            continue
        pass_count += 1
        match_id = raw_event.get("matchId")
        player_id = raw_event.get("playerId")
        if not isinstance(match_id, int) or not isinstance(player_id, int):
            continue
        if player_id == SENTINEL_PLAYER_ID:
            excluded_sentinel += 1
            continue
        state = player_match.get((match_id, player_id))
        if state is None:
            excluded_outside_participation += 1
            continue

        attributable_passes += 1
        state.passes_total += 1
        accurate = is_accurate(raw_event)
        if accurate:
            state.passes_accurate += 1

        coordinates = parse_pass_coordinates(raw_event)
        sub_event = _sub_event(raw_event)
        if not coordinates.valid:
            invalid_geometry += 1
            invalid_by_sub_event[sub_event] += 1
            if coordinates.start is None:
                start_zone_for_invalid["start_unavailable"] += 1
            elif coordinates.start.x_m >= FINAL_THIRD_X_M:
                start_zone_for_invalid["start_inside_final_third"] += 1
            else:
                start_zone_for_invalid["start_outside_final_third"] += 1

        final_third_class = classify_pass_into_final_third_exact(raw_event)
        if final_third_class == "into_final_third":
            state.passes_into_final_third += 1
        elif final_third_class == "ambiguous":
            state.final_third_missing = True
            unresolved_invalid += 1
            unresolved_by_sub_event[sub_event] += 1
        elif not coordinates.valid:
            recovered_exact_negative += 1
            recovered_by_sub_event[sub_event] += 1

        long_class = classify_long_pass(
            sub_event_name=None if sub_event == "<missing>" else sub_event,
            coordinates=coordinates,
        )
        if long_class == "long":
            if accurate:
                state.long_passes_accurate += 1
        elif long_class == "ambiguous":
            state.long_missing = True

    if pass_count != EXPECTED_PASS_COUNT:
        raise WyscoutFinalThirdAuditError(
            f"expected {EXPECTED_PASS_COUNT} Pass events, got {pass_count}"
        )

    player_season: dict[int, PlayerSeasonState] = {}
    for (match_id, player_id), match_state in player_match.items():
        season = player_season.setdefault(player_id, PlayerSeasonState())
        season.minutes += appearances[(match_id, player_id)].minutes
        season.passes_total += match_state.passes_total
        season.passes_accurate += match_state.passes_accurate
        season.passes_into_final_third += match_state.passes_into_final_third
        season.long_passes_accurate += match_state.long_passes_accurate
        season.final_third_missing = season.final_third_missing or match_state.final_third_missing
        season.long_missing = season.long_missing or match_state.long_missing

    season_states = list(player_season.values())
    match_states = list(player_match.values())
    eligible = [state for state in season_states if state.minutes >= 450]

    passing_proxy = []
    for state in eligible:
        evidence_weight = 0
        if state.passes_total > 0:
            evidence_weight += PASS_COMPLETION_WEIGHT
        if not state.final_third_missing:
            evidence_weight += FINAL_THIRD_WEIGHT
        if not state.long_missing:
            evidence_weight += LONG_ACCURATE_WEIGHT
        if state.passes_total > 0 and evidence_weight >= PASSING_MIN_EVIDENCE_WEIGHT:
            passing_proxy.append(state)

    return {
        "execution_status": "PASS",
        "methodology_candidate": "fi-wyscout-final-third-exactness-v1",
        "scope": {"competition": "ENG_PL", "season": "2017/18"},
        "source": {
            "matches": validation.match_count,
            "passes": pass_count,
            "canonical_participating_player_matches": len(player_match),
            "canonical_participating_players": len(player_season),
            "attributable_passes": attributable_passes,
            "excluded_sentinel_passes": excluded_sentinel,
            "excluded_outside_participation_passes": excluded_outside_participation,
        },
        "invalid_geometry": {
            "events": invalid_geometry,
            "by_sub_event": dict(sorted(invalid_by_sub_event.items())),
            "start_zone": dict(sorted(start_zone_for_invalid.items())),
            "exact_negative_without_endpoint": recovered_exact_negative,
            "exact_negative_by_sub_event": dict(sorted(recovered_by_sub_event.items())),
            "still_ambiguous": unresolved_invalid,
            "still_ambiguous_by_sub_event": dict(sorted(unresolved_by_sub_event.items())),
        },
        "player_match_coverage": _coverage(match_states),
        "player_season_coverage": _coverage(season_states),
        "eligible_450_minutes": {
            "players": len(eligible),
            "final_third_exact": sum(not state.final_third_missing for state in eligible),
            "long_accurate_exact": sum(not state.long_missing for state in eligible),
            "pass_completion_denominator": sum(state.passes_total > 0 for state in eligible),
            "passing_without_progressive_proxy": len(passing_proxy),
            "passing_without_progressive_proxy_pct": _pct(len(passing_proxy), len(eligible)),
            "proxy_rule": (
                "pass_completion_pct 25% + passes_into_final_third 25% + "
                "long_passes_accurate 20% >= unchanged 60% evidence gate; "
                "progressive_passes remains absent"
            ),
        },
        "metric_total_ready_only": sum(
            state.passes_into_final_third
            for state in match_states
            if not state.final_third_missing
        ),
        "safety": {
            "endpoint_imputation": False,
            "missing_to_zero_coercion": False,
            "classification_rule": (
                "invalid endpoint + observed start inside final third => exact non-qualifying; "
                "invalid endpoint + start outside final third => missing"
            ),
        },
    }


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = run_audit(args.cache_dir)
    except (WyscoutFinalThirdAuditError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"WYSCOUT FINAL-THIRD EXACTNESS AUDIT: FAIL - {exc}") from exc
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
