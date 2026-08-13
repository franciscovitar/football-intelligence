"""Coverage/capability model for the Zero-Cost Coverage Lab.

A `CoverageState` answers one question precisely: can this provider supply
this metric, for this competition, right now? A historical-only source (for
example StatsBomb Open Data) can never answer "yes" to a *current*-data
query, even if it supports the metric for a past season -- that distinction
is the whole point of separating `current_available` from `historical_only`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

FreshnessRole = Literal["current", "historical"]

CoverageState = Literal[
    "current_available",
    "historical_only",
    "partial",
    "token_required",
    "not_probed",
    "missing",
    "unsupported",
]

# States that would satisfy a *current*-data need. Nothing else may be
# treated as "the product can rely on this today".
CURRENT_SATISFYING_STATES: frozenset[CoverageState] = frozenset({"current_available"})

COVERAGE_MODEL_VERSION = "coverage-lab-v0.1"


@dataclass(frozen=True, slots=True)
class CoverageEntry:
    provider_code: str
    competition_code: str
    metric_name: str
    # The true target-catalog identity is (metric_name, granularity), not
    # metric_name alone (the same name can exist at two granularities, e.g.
    # "shots_total" at both team and player_match) -- stored explicitly
    # rather than inferred from the coarser, lossy `entity_type` bucket, so
    # product-level union aggregation can group requirements precisely.
    granularity: str
    entity_type: str
    freshness_role: FreshnessRole
    state: CoverageState
    sample_size: int
    observed_count: int
    source_reference: str | None
    last_checked_at: datetime
    notes: str | None = None


def satisfies_current(state: CoverageState) -> bool:
    return state in CURRENT_SATISFYING_STATES
