from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from football_intelligence.jobs.audit_wyscout_core_leagues import _load_country_payload
from football_intelligence.normalization.wyscout_historical import _derive_appearances
from football_intelligence.providers.wyscout_open_scopes import (
    CORE_LEAGUE_SPECS,
    SEASON_LABEL,
    verify_published_scope_counts,
)
from football_intelligence.providers.wyscout_spatial_v1 import (
    METHODOLOGY_ID,
    classify_long_pass,
    classify_pass_into_final_third,
    is_accurate,
    parse_pass_coordinates,
)

_SENTINEL_PLAYER_ID = 0
_ACCURATE_TAG = 1801
_NOT_ACCURATE_TAG = 1802
_TARGET_CODES = ("ESP_LL", "ITA_SA", "GER_BL1", "FRA_L1")
_KNOWN_PASS_SUBEVENTS = frozenset(
    {"Launch", "High pass", "Simple pass", "Smart pass", "Cross", "Hand pass", "Head pass"}
)


@dataclass(slots=True)
class PairState:
    passes: int = 0
    long_passes_accurate: int = 0
    passes_into_final_third: int = 0
    long_missing: bool = False
    final_third_missing: bool = False


@dataclass(frozen=True, slots=True)
class Coverage:
    ready: int
    missing: int
    positive: int
    true_zero: int

    @property
    def ready_pct(self) -> float:
        total = self.ready + self.missing
        return round(100.0 * self.ready / total, 4) if total else 0.0


class SpatialCoreAuditError(RuntimeError):
    pass


def _tag_ids(event: dict[str, Any]) -> set[int]:
    tags = event.get("tags")
    if not isinstance(tags, list):
        return set()
    return {
        tag["id"]
        for tag in tags
        if isinstance(tag, dict) and isinstance(tag.get("id"), int)
    }


def _coverage(states: list[tuple[bool, int]]) -> Coverage:
    ready_values = [value for missing, value in states if not missing]
    missing = sum(1 for missing, _ in states if missing)
    return Coverage(
        ready=len(ready_values),
        missing=missing,
        positive=sum(1 for value in ready_values if value > 0),
        true_zero=sum(1 for value in ready_values if value == 0),
    )


def _season_states(
    pair_states: dict[tuple[int, int], PairState], *, metric: str
) -> list[tuple[bool, int]]:
    by_player: dict[int, list[PairState]] = defaultdict(list)
    for (_, player_id), state in pair_states.items():
        by_player[player_id].append(state)

    result: list[tuple[bool, int]] = []
    for states in by_player.values():
        if metric == "long_passes_accurate":
            missing = any(state.long_missing for state in states)
            value = sum(state.long_passes_accurate for state in states)
        else:
            missing = any(state.final_third_missing for state in states)
            value = sum(state.passes_into_final_third for state in states)
        result.append((missing, value))
    return result


def audit_league(cache_dir: Path, competition_code: str) -> dict[str, Any]:
    spec = next(spec for spec in CORE_LEAGUE_SPECS if spec.competition_code == competition_code)
    matches = _load_country_payload(cache_dir, spec=spec, kind="matches")
    events = _load_country_payload(cache_dir, spec=spec, kind="events")
    source_failures = verify_published_scope_counts(
        matches_payload=matches,
        events_payload=events,
        spec=spec,
    )
    if source_failures:
        raise SpatialCoreAuditError(f"{competition_code}: source audit failed: {source_failures!r}")

    participating_pairs = set(_derive_appearances(matches))
    if not participating_pairs:
        raise SpatialCoreAuditError(f"{competition_code}: no canonical participant pairs")
    pair_states = {pair: PairState() for pair in participating_pairs}

    pass_events = 0
    attributable_passes = 0
    sentinel_actor_passes = 0
    missing_identity_passes = 0
    outside_participation_passes = 0
    valid_geometry = 0
    invalid_geometry: Counter[str] = Counter()
    pass_outcome_tag_errors = 0
    subevents: Counter[str] = Counter()
    unknown_subevents: Counter[str] = Counter()

    for raw in events:
        if not isinstance(raw, dict) or raw.get("eventName") != "Pass":
            continue
        pass_events += 1
        match_id = raw.get("matchId")
        player_id = raw.get("playerId")
        if not isinstance(match_id, int) or not isinstance(player_id, int):
            missing_identity_passes += 1
            continue
        if player_id == _SENTINEL_PLAYER_ID:
            sentinel_actor_passes += 1
            continue
        state = pair_states.get((match_id, player_id))
        if state is None:
            outside_participation_passes += 1
            continue

        attributable_passes += 1
        state.passes += 1
        tag_ids = _tag_ids(raw)
        if (_ACCURATE_TAG in tag_ids) == (_NOT_ACCURATE_TAG in tag_ids):
            pass_outcome_tag_errors += 1

        sub_event_name = raw.get("subEventName")
        sub_event = sub_event_name if isinstance(sub_event_name, str) and sub_event_name else "<missing>"
        subevents[sub_event] += 1
        if sub_event not in _KNOWN_PASS_SUBEVENTS:
            unknown_subevents[sub_event] += 1

        coordinates = parse_pass_coordinates(raw)
        if coordinates.valid:
            valid_geometry += 1
        else:
            invalid_geometry[coordinates.invalid_reason or "unknown"] += 1

        final_third = classify_pass_into_final_third(coordinates)
        if final_third == "ambiguous":
            state.final_third_missing = True
        elif final_third == "into_final_third":
            state.passes_into_final_third += 1

        long_pass = classify_long_pass(
            sub_event_name=sub_event_name if isinstance(sub_event_name, str) else None,
            coordinates=coordinates,
        )
        if long_pass == "ambiguous":
            state.long_missing = True
        elif long_pass == "long" and is_accurate(raw):
            state.long_passes_accurate += 1

    pair_long = _coverage(
        [(state.long_missing, state.long_passes_accurate) for state in pair_states.values()]
    )
    pair_final = _coverage(
        [(state.final_third_missing, state.passes_into_final_third) for state in pair_states.values()]
    )
    season_long = _coverage(_season_states(pair_states, metric="long_passes_accurate"))
    season_final = _coverage(_season_states(pair_states, metric="passes_into_final_third"))

    attributed_invalid = sum(invalid_geometry.values())
    coordinate_valid_pct = (
        round(100.0 * valid_geometry / attributable_passes, 4) if attributable_passes else 0.0
    )
    player_ids = {player_id for _, player_id in participating_pairs}

    return {
        "competition_code": competition_code,
        "season_label": SEASON_LABEL,
        "methodology_id": METHODOLOGY_ID,
        "source": {
            "matches": len(matches),
            "events": len(events),
            "pass_events": pass_events,
            "participating_player_matches": len(participating_pairs),
            "participating_players": len(player_ids),
        },
        "attribution": {
            "attributable_passes": attributable_passes,
            "missing_identity_passes": missing_identity_passes,
            "sentinel_actor_passes": sentinel_actor_passes,
            "outside_canonical_participation_passes": outside_participation_passes,
        },
        "coordinate_quality": {
            "valid_geometry": valid_geometry,
            "invalid_geometry": attributed_invalid,
            "valid_pct_of_attributable": coordinate_valid_pct,
            "invalid_reasons": dict(sorted(invalid_geometry.items())),
        },
        "pass_outcome_tag_errors": pass_outcome_tag_errors,
        "pass_subevents": dict(sorted(subevents.items())),
        "unknown_pass_subevents": dict(sorted(unknown_subevents.items())),
        "player_match_coverage": {
            "long_passes_accurate": asdict(pair_long) | {"ready_pct": pair_long.ready_pct},
            "passes_into_final_third": asdict(pair_final) | {"ready_pct": pair_final.ready_pct},
        },
        "player_season_coverage": {
            "long_passes_accurate": asdict(season_long) | {"ready_pct": season_long.ready_pct},
            "passes_into_final_third": asdict(season_final) | {"ready_pct": season_final.ready_pct},
        },
        "metric_totals_on_exact_player_matches": {
            "long_passes_accurate": sum(
                state.long_passes_accurate for state in pair_states.values() if not state.long_missing
            ),
            "passes_into_final_third": sum(
                state.passes_into_final_third
                for state in pair_states.values()
                if not state.final_third_missing
            ),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    results = [audit_league(args.cache_dir, code) for code in _TARGET_CODES]
    payload = {
        "status": "PASS",
        "methodology_id": METHODOLOGY_ID,
        "scope": "Wyscout Open 2017/18 non-England core leagues",
        "production_write": False,
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
