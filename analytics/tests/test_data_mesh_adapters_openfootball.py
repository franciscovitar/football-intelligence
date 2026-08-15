from __future__ import annotations

from football_intelligence.data_mesh.adapters.openfootball import parse_season_matches

_COMMON_KWARGS = {
    "competition_external_id": "en.1.json",
    "season_label": "2025-2026",
    "source_reference": "2025-26/en.1.json",
    "ingestion_run_id": None,
}


def test_dict_score_form_yields_full_time_goals() -> None:
    payload = {
        "matches": [
            {
                "round": "Matchday 1",
                "date": "2025-08-15",
                "team1": "Liverpool FC",
                "team2": "AFC Bournemouth",
                "score": {"ft": [4, 2], "ht": [1, 0]},
            }
        ]
    }
    observations = parse_season_matches(payload, **_COMMON_KWARGS)
    scores = {obs.metric_name: obs.value for obs in observations if obs.entity_type == "match"}
    assert scores["home_score"] == 4
    assert scores["away_score"] == 2
    assert scores["status"] == "finished"


def test_bare_list_score_form_yields_full_time_goals() -> None:
    # Verified live: ~30 of 380 real 2025/26 matches report a bare
    # `[home, away]` array instead of the `{"ft": ..., "ht": ...}` object --
    # both forms carry the same full-time result and must parse identically.
    payload = {
        "matches": [
            {
                "round": "Matchday 1",
                "date": "2025-08-16",
                "team1": "Aston Villa FC",
                "team2": "Newcastle United FC",
                "score": [0, 0],
            }
        ]
    }
    observations = parse_season_matches(payload, **_COMMON_KWARGS)
    scores = {obs.metric_name: obs.value for obs in observations if obs.entity_type == "match"}
    assert scores["home_score"] == 0
    assert scores["away_score"] == 0
    assert scores["status"] == "finished"


def test_missing_score_is_missing_not_fabricated() -> None:
    # A fixture with no score at all (not yet played) must never be treated
    # as finished or as a fabricated 0-0 -- team identity is still real
    # evidence, but no match-result observation is produced.
    payload = {
        "matches": [
            {
                "round": "Matchday 38",
                "date": "2026-05-24",
                "team1": "Arsenal FC",
                "team2": "Everton FC",
            }
        ]
    }
    observations = parse_season_matches(payload, **_COMMON_KWARGS)
    assert all(obs.entity_type == "team" for obs in observations)
    assert len(observations) == 2


def test_match_missing_team_or_date_is_skipped_entirely() -> None:
    payload = {
        "matches": [
            {"round": "Matchday 1", "date": "2025-08-15", "team1": "Liverpool FC"},
            {"round": "Matchday 1", "team1": "Liverpool FC", "team2": "AFC Bournemouth"},
        ]
    }
    observations = parse_season_matches(payload, **_COMMON_KWARGS)
    assert observations == []


def test_non_dict_match_entries_are_skipped() -> None:
    payload = {"matches": ["not-a-match", 42, None]}
    observations = parse_season_matches(payload, **_COMMON_KWARGS)
    assert observations == []


def test_malformed_payload_shape_yields_no_observations() -> None:
    assert parse_season_matches({"name": "no matches key"}, **_COMMON_KWARGS) == []


def test_team_observations_carry_full_provenance() -> None:
    payload = {
        "matches": [
            {
                "date": "2025-08-15",
                "team1": "Liverpool FC",
                "team2": "AFC Bournemouth",
                "score": {"ft": [4, 2]},
            }
        ]
    }
    observations = parse_season_matches(payload, **_COMMON_KWARGS)
    for observation in observations:
        assert observation.source_code == "openfootball"
        assert observation.source_type == "objective_structured"
        assert observation.semantic_version == "openfootball-v1"
        assert observation.source_reference == "2025-26/en.1.json"
