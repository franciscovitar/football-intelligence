"""Coverage state-machine: combine target catalog x target competitions x
provider capability manifests x live probe results into `CoverageEntry` rows.

Deterministic and pure -- no network I/O here. This is the piece that
guarantees a historical-only source can never satisfy a current-data query,
that "not probed" and "confirmed missing" stay distinct, and that partial
coverage never gets silently rounded up to full.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from football_intelligence.coverage_lab.models import CoverageEntry, CoverageState
from football_intelligence.coverage_lab.provider_capabilities import ProviderCapability
from football_intelligence.coverage_lab.target_competitions import TargetCompetition
from football_intelligence.coverage_lab.target_metrics import TargetMetric

ProbeStatus = Literal["ok", "error", "skipped_token_required", "not_attempted"]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """What was actually observed live, for one (provider, competition) pair.

    `sample_size` is the default denominator. A single probe can mix metrics
    with genuinely different natural denominators (e.g. StatsBomb's
    match-level facts are scoped to a full published season, while its deep
    per-player event metrics are scoped to a small bounded match sample) --
    `metric_sample_sizes` lets individual metrics override the default
    rather than being forced to share one misleading number.

    Both count mappings are keyed by `(metric_name, granularity)`, matching
    the target catalog's true identity -- see `provider_capabilities` for why
    bare `metric_name` is not a safe key.

    `is_current_period` answers a question separate from `provider.
    freshness_role`: not "can this provider ever report current data" but
    "did THIS probe actually verify data from the true current season/period
    (computed from the run date), as opposed to the latest completed one".
    A `current`-role provider whose probe only reached the previous season
    (e.g. a season file that has not been published yet, so the job fell
    back to the prior one) must never be reported as `current_available` --
    see `_resolve_entry`'s `previous_season` branch. Defaults to `True`
    because most probes (StatsBomb, whose historical role makes this
    irrelevant; football-data.org's live matches endpoint; any single-season
    probe with no fallback) are unambiguous.
    """

    status: ProbeStatus
    sample_size: int
    metric_observed_counts: Mapping[tuple[str, str], int]
    source_reference: str | None
    notes: str | None = None
    metric_sample_sizes: Mapping[tuple[str, str], int] | None = None
    is_current_period: bool = True


def compute_coverage(
    *,
    target_metrics: Sequence[TargetMetric],
    target_competitions: Sequence[TargetCompetition],
    providers: Sequence[ProviderCapability],
    probe_results: Mapping[tuple[str, str], ProbeResult],
    token_present_by_provider: Mapping[str, bool],
    calculated_at: datetime,
) -> list[CoverageEntry]:
    entries: list[CoverageEntry] = []
    for provider in providers:
        has_token = token_present_by_provider.get(provider.provider_code, False)
        for competition in target_competitions:
            probe = probe_results.get((provider.provider_code, competition.code))
            for metric in target_metrics:
                entries.append(
                    _resolve_entry(
                        provider=provider,
                        competition=competition,
                        metric=metric,
                        probe=probe,
                        has_token=has_token,
                        calculated_at=calculated_at,
                    )
                )
    return entries


def _resolve_entry(
    *,
    provider: ProviderCapability,
    competition: TargetCompetition,
    metric: TargetMetric,
    probe: ProbeResult | None,
    has_token: bool,
    calculated_at: datetime,
) -> CoverageEntry:
    metric_key = (metric.metric_name, metric.granularity)
    reliability = provider.supported_metrics.get(metric_key)

    if reliability is None:
        return _entry(
            provider,
            competition,
            metric,
            calculated_at,
            state="unsupported",
            sample_size=0,
            observed_count=0,
            source_reference=None,
            notes="provider does not structurally report this metric",
        )

    if provider.requires_token and not has_token:
        return _entry(
            provider,
            competition,
            metric,
            calculated_at,
            state="token_required",
            sample_size=0,
            observed_count=0,
            source_reference=None,
            notes=f"set {provider.token_env_var} to probe this provider",
        )

    if probe is None or probe.status == "not_attempted":
        return _entry(
            provider,
            competition,
            metric,
            calculated_at,
            state="not_probed",
            sample_size=0,
            observed_count=0,
            source_reference=None,
            notes="no live probe attempted for this provider/competition in this run",
        )

    if probe.status == "skipped_token_required":
        return _entry(
            provider,
            competition,
            metric,
            calculated_at,
            state="token_required",
            sample_size=0,
            observed_count=0,
            source_reference=None,
            notes=f"set {provider.token_env_var} to probe this provider",
        )

    if probe.status == "error":
        return _entry(
            provider,
            competition,
            metric,
            calculated_at,
            state="not_probed",
            sample_size=0,
            observed_count=0,
            source_reference=probe.source_reference,
            notes=probe.notes or "live probe failed this run",
        )

    sample_size = probe.sample_size
    if probe.metric_sample_sizes is not None and metric_key in probe.metric_sample_sizes:
        sample_size = probe.metric_sample_sizes[metric_key]
    observed_count = probe.metric_observed_counts.get(metric_key, 0)

    state: CoverageState
    if sample_size == 0 or observed_count == 0:
        state = "missing"
    elif provider.freshness_role == "current" and not probe.is_current_period:
        # Real evidence, but verified only for the latest *completed*
        # season/period, not the true current one -- never current_available,
        # regardless of how complete that prior-period sample is.
        state = "previous_season"
    elif observed_count < sample_size:
        state = "partial"
    elif provider.freshness_role == "historical":
        state = "historical_only"
    else:
        state = "current_available" if reliability == "full" else "partial"

    return _entry(
        provider,
        competition,
        metric,
        calculated_at,
        state=state,
        sample_size=sample_size,
        observed_count=observed_count,
        source_reference=probe.source_reference,
        notes=probe.notes,
    )


def _entry(
    provider: ProviderCapability,
    competition: TargetCompetition,
    metric: TargetMetric,
    calculated_at: datetime,
    *,
    state: CoverageState,
    sample_size: int,
    observed_count: int,
    source_reference: str | None,
    notes: str | None,
) -> CoverageEntry:
    return CoverageEntry(
        provider_code=provider.provider_code,
        competition_code=competition.code,
        metric_name=metric.metric_name,
        granularity=metric.granularity,
        entity_type=_entity_type_for(metric.granularity),
        freshness_role=provider.freshness_role,
        state=state,
        sample_size=sample_size,
        observed_count=observed_count,
        source_reference=source_reference,
        last_checked_at=calculated_at,
        notes=notes,
    )


def _entity_type_for(granularity: str) -> str:
    if granularity in ("player_appearance", "player_match"):
        return "player"
    if granularity in ("team",):
        return "team"
    if granularity == "match":
        return "match"
    return "competition"
