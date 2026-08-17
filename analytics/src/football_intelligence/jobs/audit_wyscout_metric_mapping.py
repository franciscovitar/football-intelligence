"""Block 20B.2a audit: verify the Wyscout Open -> Metric Catalog mapping
against the real, already-cached ENG_PL 2017/18 source.

Local-only: reads files already cached by the Block 20B.1 probe
(`data/cache/wyscout-open/`), never makes a network request, never connects
to PostgreSQL, and never produces `NormalizedObservation` rows or writes
canonical evidence. Its purpose is to keep
`providers/wyscout_open_mapping.py` honest as it evolves -- every check
below re-derives, from the real cached files, one of the concrete empirical
facts (exact counts, tag/label pairs, observed key sets) that a DIRECT or
DERIVABLE classification in that module depends on. If a future edit to the
mapping module or a re-download of the source ever invalidates one of those
facts, this job fails loudly instead of the mapping silently drifting from
reality.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football_intelligence.jobs.probe_wyscout_open import _resolve_content_path
from football_intelligence.providers.wyscout_open import WyscoutOpenDataArchiveError
from football_intelligence.providers.wyscout_open_mapping import (
    WYSCOUT_METRIC_MAPPINGS,
    MappingClassification,
)

DEFAULT_CACHE_DIR = Path("data/cache/wyscout-open")

_ROSTER_ENTRY_KEYS = frozenset({"playerId", "ownGoals", "redCards", "goals", "yellowCards"})
_FORMATION_KEYS = frozenset({"lineup", "bench", "substitutions"})

# Curated (tag_id, expected label) pairs the mapping module's classifications
# rely on -- verified once against the real tags2name.csv during Block
# 20B.2a's empirical audit (see docs/WYSCOUT_METRIC_MAPPING.md).
_EXPECTED_TAG_LABELS: tuple[tuple[int, str], ...] = (
    (101, "Goal"),
    (102, "own_goal"),
    (201, "opportunity"),
    (301, "assist"),
    (302, "keyPass"),
    (401, "Left"),
    (402, "Right"),
    (403, "head/body"),
    (701, "lost"),
    (702, "neutral"),
    (703, "won"),
    (901, "through"),
    (1401, "interception"),
    (1501, "clearance"),
    (1601, "sliding_tackle"),
    (1701, "red_card"),
    (1702, "yellow_card"),
    (1703, "second_yellow_card"),
    (1801, "accurate"),
    (1802, "not accurate"),
    (2001, "dangerous_ball_lost"),
    (2101, "blocked"),
)

# Exact real counts verified against ENG_PL 2017/18 during this audit's
# construction. These are regression values for the same real cached
# dataset, not thresholds -- see docs/WYSCOUT_METRIC_MAPPING.md.
_EXPECTED_MATCH_COUNT = 380
_EXPECTED_EVENT_COUNT = 643150
_EXPECTED_SHOT_LIKE_COUNT = 8881
_EXPECTED_PASS_COUNT = 328657
_EXPECTED_PASS_ACCURATE = 271280
_EXPECTED_PASS_NOT_ACCURATE = 57377
_EXPECTED_DUEL_COUNT = 176688
_EXPECTED_DUEL_OUTCOME_COUNTS = {"lost": 68305, "won": 68074, "neutral": 40148, "none": 161}
_EXPECTED_FOUL_COUNT = 8138
_EXPECTED_FOUL_CARD_COUNTS = {"none": 6917, "yellow": 1180, "red": 22, "second_yellow": 19}
_EXPECTED_ASSIST_COUNT = 517
_EXPECTED_KEY_PASS_COUNT = 1749
_EXPECTED_SHOOTER_GOAL_COUNT = 988
_EXPECTED_SCORELINE_GOAL_COUNT = 1018
_EXPECTED_OWN_GOAL_COUNT = 29
_EXPECTED_CLEARANCE_TAG_OBSERVATIONS = 0

_SHOT_LIKE_KEYS = frozenset(
    {("Shot", "Shot"), ("Free Kick", "Free kick shot"), ("Free Kick", "Penalty")}
)


class WyscoutMappingAuditError(RuntimeError):
    """The audit could not run against the currently cached local files."""


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class MappingAuditReport:
    checks: tuple[VerificationCheck, ...]
    classification_counts: dict[MappingClassification, int]

    @property
    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)


def _find_cached_file(cache_dir: Path, pattern: str) -> Path:
    matches = sorted(cache_dir.rglob(pattern))
    if not matches:
        raise WyscoutMappingAuditError(
            f"no cached file matching {pattern!r} under {cache_dir} -- run the Block "
            "20B.1 probe (football-intelligence-probe-wyscout-open) first"
        )
    if len(matches) > 1:
        raise WyscoutMappingAuditError(
            f"ambiguous cache state: {len(matches)} files matching {pattern!r} under "
            f"{cache_dir}: {matches}"
        )
    return matches[0]


def _load_local_json(
    cache_dir: Path, *, zip_pattern: str, extracted_pattern: str, keyword: str
) -> Any:
    extracted = sorted(cache_dir.rglob(extracted_pattern))
    if len(extracted) == 1:
        target = extracted[0]
    else:
        zip_path = _find_cached_file(cache_dir, zip_pattern)
        try:
            target = _resolve_content_path(zip_path, cache_dir, keyword=keyword)
        except WyscoutOpenDataArchiveError as exc:
            raise WyscoutMappingAuditError(f"unsafe cached archive {zip_path.name}: {exc}") from exc
    with target.open("rb") as handle:
        return json.load(handle)


def _load_tag_labels(cache_dir: Path) -> dict[int, str]:
    csv_path = _find_cached_file(cache_dir, "*tags2name.csv")
    labels: dict[int, str] = {}
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    for row in rows[1:]:
        if len(row) < 2 or not row[0].strip().isdigit():
            continue
        labels[int(row[0].strip())] = row[1].strip()
    return labels


def load_cached_source(cache_dir: Path) -> tuple[list[Any], list[Any], dict[int, str]]:
    matches_payload = _load_local_json(
        cache_dir,
        zip_pattern="*matches.zip",
        extracted_pattern="matches_England.json",
        keyword="england",
    )
    events_payload = _load_local_json(
        cache_dir,
        zip_pattern="*events.zip",
        extracted_pattern="events_England.json",
        keyword="england",
    )
    tag_labels = _load_tag_labels(cache_dir)
    if not isinstance(matches_payload, list) or not isinstance(events_payload, list):
        raise WyscoutMappingAuditError("cached matches/events payload is structurally unusable")
    return matches_payload, events_payload, tag_labels


def _check(name: str, passed: bool, detail: str) -> VerificationCheck:
    return VerificationCheck(name=name, passed=passed, detail=detail)


def _has_tag(event: Any, tag_id: int) -> bool:
    return any(t.get("id") == tag_id for t in event.get("tags", []))


def _events_named(events_payload: list[Any], event_name: str) -> list[Any]:
    return [e for e in events_payload if isinstance(e, dict) and e.get("eventName") == event_name]


def verify_source_primitives(
    *,
    matches_payload: list[Any],
    events_payload: list[Any],
    tag_labels: dict[int, str],
) -> tuple[VerificationCheck, ...]:
    checks: list[VerificationCheck] = []

    checks.append(
        _check(
            "match_count",
            len(matches_payload) == _EXPECTED_MATCH_COUNT,
            f"expected {_EXPECTED_MATCH_COUNT}, got {len(matches_payload)}",
        )
    )
    checks.append(
        _check(
            "event_count",
            len(events_payload) == _EXPECTED_EVENT_COUNT,
            f"expected {_EXPECTED_EVENT_COUNT}, got {len(events_payload)}",
        )
    )

    event_names = {e.get("eventName") for e in events_payload if isinstance(e, dict)}
    required_event_names = {
        "Pass",
        "Shot",
        "Duel",
        "Foul",
        "Free Kick",
        "Save attempt",
        "Offside",
        "Others on the ball",
    }
    checks.append(
        _check(
            "eventName_vocabulary",
            required_event_names <= event_names,
            f"missing: {sorted(required_event_names - event_names)}",
        )
    )

    combo_counts = Counter(
        (e.get("eventName"), e.get("subEventName")) for e in events_payload if isinstance(e, dict)
    )
    required_combos = _SHOT_LIKE_KEYS | {("Others on the ball", "Clearance")}
    checks.append(
        _check(
            "shot_like_and_clearance_subEventNames_present",
            required_combos <= set(combo_counts),
            f"missing combos: {sorted(required_combos - set(combo_counts))}",
        )
    )

    for tag_id, expected_label in _EXPECTED_TAG_LABELS:
        actual_label = tag_labels.get(tag_id)
        checks.append(
            _check(
                f"tag_label_{tag_id}",
                actual_label == expected_label,
                f"expected {expected_label!r}, got {actual_label!r}",
            )
        )

    shot_like_events = [
        e
        for e in events_payload
        if isinstance(e, dict) and (e.get("eventName"), e.get("subEventName")) in _SHOT_LIKE_KEYS
    ]
    checks.append(
        _check(
            "shot_like_event_count",
            len(shot_like_events) == _EXPECTED_SHOT_LIKE_COUNT,
            f"expected {_EXPECTED_SHOT_LIKE_COUNT}, got {len(shot_like_events)}",
        )
    )

    pass_events = _events_named(events_payload, "Pass")
    accurate = sum(1 for e in pass_events if _has_tag(e, 1801))
    not_accurate = sum(1 for e in pass_events if _has_tag(e, 1802))
    checks.append(
        _check(
            "pass_count",
            len(pass_events) == _EXPECTED_PASS_COUNT,
            f"expected {_EXPECTED_PASS_COUNT}, got {len(pass_events)}",
        )
    )
    checks.append(
        _check(
            "pass_accurate_not_accurate_mutually_exclusive_and_exhaustive",
            accurate == _EXPECTED_PASS_ACCURATE
            and not_accurate == _EXPECTED_PASS_NOT_ACCURATE
            and accurate + not_accurate == len(pass_events),
            f"accurate={accurate} (expected {_EXPECTED_PASS_ACCURATE}), "
            f"not_accurate={not_accurate} (expected {_EXPECTED_PASS_NOT_ACCURATE}), "
            f"total={len(pass_events)}",
        )
    )

    assist_count = sum(1 for e in pass_events if _has_tag(e, 301))
    keypass_count = sum(1 for e in pass_events if _has_tag(e, 302))
    checks.append(
        _check(
            "assist_and_key_pass_counts",
            assist_count == _EXPECTED_ASSIST_COUNT and keypass_count == _EXPECTED_KEY_PASS_COUNT,
            f"assist={assist_count} (expected {_EXPECTED_ASSIST_COUNT}), "
            f"keyPass={keypass_count} (expected {_EXPECTED_KEY_PASS_COUNT})",
        )
    )

    duel_events = _events_named(events_payload, "Duel")
    outcome_counts = {"lost": 0, "won": 0, "neutral": 0, "none": 0}
    for e in duel_events:
        tag_ids = {t.get("id") for t in e.get("tags", [])}
        if 701 in tag_ids:
            outcome_counts["lost"] += 1
        elif 703 in tag_ids:
            outcome_counts["won"] += 1
        elif 702 in tag_ids:
            outcome_counts["neutral"] += 1
        else:
            outcome_counts["none"] += 1
    checks.append(
        _check(
            "duel_count",
            len(duel_events) == _EXPECTED_DUEL_COUNT,
            f"expected {_EXPECTED_DUEL_COUNT}, got {len(duel_events)}",
        )
    )
    checks.append(
        _check(
            "duel_outcome_tag_coverage",
            outcome_counts == _EXPECTED_DUEL_OUTCOME_COUNTS,
            f"expected {_EXPECTED_DUEL_OUTCOME_COUNTS}, got {outcome_counts}",
        )
    )

    foul_events = _events_named(events_payload, "Foul")
    foul_card_counts = {"none": 0, "yellow": 0, "red": 0, "second_yellow": 0}
    for e in foul_events:
        tag_ids = {t.get("id") for t in e.get("tags", [])}
        if 1701 in tag_ids:
            foul_card_counts["red"] += 1
        elif 1703 in tag_ids:
            foul_card_counts["second_yellow"] += 1
        elif 1702 in tag_ids:
            foul_card_counts["yellow"] += 1
        else:
            foul_card_counts["none"] += 1
    checks.append(
        _check(
            "foul_count",
            len(foul_events) == _EXPECTED_FOUL_COUNT,
            f"expected {_EXPECTED_FOUL_COUNT}, got {len(foul_events)}",
        )
    )
    checks.append(
        _check(
            "card_tags_scoped_to_foul_events",
            foul_card_counts == _EXPECTED_FOUL_CARD_COUNTS,
            f"expected {_EXPECTED_FOUL_CARD_COUNTS}, got {foul_card_counts}",
        )
    )
    card_tag_ids = {1701, 1702, 1703}
    non_foul_card_events = sum(
        1
        for e in events_payload
        if isinstance(e, dict)
        and e.get("eventName") != "Foul"
        and any(t.get("id") in card_tag_ids for t in e.get("tags", []))
    )
    checks.append(
        _check(
            "card_tags_never_appear_outside_foul_events",
            non_foul_card_events == 0,
            f"found {non_foul_card_events} card-tagged events outside eventName=Foul",
        )
    )

    shooter_goal_count = sum(1 for e in shot_like_events if _has_tag(e, 101))
    own_goal_count = sum(1 for e in events_payload if isinstance(e, dict) and _has_tag(e, 102))
    scoreline_goal_count = 0
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue
        for team_entry in teams_data.values():
            if not isinstance(team_entry, dict):
                continue
            score = team_entry.get("score")
            if isinstance(score, int):
                scoreline_goal_count += score
    checks.append(
        _check(
            "goal_reconciliation",
            shooter_goal_count == _EXPECTED_SHOOTER_GOAL_COUNT
            and own_goal_count == _EXPECTED_OWN_GOAL_COUNT
            and scoreline_goal_count == _EXPECTED_SCORELINE_GOAL_COUNT,
            f"shooter_goals={shooter_goal_count} (expected {_EXPECTED_SHOOTER_GOAL_COUNT}), "
            f"own_goals={own_goal_count} (expected {_EXPECTED_OWN_GOAL_COUNT}), "
            f"scoreline_goals={scoreline_goal_count} (expected {_EXPECTED_SCORELINE_GOAL_COUNT})",
        )
    )

    interception_event_names = {
        str(e.get("eventName")) for e in events_payload if isinstance(e, dict) and _has_tag(e, 1401)
    }
    checks.append(
        _check(
            "interception_tag_spans_multiple_event_names",
            len(interception_event_names) >= 3,
            f"interception(1401) observed on only {sorted(interception_event_names)}",
        )
    )

    clearance_tag_observations = sum(
        1 for e in events_payload if isinstance(e, dict) and _has_tag(e, 1501)
    )
    checks.append(
        _check(
            "clearance_tag_never_observed",
            clearance_tag_observations == _EXPECTED_CLEARANCE_TAG_OBSERVATIONS,
            f"expected {_EXPECTED_CLEARANCE_TAG_OBSERVATIONS} observations of tag 1501, "
            f"got {clearance_tag_observations}",
        )
    )

    roster_keys: set[str] = set()
    formation_keys: set[str] = set()
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue
        for team_entry in teams_data.values():
            if not isinstance(team_entry, dict):
                continue
            formation = team_entry.get("formation")
            if not isinstance(formation, dict):
                continue
            formation_keys.update(formation.keys())
            for entry in (formation.get("lineup") or []) + (formation.get("bench") or []):
                if isinstance(entry, dict):
                    roster_keys.update(entry.keys())
    checks.append(
        _check(
            "roster_entries_never_carry_position_captain_or_shirt_number",
            roster_keys <= _ROSTER_ENTRY_KEYS,
            f"observed unexpected roster entry keys: {sorted(roster_keys - _ROSTER_ENTRY_KEYS)}",
        )
    )
    checks.append(
        _check(
            "formation_never_carries_a_shape_label",
            formation_keys <= _FORMATION_KEYS,
            f"observed unexpected formation keys: {sorted(formation_keys - _FORMATION_KEYS)}",
        )
    )

    return tuple(checks)


def run_audit(*, cache_dir: Path) -> MappingAuditReport:
    matches_payload, events_payload, tag_labels = load_cached_source(cache_dir)
    checks = verify_source_primitives(
        matches_payload=matches_payload, events_payload=events_payload, tag_labels=tag_labels
    )
    classification_counts: dict[MappingClassification, int] = {
        "DIRECT": 0,
        "DERIVABLE": 0,
        "REQUIRES_MODEL": 0,
        "UNSUPPORTED": 0,
        "AMBIGUOUS": 0,
    }
    for mapping in WYSCOUT_METRIC_MAPPINGS:
        classification_counts[mapping.classification] += 1
    return MappingAuditReport(checks=checks, classification_counts=classification_counts)


def _print_report(report: MappingAuditReport) -> None:
    print("=== WYSCOUT METRIC MAPPING AUDIT (Block 20B.2a) ===")
    print(f"total mapping entries: {len(WYSCOUT_METRIC_MAPPINGS)}")
    for classification, count in report.classification_counts.items():
        print(f"  {classification}: {count}")

    print()
    print("=== SOURCE PRIMITIVE VERIFICATION ===")
    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{status}  {check.name}  ({check.detail})")


def _report_to_dict(report: MappingAuditReport) -> dict[str, Any]:
    return {
        "mapping_entry_count": len(WYSCOUT_METRIC_MAPPINGS),
        "classification_counts": report.classification_counts,
        "checks": [
            {"name": check.name, "passed": check.passed, "detail": check.detail}
            for check in report.checks
        ],
        "all_checks_passed": report.all_passed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 20B.2a: verify the Wyscout Open -> Metric Catalog V2 mapping "
            "(providers/wyscout_open_mapping.py) against the real, already-cached "
            "ENG_PL 2017/18 source. Local-only, no network, no database."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--report", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        report = run_audit(cache_dir=args.cache_dir)
    except WyscoutMappingAuditError as exc:
        print(f"WYSCOUT MAPPING AUDIT: FAIL - {exc}")
        raise SystemExit(1) from exc

    _print_report(report)

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print()
        print(f"REPORT: {args.report}")

    if not report.all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
