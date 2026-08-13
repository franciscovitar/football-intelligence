"""Static, documented capability manifests: what each provider can
*structurally* ever report, independent of any specific live probe.

Every metric listed here has been verified against real payloads/events
during Block 14 implementation (see `docs/ZERO_COST_COVERAGE.md`). This is
not a place to guess -- a metric absent from a provider's manifest is
`unsupported` for that provider regardless of what any single probe finds.

`supported_metrics` is keyed by bare `metric_name`, not `(metric_name,
granularity)`, even though the same name can exist at two granularities in
the target catalog (e.g. `shots_total` at both `team` and `player_match`).
This is a deliberate V0 simplification: every provider below that supports
such a name supports it identically at every granularity it appears in
(StatsBomb's team-level rollups are derived from the same verified
player-level event data). If a future provider ever supports a name at one
granularity but not another, this manifest shape will need to become
`Mapping[tuple[str, str], MetricReliability]`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from football_intelligence.coverage_lab.models import FreshnessRole

MetricReliability = Literal["full", "partial"]


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    provider_code: str
    freshness_role: FreshnessRole
    requires_token: bool
    token_env_var: str | None
    # metric_name -> "full" (directly reported) | "partial" (a proxy/approximation)
    supported_metrics: Mapping[str, MetricReliability]


# TheSportsDB v1 Free and OpenLigaDB: verified in Block 13. Both report a
# boolean finished/not-finished signal, not the full MatchRecord.status
# vocabulary, so "status" is a partial proxy rather than a full match.
_CURRENT_MATCH_RESULT_METRICS: Mapping[str, MetricReliability] = {
    "home_score": "full",
    "away_score": "full",
    "status": "partial",
}

# StatsBomb Open Data: verified against a real Bundesliga 2023/24 match's
# events.json during Block 14 implementation. Every entry below has a
# confirmed, documented event-field derivation (see ZERO_COST_COVERAGE.md);
# nothing here is guessed.
_STATSBOMB_METRICS: Mapping[str, MetricReliability] = {
    "home_score": "full",
    "away_score": "full",
    "status": "full",
    "shots_total": "full",
    "shots_on_target": "full",
    "goals": "full",
    "key_passes": "full",
    "passes_total": "full",
    "passes_accurate": "full",
    "interceptions": "full",
    "clearances": "full",
    "blocks": "full",
    "dribbles_attempted": "full",
    "dribbles_successful": "full",
    "tackles": "full",
    "fouls_committed": "full",
    "fouls_drawn": "full",
    "yellow_cards": "full",
    "red_cards": "full",
    "saves": "full",
    "formation": "full",
    "started": "full",
    "shirt_number": "full",
    "listed_position": "full",
    "advanced.xg": "full",
}

# football-data.org Free tier: competitions/fixtures/results/standings only.
# No deep player statistics are claimed (Free tier does not expose them).
_FOOTBALL_DATA_ORG_METRICS: Mapping[str, MetricReliability] = {
    "home_score": "full",
    "away_score": "full",
    "status": "full",
}

PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    ProviderCapability(
        provider_code="thesportsdb",
        freshness_role="current",
        requires_token=False,
        token_env_var=None,
        supported_metrics=_CURRENT_MATCH_RESULT_METRICS,
    ),
    ProviderCapability(
        provider_code="openligadb",
        freshness_role="current",
        requires_token=False,
        token_env_var=None,
        supported_metrics=_CURRENT_MATCH_RESULT_METRICS,
    ),
    ProviderCapability(
        provider_code="football-data-org",
        freshness_role="current",
        requires_token=True,
        token_env_var="FOOTBALL_DATA_ORG_KEY",
        supported_metrics=_FOOTBALL_DATA_ORG_METRICS,
    ),
    ProviderCapability(
        provider_code="statsbomb-open",
        freshness_role="historical",
        requires_token=False,
        token_env_var=None,
        supported_metrics=_STATSBOMB_METRICS,
    ),
)


def capability_by_code(provider_code: str) -> ProviderCapability | None:
    for capability in PROVIDER_CAPABILITIES:
        if capability.provider_code == provider_code:
            return capability
    return None
