# Production Bootstrap Sequence (V1 Closure Pass A/B preparation)

**Nothing in this document has been executed against the real production
database.** This is the documented, intended one-time sequence for
populating production with the already-certified real ENG_PL 2025/26
evidence, prepared as part of V1 Closure Pass A/B. Running it requires
separate, explicit user authorization -- see the Global Product Closure
Review's verdict (`CONDITIONAL`) and its Pass A description.

## Why this exists

The Global Product Closure Review found that production serves real,
honest empty states everywhere (`/`, `/team-rankings`, `/compare`,
`/results-vs-performance`, `/sources`) because the three jobs that could
populate it -- `load_real_snapshot.py`, `build_real_snapshot_v2.py`,
`execute_real_intelligence_v2.py` -- have apparently never been run against
the actual production database. Two of the three already refused any
remote database by design; the third (`load_real_snapshot.py`) had an
inconsistent implicit `DATABASE_URL` fallback. This pass closed that
inconsistency and added a single shared, explicit, triple-confirmed
production-write contract (`analytics/src/football_intelligence/db/production_write_guard.py`)
that all three jobs now use identically for a remote target. Nothing about
this pass performs a production write itself.

## The shared safety contract

A **local** `--database-url` (`localhost`/`127.0.0.1`/`::1`, or a host-less
local-socket DSN) is always accepted, exactly as before -- no behavior
change for local/dev usage of any of these jobs.

A **remote** `--database-url` is refused by every write-capable job unless
**all three** of the following are supplied together on the command line:

- `--allow-remote-write`
- `--confirm-target production`
- `--production-write-confirmation` with the exact phrase defined in
  `db.production_write_guard.PRODUCTION_WRITE_CONFIRMATION_PHRASE`
  (`"I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE"`)

None of these three is a secret or a credential, and none is ever read from
an environment variable -- they exist to make a production write
unmistakable and deliberate, never accidental. The actual access boundary
remains "you must already possess the real production `--database-url`."

`build_real_snapshot_v2.py`'s existing `--persist-audit-local` flag keeps
its exact original local-only meaning; a **separate**,
`--persist-audit-remote-production` flag (requiring the full confirmation
above) is the only way that job persists audit evidence to a remote
database, so a flag literally named "local" can never silently mean
"production."

The read-only preflight command below (Step 0 / Step 4) requires none of
this -- it never writes, so it accepts a remote `--database-url` directly.
It only ever reports a safe `scheme://host:port/dbname` string, never the
full DSN, user, password, or query string.

## Expected certified invariants

Reused from already-certified checkpoints (`docs/REAL_DATA_SNAPSHOT_V2.md`,
Block 19's own report contract) -- **not invented here**:

| Layer | Expected value |
| --- | --- |
| Canonical `football.matches` (ENG_PL 2025/26) | 380 |
| Canonical `football.teams` | 20 |
| Canonical `football.team_match_stats` (ENG_PL 2025/26 scope) | 760 (380 matches x 2 teams) |
| Team V2 score rows (`analytics.product_team_ranking_candidates_v2` scope) | 80 (20 teams x 4 windows: `last_3`/`last_5`/`last_10`/`season`) |
| Player V2 | remains `insufficient_data` -- zero approved domestic ENG_PL 2025/26 player-match evidence exists; `execute_real_intelligence_v2.py` never invokes the player engine on empty input |

Partial/insufficient evidence states for individual Team V2 dimensions
remain truthful and expected exactly as already documented
(`docs/PRODUCT_EXPERIENCE_V2.md`) -- reaching these row counts does not
imply every dimension becomes `ready`.

## The sequence

Every step must be idempotent or fail before performing an unsafe mutation.
**Never automatically proceed past an unexpected preflight result** -- if
production already contains state that contradicts the certified
invariants above, stop and reconcile before writing anything.

### Step 0 -- read-only production preflight (always safe, always first)

```
uv run football-intelligence-preflight-production \
  --database-url <the real production PostgreSQL URL>
```

Never writes (every query is rolled back, even on success). Reports:
canonical `football.*` competition/season/team/match/team-match-stat
presence and counts for ENG_PL 2025/26, the six `analytics.product_*_v2`
view row counts and any active team/player V2 scope, and the Data Mesh
`ingestion.source_observations`/`ingestion.reconciliation_decisions` counts
(plus a defensive `possible_test_smoke_leakage_count` check). Use its
output to decide which of Steps 1-3 are actually still needed -- do not
assume all three are missing without checking.

### Step 1 -- load the certified canonical snapshot (only if missing/incomplete)

Only if Step 0 shows `eng_pl_2025_26_season_exists: false`, or
`matches_count_scope` is not `380`, or `team_match_stats_count_scope` is
not `760`:

```
uv run football-intelligence-load-real-snapshot \
  --database-url <the real production PostgreSQL URL> \
  --allow-remote-write \
  --confirm-target production \
  --production-write-confirmation "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE"
```

Idempotent (upsert-based, unchanged by this pass). Loads from the
committed, unchanged `data/real/2025-26/eng_pl_matches.json` -- no new
snapshot data is fabricated or fetched fresh by this step.

### Step 2 -- persist the certified Data Mesh audit evidence (only if missing/incomplete)

Only if Step 0 shows `source_observations_count: 0` /
`reconciliation_decisions_count: 0` (or clearly stale):

```
uv run football-intelligence-build-real-snapshot-v2 \
  --database-url <the real production PostgreSQL URL> \
  --persist-audit-remote-production \
  --allow-remote-write \
  --confirm-target production \
  --production-write-confirmation "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE"
```

Writes only to `ingestion.source_observations` / `ingestion.reconciliation_decisions`
(audit-only) -- never `football.*`. Fetches Football-Data.co.uk (memory-only)
and OpenFootball (CC0, written to the committed snapshot directory) exactly
as it already does locally; no new data acquisition behavior.

### Step 3 -- execute Real Intelligence V2 (only after Step 1 passes)

Only once canonical `football.*` state matches the expected invariants
above:

```
uv run football-intelligence-execute-real-intelligence-v2 \
  --database-url <the real production PostgreSQL URL> \
  --allow-remote-write \
  --confirm-target production \
  --production-write-confirmation "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE"
```

Idempotent (delete-then-insert for the exact scope being replaced). Writes
Team V2 scores/features and Diagnostic Rule Engine findings with
`data_context = "real"`; never invokes the player engine (zero real
player-match evidence exists). Model semantics, scoring gates, and
diagnostic rules are completely unchanged by this pass -- only the database
target validation changed.

### Step 4 -- read-only post-write verification

```
uv run football-intelligence-preflight-production \
  --database-url <the real production PostgreSQL URL>
```

Confirm the expected row counts above, then verify against the real
production site (`https://football-intelligence-web.vercel.app`): `/`,
`/team-rankings`, `/sources` should now show real content instead of empty
states. This corresponds to `24 Deploy + Real QA` (Pass C of the Global
Product Closure Review), not a new implementation pass.

## Stop conditions

- Step 0 shows canonical or Data Mesh state that contradicts the certified
  invariants (e.g. a match count that is neither 0 nor 380) -- stop and
  reconcile, do not proceed to Step 1/2/3 assuming a clean slate.
- Any step raises rather than completing idempotently -- stop and diagnose
  before retrying; do not repeat a failing write against production.
- Step 0's `possible_test_smoke_leakage_count` is nonzero -- stop; this
  indicates non-certified data reached production through some other path.
