# Historical Player Production Promotion

Status: operational contract for promoting one certified Wyscout Open `2017/18` European core-league scope into the production PostgreSQL database.

This procedure is historical-only. It does not add a current/day-to-day provider. The adapter/product code may support a historical scope without that scope having been written to production. `ENG_PL 2017/18` has an earlier production promotion; `ESP_LL`, `FRA_L1`, `GER_BL1`, and `ITA_SA` remain separate, explicitly authorized production operations unless a later production verification documents otherwise.

## Scope

The promotion job is:

```text
python -m football_intelligence.jobs.promote_historical_player_v2
```

Select exactly one scope with:

```text
--competition ENG_PL|ESP_LL|FRA_L1|GER_BL1|ITA_SA
```

`ENG_PL` remains the default for backward compatibility. Every invocation promotes one league in one transaction and derives the explicit Player V2 scope:

```text
competition:<competition_code>:2017/18
```

The job performs:

1. the official Wyscout archive probe plus selected-country published-count/provider-ID verification;
2. certified scoped Wyscout adapter validation;
3. canonical normalization with the documented conservative minutes policy;
4. deterministic canonical team reuse/provider mapping;
5. canonical `football.*` persistence;
6. Wyscout Data Mesh observation persistence scoped by provider + season + `competition_external_id`;
7. Player V1 compatibility + Player V2 calculation for the selected competition scope;
8. exact per-league post-write invariant checks;
9. commit only after every check passes.

An exception before the final commit leaves the transaction uncommitted. Separate leagues remain separate transactions so one failed scope does not silently widen or partially commit another.

## Production safety

`--database-url` is mandatory and never inferred by this job. Remote targets use the shared `db.production_write_guard` contract and require all four signals:

```text
--allow-remote-write
--confirm-target production
--production-write-confirmation "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE"
--confirm-database-target "<exact safe target from read-only preflight>"
```

Before any production write, run the existing read-only preflight against the same database URL and inspect its credential-free `target`. The target must then be supplied exactly to `--confirm-database-target`. The promotion additionally verifies the actually connected libpq target before issuing writes.

Merging adapter/promotion code does **not** authorize or perform a remote write. Production execution remains a distinct human authorization gate.

## Allowed pre-write states

The selected historical scope must be exactly one of:

- **fresh**: no selected `2017/18` canonical rows, no Wyscout observations for that provider competition, and no Player V2 score/feature rows for its explicit scope;
- **current certified**: exactly equal to the complete current fingerprint below; or
- **explicit certified predecessor**: exactly equal to one of the predecessor fingerprints below.

Any partial or unexpected state fails closed instead of being repaired automatically. Predecessors are exact full fingerprints, not count ranges. A state that differs by even one required row is rejected. Existing observations for another Wyscout competition cannot make the selected league appear complete because Data Mesh prewrite counts include provider-native `competition_external_id`.

## Current certified v0.5 invariants

These values were pinned from independent real-source runs over the official Wyscout Open/Figshare bytes and ephemeral PostgreSQL 17. They are not learned from a production write.

| Scope | Matches | Teams | Players | Appearances | Data Mesh observations | V2 scores | V2 features | Season players | >=450 min | `performance` ready |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ENG_PL` | 380 | 20 | 515 | 10,443 | 433,126 | 2,048 | 40,513 | 512 | 385 | 385 |
| `ESP_LL` | 380 | 20 | 557 | 10,555 | 437,170 | 2,224 | 43,881 | 556 | 415 | 415 |
| `FRA_L1` | 380 | 20 | 542 | 10,515 | 435,814 | 2,148 | 42,300 | 537 | 395 | 395 |
| `GER_BL1` | 306 | 18 | 472 | 8,501 | 352,942 | 1,888 | 37,413 | 472 | 349 | 349 |
| `ITA_SA` | 380 | 20 | 534 | 10,573 | 441,225 | 2,132 | 41,996 | 533 | 403 | 403 |

For every scope, player-match stat rows equal appearance rows and team-match stat rows equal two times the match count.

Player V2 overall evidence-state totals remain:

| Scope | `insufficient_data` | `partial` | `ready` overall | Ranking candidates | Non-null overall scores |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ENG_PL` | 1,754 | 294 | 0 | 0 | 0 |
| `ESP_LL` | 1,880 | 344 | 0 | 0 | 0 |
| `FRA_L1` | 1,822 | 326 | 0 | 0 | 0 |
| `GER_BL1` | 1,596 | 292 | 0 | 0 | 0 |
| `ITA_SA` | 1,774 | 358 | 0 | 0 | 0 |

Spatial v1.2 adds exact evidence; it does not lower Player V2 gates, renormalize partial dimensions, convert missing evidence to zero, or fabricate an overall score. `progressive_passes` remains non-emitting.

## Explicit certified predecessors

The current job accepts only these older complete states as upgrade origins:

| Scope | Historical state | Data Mesh observations | V2 scores | V2 features |
| --- | --- | ---: | ---: | ---: |
| `ENG_PL` | pre-aerial/spatial v0.2-era | 412,609 | 2,048 | 26,841 |
| `ENG_PL` | v0.3 long-pass state | 422,877 | 2,048 | 38,737 |
| `ESP_LL` | certified pre-spatial state | 416,407 | 2,224 | 29,008 |
| `FRA_L1` | certified pre-spatial state | 415,230 | 2,148 | 28,007 |
| `GER_BL1` | certified pre-spatial state | 336,265 | 1,888 | 24,786 |
| `ITA_SA` | certified pre-spatial state | 420,506 | 2,132 | 27,872 |

The non-England predecessor counts were already certified in the pre-spatial promotion contract. They must not be described as reconstructed v0.4 outputs: by v0.4 the catalog already considered the two promoted spatial identities adapter-safe while non-England emission was still deliberately suppressed, so a v0.4 adapter-validation run cannot recreate those old scopes from scratch. The exact predecessor fingerprints remain valid historical states independently of that later adapter behavior.

## v0.5 evidence gates

Before authorizing a production write for any scope, require all of the following:

1. official source + adapter validation PASS for that league;
2. Spatial v1.2 audit PASS for the exact competition-season scope;
3. canonical local load PASS in PostgreSQL 17;
4. canonical + Data Mesh rerun idempotency PASS;
5. Player V2 repeated-calculation fingerprint PASS;
6. Wyscout semantic-version/comparability recertification where applicable;
7. generalized promotion job Full Quality PASS;
8. local promotion from fresh/current/predecessor state and rerun from the exact certified-complete state PASS;
9. read-only production preflight showing an acceptable fresh/current/predecessor target state;
10. explicit human authorization for the remote production write.

The five-league same-database predecessor-to-v0.5 upgrade simulation closed **PASS** in GitHub Actions run `32879286381` on 2026-08-25. The ephemeral PostgreSQL 17 run reconstructed `ENG_PL` from its certified v0.3 state and `ESP_LL`/`FRA_L1`/`GER_BL1`/`ITA_SA` from their exact certified pre-spatial states, verified those baseline fingerprints, upgraded all five scopes to the current v0.5 fingerprints, verified `long_passes_accurate` and `passes_into_final_third` were present while `progressive_passes` remained absent, reran all five current states, and proved exact fingerprint idempotency. No production database was accessed or written.

## Product semantics

A successful production promotion makes the historical scope discoverable by the scoped player read path because contexts are derived from real `analytics.product_player_detail_v2` scope keys, not a hardcoded England list.

Promotion does not make `2017/18` the current player season, does not populate the current-context Watchlist, and does not fabricate an overall ranking. When no publication-safe ranking exists, the product may expose the neutral analyzed-player directory and detailed evidence for the selected historical context.

`wyscout-open-v0.5` and `fi-wyscout-spatial-v1.2` support both `long_passes_accurate` and `passes_into_final_third` for the five independently audited core-league `2017/18` scopes. That code capability is not evidence that all five scopes are already live in the production database.

After each authorized production promotion, perform read-only database verification and real browser QA against the deployed production site before declaring that scope live. Remove any one-shot production operator immediately after successful promotion and verification.
