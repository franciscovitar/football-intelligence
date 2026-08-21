"""Block 16: load the collected real ENG_PL 2025/26 snapshot into Postgres.

Reads the structured, provenance-tagged match JSON written by
`collect_real_snapshot.py` and upserts it into the normal
`football.*` tables (teams/seasons/matches/team_match_stats). This is a one-off loader for the
committed source snapshot, not the scheduled provider-sync pipeline
(`db.provider_repository.ProviderRepository` / `sync_core_leagues.py`) --
deliberately simpler and standalone, matching the collector job it pairs
with.

Idempotent: safe to re-run against the same JSON files.

## Database safety (V1 Closure Pass A/B preparation)

This job used to accept a bare `DATABASE_URL` environment variable as a
fallback for `--database-url` -- unlike every other real-data write job in
this repository (`build_real_snapshot_v2.py`, `execute_real_intelligence_v2.py`),
which never read `DATABASE_URL` implicitly and always required a clearly
local `--database-url`. That inconsistency meant this loader alone could
silently target any remote database a shell happened to have `DATABASE_URL`
set to. Fixed: `--database-url` is now a required, explicit CLI argument,
`DATABASE_URL` is never consulted, and the same shared target-resolution
contract as the other two jobs applies -- a local URL is accepted as before;
a remote URL requires the full explicit production-write confirmation
(`--allow-remote-write` + `--confirm-target production` +
`--production-write-confirmation <exact phrase>` +
`--confirm-database-target <exact parsed target>`), never a single flag or
an environment variable. See `db.production_write_guard` for the shared
contract and `docs/PRODUCTION_BOOTSTRAP.md` for the intended one-time
sequence this loader participates in.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg import Connection

from football_intelligence.db.production_write_guard import resolve_database_target

COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2025/26"

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_INPUT_DIR = _REPO_ROOT / "data" / "real" / "2025-26"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load the collected real ENG_PL 2025/26 snapshot JSON into Postgres."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument(
        "--database-url",
        type=str,
        required=True,
        help=(
            "Explicit PostgreSQL URL. Never read from the DATABASE_URL environment "
            "variable. A local URL (localhost/127.0.0.1/::1, or a host-less local-socket "
            "DSN) is accepted as before. A remote URL additionally requires "
            "--allow-remote-write, --confirm-target production, "
            "--production-write-confirmation with the exact required phrase, and "
            "--confirm-database-target with the exact parsed target (run the read-only "
            "preflight first and copy its reported target)."
        ),
    )
    parser.add_argument("--allow-remote-write", action="store_true")
    parser.add_argument("--confirm-target", default=None)
    parser.add_argument("--production-write-confirmation", default=None)
    parser.add_argument("--confirm-database-target", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    target = resolve_database_target(
        args.database_url,
        allow_remote_write=args.allow_remote_write,
        confirm_target=args.confirm_target,
        production_write_confirmation=args.production_write_confirmation,
        confirm_database_target=args.confirm_database_target,
    )
    assert target is not None  # --database-url is a required argument
    database_url = target.database_url

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
