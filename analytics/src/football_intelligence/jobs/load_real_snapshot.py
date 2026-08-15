"""Block 16: load the collected real ENG_PL 2025/26 snapshot into Postgres.

Reads the structured, provenance-tagged JSON files `collect_real_snapshot.py`
writes under `data/real/2025-26/` and upserts them into the normal
`football.*` tables (players/teams/seasons/matches/team_match_stats) plus the
new `football.player_season_stats` table. This is a one-off loader for a
manually-curated snapshot, not the scheduled provider-sync pipeline
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
FPL_PROVIDER_CODE = "fpl"

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
        provider_id = _ensure_provider(connection)

        identity_path = args.input_dir / "eng_pl_player_identity.json"
        stats_path = args.input_dir / "eng_pl_player_season_stats.json"
        matches_path = args.input_dir / "eng_pl_matches.json"

        player_count = 0
        if identity_path.exists() and stats_path.exists():
            player_count = _load_players_and_season_stats(
                connection,
                identity_path=identity_path,
                stats_path=stats_path,
                season_id=season_id,
                provider_id=provider_id,
            )
        else:
            print(f"SKIP players/season-stats: missing {identity_path} or {stats_path}")

        match_count = 0
        if matches_path.exists():
            match_count = _load_matches(connection, matches_path=matches_path, season_id=season_id)
        else:
            print(f"SKIP matches: missing {matches_path}")

        connection.commit()
        print(f"DONE: {player_count} player-season rows, {match_count} matches loaded")


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


def _ensure_provider(connection: Connection[Any]) -> int:
    row = connection.execute(
        """
        insert into ingestion.providers (code, display_name)
        values (%s, %s)
        on conflict (code) do update set display_name = excluded.display_name, is_active = true
        returning id
        """,
        (FPL_PROVIDER_CODE, "Official Fantasy Premier League API"),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to upsert fpl provider")
    return int(row[0])


def _load_players_and_season_stats(
    connection: Connection[Any],
    *,
    identity_path: Path,
    stats_path: Path,
    season_id: int,
    provider_id: int,
) -> int:
    identity_payload = json.loads(identity_path.read_text(encoding="utf-8"))
    stats_payload = json.loads(stats_path.read_text(encoding="utf-8"))

    identity_by_external_id: dict[str, dict[str, Any]] = {
        record["player_external_id"]: record for record in identity_payload["records"]
    }

    loaded = 0
    for record in stats_payload["records"]:
        external_id = record["player_external_id"]
        identity = identity_by_external_id.get(external_id)
        display_name = identity["display_name"] if identity else f"FPL Player {external_id}"

        player_id = _upsert_player(
            connection,
            provider_id=provider_id,
            external_id=external_id,
            display_name=display_name,
            first_name=identity.get("first_name") if identity else None,
            last_name=identity.get("last_name") if identity else None,
        )
        _upsert_player_season_stats(
            connection, player_id=player_id, season_id=season_id, record=record
        )
        loaded += 1
    return loaded


def _upsert_player(
    connection: Connection[Any],
    *,
    provider_id: int,
    external_id: str,
    display_name: str,
    first_name: str | None,
    last_name: str | None,
) -> int:
    existing = connection.execute(
        """
        select player_id from football.player_provider_ids
        where provider_id = %s and external_id = %s
        """,
        (provider_id, external_id),
    ).fetchone()
    if existing is not None:
        player_id = int(existing[0])
        connection.execute(
            "update football.players set display_name = %s, updated_at = now() where id = %s",
            (display_name, player_id),
        )
        return player_id

    row = connection.execute(
        """
        insert into football.players (display_name, first_name, last_name)
        values (%s, %s, %s)
        returning id
        """,
        (display_name, first_name, last_name),
    ).fetchone()
    if row is None:
        raise RuntimeError("failed to insert player")
    player_id = int(row[0])
    connection.execute(
        """
        insert into football.player_provider_ids (provider_id, player_id, external_id)
        values (%s, %s, %s)
        """,
        (provider_id, player_id, external_id),
    )
    return player_id


_SEASON_STATS_COLUMNS: tuple[str, ...] = (
    "minutes",
    "starts",
    "appearances",
    "goals",
    "assists",
    "clean_sheets",
    "goals_conceded",
    "own_goals",
    "penalties_saved",
    "penalties_missed",
    "yellow_cards",
    "red_cards",
    "saves",
    "bonus",
    "bps",
    "influence",
    "creativity",
    "threat",
    "ict_index",
    "tackles",
    "recoveries",
    "clearances_blocks_interceptions",
    "defensive_contribution",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "expected_goals_conceded",
)


def _upsert_player_season_stats(
    connection: Connection[Any],
    *,
    player_id: int,
    season_id: int,
    record: dict[str, Any],
) -> None:
    columns = [
        "player_id",
        "season_id",
        *_SEASON_STATS_COLUMNS,
        "source",
        "source_url",
        "retrieved_at",
        "semantic_version",
    ]
    values = [
        player_id,
        season_id,
        *[record.get(column) for column in _SEASON_STATS_COLUMNS],
        record["source"],
        record["source_url"],
        record["retrieved_at"],
        record["semantic_version"],
    ]
    placeholders = ", ".join(["%s"] * len(columns))
    update_clause = ", ".join(
        f"{column} = excluded.{column}"
        for column in (*_SEASON_STATS_COLUMNS, "source_url", "retrieved_at", "semantic_version")
    )
    connection.execute(
        f"""
        insert into football.player_season_stats ({", ".join(columns)})
        values ({placeholders})
        on conflict (player_id, season_id, source) do update
        set {update_clause}, updated_at = now()
        """,
        values,
    )


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
