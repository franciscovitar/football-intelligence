"""Atomically promote one certified Wyscout Open 2017/18 Player V2 scope.

The command remains deliberately narrow: one explicitly selected historical
core-league scope is verified from the official Wyscout Open bytes, persisted
into canonical/Data Mesh storage, and calculated into the explicit product
scope ``competition:<code>:2017/18``.

Source verification finishes before PostgreSQL is opened. Remote writes use
the repository's shared quadruple-confirmed production guard. Canonical data,
Data Mesh observations, and Player V1/V2 snapshots are committed in one
transaction only after per-league certified invariants are observed again.
Current/day-to-day provider work is out of scope.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.scope import ScopeMismatchError
from football_intelligence.data_mesh.adapters.wyscout_open import (
    SOURCE_CODE,
    WyscoutObservationConflictError,
    parse_england_season,
)
from football_intelligence.db.data_mesh_repository import DataMeshRepository
from football_intelligence.db.player_analytics_repository import PlayerAnalyticsRepository
from football_intelligence.db.production_write_guard import DatabaseTarget, resolve_database_target
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.db.target_parsing import parse_database_target
from football_intelligence.jobs.calculate_player_analytics import _persist_versioned_snapshots
from football_intelligence.jobs.historical_player_promotion_spec import (
    HistoricalPlayerPromotionSpec,
    SEASON_LABEL,
    historical_player_promotion_spec,
    supported_promotion_competitions,
)
from football_intelligence.jobs.load_wyscout_historical import (
    _apply_safe_minutes_policy,
    _prepare_canonical_team_links,
    _scoped_database_counts,
    _validate_scoped_invariants,
)
from football_intelligence.jobs.preflight_production_state import _verify_connected_target_matches
from football_intelligence.jobs.probe_wyscout_open import (
    DEFAULT_CACHE_DIR,
    WyscoutProbeError,
    run_probe,
)
from football_intelligence.jobs.wyscout_historical_scope import (
    WyscoutHistoricalScopeError,
    load_scope_inputs,
    scope_config,
    validate_adapter_observations,
    validate_source_scope,
)
from football_intelligence.normalization.wyscout_historical import (
    MINUTES_METHODOLOGY_VERSION,
    WyscoutHistoricalNormalizationError,
    normalize_wyscout_historical_scope,
)
from football_intelligence.player_analytics.engine import calculate_player_analytics
from football_intelligence.player_analytics.engine_v2 import (
    MODEL_VERSION as PLAYER_V2_MODEL_VERSION,
)
from football_intelligence.player_analytics.engine_v2 import calculate_player_analytics_v2_result

_DEFAULT_SPEC = historical_player_promotion_spec("ENG_PL")

# Backward-compatible aliases for the already-published ENG_PL promotion
# contract. New code should use HistoricalPlayerPromotionSpec directly.
COMPETITION_CODE = _DEFAULT_SPEC.competition_code
SCOPE_KEY = _DEFAULT_SPEC.scope_key
EXPECTED_MATCHES = _DEFAULT_SPEC.matches
EXPECTED_TEAMS = _DEFAULT_SPEC.teams
EXPECTED_PLAYERS = _DEFAULT_SPEC.players
EXPECTED_PLAYER_APPEARANCES = _DEFAULT_SPEC.player_appearances
EXPECTED_PLAYER_MATCH_STATS = _DEFAULT_SPEC.player_match_stats
EXPECTED_TEAM_MATCH_STATS = _DEFAULT_SPEC.team_match_stats
EXPECTED_SOURCE_OBSERVATIONS = _DEFAULT_SPEC.source_observations
EXPECTED_SCORE_SNAPSHOTS = _DEFAULT_SPEC.score_snapshots
EXPECTED_FEATURE_SNAPSHOTS = _DEFAULT_SPEC.feature_snapshots
EXPECTED_SEASON_PLAYERS = _DEFAULT_SPEC.season_players
EXPECTED_SEASON_PLAYERS_450_MIN = _DEFAULT_SPEC.season_players_450_min
EXPECTED_PERFORMANCE_READY = _DEFAULT_SPEC.performance_ready
EXPECTED_EVIDENCE_STATES = _DEFAULT_SPEC.evidence_state_counts


class HistoricalPlayerPromotionError(RuntimeError):
    """Promotion cannot continue without weakening a certified invariant."""


@dataclass(frozen=True, slots=True)
class PrewriteState:
    season_exists: bool
    matches: int
    teams: int
    players: int
    player_appearances: int
    player_match_stats: int
    team_match_stats: int
    source_observations: int
    player_v2_rows: int
    player_v2_feature_rows: int = 0

    @property
    def is_fresh(self) -> bool:
        return not self.season_exists and all(
            value == 0
            for value in (
                self.matches,
                self.teams,
                self.players,
                self.player_appearances,
                self.player_match_stats,
                self.team_match_stats,
                self.source_observations,
                self.player_v2_rows,
                self.player_v2_feature_rows,
            )
        )

    @property
    def is_certified_complete(self) -> bool:
        """Backward-compatible ENG_PL completeness property."""

        return self.is_certified_complete_for(_DEFAULT_SPEC)

    def is_certified_complete_for(self, spec: HistoricalPlayerPromotionSpec) -> bool:
        return (
            self.season_exists
            and self.matches == spec.matches
            and self.teams == spec.teams
            and self.players == spec.players
            and self.player_appearances == spec.player_appearances
            and self.player_match_stats == spec.player_match_stats
            and self.team_match_stats == spec.team_match_stats
            and self.source_observations == spec.source_observations
            and self.player_v2_rows == spec.score_snapshots
            and self.player_v2_feature_rows == spec.feature_snapshots
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Promote one certified Wyscout Open 2017/18 core-league scope + Player V2 "
            "atomically. Remote targets require the full production-write confirmation contract."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--competition",
        choices=supported_promotion_competitions(),
        default=COMPETITION_CODE,
        help="Historical Wyscout competition to promote; defaults to ENG_PL.",
    )
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--allow-remote-write", action="store_true")
    parser.add_argument("--confirm-target", default=None)
    parser.add_argument("--production-write-confirmation", default=None)
    parser.add_argument("--confirm-database-target", default=None)
    return parser


def resolve_target(args: argparse.Namespace) -> DatabaseTarget:
    target = resolve_database_target(
        args.database_url,
        allow_remote_write=args.allow_remote_write,
        confirm_target=args.confirm_target,
        production_write_confirmation=args.production_write_confirmation,
        confirm_database_target=args.confirm_database_target,
    )
    assert target is not None
    return target


def main() -> None:
    args = build_parser().parse_args()
    target = resolve_target(args)
    spec = historical_player_promotion_spec(args.competition)
    config = scope_config(spec.competition_code)
    probe_result, source_validation, adapter_report, observations, normalization = _prepare_source(
        args.cache_dir,
        spec=spec,
    )
    safe_batch, minutes_report = _apply_safe_minutes_policy(
        normalization.batch,
        observations=observations,
    )

    with connect(target.database_url) as connection:
        _verify_connected_target_matches(connection, parse_database_target(target.database_url))
        prewrite = inspect_prewrite_state(
            connection,
            spec=spec,
            provider_competition_id=config.scope.provider_competition_id,
        )
        validate_prewrite_state(prewrite, spec=spec)

        canonical_batch, team_link_report = _prepare_canonical_team_links(connection, safe_batch)
        provider_repository = ProviderRepository(connection, provider_code=SOURCE_CODE)
        run_id = provider_repository.start_run(
            job_name="promote_historical_player_v2",
            trigger_kind="manual",
            scope={
                "competition": spec.competition_code,
                "season": SEASON_LABEL,
                "scope_key": spec.scope_key,
                "historical": True,
                "production_promotion": not target.is_local,
                "minutes_methodology_version": MINUTES_METHODOLOGY_VERSION,
                "minutes_policy_version": minutes_report.version,
            },
        )

        canonical_rows_written = provider_repository.persist_batch(
            competition_code=spec.competition_code,
            batch=canonical_batch,
        )
        source_rows_written = _persist_data_mesh(connection, observations, run_id)

        canonical_counts = _scoped_database_counts(
            connection,
            competition_code=spec.competition_code,
            season_label=SEASON_LABEL,
            provider_competition_id=config.scope.provider_competition_id,
        )
        _validate_scoped_invariants(
            canonical_counts,
            expected_matches=spec.matches,
            expected_teams=spec.teams,
            expected_players=spec.players,
            expected_player_appearances=spec.player_appearances,
            expected_player_match_stats=spec.player_match_stats,
            expected_team_match_stats=spec.team_match_stats,
            expected_source_observations=spec.source_observations,
        )
        _validate_exact_canonical_counts(canonical_counts, spec=spec)

        analytics_repository = PlayerAnalyticsRepository(connection)
        player_observations = analytics_repository.load_observations(
            season_label=SEASON_LABEL,
            competition_codes=(spec.competition_code,),
        )
        if not player_observations:
            raise HistoricalPlayerPromotionError("Player V2 input observations are empty")

        v1_result = calculate_player_analytics(player_observations, scope_key=spec.scope_key)
        v2_result = calculate_player_analytics_v2_result(
            player_observations,
            scope_key=spec.scope_key,
        )
        _persist_versioned_snapshots(
            analytics_repository,
            v1_result=v1_result,
            v2_result=v2_result,
            scope_key=spec.scope_key,
        )
        snapshot_counts = analytics_repository.snapshot_counts(
            scope_key=spec.scope_key,
            model_version=PLAYER_V2_MODEL_VERSION,
        )
        product_counts = inspect_product_counts(connection, spec=spec)
        validate_player_v2_invariants(
            score_count=len(v2_result.scores),
            feature_count=len(v2_result.features),
            evidence_states=Counter(score.evidence_state for score in v2_result.scores),
            snapshot_counts=snapshot_counts,
            product_counts=product_counts,
            spec=spec,
        )

        provider_repository.finish_run(
            run_id,
            status="succeeded",
            request_count=0,
            rows_written=(
                canonical_rows_written
                + source_rows_written
                + snapshot_counts["scores"]
                + snapshot_counts["features"]
            ),
            metadata={
                "historical_only": True,
                "production_promotion": not target.is_local,
                "scope_key": spec.scope_key,
                "source_scope_counts_verified": source_validation.passed,
                "adapter_checks_passed": adapter_report.passed,
                "adapter_observations": len(observations),
                "canonical_rows_written": canonical_rows_written,
                "source_observations_written": source_rows_written,
                "team_links": dataclasses.asdict(team_link_report),
                "minutes_policy": dataclasses.asdict(minutes_report),
                "player_v2": product_counts,
            },
        )
        connection.commit()

    report = {
        "status": "PASS",
        "target": target.safe_description,
        "production_written": not target.is_local,
        "competition": spec.competition_code,
        "season": SEASON_LABEL,
        "scope_key": spec.scope_key,
        "source": {
            "provider": SOURCE_CODE,
            "matches": source_validation.match_count,
            "events": source_validation.event_count,
            "roster_players": source_validation.roster_player_count,
            "teams": source_validation.team_count,
            "provider_competition_id": source_validation.provider_competition_id,
            "provider_season_id": source_validation.provider_season_id,
            "official_archive_checksum_probe": probe_result.report.counts_verified,
            "adapter_observations": adapter_report.total_observations,
        },
        "prewrite_state": dataclasses.asdict(prewrite),
        "canonical": dataclasses.asdict(canonical_counts),
        "player_v2": {
            "score_snapshots": len(v2_result.scores),
            "feature_snapshots": len(v2_result.features),
            "evidence_states": dict(Counter(score.evidence_state for score in v2_result.scores)),
            **product_counts,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "HISTORICAL PLAYER PROMOTION: PASS "
        f"({spec.competition_code} {spec.matches} matches, {spec.season_players} player profiles, "
        f"{spec.feature_snapshots} V2 features)"
    )
    print(f"TARGET: {target.safe_description}")
    print(f"PRODUCTION WRITTEN: {not target.is_local}")
    print(f"REPORT: {args.report}")


def _prepare_source(
    cache_dir: Path,
    *,
    spec: HistoricalPlayerPromotionSpec = _DEFAULT_SPEC,
) -> tuple[Any, Any, Any, list[Any], Any]:
    try:
        probe_result = run_probe(cache_dir=cache_dir)
    except WyscoutProbeError as exc:
        raise SystemExit(f"HISTORICAL PLAYER PROMOTION: FAIL source probe - {exc}") from exc
    if not probe_result.report.counts_verified:
        raise SystemExit("HISTORICAL PLAYER PROMOTION: FAIL official archive acquisition probe")

    config = scope_config(spec.competition_code)
    try:
        matches_payload, events_payload, players_payload, teams_payload = load_scope_inputs(
            cache_dir,
            config=config,
        )
    except (WyscoutHistoricalScopeError, OSError, ValueError) as exc:
        raise SystemExit(f"HISTORICAL PLAYER PROMOTION: FAIL scope inputs - {exc}") from exc

    source_validation = validate_source_scope(
        matches_payload=matches_payload,
        events_payload=events_payload,
        config=config,
    )
    if not source_validation.passed:
        raise SystemExit(
            "HISTORICAL PLAYER PROMOTION: FAIL source scope validation: "
            + "; ".join(source_validation.failures)
        )

    try:
        observations = parse_england_season(
            matches_payload=matches_payload,
            events_payload=events_payload,
            players_payload=players_payload,
            teams_payload=teams_payload,
            scope=config.scope,
        )
    except (ScopeMismatchError, WyscoutObservationConflictError) as exc:
        raise SystemExit(f"HISTORICAL PLAYER PROMOTION: FAIL adapter - {exc}") from exc

    adapter_report = validate_adapter_observations(
        observations=observations,
        matches_payload=matches_payload,
        config=config,
    )
    if not adapter_report.passed:
        raise SystemExit(
            "HISTORICAL PLAYER PROMOTION: FAIL adapter validation: "
            + "; ".join(adapter_report.failures)
        )

    try:
        normalization = normalize_wyscout_historical_scope(
            matches_payload=matches_payload,
            events_payload=events_payload,
            players_payload=players_payload,
            teams_payload=teams_payload,
            scope=config.scope,
            expected_match_count=spec.matches,
        )
    except WyscoutHistoricalNormalizationError as exc:
        raise SystemExit(f"HISTORICAL PLAYER PROMOTION: FAIL normalization - {exc}") from exc
    if normalization.unresolved_participating_player_ids:
        raise SystemExit(
            "HISTORICAL PLAYER PROMOTION: FAIL participating players missing from source: "
            f"{list(normalization.unresolved_participating_player_ids)}"
        )
    return probe_result, source_validation, adapter_report, observations, normalization


def _persist_data_mesh(connection: Any, observations: list[Any], run_id: int) -> int:
    """Persist the large Wyscout audit set in bounded psycopg pipeline batches."""

    repository = DataMeshRepository(connection)
    written = 0
    batch_size = 1_000
    for start in range(0, len(observations), batch_size):
        with connection.pipeline():
            for observation in observations[start : start + batch_size]:
                written += repository.persist_observations(
                    [dataclasses.replace(observation, ingestion_run_id=run_id)]
                )
    return written


def inspect_prewrite_state(
    connection: Any,
    *,
    spec: HistoricalPlayerPromotionSpec = _DEFAULT_SPEC,
    provider_competition_id: int | None = None,
) -> PrewriteState:
    if provider_competition_id is None:
        provider_competition_id = scope_config(spec.competition_code).scope.provider_competition_id

    competition = connection.execute(
        "select id from football.competitions where code=%s",
        (spec.competition_code,),
    ).fetchone()
    if competition is None:
        raise HistoricalPlayerPromotionError(
            f"competition seed missing: {spec.competition_code}"
        )
    season = connection.execute(
        "select id from football.seasons where competition_id=%s and label=%s",
        (int(competition[0]), SEASON_LABEL),
    ).fetchone()
    season_id = int(season[0]) if season is not None else None

    if season_id is None:
        matches = teams = players = appearances = player_stats = team_stats = 0
    else:
        matches = _scalar(
            connection,
            "select count(*) from football.matches where season_id=%s",
            (season_id,),
        )
        teams = _scalar(
            connection,
            """select count(distinct team_id) from (
                   select home_team_id team_id from football.matches where season_id=%s
                   union all
                   select away_team_id team_id from football.matches where season_id=%s
               ) scoped""",
            (season_id, season_id),
        )
        players = _scalar(
            connection,
            """select count(distinct pa.player_id) from football.player_appearances pa
               join football.matches m on m.id=pa.match_id where m.season_id=%s""",
            (season_id,),
        )
        appearances = _scalar(
            connection,
            """select count(*) from football.player_appearances pa
               join football.matches m on m.id=pa.match_id where m.season_id=%s""",
            (season_id,),
        )
        player_stats = _scalar(
            connection,
            """select count(*) from football.player_match_stats pms
               join football.matches m on m.id=pms.match_id where m.season_id=%s""",
            (season_id,),
        )
        team_stats = _scalar(
            connection,
            """select count(*) from football.team_match_stats tms
               join football.matches m on m.id=tms.match_id where m.season_id=%s""",
            (season_id,),
        )

    source_observations = _scalar(
        connection,
        """select count(*) from ingestion.source_observations o
           join ingestion.providers p on p.id=o.provider_id
           where p.code=%s
             and o.entity_identity_hints ->> 'season_label'=%s
             and o.entity_identity_hints ->> 'competition_external_id'=%s""",
        (SOURCE_CODE, SEASON_LABEL, str(provider_competition_id)),
    )
    player_v2_rows = _scalar(
        connection,
        """select count(*) from analytics.player_score_snapshots
           where scope_key=%s and model_version=%s""",
        (spec.scope_key, PLAYER_V2_MODEL_VERSION),
    )
    player_v2_feature_rows = _scalar(
        connection,
        """select count(*) from analytics.player_feature_snapshots
           where scope_key=%s and model_version=%s""",
        (spec.scope_key, PLAYER_V2_MODEL_VERSION),
    )
    return PrewriteState(
        season_exists=season is not None,
        matches=matches,
        teams=teams,
        players=players,
        player_appearances=appearances,
        player_match_stats=player_stats,
        team_match_stats=team_stats,
        source_observations=source_observations,
        player_v2_rows=player_v2_rows,
        player_v2_feature_rows=player_v2_feature_rows,
    )


def validate_prewrite_state(
    state: PrewriteState,
    *,
    spec: HistoricalPlayerPromotionSpec = _DEFAULT_SPEC,
) -> None:
    if state.is_fresh or state.is_certified_complete_for(spec):
        return
    raise HistoricalPlayerPromotionError(
        f"historical production scope {spec.scope_key} is neither fresh nor certified complete; "
        f"refusing unexpected partial state: {state}"
    )


def _validate_exact_canonical_counts(
    counts: Any,
    *,
    spec: HistoricalPlayerPromotionSpec = _DEFAULT_SPEC,
) -> None:
    expected = {
        "matches": spec.matches,
        "teams": spec.teams,
        "players": spec.players,
        "player_appearances": spec.player_appearances,
        "player_match_stats": spec.player_match_stats,
        "team_match_stats": spec.team_match_stats,
        "source_observations": spec.source_observations,
    }
    actual = dataclasses.asdict(counts)
    if actual != expected:
        raise HistoricalPlayerPromotionError(
            f"unexpected certified canonical counts for {spec.scope_key}: {actual} != {expected}"
        )


def inspect_product_counts(
    connection: Any,
    *,
    spec: HistoricalPlayerPromotionSpec = _DEFAULT_SPEC,
) -> dict[str, int]:
    params = (spec.scope_key, PLAYER_V2_MODEL_VERSION)
    return {
        "season_players": _scalar(
            connection,
            """select count(distinct player_id) from analytics.product_player_detail_v2
               where scope_key=%s and model_version=%s and window_key='season'""",
            params,
        ),
        "season_players_450_min": _scalar(
            connection,
            """select count(distinct player_id) from analytics.product_player_detail_v2
               where scope_key=%s and model_version=%s and window_key='season' and minutes>=450""",
            params,
        ),
        "performance_ready": _scalar(
            connection,
            """select count(*) from analytics.product_player_detail_v2 s
               cross join lateral jsonb_each(s.dimension_evidence) e
               where s.scope_key=%s and s.model_version=%s and s.window_key='season'
                 and e.key='performance' and e.value->>'evidence_state'='ready'
                 and e.value->>'score' is not null""",
            params,
        ),
        "ranking_candidates": _scalar(
            connection,
            """select count(*) from analytics.product_player_ranking_candidates_v2
               where scope_key=%s and model_version=%s""",
            params,
        ),
        "overall_scores": _scalar(
            connection,
            """select count(*) from analytics.product_player_detail_v2
               where scope_key=%s and model_version=%s and overall_score is not null""",
            params,
        ),
    }


def validate_player_v2_invariants(
    *,
    score_count: int,
    feature_count: int,
    evidence_states: Counter[str],
    snapshot_counts: dict[str, int],
    product_counts: dict[str, int],
    spec: HistoricalPlayerPromotionSpec = _DEFAULT_SPEC,
) -> None:
    if score_count != spec.score_snapshots or feature_count != spec.feature_snapshots:
        raise HistoricalPlayerPromotionError(
            f"unexpected Player V2 runtime counts for {spec.scope_key}: "
            f"scores={score_count}, features={feature_count}"
        )
    if snapshot_counts != {
        "scores": spec.score_snapshots,
        "features": spec.feature_snapshots,
    }:
        raise HistoricalPlayerPromotionError(
            f"unexpected persisted snapshots for {spec.scope_key}: {snapshot_counts}"
        )
    if dict(evidence_states) != spec.evidence_state_counts:
        raise HistoricalPlayerPromotionError(
            f"unexpected Player V2 evidence states for {spec.scope_key}: {dict(evidence_states)}"
        )
    expected_product = {
        "season_players": spec.season_players,
        "season_players_450_min": spec.season_players_450_min,
        "performance_ready": spec.performance_ready,
        "ranking_candidates": 0,
        "overall_scores": 0,
    }
    if product_counts != expected_product:
        raise HistoricalPlayerPromotionError(
            f"unexpected Player V2 product counts for {spec.scope_key}: "
            f"{product_counts} != {expected_product}"
        )


def _scalar(connection: Any, query: str, params: tuple[Any, ...] = ()) -> int:
    row = connection.execute(query, params).fetchone()
    if row is None:
        raise HistoricalPlayerPromotionError("count query returned no row")
    return int(row[0])


if __name__ == "__main__":
    main()
