"""Promote certified Wyscout ENG_PL 2017/18 evidence and Player V2 atomically.

This is the explicit production-capable counterpart to the local-only historical
loader. It intentionally has one narrow scope: Wyscout Open Premier League
2017/18 -> canonical/Data Mesh -> explicit Player V2 scope
``competition:ENG_PL:2017/18``.

The source probe, adapter audit and normalization complete before PostgreSQL is
opened. A remote target is accepted only through the repository's shared
quadruple-confirmed production-write guard. Canonical evidence and Player V2
snapshots are then persisted in one database transaction and committed only
after the already-certified runtime invariants are observed again.

No current/day-to-day provider work is performed here.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.wyscout_open import (
    SOURCE_CODE,
    parse_england_season,
)
from football_intelligence.db.data_mesh_repository import DataMeshRepository
from football_intelligence.db.player_analytics_repository import PlayerAnalyticsRepository
from football_intelligence.db.production_write_guard import (
    DatabaseTarget,
    resolve_database_target,
)
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.db.target_parsing import parse_database_target
from football_intelligence.jobs.audit_wyscout_adapter import (
    WyscoutAdapterAuditError,
    build_report as build_adapter_report,
    load_adapter_inputs,
)
from football_intelligence.jobs.calculate_player_analytics import (
    _persist_versioned_snapshots,
)
from football_intelligence.jobs.load_wyscout_historical import (
    _apply_safe_minutes_policy,
    _prepare_canonical_team_links,
    _scoped_database_counts,
    _validate_scoped_invariants,
)
from football_intelligence.jobs.preflight_production_state import (
    _verify_connected_target_matches,
)
from football_intelligence.jobs.probe_wyscout_open import (
    DEFAULT_CACHE_DIR,
    WyscoutProbeError,
    run_probe,
)
from football_intelligence.normalization.wyscout_historical import (
    COMPETITION_CODE,
    MINUTES_METHODOLOGY_VERSION,
    SEASON_LABEL,
    WyscoutHistoricalNormalizationError,
    normalize_england_2017_18,
)
from football_intelligence.player_analytics.engine import calculate_player_analytics
from football_intelligence.player_analytics.engine_v2 import (
    MODEL_VERSION as PLAYER_V2_MODEL_VERSION,
)
from football_intelligence.player_analytics.engine_v2 import (
    calculate_player_analytics_v2_result,
)

SCOPE_KEY = "competition:ENG_PL:2017/18"
EXPECTED_MATCHES = 380
EXPECTED_TEAMS = 20
EXPECTED_PLAYERS = 515
EXPECTED_PLAYER_APPEARANCES = 10_443
EXPECTED_PLAYER_MATCH_STATS = 10_443
EXPECTED_TEAM_MATCH_STATS = 760
EXPECTED_SOURCE_OBSERVATIONS = 412_609
EXPECTED_SCORE_SNAPSHOTS = 2_048
EXPECTED_FEATURE_SNAPSHOTS = 26_841
EXPECTED_SEASON_PLAYERS = 512
EXPECTED_SEASON_PLAYERS_450_MIN = 385
EXPECTED_PERFORMANCE_READY = 385
EXPECTED_RANKING_CANDIDATES = 0
EXPECTED_OVERALL_SCORES = 0
EXPECTED_EVIDENCE_STATES = {
    "insufficient_data": 1_754,
    "partial": 294,
}


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
            )
        )

    @property
    def is_certified_complete(self) -> bool:
        return (
            self.season_exists
            and self.matches == EXPECTED_MATCHES
            and self.teams == EXPECTED_TEAMS
            and self.players == EXPECTED_PLAYERS
            and self.player_appearances == EXPECTED_PLAYER_APPEARANCES
            and self.player_match_stats == EXPECTED_PLAYER_MATCH_STATS
            and self.team_match_stats == EXPECTED_TEAM_MATCH_STATS
            and self.source_observations == EXPECTED_SOURCE_OBSERVATIONS
            and self.player_v2_rows == EXPECTED_SCORE_SNAPSHOTS
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Atomically promote certified Wyscout ENG_PL 2017/18 evidence and explicit "
            "Player V2 snapshots to PostgreSQL. Remote targets require the full shared "
            "production-write confirmation contract."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
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

    try:
        probe_result = run_probe(cache_dir=args.cache_dir)
    except WyscoutProbeError as exc:
        raise SystemExit(f"HISTORICAL PLAYER PROMOTION: FAIL source probe - {exc}") from exc
    if not probe_result.report.counts_verified:
        raise SystemExit("HISTORICAL PLAYER PROMOTION: FAIL source published-count verification")

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
        raise SystemExit(f"HISTORICAL PLAYER PROMOTION: FAIL adapter inputs - {exc}") from exc

    adapter_report = build_adapter_report(observations)
    if not adapter_report.all_passed:
        failed = [check.name for check in adapter_report.checks if not check.passed]
        raise SystemExit(
            "HISTORICAL PLAYER PROMOTION: FAIL certified adapter audit: " + ", ".join(failed)
        )

    try:
        normalization = normalize_england_2017_18(
            matches_payload=matches_payload,
            events_payload=events_payload,
            players_payload=players_payload,
            teams_payload=teams_payload,
        )
    except WyscoutHistoricalNormalizationError as exc:
        raise SystemExit(f"HISTORICAL PLAYER PROMOTION: FAIL normalization - {exc}") from exc

    if normalization.unresolved_participating_player_ids:
        raise SystemExit(
            "HISTORICAL PLAYER PROMOTION: FAIL participating players missing from source: "
            f"{list(normalization.unresolved_participating_player_ids)}"
        )

    safe_batch, minutes_report = _apply_safe_minutes_policy(
        normalization.batch,
        observations=observations,
    )

    with connect(target.database_url) as connection:
        _verify_connected_target_matches(connection, parse_database_target(target.database_url))
        prewrite = inspect_prewrite_state(connection)
        validate_prewrite_state(prewrite)

        canonical_batch, team_link_report = _prepare_canonical_team_links(
            connection,
            safe_batch,
        )
        provider_repository = ProviderRepository(connection, provider_code=SOURCE_CODE)
        run_id = provider_repository.start_run(
            job_name="promote_historical_player_v2",
            trigger_kind="manual",
            scope={
                "competition": COMPETITION_CODE,
                "season": SEASON_LABEL,
                "scope_key": SCOPE_KEY,
                "historical": True,
                "production_promotion": not target.is_local,
                "minutes_methodology_version": MINUTES_METHODOLOGY_VERSION,
                "minutes_policy_version": minutes_report.version,
            },
        )

        canonical_rows_written = provider_repository.persist_batch(
            competition_code=COMPETITION_CODE,
            batch=canonical_batch,
        )
        data_mesh_repository = DataMeshRepository(connection)
        source_rows_written = 0
        for observation in observations:
            source_rows_written += data_mesh_repository.persist_observations(
                [dataclasses.replace(observation, ingestion_run_id=run_id)]
            )

        canonical_counts = _scoped_database_counts(connection)
        _validate_scoped_invariants(canonical_counts)
        if canonical_counts.players != EXPECTED_PLAYERS:
            raise HistoricalPlayerPromotionError(
                f"expected {EXPECTED_PLAYERS} participating players, got "
                f"{canonical_counts.players}"
            )
        if canonical_counts.player_appearances != EXPECTED_PLAYER_APPEARANCES:
            raise HistoricalPlayerPromotionError(
                f"expected {EXPECTED_PLAYER_APPEARANCES} appearances, got "
                f"{canonical_counts.player_appearances}"
            )
        if canonical_counts.source_observations != EXPECTED_SOURCE_OBSERVATIONS:
            raise HistoricalPlayerPromotionError(
                f"expected {EXPECTED_SOURCE_OBSERVATIONS} Wyscout observations, got "
                f"{canonical_counts.source_observations}"
            )

        analytics_repository = PlayerAnalyticsRepository(connection)
        player_observations = analytics_repository.load_observations(
            season_label=SEASON_LABEL,
            competition_codes=(COMPETITION_CODE,),
        )
        if not player_observations:
            raise HistoricalPlayerPromotionError("Player V2 input observations are empty")

        v1_result = calculate_player_analytics(player_observations, scope_key=SCOPE_KEY)
        v2_result = calculate_player_analytics_v2_result(
            player_observations,
            scope_key=SCOPE_KEY,
        )
        _persist_versioned_snapshots(
            analytics_repository,
            v1_result=v1_result,
            v2_result=v2_result,
            scope_key=SCOPE_KEY,
        )
        snapshot_counts = analytics_repository.snapshot_counts(
            scope_key=SCOPE_KEY,
            model_version=PLAYER_V2_MODEL_VERSION,
        )
        product_counts = inspect_product_counts(connection)
        validate_player_v2_invariants(
            score_count=len(v2_result.scores),
            feature_count=len(v2_result.features),
            evidence_states=Counter(score.evidence_state for score in v2_result.scores),
            snapshot_counts=snapshot_counts,
            product_counts=product_counts,
        )

        provider_repository.finish_run(
            run_id,
            status="succeeded",
            request_count=0,
            rows_written=(
                canonical_rows_written
                + source_rows_written
                + snapshot_counts.get("score_snapshots", 0)
                + snapshot_counts.get("feature_snapshots", 0)
            ),
            metadata={
                "historical_only": True,
                "production_promotion": not target.is_local,
                "scope_key": SCOPE_KEY,
                "source_probe_counts_verified": True,
                "adapter_checks_passed": True,
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
        "scope_key": SCOPE_KEY,
        "source": {
            "provider": SOURCE_CODE,
            "matches": probe_result.report.match_count,
            "events": probe_result.report.event_count,
            "roster_players": probe_result.report.roster_player_count,
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
        f"({EXPECTED_MATCHES} matches, {EXPECTED_SEASON_PLAYERS} player profiles, "
        f"{EXPECTED_FEATURE_SNAPSHOTS} V2 features)"
    )
    print(f"TARGET: {target.safe_description}")
    print(f"PRODUCTION WRITTEN: {not target.is_local}")
    print(f"REPORT: {args.report}")


def inspect_prewrite_state(connection: Any) -> PrewriteState:
    competition_row = connection.execute(
        "select id from football.competitions where code = %s",
        (COMPETITION_CODE,),
    ).fetchone()
    if competition_row is None:
        raise HistoricalPlayerPromotionError(f"competition seed missing: {COMPETITION_CODE}")
    season_row = connection.execute(
        "select id from football.seasons where competition_id = %s and label = %s",
        (int(competition_row[0]), SEASON_LABEL),
    ).fetchone()
    season_exists = season_row is not None
    season_id = int(season_row[0]) if season_row is not None else None

    if season_id is None:
        matches = teams = players = appearances = player_stats = team_stats = 0
    else:
        matches = _scalar(connection, "select count(*) from football.matches where season_id=%s", (season_id,))
        teams = _scalar(
            connection,
            """
            select count(distinct team_id) from (
                select home_team_id as team_id from football.matches where season_id=%s
                union all
                select away_team_id as team_id from football.matches where season_id=%s
            ) scoped
            """,
            (season_id, season_id),
        )
        players = _scalar(
            connection,
            """
            select count(distinct pa.player_id)
            from football.player_appearances pa
            join football.matches m on m.id=pa.match_id
            where m.season_id=%s
            """,
            (season_id,),
        )
        appearances = _scalar(
            connection,
            """
            select count(*) from football.player_appearances pa
            join football.matches m on m.id=pa.match_id
            where m.season_id=%s
            """,
            (season_id,),
        )
        player_stats = _scalar(
            connection,
            """
            select count(*) from football.player_match_stats pms
            join football.matches m on m.id=pms.match_id
            where m.season_id=%s
            """,
            (season_id,),
        )
        team_stats = _scalar(
            connection,
            """
            select count(*) from football.team_match_stats tms
            join football.matches m on m.id=tms.match_id
            where m.season_id=%s
            """,
            (season_id,),
        )

    source_observations = _scalar(
        connection,
        """
        select count(*)
        from ingestion.source_observations observation
        join ingestion.providers provider on provider.id=observation.provider_id
        where provider.code=%s
          and observation.entity_identity_hints ->> 'season_label'=%s
        """,
        (SOURCE_CODE, SEASON_LABEL),
    )
    player_v2_rows = _scalar(
        connection,
        """
        select count(*) from analytics.product_player_detail_v2
        where scope_key=%s and model_version=%s
        """,
        (SCOPE_KEY, PLAYER_V2_MODEL_VERSION),
    )
    return PrewriteState(
        season_exists=season_exists,
        matches=matches,
        teams=teams,
        players=players,
        player_appearances=appearances,
        player_match_stats=player_stats,
        team_match_stats=team_stats,
        source_observations=source_observations,
        player_v2_rows=player_v2_rows,
    )


def validate_prewrite_state(state: PrewriteState) -> None:
    if state.is_fresh or state.is_certified_complete:
        return
    raise HistoricalPlayerPromotionError(
        "historical production scope is neither fresh nor already certified complete; "
        f"refusing to repair/overwrite unexpected partial state: {state}"
    )


def inspect_product_counts(connection: Any) -> dict[str, int]:
    return {
        "season_players": _scalar(
            connection,
            """
            select count(distinct player_id) from analytics.product_player_detail_v2
            where scope_key=%s and model_version=%s and window_key='season'
            """,
            (SCOPE_KEY, PLAYER_V2_MODEL_VERSION),
        ),
        "season_players_450_min": _scalar(
            connection,
            """
            select count(distinct player_id) from analytics.product_player_detail_v2
            where scope_key=%s and model_version=%s and window_key='season' and minutes >= 450
            """,
            (SCOPE_KEY, PLAYER_V2_MODEL_VERSION),
        ),
        "performance_ready": _scalar(
            connection,
            """
            select count(*)
            from analytics.product_player_detail_v2 snapshot
            cross join lateral jsonb_each(snapshot.dimension_evidence) evidence
            where snapshot.scope_key=%s
              and snapshot.model_version=%s
              and snapshot.window_key='season'
              and evidence.key='performance'
              and evidence.value->>'evidence_state'='ready'
              and evidence.value->>'score' is not null
            """,
            (SCOPE_KEY, PLAYER_V2_MODEL_VERSION),
        ),
        "ranking_candidates": _scalar(
            connection,
            """
            select count(*) from analytics.product_player_ranking_candidates_v2
            where scope_key=%s and model_version=%s
            """,
            (SCOPE_KEY, PLAYER_V2_MODEL_VERSION),
        ),
        "overall_scores": _scalar(
            connection,
            """
            select count(*) from analytics.product_player_detail_v2
            where scope_key=%s and model_version=%s and overall_score is not null
            """,
            (SCOPE_KEY, PLAYER_V2_MODEL_VERSION),
        ),
    }


def validate_player_v2_invariants(
    *,
    score_count: int,
    feature_count: int,
    evidence_states: Counter[str],
    snapshot_counts: dict[str, int],
    product_counts: dict[str, int],
) -> None:
    expected_snapshot_counts = {
        "score_snapshots": EXPECTED_SCORE_SNAPSHOTS,
        "feature_snapshots": EXPECTED_FEATURE_SNAPSHOTS,
    }
    if score_count != EXPECTED_SCORE_SNAPSHOTS or feature_count != EXPECTED_FEATURE_SNAPSHOTS:
        raise HistoricalPlayerPromotionError(
            f"unexpected Player V2 runtime counts: scores={score_count}, features={feature_count}"
        )
    for key, expected in expected_snapshot_counts.items():
        if snapshot_counts.get(key) != expected:
            raise HistoricalPlayerPromotionError(
                f"unexpected persisted {key}: {snapshot_counts.get(key)} != {expected}"
            )
    if dict(evidence_states) != EXPECTED_EVIDENCE_STATES:
        raise HistoricalPlayerPromotionError(
            f"unexpected Player V2 evidence states: {dict(evidence_states)}"
        )
    expected_product = {
        "season_players": EXPECTED_SEASON_PLAYERS,
        "season_players_450_min": EXPECTED_SEASON_PLAYERS_450_MIN,
        "performance_ready": EXPECTED_PERFORMANCE_READY,
        "ranking_candidates": EXPECTED_RANKING_CANDIDATES,
        "overall_scores": EXPECTED_OVERALL_SCORES,
    }
    if product_counts != expected_product:
        raise HistoricalPlayerPromotionError(
            f"unexpected Player V2 product counts: {product_counts} != {expected_product}"
        )


def _scalar(connection: Any, query: str, params: tuple[Any, ...] = ()) -> int:
    row = connection.execute(query, params).fetchone()
    if row is None:
        raise HistoricalPlayerPromotionError("count query returned no row")
    return int(row[0])


if __name__ == "__main__":
    main()
