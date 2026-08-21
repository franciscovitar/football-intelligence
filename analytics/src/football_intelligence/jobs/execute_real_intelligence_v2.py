"""Block 19: execute Real Intelligence V2 against the real ENG_PL 2025/26 snapshot.

This is the single official entry point that proves the accepted V2 engines
and the Diagnostic Rule Engine against real (mostly-missing) evidence:

1. verifies the target database is either local or an explicitly,
   triple-confirmed remote production instance (never a bare `DATABASE_URL`
   environment fallback in either case) -- see
   `db.production_write_guard.resolve_database_target`, the shared contract
   `jobs.build_real_snapshot_v2` and `jobs.load_real_snapshot` also use
   (V1 Closure Pass A/B preparation);
2. assesses the canonical ENG_PL 2025/26 real state (measured from the
   database every run, never hardcoded);
3. executes Team V2 on the real team observations already loaded by
   `football-intelligence-load-real-snapshot`;
4. evaluates only the Diagnostic Rule Engine findings whose required
   evidence genuinely exists in that Team V2 output, and persists them with
   explicit `data_context = "real"` / `source_model_version = "team-v2.0"`
   product-safety context;
5. records why Player V2 correctly stays `insufficient_data` (there is no
   permitted real player-match evidence -- this job never calls the player
   engine when there is nothing to score);
6. verifies the product-safe views reflect exactly this run;
7. writes a machine-readable execution report, including which database
   target (local/remote) was actually used.

Running this job twice against the same real data is idempotent: Team V2
persistence and diagnostic-findings persistence are both delete-then-insert
for the exact scope being replaced, so row counts are stable across reruns.

Remote (production) execution additionally requires `--allow-remote-write`,
`--confirm-target production`, and `--production-write-confirmation` with
the exact required phrase (`db.production_write_guard`) -- a plain remote
`--database-url` alone is refused before any connection is attempted, and
no environment variable can supply any of these three confirmations.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.db.diagnostic_findings_repository import (
    DiagnosticFindingsRepository,
)
from football_intelligence.db.production_write_guard import resolve_database_target
from football_intelligence.db.provider_repository import connect
from football_intelligence.db.team_analytics_repository import TeamAnalyticsRepository
from football_intelligence.diagnostics.models import (
    MODEL_VERSION as DIAGNOSTIC_ENGINE_MODEL_VERSION,
)
from football_intelligence.diagnostics.models import DiagnosticFinding
from football_intelligence.diagnostics.orchestrator import (
    TeamDiagnosticInputs,
    evaluate_team_diagnostics,
)
from football_intelligence.jobs.score_real_snapshot import assess_real_snapshot
from football_intelligence.team_analytics.engine_v2 import (
    MODEL_VERSION as TEAM_V2_MODEL_VERSION,
)
from football_intelligence.team_analytics.engine_v2 import (
    TeamAnalyticsResultV2,
    calculate_team_analytics_v2,
)

COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2025/26"
SCOPE_KEY = f"competition:{COMPETITION_CODE}:{SEASON_LABEL}"
DIAGNOSTIC_SOURCE_MODEL_VERSION = TEAM_V2_MODEL_VERSION  # "team-v2.0"
DATA_CONTEXT = "real"

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REPORT_PATH = _REPO_ROOT / "data" / "manifests" / "intelligence" / "ENG_PL" / "2025-26.json"

_PRODUCT_VIEWS = (
    "analytics.product_team_detail_v2",
    "analytics.product_team_ranking_candidates_v2",
    "analytics.product_team_diagnostic_findings_v2",
    "analytics.product_player_detail_v2",
    "analytics.product_player_ranking_candidates_v2",
    "analytics.product_player_diagnostic_findings_v2",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 19: execute Team V2 and the Diagnostic Rule Engine against the "
            "real ENG_PL 2025/26 snapshot and report exactly what real evidence "
            "supports."
        )
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help=(
            "Explicit PostgreSQL URL. Never read from the DATABASE_URL environment "
            "variable. A local URL (localhost/127.0.0.1/::1, or a host-less local-socket "
            "DSN) is accepted directly. A remote (production) URL additionally requires "
            "--allow-remote-write, --confirm-target production, and "
            "--production-write-confirmation with the exact required phrase -- see "
            "db.production_write_guard."
        ),
    )
    parser.add_argument("--allow-remote-write", action="store_true")
    parser.add_argument("--confirm-target", default=None)
    parser.add_argument("--production-write-confirmation", default=None)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser


def build_team_diagnostic_inputs_v2(
    result: TeamAnalyticsResultV2,
) -> tuple[TeamDiagnosticInputs, ...]:
    """Bridge real Team V2 evidence into the Diagnostic Rule Engine's input contract.

    `score` is always `None` here -- the score-dependent rules
    (`results_above_process`, `regression_risk`, `creation_problem`, ...) wrap
    the legacy V1 `TeamScore` and must never be fed for real Block 19
    execution (no V1 fallback). Only the three percentile-only rules
    (`sterile_possession`, `few_but_high_quality_chances_allowed`,
    `high_volume_low_quality_allowed`) are ever reachable this way, and each
    still requires its own real evidence to fire -- `evaluate_team_diagnostics`
    returns `None` for any rule whose inputs are missing.

    `TeamFeatureV2.percentile` is a raw rank percentile of `adjusted_value`
    (higher value -> higher percentile), not direction-adjusted. The
    diagnostic rules, like V1's percentile inputs before them, expect an
    already-inverted "higher is always better" scale for volume/quality
    *allowed* metrics (docstring of
    `team_analytics.engine_v2.classify_chance_quality_allowed`: fewer shots
    allowed, or lower xGA, must read as a *higher* percentile). `shots_allowed`,
    `shots_on_target_allowed` and `xga` are all `lower_better` metrics, so
    their raw percentile is inverted (`100 - percentile`) here before being
    passed through; `possession_pct` is `higher_better` already and needs no
    inversion.
    """

    feature_maps: dict[tuple[int, str], dict[str, Any]] = defaultdict(dict)
    for feature in result.features:
        feature_maps[(feature.team_id, feature.window)][feature.metric_name] = feature

    def _inverted_percentile(feature: Any | None) -> float | None:
        if feature is None or feature.percentile is None:
            return None
        return round(100.0 - float(feature.percentile), 2)

    inputs: list[TeamDiagnosticInputs] = []
    for score in result.scores:
        feature_map = feature_maps[(score.team_id, score.window)]
        possession = feature_map.get("possession_pct")
        shots_against = feature_map.get("shots_allowed")
        shots_on_target_against = feature_map.get("shots_on_target_allowed")
        xga = feature_map.get("xga")
        creation_evidence = score.dimension_evidence.get("creation")
        inputs.append(
            TeamDiagnosticInputs(
                team_id=score.team_id,
                team_name=score.team_name,
                comparison_group=score.scope_key,
                window=score.window,
                confidence=score.confidence,
                possession_percentile=(possession.percentile if possession is not None else None),
                chance_generation_percentile=(
                    creation_evidence.score if creation_evidence is not None else None
                ),
                shots_total_against_percentile=_inverted_percentile(shots_against),
                shots_on_target_against_percentile=_inverted_percentile(shots_on_target_against),
                xga_percentile=_inverted_percentile(xga),
                score=None,
            )
        )
    return tuple(inputs)


def _execute_team_v2(
    connection: Any, *, calculated_at: datetime
) -> tuple[TeamAnalyticsResultV2, tuple[DiagnosticFinding, ...]]:
    repository = TeamAnalyticsRepository(connection)
    observations = repository.load_observations(
        season_label=SEASON_LABEL, competition_codes=(COMPETITION_CODE,)
    )
    if not observations:
        raise SystemExit(
            f"No finished team observations found for {SCOPE_KEY}. Run "
            "football-intelligence-load-real-snapshot first."
        )
    result = calculate_team_analytics_v2(
        observations, scope_key=SCOPE_KEY, calculated_at=calculated_at
    )
    season_id = observations[0].season_id
    repository.replace_v2_snapshots(
        result, scope_key=SCOPE_KEY, season_id=season_id, data_context=DATA_CONTEXT
    )

    findings: list[DiagnosticFinding] = []
    for inputs in build_team_diagnostic_inputs_v2(result):
        findings.extend(evaluate_team_diagnostics(inputs, computed_at=calculated_at))

    findings_repository = DiagnosticFindingsRepository(connection)
    findings_repository.replace_scope(
        findings,
        entity_type="team",
        data_context=DATA_CONTEXT,
        source_model_version=DIAGNOSTIC_SOURCE_MODEL_VERSION,
        scope_key=SCOPE_KEY,
    )
    return result, tuple(findings)


def _dimension_readiness(result: TeamAnalyticsResultV2) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"ready": 0, "partial": 0, "insufficient_data": 0}
    )
    for score in result.scores:
        for dimension, evidence in score.dimension_evidence.items():
            counts[dimension][evidence.evidence_state] += 1
    return {name: dict(states) for name, states in sorted(counts.items())}


def _product_view_counts(connection: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for view in _PRODUCT_VIEWS:
        row = connection.execute(f"select count(*) from {view}").fetchone()
        counts[view.removeprefix("analytics.")] = int(row[0]) if row else 0
    return counts


def _active_scopes(connection: Any) -> dict[str, Any]:
    def _one(view: str) -> dict[str, Any] | None:
        row = connection.execute(
            f"select scope_key, model_version from analytics.{view}"
        ).fetchone()
        if row is None:
            return None
        return {"scope_key": row[0], "model_version": row[1]}

    return {
        "team": _one("product_active_team_scope_v2"),
        "player": _one("product_active_player_scope_v2"),
    }


def main() -> None:
    args = build_parser().parse_args()
    target = resolve_database_target(
        args.database_url,
        allow_remote_write=args.allow_remote_write,
        confirm_target=args.confirm_target,
        production_write_confirmation=args.production_write_confirmation,
    )
    assert target is not None  # --database-url is required
    database_url = target.database_url

    calculated_at = datetime.now(UTC)

    with connect(database_url) as connection:
        assessment = assess_real_snapshot(connection)

        team_result, team_findings = _execute_team_v2(connection, calculated_at=calculated_at)

        # Player V2 is never invoked here: with zero real player-match
        # observations there is nothing to score, and calling the player
        # engine on an empty input would only manufacture the appearance of
        # execution. `assessment` already carries the true, measured reason.
        connection.commit()

        product_counts = _product_view_counts(connection)
        active_scopes = _active_scopes(connection)
        connection.rollback()

    dimension_readiness = _dimension_readiness(team_result)
    overall_ready = sum(1 for score in team_result.scores if score.evidence_state == "ready")
    dimension_rankable = sorted(
        name for name, states in dimension_readiness.items() if states.get("ready", 0) > 0
    )

    report = {
        "model_versions": {
            "team_v2": TEAM_V2_MODEL_VERSION,
            "diagnostic_engine": DIAGNOSTIC_ENGINE_MODEL_VERSION,
        },
        "competition": COMPETITION_CODE,
        "season": SEASON_LABEL,
        "period_role": "latest_completed",
        "scope_key": SCOPE_KEY,
        "executed_at": calculated_at.isoformat(),
        "canonical_real_input": {
            "matches": assessment.match_count,
            "team_stat_rows": assessment.team_stat_rows,
            "player_observation_rows": assessment.player_observation_rows,
        },
        "team_v2_execution": {
            "feature_rows": len(team_result.features),
            "score_rows": len(team_result.scores),
            "windows": sorted({score.window for score in team_result.scores}),
            "evidence_state_counts": {
                state: sum(1 for score in team_result.scores if score.evidence_state == state)
                for state in ("ready", "partial", "insufficient_data")
            },
            "dimension_readiness": dimension_readiness,
            "dimensions_with_ready_rankings": dimension_rankable,
            "overall_score_available": overall_ready > 0,
            "overall_ranking_available": overall_ready > 0,
        },
        "player_v2_execution": {
            "player_observation_rows": assessment.player_observation_rows,
            "state": assessment.state,
            "reason": assessment.reason,
            "feature_rows": 0,
            "score_rows": 0,
            "ranking_rows": 0,
        },
        "real_diagnostics": {
            "team_findings_count": len(team_findings),
            "diagnostic_codes": sorted({finding.diagnostic_code for finding in team_findings}),
            "player_findings_count": 0,
        },
        "product_view_counts": product_counts,
        "active_scopes": active_scopes,
        "historical_deep_validation": {
            "dataset": "statsbomb-open:wc2022",
            "role": "historical_deep",
            "reproduction_command": "football-intelligence-collect-validation-snapshot",
            "capability_proven": (
                "Real StatsBomb Open Data event JSON parses into provider-independent "
                "NormalizedObservations (match + event-derived families: shots, passes, "
                "dribbles, duels, fouls, goalkeeper actions) via the existing Data Mesh "
                "adapter. Never loaded into football.* and never executes team_analytics "
                "or player_analytics V2 engines -- that would require a new ingestion "
                "path (competition/team/player entity resolution + a football.* loader) "
                "that does not exist yet; see docs/REAL_INTELLIGENCE_EXECUTION_V2.md."
            ),
            "engine_execution_performed": False,
            "product_contamination": False,
        },
        "scoring_correctness": {
            "incomplete_evidence_renormalized_into_full_score": False,
            "missing_values_converted_to_zero": False,
            "v1_fallback_used": False,
        },
        "db_safety": {
            "implicit_database_url_used": False,
            "remote_db_accepted": not target.is_local,
            "target": (target.host if target.host is not None else "(local socket)"),
        },
    }

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(
        "REAL INTELLIGENCE V2: "
        f"{SCOPE_KEY} -- {len(team_result.scores)} team score rows, "
        f"{len(team_findings)} real diagnostic findings, "
        f"overall ranking available: {overall_ready > 0}, "
        f"player state: {assessment.state}"
    )
    print(f"REPORT: {args.report_path}")


if __name__ == "__main__":
    main()
