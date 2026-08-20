"""Explicit scope contract for certified historical adapters (Block 20D.3).

Both certified adapters (`wyscout_open.py`, `statsbomb_open.py`) were
originally built around one hard-coded competition/season each (ENG_PL
2017/18, ENG_PL 2015/16 respectively). Block 20D.3 generalizes both to run
against a second real scope (ESP_LL 2017/18) without duplicating adapter
code per scope -- a small, explicit, typed contract threaded through the
certified entry points as an optional parameter, defaulting to each
adapter's original ENG_PL scope for full backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AdapterScope:
    """One real competition/season a certified adapter run is declared to
    cover.

    `provider_competition_id` / `provider_season_id` are the source's own
    native identifiers for this scope -- verified against real cached
    payload data, never our internal canonical code (e.g. Wyscout's real
    `competitionId=795` for ESP_LL, never the string `"ESP_LL"` itself).
    `provider_season_id` is optional only because the contract does not
    assume every future provider exposes one; both Wyscout and StatsBomb
    do, and both certified adapters always populate it.
    """

    canonical_competition_code: str
    season_label: str
    provider_competition_id: int
    provider_season_id: int | None = None


class ScopeMismatchError(RuntimeError):
    """A real payload record's own native competition/season identifier did
    not match the `AdapterScope` declared for this run -- e.g. a batch
    mixing ENG_PL and ESP_LL matches, or an ESP_LL run fed an England
    match. Refused outright rather than silently accepted, silently
    dropped, or silently attributed to the wrong scope."""
