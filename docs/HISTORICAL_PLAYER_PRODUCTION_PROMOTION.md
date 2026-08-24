# Historical Player Production Promotion

Status: operational contract for promoting one certified Wyscout Open `2017/18` European core-league scope into the production PostgreSQL database.

This procedure is historical-only. It does not add a current/day-to-day provider. `ENG_PL 2017/18` has already been promoted to production; the other certified scopes remain separate, explicitly authorized production operations.

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
2. the certified scoped Wyscout adapter validation;
3. canonical normalization with the documented conservative minutes policy;
4. deterministic canonical team reuse / provider mapping;
5. canonical `football.*` persistence;
6. Wyscout Data Mesh observation persistence scoped by provider + season + `competition_external_id`;
7. Player V1 compatibility + Player V2 calculation for the selected explicit competition scope;
8. exact per-league post-write invariant checks;
9. commit only after every check passes.

An exception before the final commit leaves the transaction uncommitted. Separate leagues are intentionally separate transactions so one failed scope does not silently widen or partially commit another.

## Production safety

`--database-url` is mandatory and never inferred by this job. Remote targets use the shared `db.production_write_guard` contract and require all four signals:

```text
--allow-remote-write
--confirm-target production
--production-write-confirmation "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE"
--confirm-database-target "<exact safe target from read-only preflight>"
```

Before any production write, run the existing read-only preflight against the same database URL and inspect its credential-free `target`. The target must then be supplied exactly to `--confirm-database-target`.

The promotion additionally verifies the actually connected libpq target before issuing writes.

Production execution remains a distinct authorization gate. Merging the generalized job does not itself authorize or perform a remote write.

## Allowed pre-write states

The selected historical scope must be either:

- completely fresh: no selected `2017/18` season/canonical rows, no Wyscout observations for that provider competition, and no Player V2 score/feature rows for its explicit scope; or
- already equal to that league's complete certified canonical + Data Mesh + Player V2 state from an earlier successful run.

Any partial or unexpected state fails closed instead of being repaired automatically. Existing `ENG_PL 2017/18` Wyscout observations cannot make another league appear complete because Data Mesh prewrite counts include the provider-native `competition_external_id`.

## Certified invariants

These invariants are pinned from independent real-byte evidence over Wyscout Open / Figshare and ephemeral PostgreSQL 17. They are not learned from the production write itself.

| Scope | Matches | Teams | Players | Appearances | Data Mesh observations | V2 scores | V2 features | Season players | >=450 min | `performance` ready |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ENG_PL` | 380 | 20 | 515 | 10,443 | 412,609 | 2,048 | 26,841 | 512 | 385 | 385 |
| `ESP_LL` | 380 | 20 | 557 | 10,555 | 416,407 | 2,224 | 29,008 | 556 | 415 | 415 |
| `FRA_L1` | 380 | 20 | 542 | 10,515 | 415,230 | 2,148 | 28,007 | 537 | 395 | 395 |
| `GER_BL1` | 306 | 18 | 472 | 8,501 | 336,265 | 1,888 | 24,786 | 472 | 349 | 349 |
| `ITA_SA` | 380 | 20 | 534 | 10,573 | 420,506 | 2,132 | 27,872 | 533 | 403 | 403 |

For every scope, player-match stat rows equal appearance rows and team-match stat rows equal two times the match count.

Player V2 evidence-state totals are also pinned:

| Scope | `insufficient_data` | `partial` | `ready` overall | Ranking candidates | Non-null overall scores |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ENG_PL` | 1,754 | 294 | 0 | 0 | 0 |
| `ESP_LL` | 1,880 | 344 | 0 | 0 | 0 |
| `FRA_L1` | 1,822 | 326 | 0 | 0 | 0 |
| `GER_BL1` | 1,596 | 292 | 0 | 0 | 0 |
| `ITA_SA` | 1,774 | 358 | 0 | 0 | 0 |

A changed source/model result is a stop condition, not permission to change the ranking confidence gate, renormalize partial dimensions, convert missing evidence to zero, or fabricate an overall score.

## Evidence gates before a new league promotion

Before authorizing a new production write for a scope, require all of the following:

1. official source + adapter validation PASS for that league;
2. canonical local load PASS in PostgreSQL 17;
3. full canonical + Data Mesh rerun idempotency PASS;
4. Player V2 first/second calculation fingerprint PASS;
5. generalized promotion job Quality PASS;
6. generalized promotion job executed locally against a fresh database and rerun from its exact certified-complete state;
7. read-only production preflight showing an acceptable fresh/certified-complete target state;
8. explicit human authorization for the remote production write.

## Product semantics

A successful promotion makes the historical scope discoverable by the scoped player read path because contexts are derived from real `analytics.product_player_detail_v2` scope keys, not a hardcoded England list.

Promotion does not make `2017/18` the current player season, does not populate the current-context Watchlist, and does not fabricate an overall ranking. When no publication-safe ranking exists, the product may expose the neutral analyzed-player directory and detailed evidence for the selected context.

After each production promotion, perform read-only database verification and real browser QA against the deployed production site before declaring that scope live. Remove any one-shot production operator immediately after successful promotion and verification.
