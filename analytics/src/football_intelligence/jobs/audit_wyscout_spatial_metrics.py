"""Read-only real-source audit for candidate Wyscout spatial player metrics.

Downloads the official Wyscout Open Events archive from Figshare (or reuses the
local cache), validates the five certified European 2017/18 country payloads by
event count, and reports aggregate spatial-pass diagnostics.  It never writes to
a database and never persists raw event rows in the report.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from football_intelligence.providers.wyscout_open import (
    WyscoutOpenDataClient,
    safe_extract_zip,
)
from football_intelligence.providers.wyscout_spatial_metrics import (
    METHODOLOGY_VERSION,
    classify_progressive_pass,
    is_pass_into_final_third,
    long_pass_diagnostic_bucket,
    parse_pass_geometry,
    pass_success,
)

FIGSHARE_COLLECTION_ID = 4415000
EVENTS_ARTICLE_TITLE = "Events"
COLLECTION_DOI = "10.6084/m9.figshare.c.4415000.v5"
LICENCE = "CC BY 4.0"


@dataclass(frozen=True, slots=True)
class LeagueSpec:
    competition_code: str
    country_label: str
    expected_events: int


SPECS: tuple[LeagueSpec, ...] = (
    LeagueSpec("ENG_PL", "England", 643150),
    LeagueSpec("ESP_LL", "Spain", 628659),
    LeagueSpec("ITA_SA", "Italy", 647372),
    LeagueSpec("GER_BL1", "Germany", 519407),
    LeagueSpec("FRA_L1", "France", 632807),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Wyscout spatial pass metrics")
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = audit_real_wyscout_spatial_metrics(cache_dir=args.cache_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if report["status"] != "PASS":
        raise SystemExit("WYSCOUT SPATIAL AUDIT: FAIL")
    print("WYSCOUT SPATIAL AUDIT: PASS")
    print(f"REPORT: {args.report}")


def audit_real_wyscout_spatial_metrics(*, cache_dir: Path) -> dict[str, Any]:
    client = WyscoutOpenDataClient()
    asset = client.fetch_asset(
        collection_id=FIGSHARE_COLLECTION_ID,
        article_title=EVENTS_ARTICLE_TITLE,
        cache_dir=cache_dir,
    )
    extracted_dir = cache_dir / "extracted" / asset.local_path.stem
    files = _ensure_extracted(asset.local_path, extracted_dir)
    by_name = {path.name: path for path in files}

    leagues: list[dict[str, Any]] = []
    for spec in SPECS:
        file_name = f"events_{spec.country_label}.json"
        source_path = by_name.get(file_name)
        if source_path is None:
            leagues.append(
                {
                    "competition_code": spec.competition_code,
                    "country_label": spec.country_label,
                    "status": "FAIL",
                    "reason": f"missing {file_name}",
                }
            )
            continue
        with source_path.open("rb") as handle:
            payload = json.load(handle)
        if not isinstance(payload, list):
            leagues.append(
                {
                    "competition_code": spec.competition_code,
                    "country_label": spec.country_label,
                    "status": "FAIL",
                    "reason": "events payload root is not a list",
                }
            )
            continue
        leagues.append(_audit_league(spec, payload))
        del payload

    passed = all(item.get("status") == "PASS" for item in leagues)
    return {
        "status": "PASS" if passed else "FAIL",
        "source": {
            "provider": "wyscout-open",
            "figshare_collection_id": FIGSHARE_COLLECTION_ID,
            "collection_doi": COLLECTION_DOI,
            "licence": LICENCE,
            "article": EVENTS_ARTICLE_TITLE,
            "file_id": asset.file_id,
            "source_checksum": asset.source_checksum,
            "checksum_verified": asset.checksum_verified,
        },
        "methodology_version": METHODOLOGY_VERSION,
        "scope": "five European Wyscout Open domestic leagues, 2017/18",
        "raw_events_persisted_in_report": False,
        "leagues": leagues,
    }


def _ensure_extracted(archive: Path, destination: Path) -> list[Path]:
    if destination.exists():
        cached = [path for path in destination.rglob("events_*.json") if path.is_file()]
        if cached:
            return cached
    return [path for path in safe_extract_zip(archive, destination) if path.is_file()]


def _audit_league(spec: LeagueSpec, events: list[Any]) -> dict[str, Any]:
    pass_count = 0
    valid_geometry = 0
    invalid_geometry = 0
    valid_success_tag = 0
    ambiguous_success_tag = 0
    progressive_count = 0
    progressive_success = 0
    final_third_count = 0
    final_third_success = 0
    progressive_and_final_third = 0
    progressive_zones: Counter[str] = Counter()
    pass_subtypes: Counter[str] = Counter()
    long_buckets: Counter[str] = Counter()

    for event in events:
        if not isinstance(event, dict) or event.get("eventName") != "Pass":
            continue
        pass_count += 1
        subtype = event.get("subEventName")
        pass_subtypes[str(subtype) if isinstance(subtype, str) and subtype else "<missing>"] += 1

        geometry = parse_pass_geometry(event)
        if geometry is None:
            invalid_geometry += 1
            continue
        valid_geometry += 1

        success = pass_success(event)
        if success is None:
            ambiguous_success_tag += 1
        else:
            valid_success_tag += 1

        progressive = classify_progressive_pass(event)
        into_final_third = is_pass_into_final_third(event)
        if progressive is None or into_final_third is None:
            continue
        progressive_zones[progressive.zone] += 1
        if progressive.progressive:
            progressive_count += 1
            if success is True:
                progressive_success += 1
        if into_final_third:
            final_third_count += 1
            if success is True:
                final_third_success += 1
        if progressive.progressive and into_final_third:
            progressive_and_final_third += 1

        bucket = long_pass_diagnostic_bucket(event)
        if bucket is not None:
            long_buckets[bucket] += 1

    event_count_ok = len(events) == spec.expected_events
    geometry_share = valid_geometry / pass_count if pass_count else 0.0
    success_share = valid_success_tag / pass_count if pass_count else 0.0
    # These are conservative structural gates, not football-performance targets.
    structural_ok = pass_count > 0 and geometry_share >= 0.99 and success_share >= 0.99
    return {
        "competition_code": spec.competition_code,
        "country_label": spec.country_label,
        "status": "PASS" if event_count_ok and structural_ok else "FAIL",
        "event_count": len(events),
        "expected_event_count": spec.expected_events,
        "event_count_verified": event_count_ok,
        "passes": pass_count,
        "valid_two_position_passes": valid_geometry,
        "invalid_pass_geometry": invalid_geometry,
        "geometry_coverage_pct": round(100.0 * geometry_share, 4),
        "valid_success_tag_passes": valid_success_tag,
        "ambiguous_success_tag_passes": ambiguous_success_tag,
        "success_tag_coverage_pct": round(100.0 * success_share, 4),
        "progressive_passes": progressive_count,
        "successful_progressive_passes": progressive_success,
        "passes_into_final_third": final_third_count,
        "successful_passes_into_final_third": final_third_success,
        "progressive_and_final_third": progressive_and_final_third,
        "progressive_zone_population": dict(sorted(progressive_zones.items())),
        "pass_subtypes": dict(sorted(pass_subtypes.items())),
        "long_pass_diagnostic_buckets": dict(sorted(long_buckets.items())),
        "spec": asdict(spec),
    }


if __name__ == "__main__":
    main()
