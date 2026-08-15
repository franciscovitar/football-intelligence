"""Block 16 one-off real ENG_PL 2025/26 season snapshot collector.

Collects the real, non-synthetic season snapshot this block's brief
describes (`data/real/2025-26/`, outside this worktree's `analytics/`/
`database/` scope -- a human/orchestrator run of this script creates that
directory and should add a `README.md` there documenting the collection
date, sources, and known caveats, e.g. `history_past` being season-aggregate
only and current-squad-only for the FPL side):

- FPL official API `bootstrap-static` + `element-summary` (season-aggregate
  player stats -- including partial xG/xA/defensive-contribution data no
  existing zero-cost adapter in this repo has ever supplied). ~587 elements,
  one `element-summary` request each, rate-limited with a small delay
  between requests to be a good citizen.
- Football-Data.co.uk `mmz4281/2526/E0.csv` (the full completed Premier
  League 2025/26 season: match results plus team-level shots/cards/corners),
  reusing the existing certified `data_mesh.adapters.football_data_uk`
  parser rather than writing a second CSV parser.

Writes structured JSON (normalized records + a provenance block: source,
source_url, retrieved_at, semantic_version, record_count) -- never raw
provider payloads. Idempotent: re-running overwrites the two output files
cleanly, since this is a one-off curated snapshot, not an incremental sync.

This script performs live network I/O when run. It is not invoked by the
test suite; `tests/test_collect_real_snapshot.py` covers only the pure
provenance/JSON-shaping helpers below with offline, synthetic inputs.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.football_data_uk import parse_results_csv
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.normalization.fpl import normalize_fpl_element_summary
from football_intelligence.normalization.models import PlayerSeasonStatsRecord
from football_intelligence.providers.football_data_uk import (
    FootballDataUkClient,
    FootballDataUkError,
)
from football_intelligence.providers.fpl import FplClient, FplElementNotFoundError, FplError

SEASON_LABEL = "2025/26"
COMPETITION_EXTERNAL_ID = "ENG_PL"
FOOTBALL_DATA_UK_DIVISION = "E0"
FOOTBALL_DATA_UK_SEASON_CODE = "2526"
FPL_SEMANTIC_VERSION = "fpl-official-api-v1"
FOOTBALL_DATA_UK_SEMANTIC_VERSION = "football-data-uk-v1"

REQUEST_DELAY_SECONDS = 0.15
PROGRESS_LOG_INTERVAL = 50

PLAYER_SEASON_STATS_FILENAME = "eng_pl_player_season_stats.json"
PLAYER_IDENTITY_FILENAME = "eng_pl_player_identity.json"
MATCHES_FILENAME = "eng_pl_matches.json"

# analytics/src/football_intelligence/jobs/collect_real_snapshot.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_DIR = _REPO_ROOT / "data" / "real" / "2025-26"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect the real ENG_PL 2025/26 season snapshot (FPL official API "
            "player-season stats + Football-Data.co.uk match/team results) into "
            "structured, provenance-tagged JSON files under --output-dir."
        )
    )
    parser.add_argument("--fpl-only", action="store_true", help="Only collect FPL player stats.")
    parser.add_argument(
        "--matches-only", action="store_true", help="Only collect Football-Data.co.uk matches."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of FPL elements processed (for testing against a small sample).",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.fpl_only and args.matches_only:
        raise SystemExit("--fpl-only and --matches-only are mutually exclusive")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if not args.matches_only:
        collect_fpl_player_season_stats(output_dir=args.output_dir, limit=args.limit)
    if not args.fpl_only:
        collect_football_data_uk_matches(output_dir=args.output_dir)


def collect_fpl_player_season_stats(*, output_dir: Path, limit: int | None) -> None:
    client = FplClient()
    print("FPL: fetching bootstrap-static ...")
    bootstrap = client.get_bootstrap_static()
    elements = bootstrap.elements[:limit] if limit is not None else bootstrap.elements
    print(f"FPL: {len(elements)} elements to process (season {SEASON_LABEL})")

    team_name_by_id = {
        team["id"]: team["name"] for team in bootstrap.teams if "id" in team and "name" in team
    }
    position_by_type = {
        element_type["id"]: element_type.get("singular_name", "")
        for element_type in bootstrap.element_types
        if "id" in element_type
    }
    identity_records = [
        _build_identity_record(
            element, team_name_by_id=team_name_by_id, position_by_type=position_by_type
        )
        for element in elements
    ]
    _write_json(
        output_dir / PLAYER_IDENTITY_FILENAME,
        {
            "provenance": _provenance(
                source="fpl-official-api",
                source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
                retrieved_at=datetime.now(UTC),
                semantic_version=FPL_SEMANTIC_VERSION,
                record_count=len(identity_records),
            ),
            "note": (
                "Team/position reflect the CURRENT (2026/27) FPL squad list, not "
                "necessarily the player's 2025/26 club -- a small number of "
                "summer-transferred players will show their new club here while "
                "their season_stats totals remain correctly scoped to 2025/26. "
                "Position is FPL's own 4-way element_type (Goalkeeper/Defender/"
                "Midfielder/Forward), not a fine-grained position family."
            ),
            "records": identity_records,
        },
    )

    retrieved_at = datetime.now(UTC)
    records: list[PlayerSeasonStatsRecord] = []
    errors: list[str] = []

    for index, element in enumerate(elements, start=1):
        element_id = element.get("id")
        if not isinstance(element_id, int):
            errors.append(f"element index {index}: missing/invalid id")
            continue

        try:
            summary = client.get_element_summary(element_id)
        except FplElementNotFoundError:
            errors.append(f"element {element_id}: not found")
        except FplError as exc:
            errors.append(f"element {element_id}: {exc}")
        else:
            record = _normalize_matching_season(
                element=element,
                history_past=summary.history_past,
                retrieved_at=retrieved_at,
            )
            if record is not None:
                records.append(record)

        if index % PROGRESS_LOG_INTERVAL == 0 or index == len(elements):
            print(
                f"FPL: processed {index}/{len(elements)} elements ({len(records)} records so far)"
            )

        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"FPL: done -- {len(records)} player-season records, {len(errors)} errors")
    output = build_player_season_stats_output(
        records=records,
        errors=errors,
        retrieved_at=retrieved_at,
    )
    _write_json(output_dir / PLAYER_SEASON_STATS_FILENAME, output)


def _normalize_matching_season(
    *,
    element: dict[str, Any],
    history_past: tuple[dict[str, Any], ...],
    retrieved_at: datetime,
) -> PlayerSeasonStatsRecord | None:
    matching_entry = next(
        (entry for entry in history_past if entry.get("season_name") == SEASON_LABEL),
        None,
    )
    if matching_entry is None:
        return None
    return normalize_fpl_element_summary(
        element,
        matching_entry,
        season_label=SEASON_LABEL,
        competition_external_id=COMPETITION_EXTERNAL_ID,
        retrieved_at=retrieved_at,
    )


def _build_identity_record(
    element: dict[str, Any],
    *,
    team_name_by_id: dict[Any, Any],
    position_by_type: dict[Any, Any],
) -> dict[str, Any]:
    first_name = str(element.get("first_name") or "").strip()
    second_name = str(element.get("second_name") or "").strip()
    display_name = f"{first_name} {second_name}".strip() or str(element.get("web_name", ""))
    return {
        "player_external_id": str(element.get("id")),
        "display_name": display_name,
        "first_name": first_name or None,
        "last_name": second_name or None,
        "team_name": team_name_by_id.get(element.get("team")),
        "listed_position": position_by_type.get(element.get("element_type")),
    }


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
    print(f"Football-Data.co.uk: {len(observations)} normalized observations")

    output = build_matches_output(observations=observations, retrieved_at=response.fetched_at)
    _write_json(output_dir / MATCHES_FILENAME, output)


def build_player_season_stats_output(
    *,
    records: list[PlayerSeasonStatsRecord],
    errors: list[str],
    retrieved_at: datetime,
) -> dict[str, Any]:
    """Pure JSON-shape builder (no I/O) -- kept separate from the network calls above."""

    return {
        "provenance": _provenance(
            source="fpl-official-api",
            source_url="https://fantasy.premierleague.com/api/",
            retrieved_at=retrieved_at,
            semantic_version=FPL_SEMANTIC_VERSION,
            record_count=len(records),
        ),
        "errors": errors,
        "records": [dataclasses.asdict(record) for record in records],
    }


def build_matches_output(
    *,
    observations: list[NormalizedObservation],
    retrieved_at: datetime,
) -> dict[str, Any]:
    """Pure JSON-shape builder (no I/O) -- kept separate from the network calls above."""

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
