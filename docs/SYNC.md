# Core League Sync

Block 4 introduces one incremental synchronization engine for the six core
competitions:

- Argentina Liga Profesional (`ARG_LPF`)
- Premier League (`ENG_PL`)
- LaLiga (`ESP_LL`)
- Serie A (`ITA_SA`)
- Bundesliga (`GER_BL1`)
- Ligue 1 (`FRA_L1`)

## Incremental window

Scheduled runs query only a bounded UTC date window (three days by default).
Finished fixtures in that window are fetched individually by fixture `id`,
normalized, and persisted with the idempotent provider repository established in
Block 3.

Reprocessing the overlap window is intentional: late provider corrections are
absorbed by upserts without creating duplicate domain entities.

## Freshness

Each league result records:

- latest finished kickoff observed in the batch;
- age in hours at run time;
- freshness check timestamp;
- request count and normalized row counts.

The JSON report is an operational diagnostic, not a scoring input.

## Scheduling

`.github/workflows/core-sync.yml` runs daily and can also be triggered manually.
It requires:

- `API_FOOTBALL_KEY` GitHub Actions secret;
- `DATABASE_URL` GitHub Actions secret;
- `CORE_SYNC_SEASON` repository variable.

Raw audit/sync payloads are uploaded as a short-retention GitHub Actions artifact
for operational evidence. The long-term private Supabase Storage adapter remains
an infrastructure task before production retention guarantees are claimed.

## Request budget

Block 12 adds an explicit `--request-budget` argument (default `60`). Before
any provider request is made, the job computes the logical ceiling —
`league_count * (1 fixture-list request + max_fixtures_per_league detail
requests)` — and fails immediately if that ceiling exceeds the budget. With
the default six leagues and `--max-fixtures-per-league 8`, the ceiling is
`6 * 9 = 54`, comfortably inside the default `60`. This means a larger
`--max-fixtures-per-league` can no longer silently overspend quota; the run
fails fast with a clear message instead.

World Radar (external, non-core-league competitions) is a separate, manual
workflow — see [`WORLD_RADAR.md`](WORLD_RADAR.md).

## Provider-plan constraint

The API-Football Free plan is limited to 100 requests/day and limits available
seasons. Block 4 therefore keeps the season configurable instead of embedding
"current season" in code.

The synchronization engine can be certified against an accessible historical
season without pretending that the Free plan supplies current-season data.
Switching to a provider/plan with current-season access changes runtime
configuration, not the ingestion architecture.
