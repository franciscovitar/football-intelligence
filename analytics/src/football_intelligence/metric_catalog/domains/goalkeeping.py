"""Goalkeeping metrics at player_match/team_match/goalkeeper_match/season grain.

`saves` (player_match) and `goalkeeper_saves` (team_match) reproduce the
exact `(key, granularity)` identity `coverage_lab` already derives from
`normalization.models.PlayerMatchStatsRecord.saves` /
`TeamMatchStatsRecord.goalkeeper_saves` -- never renamed. The richer
`goalkeeper_match` / `goalkeeper_season` entries below are a distinct
identity (different granularity), declared for the goalkeeping family the
product spec asks for; they do not collide with, or replace, the two
baseline entries.
"""

from __future__ import annotations

from football_intelligence.metric_catalog.types import CATALOG_V2_VERSION, MetricDefinition

_PLAYER_MATCH_SAMPLE = "min 450 minutes for percentile eligibility (player-v1.0 shrinkage prior)"
_TEAM_MATCH_SAMPLE = "min 5 matches in window for percentile eligibility (team-v1.0 confidence)"
_GOALKEEPER_MATCH_SAMPLE = (
    "min 450 minutes and primary role goalkeeper; player-v1.0 goalkeeper confidence cap applies"
)
_GOALKEEPER_SEASON_SAMPLE = "season-aggregate only; no per-match denominator"

GOALKEEPING_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="saves",
        display_name="Saves",
        granularity="player_match",
        category="goalkeeping",
        unit="count",
        kind="raw",
        per90_eligible=True,
        percentile_eligible=True,
        direction="higher_better",
        min_sample_policy=_PLAYER_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="goalkeeper_saves",
        display_name="Saves (Team)",
        granularity="team_match",
        category="goalkeeping",
        unit="count",
        kind="raw",
        per90_eligible=True,
        percentile_eligible=True,
        direction="higher_better",
        min_sample_policy=_TEAM_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="saves",
        display_name="Saves (Goalkeeper Match)",
        granularity="goalkeeper_match",
        category="goalkeeping",
        unit="count",
        kind="raw",
        per90_eligible=True,
        percentile_eligible=True,
        direction="higher_better",
        min_sample_policy=_GOALKEEPER_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
        notes="Distinct identity from player_match 'saves' (different granularity); product spec.",
    ),
    MetricDefinition(
        key="shots_on_target_faced",
        display_name="Shots on Target Faced",
        granularity="goalkeeper_match",
        category="goalkeeping",
        unit="count",
        kind="raw",
        per90_eligible=True,
        percentile_eligible=True,
        direction="contextual",
        min_sample_policy=_GOALKEEPER_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="save_pct",
        display_name="Save %",
        granularity="goalkeeper_match",
        category="goalkeeping",
        unit="percentage",
        kind="derived",
        per90_eligible=False,
        percentile_eligible=True,
        direction="higher_better",
        min_sample_policy=_GOALKEEPER_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="goals_conceded",
        display_name="Goals Conceded",
        granularity="goalkeeper_match",
        category="goalkeeping",
        unit="count",
        kind="raw",
        per90_eligible=True,
        percentile_eligible=True,
        direction="lower_better",
        min_sample_policy=_GOALKEEPER_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="clean_sheets",
        display_name="Clean Sheets",
        granularity="goalkeeper_match",
        category="goalkeeping",
        unit="boolean",
        kind="raw",
        per90_eligible=False,
        percentile_eligible=False,
        direction="higher_better",
        min_sample_policy=_GOALKEEPER_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="goals_prevented",
        display_name="Goals Prevented",
        granularity="goalkeeper_match",
        category="goalkeeping",
        unit="rating",
        kind="derived",
        per90_eligible=False,
        percentile_eligible=True,
        direction="higher_better",
        min_sample_policy=_GOALKEEPER_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
        notes="Expected goals on target faced minus goals conceded; requires shot-quality data.",
    ),
    MetricDefinition(
        key="claims",
        display_name="Claims",
        granularity="goalkeeper_match",
        category="goalkeeping",
        unit="count",
        kind="raw",
        per90_eligible=True,
        percentile_eligible=True,
        direction="higher_better",
        min_sample_policy=_GOALKEEPER_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="distribution_accuracy_pct",
        display_name="Distribution Accuracy %",
        granularity="goalkeeper_match",
        category="goalkeeping",
        unit="percentage",
        kind="derived",
        per90_eligible=False,
        percentile_eligible=True,
        direction="higher_better",
        min_sample_policy=_GOALKEEPER_MATCH_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="clean_sheets",
        display_name="Clean Sheets (Season)",
        granularity="goalkeeper_season",
        category="goalkeeping",
        unit="count",
        kind="raw",
        per90_eligible=False,
        percentile_eligible=True,
        direction="higher_better",
        min_sample_policy=_GOALKEEPER_SEASON_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="save_pct",
        display_name="Save % (Season)",
        granularity="goalkeeper_season",
        category="goalkeeping",
        unit="percentage",
        kind="derived",
        per90_eligible=False,
        percentile_eligible=True,
        direction="higher_better",
        min_sample_policy=_GOALKEEPER_SEASON_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
)
