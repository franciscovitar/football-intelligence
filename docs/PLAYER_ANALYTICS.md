# Player Analytics V1

Block 5 converts normalized match observations into role-aware player features,
percentiles, skill dimensions, an overall Performance score, and recent Form
windows.

## What V1 measures

The V1 model uses only fields already verified in the provider boundary:

- goals;
- assists;
- shots and shots on target;
- total passes as an involvement/style signal;
- key passes;
- tackles, blocks, interceptions;
- successful dribbles;
- duels won;
- fouls drawn and committed;
- goalkeeper saves.

It deliberately does **not** fabricate:

- player accurate-pass counts from API-Football's pass-accuracy percentage;
- clearances, which are not verified in the current fixture-player payload;
- xG/xA, progressive passes/carries, pressures, tracking, or spatial value metrics
  that the current provider contract does not supply.

## Roles

API-Football fixture data exposes broad positions such as `G`, `D`, `M`, and
`F`. V1 therefore uses four honest comparison groups:

- goalkeeper;
- defender;
- midfielder;
- forward.

The primary role is the position with the most minutes across the analyzed
season. `role_confidence` is the share of positioned minutes played in that
primary role.

V1 does not claim center-back/full-back/winger/number-10 precision without
verified positional data to support those distinctions.

## Per-90 normalization

Count features are converted to output per 90 minutes so players with different
playing time can be compared on rate rather than raw totals.

For `last_3`, `last_5`, and `last_10`, appearances receive exponentially
decaying weights with a three-appearance half-life. `last_5` is the main V1
**Form** view.

The `season` window uses equal weighting.

## Sparse event zero semantics

At the normalized storage boundary, provider `null` values remain `NULL` so raw
provider meaning is preserved.

At the analytics semantic layer, documented event-count fields are interpreted
as zero for a valid player appearance when API-Football emits `null` for a
zero-event match. This is necessary because the provider commonly represents
zero goals, assists, shots, tackles, and similar event counts sparsely.

This semantic conversion is limited to verified count fields. Unsupported
metrics remain excluded rather than silently converted.

## Defensive context adjustment

Tackles, interceptions, and blocks are opportunity-adjusted using team
possession before scoring. A player on a high-possession team has fewer
opponent-possession minutes in which to accumulate defensive actions, so the
same raw count receives more credit than on a low-possession team.

The adjustment normalizes observed defensive actions toward a 50% opponent
possession environment. If team possession is unavailable or invalid, the raw
count is used.

Raw per-90 values are still persisted separately from adjusted values.

## Shrinkage

Small samples can create extreme per-90 rates. Each role/window metric is
therefore shrunk toward the minutes-weighted role population mean:

- player evidence weight = `minutes / (minutes + 450)`;
- prior weight = the remainder.

The result stabilizes short samples without hiding the underlying raw per-90
value.

## Percentiles

After context adjustment and shrinkage, every feature is converted to a
percentile against players in the same broad role and scope.

Percentiles are role-aware because a tackle rate, shot rate, or key-pass rate
has different meaning for a defender, midfielder, and forward.

Ties receive their mid-rank percentile.

## Skill dimensions

V1 exposes interpretable dimension scores where the underlying metrics support
them:

- scoring;
- creation;
- carrying;
- defending;
- goalkeeping.

These are averages of directional metric percentiles, not opaque model outputs.

## Performance

`overall_score` is a 0-100 weighted combination of role-relevant percentiles.
The role templates are intentionally simple and versioned as `player-v1.0`.

Examples:

- forwards emphasize scoring, shot threat, creation, and carrying;
- midfielders balance creation, ball carrying, defensive output, duels, and
  some scoring;
- defenders emphasize context-adjusted defensive output and duels, with modest
  creation/carrying contribution;
- goalkeepers are provisional because the current provider contract gives V1
  only a narrow verified goalkeeper signal (`saves`).

These weights are product hypotheses, not permanent truth. Predictive
calibration belongs in Block 12.

## Confidence

The score is stored separately from confidence. Confidence reflects:

- minutes played;
- stability of the player's broad role;
- size of the comparison population;
- availability of role scoring inputs.

Goalkeeper confidence is capped in V1 because the current data contract is too
thin for a strong goalkeeper-quality model.

Consumers should be able to rank by score while filtering or visually
de-emphasizing low-confidence cases.

## Persistence

PostgreSQL stores:

- `analytics.player_feature_snapshots`;
- `analytics.player_score_snapshots`.

Snapshots are keyed by player, scope, window, and model version so model changes
remain explicit and reversible.

The default core scope is `core:<season>`.

## Scheduled pipeline

Once the Core League Sync workflow has real `DATABASE_URL`, `API_FOOTBALL_KEY`,
and `CORE_SYNC_SEASON` runtime configuration, it runs player analytics after
incremental ingestion and uploads a compact player-analytics report with the sync
evidence.

## Known V1 limitations

- no league-strength/opponent-strength adjustment yet;
- no xG/xA or action-value model;
- no detailed sub-role classification;
- goalkeeper model is intentionally provisional;
- model weights are not yet calibrated against predictive or scout outcomes;
- current-season data remains constrained by the provider plan documented in
  Block 4.

Those are explicit model boundaries, not hidden assumptions.
