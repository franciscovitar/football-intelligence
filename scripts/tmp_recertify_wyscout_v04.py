from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

EXPECTED_COUNT = 416407
EXPECTED_DIGEST = "29b23d96326fb82b94e6529ad951e4c1b3812d0617fff79a5d34d23bc2763eb5"


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def dump(cache_dir: Path, output: Path) -> None:
    from football_intelligence.data_mesh.adapters import wyscout_open
    from football_intelligence.jobs.audit_wyscout_core_leagues import (
        _load_country_payload,
        _load_reference_payload,
    )
    from football_intelligence.providers.wyscout_open_scopes import CORE_LEAGUE_SPECS

    spec = next(spec for spec in CORE_LEAGUE_SPECS if spec.competition_code == "ESP_LL")
    matches = _load_country_payload(cache_dir, spec=spec, kind="matches")
    events = _load_country_payload(cache_dir, spec=spec, kind="events")
    players = _load_reference_payload(cache_dir, "*players.json", label="players.json")
    teams = _load_reference_payload(cache_dir, "*teams.json", label="teams.json")
    observations = wyscout_open.parse_england_season(
        matches_payload=matches,
        events_payload=events,
        players_payload=players,
        teams_payload=teams,
        scope=wyscout_open.ESP_LL_SCOPE,
    )
    versions = sorted({obs.semantic_version for obs in observations})
    canonical: list[dict[str, Any]] = []
    for obs in observations:
        row = asdict(obs)
        row.pop("semantic_version")
        canonical.append(_normalize(row))
    canonical.sort(key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")))
    payload = {
        "semantic_versions": versions,
        "observation_count": len(canonical),
        "long_passes_accurate_count": sum(
            1 for row in canonical if row["metric_name"] == "long_passes_accurate"
        ),
        "passes_into_final_third_count": sum(
            1 for row in canonical if row["metric_name"] == "passes_into_final_third"
        ),
        "observations": canonical,
    }
    output.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"version={versions} observations={len(canonical)} "
        f"long_passes_accurate={payload['long_passes_accurate_count']} "
        f"passes_into_final_third={payload['passes_into_final_third_count']}"
    )


def compare(base_path: Path, head_path: Path, report_path: Path) -> None:
    base = json.loads(base_path.read_text(encoding="utf-8"))
    head = json.loads(head_path.read_text(encoding="utf-8"))

    assert base["semantic_versions"] == ["wyscout-open-v0.3"], base["semantic_versions"]
    assert head["semantic_versions"] == ["wyscout-open-v0.4"], head["semantic_versions"]
    assert base["observation_count"] == EXPECTED_COUNT, base["observation_count"]
    assert head["observation_count"] == EXPECTED_COUNT, head["observation_count"]
    assert head["long_passes_accurate_count"] == 0
    assert head["passes_into_final_third_count"] == 0

    if base["observations"] != head["observations"]:
        for index, (before, after) in enumerate(
            zip(base["observations"], head["observations"], strict=True)
        ):
            if before != after:
                raise AssertionError(
                    f"first v0.3/v0.4 difference at canonical row {index}: "
                    f"before={before!r} after={after!r}"
                )
        raise AssertionError("v0.3/v0.4 observation payloads differ")

    digest = hashlib.sha256(
        json.dumps(base["observations"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert digest == EXPECTED_DIGEST, (digest, EXPECTED_DIGEST)
    report = {
        "status": "PASS",
        "scope": "ESP_LL 2017/18",
        "source": "Wyscout Open Data / Figshare 4415000",
        "baseline_version": "wyscout-open-v0.3",
        "candidate_version": "wyscout-open-v0.4",
        "observation_count": EXPECTED_COUNT,
        "candidate_long_passes_accurate_observations": head["long_passes_accurate_count"],
        "candidate_passes_into_final_third_observations": head[
            "passes_into_final_third_count"
        ],
        "canonical_payload_sha256": digest,
        "equivalence_rule": "all NormalizedObservation fields identical except semantic_version",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    dump_parser = subparsers.add_parser("dump")
    dump_parser.add_argument("cache_dir", type=Path)
    dump_parser.add_argument("output", type=Path)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("base", type=Path)
    compare_parser.add_argument("head", type=Path)
    compare_parser.add_argument("report", type=Path)

    args = parser.parse_args()
    if args.command == "dump":
        dump(args.cache_dir, args.output)
    else:
        compare(args.base, args.head, args.report)


if __name__ == "__main__":
    main()
