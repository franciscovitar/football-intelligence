# V1 Validation

Block 12 adds a validation/calibration layer that measures, audits, and
reports evidence for humans to act on. It never trains a model, never
auto-tunes weights, and never adjusts scoring config from a small sample.

Model version: `validation-v1.0`.

CLI: `football-intelligence-validate-v1` (`--database-url` optional/env,
`--report` required).

## Two kinds of status

- **`hard_status`** (`pass` / `fail`): a real contract or config violation —
  a bug. This is the only thing that makes the CLI exit non-zero.
- **`calibration_status`** (`pass` / `warn` / `insufficient_data`):
  informative. `insufficient_data` is never treated as a system error and
  never blocks the CLI or CI.

## B1 — Config invariants (hard gate)

Validates, for `player_analytics.config` and `team_analytics.config`:

- every weight group (`ROLE_SCORE_WEIGHTS` per role, and each of
  `CHANCE_GENERATION_WEIGHTS`, `DEFENSIVE_PROCESS_WEIGHTS`,
  `CONTROL_WEIGHTS`, `FINISHING_WEIGHTS`, `RESULTS_WEIGHTS`,
  `PROCESS_WEIGHTS`, `ATTACK_WEIGHTS`, `OVERALL_WEIGHTS`) sums to 1;
- every weight is finite and positive;
- every player metric direction is exactly `+1`/`-1`;
- every metric/dimension reference exists (`FEATURE_METRICS`,
  `DIMENSION_METRICS`, `ROLE_DIMENSIONS`).

Any violation is a **HARD FAIL**. The config itself is never modified by this
check.

## B2 — Elo real backtest (informative)

Uses `analytics.team_elo_history` (`expected_result` vs `actual_result`) as
real ground truth:

- **Brier score**: `mean((expected - actual)^2)`;
- **baseline Brier**: `mean((0.5 - actual)^2)` (a neutral, always-50/50
  predictor);
- **skill vs baseline**: `1 - model_brier / baseline_brier`;
- calibration bins (prediction buckets vs realized outcome), each carrying
  its own `absolute_error`;
- **Expected Calibration Error (ECE)** — a weighted mean of the absolute
  prediction/outcome gap across bins:
  `sum((bin_sample_size / total_sample_size) * abs(bin_average_prediction -
  bin_average_outcome))`;
- average prediction and average outcome.

With `sample_size < 50`: `status = insufficient_data` and
`calibration_error = None` (not a failure). With `sample_size >= 50`:
`status = pass` when `skill > 0`, else `status = warn`; `calibration_error`
is always computed once the sample is sufficient. ECE is **informative
only**: it is never a hard gate and never changes `calibration_status`.
`ELO_K_FACTOR` and `ELO_HOME_ADVANTAGE` are never changed automatically by
this check.

## B3 — Player stability (informative)

Compares `season` vs `last_10` `overall_score` for the same
player/scope/role/model in `analytics.player_score_snapshots`, restricted to
pairs where both windows have `confidence >= 0.5`, using **Spearman rank
correlation** computed with a small, dependency-free implementation.

This measures **rank stability/churn**, not predictive accuracy — it is
never reported as such. Roles with fewer than 20 qualifying pairs report
`insufficient_data`.

## B4 — Rating hard invariants (hard gate)

Audits `analytics.player_rating_snapshots`: it must be structurally
impossible for a persisted `underrated`/`overrated` row to violate the gates
the Rating Intelligence engine itself defines
(`MIN_RATING_CONFIDENCE`, `POLARIZATION_GATE`, `MIN_EVIDENCE_COUNT`,
`MIN_SCORED_EVIDENCE_COUNT`, `MIN_SCORED_SOURCE_COUNT`,
`MIN_PERCEPTION_CONFIDENCE`). These thresholds are imported directly from
`rating_intelligence.engine` — never duplicated as new magic numbers.

Any violation is a **HARD FAIL** (it would mean the engine wrote data that
breaks its own contract). Signal prevalence (`underrated`, `overrated`,
`aligned`, `polarized`, `insufficient_evidence`) is reported so no label can
silently dominate unnoticed.

## B5 — Tactical audit (mostly informative, with structural hard gates)

Audits `analytics.team_tactical_snapshots`:

- `formation_matches` must never exceed `matches` (**HARD FAIL** otherwise);
- unsupported tactical claims (`high_press`, `low_block`, `mid_block`,
  `counterattack`, `pressing_height`, `defensive_block_shape`, `player
  movement paths`, …) must never appear as a persisted signal (**HARD
  FAIL** otherwise);
- formation coverage and style/formation signal prevalence are reported;
- low coverage (`< 50%`) is `WARN`/informational, never a failure — this
  audit does not form football opinions.

## B6 — Ingestion cost / freshness (observability)

Summarizes `ingestion.ingestion_runs` for the last 30 days per job: run
count, total requests, max requests per run, succeeded vs failed/partial
count, and last successful run timestamp. This is observability, not exact
billing.

Alongside this, `core-league-sync` now takes `--request-budget` (default 60)
and fails **before any provider request** when
`6 * (1 + max_fixtures_per_league) > request_budget` — so a larger
`--max-fixtures-per-league` can no longer silently overspend the default
budget.

## Persistence

`analytics.model_validation_runs` stores `model_version`, `hard_status`,
`calibration_status`, a compact `summary` JSONB, the full `report` JSONB, and
`calculated_at`. Each CLI run inserts a new row (an append-only history, not
an upsert).

## Web

`/lab` shows the latest V1 Validation run compactly: hard gates, Elo
calibration status + sample size, player stability roles measured, rating
contract prevalence, tactical contract low-coverage count, and recent
ingestion job names. It stays diagnostic, not a dashboard.

## Scheduling

`core-sync.yml` runs `football-intelligence-validate-v1` after the other
analytics jobs and uploads its report as an artifact alongside them.
