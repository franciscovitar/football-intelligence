# Checkpoint 007 — Team Intelligence

## Status

**PASS**

## Objective

Persist and expose an explainable Team Analytics V1 that distinguishes process,
results, form, and Elo inside honest competition-and-season comparison scopes.

## Implemented

- `team-v1.0` Python analytics module with explicit observations, configuration,
  feature aggregation, scoring, confidence, diagnostics, and Elo;
- `last_3`, `last_5`, `last_10`, and equal-weight `season` windows, with a
  three-match half-life for recent form;
- competition/window-relative tied mid-rank percentiles;
- empirical finishing shrinkage with 20-shot and 8-shot-on-target priors;
- separate Attack, Chance Generation, Finishing Proxy, Defensive Process,
  Control, Process, Results, Overall, and confidence values;
- deterministic Results-vs-Process and strong-evidence diagnostic codes without
  luck or deservedness claims;
- isolated competition-and-season Elo with persisted match history;
- explicit PostgreSQL migration, constraints, contract tests, repository, and
  idempotent CLI job;
- `/teams` competition/window/confidence/name explorer;
- `/team/[id]` Performance, Form, Elo trend, dimensions, diagnostics, confidence,
  raw/stabilized evidence, and limitations;
- team populations and scope diagnostics in `/lab`;
- deterministic PostgreSQL fixture and full-stack CI smoke for team routes.

## Verified

- Ruff and Ruff format: PASS;
- mypy: PASS;
- Python tests: 26 unit tests PASS;
- PostgreSQL 17 migrations and all SQL contracts: PASS;
- PostgreSQL integrations: 3 PASS, including idempotent Team Analytics
  persistence and 12 Elo history rows;
- npm audit at high severity: PASS, zero vulnerabilities;
- Web ESLint and TypeScript: PASS;
- production Next.js build: PASS;
- real PostgreSQL smoke for `/`, `/rankings`, `/player/[id]`, `/teams`,
  `/team/[id]`, and `/lab`: PASS;
- browser content, framework-overlay, console-error, and navigation checks: PASS;
- PR Web / Analytics / Database jobs: PASS in both push and pull-request runs;
- merged `main` Web / Analytics / Database jobs: PASS.

## Evidence

- analytics/persistence commit: `b64daeb1a487d90199d5c412974e66c31f249588`;
- web/smoke commit: `d49324dfe0365796b139f14545f88def010173f6`;
- merge commit: `22c385b534c9f14689d48dc4280d036209d5b24f`;
- PR: https://github.com/franciscovitar/football-intelligence/pull/2;
- `main` CI: https://github.com/franciscovitar/football-intelligence/actions/runs/31594845392.

## Model and integrity boundaries

- missing team metrics remain missing and reduce confidence;
- red cards are excluded from V1;
- goals come from matches rather than player-stat aggregation;
- Process contains no goals or points;
- Elo is persisted even when detailed team statistics cannot support a score;
- rankings and Elo never mix disconnected competitions;
- UI wording does not infer tactics, causality, luck, or deservedness;
- model weights and Elo parameters remain V1 hypotheses for Block 12 calibration.

## Not verified / not claimed

- production Supabase/Vercel runtime configuration is not operationally
  certified;
- current-season provider access remains subject to the documented provider
  plan;
- no cross-league strength calibration, xG, tactical inference, tracking, or
  opponent-strength adjustment is claimed;
- browser QA verifies rendering and error state, not pixel-perfect behavior on
  every device.

## Next action

Start Block 8 — Expectation & Meta Intelligence.
