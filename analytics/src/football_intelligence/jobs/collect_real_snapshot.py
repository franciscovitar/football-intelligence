"""Collect the public real ENG_PL 2025/26 match/team snapshot.

Only Football-Data.co.uk's published season CSV is fetched. Fantasy Premier
League automation is intentionally absent because its terms prohibit
automated extraction. The committed snapshot contains normalized real match
and team observations; it does not claim rich domestic player coverage.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.football_data_uk import parse_results_csv
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.providers.football_data_uk import (
    FootballDataUkClient,
    FootballDataUkError,
)

FOOTBALL_DATA_UK_DIVISION = "E0"
FOOTBALL_DATA_UK_SEASON_CODE = "2526"
FOOTBALL_DATA_UK_SEMANTIC_VERSION = "football-data-uk-v1"
MATCHES_FILENAME = "eng_pl_matches.json"

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_DIR = _REPO_ROOT / "data" / "real" / "2025-26"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect the real ENG_PL 2025/26 Football-Data.co.uk match/team "
            "snapshot into structured, provenance-tagged JSON."
        )
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    collect_football_data_uk_matches(output_dir=args.output_dir)


def collect_football_data_uk_matches(*, output_dir: Path) -> None:
    client = FootballDataUkClient()
    print(
        f"Football-Data.co.uk: fetching {FOOTBALL_DATA_UK_SEASON_CODE}/"
        f"{FOOTBALL_DATA_UK_DIVISION}.csv ..."
    )
    try:
        response = client.get_results_csv(
            division_code=FOOTBALL_DATA_UK_DIVISION,
            season_code=FOOTBALL_DATA_UK_SEASON_CODE,
        )
    except FootballDataUkError as exc:
        raise SystemExit(f"Football-Data.co.uk fetch failed: {exc}") from exc

    observations = parse_results_csv(
        response.csv_text,
        division_code=FOOTBALL_DATA_UK_DIVISION,
        season_code=FOOTBALL_DATA_UK_SEASON_CODE,
        ingestion_run_id=None,
    )
    output = build_matches_output(observations=observations, retrieved_at=response.fetched_at)
    _write_json(output_dir / MATCHES_FILENAME, output)
    print(f"Football-Data.co.uk: {len(observations)} normalized observations")


def build_matches_output(
    *,
    observations: list[NormalizedObservation],
    retrieved_at: datetime,
) -> dict[str, Any]:
    return {
        "provenance": _provenance(
            source="football-data-uk",
            source_url=(
                f"https://www.football-data.co.uk/mmz4281/{FOOTBALL_DATA_UK_SEASON_CODE}/"
                f"{FOOTBALL_DATA_UK_DIVISION}.csv"
            ),
            retrieved_at=retrieved_at,
            semantic_version=FOOTBALL_DATA_UK_SEMANTIC_VERSION,
            record_count=len(observations),
        ),
        "scope": {
            "competition": "ENG_PL",
            "season": "2025/26",
            "entity_grains": ["match", "team_match"],
            "player_coverage": "unavailable",
        },
        "records": [dataclasses.asdict(observation) for observation in observations],
    }


def _provenance(
    *,
    source: str,
    source_url: str,
    retrieved_at: datetime,
    semantic_version: str,
    record_count: int,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_url": source_url,
        "retrieved_at": retrieved_at.isoformat(),
        "semantic_version": semantic_version,
        "record_count": record_count,
        "automated_collection": "yes",
        "redistribution_permission": "unknown",
        "certification_state": "not_certified",
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    print(f"WROTE: {path}")


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    main()
