# Checkpoint 002 — Data Foundation

## Status

**PASS**

## Objective

Establish the provider-independent PostgreSQL data foundation required before connecting a real football provider.

## Implemented

- internal `football` and `ingestion` schemas outside `public`;
- internal identity keys for competitions, seasons, teams, players, and matches;
- separate provider mappings for competitions, teams, players, and matches;
- normalized team match statistics;
- player appearances and player match statistics;
- explicit `NULL` versus observed-zero semantics for metrics;
- match/team membership enforcement in the database;
- ingestion run lifecycle metadata;
- raw object storage traceability metadata without relational raw payloads;
- durable provider data capability audit table;
- idempotent core seeds for API-Football and the six core competitions;
- focused indexes for expected history and ingestion access paths;
- `docs/DATA_MODEL.md`;
- PostgreSQL 17 schema contract validation in GitHub Actions.

## Verified

- migration applies to a fresh PostgreSQL 17 database: PASS;
- core seed script applies after migration: PASS;
- required schemas and tables exist: PASS;
- one-current-season-per-competition invariant: PASS;
- match/team membership trigger: PASS;
- provider external-ID uniqueness: PASS;
- missing metric remains `NULL` while observed zero remains `0`: PASS;
- ingestion terminal-state timing invariant: PASS;
- raw storage object uniqueness: PASS;
- capability sample/non-null count integrity: PASS;
- existing Web quality job: PASS;
- existing Analytics quality job: PASS;
- Database quality job: PASS;
- full GitHub Actions `Quality` workflow: PASS.

## Evidence

- implementation commit: `1fc49e529e836828e2989b98cc5131d274b96a63`;
- CI run: https://github.com/franciscovitar/football-intelligence/actions/runs/31537662414.

## Security

The normalized and ingestion tables live in custom schemas rather than `public` and no Data API grants are added. Browser/Data API exposure is therefore not part of this block. If either schema is exposed later, grants and RLS must be designed explicitly first.

No real credentials or provider secrets are committed.

## Not part of this block

- live Supabase project provisioning or migration deployment;
- Supabase Storage bucket creation;
- API-Football credentials or requests;
- provider external IDs and real seasons;
- ingestion/normalization Python modules;
- scoring or analytics models.

Those external/runtime concerns begin in Block 3, where real provider coverage must be measured before analytics depend on fields.

## Risk

Low. The migration is additive, tested against a fresh database, and does not touch production or a live Supabase project.

## Next action

Start Block 3 — Provider + Data Audit from this checkpoint. Connect API-Football for one league, persist raw + normalized data, verify idempotent upserts, and populate real capability coverage before defining scoring dependencies.
