# Wyscout Open v0.3 comparability re-certification

Status: **PASS** — evidence captured on 2026-08-25 before PR #46 promotion.

## Why re-certification was required

`wyscout-open-v0.3` adds the audited `ENG_PL`-only `long_passes_accurate` observation. The existing Wyscout Open x StatsBomb Open comparability registry was deliberately pinned to `wyscout-open-v0.2`, so the adapter version bump correctly forced reconciliation to `methodology_pending` until the new version was explicitly reviewed.

## Real-source equivalence evidence

The complete official Wyscout Open `ESP_LL` 2017/18 source was emitted once with the certified `wyscout-open-v0.2` baseline and once with the candidate `wyscout-open-v0.3` adapter.

Observed result:

- v0.2 observations: **416,407**;
- v0.3 observations: **416,407**;
- comparison rule: every `NormalizedObservation` field must match exactly except `semantic_version`;
- canonical payload equality: **PASS**;
- canonical payload SHA-256: `29b23d96326fb82b94e6529ad951e4c1b3812d0617fff79a5d34d23bc2763eb5`;
- `long_passes_accurate` observations emitted in `ESP_LL`: **0**.

Therefore the v0.3 change does not alter any previously certified Wyscout observation in the Wyscout x StatsBomb comparability scope. The existing provider-pair policies can be carried from v0.2 to v0.3 by explicit evidence rather than assumption.

## Source invariants rechecked

The official Wyscout Open core-league audit passed during the same verification run:

- `ENG_PL`: 380 matches / 643,150 events;
- `ESP_LL`: 380 matches / 628,659 events;
- `FRA_L1`: 380 matches / 632,807 events;
- `GER_BL1`: 306 matches / 519,407 events;
- `ITA_SA`: 380 matches / 647,372 events.

The England source probe also reproduced 380 matches, 643,150 events and 603 roster/squad players.

## Post-change analytics verification

After updating the literal comparability pin and its independent regression tests:

- Ruff lint: PASS;
- Ruff format check: PASS;
- mypy: PASS (`168` source files);
- pytest: **1164 passed, 28 skipped**.

The skipped tests require PostgreSQL or special real-source cache/worktree state and were not executed in that runner. Full repository Quality CI remains the merge gate for PR #46.

## Scope boundary

This re-certification does **not** certify `long_passes_accurate` for Spain, France, Germany or Italy. The new metric remains explicitly scoped to the audited `ENG_PL` 2017/18 methodology path. Other leagues require their own spatial audit before the metric may emit there.
