# Sources

## Source-compliance register

Unknown permission is not certification. This table records the basis used by
the repository; it is not a legal opinion.

| Source | Permission/licence basis | Automated collection | Redistribution | Method | Scope / completeness | State |
| --- | --- | --- | --- | --- | --- | --- |
| Football-Data.co.uk | Publisher provides direct season CSV downloads and a column key; no explicit redistribution licence was located | Yes | Unknown | Direct `mmz4281/<season>/<division>.csv` download | ENG_PL 2025/26: 380/380 matches, 20 teams; selected match/team fields, no player metrics | Not certified for redistribution |
| StatsBomb Open Data | Official repository publishes JSON for research/analysis and requires attribution under its user agreement | Yes | Unknown in this repository (no standalone redistribution licence relied on) | Official GitHub raw JSON | FIFA World Cup 2022 validation sample only; never ENG_PL | Validation-only, not domestic production data |
| Fantasy Premier League | FPL terms prohibit automated systems used to access the game and extract information | No | No permission established | None; collector/client and derived files removed | No domestic player coverage | Prohibited for this implementation |
| API-Football | Existing V1 provider integration; plan/credential terms apply | No calls in Block 16 corrective pass | Unknown | Existing authenticated API integration only | Historical V1 paths; not used to fill the Block 16 gap | Not a Block 16 real-snapshot source |

Snapshot retrieval details:

- Football-Data.co.uk: `2026-08-15T00:27:07.021474+00:00`, direct E0 2025/26 CSV.
- StatsBomb WC2022: see `data/validation/wc2022/wc2022_validation_sample.json` provenance.
- FPL: no retained dataset and no automated retrieval path.

## API-Football

API-Football is the first structured football-data provider for V1.

### Boundary

Provider payloads are accepted only inside `analytics/.../providers` and
`analytics/.../normalization`. Provider IDs are persisted through mapping tables
and never become Football Intelligence primary keys.

### Block 3 audit strategy

The certification audit uses Premier League (`league=39`) season `2024`, a
completed season available to the Free plan during Block 3 verification.

The live audit intentionally stays small:

1. `GET /leagues?id=39&season=2024` to inspect provider-declared coverage.
2. `GET /fixtures?league=39&season=2024` to obtain completed fixture IDs.
3. Three `GET /fixtures?id=FIXTURE_ID` requests for the sampled matches.

This is five provider requests total for a three-match sample.

API-Football documents that a single `fixtures?id=FIXTURE_ID` response includes
the fixture's embedded events, lineups, fixture statistics, and player
statistics. The API also supports a multi-fixture `ids` parameter on plans where
that parameter is available; the Free plan used during certification rejected
`ids`, so Football Intelligence deliberately uses the portable single-`id`
path for this audit.

The season is passed explicitly. During Block 3 verification the Free plan also
rejected season `2025` and reported historical access through `2024`; this is a
provider-plan limitation, not a domain assumption.

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
`LocalRawStore`. PostgreSQL stores corresponding traceability metadata when
persistence is enabled.

The production Supabase Storage adapter is deferred to Block 4, where scheduled
sync and live infrastructure are introduced together.
