"""Transactional publisher for ``MATCH_RESEARCH_PUBLISH_V1`` packages."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from psycopg import Connection, sql
from psycopg.types.json import Jsonb

from football_intelligence.publishing.package import (
    JsonObject,
    match_publish_package_digest,
    require_publishable_package,
    validate_match_publish_package,
)

PUBLISHER_VERSION = "MATCH_PUBLISHER_V1"
_PUBLIC_SIGNAL_STATES = frozenset({"SUPPORTED", "PARTIAL", "MIXED"})


class MatchPublishError(RuntimeError):
    """Base error for safe publication failures."""


class CatalogMissingError(MatchPublishError):
    """The fixture/catalog universe is not ready for this research package."""


class IdentityConflictError(MatchPublishError):
    """A stable identity points to materially conflicting persisted facts."""


class IdempotencyConflictError(MatchPublishError):
    """A run key was already used by a different package."""


class RevisionConflictError(MatchPublishError):
    """The requested review revision is not a safe successor."""


class IntegrityGateError(MatchPublishError):
    """Objective database integrity checks failed before publication."""


@dataclass(frozen=True, slots=True)
class MatchPublishResult:
    status: Literal["PUBLISHED", "ALREADY_PUBLISHED", "DRY_RUN"]
    match_id: str
    research_run_id: str | None
    review_version: int
    package_sha256: str


@dataclass(frozen=True, slots=True)
class _CurrentReviews:
    match_id: UUID | None
    match_version: int | None
    teams: dict[str, UUID]
    managers: dict[str, UUID]
    players: dict[str, UUID]


@dataclass(frozen=True, slots=True)
class _InsertedReviews:
    match_id: UUID
    teams: dict[str, UUID]
    managers: dict[str, UUID]
    players: dict[str, UUID]


@dataclass(frozen=True, slots=True)
class _DryRunRollback(Exception):
    result: MatchPublishResult


def publish_match_research(
    connection: Connection[Any],
    payload: JsonObject,
    *,
    dry_run: bool = False,
    revision_reason: str | None = None,
) -> MatchPublishResult:
    """Validate and atomically publish one researched match package.

    The caller owns connection credentials. This function never opens a
    connection and never weakens the repository's production-write guard.
    """

    validate_match_publish_package(payload)
    require_publishable_package(payload)
    digest = match_publish_package_digest(payload)
    try:
        with connection.transaction():
            result = _publish_in_transaction(
                connection,
                payload,
                package_sha256=digest,
                revision_reason=revision_reason,
            )
            if dry_run and result.status == "PUBLISHED":
                raise _DryRunRollback(replace(result, status="DRY_RUN"))
            return result
    except _DryRunRollback as exc:
        return exc.result


def _publish_in_transaction(
    connection: Connection[Any],
    payload: JsonObject,
    *,
    package_sha256: str,
    revision_reason: str | None,
) -> MatchPublishResult:
    research = _object(payload, "research")
    match = _object(payload, "match")
    run_key = _required_str(research, "run_key")
    identity_key = _required_str(match, "identity_key")
    review_version = _required_int(_object(payload, "match_review"), "review_version")

    for lock_key in sorted((f"match:{identity_key}", f"research-run:{run_key}")):
        connection.execute("select pg_advisory_xact_lock(hashtext(%s))", (lock_key,))

    existing = connection.execute(
        "select id, status, metadata, match_id from public.research_runs where run_key = %s",
        (run_key,),
    ).fetchone()
    if existing is not None:
        metadata = existing[2] if isinstance(existing[2], dict) else {}
        existing_digest = metadata.get("package_sha256")
        if existing_digest != package_sha256:
            raise IdempotencyConflictError(
                f"research.run_key {run_key!r} already belongs to a different package"
            )
        if existing[1] == "PUBLISHED" and existing[3] is not None:
            return MatchPublishResult(
                status="ALREADY_PUBLISHED",
                match_id=str(existing[3]),
                research_run_id=str(existing[0]),
                review_version=review_version,
                package_sha256=package_sha256,
            )
        raise IdempotencyConflictError(
            f"research.run_key {run_key!r} already exists in non-published state {existing[1]!r}"
        )

    competition_id, season_id, stage_id, round_id = _resolve_fixture_catalog(connection, match)
    team_ids = _upsert_teams(connection, _object_list(payload, "teams"))
    manager_ids = _upsert_managers(connection, _object_list(payload, "managers"))
    player_ids = _upsert_players(connection, _object_list(payload, "players"))
    source_ids = _upsert_sources(connection, _object_list(payload, "sources"))
    document_ids = _upsert_documents(
        connection,
        _object_list(payload, "documents"),
        source_ids=source_ids,
    )

    match_id = _upsert_match(
        connection,
        match,
        competition_id=competition_id,
        season_id=season_id,
        stage_id=stage_id,
        round_id=round_id,
        team_ids=team_ids,
    )
    current = _load_current_reviews(
        connection,
        match_id,
        team_ids=team_ids,
        manager_ids=manager_ids,
        player_ids=player_ids,
    )
    _validate_revision_transition(
        current,
        payload,
        incoming_version=review_version,
        revision_reason=revision_reason,
    )

    research_run_id = _insert_research_run(
        connection,
        research,
        match_id=match_id,
        package_sha256=package_sha256,
    )
    _upsert_appearances(
        connection,
        _object_list(payload, "appearances"),
        match_id=match_id,
        team_ids=team_ids,
        player_ids=player_ids,
    )
    _upsert_team_stats(
        connection,
        _object_list(payload, "team_stats"),
        match_id=match_id,
        team_ids=team_ids,
        source_ids=source_ids,
        retrieved_at=_parse_datetime(_required_str(research, "data_cutoff")),
        allow_correction=revision_reason is not None,
    )
    _upsert_player_stats(
        connection,
        _object_list(payload, "player_stats"),
        match_id=match_id,
        team_ids=team_ids,
        player_ids=player_ids,
        source_ids=source_ids,
        retrieved_at=_parse_datetime(_required_str(research, "data_cutoff")),
        allow_correction=revision_reason is not None,
    )

    entity_ids = _entity_id_map(
        identity_key=identity_key,
        match_id=match_id,
        team_ids=team_ids,
        manager_ids=manager_ids,
        player_ids=player_ids,
    )
    _insert_evidence(
        connection,
        _object_list(payload, "evidence"),
        research_run_id=research_run_id,
        match_id=match_id,
        entity_ids=entity_ids,
        document_ids=document_ids,
    )
    _insert_fan_themes(
        connection,
        _object_list(payload, "fan_themes"),
        research_run_id=research_run_id,
        match_id=match_id,
        entity_ids=entity_ids,
        document_ids=document_ids,
    )
    signal_ids = _insert_signals(
        connection,
        _object_list(payload, "signals", required=False),
        research_run_id=research_run_id,
        methodology_sha=_required_str(research, "methodology_sha"),
        entity_ids=entity_ids,
    )
    inserted = _insert_reviews(
        connection,
        payload,
        research_run_id=research_run_id,
        match_id=match_id,
        team_ids=team_ids,
        manager_ids=manager_ids,
        player_ids=player_ids,
        document_ids=document_ids,
        current=current,
    )

    connection.execute(
        "update public.research_runs set status = 'QA', qa_status = 'PASS' where id = %s",
        (research_run_id,),
    )
    _pre_publish_integrity_gate(
        connection,
        payload,
        match_id=match_id,
        research_run_id=research_run_id,
        inserted=inserted,
        document_ids=document_ids,
    )
    _finalize_publication(
        connection,
        current=current,
        inserted=inserted,
        research_run_id=research_run_id,
        signal_ids=signal_ids,
        revision_reason=revision_reason,
    )
    _post_publish_integrity_gate(
        connection,
        payload,
        match_id=match_id,
        research_run_id=research_run_id,
    )

    return MatchPublishResult(
        status="PUBLISHED",
        match_id=str(match_id),
        research_run_id=str(research_run_id),
        review_version=review_version,
        package_sha256=package_sha256,
    )


def _resolve_fixture_catalog(
    connection: Connection[Any], match: JsonObject
) -> tuple[UUID, UUID, UUID | None, UUID | None]:
    competition_slug = _required_str(match, "competition_slug")
    row = connection.execute(
        "select id from public.competitions where slug = %s and active = true",
        (competition_slug,),
    ).fetchone()
    if row is None:
        raise CatalogMissingError(
            f"competition {competition_slug!r} is not in the active fixture catalog"
        )
    competition_id = _as_uuid(row[0])

    season_label = _required_str(match, "season_label")
    row = connection.execute(
        """
        select id, status from public.seasons
        where competition_id = %s and label = %s
        """,
        (competition_id, season_label),
    ).fetchone()
    if row is None or row[1] == "ARCHIVED":
        raise CatalogMissingError(
            f"season {competition_slug}/{season_label} is not an active fixture-catalog season"
        )
    season_id = _as_uuid(row[0])

    stage_id: UUID | None = None
    stage_name = match.get("stage_name")
    if stage_name is not None:
        row = connection.execute(
            "select id from public.competition_stages where season_id = %s and name = %s",
            (season_id, stage_name),
        ).fetchone()
        if row is None:
            raise CatalogMissingError(
                f"stage {stage_name!r} is not registered for {competition_slug}/{season_label}"
            )
        stage_id = _as_uuid(row[0])

    round_id: UUID | None = None
    round_label = match.get("round_label")
    if round_label is not None:
        if stage_id is None:
            row = connection.execute(
                """
                select id from public.rounds
                where season_id = %s and stage_id is null and label = %s
                order by created_at asc limit 1
                """,
                (season_id, round_label),
            ).fetchone()
        else:
            row = connection.execute(
                """
                select id from public.rounds
                where season_id = %s and stage_id = %s and label = %s
                order by created_at asc limit 1
                """,
                (season_id, stage_id, round_label),
            ).fetchone()
        if row is None:
            raise CatalogMissingError(
                f"round {round_label!r} is not registered for {competition_slug}/{season_label}"
            )
        round_id = _as_uuid(row[0])
    return competition_id, season_id, stage_id, round_id


def _upsert_teams(connection: Connection[Any], teams: list[JsonObject]) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for team in teams:
        slug = _required_str(team, "slug")
        row = connection.execute(
            "select id, name, country_code from public.teams where slug = %s", (slug,)
        ).fetchone()
        if row is None:
            row = connection.execute(
                """
                insert into public.teams (slug, name, short_name, country_code, crest_url)
                values (%s, %s, %s, %s, %s) returning id
                """,
                (
                    slug,
                    _required_str(team, "name"),
                    team.get("short_name"),
                    team.get("country_code"),
                    team.get("crest_url"),
                ),
            ).fetchone()
            if row is None:
                raise MatchPublishError(f"failed to insert team {slug}")
            ids[slug] = _as_uuid(row[0])
            continue
        if row[1] != team.get("name"):
            raise IdentityConflictError(
                f"team slug {slug!r} already maps to name {row[1]!r}, not {team.get('name')!r}"
            )
        if row[2] is not None and team.get("country_code") is not None and row[2] != team["country_code"]:
            raise IdentityConflictError(f"team {slug!r} country_code conflicts with catalog")
        team_id = _as_uuid(row[0])
        connection.execute(
            """
            update public.teams set
              short_name = coalesce(short_name, %s),
              country_code = coalesce(country_code, %s),
              crest_url = coalesce(crest_url, %s),
              updated_at = now()
            where id = %s
            """,
            (team.get("short_name"), team.get("country_code"), team.get("crest_url"), team_id),
        )
        ids[slug] = team_id
    return ids


def _upsert_players(
    connection: Connection[Any], players: list[JsonObject]
) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for player in players:
        slug = _required_str(player, "slug")
        row = connection.execute(
            "select id, birth_date from public.players where slug = %s", (slug,)
        ).fetchone()
        birth_date = _optional_date(player.get("birth_date"))
        if row is None:
            row = connection.execute(
                """
                insert into public.players
                  (slug, display_name, full_name, birth_date, nationality, preferred_foot)
                values (%s, %s, %s, %s, %s, %s) returning id
                """,
                (
                    slug,
                    _required_str(player, "display_name"),
                    player.get("full_name"),
                    birth_date,
                    player.get("nationality"),
                    player.get("preferred_foot"),
                ),
            ).fetchone()
            if row is None:
                raise MatchPublishError(f"failed to insert player {slug}")
            ids[slug] = _as_uuid(row[0])
            continue
        if row[1] is not None and birth_date is not None and row[1] != birth_date:
            raise IdentityConflictError(f"player slug {slug!r} has conflicting birth_date")
        player_id = _as_uuid(row[0])
        connection.execute(
            """
            update public.players set
              display_name = %s,
              full_name = coalesce(full_name, %s),
              birth_date = coalesce(birth_date, %s),
              nationality = coalesce(nationality, %s),
              preferred_foot = coalesce(preferred_foot, %s),
              updated_at = now()
            where id = %s
            """,
            (
                _required_str(player, "display_name"),
                player.get("full_name"),
                birth_date,
                player.get("nationality"),
                player.get("preferred_foot"),
                player_id,
            ),
        )
        ids[slug] = player_id
    return ids


def _upsert_managers(
    connection: Connection[Any], managers: list[JsonObject]
) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for manager in managers:
        slug = _required_str(manager, "slug")
        row = connection.execute(
            "select id from public.managers where slug = %s", (slug,)
        ).fetchone()
        if row is None:
            row = connection.execute(
                """
                insert into public.managers (slug, display_name, nationality)
                values (%s, %s, %s) returning id
                """,
                (slug, _required_str(manager, "display_name"), manager.get("nationality")),
            ).fetchone()
            if row is None:
                raise MatchPublishError(f"failed to insert manager {slug}")
        else:
            manager_id = _as_uuid(row[0])
            connection.execute(
                """
                update public.managers set display_name = %s,
                  nationality = coalesce(nationality, %s), updated_at = now()
                where id = %s
                """,
                (_required_str(manager, "display_name"), manager.get("nationality"), manager_id),
            )
        ids[slug] = _as_uuid(row[0])
    return ids


def _upsert_sources(
    connection: Connection[Any], sources: list[JsonObject]
) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for source in sources:
        key = _required_str(source, "key")
        name = _required_str(source, "name")
        source_type = _required_str(source, "source_type")
        row = connection.execute(
            "select id from public.sources where name = %s and source_type = %s",
            (name, source_type),
        ).fetchone()
        if row is None:
            row = connection.execute(
                """
                insert into public.sources
                  (name, source_type, domain, base_url, rights_notes, active)
                values (%s, %s, %s, %s, %s, true) returning id
                """,
                (
                    name,
                    source_type,
                    source.get("domain"),
                    source.get("base_url"),
                    source.get("rights_notes"),
                ),
            ).fetchone()
            if row is None:
                raise MatchPublishError(f"failed to insert source {key}")
        source_id = _as_uuid(row[0])
        connection.execute(
            """
            update public.sources set
              domain = coalesce(domain, %s), base_url = coalesce(base_url, %s),
              rights_notes = coalesce(rights_notes, %s), active = true, updated_at = now()
            where id = %s
            """,
            (source.get("domain"), source.get("base_url"), source.get("rights_notes"), source_id),
        )
        ids[key] = source_id
    return ids


def _upsert_documents(
    connection: Connection[Any],
    documents: list[JsonObject],
    *,
    source_ids: dict[str, UUID],
) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for document in documents:
        key = _required_str(document, "key")
        source_id = source_ids[_required_str(document, "source_key")]
        raw_url = _required_str(document, "url")
        normalized_url = _normalize_url(raw_url)
        row = connection.execute(
            "select id, source_id from public.source_documents where normalized_url = %s",
            (normalized_url,),
        ).fetchone()
        if row is not None and _as_uuid(row[1]) != source_id:
            raise IdentityConflictError(
                f"document {normalized_url!r} is already owned by a different source"
            )
        if row is None:
            row = connection.execute(
                """
                insert into public.source_documents
                  (source_id, url, normalized_url, title, author_text, published_at,
                   retrieved_at, document_type)
                values (%s, %s, %s, %s, %s, %s, %s, %s) returning id
                """,
                (
                    source_id,
                    raw_url,
                    normalized_url,
                    document.get("title"),
                    document.get("author"),
                    _optional_datetime(document.get("published_at")),
                    _parse_datetime(_required_str(document, "retrieved_at")),
                    _required_str(document, "document_type"),
                ),
            ).fetchone()
            if row is None:
                raise MatchPublishError(f"failed to insert document {key}")
        document_id = _as_uuid(row[0])
        connection.execute(
            """
            update public.source_documents set
              title = coalesce(title, %s), author_text = coalesce(author_text, %s),
              published_at = coalesce(published_at, %s),
              retrieved_at = greatest(retrieved_at, %s)
            where id = %s
            """,
            (
                document.get("title"),
                document.get("author"),
                _optional_datetime(document.get("published_at")),
                _parse_datetime(_required_str(document, "retrieved_at")),
                document_id,
            ),
        )
        ids[key] = document_id
    return ids


def _upsert_match(
    connection: Connection[Any],
    match: JsonObject,
    *,
    competition_id: UUID,
    season_id: UUID,
    stage_id: UUID | None,
    round_id: UUID | None,
    team_ids: dict[str, UUID],
) -> UUID:
    del competition_id  # season foreign key already binds the competition.
    identity_key = _required_str(match, "identity_key")
    home_team_id = team_ids[_required_str(match, "home_team_slug")]
    away_team_id = team_ids[_required_str(match, "away_team_slug")]
    kickoff_at = _parse_datetime(_required_str(match, "kickoff_at"))
    row = connection.execute(
        """
        select id, season_id, stage_id, round_id, home_team_id, away_team_id,
               kickoff_at, status, home_goals, away_goals
        from public.matches where external_identity_key = %s
        """,
        (identity_key,),
    ).fetchone()
    if row is None:
        inserted = connection.execute(
            """
            insert into public.matches
              (external_identity_key, season_id, stage_id, round_id, home_team_id, away_team_id,
               kickoff_at, status, home_goals, away_goals, venue, attendance, referee,
               match_context, identity_verified)
            values (%s, %s, %s, %s, %s, %s, %s, 'FINAL', %s, %s, %s, %s, %s, %s, true)
            returning id
            """,
            (
                identity_key,
                season_id,
                stage_id,
                round_id,
                home_team_id,
                away_team_id,
                kickoff_at,
                _required_int(match, "home_goals"),
                _required_int(match, "away_goals"),
                match.get("venue"),
                match.get("attendance"),
                match.get("referee"),
                Jsonb(match.get("context", {})),
            ),
        ).fetchone()
        if inserted is None:
            raise MatchPublishError("failed to insert match")
        return _as_uuid(inserted[0])

    match_id = _as_uuid(row[0])
    fixed_pairs = (
        ("season", _as_uuid(row[1]), season_id),
        ("home team", _as_uuid(row[4]), home_team_id),
        ("away team", _as_uuid(row[5]), away_team_id),
    )
    for label, persisted, incoming in fixed_pairs:
        if persisted != incoming:
            raise IdentityConflictError(f"match {identity_key!r} has conflicting {label}")
    if row[2] is not None and stage_id is not None and _as_uuid(row[2]) != stage_id:
        raise IdentityConflictError(f"match {identity_key!r} has conflicting stage")
    if row[3] is not None and round_id is not None and _as_uuid(row[3]) != round_id:
        raise IdentityConflictError(f"match {identity_key!r} has conflicting round")
    if row[7] == "FINAL":
        if row[6] is not None and row[6] != kickoff_at:
            raise IdentityConflictError(f"final match {identity_key!r} has conflicting kickoff")
        if row[8] != match.get("home_goals") or row[9] != match.get("away_goals"):
            raise IdentityConflictError(f"final match {identity_key!r} has conflicting score")

    connection.execute(
        """
        update public.matches set
          stage_id = coalesce(stage_id, %s), round_id = coalesce(round_id, %s),
          kickoff_at = %s, status = 'FINAL', home_goals = %s, away_goals = %s,
          venue = coalesce(%s, venue), attendance = coalesce(%s, attendance),
          referee = coalesce(%s, referee), match_context = match_context || %s::jsonb,
          identity_verified = true, updated_at = now()
        where id = %s
        """,
        (
            stage_id,
            round_id,
            kickoff_at,
            _required_int(match, "home_goals"),
            _required_int(match, "away_goals"),
            match.get("venue"),
            match.get("attendance"),
            match.get("referee"),
            Jsonb(match.get("context", {})),
            match_id,
        ),
    )
    return match_id


def _insert_research_run(
    connection: Connection[Any],
    research: JsonObject,
    *,
    match_id: UUID,
    package_sha256: str,
) -> UUID:
    row = connection.execute(
        """
        insert into public.research_runs
          (run_type, target_type, target_id, match_id, methodology_sha,
           search_protocol_version, output_contract_version, rating_scale_version,
           benchmark_version, data_cutoff, status, qa_status, notes, metadata, run_key)
        values
          ('MATCH_REVIEW', 'MATCH', %s, %s, %s, %s, %s, %s, %s, %s,
           'RESEARCHING', null, %s, %s, %s)
        returning id
        """,
        (
            match_id,
            match_id,
            _required_str(research, "methodology_sha"),
            _required_str(research, "search_protocol_version"),
            _required_str(research, "output_contract_version"),
            _required_str(research, "rating_scale_version"),
            _required_str(research, "benchmark_version"),
            _parse_datetime(_required_str(research, "data_cutoff")),
            research.get("notes"),
            Jsonb(
                {
                    "package_sha256": package_sha256,
                    "contract_version": "MATCH_RESEARCH_PUBLISH_V1",
                    "publisher_version": PUBLISHER_VERSION,
                }
            ),
            _required_str(research, "run_key"),
        ),
    ).fetchone()
    if row is None:
        raise MatchPublishError("failed to create research run")
    return _as_uuid(row[0])


def _upsert_appearances(
    connection: Connection[Any],
    appearances: list[JsonObject],
    *,
    match_id: UUID,
    team_ids: dict[str, UUID],
    player_ids: dict[str, UUID],
) -> None:
    for appearance in appearances:
        player_id = player_ids[_required_str(appearance, "player_slug")]
        team_id = team_ids[_required_str(appearance, "team_slug")]
        row = connection.execute(
            "select team_id from public.player_appearances where match_id = %s and player_id = %s",
            (match_id, player_id),
        ).fetchone()
        if row is not None and _as_uuid(row[0]) != team_id:
            raise IdentityConflictError("persisted player appearance belongs to the other team")
        connection.execute(
            """
            insert into public.player_appearances
              (match_id, player_id, team_id, starter, minute_on, minute_off, minutes,
               broad_position, role_label, role_confidence, captain)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (match_id, player_id) do update set
              starter = excluded.starter,
              minute_on = coalesce(excluded.minute_on, player_appearances.minute_on),
              minute_off = coalesce(excluded.minute_off, player_appearances.minute_off),
              minutes = excluded.minutes,
              broad_position = coalesce(excluded.broad_position, player_appearances.broad_position),
              role_label = coalesce(excluded.role_label, player_appearances.role_label),
              role_confidence = coalesce(excluded.role_confidence, player_appearances.role_confidence),
              captain = coalesce(excluded.captain, player_appearances.captain),
              updated_at = now()
            """,
            (
                match_id,
                player_id,
                team_id,
                appearance.get("starter"),
                appearance.get("minute_on"),
                appearance.get("minute_off"),
                appearance.get("minutes"),
                appearance.get("broad_position"),
                appearance.get("role_label"),
                appearance.get("role_confidence"),
                appearance.get("captain"),
            ),
        )


_TEAM_STAT_COLUMNS = (
    "goals",
    "xg",
    "npxg",
    "shots",
    "shots_on_target",
    "possession_pct",
    "big_chances",
    "box_touches",
    "corners",
    "fouls",
    "field_tilt",
    "ppda",
)
_PLAYER_STAT_COLUMNS = (
    "minutes",
    "goals",
    "assists",
    "penalties_scored",
    "xg",
    "npxg",
    "xa",
    "shots",
    "shots_on_target",
    "chances_created",
    "big_chances_created",
    "touches",
    "box_touches",
    "passes_attempted",
    "passes_completed",
    "progressive_passes",
    "carries",
    "progressive_carries",
    "dribbles_attempted",
    "dribbles_completed",
    "duels_attempted",
    "duels_won",
    "aerials_attempted",
    "aerials_won",
    "tackles",
    "interceptions",
    "recoveries",
    "pressures",
)
_STAT_CONTROL_KEYS = frozenset(
    {"team_slug", "player_slug", "source_key", "provider_model", "definition_version", "evidence_class", "extra_stats", "coverage_notes"}
)


def _upsert_team_stats(
    connection: Connection[Any],
    stats: list[JsonObject],
    *,
    match_id: UUID,
    team_ids: dict[str, UUID],
    source_ids: dict[str, UUID],
    retrieved_at: datetime,
    allow_correction: bool,
) -> None:
    for item in stats:
        _upsert_stat_row(
            connection,
            table="team_match_stats",
            entity_column="team_id",
            entity_id=team_ids[_required_str(item, "team_slug")],
            match_id=match_id,
            source_id=source_ids[_required_str(item, "source_key")],
            item=item,
            canonical_columns=_TEAM_STAT_COLUMNS,
            retrieved_at=retrieved_at,
            allow_correction=allow_correction,
            team_id=None,
        )


def _upsert_player_stats(
    connection: Connection[Any],
    stats: list[JsonObject],
    *,
    match_id: UUID,
    team_ids: dict[str, UUID],
    player_ids: dict[str, UUID],
    source_ids: dict[str, UUID],
    retrieved_at: datetime,
    allow_correction: bool,
) -> None:
    for item in stats:
        _upsert_stat_row(
            connection,
            table="player_match_stats",
            entity_column="player_id",
            entity_id=player_ids[_required_str(item, "player_slug")],
            match_id=match_id,
            source_id=source_ids[_required_str(item, "source_key")],
            item=item,
            canonical_columns=_PLAYER_STAT_COLUMNS,
            retrieved_at=retrieved_at,
            allow_correction=allow_correction,
            team_id=team_ids[_required_str(item, "team_slug")],
        )


def _upsert_stat_row(
    connection: Connection[Any],
    *,
    table: Literal["team_match_stats", "player_match_stats"],
    entity_column: Literal["team_id", "player_id"],
    entity_id: UUID,
    match_id: UUID,
    source_id: UUID,
    item: JsonObject,
    canonical_columns: tuple[str, ...],
    retrieved_at: datetime,
    allow_correction: bool,
    team_id: UUID | None,
) -> None:
    provider_model = item.get("provider_model")
    definition_version = item.get("definition_version")
    query = sql.SQL(
        "select id, {columns}, extra_stats from public.{table} "
        "where match_id = %s and {entity_column} = %s and provider_source_id = %s "
        "and provider_model is not distinct from %s and definition_version is not distinct from %s "
        "order by retrieved_at desc limit 1"
    ).format(
        columns=sql.SQL(", ").join(sql.Identifier(column) for column in canonical_columns),
        table=sql.Identifier(table),
        entity_column=sql.Identifier(entity_column),
    )
    existing = connection.execute(
        query, (match_id, entity_id, source_id, provider_model, definition_version)
    ).fetchone()

    incoming_extra = dict(item.get("extra_stats", {}))
    for key, value in item.items():
        if key not in canonical_columns and key not in _STAT_CONTROL_KEYS:
            incoming_extra[key] = value

    values = [item.get(column) for column in canonical_columns]
    if existing is not None:
        if not allow_correction:
            for index, column in enumerate(canonical_columns, start=1):
                persisted = existing[index]
                incoming = item.get(column)
                if persisted is not None and incoming is not None and persisted != incoming:
                    raise IdentityConflictError(
                        f"{table} {column} conflicts with an existing same-provider value; "
                        "publish a documented revision to correct facts"
                    )
        assignments = [
            sql.SQL("{column} = coalesce(%s, {column})").format(column=sql.Identifier(column))
            for column in canonical_columns
        ]
        update_query = sql.SQL(
            "update public.{table} set {assignments}, extra_stats = extra_stats || %s::jsonb, "
            "evidence_class = %s, retrieved_at = greatest(retrieved_at, %s), "
            "coverage_notes = coalesce(%s, coverage_notes) where id = %s"
        ).format(table=sql.Identifier(table), assignments=sql.SQL(", ").join(assignments))
        connection.execute(
            update_query,
            (
                *values,
                Jsonb(incoming_extra),
                _required_str(item, "evidence_class"),
                retrieved_at,
                item.get("coverage_notes"),
                existing[0],
            ),
        )
        return

    columns = ["match_id", entity_column]
    insert_values: list[Any] = [match_id, entity_id]
    if table == "player_match_stats":
        if team_id is None:
            raise MatchPublishError("player stat row requires team_id")
        columns.append("team_id")
        insert_values.append(team_id)
    columns.extend(canonical_columns)
    insert_values.extend(values)
    columns.extend(
        [
            "extra_stats",
            "provider_source_id",
            "provider_model",
            "definition_version",
            "evidence_class",
            "retrieved_at",
            "coverage_notes",
        ]
    )
    insert_values.extend(
        [
            Jsonb(incoming_extra),
            source_id,
            provider_model,
            definition_version,
            _required_str(item, "evidence_class"),
            retrieved_at,
            item.get("coverage_notes"),
        ]
    )
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
    insert_query = sql.SQL("insert into public.{table} ({columns}) values ({placeholders})").format(
        table=sql.Identifier(table),
        columns=sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        placeholders=placeholders,
    )
    connection.execute(insert_query, tuple(insert_values))


def _entity_id_map(
    *,
    identity_key: str,
    match_id: UUID,
    team_ids: dict[str, UUID],
    manager_ids: dict[str, UUID],
    player_ids: dict[str, UUID],
) -> dict[tuple[str, str], UUID]:
    result: dict[tuple[str, str], UUID] = {("MATCH", identity_key): match_id}
    result.update({("TEAM", key): value for key, value in team_ids.items()})
    result.update({("MANAGER", key): value for key, value in manager_ids.items()})
    result.update({("PLAYER", key): value for key, value in player_ids.items()})
    return result


def _insert_evidence(
    connection: Connection[Any],
    evidence: list[JsonObject],
    *,
    research_run_id: UUID,
    match_id: UUID,
    entity_ids: dict[tuple[str, str], UUID],
    document_ids: dict[str, UUID],
) -> None:
    for item in evidence:
        document_key = item.get("document_key")
        connection.execute(
            """
            insert into public.evidence_items
              (research_run_id, document_id, match_id, entity_type, entity_id, channel,
               domain, evidence_class, claim_type, normalized_claim, direction, confidence)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                research_run_id,
                document_ids[str(document_key)] if document_key is not None else None,
                match_id,
                item.get("entity_type"),
                entity_ids[(_required_str(item, "entity_type"), _required_str(item, "entity_key"))],
                item.get("channel"),
                item.get("domain"),
                item.get("evidence_class"),
                item.get("claim_type"),
                item.get("normalized_claim"),
                item.get("direction"),
                item.get("confidence"),
            ),
        )


def _insert_fan_themes(
    connection: Connection[Any],
    themes: list[JsonObject],
    *,
    research_run_id: UUID,
    match_id: UUID,
    entity_ids: dict[tuple[str, str], UUID],
    document_ids: dict[str, UUID],
) -> None:
    for item in themes:
        document_keys = item.get("document_keys", [])
        source_document_ids = [document_ids[str(key)] for key in document_keys]
        connection.execute(
            """
            insert into public.fan_themes
              (research_run_id, match_id, entity_type, entity_id, theme, direction,
               community_cohort, coverage, repeated_signal_count, source_document_ids, caveats)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                research_run_id,
                match_id,
                item.get("entity_type"),
                entity_ids[(_required_str(item, "entity_type"), _required_str(item, "entity_key"))],
                item.get("theme"),
                item.get("direction"),
                item.get("community_cohort"),
                item.get("coverage"),
                item.get("repeated_signal_count"),
                source_document_ids,
                item.get("caveats"),
            ),
        )


def _insert_signals(
    connection: Connection[Any],
    signals: list[JsonObject],
    *,
    research_run_id: UUID,
    methodology_sha: str,
    entity_ids: dict[tuple[str, str], UUID],
) -> list[tuple[UUID, str]]:
    inserted: list[tuple[UUID, str]] = []
    for item in signals:
        row = connection.execute(
            """
            insert into public.intelligence_signals
              (entity_type, entity_id, signal_type, status, score_or_strength, confidence,
               baseline_description, rationale, research_run_id, methodology_sha)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id
            """,
            (
                item.get("entity_type"),
                entity_ids[(_required_str(item, "entity_type"), _required_str(item, "entity_key"))],
                item.get("signal_type"),
                item.get("status"),
                item.get("score_or_strength"),
                item.get("confidence"),
                item.get("baseline_description"),
                item.get("rationale"),
                research_run_id,
                methodology_sha,
            ),
        ).fetchone()
        if row is None:
            raise MatchPublishError("failed to insert intelligence signal")
        inserted.append((_as_uuid(row[0]), _required_str(item, "status")))
    return inserted


def _load_current_reviews(
    connection: Connection[Any],
    match_id: UUID,
    *,
    team_ids: dict[str, UUID],
    manager_ids: dict[str, UUID],
    player_ids: dict[str, UUID],
) -> _CurrentReviews:
    row = connection.execute(
        "select id, review_version from public.match_reviews where match_id = %s and status = 'PUBLISHED'",
        (match_id,),
    ).fetchone()
    match_review_id = _as_uuid(row[0]) if row is not None else None
    match_version = int(row[1]) if row is not None else None
    return _CurrentReviews(
        match_id=match_review_id,
        match_version=match_version,
        teams=_current_entity_reviews(connection, "team_match_reviews", "team_id", match_id, team_ids),
        managers=_current_entity_reviews(
            connection, "manager_match_reviews", "manager_id", match_id, manager_ids
        ),
        players=_current_entity_reviews(
            connection, "player_match_reviews", "player_id", match_id, player_ids
        ),
    )


def _current_entity_reviews(
    connection: Connection[Any],
    table: Literal["team_match_reviews", "manager_match_reviews", "player_match_reviews"],
    entity_column: Literal["team_id", "manager_id", "player_id"],
    match_id: UUID,
    ids_by_slug: dict[str, UUID],
) -> dict[str, UUID]:
    slug_by_id = {value: key for key, value in ids_by_slug.items()}
    query = sql.SQL(
        "select {entity_column}, id from public.{table} where match_id = %s and status = 'PUBLISHED'"
    ).format(entity_column=sql.Identifier(entity_column), table=sql.Identifier(table))
    rows = connection.execute(query, (match_id,)).fetchall()
    result: dict[str, UUID] = {}
    for entity_id_raw, review_id_raw in rows:
        entity_id = _as_uuid(entity_id_raw)
        slug = slug_by_id.get(entity_id)
        if slug is None:
            raise RevisionConflictError(
                f"current {table} contains an entity not present in the incoming identity set"
            )
        result[slug] = _as_uuid(review_id_raw)
    return result


def _validate_revision_transition(
    current: _CurrentReviews,
    payload: JsonObject,
    *,
    incoming_version: int,
    revision_reason: str | None,
) -> None:
    if current.match_version is None:
        if incoming_version != 1:
            raise RevisionConflictError("first publication for a match must use review_version 1")
        return
    if incoming_version <= current.match_version:
        raise RevisionConflictError(
            f"incoming review_version {incoming_version} must be greater than current {current.match_version}"
        )
    if not revision_reason or not revision_reason.strip():
        raise RevisionConflictError("replacing published intelligence requires --revision-reason")

    incoming_team_slugs = {item["team_slug"] for item in _object_list(payload, "team_reviews")}
    incoming_manager_slugs = {
        item["manager_slug"] for item in _object_list(payload, "manager_reviews")
    }
    incoming_player_slugs = {
        item["player_slug"] for item in _object_list(payload, "player_reviews")
    }
    if not set(current.teams).issubset(incoming_team_slugs):
        raise RevisionConflictError("a revision cannot silently drop a published team review")
    if not set(current.managers).issubset(incoming_manager_slugs):
        raise RevisionConflictError("a revision cannot silently drop a published manager review")
    if not set(current.players).issubset(incoming_player_slugs):
        raise RevisionConflictError("a revision cannot silently drop a published player review")


def _insert_reviews(
    connection: Connection[Any],
    payload: JsonObject,
    *,
    research_run_id: UUID,
    match_id: UUID,
    team_ids: dict[str, UUID],
    manager_ids: dict[str, UUID],
    player_ids: dict[str, UUID],
    document_ids: dict[str, UUID],
    current: _CurrentReviews,
) -> _InsertedReviews:
    research = _object(payload, "research")
    methodology_sha = _required_str(research, "methodology_sha")
    rating_scale_version = _required_str(research, "rating_scale_version")
    benchmark_version = _required_str(research, "benchmark_version")

    match_review = _object(payload, "match_review")
    source_ids = [document_ids[str(key)] for key in match_review["source_document_keys"]]
    row = connection.execute(
        """
        insert into public.match_reviews
          (match_id, research_run_id, review_version, summary, key_takeaways, evidence_mix,
           methodology_sha, rating_scale_version, benchmark_version, status, supersedes_review_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'QA', %s) returning id
        """,
        (
            match_id,
            research_run_id,
            match_review.get("review_version"),
            match_review.get("summary"),
            Jsonb(match_review.get("key_takeaways", [])),
            Jsonb({"source_document_ids": [str(item) for item in source_ids]}),
            methodology_sha,
            rating_scale_version,
            benchmark_version,
            current.match_id,
        ),
    ).fetchone()
    if row is None:
        raise MatchPublishError("failed to insert match review")
    inserted_match_id = _as_uuid(row[0])

    team_review_ids: dict[str, UUID] = {}
    for review in _object_list(payload, "team_reviews"):
        slug = _required_str(review, "team_slug")
        row = connection.execute(
            """
            insert into public.team_match_reviews
              (match_id, team_id, research_run_id, review_version, facts_score, expert_score,
               fan_score, final_score, confidence, evidence_status, facts_coverage,
               expert_coverage, fan_coverage, tactical_coverage, attack_score, creation_score,
               control_score, defence_score, pressing_score, offensive_transition_score,
               defensive_transition_score, set_pieces_score, summary, strengths, concerns,
               evidence_mix, methodology_sha, rating_scale_version, benchmark_version,
               status, supersedes_review_id)
            values
              (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
               %s,%s,%s,%s,%s,%s,'QA',%s) returning id
            """,
            (
                match_id,
                team_ids[slug],
                research_run_id,
                review.get("review_version"),
                review.get("facts_score"),
                review.get("expert_score"),
                review.get("fan_score"),
                review.get("final_score"),
                review.get("confidence"),
                review.get("evidence_status"),
                review.get("facts_coverage"),
                review.get("expert_coverage"),
                review.get("fan_coverage"),
                review.get("tactical_coverage"),
                review.get("attack_score"),
                review.get("creation_score"),
                review.get("control_score"),
                review.get("defence_score"),
                review.get("pressing_score"),
                review.get("offensive_transition_score"),
                review.get("defensive_transition_score"),
                review.get("set_pieces_score"),
                review.get("summary"),
                Jsonb(review.get("strengths", [])),
                Jsonb(review.get("concerns", [])),
                Jsonb(review.get("evidence_mix", {})),
                methodology_sha,
                rating_scale_version,
                benchmark_version,
                current.teams.get(slug),
            ),
        ).fetchone()
        if row is None:
            raise MatchPublishError(f"failed to insert team review {slug}")
        team_review_ids[slug] = _as_uuid(row[0])

    manager_review_ids: dict[str, UUID] = {}
    for review in _object_list(payload, "manager_reviews"):
        slug = _required_str(review, "manager_slug")
        row = connection.execute(
            """
            insert into public.manager_match_reviews
              (match_id, manager_id, team_id, research_run_id, review_version, facts_score,
               expert_score, fan_score, final_score, confidence, evidence_status,
               initial_plan_score, adaptation_score, substitutions_score, initial_plan,
               adjustments, what_worked, what_failed, summary, evidence_mix, methodology_sha,
               rating_scale_version, benchmark_version, status, supersedes_review_id)
            values
              (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
               'QA',%s) returning id
            """,
            (
                match_id,
                manager_ids[slug],
                team_ids[_required_str(review, "team_slug")],
                research_run_id,
                review.get("review_version"),
                review.get("facts_score"),
                review.get("expert_score"),
                review.get("fan_score"),
                review.get("final_score"),
                review.get("confidence"),
                review.get("evidence_status"),
                review.get("initial_plan_score"),
                review.get("adaptation_score"),
                review.get("substitutions_score"),
                review.get("initial_plan"),
                review.get("adjustments"),
                Jsonb(review.get("what_worked", [])),
                Jsonb(review.get("what_failed", [])),
                review.get("summary"),
                Jsonb(review.get("evidence_mix", {})),
                methodology_sha,
                rating_scale_version,
                benchmark_version,
                current.managers.get(slug),
            ),
        ).fetchone()
        if row is None:
            raise MatchPublishError(f"failed to insert manager review {slug}")
        manager_review_ids[slug] = _as_uuid(row[0])

    player_review_ids: dict[str, UUID] = {}
    for review in _object_list(payload, "player_reviews"):
        slug = _required_str(review, "player_slug")
        row = connection.execute(
            """
            insert into public.player_match_reviews
              (match_id, player_id, team_id, research_run_id, review_version, facts_score,
               expert_score, fan_score, final_score, confidence, evidence_status,
               facts_coverage, expert_coverage, fan_coverage, tactical_coverage, role_label,
               summary, positive_notes, negative_notes, evidence_mix, methodology_sha,
               rating_scale_version, benchmark_version, status, supersedes_review_id)
            values
              (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
               'QA',%s) returning id
            """,
            (
                match_id,
                player_ids[slug],
                team_ids[_required_str(review, "team_slug")],
                research_run_id,
                review.get("review_version"),
                review.get("facts_score"),
                review.get("expert_score"),
                review.get("fan_score"),
                review.get("final_score"),
                review.get("confidence"),
                review.get("evidence_status"),
                review.get("facts_coverage"),
                review.get("expert_coverage"),
                review.get("fan_coverage"),
                review.get("tactical_coverage"),
                review.get("role_label"),
                review.get("summary"),
                Jsonb(review.get("positive_notes", [])),
                Jsonb(review.get("negative_notes", [])),
                Jsonb(review.get("evidence_mix", {})),
                methodology_sha,
                rating_scale_version,
                benchmark_version,
                current.players.get(slug),
            ),
        ).fetchone()
        if row is None:
            raise MatchPublishError(f"failed to insert player review {slug}")
        player_review_ids[slug] = _as_uuid(row[0])

    return _InsertedReviews(
        match_id=inserted_match_id,
        teams=team_review_ids,
        managers=manager_review_ids,
        players=player_review_ids,
    )


def _pre_publish_integrity_gate(
    connection: Connection[Any],
    payload: JsonObject,
    *,
    match_id: UUID,
    research_run_id: UUID,
    inserted: _InsertedReviews,
    document_ids: dict[str, UUID],
) -> None:
    row = connection.execute(
        "select status, identity_verified, home_goals, away_goals from public.matches where id = %s",
        (match_id,),
    ).fetchone()
    match = _object(payload, "match")
    if row is None or row[0] != "FINAL" or row[1] is not True:
        raise IntegrityGateError("match must be FINAL and identity_verified before publication")
    if row[2] != match.get("home_goals") or row[3] != match.get("away_goals"):
        raise IntegrityGateError("persisted score does not match the QA-approved package")

    expected_counts = {
        "team_match_reviews": len(_object_list(payload, "team_reviews")),
        "manager_match_reviews": len(_object_list(payload, "manager_reviews")),
        "player_match_reviews": len(_object_list(payload, "player_reviews")),
    }
    for table, expected in expected_counts.items():
        table_sql = sql.Identifier(table)
        row = connection.execute(
            sql.SQL(
                "select count(*) from public.{table} where research_run_id = %s and status = 'QA'"
            ).format(table=table_sql),
            (research_run_id,),
        ).fetchone()
        if row is None or int(row[0]) != expected:
            raise IntegrityGateError(f"{table} QA row count does not match package")

    row = connection.execute(
        "select count(*) from public.match_reviews where id = %s and status = 'QA'",
        (inserted.match_id,),
    ).fetchone()
    if row is None or int(row[0]) != 1:
        raise IntegrityGateError("match review is not in QA state")

    required_document_keys = _object(payload, "match_review").get("source_document_keys", [])
    if any(str(key) not in document_ids for key in required_document_keys):
        raise IntegrityGateError("match review source document reference is unresolved")


def _finalize_publication(
    connection: Connection[Any],
    *,
    current: _CurrentReviews,
    inserted: _InsertedReviews,
    research_run_id: UUID,
    signal_ids: list[tuple[UUID, str]],
    revision_reason: str | None,
) -> None:
    revision_pairs: list[tuple[str, UUID, UUID]] = []
    if current.match_id is not None:
        connection.execute(
            "update public.match_reviews set status = 'REVISED', updated_at = now() where id = %s",
            (current.match_id,),
        )
        revision_pairs.append(("MATCH", current.match_id, inserted.match_id))

    for entity_type, table, old_map, new_map in (
        ("TEAM", "team_match_reviews", current.teams, inserted.teams),
        ("MANAGER", "manager_match_reviews", current.managers, inserted.managers),
        ("PLAYER", "player_match_reviews", current.players, inserted.players),
    ):
        for slug, old_id in old_map.items():
            new_id = new_map[slug]
            connection.execute(
                sql.SQL("update public.{table} set status = 'REVISED', updated_at = now() where id = %s").format(
                    table=sql.Identifier(table)
                ),
                (old_id,),
            )
            revision_pairs.append((entity_type, old_id, new_id))

    connection.execute(
        "update public.match_reviews set status = 'PUBLISHED', published_at = now(), updated_at = now() where id = %s",
        (inserted.match_id,),
    )
    for table, ids in (
        ("team_match_reviews", inserted.teams.values()),
        ("manager_match_reviews", inserted.managers.values()),
        ("player_match_reviews", inserted.players.values()),
    ):
        for review_id in ids:
            connection.execute(
                sql.SQL(
                    "update public.{table} set status = 'PUBLISHED', published_at = now(), updated_at = now() where id = %s"
                ).format(table=sql.Identifier(table)),
                (review_id,),
            )

    for signal_id, state in signal_ids:
        if state in _PUBLIC_SIGNAL_STATES:
            connection.execute(
                "update public.intelligence_signals set published_at = now() where id = %s",
                (signal_id,),
            )

    if revision_pairs:
        if revision_reason is None:
            raise RevisionConflictError("revision reason disappeared before finalization")
        for entity_type, old_id, new_id in revision_pairs:
            connection.execute(
                """
                insert into public.rating_revisions
                  (entity_type, old_review_id, new_review_id, reason, metadata)
                values (%s, %s, %s, %s, %s)
                """,
                (
                    entity_type,
                    old_id,
                    new_id,
                    revision_reason,
                    Jsonb({"publisher_version": PUBLISHER_VERSION}),
                ),
            )

    connection.execute(
        """
        update public.research_runs set
          status = 'PUBLISHED', qa_status = 'PASS', completed_at = now()
        where id = %s
        """,
        (research_run_id,),
    )


def _post_publish_integrity_gate(
    connection: Connection[Any],
    payload: JsonObject,
    *,
    match_id: UUID,
    research_run_id: UUID,
) -> None:
    expected_counts = {
        "match_reviews": 1,
        "team_match_reviews": len(_object_list(payload, "team_reviews")),
        "manager_match_reviews": len(_object_list(payload, "manager_reviews")),
        "player_match_reviews": len(_object_list(payload, "player_reviews")),
    }
    for table, expected in expected_counts.items():
        row = connection.execute(
            sql.SQL(
                "select count(*) from public.{table} where match_id = %s and status = 'PUBLISHED'"
            ).format(table=sql.Identifier(table)),
            (match_id,),
        ).fetchone()
        if row is None or int(row[0]) != expected:
            raise IntegrityGateError(
                f"post-publish current count for {table} is {None if row is None else row[0]}, expected {expected}"
            )
    row = connection.execute(
        "select status, qa_status, completed_at from public.research_runs where id = %s",
        (research_run_id,),
    ).fetchone()
    if row is None or row[0] != "PUBLISHED" or row[1] != "PASS" or row[2] is None:
        raise IntegrityGateError("research run did not reach PUBLISHED/PASS atomically")


def _normalize_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        raise IdentityConflictError("source document URLs must not contain credentials")
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    port = parsed.port
    if port is not None and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        host = f"{host}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, host, path, parsed.query, ""))


def _object(payload: JsonObject, key: str) -> JsonObject:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise MatchPublishError(f"validated package field {key!r} is not an object")
    return value


def _object_list(payload: JsonObject, key: str, *, required: bool = True) -> list[JsonObject]:
    value = payload.get(key)
    if value is None and not required:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise MatchPublishError(f"validated package field {key!r} is not a list of objects")
    return value


def _required_str(payload: JsonObject, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise MatchPublishError(f"validated package field {key!r} is not a string")
    return value


def _required_int(payload: JsonObject, key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise MatchPublishError(f"validated package field {key!r} is not an integer")
    return value


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_datetime(value: Any) -> datetime | None:
    return _parse_datetime(value) if isinstance(value, str) else None


def _optional_date(value: Any) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else None


def _as_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))
