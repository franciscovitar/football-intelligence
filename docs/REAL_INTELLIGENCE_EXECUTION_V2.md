# Real Intelligence Execution V2 (Block 19)

Block 18 proved the real ENG_PL 2025/26 snapshot itself is correct,
reproducible and idempotent. Block 19 actually *executes* the accepted V2
engines and the Diagnostic Rule Engine against that snapshot and reports,
in plain language, exactly what real evidence supports today -- measured
from a real run, not predicted. The machine-readable result of that run is
committed at
[`data/manifests/intelligence/ENG_PL/2025-26.json`](../data/manifests/intelligence/ENG_PL/2025-26.json).

Reproduce it with:

```
cd analytics
uv run football-intelligence-load-real-snapshot --database-url <local>
uv run football-intelligence-execute-real-intelligence-v2 --database-url <local>
```

Both commands require an explicit `--database-url` resolving to
`localhost`/`127.0.0.1`/`::1` (or a host-less local-socket DSN); a bare
`DATABASE_URL` environment variable is never read by either job.

## A genuine bug found and fixed

While implementing this block, the Team V2 `overall_score` composition in
`team_analytics/engine_v2.py` was found to renormalize across only the
dimensions that happened to be `ready`, dividing by their combined weight
instead of the full fourteen-dimension weight. That produced a non-null
`overall_score` the moment a single dimension reached `ready`, while
`evidence_state` simultaneously read `partial` -- exactly the "missing
evidence renormalized into a full score" anti-pattern this product commits
to avoiding, and inconsistent with Player V2's already-correct
`_compose_overall` gate. This is now fixed: `overall_score` is `None`
unless every one of the fourteen intended dimensions individually reached
`ready`. See `analytics/tests/test_team_analytics_v2.py`'s
`test_team_overall_score_never_renormalizes_a_partial_subset` and
`test_team_overall_score_becomes_available_once_every_intended_dimension_is_ready`
for the regression coverage.

## What works with real ENG_PL 2025/26 data today

Team V2 executes against all 20 real teams across all four windows
(`last_3`, `last_5`, `last_10`, `season` -- 80 score rows total, one per
team per window):

- **`finishing`** and **`shot_generation`** reach real, honest `partial`
  evidence for every team/window (80/80 each) -- `goals_for` and
  `shots_on_target`/`shots_total` are real observed evidence, while
  `xg_per_shot` (finishing) and `shots_inside_box` (shot_generation) stay
  missing. Neither dimension's own score is populated (a dimension's score
  is only set once *that* dimension individually reaches full coverage),
  but their raw features and coverage percentage are real and visible on
  the team detail page.
- **One real, evidence-based team diagnostic finding** fired on this run:
  `few_but_high_quality_chances_allowed` for Chelsea's `last_10` window
  (`shots_total_against_percentile = 78.95`, `shots_on_target_against_percentile
  = 31.58`, `xga_percentile = null` -- the shots-on-target-against fallback
  proxy the rule explicitly supports when xGA is unavailable). Confidence is
  a real, honest `0.2205`, reflecting the thin sample this proxy is built
  on. No other team/window pattern crossed either rule's threshold this
  run -- an empty result for those would have been equally correct.
- The other two percentile-only rules the engine can reach without a V1
  score (`sterile_possession`, `high_volume_low_quality_allowed`) were also
  evaluated for all 80 team/windows; `sterile_possession` never fires
  because `possession_pct` is not part of the real ENG_PL catalog
  identities at all.

## What does not work, and why

- **The other twelve dimensions** (`attack`, `defence`, `creation`,
  `chance_quality`, `control`, `progression`, `penetration`, `build_up`,
  `pressing`, `offensive_transition`, `defensive_transition`, `set_pieces`)
  are `insufficient_data` for every team/window: each has at least one
  *core* metric (e.g. `xg`, `xga`, `possession_pct`, `progressive_passes`,
  `big_chances`) that Football-Data.co.uk's published columns simply do not
  contain. This is unchanged from Block 16/18's finding, re-confirmed by
  actually running the engine rather than re-asserting it.
- **Overall Team V2 score and overall ranking are unavailable for every
  team** (`overall_score_available: false` for all 80 rows). This has two
  independent causes, both worth stating precisely:
  1. Real evidence coverage: no team reaches all fourteen dimensions ready
     with today's data (see above).
  2. A structural gap independent of data volume: `defensive_transition`'s
     intended profile is deliberately empty in `profiles_v2.py` ("Catalog
     V2 currently has offensive transition evidence only... rather than
     manufacturing defensive transition from generic xGA/shot volume").
     That means `defensive_transition` can never individually reach `ready`
     under the *current* catalog, so the overall composite cannot reach
     `ready` even given hypothetically complete evidence for the other
     thirteen dimensions, until a defensive-transition-specific metric is
     added to Catalog V2. This is pre-existing, accepted design from an
     earlier block, not a Block 19 regression, and Block 19 does not weaken
     the fourteen-dimension model to work around it.
- **Dimension and overall rankings correctly stay empty.** The product
  ranking queries (`apps/web/lib/queries/product-intelligence.ts`) already
  gated on `evidence_state = 'ready'` (dimension) and `evidence_state =
  'ready' AND overall_score IS NOT NULL` (overall) before this block; with
  zero dimensions reaching `ready` on real data, zero rankings is the
  correct, measured outcome -- not a bug to route around.
- **Nine of the fifteen diagnostic rules never fire on real data**:
  `results_above_process`, `results_below_process`, `regression_risk`,
  `creation_problem`, `defensive_process_strong`, `defensive_process_weak`
  all wrap the legacy V1 `TeamScore`, which this block never feeds into the
  real diagnostic path (no V1 fallback). `sterile_possession` needs
  `possession_pct`, which is absent. Player-side rules never fire because
  there are zero player observations.

## Why player intelligence is unavailable

Zero real player-match observations exist for ENG_PL 2025/26 (confirmed by
`assess_real_snapshot`, re-measured live on every run of this block's job,
never hardcoded). Per Block 19's explicit scope, this job never calls the
player V2 engine when there is nothing to score -- doing so would only
manufacture the appearance of execution. The product's Player, Rankings and
Watchlist surfaces correctly show an explicit unavailable state; no
placeholder players, no team-derived player quality, no historical StatsBomb
players standing in for ENG_PL players.

## What the WC2022 historical/deep dataset proves -- and doesn't

`data/validation/wc2022/` and `data_mesh/adapters/statsbomb_open.py` already
parse real StatsBomb Open Data event JSON (10 matches spread across the
tournament) into provider-independent `NormalizedObservation`s covering
shots, passes, dribbles, duels, fouls and goalkeeper actions -- richer
families than anything the ENG_PL snapshot has. Re-running
`football-intelligence-collect-validation-snapshot` during this block
reconfirmed it is still live and reproducible: 64/64 WC2022 matches
published, 10 sampled, 321 match-level and 5,975 event-derived
observations.

What it does **not** yet prove: nothing loads this data into `football.*`
or executes `team_analytics`/`player_analytics` V2 engines against it. Doing
so would require a new ingestion path -- competition/team/player entity
resolution plus a `football.*` loader for StatsBomb identities -- that does
not exist today and would be a new parallel ingestion architecture, not a
small addition. Per this block's explicit scope, that pipeline was not
built. WC2022 therefore stays exactly what Block 16 already established it
as: proof that the adapter and Metric Catalog V2's richer metric families
work against real event data, never the product snapshot, never contaminating
`ENG_PL 2025/26` or any current/recent-completed product state.

## Idempotency

Running `football-intelligence-execute-real-intelligence-v2` twice against
the same real database produced byte-identical `team_v2_execution`,
`real_diagnostics` and `product_view_counts` report sections both times: 80
team score rows, 560 feature rows, 1 real diagnostic finding, identical
dimension-readiness counts. Team V2 and diagnostic-findings persistence are
both delete-then-insert for the exact scope being replaced, so reruns never
duplicate rows or drift.

## What happens automatically when a compliant rich source is connected

No rebuild is needed. A future permitted player-match provider flows through
the existing, unchanged path: provider adapter -> `NormalizedObservation`s ->
entity resolution -> canonical `football.player_appearances` /
`football.player_match_stats` -> the existing `player_analytics` V2 engine
and `analytics.player_score_snapshots` -> the existing product read paths.
The same applies to any future team-level xG/xGA/possession source feeding
the remaining twelve Team V2 dimensions -- the engine, evidence contract and
diagnostic rules already support them; only real observations are missing.

## Known limitations carried forward (not Block 19 regressions)

- No true current-period (2026/27) evidence -- ENG_PL 2025/26 remains
  `latest_completed`, per Block 18.
- No cross-league strength calibration (unchanged V1/V2 limitation).
- `defensive_transition` has no catalog-backed metric yet (see above) --
  the single largest reason overall ranking is unavailable regardless of
  future ENG_PL data volume, until a future block adds that evidence to
  Catalog V2.
