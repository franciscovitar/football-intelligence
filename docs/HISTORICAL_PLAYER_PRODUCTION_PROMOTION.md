# Historical Player Production Promotion

Status: operational contract for promoting the already-certified Wyscout Open `ENG_PL 2017/18` scope into the production PostgreSQL database.

This procedure is historical-only. It does not add a current/day-to-day provider.

## Scope

The promotion job is:

```text
python -m football_intelligence.jobs.promote_historical_player_v2
```

It performs, in one PostgreSQL transaction:

1. the official Wyscout source probe and published-count verification;
2. the certified Wyscout adapter audit;
3. canonical normalization with the documented conservative minutes policy;
4. deterministic canonical team reuse / provider mapping;
5. canonical `football.*` persistence;
6. Wyscout Data Mesh observation persistence;
7. Player V1 compatibility + Player V2 calculation for the explicit scope `competition:ENG_PL:2017/18`;
8. exact post-write invariant checks;
9. commit only after every check passes.

An exception before the final commit leaves the transaction uncommitted.

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

## Allowed pre-write states

The historical scope must be either:

- completely fresh: no `ENG_PL 2017/18` season/canonical rows, no Wyscout observations for the scope and no Player V2 rows; or
- already equal to the complete certified state from an earlier successful run.

Any partial or unexpected state fails closed instead of being repaired automatically.

## Certified invariants

The full Wyscout 2017/18 runtime previously certified in ephemeral PostgreSQL is rechecked before commit:

| Layer | Expected |
| --- | ---: |
| Matches | 380 |
| Teams in scope | 20 |
| Participating players | 515 |
| Player appearances | 10,443 |
| Player-match stat rows | 10,443 |
| Team-match stat rows | 760 |
| Wyscout Data Mesh observations | 412,609 |
| Player V2 score snapshots | 2,048 |
| Player V2 feature snapshots | 26,841 |
| Season player profiles | 512 |
| Season profiles with >=450 min | 385 |
| `performance` ready | 385 |
| Overall ranking candidates | 0 |
| Non-null overall scores | 0 |

Evidence-state totals must remain `1,754 insufficient_data` and `294 partial`. A changed source/model result is a stop condition, not permission to alter thresholds.

## Product semantics

A successful promotion makes the historical context queryable by the product read path added in PR #25. It does not make `2017/18` the current player season, does not populate the current-context Watchlist, and does not fabricate an overall ranking.

After promotion, perform read-only verification and real browser QA against production before declaring the historical player experience live.
