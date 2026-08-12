# Expectation & Meta Intelligence V1

Block 8 adds a player-level meta layer above persisted `player-v1.0` score
snapshots. It does not recalculate football events.

## Outputs

- **Stable score**: long-term level using current Performance plus up to three
  prior seasons of the same broad role.
- **Expectation**: historical baseline built only from prior seasons.
- **Surprise / Disappointment**: current Performance minus Expectation with
  confidence gates.
- **Trend**: a recent-window gradient, not a fake longitudinal time series.
- **Watchlist**: stable quality plus positive surprise/trend signals.

Model version: `meta-v1.0`.

## Stable level

Recency weights are 1.00, 0.60, 0.36 and 0.216 from current to third previous
season. Effective evidence weight is recency multiplied by source confidence.

Stable confidence combines weighted source confidence and evidence breadth:

```text
weighted_input_confidence =
  sum(confidence * recency) / sum(recency)

breadth_factor = min(1, 0.7 + 0.1 * seasons_used)
stable_confidence = weighted_input_confidence * breadth_factor
```

## Expectation

Expectation uses only historical same-role `season` snapshots with recency
1.00, 0.60, 0.36. Missing history is a valid state, not a pipeline failure.

Expectation is a historical baseline. It is not a probabilistic prediction,
transfer value, or expert forecast.

## Surprise / Disappointment

```text
surprise_delta = Performance - Expectation
```

Classification requires both Performance and Expectation confidence >= 0.35:

- +12 or more: `surprise`;
- -12 or less: `disappointment`;
- otherwise: `aligned`.

Missing history and insufficient evidence have explicit signals.

## Trend

Trend uses available current-scope pairs:

- 60% base weight: last-3 minus last-10;
- 40% base weight: last-5 minus season.

Each pair is additionally weighted by the minimum confidence of its endpoints.
The persisted `trend_evidence` JSONB records the exact window inputs and pair
deltas. A confidence below 0.30 is not classified as rising/falling.

## Watchlist

```text
quality = stable_score
positive_surprise = clamp(max(0, surprise_delta) * 4)
positive_trend = clamp(max(0, trend_delta) * 5)

watchlist =
  45% quality
  + 35% positive_surprise
  + 20% positive_trend
```

Unavailable or confidence-gated surprise/trend contributes zero and is not
renormalized. Watchlist is an interest signal, not a claim about age,
potential, market value, or future transfer success.

## Boundaries

- roles are broad and history from another role is excluded;
- no team expectation in V1;
- no market, media, fan or expert perception yet;
- no luck/deservedness language;
- no current-season provider claim beyond the data actually persisted;
- calibration belongs to Block 12.
