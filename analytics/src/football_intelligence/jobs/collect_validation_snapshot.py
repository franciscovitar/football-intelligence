"""Block 16: collect a secondary StatsBomb Open Data validation snapshot.

Per explicit product direction, the PRIMARY real snapshot is ENG_PL 2025/26
(`collect_real_snapshot.py`). That snapshot cannot supply match-level
passing/defending/dribbling/xG detail -- no zero-cost domestic-league source
does. This script collects a SEPARATE, secondary dataset purely to validate
that Metric Catalog V2 / the diagnostic engine / position-family scoring
correctly handle genuinely rich, real, match-level data when it exists.

FIFA World Cup 2022 (StatsBomb Open Data `competition_id=43, season_id=106`)
is used because it is the only StatsBomb Open Data competition-season that is
verified FULLY complete (64/64 matches published), unlike every domestic
league sample in that dataset (e.g. Bundesliga 2023/24 publishes only 34/306
matches). This is NOT the primary product snapshot, is NOT one of the six
named core domestic leagues, and must never be presented as ENG_PL/any core
league's data -- it is validation-only evidence, kept in its own
`data/validation/wc2022/` directory and its own competition_code (`WC2022`)
so it can never be confused with real core-league observations.

Collects a BOUNDED sample of matches' event logs (not all 64 -- proportional
to "validate the pipeline works," not "build a second product surface"),
spanning group stage through the final so the sample isn't skewed toward one
stage of the tournament.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.statsbomb_open import (
    find_competition_season,
    parse_match_events,
    parse_match_list,
)
from football_intelligence.providers.statsbomb_open import (
    StatsBombOpenDataClient,
    StatsBombOpenDataError,
)

COMPETITION_NAME = "FIFA World Cup"
SEASON_NAME = "2022"
COMPETITION_CODE = "WC2022"
SEASON_LABEL = "2022"
SEMANTIC_VERSION = "statsbomb-open-v1"

DEFAULT_MATCH_SAMPLE_SIZE = 10

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_DIR = _REPO_ROOT / "data" / "validation" / "wc2022"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect a bounded, secondary StatsBomb Open Data FIFA World Cup 2022 "
            "validation sample -- never the primary product snapshot."
        )
    )
    parser.add_argument("--match-sample-size", type=int, default=DEFAULT_MATCH_SAMPLE_SIZE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    client = StatsBombOpenDataClient()

    print("StatsBomb: fetching competitions.json ...")
    competitions_response = client.get("competitions.json")
    located = find_competition_season(
        competitions_response.payload,
        competition_name=COMPETITION_NAME,
        season_name=SEASON_NAME,
    )
    if located is None:
        raise SystemExit(f"could not locate {COMPETITION_NAME} {SEASON_NAME} in competitions.json")
    competition_id, season_id = located
    print(f"StatsBomb: located competition_id={competition_id} season_id={season_id}")

    print(f"StatsBomb: fetching matches/{competition_id}/{season_id}.json ...")
    matches_response = client.get(f"matches/{competition_id}/{season_id}.json")
    match_observations = parse_match_list(
        matches_response.payload,
        competition_code=COMPETITION_CODE,
        season_label=SEASON_LABEL,
        ingestion_run_id=None,
    )
    match_ids = _extract_match_ids(matches_response.payload)
    print(f"StatsBomb: {len(match_ids)} matches published (expected 64 for a complete WC2022)")

    sample_match_ids = _spread_sample(match_ids, args.match_sample_size)
    print(f"StatsBomb: sampling {len(sample_match_ids)} matches for event-level detail")

    event_observations = []
    for index, match_id in enumerate(sample_match_ids, start=1):
        try:
            events_response = client.get(f"events/{match_id}.json")
        except StatsBombOpenDataError as exc:
            print(f"StatsBomb: skipping match {match_id} ({exc})")
            continue
        event_observations.extend(
            parse_match_events(
                events_response.payload,
                match_id=str(match_id),
                competition_code=COMPETITION_CODE,
                ingestion_run_id=None,
            )
        )
        print(f"StatsBomb: processed {index}/{len(sample_match_ids)} sampled matches")

    retrieved_at = datetime.now(UTC)
    output = {
        "warning": (
            "SECONDARY VALIDATION DATA ONLY. This is FIFA World Cup 2022, not any "
            "core domestic league, and not season 2025/26. It exists only to prove "
            "Metric Catalog V2 / diagnostics / position-family scoring work "
            "correctly against genuinely rich real event data. Never present this "
            "as ENG_PL or any other core-league product data."
        ),
        "provenance": {
            "source": "statsbomb-open",
            "source_url": (
                "https://github.com/statsbomb/open-data/blob/master/data/"
                f"matches/{competition_id}/{season_id}.json"
            ),
            "retrieved_at": retrieved_at.isoformat(),
            "semantic_version": SEMANTIC_VERSION,
            "competition_name": COMPETITION_NAME,
            "season_name": SEASON_NAME,
            "total_matches_published": len(match_ids),
            "expected_full_tournament_matches": 64,
            "sampled_match_ids": sample_match_ids,
        },
        "match_observations": [dataclasses.asdict(item) for item in match_observations],
        "event_observations": [dataclasses.asdict(item) for item in event_observations],
    }

    output_path = args.output_dir / "wc2022_validation_sample.json"
    output_path.write_text(
        json.dumps(output, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    print(f"WROTE: {output_path}")
    print(
        f"DONE: {len(match_observations)} match-level observations, "
        f"{len(event_observations)} event-derived observations from "
        f"{len(sample_match_ids)} sampled matches"
    )


def _extract_match_ids(payload: Any) -> list[int]:
    if not isinstance(payload, list):
        return []
    ids: list[int] = []
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("match_id"), int):
            ids.append(item["match_id"])
    return sorted(ids)


def _spread_sample(match_ids: list[int], sample_size: int) -> list[int]:
    """Evenly spread a bounded sample across the full list (never just the first N)."""

    if sample_size <= 0 or not match_ids:
        return []
    if sample_size >= len(match_ids):
        return list(match_ids)
    step = len(match_ids) / sample_size
    indices = sorted({int(i * step) for i in range(sample_size)})
    return [match_ids[i] for i in indices]


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    main()
