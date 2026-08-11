# Sources

## API-Football

API-Football is the first structured football-data provider for V1.

### Boundary

Provider payloads are accepted only inside `analytics/.../providers` and
`analytics/.../normalization`. Provider IDs are persisted through mapping tables
and never become Football Intelligence primary keys.

### Block 3 audit strategy

The provider audit uses Premier League (`league=39`) season `2025` as a stable,
completed sample.

The audit intentionally uses few requests:

1. `GET /leagues?id=39&season=2025` to inspect provider-declared coverage.
2. `GET /fixtures?league=39&season=2025` to obtain fixture IDs.
3. `GET /fixtures?ids=...` for up to three recent completed fixtures.

API-Football documents that the multi-ID fixture request can return embedded
events, lineups, fixture statistics, and player statistics for up to 20 fixture
IDs in one call. This is preferred over multiplying endpoint-specific calls.

### Coverage rule

Provider-declared coverage is advisory, not proof of field completeness. The
project therefore records observed non-null coverage from real sampled payloads
before later scoring models depend on a metric.

A missing value stays `NULL`. Zero is only stored when the provider actually
returns zero.

Known V1 examples from the documented fixture-player shape:

- fixture player `passes.accuracy` is a percentage, not a verified accurate-pass
  count, so `player_match_stats.passes_accurate` remains `NULL`;
- a verified player clearance count is not assumed from undocumented fields.

### Raw data

Block 3 stores live audit payloads as deterministic gzip-compressed JSON through
`LocalRawStore`. PostgreSQL stores the corresponding traceability metadata when
persistence is enabled.

The production Supabase Storage adapter is deferred to Block 4, where scheduled
sync and live infrastructure are introduced together. This keeps the Block 3
provider audit independent from cloud provisioning while preserving the raw
storage contract.
