# Real Data Snapshot V2 (Block 18)

Block 16/17 already produced a real, single-source ENG_PL 2025/26 match/team
snapshot from Football-Data.co.uk (see `docs/STATISTICAL_MODEL_V2.md`'s "Real
season snapshot" section and `data/real/2025-26/README.md`). Block 18 turns
that into an **auditable, reconciled, reproducible** snapshot: it adds a
second, independent, public-domain current source (OpenFootball), runs both
through the existing Data Mesh resolve-then-reconcile pipeline, and reports
real coverage against the full, dynamic Metric Catalog V2 in a
machine-readable manifest. It does not change what `load_real_snapshot.py`
loads into `football.*` -- that remains the single already-trusted,
**unchanged** Football-Data.co.uk file.

A corrective pass on the initial Block 18 implementation (documented
throughout this file) fixed three safety issues found in review: conflating
"latest completed season" with "current period" coverage, an implicit
database-write path via a bare `DATABASE_URL` environment variable, and the
job rewriting the committed, not-yet-certified-for-redistribution
Football-Data.co.uk file as an unreviewed side effect. All three are fixed
below.

## Temporal semantics: this is the latest COMPLETED season, not "current"

ENG_PL 2025/26 is the latest **completed** Premier League season. As of the
implementation date (2026-08-15), it is not the true current period -- that
would be 2026/27, which this job does not acquire. Two facts must stay
separate and are never conflated in the manifest, the job's output, or this
document:

- **Provider freshness capability** -- whether a source CAN structurally
  report current data. `coverage_lab.provider_capabilities` already
  classifies `football-data-uk` and `openfootball` as `freshness_role ==
  "current"` (they are continuously updated feeds, not static historical
  archives).
- **Period actually acquired by this snapshot** -- `latest_completed`,
  always, for every run of `build-real-snapshot-v2`. A current-*capable*
  provider serving a completed season never becomes current-*period*
  coverage.

The manifest expresses this with a top-level `"period_role":
"latest_completed"` field and four mutually-exclusive metric-coverage
buckets (see below): `available_current_period_identity_count` is always
`0` for this job; the real evidence lives under
`available_recent_completed_identity_count`. A regression test
(`tests/test_build_real_snapshot_v2.py::test_current_capable_provider_serving_a_completed_season_never_becomes_current_period`)
proves a current-capable provider's completed-season evidence can never
leak into the current-period bucket.

## What we have

- **Match facts, fully real, for the whole completed season.** 380/380
  ENG_PL 2025/26 matches, 20/20 clubs, from Football-Data.co.uk's published
  `mmz4281/2526/E0.csv`.
- **A second, independent real source for the same matches.** OpenFootball's
  public-domain (CC0) `football.json` repository (`2025-26/en.1.json`), 380
  matches, 20 clubs, fetched and normalized the same way.
- **Real, measured cross-source agreement.** Running both sources through
  the existing `data_mesh.pipeline.resolve_and_reconcile` produces **1,140
  agreed decisions out of 1,140 real match-fact observations** (`home_score`,
  `away_score`, `status` for all 380 matches) -- both independent sources
  report identical results for every match. Zero conflicts on match facts,
  zero unresolved identities. This is concrete evidence the primary
  Football-Data.co.uk file `load_real_snapshot.py` already loads is
  correct, not merely assumed correct.
- **20 real, documented team-name conflicts.** The two sources use different
  exact strings for the same real club (Football-Data.co.uk's short form,
  e.g. "Wolves", vs OpenFootball's official long form, "Wolverhampton
  Wanderers FC"). Both resolve to one logical team identity (see "Entity
  resolution" below) -- the mismatch is on the literal `name` string, not on
  which real club is meant, and is recorded as a real `conflict` decision,
  never silently picked or hidden.
- **Team-match statistics from Football-Data.co.uk only.** `shots_total`,
  `shots_on_target`, `fouls`, `corners`, `yellow_cards`, `red_cards` -- 4,560
  observations, correctly `single_source` (OpenFootball publishes no
  team-match statistics at all).
- **Zero player-level data of any kind.** Neither real source publishes it;
  see "Rich player data decision" below.

## What we still do not have

- Any true **current-period** (2026/27) evidence of any kind -- this
  snapshot is `latest_completed` only.
- Any domestic ENG_PL 2025/26 **player**-level statistics (shots, passes,
  defensive actions, minutes, or advanced metrics such as xG/xA at player
  grain).
- Team-level `possession_pct`, `passes_total`/`passes_accurate`,
  `shots_inside_box`/`shots_outside_box`, `blocked_shots`, `offsides`,
  `goalkeeper_saves`, or any expected-output (xG/xGA) metric for ENG_PL
  2025/26 -- Football-Data.co.uk's published columns do not include them,
  and OpenFootball publishes match results only.
- Cross-league strength calibration (unchanged, documented V1/V2
  limitation).

## Metric Catalog V2 coverage (this snapshot only)

Computed live from `metric_catalog.METRIC_CATALOG_V2` every run -- never a
hardcoded denominator that could drift from the real catalog. As of this
implementation the live catalog reports **194 identities** (154 raw, 40
derived) across all 9 grains; this number is read from the code, not fixed
in this document.

| | Count | Identities |
| --- | --- | --- |
| Catalog identities (total) | 194 | -- |
| **Current period** (2026/27; never claimed by this job) | **0** | -- |
| **Recent completed season** (this snapshot, ENG_PL 2025/26) | **9** | `home_score@match`, `away_score@match`, `status@match`, `shots_total@team_match`, `shots_on_target@team_match`, `fouls@team_match`, `corners@team_match`, `yellow_cards@team_match`, `red_cards@team_match` |
| Historical/deep only (StatsBomb Open Data, never current) | 22 | see `coverage_lab.provider_capabilities` |
| Unavailable | 163 | everything else -- overwhelmingly player-level (finishing, creation, progression, passing, 1v1, defence, ball-winning, aerial, goalkeeping) and team process/tactical (pressing, transition, build-up, set pieces, chance quality) |

These four figures are mutually exclusive and are never blended into one
percentage (per `docs/ZERO_COST_COVERAGE.md`'s coverage-state discipline) --
"true current period", "recent completed season", "only ever available from
a historical/deep source", and "unavailable" answer different questions and
must stay legible separately. `0 + 9 + 22 + 163 = 194`.

**Player V2's twelve scoring dimensions** (Performance, Underlying
Performance, Finishing, Shot Generation, Creation, Progression, Passing, 1v1,
Defence, Ball Winning, Aerial, Goalkeeping) and **all fourteen Team V2
dimensions except Attack/Defence's most basic shot-count inputs** remain
`insufficient_data` for this real snapshot -- exactly as Block 16 already
found and Block 18 reconfirms with a second independent source, not a
smaller-scope re-measurement.

## Rich player data decision

Block 18 re-ran the source search from `AGENTS.md` section 5 seriously, not
ceremonially (full detail: `docs/REAL_DATA_SOURCE_AUDIT_V2.md`):

- **Fantasy Premier League**: rejected. Terms explicitly prohibit automated
  extraction; re-verified 2026-08-15, unchanged since Block 16.
- **StatsBomb Open Data**: does not publish ENG_PL 2025/26 at all (its
  domestic-league coverage is historical and partial; only FIFA World Cup
  2022 is fully published). Confirmed not usable for this snapshot's player
  gap, only for validating that the engine's richer metric families work
  against real event data (`data/validation/wc2022/`).
- **OpenFootball**: publishes match results only, no player data.
- **FBref, SofaScore, FotMob, Understat, Transfermarkt, ESPN hidden
  endpoints, Bundesliga.com scraping, repackaged Kaggle/GitHub datasets**:
  all rejected on the same source-policy grounds as `AGENTS.md` section 5 --
  scraping, unofficial/private endpoints, or unverifiable upstream rights.
  None was implemented, none was even trialled for data extraction.
- **API-Football**: existing authenticated V1 integration, out of scope for
  a zero-cost real-snapshot block; not called in Block 18.

**Result: rich player source found = NO.** This is the honest, evidence-based
Block 18 finding, not a target count that was missed. Player-level Metric
Catalog V2 cells stay `unavailable`, never fabricated.

## Reproducing the snapshot

```
cd analytics
uv run football-intelligence-build-real-snapshot-v2
```

This is the single reproducible command for Block 18. It:

1. fetches Football-Data.co.uk's published `mmz4281/2526/E0.csv` **in
   memory only** -- it never rewrites the committed
   `data/real/2025-26/eng_pl_matches.json` (see "Source storage" below);
2. fetches OpenFootball's published `2025-26/en.1.json` and writes
   `data/real/2025-26/eng_pl_matches_openfootball.json` in the same
   provenance-tagged shape (safe to commit -- CC0);
3. normalizes both into `NormalizedObservation`s through the existing
   adapters;
4. resolves entity identity and reconciles the two sources through the
   existing `data_mesh.pipeline.resolve_and_reconcile` (the same pipeline
   the Block 13 PoC and Zero-Cost Coverage Lab already use);
5. measures coverage against the live Metric Catalog V2, keeping temporal
   roles separate (see above);
6. writes `data/manifests/real/ENG_PL/2025-26.json`, including a SHA-256
   content fingerprint for every source fetched this run.

Only `--competition ENG_PL --season "2025/26"` (the defaults) are
implemented; any other value exits with an explicit error rather than
silently reporting coverage that was never acquired.

No token/auth is required for any step. Total live requests per run: 2
(one CSV, one JSON) -- bounded, zero-auth, well under any provider's
documented rate limit.

## Database safety: no implicit writes, ever

The initial Block 18 implementation read `DATABASE_URL` from the
environment and wrote audit evidence whenever it happened to be set -- a
generic `DATABASE_URL` in a real deployment is not evidence that the target
is local or safe to write to. This is now fixed:

- **`DATABASE_URL` is never read from the environment**, for reads or
  writes. Only an explicit `--database-url` CLI value is ever considered.
- **`--database-url` alone never triggers a write.** By itself it only
  enables a read-only canonical-state check (`assess_real_snapshot`,
  select-only, always rolled back).
- **Writing audit evidence requires the explicit `--persist-audit-local`
  flag**, in addition to `--database-url`. `--persist-audit-local` without
  `--database-url` is a CLI error (`SystemExit`).
- **Any `--database-url` value is validated before any connection is
  attempted**: the scheme must be `postgresql`/`postgres` and the host must
  be `localhost`, `127.0.0.1`, `::1`, or absent (a host-less DSN, which
  libpq resolves to a local Unix-domain socket). Anything else -- a real
  hostname, an IP outside the loopback range, an unrecognized scheme --
  is rejected with a clear error, before a socket is ever opened.
- This job **never writes to `football.*`** in any case, flag or no flag.
  When persistence is enabled, only `ingestion.source_observations` /
  `ingestion.reconciliation_decisions` (audit-only) are written -- the same
  boundary the Block 13 PoC and Zero-Cost Coverage Lab already use.

```
# Read-only canonical-state check only (no writes, requires a local DB):
uv run football-intelligence-build-real-snapshot-v2 \
  --database-url postgresql://postgres:postgres@localhost:5432/football_intelligence_dev

# Also persist reconciliation evidence to ingestion.* (audit-only):
uv run football-intelligence-build-real-snapshot-v2 \
  --database-url postgresql://postgres:postgres@localhost:5432/football_intelligence_dev \
  --persist-audit-local

# Default (no flags): no database interaction of any kind, even if
# DATABASE_URL happens to be set in the shell.
uv run football-intelligence-build-real-snapshot-v2
```

The canonical `football.*` load remains a separate, unchanged step -- still
reading the unmodified, committed Football-Data.co.uk file:

```
uv run football-intelligence-load-real-snapshot --database-url <local-url>
```

## Source storage: no new redistribution claim

The initial Block 18 implementation refreshed and rewrote
`data/real/2025-26/eng_pl_matches.json` (the Football-Data.co.uk file) on
every run. That file's redistribution permission is recorded as **unknown**
(`docs/REAL_DATA_SOURCE_AUDIT_V2.md`) -- silently rewriting it as a side
effect of an unrelated corrective/reconciliation pass would have implicitly
extended a redistribution claim that was never reviewed. This is now fixed:

- `data/real/2025-26/eng_pl_matches.json` is reverted to, and `build-real-snapshot-v2`
  never touches, the exact Block 16/17 content
  (`ede8d25`/`ade6b5c`, unchanged through `fe8dae4`). It remains the sole
  canonical `football.*` load source.
- Block 18's fresh Football-Data.co.uk acquisition (needed to reconcile
  against OpenFootball) is **memory-only**: the CSV is fetched, parsed, and
  discarded after this run's reconciliation and fingerprinting -- no file is
  written for it at all, tracked or otherwise. This is stricter than a
  gitignored cache (there is nothing to `.gitignore` because nothing is
  written).
- OpenFootball's normalized evidence continues to be committed
  (`data/real/2025-26/eng_pl_matches_openfootball.json`) -- its CC0 licence
  makes that safe, unlike Football-Data.co.uk's unresolved redistribution
  status.
- Every source actually fetched this run gets a fingerprint in the
  manifest's `source_files` array: `provider`, `source_locator`,
  `collection_method`, `retrieved_at`, `sha256` (of the exact response
  bytes, before any decoding/re-serialization), `byte_size`,
  `competition_code`, `season_label`, `redistribution_permission`,
  `certification_state`, and where the evidence was (or explicitly was not)
  persisted. OpenFootball's upstream URL points at mutable `master`, so its
  content SHA-256 -- not a fixed commit -- is the real integrity anchor;
  the manifest notes that the upstream Git commit SHA is deliberately not
  captured (it would require a second network request per run for no
  functional benefit here).

## Idempotency (verified against a real local PostgreSQL 17 instance)

Running the full pipeline (`build-real-snapshot-v2 --database-url <local>
--persist-audit-local` then `load-real-snapshot --database-url <local>`)
twice against a fresh database, back to back:

| | Run 1 | Run 2 |
| --- | --- | --- |
| `football.matches` | 380 | 380 |
| `football.teams` | 20 | 20 |
| `football.team_match_stats` | 760 | 760 |
| `ingestion.reconciliation_decisions` | 5,720 | 5,720 |

Canonical state and reconciliation decisions are exactly stable across
reruns -- no duplicate entities, no duplicate canonical facts. The raw
`ingestion.source_observations` audit table is an append-only, per-fetch
observation log keyed on `(provider, entity, metric, observed_at)`; because
`observed_at` is the real timestamp of that fetch, a rerun legitimately logs
a new observation event per run (the same behavior the existing Block 13 PoC
job already has) rather than a duplicate of the same fact. This is by
design for an audit trail, not a defect in the canonical snapshot.

## Entity resolution notes (Block 18 addition)

Football-Data.co.uk's short club names ("Man City", "Nott'm Forest",
"Wolves", ...) do not share tokens with OpenFootball's official long names
("Manchester City FC", "Nottingham Forest FC", "Wolverhampton Wanderers
FC", ...) even after the existing generic stopword-stripping
(`fc`/`sc`/`sv`/...). `data_mesh/entity_resolution.py` adds:

- `afc` to the generic corporate-suffix stopword list (fixes "AFC
  Bournemouth" / "Sunderland AFC" automatically, same mechanism as the
  existing `fc` handling);
- a small, explicit, reviewed alias table
  (`_ENGLISH_SHORT_NAME_ALIASES`) for the 9 real ENG_PL clubs whose short
  form does not converge with the long form through stopword-stripping
  alone (Brighton, Leeds, Man City, Man United, Newcastle, Nott'm Forest,
  Tottenham, West Ham, Wolves) -- verified against all 20 real committed
  club names from both sources, never a fuzzy/edit-distance guess, in the
  same spirit as the existing `munich` -> `munchen` cross-language alias.

All 20 real clubs resolve to one logical team identity across both sources;
0 unresolved entities in the combined 8,360-observation snapshot.

## Handoff to Block 19

- The canonical `football.*` ENG_PL 2025/26 snapshot (match + team-stat
  evidence only) is real, reproducible, idempotent, and now cross-validated
  by a second independent source with 100% match-fact agreement.
- This snapshot is `latest_completed`, never current-period -- Block 19 must
  not treat it as, or report it as, live/current-season evidence.
- `football-intelligence-score-real-snapshot` continues to correctly report
  `insufficient_data` for player scoring -- there is still no permitted
  player-match evidence to score. Block 19 must not treat this as a bug to
  route around; it is the accurate state of available real data.
- If a compliant rich player-data source becomes available in the future,
  the existing `player_analytics` V2 job and `analytics.player_score_snapshots`
  read path (already built, Block 16) apply unchanged -- no new pipeline is
  needed on the scoring side, only a new adapter feeding real
  `player_match`/`goalkeeper_match` observations through the existing
  entity-resolution and load path.
- Team V2 dimensions that need xG/xGA or team process stats
  (`sterile_possession`, `few_but_high_quality_chances_allowed`, chance
  quality, pressing, transition, build-up) remain `insufficient_data` for
  ENG_PL 2025/26 real data; this is unchanged by Block 18 and is not a
  regression.
- Any future job that connects to a database should follow this job's
  pattern: never read a bare `DATABASE_URL` from the environment, require
  explicit opt-in for writes, and validate the target is clearly local
  before connecting.
