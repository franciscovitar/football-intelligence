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
inconsistency and added a single shared, explicit, quadruple-confirmed
production-write contract (`analytics/src/football_intelligence/db/production_write_guard.py`)
that all three jobs now use identically for a remote target. A follow-up
hardening pass then closed a real gap in how "local" was determined (see
"Target parsing" below) and added the fourth, exact-target confirmation.
Nothing about either pass performs a production write itself.

## Target parsing: the effective target, not just the authority hostname

The naive `urllib.parse.urlsplit(database_url).hostname` check used before
this hardening pass could be fooled: PostgreSQL's `hostaddr` connection
parameter, when present, is the real network address libpq connects to --
`host` becomes verification/SNI-only -- and a URI query parameter can
itself be named `host=`, overriding the authority hostname entirely. Both
are invisible to `urlsplit`. A DSN conceptually like
`postgresql://localhost/db?hostaddr=<remote-ip>` would previously have
passed local validation despite genuinely connecting to a remote host.

`db.target_parsing.parse_database_target` (used by both
`db.local_safety.validate_local_database_url` and
`db.production_write_guard.resolve_database_target`, so "local" means the
same thing everywhere) now resolves the connection string through
psycopg's own libpq-aware conninfo parser (`psycopg.conninfo.conninfo_to_dict`
-- no new dependency) and classifies `hostaddr` (when present) as the
effective target, never the bare authority hostname. It also fails closed
(`SystemExit`) on a `service`/`servicefile` reference (points at external,
uninspectable connection parameters) and on a comma-separated multi-host/
multi-port DSN (this bootstrap tooling only ever targets exactly one
database). Ordinary single-host Neon-style URLs with `sslmode`/similar
options, and ordinary local URLs, are unaffected.

## Ambient libpq environment variables (a second hardening pass)

`psycopg.conninfo.conninfo_to_dict` is a pure string parser -- it never
consults the process environment. Real libpq does, for any of
`host`/`hostaddr`/`port`/`dbname` a connection string leaves unset: it
falls back to `PGHOST`/`PGHOSTADDR`/`PGPORT`/`PGDATABASE` before its own
compiled-in default. Two concrete gaps this closed: a host-less
`postgresql:///db` with `PGHOST=remote.example.com` set would previously
have been assumed to be an always-local Unix socket, when real libpq opens
a TCP connection to `remote.example.com`; and `postgresql://expected.example.com/db`
with `PGHOSTADDR=<other-ip>` set would actually reach `<other-ip>`, not
`expected.example.com`. `parse_database_target` now reproduces libpq's
exact, documented environment-variable precedence for those four
parameters (never a heuristic guess), so bootstrap commands' target
classification and reported target always match what libpq will really
do -- they never silently rely on ambient `PGHOST`/`PGHOSTADDR`/`PGPORT`/
`PGDATABASE`/`PGSERVICE` defaults for their answer.

`PGSERVICE`/`PGSERVICEFILE` are handled more strictly: either one being set
fails closed (`SystemExit`) unconditionally, because a `pg_service.conf`
entry can supply its own host/port/dbname that this lightweight parser has
no way to inspect.

**A remote production write goes one step further than general
classification**: it also requires a target with *zero* ambient
environment involvement -- every one of host/hostaddr, port, and dbname
must come from `--database-url` itself, not from a `PG*` fallback, and
`port`/`dbname` may not be silently left to libpq's own compiled-in
default either. A one-time production write must never depend on ambient
shell state at all. (Local classification and the read-only preflight stay
libpq-accurate and environment-aware as described above -- this extra
restriction applies only to the highest-stakes remote-write confirmation
path.)

## The shared safety contract

A **local** effective target (`localhost`/`127.0.0.1`/`::1`, or a host-less
local-socket DSN) is always accepted, exactly as before -- no behavior
change for local/dev usage of any of these jobs.

A **remote** effective target is refused by every write-capable job unless
**all four** of the following are supplied together on the command line:

- `--allow-remote-write`
- `--confirm-target production`
- `--production-write-confirmation` with the exact phrase defined in
  `db.production_write_guard.PRODUCTION_WRITE_CONFIRMATION_PHRASE`
  (`"I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE"`) -- proves
  "I intend to write to production."
- `--confirm-database-target` with the **exact** safe target description
  (`postgresql://<host>[:<port>]/<dbname>`, no username/password/query
  string) that the read-only preflight (Step 0) reported for this
  `--database-url` -- proves "I intend to write to *this* production
  database." Without this, an unchanged copied confirmation phrase from a
  previous, different production target would still pass; this flag forces
  a human to look at, and re-affirm, the real target every time the DSN
  changes.

None of these four is a secret or a credential, and none is ever read from
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
It only ever reports the same safe `postgresql://<host>[:<port>]/<dbname>`
string, never the full DSN, user, password, or query string -- and prints
it in a form that can be copied directly into `--confirm-database-target`
(along with which, if any, `PG*` environment variables contributed to it,
so a `--confirm-database-target` copied from the preflight can never be
built from a write-capable job's own rejected, partly-ambient target).
After connecting, it additionally asks libpq itself (via psycopg's
`Connection.info`, backed by `PQhost`/`PQhostaddr`/`PQdb`) what target it
really reached and fails loudly on any disagreement with what was
validated pre-connect, so the printed target is guaranteed to be the one
actually used, not merely a pre-connect guess. Its own inspection
transaction is additionally put into PostgreSQL's `READ ONLY` mode as its
first SQL statement, so the database engine itself -- not just application
discipline -- refuses any accidental write.

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
  --production-write-confirmation "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE" \
  --confirm-database-target "<exact target reported by Step 0>"
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
  --production-write-confirmation "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE" \
  --confirm-database-target "<exact target reported by Step 0>"
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
  --production-write-confirmation "I UNDERSTAND THIS WRITES TO THE REAL PRODUCTION DATABASE" \
  --confirm-database-target "<exact target reported by Step 0>"
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
- A write-capable job's `--confirm-database-target` does not exactly match
  its own `--database-url`'s parsed target -- fails closed by design; re-run
  Step 0 and copy its current reported `target` fresh rather than reusing an
  old one.
