"""Explicit exposure-policy marker for StatsBomb Open Data evidence.

This is intentionally tiny: a single frozen constant plus a small assertion
helper, not an authorization framework. Its only job is to prevent later
code from accidentally treating StatsBomb-derived data as cleared for
user-facing production before an explicit decision is made.

## Why this exists (Block 20C.1 finding, not a legal conclusion)

The StatsBomb Public Data User Agreement is materially stricter than the
Wyscout Open Data CC BY 4.0 licence already accepted for this repository:

- **Attribution**: any published analysis must be accredited with the
  StatsBomb brand logo, not just a text citation (README + User Agreement
  Sec. 1.4).
- **Redistribution**: the User "may not... distribute, reproduce, sell or
  in any way provide the data to any external or third party" (Sec. 1.2.1),
  and all data remains StatsBomb's property (Sec. 7).
- **Commercial use**: the User "may not... commercially exploit the data
  or any analysis derived from the use of the Service" (Sec. 1.2.2). The
  Agreement does not define "commercially exploit" or distinguish a free
  product from a paid one, so whether Football Intelligence surfacing
  StatsBomb-derived intelligence to end users would count is genuinely
  **unclear from the document alone**.

This module makes no legal determination about any of the above. It only
records, as code, that the question is open and that Block 20C data must
stay internal until a human makes that call.
"""

from __future__ import annotations

STATSBOMB_INTERNAL_ONLY: bool = True

ATTRIBUTION_REQUIREMENT = (
    "Any published analysis using StatsBomb Open Data must cite StatsBomb as the source "
    "AND display the StatsBomb brand logo (README + User Agreement Sec. 1.4) -- a stricter "
    "requirement than Wyscout Open Data's CC BY 4.0 text-only attribution."
)

REDISTRIBUTION_RESTRICTION = (
    "The StatsBomb User Agreement prohibits distributing, reproducing, or providing the raw "
    "data to any external/third party (Sec. 1.2.1); all data remains StatsBomb's property "
    "(Sec. 7). Raw StatsBomb Open Data files must never be committed to this repository or "
    "otherwise redistributed."
)

COMMERCIAL_USE_AMBIGUITY = (
    "The User Agreement prohibits commercially exploiting the data 'or any analysis derived "
    "from the use of the Service' (Sec. 1.2.2), without defining 'commercially exploit' or "
    "distinguishing a free product from a paid one. Whether serving StatsBomb-derived "
    "intelligence to Football Intelligence's users would fall under this restriction is NOT "
    "resolved by this repository -- it requires an explicit product/legal decision, not a "
    "code-level assumption."
)

NO_USER_FACING_PROMOTION_NOTICE = (
    "Until the commercial-use question above is explicitly resolved, no StatsBomb-derived "
    "value may reach production, the web app, or any other user-facing surface. "
    "STATSBOMB_INTERNAL_ONLY exists precisely to make that omission structural rather than "
    "a matter of remembering not to wire it up."
)


def assert_internal_only_evidence() -> None:
    """Defensive guard for any future code path that might be tempted to promote
    StatsBomb-derived evidence to a user-facing surface. Raises unconditionally
    while `STATSBOMB_INTERNAL_ONLY` is True -- flip that constant only as part of
    the explicit product/legal decision described above, never as an incidental
    code change."""

    if STATSBOMB_INTERNAL_ONLY:
        raise RuntimeError(
            "StatsBomb Open Data evidence is internal_only for Block 20C "
            "(see providers.statsbomb_open_policy for why) and must not be exposed "
            "to any user-facing/production surface."
        )
