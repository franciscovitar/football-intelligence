"""Idempotent PostgreSQL persistence for normalized provider data."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg import Connection

from football_intelligence.data_quality.coverage import CoverageReport
from football_intelligence.ingestion.raw_store import RawObjectRef
from football_intelligence.normalization.models import (
    MatchRecord,
    NormalizedFixtureBatch,
    PlayerAppearanceRecord,
    PlayerMatchStatsRecord,
    PlayerRecord,
    TeamMatchStatsRecord,
    TeamRecord,
)


class ProviderRepository:
    """Persist one provider-normalized batch inside a transaction."""

    def __init__(self, connection: Connection[Any], *, provider_code: str) -> None:
        self._connection = connection
        self._provider_code = provider_code
        self._provider_id = self._lookup_provider_id(provider_code)

    def start_run(
        self,
        *,
        job_name: str,
        trigger_kind: str,
        scope: dict[str, Any],
    ) -> int:
        row = self._connection.execute(
            """
            insert into ingestion.ingestion_runs (
                provider_id, job_name, trigger_kind, scope
            )
            values (%s, %s, %s, %s::jsonb)
            returning id
            """,
            (self._provider_id, job_name, trigger_kind, json.dumps(scope)),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to create ingestion run")
        return int(row[0])

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        request_count: int,
        rows_written: int,
        metadata: dict[str, Any],
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self._connection.execute(
            """
            update ingestion.ingestion_runs
            set
                status = %s,
                request_count = %s,
                rows_written = %s,
                finished_at = now(),
                metadata = %s::jsonb,
                error_code = %s,
                error_message = %s
            where id = %s
            """,
            (
                status,
                request_count,
                rows_written,
                json.dumps(metadata),
                error_code,
                error_message,
                run_id,
            ),
        )

    def record_raw_objects(
        self,
        run_id: int,
        raw_objects: Iterable[RawObjectRef],
        *,
        http_status: int = 200,
    ) -> None:
        for raw in raw_objects:
            self._connection.execute(
                """
                insert into ingestion.raw_objects (
                    ingestion_run_id,
                    storage_bucket,
                    storage_path,
                    endpoint,
                    request_fingerprint,
                    http_status,
                    content_type,
                    content_encoding,
                    payload_sha256,
                    byte_size
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (storage_bucket, storage_path) do update
                set
                    ingestion_run_id = excluded.ingestion_run_id,
                    fetched_at = now(),
                    http_status = excluded.http_status,
                    content_type = excluded.content_type,
                    content_encoding = excluded.content_encoding,
                    payload_sha256 = excluded.payload_sha256,
                    byte_size = excluded.byte_size
                """,
                (
                    run_id,
                    raw.storage_bucket,
                    raw.storage_path,
                    raw.endpoint,
                    raw.request_fingerprint,
                    http_status,
                    raw.content_type,
                    raw.content_encoding,
                    raw.payload_sha256,
                    raw.byte_size,
                ),
            )

    def persist_batch(
        self,
        *,
        competition_code: str,
        batch: NormalizedFixtureBatch,
    ) -> int:
        competition_id = self._upsert_competition_mapping(
            competition_code=competition_code,
            external_id=batch.provider_competition_id,
        )
        season_id = self._upsert_season(
            competition_id=competition_id,
            label=batch.season_label,
        )

        team_ids = {team.external_id: self._upsert_team(team) for team in batch.teams}
        player_ids = {player.external_id: self._upsert_player(player) for player in batch.players}

        match_ids: dict[str, int] = {}
        for match in batch.matches:
            match_ids[match.external_id] = self._upsert_match(
                season_id=season_id,
                team_ids=team_ids,
                match=match,
            )

        for team_stats in batch.team_match_stats:
            self._upsert_team_stats(match_ids, team_ids, team_stats)

        for appearance in batch.appearances:
            self._upsert_appearance(match_ids, team_ids, player_ids, appearance)

        for player_stats in batch.player_match_stats:
            self._upsert_player_stats(match_ids, player_ids, player_stats)

        return (
            len(batch.teams)
            + len(batch.players)
            + len(batch.matches)
            + len(batch.team_match_stats)
            + len(batch.appearances)
            + len(batch.player_match_stats)
        )

    def upsert_capabilities(
        self,
        coverage: dict[str, CoverageReport],
    ) -> None:
        for entity_type, metrics in coverage.items():
            for metric_name, summary in metrics.items():
                self._connection.execute(
                    """
                    insert into ingestion.data_capabilities (
                        provider_id,
                        entity_type,
                        metric_name,
                        availability,
                        sample_size,
                        non_null_count,
                        observed_at
                    )
                    values (%s, %s, %s, %s, %s, %s, now())
                    on conflict (provider_id, entity_type, metric_name) do update
                    set
                        availability = excluded.availability,
                        sample_size = excluded.sample_size,
                        non_null_count = excluded.non_null_count,
                        observed_at = excluded.observed_at
                    """,
                    (
                        self._provider_id,
                        entity_type,
                        metric_name,
                        str(summary["availability"]),
                        int(summary["sample_size"]),
                        int(summary["non_null_count"]),
                    ),
                )

    def snapshot_counts(self) -> dict[str, int]:
        queries = {
            "teams": "select count(*) from football.teams",
            "players": "select count(*) from football.players",
            "matches": "select count(*) from football.matches",
            "team_match_stats": "select count(*) from football.team_match_stats",
            "player_appearances": "select count(*) from football.player_appearances",
            "player_match_stats": "select count(*) from football.player_match_stats",
        }
        result: dict[str, int] = {}
        for key, query in queries.items():
            row = self._connection.execute(query).fetchone()
            if row is None:
                raise RuntimeError(f"failed to count {key}")
            result[key] = int(row[0])
        return result

    def _lookup_provider_id(self, provider_code: str) -> int:
        row = self._connection.execute(
            "select id from ingestion.providers where code = %s",
            (provider_code,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"provider seed not found: {provider_code}")
        return int(row[0])

    def _upsert_competition_mapping(self, *, competition_code: str, external_id: str) -> int:
        row = self._connection.execute(
            """
            select id
            from football.competitions
            where code = %s
            """,
            (competition_code,),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"competition seed not found: {competition_code}")
        competition_id = int(row[0])

        self._connection.execute(
            """
            insert into football.competition_provider_ids (
                provider_id, competition_id, external_id
            )
            values (%s, %s, %s)
            on conflict (provider_id, competition_id) do update
            set external_id = excluded.external_id, updated_at = now()
            """,
            (self._provider_id, competition_id, external_id),
        )
        return competition_id

    def _upsert_season(self, *, competition_id: int, label: str) -> int:
        row = self._connection.execute(
            """
            insert into football.seasons (competition_id, label)
            values (%s, %s)
            on conflict (competition_id, label) do update
            set updated_at = now()
            returning id
            """,
            (competition_id, label),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to upsert season")
        return int(row[0])

    def _upsert_team(self, team: TeamRecord) -> int:
        existing = self._connection.execute(
            """
            select team_id
            from football.team_provider_ids
            where provider_id = %s and external_id = %s
            """,
            (self._provider_id, team.external_id),
        ).fetchone()

        if existing is None:
            row = self._connection.execute(
                """
                insert into football.teams (name, short_name, country_code)
                values (%s, %s, %s)
                returning id
                """,
                (team.name, team.short_name, team.country_code),
            ).fetchone()
            if row is None:
                raise RuntimeError("failed to insert team")
            team_id = int(row[0])
            self._connection.execute(
                """
                insert into football.team_provider_ids (
                    provider_id, team_id, external_id
                )
                values (%s, %s, %s)
                """,
                (self._provider_id, team_id, team.external_id),
            )
            return team_id

        team_id = int(existing[0])
        self._connection.execute(
            """
            update football.teams
            set name = %s, short_name = %s, country_code = %s, updated_at = now()
            where id = %s
            """,
            (team.name, team.short_name, team.country_code, team_id),
        )
        return team_id

    def _upsert_player(self, player: PlayerRecord) -> int:
        existing = self._connection.execute(
            """
            select player_id
            from football.player_provider_ids
            where provider_id = %s and external_id = %s
            """,
            (self._provider_id, player.external_id),
        ).fetchone()

        if existing is None:
            row = self._connection.execute(
                """
                insert into football.players (
                    display_name, first_name, last_name, date_of_birth, nationality_code
                )
                values (%s, %s, %s, %s, %s)
                returning id
                """,
                (
                    player.display_name,
                    player.first_name,
                    player.last_name,
                    player.date_of_birth,
                    player.nationality_code,
                ),
            ).fetchone()
            if row is None:
                raise RuntimeError("failed to insert player")
            player_id = int(row[0])
            self._connection.execute(
                """
                insert into football.player_provider_ids (
                    provider_id, player_id, external_id
                )
                values (%s, %s, %s)
                """,
                (self._provider_id, player_id, player.external_id),
            )
            return player_id

        player_id = int(existing[0])
        self._connection.execute(
            """
            update football.players
            set display_name = %s, updated_at = now()
            where id = %s
            """,
            (player.display_name, player_id),
        )
        return player_id

    def _upsert_match(
        self,
        *,
        season_id: int,
        team_ids: dict[str, int],
        match: MatchRecord,
    ) -> int:
        existing = self._connection.execute(
            """
            select match_id
            from football.match_provider_ids
            where provider_id = %s and external_id = %s
            """,
            (self._provider_id, match.external_id),
        ).fetchone()

        values = (
            season_id,
            team_ids[match.home_team_external_id],
            team_ids[match.away_team_external_id],
            match.kickoff_at,
            match.status,
            match.round_name,
            match.venue_name,
            match.home_score,
            match.away_score,
        )

        if existing is None:
            row = self._connection.execute(
                """
                insert into football.matches (
                    season_id,
                    home_team_id,
                    away_team_id,
                    kickoff_at,
                    status,
                    round_name,
                    venue_name,
                    home_score,
                    away_score
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                values,
            ).fetchone()
            if row is None:
                raise RuntimeError("failed to insert match")
            match_id = int(row[0])
            self._connection.execute(
                """
                insert into football.match_provider_ids (
                    provider_id, match_id, external_id
                )
                values (%s, %s, %s)
                """,
                (self._provider_id, match_id, match.external_id),
            )
            return match_id

        match_id = int(existing[0])
        self._connection.execute(
            """
            update football.matches
            set
                season_id = %s,
                home_team_id = %s,
                away_team_id = %s,
                kickoff_at = %s,
                status = %s,
                round_name = %s,
                venue_name = %s,
                home_score = %s,
                away_score = %s,
                updated_at = now()
            where id = %s
            """,
            (*values, match_id),
        )
        return match_id

    def _upsert_team_stats(
        self,
        match_ids: dict[str, int],
        team_ids: dict[str, int],
        stats: TeamMatchStatsRecord,
    ) -> None:
        values = asdict(stats)
        self._connection.execute(
            """
            insert into football.team_match_stats (
                match_id, team_id, possession_pct, shots_total, shots_on_target,
                shots_inside_box, shots_outside_box, blocked_shots, corners,
                offsides, fouls, yellow_cards, red_cards, passes_total,
                passes_accurate, goalkeeper_saves
            )
            values (
                %(match_id)s, %(team_id)s, %(possession_pct)s, %(shots_total)s,
                %(shots_on_target)s, %(shots_inside_box)s, %(shots_outside_box)s,
                %(blocked_shots)s, %(corners)s, %(offsides)s, %(fouls)s,
                %(yellow_cards)s, %(red_cards)s, %(passes_total)s,
                %(passes_accurate)s, %(goalkeeper_saves)s
            )
            on conflict (match_id, team_id) do update
            set
                possession_pct = excluded.possession_pct,
                shots_total = excluded.shots_total,
                shots_on_target = excluded.shots_on_target,
                shots_inside_box = excluded.shots_inside_box,
                shots_outside_box = excluded.shots_outside_box,
                blocked_shots = excluded.blocked_shots,
                corners = excluded.corners,
                offsides = excluded.offsides,
                fouls = excluded.fouls,
                yellow_cards = excluded.yellow_cards,
                red_cards = excluded.red_cards,
                passes_total = excluded.passes_total,
                passes_accurate = excluded.passes_accurate,
                goalkeeper_saves = excluded.goalkeeper_saves,
                updated_at = now()
            """,
            {
                **values,
                "match_id": match_ids[stats.match_external_id],
                "team_id": team_ids[stats.team_external_id],
            },
        )

    def _upsert_appearance(
        self,
        match_ids: dict[str, int],
        team_ids: dict[str, int],
        player_ids: dict[str, int],
        appearance: PlayerAppearanceRecord,
    ) -> None:
        self._connection.execute(
            """
            insert into football.player_appearances (
                match_id, player_id, team_id, minutes, started, captain,
                shirt_number, listed_position
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (match_id, player_id) do update
            set
                team_id = excluded.team_id,
                minutes = excluded.minutes,
                started = excluded.started,
                captain = excluded.captain,
                shirt_number = excluded.shirt_number,
                listed_position = excluded.listed_position,
                updated_at = now()
            """,
            (
                match_ids[appearance.match_external_id],
                player_ids[appearance.player_external_id],
                team_ids[appearance.team_external_id],
                appearance.minutes,
                appearance.started,
                appearance.captain,
                appearance.shirt_number,
                appearance.listed_position,
            ),
        )

    def _upsert_player_stats(
        self,
        match_ids: dict[str, int],
        player_ids: dict[str, int],
        stats: PlayerMatchStatsRecord,
    ) -> None:
        values = asdict(stats)
        self._connection.execute(
            """
            insert into football.player_match_stats (
                match_id, player_id, goals, assists, shots_total, shots_on_target,
                passes_total, passes_accurate, key_passes, tackles, blocks,
                interceptions, clearances, dribbles_attempted, dribbles_successful,
                duels_total, duels_won, fouls_drawn, fouls_committed,
                yellow_cards, red_cards, saves
            )
            values (
                %(match_id)s, %(player_id)s, %(goals)s, %(assists)s,
                %(shots_total)s, %(shots_on_target)s, %(passes_total)s,
                %(passes_accurate)s, %(key_passes)s, %(tackles)s, %(blocks)s,
                %(interceptions)s, %(clearances)s, %(dribbles_attempted)s,
                %(dribbles_successful)s, %(duels_total)s, %(duels_won)s,
                %(fouls_drawn)s, %(fouls_committed)s, %(yellow_cards)s,
                %(red_cards)s, %(saves)s
            )
            on conflict (match_id, player_id) do update
            set
                goals = excluded.goals,
                assists = excluded.assists,
                shots_total = excluded.shots_total,
                shots_on_target = excluded.shots_on_target,
                passes_total = excluded.passes_total,
                passes_accurate = excluded.passes_accurate,
                key_passes = excluded.key_passes,
                tackles = excluded.tackles,
                blocks = excluded.blocks,
                interceptions = excluded.interceptions,
                clearances = excluded.clearances,
                dribbles_attempted = excluded.dribbles_attempted,
                dribbles_successful = excluded.dribbles_successful,
                duels_total = excluded.duels_total,
                duels_won = excluded.duels_won,
                fouls_drawn = excluded.fouls_drawn,
                fouls_committed = excluded.fouls_committed,
                yellow_cards = excluded.yellow_cards,
                red_cards = excluded.red_cards,
                saves = excluded.saves,
                updated_at = now()
            """,
            {
                **values,
                "match_id": match_ids[stats.match_external_id],
                "player_id": player_ids[stats.player_external_id],
            },
        )


def connect(database_url: str) -> Connection[Any]:
    """Open a PostgreSQL connection using Psycopg 3."""

    return psycopg.connect(database_url)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
