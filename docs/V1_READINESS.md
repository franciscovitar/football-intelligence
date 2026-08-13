# V1 Readiness

This document states, explicitly and without hedging, what "V1 done" means at
the end of Block 12 — and what it does not mean.

## CODE/CI READY vs PRODUCTION CERTIFIED

These are two different claims. **This document only claims the first.**

- **CODE/CI READY** — the code exists, is internally consistent (hard gates
  pass), is covered by unit/integration tests that run without hitting a real
  provider, and CI (lint/format/typecheck/tests/build/DB contracts/web smoke)
  passes on the branch and, once merged, on `main`.
- **PRODUCTION CERTIFIED** — the system has been deployed to real production
  infrastructure, verified against real user traffic and a real provider
  connection, and observed to behave correctly under those real conditions.

Blocks 1–11 are CODE/CI READY and CI-certified on `main`. **Block 12 does not
claim PRODUCTION CERTIFIED for any block**, including itself.

## What Block 12 verified

- Player/Team Analytics weight configuration is internally consistent
  (`validation-v1.0` B1 hard gate);
- Elo has a real backtest methodology against real match ground truth
  (`analytics.team_elo_history`), not an assumed accuracy number;
- Player score stability (not "predictive accuracy") has a measurement
  methodology;
- Rating Intelligence's confidence/polarization/evidence gates are audited
  as structurally unbreakable, not just "assumed correct";
- Tactical Intelligence's unsupported-claim boundary is audited as
  structurally unbreakable;
- Ingestion cost/freshness is observable per job for the last 30 days;
- `core-league-sync` now has an explicit, pre-flight request budget so a
  larger `--max-fixtures-per-league` cannot silently overspend;
- World Radar can detect offensive/creative candidates outside the core
  leagues with a small, explicit, pre-flight-checked request budget, without
  a misleading cross-league score comparison;
- CI exercises World Radar, Validation, and their web surfaces
  (`/radar`, `/lab`) entirely with deterministic fixtures — **no live
  provider network calls**.

## What is predictive vs descriptive (do not conflate these)

- **Predictive / calibration-checked**: Elo's `expected_result` vs a real
  Brier-score backtest against `actual_result`. This is the only signal in
  the system with a real accuracy claim, and even that claim is gated by
  sample size (`insufficient_data` below 50 matches).
- **Descriptive / stability, not accuracy**: player score rank correlation
  (season vs last_10). This describes how much a player's rank moves over
  time; it makes no claim about predicting future performance.
- **Structural, not predictive**: Rating and Tactical contract audits. These
  confirm persisted data respects the engine's own rules; they say nothing
  about whether the underlying football judgment is "correct."
- **Relative, not absolute**: World Radar scores. Percentile-ranked within
  one competition's candidate pool only — never a cross-league comparison.

## Known operational limitations (not hidden)

These remain open regardless of how much code and CI pass:

- **current-season API-Football access/config** is not yet certified for
  production use — core sync, perception sync, and World Radar all depend on
  a real, correctly configured provider subscription and season value in the
  target environment;
- **Supabase production secrets/environment** (the real `DATABASE_URL` used
  by production, as opposed to the ephemeral CI Postgres service) have not
  been verified in this block;
- **Vercel production deployment/QA** — the web app has not been deployed to
  and manually verified against a real production environment in this block;
- **World Radar has never been run against the live provider** — its CI
  coverage is entirely fixture-based; a first live `workflow_dispatch` run
  and manual review of its output is still pending;
- **Calibration confidence is limited by real historical sample size** — Elo
  and player-stability calibration will only become statistically meaningful
  once enough real match/season history has accumulated in production;
  `insufficient_data` today is the honest, expected state, not a failure to
  hide.

## Bottom line

Block 12 makes V1 **CODE/CI READY** end-to-end, including a real
calibration/audit layer and a cost/security-hardened World Radar. It does
**not** claim production certification, and the operational limitations above
are the explicit gate between "CI passed" and "safe to rely on in
production."
