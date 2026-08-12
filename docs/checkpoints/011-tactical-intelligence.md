# Checkpoint 011 — Tactical Intelligence

## Status

**PASS**

## Objective

Add nominal formation profiles and evidence-backed tactical summaries by reusing
existing fixture-detail ingestion, without claiming spatial precision (pressing
height, block shape, counterattack frequency, player movement paths) the
available data cannot support.

## Implemented

- `tactical-v1.0`;
- nominal formation ingestion reusing the existing fixture detail payload
  (no additional provider request per fixture);
- `football.team_match_lineups` with a strict nominal-formation format check;
- Control, Attacking Volume, and Defensive Resistance tactical proxies derived
  from Team Intelligence dimensions;
- Formation stability/variability signal;
- explicit `claims_not_supported` allowlist (pressing height, defensive block
  shape, counterattack frequency, player movement paths);
- PostgreSQL snapshots (`analytics.team_tactical_snapshots`);
- `/tactics` and team-detail tactical context panel.

## Verified

- local Ruff / format / mypy: PASS;
- local Python test suite: 56 passed, 7 DB integrations skipped without `DATABASE_URL`;
- local npm audit high: 0 vulnerabilities;
- local ESLint / TypeScript / Next.js build: PASS;
- PR Quality run `31640669877`: Web / Analytics / Database PASS;
- PostgreSQL migrations, contracts, integrations, deterministic Tactical
  calculation, and `/tactics` + team-detail smoke: PASS;
- merged-main Quality run `31641009281`: Web / Analytics / Database PASS.

## Evidence

- implementation commit: `fbb68d2`;
- CI-fix commit: `18fd52aef95fa759cfcdc3c8a2efbbce529766d9`;
- PR: https://github.com/franciscovitar/football-intelligence/pull/6;
- merge commit: `7910328f7147f1abe3b3d14da390d9b1ad0fa7f8`;
- PR CI: https://github.com/franciscovitar/football-intelligence/actions/runs/31640669877;
- main CI: https://github.com/franciscovitar/football-intelligence/actions/runs/31641009281.

## Boundaries

- offense/defense proxies stay relative to Team Intelligence dimensions, not
  absolute tactical labels;
- formation is nominal (as reported by the provider lineup), never inferred
  from tracking or event data;
- no pressing height, defensive block shape, counterattack frequency, or
  player movement path claims;
- production public-feed operation and current-season provider configuration
  remain operational concerns separate from the CI-certified code path.

## Next action

Block 12 — World Radar + Calibration + V1 Hardening.
