"""Block 16 corrective additions required by the statistical product brief.

These are target definitions, not claims of current provider coverage.  The
Coverage Lab reports them as unsupported until an exact-grain, permitted
source is verified.
"""

from __future__ import annotations

from football_intelligence.metric_catalog.types import (
    CATALOG_V2_VERSION,
    MetricCategory,
    MetricDefinition,
    MetricDirection,
    MetricGranularity,
    MetricKind,
)

_PLAYER_SAMPLE = "min 450 minutes plus metric-specific opportunity sample"
_GOALKEEPER_SAMPLE = "min 450 minutes and sufficient shots/actions faced"
_TEAM_SAMPLE = "min 5 matches in window for percentile eligibility"


def _metric(
    key: str,
    display_name: str,
    category: MetricCategory,
    *,
    granularity: MetricGranularity = "player_match",
    unit: str = "count",
    kind: MetricKind = "raw",
    per90: bool = True,
    direction: MetricDirection = "higher_better",
    sample: str = _PLAYER_SAMPLE,
    notes: str = "",
) -> MetricDefinition:
    return MetricDefinition(
        key=key,
        display_name=display_name,
        granularity=granularity,
        category=category,
        unit=unit,
        kind=kind,
        per90_eligible=per90,
        percentile_eligible=True,
        direction=direction,
        min_sample_policy=sample,
        semantic_version=CATALOG_V2_VERSION,
        notes=notes,
    )


PRODUCT_GAP_METRICS: tuple[MetricDefinition, ...] = (
    # Shooting / expected output.
    _metric(
        "goals_per_shot", "Goals per Shot", "shooting", unit="ratio", kind="derived", per90=False
    ),
    _metric(
        "goals_per_shot_on_target",
        "Goals per Shot on Target",
        "shooting",
        unit="ratio",
        kind="derived",
        per90=False,
    ),
    _metric("big_chances_missed", "Big Chances Missed", "shooting", direction="lower_better"),
    _metric("touches_in_box", "Touches in Box", "shooting"),
    _metric("headed_shots", "Headed Shots", "shooting"),
    _metric(
        "shot_distance",
        "Average Shot Distance",
        "shooting",
        unit="distance_m",
        kind="derived",
        per90=False,
        direction="contextual",
    ),
    _metric(
        "non_penalty_goals_minus_npxg",
        "Non-Penalty Goals Minus npxG",
        "expected_output",
        unit="rating",
        kind="derived",
        per90=False,
        direction="contextual",
        notes="Direct finishing residual; may also be expressed per 90.",
    ),
    # Creation.
    _metric("passes_into_final_third", "Passes Into Final Third", "creation"),
    _metric("shot_creating_actions", "Shot-Creating Actions", "creation"),
    _metric("goal_creating_actions", "Goal-Creating Actions", "creation"),
    _metric(
        "xa_per90", "Expected Assists per 90", "creation", unit="per90", kind="derived", per90=False
    ),
    _metric("expected_threat_pass", "Expected Threat from Passes", "creation", unit="rating"),
    _metric("expected_threat_created", "Expected Threat Created", "creation", unit="rating"),
    _metric("expected_assists_open_play", "Open-Play Expected Assists", "creation", unit="rating"),
    # Passing.
    _metric("short_passes_accurate", "Accurate Short Passes", "passing"),
    _metric("medium_passes_accurate", "Accurate Medium Passes", "passing"),
    _metric("long_passes_accurate", "Accurate Long Passes", "passing"),
    _metric("progressive_pass_distance", "Progressive Pass Distance", "passing", unit="distance_m"),
    _metric("switches", "Switches", "passing"),
    _metric("passes_under_pressure", "Passes Under Pressure", "passing", direction="contextual"),
    _metric("passes_received", "Passes Received", "passing", direction="contextual"),
    _metric("progressive_passes_received", "Progressive Passes Received", "passing"),
    # Progression and touches.
    _metric(
        "progressive_carry_distance", "Progressive Carry Distance", "progression", unit="distance_m"
    ),
    _metric(
        "carry_distance", "Carry Distance", "progression", unit="distance_m", direction="contextual"
    ),
    _metric("carries_into_box", "Carries Into Box", "progression"),
    _metric("progressive_actions", "Progressive Actions", "progression", kind="derived"),
    _metric("ball_progressions", "Ball Progressions", "progression", kind="derived"),
    _metric("touches", "Touches", "progression", direction="contextual"),
    _metric("touches_final_third", "Touches in Final Third", "progression"),
    _metric("touches_box", "Touches in Penalty Area", "progression"),
    # Dribbling and possession security.
    _metric("players_beaten", "Players Beaten", "dribbling"),
    _metric(
        "take_on_success_pct",
        "Take-On Success %",
        "dribbling",
        unit="percentage",
        kind="derived",
        per90=False,
    ),
    _metric("turnovers", "Turnovers", "possession_security", direction="lower_better"),
    _metric(
        "receiving_errors",
        "Receiving Errors",
        "possession_security",
        direction="lower_better",
        notes="Use only when the provider definition and reliability are verified.",
    ),
    # Defending and duels.
    _metric("shot_blocks", "Shot Blocks", "defending"),
    _metric("pass_blocks", "Pass Blocks", "defending"),
    _metric("successful_pressures", "Successful Pressures", "defending"),
    _metric(
        "pressure_success_pct",
        "Pressure Success %",
        "defending",
        unit="percentage",
        kind="derived",
        per90=False,
    ),
    _metric(
        "errors_leading_to_shot", "Errors Leading to Shot", "defending", direction="lower_better"
    ),
    _metric(
        "errors_leading_to_goal", "Errors Leading to Goal", "defending", direction="lower_better"
    ),
    _metric("ground_duels", "Ground Duels", "duels", direction="contextual"),
    _metric("ground_duels_won", "Ground Duels Won", "duels"),
    _metric("aerial_duels_won", "Aerial Duels Won", "duels"),
    _metric(
        "aerial_duel_win_pct",
        "Aerial Duel Win %",
        "duels",
        unit="percentage",
        kind="derived",
        per90=False,
    ),
    # Goalkeeping.
    _metric(
        "xg_on_target_faced",
        "Expected Goals on Target Faced",
        "goalkeeping",
        granularity="goalkeeper_match",
        unit="rating",
        sample=_GOALKEEPER_SAMPLE,
    ),
    _metric(
        "psxg",
        "Post-Shot Expected Goals",
        "goalkeeping",
        granularity="goalkeeper_match",
        unit="rating",
        sample=_GOALKEEPER_SAMPLE,
        notes="Provider-neutral alias retained alongside xg_on_target_faced.",
    ),
    _metric(
        "crosses_stopped",
        "Crosses Stopped",
        "goalkeeping",
        granularity="goalkeeper_match",
        sample=_GOALKEEPER_SAMPLE,
    ),
    _metric(
        "sweeper_actions",
        "Sweeper Actions",
        "goalkeeping",
        granularity="goalkeeper_match",
        sample=_GOALKEEPER_SAMPLE,
    ),
    _metric(
        "passes",
        "Goalkeeper Passes",
        "goalkeeping",
        granularity="goalkeeper_match",
        direction="contextual",
        sample=_GOALKEEPER_SAMPLE,
    ),
    _metric(
        "long_passes",
        "Goalkeeper Long Passes",
        "goalkeeping",
        granularity="goalkeeper_match",
        direction="contextual",
        sample=_GOALKEEPER_SAMPLE,
    ),
    _metric(
        "launches",
        "Goalkeeper Launches",
        "goalkeeping",
        granularity="goalkeeper_match",
        direction="contextual",
        sample=_GOALKEEPER_SAMPLE,
    ),
    _metric(
        "average_distance_from_goal",
        "Average Distance from Goal",
        "goalkeeping",
        granularity="goalkeeper_match",
        unit="distance_m",
        kind="derived",
        per90=False,
        direction="contextual",
        sample=_GOALKEEPER_SAMPLE,
    ),
    # Team model gaps. Existing counter_attacks/counter_attack_shots remain in
    # match_and_team.py and are intentionally not duplicated here.
    _metric(
        "npxg",
        "Non-Penalty Expected Goals (Team)",
        "team_performance",
        granularity="team_match",
        unit="rating",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "npxga",
        "Non-Penalty Expected Goals Against (Team)",
        "team_performance",
        granularity="team_match",
        unit="rating",
        direction="lower_better",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "shots_on_target_allowed",
        "Shots on Target Allowed",
        "team_performance",
        granularity="team_match",
        direction="lower_better",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "xga_per_shot",
        "xGA per Shot",
        "team_performance",
        granularity="team_match",
        unit="ratio",
        kind="derived",
        per90=False,
        direction="lower_better",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "big_chances",
        "Big Chances (Team)",
        "team_performance",
        granularity="team_match",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "big_chances_allowed",
        "Big Chances Allowed",
        "team_performance",
        granularity="team_match",
        direction="lower_better",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "box_entries",
        "Box Entries",
        "team_possession",
        granularity="team_match",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "touches_in_box",
        "Touches in Box (Team)",
        "team_possession",
        granularity="team_match",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "high_turnovers",
        "High Turnovers",
        "team_pressing",
        granularity="team_match",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "successful_pressures",
        "Successful Pressures (Team)",
        "team_pressing",
        granularity="team_match",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "transition_xg",
        "Transition xG",
        "team_transition",
        granularity="team_match",
        unit="rating",
        sample=_TEAM_SAMPLE,
    ),
    _metric(
        "deep_completions",
        "Deep Completions",
        "team_possession",
        granularity="team_match",
        sample=_TEAM_SAMPLE,
    ),
)
