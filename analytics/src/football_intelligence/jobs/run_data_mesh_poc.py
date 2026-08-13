"""Block 13 multi-source data mesh PoC.

Fetches a tiny, bounded sample from two zero-cost, zero-auth providers
(TheSportsDB free v1, OpenLigaDB), normalizes both into provider-independent
observations, resolves entity identity deterministically, reconciles
overlapping facts, and produces a machine-readable report.

This PoC proves the pipeline. It does NOT write to `football.*` canonical
tables -- persistence, when enabled via --database-url, only writes to the
`ingestion` schema's audit/reconciliation tables.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.openligadb import parse_league_matches
from football_intelligence.data_mesh.adapters.thesportsdb import parse_league_events
from football_intelligence.data_mesh.entity_resolution import COMPETITION_MAPPINGS
from football_intelligence.data_mesh.models import NormalizedObservation, ReconciliationDecision
from football_intelligence.data_mesh.pipeline import (
    coverage_by_source as _coverage_by_source,
)
from football_intelligence.data_mesh.pipeline import (
    resolve_and_reconcile as _resolve_and_reconcile,
)
from football_intelligence.data_mesh.reconciliation import MODEL_VERSION
from football_intelligence.db.data_mesh_repository import DataMeshRepository
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.ingestion.raw_store import LocalRawStore
from football_intelligence.providers.openligadb import OpenLigaDbClient, OpenLigaDbError
from football_intelligence.providers.thesportsdb import TheSportsDbClient, TheSportsDbError

# The two source adapters each issue exactly one request in V0: no
# pagination, no per-team/per-match follow-up calls.
PLANNED_REQUESTS = 2
DEFAULT_REQUEST_BUDGET = 4
MAX_REQUEST_BUDGET = 15

# TheSportsDB's free `eventsseason.php` naturally caps around 15 events per
# call. OpenLigaDB has no such cap and returns the entire season (~306
# matches) in one response -- bounding it client-side keeps the PoC sample
# genuinely tiny and comparable, even though both are still just 1 request.
OPENLIGADB_SAMPLE_LIMIT = 15

# Verified via a live probe during Block 13 implementation: the current
# (2026-2027) Bundesliga season had not yet produced enough finished matches
# through both free sources, so V0 defaults to the completed 2025-2026
# sample the task explicitly allows. Override with --season if a later
# season becomes fully usable.
DEFAULT_SEASON_LABEL = "2025-2026"

_CANONICAL_COMPETITION_CODE = "GER_BL1"

REPORT_EXAMPLE_LIMIT = 10


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 13 multi-source data mesh PoC: fetch a tiny bounded sample from "
            "TheSportsDB + OpenLigaDB, normalize, resolve identity, and reconcile."
        )
    )
    parser.add_argument("--season", default=DEFAULT_SEASON_LABEL)
    parser.add_argument("--request-budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.request_budget < 1 or args.request_budget > MAX_REQUEST_BUDGET:
        raise SystemExit(f"--request-budget must be between 1 and {MAX_REQUEST_BUDGET}")
    if args.request_budget < PLANNED_REQUESTS:
        raise SystemExit(
            f"data mesh PoC planned_requests={PLANNED_REQUESTS} exceeds "
            f"--request-budget={args.request_budget}"
        )

    thesportsdb_external_id = _competition_external_id("thesportsdb")
    openligadb_external_id = _competition_external_id("openligadb")
    openligadb_season = str(args.season).split("-")[0]

    raw_store = LocalRawStore(args.raw_dir)
    database_url = args.database_url or os.environ.get("DATABASE_URL")

    connection = connect(database_url) if database_url else None
    thesportsdb_run_id: int | None = None
    openligadb_run_id: int | None = None
    thesportsdb_provider_repo: ProviderRepository | None = None
    openligadb_provider_repo: ProviderRepository | None = None

    if connection is not None:
        thesportsdb_provider_repo = ProviderRepository(connection, provider_code="thesportsdb")
        thesportsdb_run_id = thesportsdb_provider_repo.start_run(
            job_name="data-mesh-poc",
            trigger_kind="manual",
            scope={"competition_external_id": thesportsdb_external_id, "season": args.season},
        )
        openligadb_provider_repo = ProviderRepository(connection, provider_code="openligadb")
        openligadb_run_id = openligadb_provider_repo.start_run(
            job_name="data-mesh-poc",
            trigger_kind="manual",
            scope={"competition_external_id": openligadb_external_id, "season": openligadb_season},
        )

    thesportsdb_status, thesportsdb_requests, thesportsdb_observations = _fetch_thesportsdb(
        raw_store=raw_store,
        competition_external_id=thesportsdb_external_id,
        season_label=str(args.season),
        ingestion_run_id=thesportsdb_run_id,
    )
    openligadb_status, openligadb_requests, openligadb_observations = _fetch_openligadb(
        raw_store=raw_store,
        competition_external_id=openligadb_external_id,
        season=openligadb_season,
        ingestion_run_id=openligadb_run_id,
    )

    all_observations = thesportsdb_observations + openligadb_observations
    decisions, resolution_meta = _resolve_and_reconcile(all_observations)

    persistence: dict[str, Any] = {"mode": "not_requested"}
    if connection is not None:
        mesh_repository = DataMeshRepository(connection)
        observations_written = mesh_repository.persist_observations(all_observations)
        decisions_written = mesh_repository.replace_decisions(decisions)

        assert thesportsdb_provider_repo is not None
        assert openligadb_provider_repo is not None
        assert thesportsdb_run_id is not None
        assert openligadb_run_id is not None
        thesportsdb_provider_repo.finish_run(
            thesportsdb_run_id,
            status="succeeded" if thesportsdb_status == "ok" else "failed",
            request_count=thesportsdb_requests,
            rows_written=len(thesportsdb_observations),
            metadata={"status": thesportsdb_status},
            error_message=None if thesportsdb_status == "ok" else thesportsdb_status,
        )
        openligadb_provider_repo.finish_run(
            openligadb_run_id,
            status="succeeded" if openligadb_status == "ok" else "failed",
            request_count=openligadb_requests,
            rows_written=len(openligadb_observations),
            metadata={"status": openligadb_status},
            error_message=None if openligadb_status == "ok" else openligadb_status,
        )
        connection.commit()
        connection.close()
        persistence = {
            "mode": "postgresql",
            "observations_written": observations_written,
            "decisions_written": decisions_written,
        }

    report = _build_report(
        args=args,
        thesportsdb_status=thesportsdb_status,
        thesportsdb_requests=thesportsdb_requests,
        thesportsdb_observations=thesportsdb_observations,
        openligadb_status=openligadb_status,
        openligadb_requests=openligadb_requests,
        openligadb_observations=openligadb_observations,
        all_observations=all_observations,
        decisions=decisions,
        resolution_meta=resolution_meta,
        persistence=persistence,
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        f"DATA MESH POC: {thesportsdb_status}/{openligadb_status} "
        f"({len(all_observations)} observations, {len(decisions)} decisions, "
        f"{thesportsdb_requests + openligadb_requests} API requests)"
    )
    print(f"REPORT: {args.report}")


def _competition_external_id(source_code: str) -> str:
    for mapping in COMPETITION_MAPPINGS:
        if (
            mapping.source_code == source_code
            and mapping.canonical_code == _CANONICAL_COMPETITION_CODE
        ):
            return mapping.external_id
    raise RuntimeError(f"no PoC competition mapping configured for {source_code}")


def _fetch_thesportsdb(
    *,
    raw_store: LocalRawStore,
    competition_external_id: str,
    season_label: str,
    ingestion_run_id: int | None,
) -> tuple[str, int, list[NormalizedObservation]]:
    client = TheSportsDbClient()
    try:
        response = client.get(
            "eventsseason.php",
            {"id": competition_external_id, "s": season_label},
        )
    except TheSportsDbError as exc:
        return f"error: {exc}", 0, []

    raw_store.put(
        endpoint=response.endpoint,
        parameters=dict(response.parameters),
        payload=response.payload,
    )
    observations = parse_league_events(
        response.payload,
        competition_external_id=competition_external_id,
        ingestion_run_id=ingestion_run_id,
    )
    return "ok", 1, observations


def _fetch_openligadb(
    *,
    raw_store: LocalRawStore,
    competition_external_id: str,
    season: str,
    ingestion_run_id: int | None,
) -> tuple[str, int, list[NormalizedObservation]]:
    client = OpenLigaDbClient()
    try:
        response = client.get(f"getmatchdata/{competition_external_id}/{season}")
    except OpenLigaDbError as exc:
        return f"error: {exc}", 0, []

    payload_object = {"matches": response.payload}
    raw_store.put(
        endpoint=response.endpoint,
        parameters={"competition": competition_external_id, "season": season},
        payload=payload_object,
    )
    observations = parse_league_matches(
        response.payload,
        competition_external_id=competition_external_id,
        ingestion_run_id=ingestion_run_id,
        limit=OPENLIGADB_SAMPLE_LIMIT,
    )
    return "ok", 1, observations


def _build_report(
    *,
    args: argparse.Namespace,
    thesportsdb_status: str,
    thesportsdb_requests: int,
    thesportsdb_observations: list[NormalizedObservation],
    openligadb_status: str,
    openligadb_requests: int,
    openligadb_observations: list[NormalizedObservation],
    all_observations: list[NormalizedObservation],
    decisions: list[ReconciliationDecision],
    resolution_meta: dict[str, Any],
    persistence: dict[str, Any],
) -> dict[str, Any]:
    entities_observed: dict[str, int] = defaultdict(int)
    seen_entities: set[tuple[str, str]] = set()
    for observation in all_observations:
        entity_key = (observation.entity_type, observation.entity_source_id)
        if entity_key not in seen_entities:
            seen_entities.add(entity_key)
            entities_observed[observation.entity_type] += 1

    examples = [
        {
            "logical_entity_key": decision.logical_entity_key,
            "entity_type": decision.entity_type,
            "metric_name": decision.metric_name,
            "status": decision.status,
            "candidate_value": decision.candidate_value,
            "confidence": decision.confidence,
            "participating_sources": list(decision.participating_sources),
        }
        for decision in decisions[:REPORT_EXAMPLE_LIMIT]
    ]

    return {
        "model_version": MODEL_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "season": args.season,
        "request_budget": args.request_budget,
        "planned_requests": PLANNED_REQUESTS,
        "actual_requests": thesportsdb_requests + openligadb_requests,
        "sources": {
            "thesportsdb": {
                "status": thesportsdb_status,
                "requests": thesportsdb_requests,
                "observation_count": len(thesportsdb_observations),
            },
            "openligadb": {
                "status": openligadb_status,
                "requests": openligadb_requests,
                "observation_count": len(openligadb_observations),
            },
        },
        "entities_observed": dict(entities_observed),
        "metrics_observed": sorted({observation.metric_name for observation in all_observations}),
        "overlap_count": resolution_meta["overlap_count"],
        "agreement_count": sum(1 for decision in decisions if decision.status == "agreed"),
        "single_source_count": sum(
            1 for decision in decisions if decision.status == "single_source"
        ),
        "conflict_count": sum(1 for decision in decisions if decision.status == "conflict"),
        "unresolved_identity_count": resolution_meta["unresolved_observation_count"],
        "unresolved_identity_examples": resolution_meta["unresolved_identity_examples"],
        "coverage_by_source": _coverage_by_source(all_observations),
        "reconciliation_examples": examples,
        "persistence": persistence,
        "scope": (
            "PoC only: proves multi-source reconciliation. football.* canonical "
            "tables are not fed by this job."
        ),
    }


if __name__ == "__main__":
    main()
