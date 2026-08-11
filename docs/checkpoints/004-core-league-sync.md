# Checkpoint 004 — Core League Sync

## Status

**PASS**

## Objective

Expand the verified provider path to all six core competitions with one bounded,
idempotent synchronization engine, scheduled execution wiring, and freshness
reporting.

## Implemented

- central six-league provider catalog;
- configurable season rather than hardcoded "current" season;
- bounded incremental date window with intentional overlap;
- singular fixture-detail calls compatible with the verified Free-plan path;
- normalization and PostgreSQL upserts reused from Block 3;
- per-league freshness/request/row reporting;
- daily + manual GitHub Actions workflow;
- runtime secret/variable guards;
- short-retention raw/report workflow artifacts;
- unit tests for catalog, fixture selection, and deterministic windows;
- operational documentation in `docs/SYNC.md`.

## Verified

- Ruff: PASS;
- mypy strict: PASS;
- pytest: PASS;
- existing PostgreSQL integration suite: PASS in GitHub Actions;
- Web / Analytics / Database Quality jobs: PASS;
- live API-Football sync probe across all six configured core leagues: PASS;
- six distinct league IDs returned usable completed fixtures for the certification window: PASS;
- live request budget stayed below the Free daily quota: PASS.

## Evidence

- implementation commit: `28c3c25782e61d2033e8869b752742de862172b8`;
- CI: https://github.com/franciscovitar/football-intelligence/actions/runs/31546568225;
- live certification report: `docs/audits/api-football-core-leagues-2024.json`;
- live requests: 12.

## Live certification scope

The live probe uses season `2024` because the API-Football Free plan used by this
project does not provide current-season access. This verifies the six-league
synchronization engine and provider mappings without claiming current-data
freshness.

## Production constraint

**Current-season scheduled sync is configuration-blocked by provider-plan access,
not by application code.** The first API-Football paid plan is materially above
the project's target data budget, so Block 4 does not silently introduce it.

The GitHub Actions workflow is structurally ready but requires repository secrets
`API_FOOTBALL_KEY`, `DATABASE_URL`, and variable `CORE_SYNC_SEASON` before an
operational scheduled run can succeed.

Long-term private raw-object retention in Supabase Storage is also not claimed;
scheduled runs retain raw/report evidence as GitHub Actions artifacts for 30 days.

## Risk

Moderate. The sync engine is verified across all six leagues, but real current
football requires a current-season-capable provider/plan. This constraint must be
resolved before the user-facing product is described as current.

## Next action

Start Block 5 — Player Analytics V1 against the normalized historical fixture
dataset while keeping current-season provider selection as an explicit
infrastructure/cost decision before public launch.
