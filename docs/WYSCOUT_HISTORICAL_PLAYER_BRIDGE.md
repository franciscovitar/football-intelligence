# Wyscout Historical Player Bridge

Status: implementation path for **historical/deep** Wyscout Open evidence only.

Scope implemented by the loader:

- competition: `ENG_PL`
- season: `2017/18`
- provider: `wyscout-open`
- official source: Figshare collection `4415000`
- collection DOI: `10.6084/m9.figshare.c.4415000.v5`
- licence: CC BY 4.0
- certified source invariants: 380 matches, 20 teams, 603 roster/squad players, 643,150 events

This is **not current-season evidence** and must never be presented as such.

## Observed real-runtime verification

Verified on 2026-08-22 in an ephemeral GitHub Actions runner with PostgreSQL 17. The runtime used only the public Wyscout source and a temporary local database; no production/Neon database was accessed or written.

The first block below preserves the observed `wyscout-open-v0.2` baseline for
historical traceability. A later 2026-08-25 post-promotion runtime separately
verified the current v0.4 adapter and Player V2 path; those current counts are
recorded immediately after the baseline rather than rewriting history.

Observed first-load invariants:

- official source probe: 380 matches, 643,150 events, 603 roster/squad players — PASS;
- certified v0.2 adapter: 412,609 `NormalizedObservation` rows, 77/77 adapter-safe identities observed — PASS;
- canonical scope: 380 matches, 20 teams, 515 participating players;
- 10,443 `player_appearances` and 10,443 `player_match_stats` rows;
- 760 `team_match_stats` rows;
- 412,609 Data Mesh `source_observations`, equal to adapter output;
- conservative minutes policy withheld exposure for 41 red-card appearances and 99 zero-duration standardized appearances rather than inventing minutes;
- zero Player V2 score/feature snapshots were published.

Full-load idempotency was then verified by executing the same loader a second time against the same temporary database. All scoped counts remained identical, `football.teams` remained at 20 rows, Wyscout team-provider mappings remained at 20, and all 20 teams were recognized as already linked. Runtime evidence: GitHub Actions run `32596409687`.

Current v0.4 post-promotion verification (2026-08-25, ephemeral PostgreSQL 17):

- historical load: 380 matches, 20 teams, 515 participating players — PASS;
- 10,443 `player_appearances` and 10,443 `player_match_stats` rows;
- 433,126 Data Mesh `source_observations`;
- `long_passes_accurate`: 10,268 known player-match rows, 175 missing;
- `passes_into_final_third`: 10,249 known player-match rows, 194 missing;
- exact Player V2 season features: 384 `long_passes_accurate`, 377 `passes_into_final_third`;
- Passing dimension: 231 partial, 281 insufficient-data, 0 ready/scored;
- `progressive_passes` remained absent;
- repeated Player V2 calculation produced byte-identical reports — PASS.

A separate ESP_LL 2017/18 recertification compared `wyscout-open-v0.3` and
`wyscout-open-v0.4` over all 416,407 observations and found every field identical
except `semantic_version`; both ENG-only spatial metrics emitted zero observations
in Spain. Canonical payload SHA-256 remained
`29b23d96326fb82b94e6529ad951e4c1b3812d0617fff79a5d34d23bc2763eb5`.

## Command

From `analytics/`:

```bash
uv run football-intelligence-load-wyscout-historical \
  --database-url postgresql://...LOCAL... \
  --report /tmp/wyscout-historical-load.json
```

The job may acquire/reuse the official Figshare cache through the existing Wyscout probe, but the PostgreSQL target is strictly local-only:

- `--database-url` is explicit and required;
- ambient `DATABASE_URL` is never read;
- the shared libpq-aware local target guard is used;
- remote/production writes are rejected;
- no Vercel/Neon operation is performed.

## Safety sequence

Before opening PostgreSQL the loader:

1. runs the existing official Wyscout source probe and requires the published counts to reproduce;
2. loads the same cached payloads used by the certified adapter audit;
3. runs the current certified Wyscout adapter (`wyscout-open-v0.4` after the spatial v1.2 final-third promotion);
4. requires every adapter audit check to pass;
5. normalizes only the explicit subset supported by the existing canonical `football.*` schema.

Only then does one local PostgreSQL transaction begin.

## Canonical identity

Existing clubs are reused with the repository's deterministic `normalize_team_name()` rules. No fuzzy matching, similarity threshold, or LLM identity resolution is allowed.

If one Wyscout name maps to more than one canonical team, the job stops. If a Wyscout provider id already points at a canonical team whose normalized identity conflicts with the source name, the job stops.

When an existing canonical club is reused, its canonical `name`, `short_name`, and `country_code` are preserved. Historical Wyscout variants/nulls do not overwrite current canonical display metadata.

Players are **not** name-matched across providers. Wyscout players are keyed through their Wyscout provider ids. A future cross-provider merge must use validated player-crosswalk evidence; absence of such evidence stays unresolved.

## Missing vs zero

The canonical bridge only fills fields whose Wyscout semantics are already certified. Unsupported/ambiguous fields stay `NULL`.

Examples intentionally kept missing in the legacy canonical row include player tackles, blocks, dribbles and fouls drawn. A missing field is never converted into a synthetic zero merely to improve scoring coverage.

All certified adapter observations are additionally persisted in `ingestion.source_observations` with `metric_granularity`, source reference and semantic version, so evidence that does not fit the older canonical table is not discarded.

## Minutes methodology

Wyscout confirms regular matches and substitution minutes, but not an exact final-whistle timestamp. The canonical normalization therefore derives **standardized regular-90 analytics minutes** (`wyscout-regular-90-v1.0`): starter at minute 0, substitute at the published substitution minute, end at substitution-out minute or standardized 90.

Two exposures remain deliberately unavailable rather than guessed (`wyscout-regular-90-ambiguous-missing-v1.0`):

- red-card appearances whose exact end exposure is not certified by the participation primitive;
- appearances whose stoppage-time substitution clamps to a zero standardized interval.

Those appearances and their real stats remain stored, but `minutes=NULL`, so per-90 analytics cannot fabricate exposure.

## Why Player V2 snapshots are not published by this loader

The current product query chooses the most recently calculated real Player V2 context. It does not yet have an explicit historical-season routing contract. If this historical loader calculated 2017/18 snapshots now, the product could select them as its implicit active player context even though the main product is scoped around the latest completed season.

Therefore this loader intentionally stops at **canonical data + Data Mesh evidence**. It writes zero Player V2 product snapshots.

The next product step is explicit historical context selection/routing. Only after that exists should ENG_PL 2017/18 Player V2 snapshots be calculated and exposed to the web.

## Known limitation

Wyscout 2017/18 materially improves real player evidence, but it does not support every intended Player V2 metric/dimension (for example xG/xA/model-dependent and several progression/one-v-one/defensive primitives remain unavailable or pending). The scoring model must not be weakened or partially renormalized just to produce an overall ranking.
