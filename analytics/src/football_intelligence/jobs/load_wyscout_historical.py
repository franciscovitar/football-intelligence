"""Safely load certified Wyscout Open ENG_PL 2017/18 evidence into local PostgreSQL.

This is an intentionally local-only historical bootstrap. It reuses the
existing official Figshare acquisition/probe and the certified Wyscout Data
Mesh adapter, verifies both before opening PostgreSQL, then persists:

- the explicit legacy-canonical subset supported by ``football.*``;
- every certified Wyscout ``NormalizedObservation`` in the Data Mesh audit
  store so richer evidence is not discarded merely because the legacy
  canonical tables have fewer columns.

It does NOT calculate/publish Player V2 snapshots. The current product read
path selects the most recently calculated Player V2 context without an
explicit historical-season selector; calculating 2017/18 now could therefore
make historical data look like the active/latest product context. Publishing
historical analytics is a separate, deliberate product step.

Database safety: ``--database-url`` is required and must resolve to a local
PostgreSQL target through the repository's shared libpq-aware validator.
``DATABASE_URL`` is never read implicitly and remote writes are not supported
by this command.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg import Connection

from football_intelligence.data_mesh.adapters.wyscout_open import (
    SOURCE_CODE,
    parse_england_season,
)
from football_intelligence.data_mesh.entity_resolution import normalize_team_name
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.db.data_mesh_repository import DataMeshRepository
from football_intelligence.db.local_safety import validate_local_database_url
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.jobs.audit_wyscout_adapter import (
    WyscoutAdapterAuditError,
    build_report as build_adapter_report,
    load_adapter_inputs,
)
from football_intelligence.jobs.probe_wyscout_open import (
    DEFAULT_CACHE_DIR,
    WyscoutProbeError,
    run_probe,
)
from football_intelligence.normalization.models import (
    NormalizedFixtureBatch,
    PlayerAppearanceRecord,
    TeamRecord,
)
from football_intelligence.normalization.wyscout_historical import (
    COMPETITION_CODE,
    MINUTES_METHODOLOGY_VERSION,
    SEASON_LABEL,
    WyscoutHistoricalNormalizationError,
    normalize_england_2017_18,
)

_MINUTES_POLICY_VERSION = "wyscout-regular-90-ambiguous-missing-v1.0"


class WyscoutHistoricalLoadError(RuntimeError):
    """The historical bootstrap could not complete without weakening guarantees."""


@dataclass(frozen=True, slots=True)
class MinutesPolicyReport:
    red_card_appearances_excluded: int
    zero_duration_appearances_excluded: int
    version: str = _MINUTES_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class TeamLinkReport:
    already_linked: int
    reused_existing_canonical: int
    new_canonical_required: int


@dataclass(frozen=True, slots=True)
class ScopedDatabaseCounts:
    matches: int
    teams: int
    players: int
    player_appearances: int
    player_match_stats: int
    team_match_stats: int
    source_observations: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load certified Wyscout Open ENG_PL 2017/18 historical evidence into a "
            "LOCAL PostgreSQL database. Source probe + adapter audit run before any DB "
            "connection. No remote/production writes and no Player V2 publication."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--database-url",
        required=True,
        help=(
            "Explicit LOCAL PostgreSQL URL only. DATABASE_URL is never read implicitly; "
            "remote targets are rejected before connection."
        ),
    )
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database_url = validate_local_database_url(args.database_url)
    assert database_url is not None

    # Source + semantic validation is deliberately complete before a DB socket
    # is opened. A changed/corrupt upstream source can never partially load.
    try:
        probe_result = run_probe(cache_dir=args.cache_dir)
    except WyscoutProbeError as exc:
        raise SystemExit(f"WYSCOUT HISTORICAL LOAD: FAIL source probe - {exc}") from exc
    if not probe_result.report.counts_verified:
        raise SystemExit("WYSCOUT HISTORICAL LOAD: FAIL source published-count verification")

    try:
        matches_payload, events_payload, players_payload, teams_payload = load_adapter_inputs(
            args.cache_dir
        )
        observations = parse_england_season(
            matches_payload=matches_payload,
            events_payload=events_payload,
            players_payload=players_payload,
            teams_payload=teams_payload,
        )
    except WyscoutAdapterAuditError as exc:
        raise SystemExit(f"WYSCOUT HISTORICAL LOAD: FAIL adapter inputs - {exc}") from exc

    adapter_report = build_adapter_report(observations)
    if not adapter_report.all_passed:
        failed = [check.name for check in adapter_report.checks if not check.passed]
        raise SystemExit(
            "WYSCOUT HISTORICAL LOAD: FAIL certified adapter audit: " + ", ".join(failed)
        )

    try:
        normalization = normalize_england_2017_18(
            matches_payload=matches_payload,
            events_payload=events_payload,
            players_payload=players_payload,
            teams_payload=teams_payload,
        )
    except WyscoutHistoricalNormalizationError as exc:
        raise SystemExit(f"WYSCOUT HISTORICAL LOAD: FAIL canonical normalization - {exc}") from exc

    if normalization.unresolved_participating_player_ids:
        raise SystemExit(
            "WYSCOUT HISTORICAL LOAD: FAIL participating players missing from players.json: "
            f"{list(normalization.unresolved_participating_player_ids)}"
        )

    safe_batch, minutes_report = _apply_safe_minutes_policy(
        normalization.batch,
        observations=observations,
    )

    with connect(database_url) as connection:
        canonical_batch, team_link_report = _prepare_canonical_team_links(
            connection,
            safe_batch,
        )
        provider_repository = ProviderRepository(connection, provider_code=SOURCE_CODE)
        run_id = provider_repository.start_run(
            job_name="load_wyscout_historical",
            trigger_kind="manual",
            scope={
                "competition": COMPETITION_CODE,
                "season": SEASON_LABEL,
                "historical": True,
                "minutes_methodology_version": MINUTES_METHODOLOGY_VERSION,
                "minutes_policy_version": minutes_report.version,
            },
        )

        canonical_rows_written = provider_repository.persist_batch(
            competition_code=COMPETITION_CODE,
            batch=canonical_batch,
        )

        # Link every observation to this explicit ingestion run without
        # materializing a second ~400k-row list in memory.
        data_mesh_repository = DataMeshRepository(connection)
        source_rows_written = 0
        for observation in observations:
            source_rows_written += data_mesh_repository.persist_observations(
                [dataclasses.replace(observation, ingestion_run_id=run_id)]
            )

        counts = _scoped_database_counts(connection)
        _validate_scoped_invariants(counts)

        provider_repository.finish_run(
            run_id,
            status="succeeded",
            request_count=0,
            rows_written=canonical_rows_written + source_rows_written,
            metadata={
                "historical_only": True,
                "product_snapshots_published": False,
                "source_probe_counts_verified": True,
                "adapter_checks_passed": True,
                "adapter_observations": len(observations),
                "canonical_rows_written": canonical_rows_written,
                "source_observations_written": source_rows_written,
                "team_links": dataclasses.asdict(team_link_report),
                "minutes_policy": dataclasses.asdict(minutes_report),
            },
        )
        connection.commit()

    report = {
        "status": "PASS",
        "source": SOURCE_CODE,
        "scope": {
            "competition": COMPETITION_CODE,
            "season": SEASON_LABEL,
            "role": "historical_deep",
        },
        "source_probe": {
            "matches": probe_result.report.match_count,
            "events": probe_result.report.event_count,
            "roster_players": probe_result.report.roster_player_count,
            "counts_verified": probe_result.report.counts_verified,
        },
        "adapter": {
            "observations": adapter_report.total_observations,
            "safe_identities": adapter_report.safe_identity_count,
            "identities_with_observations": adapter_report.identities_with_observations,
            "all_checks_passed": adapter_report.all_passed,
        },
        "canonical": {
            "rows_written": canonical_rows_written,
            "team_links": dataclasses.asdict(team_link_report),
            "minutes_methodology_version": normalization.minutes_methodology_version,
            "minutes_policy": dataclasses.asdict(minutes_report),
        },
        "data_mesh": {
            "source_observations_written": source_rows_written,
            "reconciliation_decisions_written": 0,
            "note": (
                "Player cross-source reconciliation is intentionally not fabricated: "
                "the V2 player crosswalk contract requires validated shared-match evidence."
            ),
        },
        "database_scope_counts": dataclasses.asdict(counts),
        "product": {
            "player_v2_snapshots_published": False,
            "reason": (
                "Historical 2017/18 must not become the implicit latest Player V2 context. "
                "Historical product routing is a separate step."
            ),
        },
        "writes": {
            "database_target": "local-only",
            "production_written": False,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        "WYSCOUT HISTORICAL LOAD: PASS "
        f"({counts.matches} matches, {counts.teams} teams, {counts.players} players, "
        f"{counts.source_observations} source observations)"
    )
    print("PLAYER V2 PRODUCT PUBLICATION: NOT RUN (historical context safety)")
    print(f"REPORT: {args.report}")


def _red_card_player_match_keys(
    observations: list[NormalizedObservation],
) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for observation in observations:
        if (
            observation.entity_type != "player"
            or observation.metric_granularity != "player_match"
            or observation.metric_name != "red_cards"
        ):
            continue
        value = observation.value
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            continue
        match_id = observation.entity_identity_hints.get("match_external_id")
        player_id = observation.entity_identity_hints.get("player_external_id")
        if match_id and player_id:
            result.add((match_id, player_id))
    return result


def _apply_safe_minutes_policy(
    batch: NormalizedFixtureBatch,
    *,
    observations: list[NormalizedObservation],
) -> tuple[NormalizedFixtureBatch, MinutesPolicyReport]:
    """Keep standardized 90-minute exposure only where the source supports it.

    Wyscout gives substitution minutes but not a final-whistle timestamp.
    ``normalize_england_2017_18`` therefore derives standardized regular-90
    minutes. Two cases remain unsafe for per-90 exposure:

    - a player sent off without a substitution-out record: the exact red-card
      event time is not a certified participation primitive here, so we do
      not pretend they played to minute 90;
    - a stoppage-time substitute whose clamped standardized interval becomes
      zero minutes.

    Both retain their real appearance and performance stats, but ``minutes``
    becomes NULL so Player V2 will exclude the appearance from per-90 math
    rather than inventing exposure.
    """

    red_card_keys = _red_card_player_match_keys(observations)
    red_card_excluded = 0
    zero_duration_excluded = 0
    appearances: list[PlayerAppearanceRecord] = []

    for appearance in batch.appearances:
        key = (appearance.match_external_id, appearance.player_external_id)
        minutes = appearance.minutes
        if key in red_card_keys:
            if minutes is not None:
                red_card_excluded += 1
            minutes = None
        elif minutes is not None and minutes <= 0:
            zero_duration_excluded += 1
            minutes = None
        appearances.append(dataclasses.replace(appearance, minutes=minutes))

    return (
        dataclasses.replace(batch, appearances=tuple(appearances)),
        MinutesPolicyReport(
            red_card_appearances_excluded=red_card_excluded,
            zero_duration_appearances_excluded=zero_duration_excluded,
        ),
    )


def _prepare_canonical_team_links(
    connection: Connection[Any],
    batch: NormalizedFixtureBatch,
) -> tuple[NormalizedFixtureBatch, TeamLinkReport]:
    """Reuse canonical clubs deterministically before ProviderRepository writes.

    ``ProviderRepository`` correctly keys provider mappings by external id,
    but when a new provider id has never been seen it otherwise creates a new
    ``football.teams`` row. For a historical provider that would duplicate
    clubs already present from current sources (e.g. Arsenal). We bridge only
    through the repository's established deterministic team-name normalizer;
    ambiguous matches fail closed and no fuzzy/LLM matching is used.

    Reused teams are rewritten to their existing canonical display fields so
    the generic repository cannot overwrite current canonical names/metadata
    with historical Wyscout nulls/variants on the subsequent upsert.
    """

    provider_row = connection.execute(
        "select id from ingestion.providers where code = %s",
        (SOURCE_CODE,),
    ).fetchone()
    if provider_row is None:
        raise WyscoutHistoricalLoadError(f"provider seed not found: {SOURCE_CODE}")
    provider_id = int(provider_row[0])

    source_by_normalized: dict[str, TeamRecord] = {}
    for team in batch.teams:
        normalized = normalize_team_name(team.name)
        if not normalized:
            raise WyscoutHistoricalLoadError(
                f"team {team.external_id} has unusable name {team.name!r}"
            )
        previous = source_by_normalized.get(normalized)
        if previous is not None and previous.external_id != team.external_id:
            raise WyscoutHistoricalLoadError(
                "two Wyscout teams collapse to the same deterministic normalized name: "
                f"{previous.external_id}/{previous.name!r} and {team.external_id}/{team.name!r}"
            )
        source_by_normalized[normalized] = team

    existing_rows = connection.execute(
        "select id, name, short_name, country_code from football.teams"
    ).fetchall()
    existing_by_normalized: dict[str, list[tuple[int, str, str | None, str | None]]] = {}
    for row in existing_rows:
        normalized = normalize_team_name(str(row[1]))
        existing_by_normalized.setdefault(normalized, []).append(
            (
                int(row[0]),
                str(row[1]),
                None if row[2] is None else str(row[2]),
                None if row[3] is None else str(row[3]),
            )
        )

    canonical_records: list[TeamRecord] = []
    already_linked = 0
    reused = 0
    new_required = 0

    for team in batch.teams:
        mapped = connection.execute(
            """
            select t.id, t.name, t.short_name, t.country_code
            from football.team_provider_ids as provider_map
            join football.teams as t on t.id = provider_map.team_id
            where provider_map.provider_id = %s and provider_map.external_id = %s
            """,
            (provider_id, team.external_id),
        ).fetchone()
        if mapped is not None:
            canonical = _canonical_team_record(team.external_id, mapped)
            if normalize_team_name(canonical.name) != normalize_team_name(team.name):
                raise WyscoutHistoricalLoadError(
                    f"existing Wyscout mapping {team.external_id} points to canonical team "
                    f"{canonical.name!r}, incompatible with source name {team.name!r}"
                )
            canonical_records.append(canonical)
            already_linked += 1
            continue

        candidates = existing_by_normalized.get(normalize_team_name(team.name), [])
        if len(candidates) > 1:
            raise WyscoutHistoricalLoadError(
                f"ambiguous canonical team match for Wyscout {team.external_id} {team.name!r}: "
                f"{[(candidate[0], candidate[1]) for candidate in candidates]}"
            )
        if not candidates:
            canonical_records.append(team)
            new_required += 1
            continue

        candidate = candidates[0]
        existing_provider_mapping = connection.execute(
            """
            select external_id
            from football.team_provider_ids
            where provider_id = %s and team_id = %s
            """,
            (provider_id, candidate[0]),
        ).fetchone()
        if (
            existing_provider_mapping is not None
            and str(existing_provider_mapping[0]) != team.external_id
        ):
            raise WyscoutHistoricalLoadError(
                f"canonical team {candidate[0]} {candidate[1]!r} already has Wyscout id "
                f"{existing_provider_mapping[0]!r}; refusing second id {team.external_id!r}"
            )
        if existing_provider_mapping is None:
            connection.execute(
                """
                insert into football.team_provider_ids (provider_id, team_id, external_id)
                values (%s, %s, %s)
                """,
                (provider_id, candidate[0], team.external_id),
            )
        canonical_records.append(
            TeamRecord(
                external_id=team.external_id,
                name=candidate[1],
                short_name=candidate[2],
                country_code=candidate[3],
            )
        )
        reused += 1

    return (
        dataclasses.replace(batch, teams=tuple(canonical_records)),
        TeamLinkReport(
            already_linked=already_linked,
            reused_existing_canonical=reused,
            new_canonical_required=new_required,
        ),
    )


def _canonical_team_record(external_id: str, row: tuple[Any, ...]) -> TeamRecord:
    return TeamRecord(
        external_id=external_id,
        name=str(row[1]),
        short_name=None if row[2] is None else str(row[2]),
        country_code=None if row[3] is None else str(row[3]),
    )


def _scoped_database_counts(connection: Connection[Any]) -> ScopedDatabaseCounts:
    season_row = connection.execute(
        """
        select season.id
        from football.seasons as season
        join football.competitions as competition on competition.id = season.competition_id
        where competition.code = %s and season.label = %s
        """,
        (COMPETITION_CODE, SEASON_LABEL),
    ).fetchone()
    if season_row is None:
        raise WyscoutHistoricalLoadError("persisted historical season could not be found")
    season_id = int(season_row[0])

    matches = _scalar(
        connection,
        "select count(*) from football.matches where season_id = %s",
        (season_id,),
    )
    teams = _scalar(
        connection,
        """
        select count(distinct team_id)
        from (
            select home_team_id as team_id from football.matches where season_id = %s
            union all
            select away_team_id as team_id from football.matches where season_id = %s
        ) as scope_teams
        """,
        (season_id, season_id),
    )
    players = _scalar(
        connection,
        """
        select count(distinct appearance.player_id)
        from football.player_appearances as appearance
        join football.matches as match on match.id = appearance.match_id
        where match.season_id = %s
        """,
        (season_id,),
    )
    player_appearances = _scalar(
        connection,
        """
        select count(*)
        from football.player_appearances as appearance
        join football.matches as match on match.id = appearance.match_id
        where match.season_id = %s
        """,
        (season_id,),
    )
    player_match_stats = _scalar(
        connection,
        """
        select count(*)
        from football.player_match_stats as stats
        join football.matches as match on match.id = stats.match_id
        where match.season_id = %s
        """,
        (season_id,),
    )
    team_match_stats = _scalar(
        connection,
        """
        select count(*)
        from football.team_match_stats as stats
        join football.matches as match on match.id = stats.match_id
        where match.season_id = %s
        """,
        (season_id,),
    )
    source_observations = _scalar(
        connection,
        """
        select count(*)
        from ingestion.source_observations as observation
        join ingestion.providers as provider on provider.id = observation.provider_id
        where provider.code = %s
          and observation.entity_identity_hints ->> 'season_label' = %s
        """,
        (SOURCE_CODE, SEASON_LABEL),
    )

    return ScopedDatabaseCounts(
        matches=matches,
        teams=teams,
        players=players,
        player_appearances=player_appearances,
        player_match_stats=player_match_stats,
        team_match_stats=team_match_stats,
        source_observations=source_observations,
    )


def _scalar(connection: Connection[Any], query: str, params: tuple[Any, ...]) -> int:
    row = connection.execute(query, params).fetchone()
    if row is None:
        raise WyscoutHistoricalLoadError("count query returned no row")
    return int(row[0])


def _validate_scoped_invariants(counts: ScopedDatabaseCounts) -> None:
    if counts.matches != 380:
        raise WyscoutHistoricalLoadError(
            f"expected 380 ENG_PL 2017/18 matches after load, got {counts.matches}"
        )
    if counts.teams != 20:
        raise WyscoutHistoricalLoadError(
            f"expected 20 ENG_PL 2017/18 teams after load, got {counts.teams}"
        )
    if counts.player_appearances <= 0 or counts.player_match_stats <= 0:
        raise WyscoutHistoricalLoadError("historical player rows were not persisted")
    if counts.player_appearances != counts.player_match_stats:
        raise WyscoutHistoricalLoadError(
            "every persisted participating appearance must have one player_match_stats row: "
            f"appearances={counts.player_appearances}, stats={counts.player_match_stats}"
        )
    if counts.team_match_stats != 760:
        raise WyscoutHistoricalLoadError(
            f"expected 760 team-match stat rows after load, got {counts.team_match_stats}"
        )
    if counts.source_observations <= 0:
        raise WyscoutHistoricalLoadError("certified Wyscout Data Mesh observations were not persisted")


if __name__ == "__main__":
    main()
