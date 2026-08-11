# Checkpoint 003 — Provider + Data Audit

## Status

**PASS**

## Objective

Connect API-Football through a provider boundary, normalize a real football sample,
verify PostgreSQL persistence/idempotency, preserve raw replayability, and measure
observed field coverage before analytics models depend on provider fields.

## Implemented

- server-side API-Football client with bounded retry/error handling;
- provider response/quota metadata;
- deterministic gzip raw JSON storage contract;
- provider-independent fixture/team/player normalization;
- PostgreSQL provider repository and internal-ID mappings;
- idempotent normalized upserts;
- ingestion run and raw-object traceability;
- data-capability coverage calculation;
- fixture-based integration test against PostgreSQL;
- live audit CLI;
- Free-plan compatible fixture details using singular id, not restricted ids.

## Verified

- local Ruff: PASS;
- local mypy strict: PASS;
- local pytest: PASS;
- PostgreSQL persistence integration in CI: PASS;
- Web / Analytics / Database GitHub Actions: PASS;
- live API-Football authentication: PASS;
- live Premier League season 2024 access: PASS;
- three completed fixtures fetched with singular fixture IDs: PASS;
- team and player statistics returned and normalized: PASS;
- raw payloads stored with SHA-256 traceability: PASS;
- observed metric coverage report generated: PASS.

## Evidence

- original provider implementation: $ExpectedHead;
- Free-plan compatibility fix: $FixSha;
- CI for compatibility fix: https://github.com/franciscovitar/football-intelligence/actions/runs/31542315376;
- live audit report: docs/audits/api-football-premier-league-2024.json;
- live API requests: 5;
- sampled fixture IDs: 1208402, 1208401, 1208400.

## Live coverage findings

- possession_pct: 100.0% (6/6) - available
- shots_total: 100.0% (6/6) - available
- passes_accurate: 100.0% (6/6) - available
- goals: 7.5% (9/120) - partial
- shots_total: 31.67% (38/120) - partial
- passes_total: 75.83% (91/120) - partial
- passes_accurate: 0.0% (0/120) - unavailable
- clearances: 0.0% (0/120) - unavailable
- duels_total: 70.0% (84/120) - partial

Provider-declared coverage remains advisory. Later scoring code must use observed
coverage and confidence rather than assuming every documented field is complete.

## Provider-plan findings

The Free plan used for certification rejected season 2025 and the multi-fixture
ids parameter. Season 2024 plus singular ixtures?id=... requests were
verified live. The audit uses five requests for three fixtures and remains well
within the Free-plan daily request budget.

## Security

API_FOOTBALL_KEY is read only from the process environment/hidden prompt.
It is not written to Git, reports, raw JSON paths, logs by application code, or
documentation.

## Not part of this block

- production Supabase provisioning;
- scheduled multi-league synchronization;
- Supabase Storage adapter;
- scoring models.

## Next action

Start Block 4 — Core League Sync from this checkpoint, reusing the verified
provider boundary, persistence path, raw contract, and measured capabilities.