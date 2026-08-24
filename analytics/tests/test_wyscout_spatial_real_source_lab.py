"""TEMPORARY PR #43 real-source lab gate. Remove before merge."""

from __future__ import annotations

import json
import warnings

from football_intelligence.jobs.audit_wyscout_spatial_metrics import (
    audit_real_wyscout_spatial_metrics,
)


def test_real_wyscout_spatial_metric_lab(tmp_path) -> None:
    report = audit_real_wyscout_spatial_metrics(cache_dir=tmp_path / "wyscout-open")
    compact = {
        "status": report["status"],
        "methodology_version": report["methodology_version"],
        "leagues": [
            {
                key: league[key]
                for key in (
                    "competition_code",
                    "status",
                    "event_count",
                    "passes",
                    "geometry_coverage_pct",
                    "success_tag_coverage_pct",
                    "progressive_passes",
                    "successful_progressive_passes",
                    "passes_into_final_third",
                    "successful_passes_into_final_third",
                    "progressive_and_final_third",
                    "pass_subtypes",
                    "long_pass_diagnostic_buckets",
                )
            }
            for league in report["leagues"]
        ],
    }
    warnings.warn(
        "WYSCOUT_SPATIAL_REAL_SOURCE_REPORT=" + json.dumps(compact, sort_keys=True),
        stacklevel=1,
    )
    assert report["status"] == "PASS"
