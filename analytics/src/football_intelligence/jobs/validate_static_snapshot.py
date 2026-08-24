"""Validate provenance metadata and cached bytes for one static source snapshot."""

from __future__ import annotations

import argparse
import dataclasses
import json
from pathlib import Path

from football_intelligence.ingestion.static_snapshot import (
    StaticSnapshotManifestError,
    load_static_snapshot_manifest,
    verify_static_snapshot_files,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a static source snapshot manifest and cached file checksums."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Directory containing manifest file paths. Defaults to the manifest directory.",
    )
    parser.add_argument("--report", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    base_dir = args.base_dir if args.base_dir is not None else args.manifest.parent
    try:
        manifest = load_static_snapshot_manifest(args.manifest)
    except (OSError, json.JSONDecodeError, StaticSnapshotManifestError) as exc:
        raise SystemExit(f"STATIC SNAPSHOT: FAIL manifest - {exc}") from exc

    verification = verify_static_snapshot_files(manifest, base_dir=base_dir)
    payload = {
        "status": "PASS" if verification.passed else "FAIL",
        "snapshot_id": manifest.snapshot_id,
        "source_code": manifest.source_code,
        "source_reference": manifest.source_reference,
        "acquired_at": manifest.acquired_at.isoformat(),
        "competition_codes": list(manifest.competition_codes),
        "season_labels": list(manifest.season_labels),
        "data_grains": list(manifest.data_grains),
        "files": [dataclasses.asdict(file) for file in verification.files],
    }

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not verification.passed:
        failed = [file.path for file in verification.files if not file.passed]
        raise SystemExit("STATIC SNAPSHOT: FAIL files - " + ", ".join(failed))

    print(
        "STATIC SNAPSHOT: PASS "
        f"({manifest.source_code} / {manifest.snapshot_id}, {len(verification.files)} files)"
    )
    if args.report is not None:
        print(f"REPORT: {args.report}")


if __name__ == "__main__":
    main()
