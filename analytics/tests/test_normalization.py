from __future__ import annotations

import json
from pathlib import Path

from football_intelligence.normalization.api_football import normalize_fixture_bundle


def _fixture() -> dict[str, object]:
    path = Path(__file__).parent / "fixtures" / "api_football_fixture_bundle.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_normalizes_fixture_bundle_without_inventing_missing_metrics() -> None:
    batch = normalize_fixture_bundle(_fixture())

    assert batch.provider_competition_id == "39"
    assert batch.season_label == "2025"
    assert len(batch.matches) == 1
    assert len(batch.teams) == 2
    assert len(batch.players) == 2
    assert len(batch.team_match_stats) == 2
    assert len(batch.player_match_stats) == 2

    home_stats = next(stats for stats in batch.team_match_stats if stats.team_external_id == "10")
    assert home_stats.possession_pct == 58.0
    assert home_stats.red_cards == 0

    striker = next(stats for stats in batch.player_match_stats if stats.player_external_id == "101")
    assert striker.goals == 2
    assert striker.passes_total == 25
    assert striker.passes_accurate is None
    assert striker.clearances is None

    keeper = next(stats for stats in batch.player_match_stats if stats.player_external_id == "201")
    assert keeper.shots_total == 0
    assert keeper.saves == 4


def test_maps_finished_fixture_status() -> None:
    batch = normalize_fixture_bundle(_fixture())
    assert batch.matches[0].status == "finished"
    assert batch.matches[0].home_score == 2
    assert batch.matches[0].away_score == 0
