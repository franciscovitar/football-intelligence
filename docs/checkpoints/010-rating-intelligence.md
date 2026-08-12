# Checkpoint 010 — Rating Intelligence

## Status

**PASS**

## Objective

Compare stable player performance with sufficiently supported external perception
to surface Underrated, Overrated, Consensus, and Polarization without allowing
article volume or unsupported sentiment guesses to dominate the result.

## Implemented

- `rating-v1.0`;
- deterministic English-first stance evidence model;
- source-balanced perception aggregation;
- evidence recency weighting;
- strong evidence/source/confidence gates;
- explicit Polarization gate before Overrated/Underrated;
- Consensus and Rating Gap;
- PostgreSQL snapshots and evidence breakdown;
- `/ratings` and player-detail Rating Intelligence;
- recalculation after football/meta and perception updates.

## Verified

- local Ruff / format / mypy: PASS;
- local targeted Rating tests: 5 passed;
- local full Python suite: 52 passed, 6 DB integrations skipped without `DATABASE_URL`;
- local npm audit high: 0 vulnerabilities;
- local ESLint / TypeScript / Next.js build: PASS;
- PR Quality run `31635612364`: Web / Analytics / Database PASS;
- PostgreSQL migrations, contracts, integrations, deterministic Rating calculation,
  and `/ratings` smoke: PASS;
- merged-main Quality run `31636641827`: Web / Analytics / Database PASS.

## Evidence

- implementation commit: `53a7587b2f15facf8945bdd1575d1996d4025148`;
- PR: https://github.com/franciscovitar/football-intelligence/pull/5;
- merge commit: `b7ec710bc9f24499ea2565e5474083694a1929dd`;
- PR CI: https://github.com/franciscovitar/football-intelligence/actions/runs/31635612364;
- main CI: https://github.com/franciscovitar/football-intelligence/actions/runs/31636641827.

## Boundaries

- no LLM-derived quantitative perception score;
- no market value or transfer recommendation;
- one source cannot create an Overrated/Underrated label;
- high polarization blocks forced Overrated/Underrated labels;
- V1 phrase rules are English-first and require calibration on real evidence;
- production public-feed operation and current-season provider configuration remain
  operational concerns separate from the CI-certified code path.

## Next action

Block 11 — Tactical Intelligence.
