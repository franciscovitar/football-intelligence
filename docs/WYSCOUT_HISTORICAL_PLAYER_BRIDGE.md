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
3. runs the certified `wyscout-open-v0.2` adapter;
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
