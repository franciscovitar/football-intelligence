# Statistical Model V2 (Block 16)

Block 16 changes the project's priority: the statistical product specification
is now the source of truth, not what today's free/zero-cost providers happen
to expose. This document explains the resulting methodology. It is a
methodology reference, not an architecture document -- see `docs/ARCHITECTURE.md`
for system structure and the per-block docs (`PLAYER_ANALYTICS.md`,
`TEAM_ANALYTICS.md`, `META_ANALYTICS.md`, `RATING_INTELLIGENCE.md`,
`TACTICAL_INTELLIGENCE.md`, `ZERO_COST_COVERAGE.md`) for the blocks V2 builds
on top of rather than replaces.

## Metric Catalog V2

`analytics/src/football_intelligence/metric_catalog/` declares **130**
metrics (up from the pre-Block-16 catalog of 48), each a `MetricDefinition`:
key, display name, granularity, category, unit, `raw`/`derived`, per90
eligibility, percentile eligibility, preferred direction, a minimum-sample
policy note, and a semantic version. It spans participation, output,
expected output, shooting, creation, passing, progression, dribbling,
possession security, defending, duels, discipline, goalkeeping, and the
team-level equivalents (performance, possession, set pieces, pressing,
transition), plus a small advanced/contextual namespace.

Declaring a metric here **never implies a live data source exists for it
yet**. Missing is not the same as removed: `coverage_lab` measures the real
provider gap against this catalog (see `docs/ZERO_COST_COVERAGE.md`, whose
denominator grew from 48x10=480 to 127x10=1270 in lockstep -- 127 is the
count of catalog entries collapsed onto Coverage Lab's five-grain identity
space, not a second, drifting catalog). `player_analytics`/`team_analytics`
scoring only ever use the subset backed by a real per-observation source
today; everything else is honestly reported as not available (see "Missing
data" below), never silently dropped from the catalog or fabricated as zero.

## Raw vs. derived

Every catalog entry is marked `raw` (a value a provider can report directly,
e.g. `goals`, `shots_total`, `expected_goals`) or `derived` (computed from
one or more raw/other-derived values, e.g. `goals_minus_xg`,
`shots_on_target_pct`, `xg_per_shot`). Derived values are never persisted in
place of the raw evidence they're computed from -- raw provider evidence is
never silently overwritten by a downstream computation.

## Per-90 and percentiles

Count metrics convert to a rate per 90 minutes so players/teams with
different playing time are compared on rate, not raw totals (unchanged from
V1, `player_analytics`/`team_analytics`). Percentiles are always computed
within an explicit **comparison group**, never a single universal pool:

- competition (V1 team scoring is competition-scoped only, no cross-league
  ranking);
- season/window (`last_3`/`last_5`/`last_10`/`season` -- unchanged from V1);
- position family (V2, see below) where a fine-enough peer group exists,
  falling back to V1's four broad roles (goalkeeper/defender/midfielder/
  forward) otherwise;
- a minimum-minutes eligibility gate (V1 already shrinks toward the
  population mean by playing time; V2's real-snapshot scoring job additionally
  applies an explicit minimum-minutes filter -- 450 minutes -- before a
  player enters a percentile population at all, per the product rule that a
  window must never be manufactured from too small a sample).

## Position families (V2)

`analytics/src/football_intelligence/position_profiles/` adds a finer
classification on top of V1's four broad roles: goalkeeper, centre_back,
fullback_wingback, defensive_midfielder, central_midfielder,
attacking_midfielder, winger, forward. `classify_position_family` maps common
`listed_position` tokens to a family and falls back to V1's broad role when
no fine-grained token is available (so nothing V1 could already classify
becomes unclassified under V2). Per-family score weight profiles
(`POSITION_FAMILY_SCORE_WEIGHTS`) exist only where a materially different
weighting is defensible -- a centre-back is not scored on shot/xG weights the
way a forward is, and a fullback's profile weights progression/crossing
higher than a centre-back's. V2 (`player_analytics/engine_v2.py`, model
version `player-v2.0`) layers this on top of V1's already-computed
percentiles rather than recomputing them from scratch: recomputing
percentiles within a materially smaller fine-family population would often
be less reliable than V1's existing role-scoped populations, not more. When a
player's position doesn't resolve to a fine family, or that family's
weighted metrics have no computed feature, V2 falls back to the player's V1
score rather than fabricating one from an empty weight set.

## Confidence and ranking eligibility

Confidence is always an explicit, deterministic, non-ML field, separate from
the score itself (unchanged principle from V1/Team V1/Meta/Rating). V2 adds
an explicit **ranking eligibility gate**
(`player_analytics.engine_v2.rank_by_confidence_gated_score`,
`MIN_RANKING_CONFIDENCE = 0.40`): an entry below the confidence floor is real
evidence (never hidden) but can never outrank an eligible entry purely
because its raw score is numerically higher. Verified with the product
spec's own example: Player A (score 96, confidence 94%, minutes 2183) ranks
ahead of Player B (score 98, confidence 31%, minutes 238).

## Results vs. underlying performance

`player_analytics.engine_v2.classify_results_vs_process` and
`team_analytics.engine_v2`'s equivalent classify raw output against
expected/underlying-process output into `results_above_process` /
`results_below_process` / `aligned` / `insufficient_data`, using the same
+-12-percentile-point threshold pattern `team_analytics.engine` already used
for `results_process_delta` before Block 16. It requires both the raw
expected-output value and its percentile; when xG (or another required
expected-output metric) is absent for the entity, the result is always
`insufficient_data` -- **never a fabricated verdict from a missing input
treated as zero.**

## Diagnostic rule engine

`analytics/src/football_intelligence/diagnostics/` (model version
`diagnostic-v1.0`) is a deterministic, pure, non-ML rule engine: every rule
is a function of already-computed evidence (percentiles, scores, meta/rating
snapshots) that returns a `DiagnosticFinding | None`. `None` means the
required evidence was absent or didn't clear the rule's threshold -- never
guessed. 15 rules across `rules_player.py`/`rules_team.py`:

- player: `finishing_underperformance`, `finishing_overperformance`,
  `high_volume_low_quality_shooting`, `breakout_signal` (wraps
  `meta_analytics`' existing Watchlist verdict), `underrated`/`overrated`
  (wrap `rating_intelligence`'s existing rating-gap verdict);
- team: `results_above_process`/`results_below_process` (wrap
  `team_analytics`'s existing `results_process_delta`),
  `sterile_possession`, `few_but_high_quality_chances_allowed`,
  `high_volume_low_quality_allowed`, `creation_problem`,
  `defensive_process_strong`/`defensive_process_weak`, `regression_risk`.

Rules that "wrap" an existing block's verdict never recompute it -- Meta/
Rating/Team Intelligence stay the single source of truth for those numbers;
the diagnostic engine only reshapes an already-trusted result into the
common `DiagnosticFinding` contract (`diagnostic_code`, `entity_type`,
`entity_id`, `severity`, `confidence`, `supporting_metrics`,
`comparison_group`, `window`, `model_version`, `computed_at`), persisted to
`analytics.diagnostic_findings`. An entity with no finding is a valid,
correct, common result, not an error.

## League/team context

V1's team comparison scope stays competition-scoped only (no cross-league
calibration in Block 16 either -- that remains a documented V1 limitation,
not solved here). Existing per-competition Elo (`team_analytics`) is
unchanged. Block 16 does not add a cross-league strength adjustment; doing so
without real evidence would be exactly the kind of unsupported claim the
product's diagnostic engine is designed to avoid.

## Perception stays separate

Rating Intelligence's objective-vs-perception separation (Block 10) is
unchanged and reused, not reimplemented: the `underrated`/`overrated`
diagnostic rules wrap `rating_intelligence`'s existing rating-gap output,
which itself never lets qualitative evidence overwrite an objective score
(see `docs/RATING_INTELLIGENCE.md`).

## Missing data

A metric declared in Catalog V2 with no current observation is `None` at
every layer -- normalization DTOs, persisted rows, and diagnostic rule
inputs -- and every rule that needs it returns `None`/`insufficient_data`
rather than treating the gap as zero. The web layer must render an explicit
"not available" state for such a metric, never a blank cell or a fabricated
zero (see `docs/WEB.md` for the UI convention).

## Real season snapshot: ENG_PL 2025/26

Primary, non-synthetic real snapshot (see `data/real/2025-26/README.md` for
the full detail): the completed 2025/26 Premier League season, loaded from
two sources chosen after research beyond the already-certified Block 13-15
zero-cost adapters (none of which expose player-level detail for any
domestic league):

- **Official Fantasy Premier League API** (`fantasy.premierleague.com/api/`,
  public, unauthenticated) -- 459 real player-season aggregate records
  (minutes, goals, assists, cards, saves, bonus/ICT, partial defensive
  counts, and real xG/xA/xGI/xGC -- no existing zero-cost adapter had ever
  supplied player xG/xA before this).
- **Football-Data.co.uk** (already Block-15-certified) -- the full 380-match
  2025/26 season: results plus team-level shots/shots-on-target/fouls/
  corners/cards.

Loaded via `football-intelligence-load-real-snapshot` into
`football.player_season_stats` (new) and the existing `football.matches`/
`football.team_match_stats` tables. Scored via
`football-intelligence-score-real-snapshot`, which bridges the
season-aggregate table into the same `classify_results_vs_process` +
diagnostic-rule machinery the rest of the product uses (season-aggregate
data has no match-by-match rows, so V1's per-match feature engine cannot
consume it directly for this snapshot; only a `season` window is valid here,
never a manufactured `last_5`/`last_10`).

Real result from this run, against 316 players with >=450 minutes: 60
`finishing_underperformance` and 55 `finishing_overperformance` findings,
average confidence ~0.77-0.78. Spot-checked examples are football-plausible
(e.g. injury-affected/struggling forwards underperforming a healthy xG
total; a deep-lying midfielder and a set-piece-threat centre-back
overperforming a low xG total) -- no nonsense pattern (a goalkeeper as a top
finisher, a starter ranked on nearly-zero confidence, a centre-back punished
for low xG) was observed.

### Secondary validation dataset: WC2022 (not the product snapshot)

`data/validation/wc2022/` holds a bounded 10-match sample (spread across the
tournament, not just the first N) from StatsBomb Open Data's FIFA World Cup
2022 -- the only StatsBomb Open Data competition-season verified **fully**
complete (64/64 matches; every domestic league sample in that dataset is
partial, e.g. Bundesliga 2023/24 publishes only 34/306 matches). This exists
solely to validate that Catalog V2's richer families (passing, defending,
dribbling, event-derived xG) work correctly when real match-level data
exists -- it is explicitly **not** the primary product snapshot, not a core
league, and not season 2025/26; every file carries an explicit warning to
that effect and it must never be presented as ENG_PL or any other core-league
data.

## Known limitations (Block 16)

- No passing/defensive/carrying/dribbling granularity for any domestic
  league in the primary real snapshot -- no zero-cost current source
  provides it (see `data/real/2025-26/README.md`).
- No team-level xG/xGA for ENG_PL 2025/26 -- team diagnostics that require it
  (`sterile_possession`, `few_but_high_quality_chances_allowed`) correctly
  return no finding for this snapshot rather than a fabricated one.
- FPL-sourced team labels reflect the *current* (2026/27) squad, not
  necessarily 2025/26 (season totals themselves remain correctly scoped).
- The real-snapshot population is current-FPL-roster-scoped: a 2025/26
  player who left the Premier League entirely is absent, not silently
  zeroed.
- No cross-league strength calibration (unchanged V1 limitation).
- No daily automation -- this is a one-off, manually-run curated snapshot,
  per explicit Block 16 scope (see `AI/prompts` Block 16 brief SS26).
