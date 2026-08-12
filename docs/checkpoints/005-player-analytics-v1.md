# Checkpoint 005 — Player Analytics V1

## Status

**PASS**

## Objective

Turn normalized player match data into transparent, role-aware, versioned player
features and rankings suitable for the first usable product surface.

## Implemented

- broad role assignment from verified position data (`G`, `D`, `M`, `F`);
- minutes-weighted role confidence;
- per-90 player feature rates;
- exponentially weighted `last_3`, `last_5`, and `last_10` Form windows;
- equal-weight season window;
- semantic zero handling for sparse documented event counts;
- possession-opportunity adjustment for tackles, interceptions, and blocks;
- empirical shrinkage toward role/window population means;
- role-specific percentiles;
- interpretable skill dimensions;
- role-weighted 0-100 Performance score;
- independent score confidence;
- explicit provisional goalkeeper confidence cap;
- PostgreSQL feature and score snapshot tables;
- model version `player-v1.0`;
- scheduled player analytics step after core-league ingestion;
- role/scoring architecture ADR and model documentation.

## Verified

- pure player analytics unit tests: PASS;
- sparse-zero regression test: PASS;
- role assignment regression test: PASS;
- recency-weighted Form regression test: PASS;
- possession-context regression test: PASS;
- PostgreSQL player analytics integration: PASS;
- snapshot replacement/idempotency: PASS;
- analytics database constraints: PASS;
- Ruff: PASS;
- mypy strict: PASS;
- full pytest suite: PASS;
- Web / Analytics / Database GitHub Actions: PASS.

## Evidence

- implementation commit: `9ea1241172c1820c0203fe227518f01954b2abce`;
- database syntax repair commit: `79757a2c7fdffd42471354f8106ab191150e77d1`;
- CI run validating the repaired implementation: https://github.com/franciscovitar/football-intelligence/actions/runs/31549563203.

## Repair note

The first CI run for the implementation exposed a PostgreSQL syntax error because `window` was used as an unquoted column name. PostgreSQL treats `WINDOW` as syntax. The persisted column was renamed to `window_key` consistently in the migration, repository inserts, and database contract tests. The Python domain field remains `window` because the conflict exists only at the SQL identifier boundary.

## Model boundaries

Player V1 is intentionally transparent rather than falsely precise.

- Position comparison is broad-role only.
- `passes_total` is persisted as an involvement/style feature and is not used as
  direct evidence of passing quality.
- `passes_accurate` is excluded because the verified fixture payload provides a
  percentage, not a trusted accurate-pass count.
- `clearances` are excluded because that field is not verified in the current
  fixture-player contract.
- Goalkeeper quality is provisional because V1 has only a narrow verified saves
  signal.
- League/opponent strength adjustment is not yet included.
- Weights are hypotheses versioned as `player-v1.0`; predictive calibration is
  deferred to Block 12.

## Product interpretation

`season` represents stabilized Performance across the available season sample.

`last_5` is the primary Form view and uses exponential recency weighting rather
than treating all recent appearances equally.

Scores are never intended to be read without confidence. Low-minute players can
still surface as interesting outliers, but the UI should visibly distinguish
them from high-confidence rankings.

## Next action

Start Block 6 — First Usable Web. Read `analytics.player_score_snapshots` and
`analytics.player_feature_snapshots` to expose role rankings, Form vs Performance,
skill dimensions, confidence, and transparent metric explanations.
