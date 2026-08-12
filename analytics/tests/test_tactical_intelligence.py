from __future__ import annotations

from datetime import UTC, datetime, timedelta

from football_intelligence.normalization.api_football import normalize_fixture_bundle
from football_intelligence.tactical_intelligence.engine import (
    calculate_tactical_intelligence,
)
from football_intelligence.tactical_intelligence.models import (
    FormationObservation,
    TeamTacticalInput,
)

NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)


def _input(
    *,
    control: float = 80,
    volume: float = 78,
    defense: float = 72,
    confidence: float = 0.84,
    formations: tuple[str, ...] = ("4-3-3", "4-3-3", "4-3-3", "4-2-3-1"),
) -> TeamTacticalInput:
    observations = tuple(
        FormationObservation(
            match_id=index + 1,
            kickoff_at=NOW - timedelta(days=index),
            formation=formation,
        )
        for index, formation in enumerate(formations)
    )
    return TeamTacticalInput(
        team_id=1,
        team_name="Test FC",
        competition_id=1,
        competition_code="TEST",
        competition_name="Test League",
        season_id=1,
        season_label="2026",
        scope_key="competition:TEST:2026",
        matches=4,
        source_confidence=confidence,
        dimension_scores={
            "control": control,
            "chance_generation": volume,
            "defense": defense,
        },
        formations=observations,
    )


def test_normalization_captures_nominal_formation_without_extra_endpoint() -> None:
    payload = {
        "response": [
            {
                "league": {"id": 39, "season": 2026, "round": "Regular Season - 1"},
                "fixture": {
                    "id": 123,
                    "date": "2026-08-12T18:00:00+00:00",
                    "status": {"short": "FT"},
                    "venue": {"name": "Test"},
                },
                "teams": {
                    "home": {"id": 10, "name": "Home"},
                    "away": {"id": 20, "name": "Away"},
                },
                "goals": {"home": 2, "away": 1},
                "lineups": [
                    {
                        "team": {"id": 10},
                        "formation": "4-3-3",
                        "coach": {"name": "Home Coach"},
                        "startXI": [],
                    },
                    {
                        "team": {"id": 20},
                        "formation": "4-2-3-1",
                        "coach": {"name": "Away Coach"},
                        "startXI": [],
                    },
                ],
                "statistics": [],
                "players": [],
            }
        ]
    }

    batch = normalize_fixture_bundle(payload)

    assert len(batch.team_lineups) == 2
    assert batch.team_lineups[0].formation == "4-3-3"
    assert batch.team_lineups[0].coach_name == "Home Coach"


def test_high_control_and_volume_produce_control_and_volume_profile() -> None:
    snapshot = calculate_tactical_intelligence([_input()], calculated_at=NOW)[0]

    assert snapshot.style_signal == "control_and_volume"
    assert snapshot.defensive_signal == "restrictive_shot_profile"
    assert snapshot.primary_formation == "4-3-3"
    assert snapshot.formation_signal == "stable"
    assert snapshot.formation_share == 0.75


def test_volume_without_control_never_claims_counterattack() -> None:
    snapshot = calculate_tactical_intelligence(
        [_input(control=42, volume=82, defense=52)],
        calculated_at=NOW,
    )[0]

    assert snapshot.style_signal == "volume_without_control"
    assert "no prueba juego de contra" in snapshot.summary


def test_missing_lineups_keeps_style_but_marks_formation_unavailable() -> None:
    snapshot = calculate_tactical_intelligence(
        [_input(formations=())],
        calculated_at=NOW,
    )[0]

    assert snapshot.style_signal == "control_and_volume"
    assert snapshot.primary_formation is None
    assert snapshot.formation_signal == "unavailable"
    assert snapshot.formation_confidence == 0.0
