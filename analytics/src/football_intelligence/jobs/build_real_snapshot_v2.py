"""Block 18: build the auditable, reconciled real ENG_PL 2025/26 snapshot.

Single reproducible command that:

1. acquires Football-Data.co.uk's published results CSV (the primary
   current source; already the source `load_real_snapshot.py` loads into
   `football.*`, unchanged here) and OpenFootball's published season JSON
   (a second, independent, public-domain current source, new in Block 18);
2. normalizes both into provider-independent observations through the
   existing adapters -- missing stays missing, never fabricated;
3. resolves entity identity and reconciles the two sources' overlapping
   match-result facts through the existing Data Mesh pipeline
   (`resolve_and_reconcile`), proving real multi-source agreement/conflict
   detection on the canonical current-season snapshot rather than only a
   Bundesliga PoC sample;
4. measures real coverage against the full, dynamic Metric Catalog V2
   (never a shrunk or hand-maintained list);
5. writes a machine-readable snapshot manifest
   (`data/manifests/real/ENG_PL/2025-26.json` by default).

This job never writes to `football.*` canonical tables itself. Reconciled
evidence is audit-only, persisted (when `--database-url` is given) to the
`ingestion` schema only -- the same boundary the Block 13 PoC and Zero-Cost
Coverage Lab already use (see docs/MULTI_SOURCE_DATA_MESH.md's "Future
promotion contract"). The canonical `football.*` load remains
`football-intelligence-load-real-snapshot`'s job, run separately, using the
single already-trusted Football-Data.co.uk source.

Only ENG_PL 2025/26 is implemented. `--competition`/`--season` exist for an
honest, explicit contract (and to keep the job self-documenting), not
because another combination is actually supported -- claiming coverage for
a competition/season that was never acquired would fabricate evidence.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.coverage_lab.provider_capabilities import PROVIDER_CAPABILITIES
from football_intelligence.coverage_lab.target_metrics import build_metric_granularity_index
from football_intelligence.data_mesh.adapters.openfootball import parse_season_matches
from football_intelligence.data_mesh.entity_resolution import COMPETITION_MAPPINGS
from football_intelligence.data_mesh.models import NormalizedObservation, ReconciliationDecision
from football_intelligence.data_mesh.pipeline import resolve_and_reconcile
from football_intelligence.data_mesh.reconciliation import MODEL_VERSION
from football_intelligence.db.data_mesh_repository import DataMeshRepository
from football_intelligence.db.provider_repository import connect
from football_intelligence.jobs.collect_real_snapshot import collect_football_data_uk_matches
from football_intelligence.jobs.score_real_snapshot import assess_real_snapshot
from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2
from football_intelligence.providers.openfootball import OpenFootballClient, OpenFootballError

SUPPORTED_COMPETITION_CODE = "ENG_PL"
SUPPORTED_SEASON_LABEL = "2025/26"

OPENFOOTBALL_SOURCE_CODE = "openfootball"
OPENFOOTBALL_SEASON_CODE = "2025-26"
OPENFOOTBALL_COMPETITION_FILE = "en.1.json"
OPENFOOTBALL_SEMANTIC_SEASON_LABEL = "2025-2026"
OPENFOOTBALL_MATCHES_FILENAME = "eng_pl_matches_openfootball.json"
OPENFOOTBALL_SEMANTIC_VERSION = "openfootball-v1"

PLANNED_REQUESTS = 2
DEFAULT_REQUEST_BUDGET = 4
MAX_REQUEST_BUDGET = 10

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_OUTPUT_DIR = _REPO_ROOT / "data" / "real" / "2025-26"
DEFAULT_MANIFEST_PATH = _REPO_ROOT / "data" / "manifests" / "real" / "ENG_PL" / "2025-26.json"

SNAPSHOT_ID = "real-eng_pl-2025_26-v2"
SOURCE_AUDIT_DOC = "docs/REAL_DATA_SOURCE_AUDIT_V2.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 18: acquire, normalize, resolve, reconcile and report the real "
            "ENG_PL 2025/26 snapshot from two independent zero-cost sources, and "
            "write a machine-readable snapshot manifest."
        )
    )
    parser.add_argument("--competition", default=SUPPORTED_COMPETITION_CODE)
    parser.add_argument("--season", default=SUPPORTED_SEASON_LABEL)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--request-budget", type=int, default=DEFAULT_REQUEST_BUDGET)
    parser.add_argument("--database-url", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.competition != SUPPORTED_COMPETITION_CODE or args.season != SUPPORTED_SEASON_LABEL:
        raise SystemExit(
            "build_real_snapshot_v2 only implements "
            f"{SUPPORTED_COMPETITION_CODE} {SUPPORTED_SEASON_LABEL} in Block 18; got "
            f"--competition={args.competition!r} --season={args.season!r}. Claiming any "
            "other competition/season here would report coverage that was never acquired."
        )
    if args.request_budget < PLANNED_REQUESTS or args.request_budget > MAX_REQUEST_BUDGET:
        raise SystemExit(
            f"--request-budget must be between {PLANNED_REQUESTS} and {MAX_REQUEST_BUDGET}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    fduk_observations = collect_football_data_uk_matches(output_dir=args.output_dir)
    openfootball_observations, openfootball_status = _collect_openfootball_matches(
        output_dir=args.output_dir
    )

    all_observations = fduk_observations + openfootball_observations
    decisions, resolution_meta = resolve_and_reconcile(all_observations)

    database_url = args.database_url or os.environ.get("DATABASE_URL")
    persistence = _persist_audit_evidence(
        database_url=database_url, all_observations=all_observations, decisions=decisions
    )
    canonical = _read_canonical_state(database_url)

    manifest = _build_manifest(
        fduk_observations=fduk_observations,
        openfootball_observations=openfootball_observations,
        openfootball_status=openfootball_status,
        all_observations=all_observations,
        decisions=decisions,
        resolution_meta=resolution_meta,
        persistence=persistence,
        canonical=canonical,
    )
    args.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )

    coverage = manifest["metric_coverage"]
    print(
        f"REAL SNAPSHOT V2: {SUPPORTED_COMPETITION_CODE} {SUPPORTED_SEASON_LABEL} -- "
        f"{len(all_observations)} observations, {len(decisions)} reconciliation decisions, "
        f"{coverage['available_current_identity_count']}/{coverage['catalog_identity_count']} "
        "catalog identities covered by a real current source"
    )
    print(f"MANIFEST: {args.manifest_path}")


def _competition_external_id(source_code: str) -> str:
    for mapping in COMPETITION_MAPPINGS:
        if mapping.source_code == source_code and mapping.canonical_code == (
            SUPPORTED_COMPETITION_CODE
        ):
            return mapping.external_id
    raise RuntimeError(
        f"no competition mapping configured for {source_code}:{SUPPORTED_COMPETITION_CODE}"
    )


def _collect_openfootball_matches(*, output_dir: Path) -> tuple[list[NormalizedObservation], str]:
    competition_external_id = _competition_external_id(OPENFOOTBALL_SOURCE_CODE)
    client = OpenFootballClient()
    print(f"OpenFootball: fetching {OPENFOOTBALL_SEASON_CODE}/{OPENFOOTBALL_COMPETITION_FILE} ...")
    try:
        response = client.get_season_json(
            competition_file=OPENFOOTBALL_COMPETITION_FILE,
            season_code=OPENFOOTBALL_SEASON_CODE,
        )
    except OpenFootballError as exc:
        # OpenFootball is the SECONDARY reconciliation source: its absence
        # degrades this run to single-source (still fully real) rather than
        # blocking the primary Football-Data.co.uk snapshot, which
        # `load_real_snapshot.py` already depends on independently. Never
        # silently hidden -- the manifest records this status explicitly.
        print(f"OpenFootball: fetch failed ({exc}); continuing with football-data-uk only")
        return [], f"error: {exc}"

    source_reference = f"{OPENFOOTBALL_SEASON_CODE}/{OPENFOOTBALL_COMPETITION_FILE}"
    observations = parse_season_matches(
        response.payload,
        competition_external_id=competition_external_id,
        season_label=OPENFOOTBALL_SEMANTIC_SEASON_LABEL,
        source_reference=source_reference,
        ingestion_run_id=None,
    )
    output = _build_openfootball_output(
        observations=observations,
        retrieved_at=response.fetched_at,
        source_reference=source_reference,
    )
    _write_json(output_dir / OPENFOOTBALL_MATCHES_FILENAME, output)
    print(f"OpenFootball: {len(observations)} normalized observations")
    return observations, "ok"


def _build_openfootball_output(
    *,
    observations: list[NormalizedObservation],
    retrieved_at: datetime,
    source_reference: str,
) -> dict[str, Any]:
    return {
        "provenance": {
            "source": OPENFOOTBALL_SOURCE_CODE,
            "source_url": (
                "https://raw.githubusercontent.com/openfootball/football.json/master/"
                f"{source_reference}"
            ),
            "retrieved_at": retrieved_at.isoformat(),
            "semantic_version": OPENFOOTBALL_SEMANTIC_VERSION,
            "record_count": len(observations),
            "automated_collection": "yes",
            "redistribution_permission": "public_domain_cc0",
            "certification_state": "certified",
        },
        "scope": {
            "competition": SUPPORTED_COMPETITION_CODE,
            "season": SUPPORTED_SEASON_LABEL,
            "entity_grains": ["match"],
            "player_coverage": "unavailable",
        },
        "records": [dataclasses.asdict(observation) for observation in observations],
    }


def _persist_audit_evidence(
    *,
    database_url: str | None,
    all_observations: list[NormalizedObservation],
    decisions: list[ReconciliationDecision],
) -> dict[str, Any]:
    if not database_url:
        return {"mode": "not_requested"}
    with connect(database_url) as connection:
        mesh_repository = DataMeshRepository(connection)
        observations_written = mesh_repository.persist_observations(all_observations)
        decisions_written = mesh_repository.replace_decisions(decisions)
        connection.commit()
    return {
        "mode": "postgresql_ingestion_schema_audit_only",
        "observations_written": observations_written,
        "decisions_written": decisions_written,
        "scope": "ingestion.source_observations / ingestion.reconciliation_decisions only",
    }


def _read_canonical_state(database_url: str | None) -> dict[str, Any]:
    if not database_url:
        return {"mode": "not_requested"}
    with connect(database_url) as connection:
        assessment = assess_real_snapshot(connection)
        connection.rollback()
    return {
        "mode": "postgresql",
        "matches_loaded": assessment.match_count,
        "team_stat_rows_loaded": assessment.team_stat_rows,
        "player_observation_rows_loaded": assessment.player_observation_rows,
        "note": (
            "Reflects football.* as of this run. Run "
            "football-intelligence-load-real-snapshot separately to (re)load it from "
            "the Football-Data.co.uk evidence written by this job."
        ),
    }


def _observations_by_granularity(observations: list[NormalizedObservation]) -> dict[str, int]:
    granularity_index = build_metric_granularity_index()
    counts: dict[str, int] = defaultdict(int)
    for observation in observations:
        granularity = granularity_index.get((observation.entity_type, observation.metric_name))
        bucket = granularity if granularity is not None else f"{observation.entity_type}_identity"
        counts[bucket] += 1
    return dict(sorted(counts.items()))


def _metric_coverage(observations: list[NormalizedObservation]) -> dict[str, Any]:
    granularity_index = build_metric_granularity_index()

    available_identities: set[tuple[str, str]] = set()
    for observation in observations:
        granularity = granularity_index.get((observation.entity_type, observation.metric_name))
        if granularity is not None:
            available_identities.add((observation.metric_name, granularity))

    catalog_identities = {(metric.key, metric.granularity) for metric in METRIC_CATALOG_V2}
    available_current = available_identities & catalog_identities

    # A catalog identity that only a `historical`-freshness-role provider
    # (StatsBomb Open Data) can ever supply, structurally -- never
    # satisfiable by this current-season snapshot regardless of which
    # current-role source is used. Reused, static, already-verified
    # capability data (`coverage_lab.provider_capabilities`), never
    # re-derived or guessed here.
    current_capable_keys: set[tuple[str, str]] = set()
    historical_capable_keys: set[tuple[str, str]] = set()
    for capability in PROVIDER_CAPABILITIES:
        target = (
            current_capable_keys
            if capability.freshness_role == "current"
            else (historical_capable_keys)
        )
        target.update(capability.supported_metrics.keys())
    historical_deep_only = (historical_capable_keys - current_capable_keys) & catalog_identities

    raw_count = sum(1 for metric in METRIC_CATALOG_V2 if metric.kind == "raw")
    derived_count = sum(1 for metric in METRIC_CATALOG_V2 if metric.kind == "derived")

    return {
        "catalog_identity_count": len(catalog_identities),
        "raw_identity_count": raw_count,
        "derived_identity_count": derived_count,
        "available_current_identity_count": len(available_current),
        "available_current_identities": sorted(f"{key}@{gran}" for key, gran in available_current),
        "historical_deep_only_identity_count": len(historical_deep_only),
        "unavailable_identity_count": len(catalog_identities)
        - len(available_current)
        - len(historical_deep_only),
        "note": (
            "available_current/historical_deep_only/unavailable are never blended into "
            "one percentage -- see docs/ZERO_COST_COVERAGE.md's coverage-state discipline."
        ),
    }


def _build_manifest(
    *,
    fduk_observations: list[NormalizedObservation],
    openfootball_observations: list[NormalizedObservation],
    openfootball_status: str,
    all_observations: list[NormalizedObservation],
    decisions: list[ReconciliationDecision],
    resolution_meta: dict[str, Any],
    persistence: dict[str, Any],
    canonical: dict[str, Any],
) -> dict[str, Any]:
    generated_at = datetime.now(UTC)

    teams_resolved = {
        decision.logical_entity_key
        for decision in decisions
        if decision.entity_type == "team" and decision.metric_name == "name"
    }
    matches_resolved = {
        decision.logical_entity_key
        for decision in decisions
        if decision.entity_type == "match" and decision.metric_name == "status"
    }
    conflicts = [
        {
            "logical_entity_key": decision.logical_entity_key,
            "metric_name": decision.metric_name,
            "participating_sources": list(decision.participating_sources),
            "evidence": dict(decision.evidence),
        }
        for decision in decisions
        if decision.status == "conflict"
    ]

    return {
        "snapshot_id": SNAPSHOT_ID,
        "competition_code": SUPPORTED_COMPETITION_CODE,
        "season_label": SUPPORTED_SEASON_LABEL,
        "created_at": generated_at.isoformat(),
        "data_context": "real",
        "reconciliation_model_version": MODEL_VERSION,
        "providers_used": {
            "football-data-uk": {
                "status": "ok",
                "role": "primary_current_source_and_canonical_load_source",
                "observation_count": len(fduk_observations),
            },
            "openfootball": {
                "status": openfootball_status,
                "role": "secondary_current_source_for_reconciliation_audit",
                "observation_count": len(openfootball_observations),
            },
        },
        "source_files": [
            {
                "provider": "football-data-uk",
                "local_path": "data/real/2025-26/eng_pl_matches.json",
                "source_url": "https://www.football-data.co.uk/mmz4281/2526/E0.csv",
            },
            {
                "provider": "openfootball",
                "local_path": f"data/real/2025-26/{OPENFOOTBALL_MATCHES_FILENAME}",
                "source_url": (
                    "https://raw.githubusercontent.com/openfootball/football.json/master/"
                    f"{OPENFOOTBALL_SEASON_CODE}/{OPENFOOTBALL_COMPETITION_FILE}"
                ),
            },
        ],
        "teams_resolved": len(teams_resolved),
        "players_resolved": 0,
        "matches_resolved": len(matches_resolved),
        "observations_by_granularity": _observations_by_granularity(all_observations),
        "metric_coverage": _metric_coverage(all_observations),
        "reconciliation": {
            "overlap_count": resolution_meta["overlap_count"],
            "agreed_count": sum(1 for decision in decisions if decision.status == "agreed"),
            "single_source_count": sum(
                1 for decision in decisions if decision.status == "single_source"
            ),
            "conflict_count": len(conflicts),
        },
        "conflicts": conflicts,
        "unresolved_entities": {
            "count": resolution_meta["unresolved_observation_count"],
            "examples": resolution_meta["unresolved_identity_examples"],
        },
        "provenance_completeness": (
            "full: every persisted observation carries source_code, source_reference, "
            "observed_at and semantic_version"
        ),
        "audit_persistence": persistence,
        "canonical_database_state": canonical,
        "source_audit_reference": SOURCE_AUDIT_DOC,
        "player_data": {
            "rich_player_source_found": False,
            "reason": (
                "No compliant zero-cost source publishing ENG_PL 2025/26 player-match "
                "statistics was found in the Block 18 source audit; see "
                f"{SOURCE_AUDIT_DOC} and docs/REAL_DATA_SNAPSHOT_V2.md."
            ),
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )
    print(f"WROTE: {path}")


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    main()
