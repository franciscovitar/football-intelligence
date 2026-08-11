# Data Model

## Scope

Block 2 establishes the provider-independent PostgreSQL foundation used by ingestion, analytics, and server-side reads.

The schema is deliberately conservative: it stores stable football entities, normalized match-level facts, provider mappings, and ingestion traceability. Provider-specific payload shapes stay outside the domain model.

## Schema boundaries

### `football`

Provider-independent football data:

- `competitions`
- `seasons`
- `teams`
- `players`
- `matches`
- provider-ID mapping tables
- `team_match_stats`
- `player_appearances`
- `player_match_stats`

### `ingestion`

External-provider and pipeline operations:

- `providers`
- `ingestion_runs`
- `raw_objects`
- `data_capabilities`

These schemas are intentionally separate from `public`. The application currently expects trusted server/batch access through PostgreSQL rather than browser access through the Supabase Data API.

If a schema is exposed through the Data API later, permissions and RLS must be designed explicitly before exposure.

## Identifier strategy

Domain entities use internal `bigint generated always as identity` primary keys.

Provider IDs never become domain primary keys. Each provider mapping table guarantees both:

- one external ID maps to at most one internal entity for a provider;
- one internal entity maps to at most one external ID for a provider.

This preserves the ADR-003 boundary and allows future provider replacement or reconciliation.

## Catalog

### `competitions`

Canonical competitions. `code` is a stable internal code, not a provider ID.

### `seasons`

A season belongs to one competition. Only one season per competition may be flagged `is_current` at a time.

### `teams`

Canonical club/team records. Team names are not globally unique because real football data can contain legitimate naming collisions.

### `players`

Canonical player records. No uniqueness constraint is placed on names because names are not identities.

### `matches`

A match belongs to a season and references two different teams. Scores remain nullable until known. A normalized status vocabulary prevents provider status codes from leaking beyond normalization.

## Normalized match facts

### `team_match_stats`

One row per match/team. Metrics are nullable and never default to zero.

### `player_appearances`

One row per match/player. Appearance context such as team, minutes, starter flag, captain flag, listed position, and shirt number lives here.

### `player_match_stats`

One row per appearance. Quantitative metrics are nullable and never default to zero.

A database trigger rejects team statistics or player appearances whose team is not one of the two teams in the referenced match.

## Missing data semantics

`NULL` means the metric was not available or not observed.

`0` means the metric was observed and its value was zero.

This distinction is mandatory because Block 3 will audit real API-Football coverage before scoring logic is allowed to depend on a field.

## Raw data traceability

Raw provider response bodies are not stored in relational tables.

`ingestion.raw_objects` stores only metadata needed to locate and verify an object in private object storage:

- storage bucket/path;
- endpoint;
- request fingerprint;
- fetch timestamp;
- HTTP status;
- content metadata;
- SHA-256;
- byte size;
- extra structured metadata.

This keeps raw payloads replayable without coupling the relational model to provider JSON.

## Ingestion runs

`ingestion.ingestion_runs` records batch lifecycle, scope, request counts, rows written, errors, and timing.

Terminal states (`succeeded`, `failed`, `partial`) require `finished_at`; a `running` job must not have one.

## Capability audit

`ingestion.data_capabilities` is the durable output of the Block 3 provider coverage audit.

It records, per provider/entity/metric:

- availability classification;
- sample size;
- non-null observations;
- observation timestamp;
- notes.

This prevents scoring code from assuming that a provider field is reliably populated.

## Core seeds

The seed file establishes:

- provider: API-Football;
- Liga Profesional;
- Premier League;
- LaLiga;
- Serie A;
- Bundesliga;
- Ligue 1.

It intentionally does not seed provider external IDs or seasons. Those come from verified provider data during Block 3.

## Indexes

Indexes are limited to current expected access paths:

- matches by season/kickoff;
- match history by home/away team;
- team stats by team/match;
- player appearances and player stats by player/match;
- ingestion runs by provider/start time;
- raw objects by run/fetch time.

Additional indexes require an observed query pattern.

## Validation

CI applies the migration to a fresh PostgreSQL 17 database, applies seeds, and executes `database/tests/001_schema_contract.sql`.

The contract test checks:

- required schemas/tables exist;
- core seeds exist;
- one-current-season invariant;
- match/team membership enforcement;
- missing-vs-zero semantics;
- provider mapping uniqueness;
- ingestion lifecycle constraints;
- raw object uniqueness;
- capability count integrity.
