"""Advanced/contextual metrics: strength adjustments and meta signals.

All entries here are `derived` and mostly `percentile_eligible=False` -- they
describe context for interpreting other metrics rather than a directly
comparable skill measurement, per the product spec's "Advanced/contextual"
family.
"""

from __future__ import annotations

from football_intelligence.metric_catalog.types import CATALOG_V2_VERSION, MetricDefinition

_CONTEXT_SAMPLE = "contextual adjustment factor; not itself a shrinkage-eligible skill metric"

CONTEXT_METRICS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        key="league_strength",
        display_name="League Strength",
        granularity="competition",
        category="advanced_context",
        unit="rating",
        kind="derived",
        per90_eligible=False,
        percentile_eligible=False,
        direction="contextual",
        min_sample_policy=_CONTEXT_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
        notes="Not calibrated in V1; declared for future cross-league adjustment (see Block 12).",
    ),
    MetricDefinition(
        key="team_strength_elo",
        display_name="Team Strength (Elo)",
        granularity="team",
        category="advanced_context",
        unit="rating",
        kind="derived",
        per90_eligible=False,
        percentile_eligible=True,
        direction="contextual",
        min_sample_policy=_CONTEXT_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
        notes="team_analytics.engine Elo history already computes this; catalog entry only.",
    ),
    MetricDefinition(
        key="opponent_strength",
        display_name="Opponent Strength",
        granularity="team_match",
        category="advanced_context",
        unit="rating",
        kind="derived",
        per90_eligible=False,
        percentile_eligible=False,
        direction="contextual",
        min_sample_policy=_CONTEXT_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="home_away",
        display_name="Home / Away",
        granularity="match",
        category="advanced_context",
        unit="label",
        kind="raw",
        per90_eligible=False,
        percentile_eligible=False,
        direction="contextual",
        min_sample_policy=_CONTEXT_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
    MetricDefinition(
        key="positional_peer_group",
        display_name="Positional Peer Group",
        granularity="player_season",
        category="advanced_context",
        unit="label",
        kind="derived",
        per90_eligible=False,
        percentile_eligible=False,
        direction="contextual",
        min_sample_policy=_CONTEXT_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
        notes="See position_profiles.classify_position_family for the deterministic classifier.",
    ),
    MetricDefinition(
        key="minutes_confidence",
        display_name="Minutes Confidence",
        granularity="player_season",
        category="advanced_context",
        unit="rating",
        kind="derived",
        per90_eligible=False,
        percentile_eligible=False,
        direction="contextual",
        min_sample_policy=_CONTEXT_SAMPLE,
        semantic_version=CATALOG_V2_VERSION,
    ),
)
