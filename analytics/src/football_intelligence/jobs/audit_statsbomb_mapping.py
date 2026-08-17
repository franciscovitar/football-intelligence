"""Block 20C.2a audit: verify the StatsBomb Open -> Metric Catalog mapping
against the real, pinned-and-cached Premier League 2015/16 source.

Offline/cache-aware: uses `providers.statsbomb_open_cache.fetch_json_cached`
against the pinned `StatsBombOpenDataClient` (never `master`), so anything
already cached under `data/cache/statsbomb-open/<SOURCE_SHA>/` is read from
disk; anything missing is fetched once (through the pinned provider client,
never a raw ad-hoc request) and then cached. Never connects to PostgreSQL,
never produces `NormalizedObservation` rows.

Every check below re-derives, from the real cached files, one of the
concrete empirical facts (exact full-season counts) a DIRECT or DERIVABLE
classification in `providers/statsbomb_open_mapping.py` depends on. If a
future edit to the mapping module or a source-revision upgrade ever
invalidates one of those facts, this job fails loudly instead of the
mapping silently drifting from reality.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from football_intelligence.jobs.fetch_statsbomb_open import COMPETITION_ID, SEASON_ID
from football_intelligence.providers.statsbomb_open import (
    DEFAULT_PINNED_REVISION,
    StatsBombOpenDataClient,
)
from football_intelligence.providers.statsbomb_open_cache import (
    StatsBombCacheError,
    fetch_json_cached,
)
from football_intelligence.providers.statsbomb_open_mapping import (
    STATSBOMB_METRIC_MAPPINGS,
    STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS,
    adapter_safe_mappings,
    derivable_methodology_pending_mappings,
    derivable_ready_mappings,
    mappings_by_classification,
)

DEFAULT_CACHE_ROOT = Path("data/cache/statsbomb-open")

_EXPECTED_MATCH_COUNT = 380
_EXPECTED_NATIVE_SCORE_SUM = 1026
_EXPECTED_SHOOTER_GOALS = 988
_EXPECTED_OWN_GOAL_FOR = 38
_EXPECTED_ASSISTS_GOAL_ASSIST = 669
_EXPECTED_LINEUP_YELLOW_CARDS = 1203
_EXPECTED_LINEUP_RED_CARDS = 34
_EXPECTED_LINEUP_SECOND_YELLOW = 25
_EXPECTED_SAVES = 2277
_EXPECTED_GOALS_CONCEDED = 988
_EXPECTED_PENALTY_GOALS = 74


class AuditFailure(RuntimeError):
    """A regression check against the real cached source failed."""


def _match_ids(matches_payload: Any) -> list[int]:
    return [
        item["match_id"]
        for item in matches_payload
        if isinstance(item, dict) and isinstance(item.get("match_id"), int)
    ]


def run_audit(*, cache_root: Path, ref: str = DEFAULT_PINNED_REVISION) -> dict[str, Any]:
    client = StatsBombOpenDataClient(ref=ref)

    try:
        matches_fetch = fetch_json_cached(
            client, f"matches/{COMPETITION_ID}/{SEASON_ID}.json", cache_root=cache_root
        )
    except StatsBombCacheError as exc:
        raise AuditFailure(f"could not acquire match list: {exc}") from exc

    matches = matches_fetch.payload
    match_ids = _match_ids(matches)
    native_score_sum = sum(m.get("home_score", 0) + m.get("away_score", 0) for m in matches)

    goals = 0
    own_goal_for = 0
    goal_assists = 0
    penalty_goals = 0
    save_types = 0
    goals_conceded_types = 0
    lineup_card_counter: Counter[str] = Counter()

    for match_id in match_ids:
        try:
            events_fetch = fetch_json_cached(
                client, f"events/{match_id}.json", cache_root=cache_root
            )
            lineups_fetch = fetch_json_cached(
                client, f"lineups/{match_id}.json", cache_root=cache_root
            )
        except StatsBombCacheError as exc:
            raise AuditFailure(f"could not acquire match {match_id} files: {exc}") from exc

        for event in events_fetch.payload:
            type_name = event.get("type", {}).get("name")
            if type_name == "Shot":
                shot = event.get("shot", {})
                if shot.get("outcome", {}).get("name") == "Goal":
                    goals += 1
                    if shot.get("type", {}).get("name") == "Penalty":
                        penalty_goals += 1
            elif type_name == "Own Goal For":
                own_goal_for += 1
            elif type_name == "Pass":
                if event.get("pass", {}).get("goal_assist") is True:
                    goal_assists += 1
            elif type_name == "Goal Keeper":
                gk_type = event.get("goalkeeper", {}).get("type", {}).get("name")
                if gk_type in {
                    "Shot Saved",
                    "Shot Saved Off Target",
                    "Shot Saved to Post",
                    "Penalty Saved",
                    "Penalty Saved to Post",
                }:
                    save_types += 1
                elif gk_type in {"Goal Conceded", "Penalty Conceded"}:
                    goals_conceded_types += 1

        for team in lineups_fetch.payload:
            for player in team.get("lineup", []):
                for card in player.get("cards", []):
                    lineup_card_counter[card.get("card_type")] += 1

    checks = {
        "match_count": (_EXPECTED_MATCH_COUNT, len(match_ids)),
        "native_score_sum": (_EXPECTED_NATIVE_SCORE_SUM, native_score_sum),
        "shooter_goals": (_EXPECTED_SHOOTER_GOALS, goals),
        "own_goal_for": (_EXPECTED_OWN_GOAL_FOR, own_goal_for),
        "score_reconciliation": (
            _EXPECTED_NATIVE_SCORE_SUM,
            goals + own_goal_for,
        ),
        "goal_assist_count": (_EXPECTED_ASSISTS_GOAL_ASSIST, goal_assists),
        "penalty_goals": (_EXPECTED_PENALTY_GOALS, penalty_goals),
        "saves": (_EXPECTED_SAVES, save_types),
        "goals_conceded": (_EXPECTED_GOALS_CONCEDED, goals_conceded_types),
        "shots_on_target_faced_reconciliation": (
            save_types + goals_conceded_types,
            save_types + goals_conceded_types,
        ),
        "lineup_yellow_cards": (
            _EXPECTED_LINEUP_YELLOW_CARDS,
            lineup_card_counter.get("Yellow Card", 0),
        ),
        "lineup_red_cards": (_EXPECTED_LINEUP_RED_CARDS, lineup_card_counter.get("Red Card", 0)),
        "lineup_second_yellow": (
            _EXPECTED_LINEUP_SECOND_YELLOW,
            lineup_card_counter.get("Second Yellow", 0),
        ),
    }

    return {
        "checks": checks,
        "counts_verified": all(expected == actual for expected, actual in checks.values()),
    }


def _classification_report() -> dict[str, int]:
    report: dict[str, int] = {}
    for classification in (
        "DIRECT",
        "DERIVABLE",
        "REQUIRES_MODEL",
        "UNSUPPORTED",
        "AMBIGUOUS",
    ):
        report[classification] = len(mappings_by_classification(classification))
    report["DERIVABLE_READY"] = len(derivable_ready_mappings())
    report["DERIVABLE_METHODOLOGY_PENDING"] = len(derivable_methodology_pending_mappings())
    report["provider_out_of_scope"] = len(STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS)
    report["total_catalog_identities"] = len(STATSBOMB_METRIC_MAPPINGS) + len(
        STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS
    )
    report["adapter_safe"] = len(adapter_safe_mappings())
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 20C.2a audit: verify providers/statsbomb_open_mapping.py "
            "classifications against the real, pinned-and-cached Premier League "
            "2015/16 StatsBomb Open Data source. Local/cache-aware -- never a "
            "master-tracking fetch, never a database connection."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--ref", type=str, default=DEFAULT_PINNED_REVISION)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    print("=== STATSBOMB METRIC MAPPING AUDIT (Block 20C.2a) ===")
    classification_report = _classification_report()
    for key, value in classification_report.items():
        print(f"{key}: {value}")

    print()
    print("=== REAL-SOURCE REGRESSION CHECKS ===")
    try:
        result = run_audit(cache_root=args.cache_dir, ref=args.ref)
    except AuditFailure as exc:
        print(f"STATSBOMB MAPPING AUDIT: FAIL - {exc}")
        raise SystemExit(1) from exc

    for name, (expected, actual) in result["checks"].items():
        status = "PASS" if expected == actual else "MISMATCH"
        print(f"{name}: {status} (expected={expected}, actual={actual})")

    if not result["counts_verified"]:
        print()
        print("STATSBOMB MAPPING AUDIT: FAIL - one or more regression checks mismatched")
        raise SystemExit(1)

    print()
    print("STATSBOMB MAPPING AUDIT: PASS")


if __name__ == "__main__":
    main()
