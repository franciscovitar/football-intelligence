from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.wyscout_open import SEMANTIC_VERSION, parse_england_season
from football_intelligence.jobs.wyscout_historical_scope import load_scope_inputs, scope_config

SPATIAL_METRICS = frozenset({"long_passes_accurate", "passes_into_final_third"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("baseline", "candidate"))
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    return parser


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported canonical payload value: {type(value)!r}")


def _canonical_digest(observations: list[Any]) -> str:
    row_hashes: list[bytes] = []
    for observation in observations:
        payload = dataclasses.asdict(observation)
        payload.pop("semantic_version", None)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=_json_default,
        ).encode("utf-8")
        row_hashes.append(hashlib.sha256(encoded).digest())
    row_hashes.sort()
    digest = hashlib.sha256()
    for row_hash in row_hashes:
        digest.update(row_hash)
    return digest.hexdigest()


def _load_esp(cache_dir: Path) -> list[Any]:
    config = scope_config("ESP_LL")
    matches, events, players, teams = load_scope_inputs(cache_dir, config=config)
    return parse_england_season(
        matches_payload=matches,
        events_payload=events,
        players_payload=players,
        teams_payload=teams,
        scope=config.scope,
    )


def main() -> None:
    args = build_parser().parse_args()
    observations = _load_esp(args.cache_dir)
    metric_counts = Counter(observation.metric_name for observation in observations)
    versions = sorted({observation.semantic_version for observation in observations})

    if args.phase == "baseline":
        if SEMANTIC_VERSION != "wyscout-open-v0.4" or versions != ["wyscout-open-v0.4"]:
            raise SystemExit(f"unexpected baseline versions: module={SEMANTIC_VERSION}, rows={versions}")
        spatial_counts = {metric: metric_counts.get(metric, 0) for metric in sorted(SPATIAL_METRICS)}
        if any(spatial_counts.values()):
            raise SystemExit(f"baseline unexpectedly emits spatial metrics in ESP_LL: {spatial_counts}")
        state = {
            "semantic_version": SEMANTIC_VERSION,
            "observation_count": len(observations),
            "canonical_digest_without_semantic_version": _canonical_digest(observations),
            "spatial_metric_counts": spatial_counts,
        }
        args.state.parent.mkdir(parents=True, exist_ok=True)
        args.state.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(state, sort_keys=True))
        return

    if args.report is None:
        raise SystemExit("--report is required for candidate phase")
    if SEMANTIC_VERSION != "wyscout-open-v0.5" or versions != ["wyscout-open-v0.5"]:
        raise SystemExit(f"unexpected candidate versions: module={SEMANTIC_VERSION}, rows={versions}")

    baseline = json.loads(args.state.read_text(encoding="utf-8"))
    non_spatial = [observation for observation in observations if observation.metric_name not in SPATIAL_METRICS]
    candidate_digest = _canonical_digest(non_spatial)
    spatial_counts = {metric: metric_counts.get(metric, 0) for metric in sorted(SPATIAL_METRICS)}

    failures: list[str] = []
    if len(non_spatial) != int(baseline["observation_count"]):
        failures.append(
            f"non-spatial count changed: {len(non_spatial)} != {baseline['observation_count']}"
        )
    if candidate_digest != baseline["canonical_digest_without_semantic_version"]:
        failures.append("non-spatial canonical payload digest changed")
    if any(count <= 0 for count in spatial_counts.values()):
        failures.append(f"candidate did not emit both spatial metrics: {spatial_counts}")
    expected_total = int(baseline["observation_count"]) + sum(spatial_counts.values())
    if len(observations) != expected_total:
        failures.append(f"candidate total {len(observations)} != expected {expected_total}")

    report = {
        "status": "FAIL" if failures else "PASS",
        "scope": "ESP_LL 2017/18",
        "baseline_semantic_version": baseline["semantic_version"],
        "candidate_semantic_version": SEMANTIC_VERSION,
        "baseline_observations": baseline["observation_count"],
        "candidate_observations": len(observations),
        "candidate_non_spatial_observations": len(non_spatial),
        "non_spatial_payload_digest_baseline": baseline[
            "canonical_digest_without_semantic_version"
        ],
        "non_spatial_payload_digest_candidate": candidate_digest,
        "new_spatial_metric_counts": spatial_counts,
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    if failures:
        raise SystemExit("WYSCOUT v0.5 ESP RECERTIFICATION: FAIL")
    print("WYSCOUT v0.5 ESP RECERTIFICATION: PASS")


if __name__ == "__main__":
    main()
