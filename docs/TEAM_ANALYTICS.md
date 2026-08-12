# Team Analytics V1

Block 7 converts finished matches and normalized team-match statistics into
competition-relative team features, scores, deterministic diagnostics, and Elo
history. The model version is `team-v1.0`.

## Comparison scope

Every score and percentile is calculated inside one competition and season:

```text
competition:<competition_code>:<season>
```

V1 never creates a global ranking across disconnected leagues. League styles,
possession environments, and Elo graphs are not calibrated across competitions.

## Match observations and missing data

Goals and points come from `football.matches`. Creation, opponent creation, and
control inputs come from `football.team_match_stats`.

- missing team statistics remain missing, never zero;
- ratios are produced only when their denominators exist and are positive;
- pass share requires both teams' pass totals;
- red cards are excluded because audited coverage is unreliable;
- Elo still uses every finished match with a valid result when detailed team
  statistics are absent.

## Windows and percentiles

The supported windows are `last_3`, `last_5`, `last_10`, and `season`.
`last_5` is Team Form. For recent windows, match `i` receives weight:

```text
w_i = 0.5 ^ (i / 3)
```

where `i = 0` is the most recent match. The season window gives every match
equal weight. Ties receive the same deterministic mid-rank percentile behavior
as Player Analytics.

When a composite has some, but not all, inputs, its declared weights are
renormalized over the available inputs. Missing inputs are not assigned neutral
percentiles. A score is not emitted when Process or Results cannot be calculated
responsibly.

## Exact score definitions

All components are 0-100 competition/window-relative percentile composites.
Opponent-volume percentiles are inverted before Defensive Process is calculated,
so higher is always better.

### Chance Generation

- shots on target for: 40%;
- shots inside the box for: 30%;
- total shots for: 20%;
- corners for: 10%.

This is attacking-event volume, not xG or chance quality.

### Defensive Process

- inverse opponent shots on target: 45%;
- inverse opponent shots inside the box: 35%;
- inverse opponent total shots: 20%.

This is chance suppression, not goals conceded.

### Control proxy

- possession: 50%;
- pass accuracy: 30%;
- pass share: 20%.

Low control is not automatically bad football, and the score is not a tactical
dominance claim.

### Finishing Proxy

- stabilized goals per total shot: 55%;
- stabilized goals per shot on target: 45%.

Each ratio is shrunk toward its competition/window population rate:

```text
adjusted_rate = (weighted_goals + prior * population_rate)
                / (weighted_denominator + prior)
```

The conservative V1 priors are 20 total shots and 8 shots on target. This proxy
reflects shot quality, player quality, game state, and variance as well as
conversion; it is not pure finishing skill.

### Attack, Process, Results, and Overall

```text
Attack  = 70% Chance Generation + 30% Finishing Proxy
Process = 40% Chance Generation + 35% Defensive Process + 25% Control
Results = 60% points per match percentile + 40% goal difference per match percentile
Overall = 65% Process + 35% Results
```

Process contains no goals or points directly. Season Overall is Performance;
last-5 Overall is Form.

## Results versus Process

```text
results_process_delta = Results - Process
```

- delta at least +12: `results_above_process`;
- delta at most -12: `results_below_process`;
- otherwise: `results_aligned`.

The product never converts these codes into claims of luck, deservedness, or
causal certainty. Differences may reflect conversion, goalkeeping, game state,
opponent effects, or variance.

Additional deterministic signals use deliberately strong thresholds:

- Chance Generation at least 65 and Finishing Proxy at most 35:
  `finishing_issue`;
- Chance Generation at most 35 and Finishing Proxy at least 45:
  `creation_issue`;
- Defensive Process at most 35: `defensive_process_issue`.

The above/below-process signal is also included in structured diagnostics when
the absolute delta reaches 12.

## Confidence

Confidence is persisted separately from score. Let:

- `M` be matches in the window;
- `C` be the mean observed-match coverage across the ten required process
  metrics: four creation, three opponent-creation, possession, pass accuracy,
  and pass share;
- `N` be the number of teams in the reference population.

The exact V1 formula is:

```text
match_confidence      = 1 - exp(-M / 5)
population_confidence = min(1, N / 12)
confidence = match_confidence
             * (0.55 + 0.45 * C)
             * (0.75 + 0.25 * population_confidence)
```

The result is capped at 1. Few matches, missing metrics, and a small comparison
population reduce confidence without silently changing the score to neutral.

## Elo

Elo is recalculated independently for each competition and season, ordered by
kickoff timestamp and then match ID.

- initial rating: 1500;
- K factor: 20;
- home advantage: 60 Elo points;
- result: win 1, draw 0.5, loss 0;
- no margin-of-victory multiplier.

For the home team:

```text
E_home = 1 / (1 + 10 ^ ((R_away - (R_home + 60)) / 400))
R_post = R_pre + 20 * (result - expectation)
```

The parameters are transparent V1 heuristics for calibration in Block 12. Elo
values from disconnected competitions are not directly comparable.

## Persistence and read path

PostgreSQL stores:

- `analytics.team_feature_snapshots` for raw, stabilized, and percentile
  evidence;
- `analytics.team_score_snapshots` for dimensions, Overall, confidence,
  diagnostics, current Elo, and five-match Elo trend;
- `analytics.team_elo_history` for reproducible match-level pre/post ratings,
  expectation, result, and opponent context.

The `football-intelligence-team-analytics` CLI reads `DATABASE_URL`, processes
core competitions for a requested season, replaces versioned scope snapshots
idempotently, and writes a compact JSON report. The Next.js application reads
these snapshots server-side; it does not calculate scores in the browser.

## V1 boundaries

Team V1 does not claim xG, xA, tactical formations, pressing shape, movements,
field tilt, tracking, opponent-strength adjustment, preseason expectations, or
cross-league calibration. Those require later blocks and additional evidence.
