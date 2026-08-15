from __future__ import annotations

from datetime import UTC, datetime

from football_intelligence.diagnostics.orchestrator import evaluate_team_diagnostics
from football_intelligence.jobs.execute_real_intelligence_v2 import (
    build_team_diagnostic_inputs_v2,
)
from football_intelligence.team_analytics.engine_v2 import calculate_team_analytics_v2
from football_intelligence.team_analytics.models import TeamObservation

_NOW = datetime(2026, 8, 15, tzinfo=UTC)


def _team_observation(
    team_id: int,
    stats: dict[str, float | None],
    *,
    match_id: int,
    goals_for: int = 1,
    goals_against: int = 1,
) -> TeamObservation:
    return TeamObservation(
        competition_id=1,
        competition_code="ENG_PL",
        competition_name="Premier League",
        season_id=1,
        season_label="2025/26",
        team_id=team_id,
        team_name=f"Team {team_id}",
        opponent_team_id=3 - team_id,
        match_id=match_id,
        kickoff_at=_NOW,
        is_home=team_id == 1,
        goals_for=goals_for,
        goals_against=goals_against,
        stats=stats,
    )


def test_build_team_diagnostic_inputs_v2_never_carries_a_v1_score() -> None:
    observations = [
        _team_observation(1, {"shots_total_against": 20.0}, match_id=1),
        _team_observation(2, {"shots_total_against": 5.0}, match_id=2),
    ]
    result = calculate_team_analytics_v2(observations, scope_key="competition:test-bridge")
    inputs = build_team_diagnostic_inputs_v2(result)

    assert inputs
    assert all(item.score is None for item in inputs)
    assert all(item.comparison_group == "competition:test-bridge" for item in inputs)


def test_few_but_high_quality_chances_allowed_fires_from_real_shots_evidence() -> None:
    """Real ENG_PL 2025/26 evidence shape: `shots_total`/`shots_on_target` are
    real (the 9 recent-completed catalog identities), `xg`/`xga` are not.
    Team 1 concedes few shots overall but the ones it concedes are mostly on
    target (dangerous); Team 2 concedes many shots but few on target
    (harmless). Both diagnostics should be reachable from this real-shaped
    evidence via the shots-on-target-against fallback proxy, with no xG.
    """

    observations = [
        _team_observation(
            1, {"shots_total_against": 5.0, "shots_on_target_against": 4.0}, match_id=1
        ),
        _team_observation(
            2, {"shots_total_against": 20.0, "shots_on_target_against": 2.0}, match_id=2
        ),
    ]
    result = calculate_team_analytics_v2(observations, scope_key="competition:test-proxy")
    season_inputs = {
        item.team_id: item
        for item in build_team_diagnostic_inputs_v2(result)
        if item.window == "season"
    }
    assert set(season_inputs) == {1, 2}
    # Sanity: no xG evidence at all in this real-shaped fixture.
    assert all(item.xga_percentile is None for item in season_inputs.values())

    findings_by_team = {
        team_id: {
            finding.diagnostic_code for finding in evaluate_team_diagnostics(item, computed_at=_NOW)
        }
        for team_id, item in season_inputs.items()
    }
    assert "few_but_high_quality_chances_allowed" in findings_by_team[1]
    assert "high_volume_low_quality_allowed" in findings_by_team[2]


def test_sterile_possession_never_fires_without_possession_evidence() -> None:
    """`possession_pct` is not part of the real ENG_PL 2025/26 catalog
    identities, so `sterile_possession` must correctly stay unreachable
    regardless of what other evidence exists.
    """

    observations = [
        _team_observation(1, {"shots_total_against": 5.0}, match_id=1),
        _team_observation(2, {"shots_total_against": 20.0}, match_id=2),
    ]
    result = calculate_team_analytics_v2(observations, scope_key="competition:test-no-possession")
    inputs = build_team_diagnostic_inputs_v2(result)

    assert all(item.possession_percentile is None for item in inputs)
    codes = {
        finding.diagnostic_code
        for item in inputs
        for finding in evaluate_team_diagnostics(item, computed_at=_NOW)
    }
    assert "sterile_possession" not in codes
