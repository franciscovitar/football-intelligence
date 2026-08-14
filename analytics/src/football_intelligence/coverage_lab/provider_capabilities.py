"""Static, documented capability manifests: what each provider can
*structurally* ever report, independent of any specific live probe.

Every metric listed here has been verified against real payloads/events
during Block 14/15 implementation (see `docs/ZERO_COST_COVERAGE.md`). This is
not a place to guess -- a metric absent from a provider's manifest is
`unsupported` for that provider regardless of what any single probe finds.

`supported_metrics` is keyed by `(metric_name, granularity)`, matching the
target catalog's true identity (`target_metrics.TargetMetric`'s uniqueness
key), not bare `metric_name` alone. The same bare name can mean two different
things at two granularities -- for example StatsBomb's Open Data derives both
a team-level `shots_total` (a match rollup) and a player-level `shots_total`
(one player's own shots) from the same event log, and TheSportsDB's Free
event-stats endpoint only ever supports the team-level one. A bare-name key
would silently claim a provider supports a granularity it never touched.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from football_intelligence.coverage_lab.models import FreshnessRole

MetricReliability = Literal["full", "partial"]
MetricKey = tuple[str, str]  # (metric_name, granularity)


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    provider_code: str
    freshness_role: FreshnessRole
    requires_token: bool
    token_env_var: str | None
    # (metric_name, granularity) -> "full" (directly reported) | "partial"
    # (a proxy/approximation, or structurally capped so completeness can
    # never be proven -- e.g. TheSportsDB Free's 5-row lineup cap).
    supported_metrics: Mapping[MetricKey, MetricReliability]


# TheSportsDB v1 Free and OpenLigaDB: verified in Block 13. Both report a
# boolean finished/not-finished signal, not the full MatchRecord.status
# vocabulary, so "status" is a partial proxy rather than a full match.
_CURRENT_MATCH_RESULT_METRICS: Mapping[MetricKey, MetricReliability] = {
    ("home_score", "match"): "full",
    ("away_score", "match"): "full",
    ("status", "match"): "partial",
}

# TheSportsDB v1 Free, deepened in Block 15: `lookupeventstats.php` and
# `lookuplineup.php`, both documented free endpoints, verified live against a
# real finished Bundesliga match during implementation.
#
# `lookupeventstats.php` returns at most 5 stat rows per match (a verified
# Free-tier cap, not a documentation guess). The 5 rows returned were
# consistently: "Shots on Goal", "Shots off Goal", "Total Shots",
# "Blocked Shots", "Shots insidebox". Only the 4 with unambiguous, exact
# TeamMatchStatsRecord semantics are mapped; "Shots off Goal" is NOT the same
# concept as `shots_outside_box` (off-target vs inside/outside the penalty
# box are different classifications) so it is deliberately left unmapped.
# All 4 mapped fields are reliably present whenever the endpoint returns
# data at all, so they are "full", not capped like the lineup below.
_THESPORTSDB_EVENT_STATS_METRICS: Mapping[MetricKey, MetricReliability] = {
    ("shots_on_target", "team"): "full",
    ("shots_total", "team"): "full",
    ("blocked_shots", "team"): "full",
    ("shots_inside_box", "team"): "full",
}

# `lookuplineup.php` returns at most 5 player rows per match (verified live:
# a real finished match returned exactly 5, all one team). Real, useful
# evidence, but never provably a complete lineup (a real squad has ~18-23
# rows) -- capped at "partial" permanently, regardless of how many rows a
# given probe happens to observe, so `current_available` can never be claimed
# from a structurally incomplete payload.
_THESPORTSDB_LINEUP_METRICS: Mapping[MetricKey, MetricReliability] = {
    ("listed_position", "player_appearance"): "partial",
    ("started", "player_appearance"): "partial",
    ("shirt_number", "player_appearance"): "partial",
}

_THESPORTSDB_METRICS: Mapping[MetricKey, MetricReliability] = {
    **_CURRENT_MATCH_RESULT_METRICS,
    **_THESPORTSDB_EVENT_STATS_METRICS,
    **_THESPORTSDB_LINEUP_METRICS,
}

# StatsBomb Open Data: verified against a real Bundesliga 2023/24 match's
# events.json during Block 14 implementation. Every entry below has a
# confirmed, documented event-field derivation (see ZERO_COST_COVERAGE.md);
# nothing here is guessed. Several names are derived at BOTH team (a match
# rollup) and player_match (one player's own count) granularity from the same
# verified event data -- both are listed explicitly, never inferred.
_STATSBOMB_TEAM_ROLLUP_METRICS: Mapping[MetricKey, MetricReliability] = {
    ("shots_total", "team"): "full",
    ("shots_on_target", "team"): "full",
    ("passes_total", "team"): "full",
    ("passes_accurate", "team"): "full",
    ("yellow_cards", "team"): "full",
    ("red_cards", "team"): "full",
    ("fouls", "team"): "full",
    ("goalkeeper_saves", "team"): "full",
    ("formation", "team"): "full",
}
_STATSBOMB_PLAYER_MATCH_METRICS: Mapping[MetricKey, MetricReliability] = {
    ("goals", "player_match"): "full",
    ("shots_total", "player_match"): "full",
    ("shots_on_target", "player_match"): "full",
    ("passes_total", "player_match"): "full",
    ("passes_accurate", "player_match"): "full",
    ("key_passes", "player_match"): "full",
    ("interceptions", "player_match"): "full",
    ("clearances", "player_match"): "full",
    ("blocks", "player_match"): "full",
    ("dribbles_attempted", "player_match"): "full",
    ("dribbles_successful", "player_match"): "full",
    ("tackles", "player_match"): "full",
    ("fouls_committed", "player_match"): "full",
    ("fouls_drawn", "player_match"): "full",
    ("yellow_cards", "player_match"): "full",
    ("red_cards", "player_match"): "full",
    ("saves", "player_match"): "full",
    ("advanced.xg", "player_match"): "full",
}
_STATSBOMB_APPEARANCE_METRICS: Mapping[MetricKey, MetricReliability] = {
    ("started", "player_appearance"): "full",
    ("shirt_number", "player_appearance"): "full",
    ("listed_position", "player_appearance"): "full",
}
_STATSBOMB_METRICS: Mapping[MetricKey, MetricReliability] = {
    ("home_score", "match"): "full",
    ("away_score", "match"): "full",
    ("status", "match"): "full",
    **_STATSBOMB_TEAM_ROLLUP_METRICS,
    **_STATSBOMB_PLAYER_MATCH_METRICS,
    **_STATSBOMB_APPEARANCE_METRICS,
}

# football-data.org Free tier: competitions/fixtures/results/standings only.
# No deep player statistics are claimed (Free tier does not expose them).
# "status" is "partial", not "full": the adapter only ever proxies a
# cross-source finished/not-finished boolean (see
# `data_mesh/adapters/football_data_org.py`), never the provider's full
# status vocabulary (SCHEDULED/TIMED/IN_PLAY/PAUSED/FINISHED/SUSPENDED/
# POSTPONED/CANCELLED/AWARDED) -- the same limitation TheSportsDB/OpenLigaDB
# have, for the same reason.
_FOOTBALL_DATA_ORG_METRICS: Mapping[MetricKey, MetricReliability] = {
    ("home_score", "match"): "full",
    ("away_score", "match"): "full",
    ("status", "match"): "partial",
}

# Football-Data.co.uk: explicitly published downloadable CSV files (structured
# file ingestion, not scraping). Verified live during Block 15 implementation
# against the official https://www.football-data.co.uk/notes.txt column key
# and real current-season CSV downloads. Every CSV row is a completed result
# (the site's own description: "Current results (full time, half time)"), so
# "status" is "full", not a proxy -- unlike the live-score sources above,
# there is no ambiguity about what "finished" means for a historical results
# file. Odds/betting columns are never mapped. Fields the CSV does not
# publish (shots_inside_box, shots_outside_box, blocked_shots, offsides,
# passes_total, passes_accurate, goalkeeper_saves, possession_pct) are
# deliberately absent here -- unsupported, never guessed.
_FOOTBALL_DATA_UK_METRICS: Mapping[MetricKey, MetricReliability] = {
    ("home_score", "match"): "full",
    ("away_score", "match"): "full",
    ("status", "match"): "full",
    ("shots_total", "team"): "full",
    ("shots_on_target", "team"): "full",
    ("fouls", "team"): "full",
    ("corners", "team"): "full",
    ("yellow_cards", "team"): "full",
    ("red_cards", "team"): "full",
}

PROVIDER_CAPABILITIES: tuple[ProviderCapability, ...] = (
    ProviderCapability(
        provider_code="thesportsdb",
        freshness_role="current",
        requires_token=False,
        token_env_var=None,
        supported_metrics=_THESPORTSDB_METRICS,
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
        provider_code="football-data-uk",
        freshness_role="current",
        requires_token=False,
        token_env_var=None,
        supported_metrics=_FOOTBALL_DATA_UK_METRICS,
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
