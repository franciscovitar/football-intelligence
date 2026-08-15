"""Block 16: load the collected real ENG_PL 2025/26 snapshot into Postgres.

Reads the structured, provenance-tagged match JSON written by
`collect_real_snapshot.py` and upserts it into the normal
`football.*` tables (teams/seasons/matches/team_match_stats). This is a one-off loader for the
committed source snapshot, not the scheduled provider-sync pipeline
(`db.provider_repository.ProviderRepository` / `sync_core_leagues.py`) --
deliberately simpler and standalone, matching the collector job it pairs
with.

Idempotent: safe to re-run against the same JSON files.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection

COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2025/26"

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT_DIR = _REPO_ROOT / "data" / "real" / "2025-26"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load the collected real ENG_PL 2025/26 snapshot JSON into Postgres."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--database-url", type=str, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required (env var or --database-url)")

    with psycopg.connect(database_url, autocommit=False) as connection:
        season_id = _ensure_season(connection)
        matches_path = args.input_dir / "eng_pl_matches.json"

        match_count = 0
        if matches_path.exists():
            match_count = _load_matches(connection, matches_path=matches_path, season_id=season_id)
        else:
            print(f"SKIP matches: missing {matches_path}")

        connection.commit()
        print(
            f"DONE: {match_count} real matches loaded; rich ENG_PL player data remains unavailable"
        )


def _ensure_season(connection: Connection[Any]) -> int:
    row = connection.execute(
        "select id from football.competitions where code = %s", (COMPETITION_CODE,)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"competition seed not found: {COMPETITION_CODE}")
    competition_id = int(row[0])

    row = connection.execute(
        """
        insert into football.seasons (competition_id, label)
        values (%s, %s)
        on conflict (competition_id, label) do update set updated_at = now()
        returning id
        """,
        (competition_id, SEASON_LABEL),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to upsert season")
    return int(row[0])


def _load_matches(connection: Connection[Any], *, matches_path: Path, season_id: int) -> int:
    payload = json.loads(matches_path.read_text(encoding="utf-8"))
    observations: list[dict[str, Any]] = payload["records"]

    match_observations: dict[str, dict[str, Any]] = {}
    team_observations: dict[str, list[dict[str, Any]]] = {}
    for observation in observations:
        if observation["entity_type"] == "match":
            bucket = match_observations.setdefault(observation["entity_source_id"], {})
            bucket[observation["metric_name"]] = observation["value"]
            bucket.setdefault("_identity_hints", observation["entity_identity_hints"])
        elif observation["entity_type"] == "team" and "match_external_id" in observation.get(
            "entity_identity_hints", {}
        ):
            team_observations.setdefault(
                observation["entity_identity_hints"]["match_external_id"], []
            ).append(observation)

    loaded = 0
    for match_external_id, match_fields in match_observations.items():
        hints = match_fields["_identity_hints"]
        home_team_name = hints.get("home_team_name")
        away_team_name = hints.get("away_team_name")
        kickoff_date_str = hints.get("kickoff_date")
        if not home_team_name or not away_team_name:
            continue

        home_team_id = _upsert_team_by_name(connection, home_team_name)
        away_team_id = _upsert_team_by_name(connection, away_team_name)
        kickoff_at = f"{kickoff_date_str}T12:00:00+00:00" if kickoff_date_str else None

        match_id = _upsert_match(
            connection,
            season_id=season_id,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            kickoff_at=kickoff_at,
            home_score=match_fields.get("home_score"),
            away_score=match_fields.get("away_score"),
            status=match_fields.get("status", "finished"),
        )

        for observation in team_observations.get(match_external_id, []):
            if observation["metric_name"] == "name":
                continue
            team_name = observation["entity_source_id"]
            team_id = home_team_id if team_name == home_team_name else away_team_id
            _upsert_team_match_stat(
                connection,
                match_id=match_id,
                team_id=team_id,
                metric_name=observation["metric_name"],
                value=observation["value"],
            )
        loaded += 1

    return loaded


def _upsert_team_by_name(connection: Connection[Any], name: str) -> int:
    row = connection.execute("select id from football.teams where name = %s", (name,)).fetchone()
    if row is not None:
        return int(row[0])
    row = connection.execute(
        "insert into football.teams (name) values (%s) returning id", (name,)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"failed to insert team {name}")
    return int(row[0])


def _upsert_match(
    connection: Connection[Any],
    *,
    season_id: int,
    home_team_id: int,
    away_team_id: int,
    kickoff_at: str | None,
    home_score: int | None,
    away_score: int | None,
    status: str,
) -> int:
    existing = connection.execute(
        """
        select id from football.matches
        where season_id = %s and home_team_id = %s and away_team_id = %s
          and kickoff_at::date = %s::date
        """,
        (season_id, home_team_id, away_team_id, kickoff_at),
    ).fetchone()
    if existing is not None:
        match_id = int(existing[0])
        connection.execute(
            """
            update football.matches
            set home_score = %s, away_score = %s, status = %s, updated_at = now()
            where id = %s
            """,
            (home_score, away_score, status, match_id),
        )
        return match_id

    row = connection.execute(
        """
        insert into football.matches (
            season_id, home_team_id, away_team_id, kickoff_at, status, home_score, away_score
        )
        values (%s, %s, %s, %s, %s, %s, %s)
        returning id
        """,
        (season_id, home_team_id, away_team_id, kickoff_at, status, home_score, away_score),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to insert match")
    return int(row[0])


_TEAM_MATCH_STAT_METRICS = frozenset(
    {"shots_total", "shots_on_target", "fouls", "corners", "yellow_cards", "red_cards"}
)


def _upsert_team_match_stat(
    connection: Connection[Any],
    *,
    match_id: int,
    team_id: int,
    metric_name: str,
    value: Any,
) -> None:
    if metric_name not in _TEAM_MATCH_STAT_METRICS:
        return
    connection.execute(
        f"""
        insert into football.team_match_stats (match_id, team_id, {metric_name})
        values (%s, %s, %s)
        on conflict (match_id, team_id) do update
        set {metric_name} = excluded.{metric_name}, updated_at = now()
        """,
        (match_id, team_id, value),
    )


if __name__ == "__main__":
    main()
