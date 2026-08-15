"""Structural invariants for the committed real ENG_PL 2025/26 snapshot files.

Does not assert on specific player names/values (that would be brittle and
would re-litigate football facts in a test file) -- only that the collected
data is structurally real: real provenance, a plausible real-world record
count, no placeholder/synthetic entities, and correct season scoping.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "real" / "2025-26"

_PLACEHOLDER_NAME_FRAGMENTS = ("test player", "home fc", "away fc", "sample team", "placeholder")

pytestmark = pytest.mark.skipif(
    not _DATA_DIR.exists(), reason="real snapshot not collected in this environment"
)


def _load(filename: str) -> dict:
    return json.loads((_DATA_DIR / filename).read_text(encoding="utf-8"))


def test_player_identity_has_real_provenance_and_no_placeholders() -> None:
    payload = _load("eng_pl_player_identity.json")
    provenance = payload["provenance"]
    assert provenance["source"] == "fpl-official-api"
    assert provenance["source_url"].startswith("https://fantasy.premierleague.com/api/")
    assert provenance["record_count"] == len(payload["records"])
    # A real Premier League squad list is materially larger than any smoke fixture.
    assert len(payload["records"]) > 300

    for record in payload["records"]:
        name = record["display_name"].strip().lower()
        assert name, "player identity record must not have a blank name"
        assert not any(fragment in name for fragment in _PLACEHOLDER_NAME_FRAGMENTS)


def test_player_season_stats_are_scoped_to_2025_26_with_real_provenance() -> None:
    payload = _load("eng_pl_player_season_stats.json")
    provenance = payload["provenance"]
    assert provenance["source"] == "fpl-official-api"
    assert provenance["semantic_version"] == "fpl-official-api-v1"
    assert len(payload["records"]) > 300

    for record in payload["records"]:
        assert record["season_label"] == "2025/26"
        assert record["competition_external_id"] == "ENG_PL"
        assert record["source"] == "fpl-official-api"
        assert record["source_url"].startswith("https://fantasy.premierleague.com/api/")
        # Missing is never fabricated as a negative/impossible value.
        if record["minutes"] is not None:
            assert 0 <= record["minutes"] <= 3420  # 38 matches x 90 minutes, the real season cap
        if record["goals"] is not None:
            assert record["goals"] >= 0


def test_matches_cover_a_full_real_premier_league_season_with_no_placeholder_teams() -> None:
    payload = _load("eng_pl_matches.json")
    provenance = payload["provenance"]
    assert provenance["source"] == "football-data-uk"
    assert "mmz4281/2526/E0.csv" in provenance["source_url"]

    match_status_observations = [
        record
        for record in payload["records"]
        if record["entity_type"] == "match" and record["metric_name"] == "status"
    ]
    # A completed real Premier League season is exactly 380 matches (20 teams,
    # double round robin) -- this is a real, checkable invariant, not a guess.
    assert len(match_status_observations) == 380
    assert all(record["value"] == "finished" for record in match_status_observations)

    team_name_observations = [
        record
        for record in payload["records"]
        if record["entity_type"] == "team" and record["metric_name"] == "name"
    ]
    team_names = {record["value"].strip().lower() for record in team_name_observations}
    # A real Premier League season has exactly 20 clubs.
    assert len(team_names) == 20
    assert not any(
        any(fragment in name for fragment in _PLACEHOLDER_NAME_FRAGMENTS) for name in team_names
    )
