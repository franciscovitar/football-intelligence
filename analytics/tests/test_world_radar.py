from __future__ import annotations

import pytest

from football_intelligence.config.world_radar_competitions import parse_radar_competitions
from football_intelligence.jobs.sync_world_radar import (
    REQUESTS_PER_COMPETITION,
    check_request_budget,
)
from football_intelligence.world_radar.engine import (
    ATTACKER_WEIGHTS,
    MIDFIELDER_WEIGHTS,
    calculate_metrics,
    calculate_world_radar,
    classify_profile,
    merge_feed_entries,
)
from football_intelligence.world_radar.models import PlayerRadarCandidate, RawPlayerFeedEntry
from football_intelligence.world_radar.parser import find_league_matches, parse_player_feed


def _entry(**overrides: object) -> RawPlayerFeedEntry:
    defaults: dict[str, object] = {
        "provider_player_id": "1",
        "player_name": "Player One",
        "team_name": "Team A",
        "position": "Attacker",
        "age": 24,
        "nationality": "NL",
        "appearances": 10,
        "minutes": 900,
        "goals": 9,
        "assists": 3,
        "shots_total": 30,
        "shots_on_target": 15,
        "key_passes": 12,
        "dribbles_successful": 10,
        "source_list": "topscorers",
    }
    defaults.update(overrides)
    return RawPlayerFeedEntry(**defaults)  # type: ignore[arg-type]


def test_weights_sum_to_one() -> None:
    assert abs(sum(ATTACKER_WEIGHTS.values()) - 1.0) < 1e-9
    assert abs(sum(MIDFIELDER_WEIGHTS.values()) - 1.0) < 1e-9


def test_classify_profile_uses_position_text() -> None:
    assert classify_profile("Midfielder") == "midfielder"
    assert classify_profile("Attacker") == "attacker"
    assert classify_profile(None) == "attacker"


def test_merge_feed_entries_processes_each_player_once() -> None:
    scorer = _entry(provider_player_id="7", source_list="topscorers", assists=None)
    assist = _entry(provider_player_id="7", source_list="topassists", goals=None, assists=5)

    merged = merge_feed_entries([scorer, assist])

    assert len(merged) == 1
    candidate = merged[0]
    assert candidate.source_lists == ("topassists", "topscorers")
    # Missing fields are filled from whichever feed carried them.
    assert candidate.goals == 9
    assert candidate.assists == 5


def test_per90_metrics_require_positive_minutes() -> None:
    candidate = PlayerRadarCandidate(
        provider_player_id="1",
        player_name="Zero Minutes",
        team_name=None,
        position="Attacker",
        appearances=1,
        minutes=0,
        goals=1,
        assists=0,
        shots_total=1,
        shots_on_target=1,
        key_passes=0,
        dribbles_successful=0,
        source_lists=("topscorers",),
    )
    metrics = calculate_metrics(candidate)
    assert all(value is None for value in metrics.values())


def test_per90_metrics_correct_for_positive_minutes() -> None:
    candidate = PlayerRadarCandidate(
        provider_player_id="1",
        player_name="Ninety Minutes",
        team_name=None,
        position="Attacker",
        appearances=1,
        minutes=450,
        goals=5,
        assists=None,
        shots_total=10,
        shots_on_target=5,
        key_passes=2,
        dribbles_successful=1,
        source_lists=("topscorers",),
    )
    metrics = calculate_metrics(candidate)
    assert metrics["goals_per90"] == pytest.approx(1.0)
    assert metrics["shots_on_target_per90"] == pytest.approx(1.0)
    assert metrics["assists_per90"] is None  # missing stays missing, never coerced to 0


def test_calculate_world_radar_scores_are_league_relative_and_bounded() -> None:
    candidates = [
        PlayerRadarCandidate(
            provider_player_id=str(i),
            player_name=f"Player {i}",
            team_name="Team",
            position="Attacker",
            appearances=10,
            minutes=900,
            goals=goals,
            assists=1,
            shots_total=10,
            shots_on_target=5,
            key_passes=3,
            dribbles_successful=2,
            source_lists=("topscorers",),
        )
        for i, goals in enumerate([1, 5, 10], start=1)
    ]

    snapshots = calculate_world_radar(
        candidates,
        provider_code="api-football",
        competition_code="NED_ED",
        competition_name="Eredivisie",
        country="Netherlands",
        season_label="2024",
    )

    assert len(snapshots) == 3
    for snapshot in snapshots:
        assert 0.0 <= snapshot.radar_score <= 100.0
        assert 0.0 <= snapshot.confidence <= 1.0
    # The top scorer within this competition should rank highest.
    best = max(snapshots, key=lambda item: item.radar_score)
    assert best.goals == 10


def test_calculate_world_radar_excludes_zero_minutes_candidates() -> None:
    candidates = [
        PlayerRadarCandidate(
            provider_player_id="1",
            player_name="No Minutes",
            team_name=None,
            position="Attacker",
            appearances=0,
            minutes=None,
            goals=None,
            assists=None,
            shots_total=None,
            shots_on_target=None,
            key_passes=None,
            dribbles_successful=None,
            source_lists=("topscorers",),
        )
    ]
    snapshots = calculate_world_radar(
        candidates,
        provider_code="api-football",
        competition_code="NED_ED",
        competition_name="Eredivisie",
        country="Netherlands",
        season_label="2024",
    )
    assert snapshots == ()


def test_confidence_increases_with_minutes_and_appearances() -> None:
    low = PlayerRadarCandidate(
        provider_player_id="1",
        player_name="Low Sample",
        team_name=None,
        position="Attacker",
        appearances=1,
        minutes=90,
        goals=1,
        assists=0,
        shots_total=2,
        shots_on_target=1,
        key_passes=0,
        dribbles_successful=0,
        source_lists=("topscorers",),
    )
    high = PlayerRadarCandidate(
        provider_player_id="2",
        player_name="High Sample",
        team_name=None,
        position="Attacker",
        appearances=14,
        minutes=1200,
        goals=1,
        assists=0,
        shots_total=2,
        shots_on_target=1,
        key_passes=0,
        dribbles_successful=0,
        source_lists=("topscorers", "topassists"),
    )
    low_snapshot, high_snapshot = calculate_world_radar(
        [low, high],
        provider_code="api-football",
        competition_code="NED_ED",
        competition_name="Eredivisie",
        country="Netherlands",
        season_label="2024",
    )
    assert high_snapshot.confidence > low_snapshot.confidence


def test_find_league_matches_requires_unambiguous_name_and_country() -> None:
    payload = {
        "response": [
            {"league": {"id": 88, "name": "Eredivisie"}, "country": {"name": "Netherlands"}},
            {"league": {"id": 99, "name": "Eredivisie"}, "country": {"name": "Belgium"}},
        ]
    }
    assert find_league_matches(payload, name="Eredivisie", country="Netherlands") == [88]
    assert find_league_matches(payload, name="Eredivisie", country="Portugal") == []


def test_find_league_matches_rejects_ambiguous_duplicates() -> None:
    payload = {
        "response": [
            {"league": {"id": 1, "name": "Serie A"}, "country": {"name": "Brazil"}},
            {"league": {"id": 2, "name": "Serie A"}, "country": {"name": "Brazil"}},
        ]
    }
    assert find_league_matches(payload, name="Serie A", country="Brazil") == [1, 2]


def test_parse_player_feed_extracts_expected_fields() -> None:
    payload = {
        "response": [
            {
                "player": {"id": 42, "name": "Jane Doe", "age": 27, "nationality": "BR"},
                "statistics": [
                    {
                        "team": {"name": "FC Sample"},
                        "games": {"appearences": 12, "minutes": 1000, "position": "Attacker"},
                        "goals": {"total": 8, "assists": 4},
                        "shots": {"total": 20, "on": 10},
                        "passes": {"key": 15},
                        "dribbles": {"success": 6},
                    }
                ],
            }
        ]
    }
    entries = parse_player_feed(payload, source_list="topscorers")
    assert len(entries) == 1
    entry = entries[0]
    assert entry.provider_player_id == "42"
    assert entry.minutes == 1000
    assert entry.goals == 8
    assert entry.assists == 4
    assert entry.shots_on_target == 10
    assert entry.key_passes == 15
    assert entry.dribbles_successful == 6


def test_parse_player_feed_skips_entries_without_statistics() -> None:
    payload = {"response": [{"player": {"id": 1, "name": "No Stats"}, "statistics": []}]}
    assert parse_player_feed(payload, source_list="topscorers") == []


def test_check_request_budget_rejects_overspend_before_network() -> None:
    with pytest.raises(SystemExit):
        check_request_budget(5, 12)  # 5 competitions * 3 requests = 15 > 12


def test_check_request_budget_accepts_within_budget() -> None:
    assert check_request_budget(4, 12) == 4 * REQUESTS_PER_COMPETITION


def test_parse_radar_competitions_requires_exact_schema() -> None:
    with pytest.raises(ValueError):
        parse_radar_competitions([{"code": "NED_ED", "name": "Eredivisie"}])  # missing country

    with pytest.raises(ValueError):
        parse_radar_competitions(
            [{"code": "ned_ed", "name": "Eredivisie", "country": "Netherlands"}]
        )  # lowercase code

    with pytest.raises(ValueError):
        parse_radar_competitions(
            [
                {"code": "NED_ED", "name": "Eredivisie", "country": "Netherlands"},
                {"code": "NED_ED", "name": "Duplicate", "country": "Netherlands"},
            ]
        )  # duplicate code

    with pytest.raises(ValueError):
        parse_radar_competitions(
            [{"code": "NED_ED", "name": "Eredivisie", "country": "Netherlands", "url": "https://x"}]
        )  # extra key not allowed

    competitions = parse_radar_competitions(
        [{"code": "NED_ED", "name": "Eredivisie", "country": "Netherlands"}]
    )
    assert competitions[0].code == "NED_ED"


def test_world_radar_never_produces_football_player_link() -> None:
    """World Radar snapshots must never carry an internal football.players id."""

    candidate = PlayerRadarCandidate(
        provider_player_id="1",
        player_name="External Candidate",
        team_name="Team",
        position="Attacker",
        appearances=10,
        minutes=900,
        goals=5,
        assists=1,
        shots_total=10,
        shots_on_target=5,
        key_passes=3,
        dribbles_successful=2,
        source_lists=("topscorers",),
    )
    snapshot = calculate_world_radar(
        [candidate],
        provider_code="api-football",
        competition_code="NED_ED",
        competition_name="Eredivisie",
        country="Netherlands",
        season_label="2024",
    )[0]
    assert not hasattr(snapshot, "player_id")
