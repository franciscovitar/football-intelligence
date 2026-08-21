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

    `season_scope_complete` (Block 20D.4): whether the real `MatchBundle`s a
    certified adapter run declares this scope for genuinely cover the WHOLE
    real competition/season -- the aggregation universe a `player_season`/
    `goalkeeper_season` fact implicitly claims. Defaults to `True` because
    every scope declared before Block 20D.4 genuinely is a complete real
    season (Wyscout ENG_PL 2017/18: 380/380 matches; StatsBomb ENG_PL
    2015/16: 380/380; Wyscout ESP_LL 2017/18: 380/380). It must be set to
    `False` for a scope whose real available match set is a genuine subset
    of the real competition/season (e.g. StatsBomb's real ESP_LL Open Data
    scope: only 36 of one club's 38 real league matches, never a full
    780-team-match league season for any player) -- a certified adapter's
    season-level entry point must refuse to emit `player_season`/
    `goalkeeper_season` facts for such a scope rather than silently
    presenting a partial-window aggregate as if it were the real season
    total. This is a scope-declaration property, never inferred from the
    real number of bundles a caller happens to pass in -- a genuinely
    complete season could legitimately be split across multiple batched
    calls, so completeness is asserted by whoever declares the scope, not
    guessed from `len(bundles)`.
    """

    canonical_competition_code: str
    season_label: str
    provider_competition_id: int
    provider_season_id: int | None = None
    season_scope_complete: bool = True


class ScopeMismatchError(RuntimeError):
    """A real payload record's own native competition/season identifier did
    not match the `AdapterScope` declared for this run -- e.g. a batch
    mixing ENG_PL and ESP_LL matches, or an ESP_LL run fed an England
    match. Refused outright rather than silently accepted, silently
    dropped, or silently attributed to the wrong scope."""
