# Wyscout Historical Player Bridge

Status: implementation path for **historical/deep** Wyscout Open evidence only.

The legacy local loader remains intentionally scoped to:

- competition: `ENG_PL`;
- season: `2017/18`;
- provider: `wyscout-open`;
- official source: Figshare collection `4415000`;
- collection DOI: `10.6084/m9.figshare.c.4415000.v5`;
- licence: CC BY 4.0;
- certified England source invariants: 380 matches, 20 teams, 603 roster/squad players, 643,150 events.

This is **not current-season evidence** and must never be presented as such. Multileague production promotion uses the separate, scope-explicit `promote_historical_player_v2` path documented in `docs/HISTORICAL_PLAYER_PRODUCTION_PROMOTION.md`; expanding that path does not silently broaden this legacy loader command.

## Historical England verification

The original real runtime was executed in an ephemeral GitHub Actions runner with PostgreSQL 17 using only the public Wyscout source and a temporary local database.

The pre-spatial baseline established:

- official source probe: 380 matches, 643,150 events, 603 roster/squad players — PASS;
- 380 matches, 20 teams, 515 participating players in the canonical scope;
- 10,443 `player_appearances` and 10,443 `player_match_stats`;
- 760 `team_match_stats`;
- 412,609 Data Mesh observations in the original certified state;
- conservative minutes withheld unsafe exposure for red-card and zero-duration standardized appearances;
- full loader rerun idempotency PASS.

Subsequent promotions advanced the same England scope without rewriting that historical evidence:

- v0.3 long-pass state: 422,877 Data Mesh observations / 38,737 Player V2 features;
- v0.4 final-third-capable runtime: 433,126 Data Mesh observations / 40,513 Player V2 features;
- v0.5 keeps the same England spatial methodology/output while expanding the two independently audited spatial metrics to the other four core leagues.

For the current England Spatial v1.2 path:

- `long_passes_accurate`: 10,268 known player-match rows, 175 missing;
- `passes_into_final_third`: 10,249 known player-match rows, 194 missing;
- exact Player V2 season features: 384 long-pass, 377 final-third;
- Passing: 231 partial, 281 insufficient-data, 0 ready/scored;
- `progressive_passes`: absent;
- repeated Player V2 calculation: idempotent PASS.

## v0.5 multileague evidence

Spatial v1.2 was independently audited on `ESP_LL`, `FRA_L1`, `GER_BL1`, and `ITA_SA` 2017/18 before their adapter scopes were enabled in the v0.5 candidate. Real product-path runs exercised adapter -> normalization -> PostgreSQL -> Player Analytics read path -> Player V2 for each league and produced these stable current fingerprints:

| Scope | Data Mesh observations | V2 scores | V2 features |
| --- | ---: | ---: | ---: |
| `ENG_PL` | 433,126 | 2,048 | 40,513 |
| `ESP_LL` | 437,170 | 2,224 | 43,881 |
| `FRA_L1` | 435,814 | 2,148 | 42,300 |
| `GER_BL1` | 352,942 | 1,888 | 37,413 |
| `ITA_SA` | 441,225 | 2,132 | 41,996 |

Those are code/runtime certification fingerprints. They are **not** a claim that all five scopes have been written to production.

The v0.4 -> v0.5 ESP_LL semantic-version recertification compared complete real-source output and found all 416,407 previously emitted non-spatial `NormalizedObservation` facts identical after excluding only `semantic_version`. v0.5 added exactly 10,380 `long_passes_accurate` and 10,383 `passes_into_final_third` observations for the independently audited Spain scope. The non-spatial canonical digest was unchanged:

```text
7594f0bf71c6c0deffee5c0d44d8784aaa4b04edf7d1d9766801cbbdabbb5c69
```

Existing Wyscout x StatsBomb comparability policies therefore carry forward only for identities already reviewed before v0.5. The new spatial identities still have no cross-provider comparability policy and fail closed to `methodology_pending`.

## Local loader command

From `analytics/`:

```bash
uv run football-intelligence-load-wyscout-historical \
  --database-url postgresql://...LOCAL... \
  --report /tmp/wyscout-historical-load.json
```

The job may acquire/reuse the official Figshare cache through the existing Wyscout probe, but its PostgreSQL target is strictly local-only:

- `--database-url` is explicit and required;
- ambient `DATABASE_URL` is never read;
- the shared libpq-aware local target guard is used;
- remote/production writes are rejected;
- no Vercel/Neon operation is performed.

Before opening PostgreSQL it runs the official Wyscout source probe, loads the certified cached payloads, validates the current Wyscout adapter, and normalizes only fields supported by the canonical schema. Only then does one local PostgreSQL transaction begin.

## Canonical identity

Existing clubs are reused with deterministic `normalize_team_name()` rules. No fuzzy matching, similarity threshold, or LLM identity resolution is allowed.

If one Wyscout name maps to more than one canonical team, the job stops. If a Wyscout provider id already points at a canonical team whose normalized identity conflicts with the source name, the job stops.

When an existing canonical club is reused, canonical display metadata is preserved. Historical Wyscout variants/nulls do not overwrite current names.

Players are **not** name-matched across providers. Wyscout players are keyed through Wyscout provider ids. Cross-provider merge requires independently validated player-crosswalk evidence; absent evidence remains unresolved.

## Missing versus zero

The bridge only fills fields whose semantics are certified. Unsupported or ambiguous values stay `NULL`.

A missing field is never converted into zero to improve coverage. All certified adapter observations are additionally persisted in `ingestion.source_observations` with granularity, source reference and semantic version so evidence that does not fit the older canonical table is not discarded.

Spatial v1.2 keeps this guarantee through Player V2: `long_passes_accurate` and `passes_into_final_third` season/window aggregates are emitted only when every contributing player-match has an exact value for that metric.

## Minutes methodology

Wyscout confirms regular matches and substitution minutes but not an exact final-whistle timestamp. Normalization therefore uses standardized regular-90 analytics minutes (`wyscout-regular-90-v1.0`): starter at 0, substitute at the published substitution minute, end at substitution-out minute or standardized 90.

Two exposures remain deliberately unavailable (`wyscout-regular-90-ambiguous-missing-v1.0`):

- red-card appearances whose exact end exposure is not certified;
- appearances whose stoppage-time substitution clamps to a zero standardized interval.

Those appearances and their real statistics remain stored, but `minutes=NULL`, so per-90 analytics cannot fabricate exposure. This policy can make product-runtime season-feature coverage slightly lower than a geometry-only audit; that is expected.

## Product publication boundary

The legacy loader intentionally stops at canonical data + Data Mesh evidence. Historical Player V2 publication belongs to the scope-explicit promotion job because the product must know which historical competition-season context it is exposing.

A scope supported by the adapter/promotion code is not automatically live. Remote production writes still require the explicit guarded production procedure, followed by read-only database verification and browser QA.

## Known limitation

Wyscout 2017/18 materially improves real player evidence but does not support every intended Player V2 input. In particular, `progressive_passes` remains blocked, and several xG/xA/model-dependent, progression, one-v-one and defensive primitives remain unavailable or methodology-pending. The scoring model must not be weakened or partially renormalized merely to produce an overall ranking.
