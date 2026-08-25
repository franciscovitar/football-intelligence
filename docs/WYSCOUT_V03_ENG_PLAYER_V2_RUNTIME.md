# Wyscout Open v0.3 — ENG_PL 2017/18 Player V2 runtime

Status: **PASS** — real-source, ephemeral-PostgreSQL evidence captured on 2026-08-25 from `main` after PR #46.

This run did **not** access or write the production database. It used PostgreSQL 17 in GitHub Actions, the official Wyscout Open source, all repository migrations, and the current `player-v2.0` engine.

Evidence run: GitHub Actions `32839725705`.
Artifact: `wyscout-v03-eng-player-v2-runtime` (`9560254725`, retained temporarily by GitHub Actions).

## Canonical/Data Mesh runtime

Both consecutive historical loads produced the same state:

- matches: **380**;
- teams: **20**;
- participating players: **515**;
- player appearances: **10,443**;
- player-match stat rows: **10,443**;
- team-match stat rows: **760**;
- Wyscout scoped source observations: **422,877**.

The previous certified `wyscout-open-v0.2` fingerprint contained 412,609 source observations. The v0.3 increase is exactly **10,268**, equal to the newly emitted `long_passes_accurate` observations. Existing Data Mesh observations are upserted by their natural fact identity; `semantic_version` is updated rather than used as a duplicate-producing key.

Loader idempotency: **PASS**. The second complete real-source load reproduced the same canonical counts, metric coverage and scoped source-observation counts.

## New/previously blocked evidence

Across the 10,443 canonical player-match rows:

- `passes_total`: known in **10,443 / 10,443**;
- `passes_accurate`: known in **10,443 / 10,443**;
- `aerial_duels`: known in **10,443 / 10,443**;
- `aerial_duels_won`: known in **10,443 / 10,443**;
- `long_passes_accurate`: known in **10,268 / 10,443**;
- `long_passes_accurate` missing: **175** player-matches;
- confirmed zero `long_passes_accurate`: **4,040** player-matches;
- positive `long_passes_accurate`: **6,228** player-matches.

Missing long-pass geometry remains missing. It is not converted to zero.

`progressive_passes` and `passes_into_final_third` remain absent because their exact Wyscout spatial methodology has not passed the required coverage/evidence gate.

## Player V2 runtime

The current engine was calculated twice on the same loaded state. Both runs produced byte-identical reports and runtime evidence:

- score snapshots: **2,048**;
- feature snapshots: **38,737**;
- season players: **512**;
- season players with at least 450 minutes: **385**;
- overall scores: **0**;
- ranking candidates: **0**.

Player V2 idempotency: **PASS**.

Top-level evidence states remained:

- `insufficient_data`: **1,754** snapshots;
- `partial`: **294** snapshots.

No overall ranking was fabricated from incomplete dimensions.

## Aerial result

For the season window:

- `aerial` ready: **385** players;
- `aerial` insufficient data: **127** players;
- scored Aerial rows: **385**.

Therefore Aerial is now ready for every season player meeting the 450-minute comparison threshold. This resolves the previously identified Aerial bottleneck without changing Player V2 gates.

Season feature evidence includes:

- `aerial_duels_won`: 512 raw rows, 385 percentile rows;
- `aerial_duel_win_pct`: 488 raw rows, 385 percentile rows.

## Passing result

Passing remains correctly `insufficient_data` for **512 / 512** season players and has **0** scored season rows.

The profile requires:

- `pass_completion_pct` — 25%;
- `progressive_passes` — 30%;
- `passes_into_final_third` — 25%;
- `long_passes_accurate` — 20%;
- minimum evidence coverage — 60%.

Current real evidence now provides `pass_completion_pct` for all 512 season players and an exact `long_passes_accurate` season feature for 384 players. Even where both exist, their combined profile weight is only **45%**, below the unchanged 60% gate. Passing therefore stays unscored by design.

The correct next step is to improve evidence for `progressive_passes` and/or `passes_into_final_third`; lowering the evidence threshold or replacing missing values with zero is explicitly not justified by this runtime.

## Promotion implication

The ENG_PL production-promotion fingerprint must be updated only from observed runtime evidence:

- `source_observations`: **412,609 → 422,877**;
- `feature_snapshots`: **26,841 → 38,737**.

All other already-certified promotion invariants used by the existing contract remain unchanged unless separately re-observed or affected by their own methodology. The pre-v0.3 published ENG_PL state must be treated as an explicit certified predecessor during upgrade rather than as an arbitrary partial state.
