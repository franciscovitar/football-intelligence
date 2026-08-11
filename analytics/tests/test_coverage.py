from __future__ import annotations

import json
from pathlib import Path

from football_intelligence.data_quality.coverage import build_normalized_coverage
from football_intelligence.normalization.api_football import normalize_fixture_bundle


def test_coverage_distinguishes_zero_from_missing() -> None:
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "api_football_fixture_bundle.json").read_text(
            encoding="utf-8"
        )
    )
    batch = normalize_fixture_bundle(payload)

    report = build_normalized_coverage(
        team_stats=batch.team_match_stats,
        player_stats=batch.player_match_stats,
    )

    player = report["player_match_stats"]
    assert player["passes_total"]["availability"] == "available"
    assert player["passes_accurate"]["availability"] == "unavailable"
    assert player["clearances"]["availability"] == "unavailable"
    assert player["red_cards"]["availability"] == "available"
    assert player["red_cards"]["non_null_count"] == 2
