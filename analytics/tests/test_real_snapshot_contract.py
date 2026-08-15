"""Structural invariants for the committed real ENG_PL match/team snapshot."""

from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "real" / "2025-26"
_PLACEHOLDER_NAME_FRAGMENTS = ("test player", "home fc", "away fc", "sample team")


def _load(filename: str) -> dict:
    return json.loads((_DATA_DIR / filename).read_text(encoding="utf-8"))


def test_no_unpermitted_domestic_player_snapshot_is_committed() -> None:
    assert not (_DATA_DIR / "eng_pl_player_identity.json").exists()
    assert not (_DATA_DIR / "eng_pl_player_season_stats.json").exists()


def test_matches_cover_a_full_real_premier_league_season() -> None:
    payload = _load("eng_pl_matches.json")
    provenance = payload["provenance"]
    assert provenance["source"] == "football-data-uk"
    assert "mmz4281/2526/E0.csv" in provenance["source_url"]

    statuses = [
        record
        for record in payload["records"]
        if record["entity_type"] == "match" and record["metric_name"] == "status"
    ]
    assert len(statuses) == 380
    assert all(record["value"] == "finished" for record in statuses)

    team_names = {
        record["value"].strip().lower()
        for record in payload["records"]
        if record["entity_type"] == "team" and record["metric_name"] == "name"
    }
    assert len(team_names) == 20
    assert not any(
        fragment in name for name in team_names for fragment in _PLACEHOLDER_NAME_FRAGMENTS
    )


def test_wc2022_rich_data_is_explicitly_validation_only_and_never_eng_pl() -> None:
    validation_path = (
        _DATA_DIR.parents[1] / "validation" / "wc2022" / "wc2022_validation_sample.json"
    )
    payload = json.loads(validation_path.read_text(encoding="utf-8"))
    assert payload["provenance"]["source"] == "statsbomb-open"
    assert payload["provenance"]["competition_name"] == "FIFA World Cup"
    assert payload["provenance"]["total_matches_published"] == 64
    assert payload["provenance"]["certification_state"] == "validation_only"
    assert "not any core domestic league" in payload["warning"]
