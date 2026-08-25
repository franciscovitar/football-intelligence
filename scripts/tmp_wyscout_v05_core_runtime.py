from __future__ import annotations

import argparse
import dataclasses
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.wyscout_open import SEMANTIC_VERSION, SOURCE_CODE
from football_intelligence.db.player_analytics_repository import PlayerAnalyticsRepository
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.jobs.calculate_player_analytics import _persist_versioned_snapshots
from football_intelligence.jobs.historical_player_promotion_spec import (
    SEASON_LABEL,
    historical_player_promotion_spec,
)
from football_intelligence.jobs.load_wyscout_historical import (
    _apply_safe_minutes_policy,
    _prepare_canonical_team_links,
    _scoped_database_counts,
)
from football_intelligence.jobs.promote_historical_player_v2 import (
    _prepare_source,
    inspect_product_counts,
)
from football_intelligence.jobs.wyscout_historical_scope import scope_config
from football_intelligence.player_analytics.engine import calculate_player_analytics
from football_intelligence.player_analytics.engine_v2 import (
    MODEL_VERSION as PLAYER_V2_MODEL_VERSION,
)
from football_intelligence.player_analytics.engine_v2 import calculate_player_analytics_v2_result

COMPETITIONS = ("ESP_LL", "ITA_SA", "GER_BL1", "FRA_L1")
SPATIAL_METRICS = ("long_passes_accurate", "passes_into_final_third")
FIXED_CALCULATED_AT = datetime(2026, 8, 25, 15, 30, tzinfo=UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def _bridge_metrics(connection: Any, competition_code: str) -> dict[str, Any]:
    row = connection.execute(
        """
        select
            count(*) as player_match_rows,
            count(pms.long_passes_accurate),
            count(*) filter (where pms.long_passes_accurate = 0),
            count(*) filter (where pms.long_passes_accurate > 0),
            coalesce(sum(pms.long_passes_accurate), 0),
            count(pms.passes_into_final_third),
            count(*) filter (where pms.passes_into_final_third = 0),
            count(*) filter (where pms.passes_into_final_third > 0),
            coalesce(sum(pms.passes_into_final_third), 0)
        from football.player_match_stats pms
        join football.matches m on m.id = pms.match_id
        join football.seasons s on s.id = m.season_id
        join football.competitions c on c.id = s.competition_id
        where c.code = %s and s.label = %s
        """,
        (competition_code, SEASON_LABEL),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"no bridge count row for {competition_code}")
    return {
        "player_match_rows": int(row[0]),
        "long_passes_accurate": {
            "observed": int(row[1]),
            "true_zero": int(row[2]),
            "positive": int(row[3]),
            "sum": int(row[4]),
        },
        "passes_into_final_third": {
            "observed": int(row[5]),
            "true_zero": int(row[6]),
            "positive": int(row[7]),
            "sum": int(row[8]),
        },
    }


def _read_path_metrics(player_observations: list[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for metric in SPATIAL_METRICS:
        values = [observation.stats.get(metric) for observation in player_observations]
        observed = [value for value in values if value is not None]
        result[metric] = {
            "observed_player_matches": len(observed),
            "true_zero": sum(1 for value in observed if value == 0),
            "positive": sum(1 for value in observed if value is not None and value > 0),
            "sum": int(sum(float(value) for value in observed)),
        }
    return result


def _adapter_spatial(observations: list[Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for metric in SPATIAL_METRICS:
        values = [
            observation.value
            for observation in observations
            if observation.metric_name == metric
            and observation.entity_type == "player"
            and observation.metric_granularity == "player_match"
        ]
        result[metric] = {
            "observations": len(values),
            "true_zero": sum(1 for value in values if value == 0),
            "positive": sum(1 for value in values if isinstance(value, int | float) and value > 0),
            "sum": int(sum(float(value) for value in values)),
        }
    return result


def _season_feature_counts(v2_result: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for metric in SPATIAL_METRICS:
        features = [
            feature
            for feature in v2_result.features
            if feature.window == "season" and feature.metric_name == metric
        ]
        result[metric] = {
            "features": len(features),
            "percentile_ready": sum(1 for feature in features if feature.percentile_state == "ready"),
            "percentile_insufficient_sample": sum(
                1 for feature in features if feature.percentile_state == "insufficient_sample"
            ),
            "percentile_not_applicable": sum(
                1 for feature in features if feature.percentile_state == "not_applicable"
            ),
        }
    return result


def _passing_states(v2_result: Any) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for score in v2_result.scores:
        if score.window != "season":
            continue
        evidence = score.dimension_evidence.get("passing")
        if evidence is not None:
            counter[evidence.evidence_state] += 1
    return dict(counter)


def _validate_spatial_flow(
    *,
    competition_code: str,
    adapter: dict[str, Any],
    bridge: dict[str, Any],
    metric_counts: Counter[str],
) -> list[str]:
    failures: list[str] = []
    if metric_counts.get("progressive_passes", 0) != 0:
        failures.append(f"{competition_code}: progressive_passes unexpectedly emitted")
    for metric in SPATIAL_METRICS:
        adapter_metric = adapter[metric]
        bridge_metric = bridge[metric]
        if adapter_metric["observations"] <= 0:
            failures.append(f"{competition_code}: {metric} has no adapter observations")
        if adapter_metric["observations"] != bridge_metric["observed"]:
            failures.append(
                f"{competition_code}: {metric} adapter/bridge observed mismatch "
                f"{adapter_metric['observations']} != {bridge_metric['observed']}"
            )
        if adapter_metric["sum"] != bridge_metric["sum"]:
            failures.append(
                f"{competition_code}: {metric} adapter/bridge sum mismatch "
                f"{adapter_metric['sum']} != {bridge_metric['sum']}"
            )
        if adapter_metric["true_zero"] != bridge_metric["true_zero"]:
            failures.append(
                f"{competition_code}: {metric} adapter/bridge zero mismatch "
                f"{adapter_metric['true_zero']} != {bridge_metric['true_zero']}"
            )
    return failures


def main() -> None:
    args = build_parser().parse_args()
    if SEMANTIC_VERSION != "wyscout-open-v0.5":
        raise SystemExit(f"runtime evidence requires v0.5 candidate, got {SEMANTIC_VERSION}")

    results: list[dict[str, Any]] = []
    failures: list[str] = []

    with connect(args.database_url) as connection:
        for competition_code in COMPETITIONS:
            spec = historical_player_promotion_spec(competition_code)
            config = scope_config(competition_code)
            probe, source_validation, adapter_report, observations, normalization = _prepare_source(
                args.cache_dir,
                spec=spec,
            )
            if not source_validation.passed or not adapter_report.passed:
                failures.append(f"{competition_code}: source or adapter validation failed")

            metric_counts = Counter(observation.metric_name for observation in observations)
            adapter_spatial = _adapter_spatial(observations)
            safe_batch, minutes_report = _apply_safe_minutes_policy(
                normalization.batch,
                observations=observations,
            )
            canonical_batch, team_links = _prepare_canonical_team_links(connection, safe_batch)

            provider = ProviderRepository(connection, provider_code=SOURCE_CODE)
            run_id = provider.start_run(
                job_name="evidence_wyscout_v05_core_runtime",
                trigger_kind="manual",
                scope={
                    "competition": competition_code,
                    "season": SEASON_LABEL,
                    "candidate_semantic_version": SEMANTIC_VERSION,
                    "evidence_only": True,
                },
            )
            canonical_rows_written = provider.persist_batch(
                competition_code=competition_code,
                batch=canonical_batch,
            )
            provider.finish_run(
                run_id,
                status="succeeded",
                request_count=0,
                rows_written=canonical_rows_written,
                metadata={"evidence_only": True, "source_observations_not_persisted": True},
            )
            connection.commit()

            db_counts = _scoped_database_counts(
                connection,
                competition_code=competition_code,
                season_label=SEASON_LABEL,
                provider_competition_id=config.scope.provider_competition_id,
            )
            bridge = _bridge_metrics(connection, competition_code)
            failures.extend(
                _validate_spatial_flow(
                    competition_code=competition_code,
                    adapter=adapter_spatial,
                    bridge=bridge,
                    metric_counts=metric_counts,
                )
            )

            repository = PlayerAnalyticsRepository(connection)
            player_observations = repository.load_observations(
                season_label=SEASON_LABEL,
                competition_codes=(competition_code,),
            )
            scope_key = spec.scope_key
            v1_first = calculate_player_analytics(
                player_observations,
                scope_key=scope_key,
                calculated_at=FIXED_CALCULATED_AT,
            )
            v2_first = calculate_player_analytics_v2_result(
                player_observations,
                scope_key=scope_key,
                calculated_at=FIXED_CALCULATED_AT,
            )
            v1_second = calculate_player_analytics(
                player_observations,
                scope_key=scope_key,
                calculated_at=FIXED_CALCULATED_AT,
            )
            v2_second = calculate_player_analytics_v2_result(
                player_observations,
                scope_key=scope_key,
                calculated_at=FIXED_CALCULATED_AT,
            )
            deterministic = v1_first == v1_second and v2_first == v2_second
            if not deterministic:
                failures.append(f"{competition_code}: repeated Player V1/V2 calculation differs")

            _persist_versioned_snapshots(
                repository,
                v1_result=v1_first,
                v2_result=v2_first,
                scope_key=scope_key,
            )
            first_snapshot_counts = repository.snapshot_counts(
                scope_key=scope_key,
                model_version=PLAYER_V2_MODEL_VERSION,
            )
            connection.commit()

            _persist_versioned_snapshots(
                repository,
                v1_result=v1_second,
                v2_result=v2_second,
                scope_key=scope_key,
            )
            second_snapshot_counts = repository.snapshot_counts(
                scope_key=scope_key,
                model_version=PLAYER_V2_MODEL_VERSION,
            )
            connection.commit()
            if first_snapshot_counts != second_snapshot_counts:
                failures.append(
                    f"{competition_code}: snapshot counts changed on repeat "
                    f"{first_snapshot_counts} != {second_snapshot_counts}"
                )

            product_counts = inspect_product_counts(connection, spec=spec)
            season_scores = [score for score in v2_first.scores if score.window == "season"]
            evidence_states = dict(Counter(score.evidence_state for score in v2_first.scores))

            result = {
                "competition_code": competition_code,
                "semantic_version": SEMANTIC_VERSION,
                "source": {
                    "matches": source_validation.match_count,
                    "events": source_validation.event_count,
                    "adapter_observations": len(observations),
                    "adapter_safe_identities": adapter_report.safe_identity_count,
                    "progressive_passes_observations": metric_counts.get("progressive_passes", 0),
                    "official_archive_checksum_probe": probe.report.counts_verified,
                },
                "adapter_spatial": adapter_spatial,
                "canonical_db": {
                    **dataclasses.asdict(db_counts),
                    "note": "source_observations intentionally not persisted in this evidence runner",
                },
                "bridge_spatial": bridge,
                "read_path_spatial": _read_path_metrics(player_observations),
                "player_v2": {
                    "input_player_match_observations": len(player_observations),
                    "score_snapshots": len(v2_first.scores),
                    "feature_snapshots": len(v2_first.features),
                    "season_players": len(season_scores),
                    "evidence_states": evidence_states,
                    "passing_season_states": _passing_states(v2_first),
                    "season_spatial_features": _season_feature_counts(v2_first),
                    "snapshot_counts_first": first_snapshot_counts,
                    "snapshot_counts_second": second_snapshot_counts,
                    "deterministic_repeat": deterministic,
                    "product_counts": product_counts,
                },
                "canonical_rows_written": canonical_rows_written,
                "team_links": dataclasses.asdict(team_links),
                "minutes_policy": dataclasses.asdict(minutes_report),
            }
            results.append(result)

    report = {
        "status": "FAIL" if failures else "PASS",
        "candidate_semantic_version": SEMANTIC_VERSION,
        "methodology_id": "fi-wyscout-spatial-v1.2",
        "production_write": False,
        "data_mesh_persisted": False,
        "results": results,
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    if failures:
        raise SystemExit("WYSCOUT v0.5 CORE RUNTIME EVIDENCE: FAIL")
    print("WYSCOUT v0.5 CORE RUNTIME EVIDENCE: PASS")


if __name__ == "__main__":
    main()
