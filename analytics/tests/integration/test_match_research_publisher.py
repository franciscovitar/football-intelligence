from __future__ import annotations

import os
from copy import deepcopy

import psycopg
import pytest

from football_intelligence.publishing.publisher import (
    IdempotencyConflictError,
    IdentityConflictError,
    RevisionConflictError,
    publish_match_research,
)
from tests.test_match_publish_package import valid_publish_payload


def _database_url() -> str:
    value = os.environ.get("DATABASE_URL")
    if not value:
        pytest.skip("DATABASE_URL not configured")
    return value


def _seed_fixture_catalog(connection: psycopg.Connection[tuple[object, ...]]) -> None:
    competition_id = connection.execute(
        """
        insert into public.competitions (slug, name, country_code, competition_type, active)
        values ('test-league', 'Test League', 'AR', 'LEAGUE', true)
        on conflict (slug) do update set active = true
        returning id
        """
    ).fetchone()[0]
    season_id = connection.execute(
        """
        insert into public.seasons (competition_id, label, status)
        values (%s, '2026/27', 'ACTIVE')
        on conflict (competition_id, label) do update set status = 'ACTIVE'
        returning id
        """,
        (competition_id,),
    ).fetchone()[0]
    connection.execute(
        """
        insert into public.rounds (season_id, stage_id, label, sequence)
        select %s, null, 'Round 1', 1
        where not exists (
          select 1 from public.rounds
          where season_id = %s and stage_id is null and label = 'Round 1'
        )
        """,
        (season_id, season_id),
    )


def _version(payload: dict[str, object], version: int, run_key: str) -> dict[str, object]:
    revised = deepcopy(payload)
    revised["research"]["run_key"] = run_key  # type: ignore[index]
    revised["match_review"]["review_version"] = version  # type: ignore[index]
    revised["match_review"]["summary"] = (  # type: ignore[index]
        "Revisión explícita de la lectura del partido con nueva evidencia, sin borrar el historial."
    )
    for collection in ("team_reviews", "manager_reviews", "player_reviews"):
        for review in revised[collection]:  # type: ignore[union-attr]
            review["review_version"] = version
    return revised


@pytest.mark.integration
def test_publish_is_atomic_and_exact_retry_is_idempotent() -> None:
    with psycopg.connect(_database_url(), autocommit=False) as connection:
        try:
            _seed_fixture_catalog(connection)
            payload = valid_publish_payload()

            first = publish_match_research(connection, payload)
            second = publish_match_research(connection, payload)

            assert first.status == "PUBLISHED"
            assert second.status == "ALREADY_PUBLISHED"
            assert first.match_id == second.match_id
            assert first.research_run_id == second.research_run_id

            run_count = connection.execute(
                "select count(*) from public.research_runs where run_key = 'test-run-0001'"
            ).fetchone()[0]
            match_count = connection.execute(
                "select count(*) from public.matches where external_identity_key = %s",
                (payload["match"]["identity_key"],),  # type: ignore[index]
            ).fetchone()[0]
            assert run_count == 1
            assert match_count == 1
        finally:
            connection.rollback()


@pytest.mark.integration
def test_same_run_key_with_changed_payload_fails_closed() -> None:
    with psycopg.connect(_database_url(), autocommit=False) as connection:
        try:
            _seed_fixture_catalog(connection)
            payload = valid_publish_payload()
            publish_match_research(connection, payload)

            changed = deepcopy(payload)
            changed["match_review"]["summary"] = (  # type: ignore[index]
                "Mismo run key pero contenido distinto, que debe considerarse un conflicto de idempotencia."
            )
            with pytest.raises(IdempotencyConflictError):
                publish_match_research(connection, changed)
        finally:
            connection.rollback()


@pytest.mark.integration
def test_dry_run_exercises_flow_but_persists_nothing() -> None:
    with psycopg.connect(_database_url(), autocommit=False) as connection:
        try:
            _seed_fixture_catalog(connection)
            payload = valid_publish_payload()
            result = publish_match_research(connection, payload, dry_run=True)
            assert result.status == "DRY_RUN"
            assert (
                connection.execute(
                    "select count(*) from public.research_runs where run_key = 'test-run-0001'"
                ).fetchone()[0]
                == 0
            )
            assert (
                connection.execute(
                    "select count(*) from public.matches where external_identity_key = %s",
                    (payload["match"]["identity_key"],),  # type: ignore[index]
                ).fetchone()[0]
                == 0
            )
        finally:
            connection.rollback()


@pytest.mark.integration
def test_mid_transaction_identity_conflict_rolls_back_prior_updates() -> None:
    with psycopg.connect(_database_url(), autocommit=False) as connection:
        try:
            _seed_fixture_catalog(connection)
            connection.execute(
                """
                insert into public.managers (slug, display_name, nationality)
                values ('alpha-coach', 'Old Coach Name', 'AR')
                on conflict (slug) do update set display_name = 'Old Coach Name'
                """
            )
            connection.execute(
                """
                insert into public.players (slug, display_name, birth_date)
                values ('alpha-player', 'Alpha Player', '1999-01-01')
                on conflict (slug) do update set birth_date = '1999-01-01'
                """
            )

            with pytest.raises(IdentityConflictError, match="birth_date"):
                publish_match_research(connection, valid_publish_payload())

            manager_name = connection.execute(
                "select display_name from public.managers where slug = 'alpha-coach'"
            ).fetchone()[0]
            run_count = connection.execute(
                "select count(*) from public.research_runs where run_key = 'test-run-0001'"
            ).fetchone()[0]
            assert manager_name == "Old Coach Name"
            assert run_count == 0
        finally:
            connection.rollback()


@pytest.mark.integration
def test_revision_preserves_history_and_switches_current_atomically() -> None:
    with psycopg.connect(_database_url(), autocommit=False) as connection:
        try:
            _seed_fixture_catalog(connection)
            v1 = valid_publish_payload()
            first = publish_match_research(connection, v1)
            v2 = _version(v1, 2, "test-run-0002")

            second = publish_match_research(
                connection,
                v2,
                revision_reason="New verified evidence materially changed the published reading.",
            )

            assert first.status == "PUBLISHED"
            assert second.status == "PUBLISHED"
            rows = connection.execute(
                """
                select review_version, status from public.match_reviews
                where match_id = %s order by review_version
                """,
                (second.match_id,),
            ).fetchall()
            assert rows == [(1, "REVISED"), (2, "PUBLISHED")]
            assert (
                connection.execute(
                    "select count(*) from public.rating_revisions where entity_type = 'MATCH'"
                ).fetchone()[0]
                >= 1
            )
            assert (
                connection.execute(
                    """
                    select count(*) from public.player_match_reviews
                    where match_id = %s and status = 'PUBLISHED'
                    """,
                    (second.match_id,),
                ).fetchone()[0]
                == len(v2["player_reviews"])  # type: ignore[arg-type]
            )
        finally:
            connection.rollback()


@pytest.mark.integration
def test_revision_without_reason_fails_without_creating_v2() -> None:
    with psycopg.connect(_database_url(), autocommit=False) as connection:
        try:
            _seed_fixture_catalog(connection)
            v1 = valid_publish_payload()
            first = publish_match_research(connection, v1)
            v2 = _version(v1, 2, "test-run-0002")

            with pytest.raises(RevisionConflictError, match="revision-reason"):
                publish_match_research(connection, v2)

            assert (
                connection.execute(
                    "select count(*) from public.match_reviews where match_id = %s",
                    (first.match_id,),
                ).fetchone()[0]
                == 1
            )
            assert (
                connection.execute(
                    "select count(*) from public.research_runs where run_key = 'test-run-0002'"
                ).fetchone()[0]
                == 0
            )
        finally:
            connection.rollback()
