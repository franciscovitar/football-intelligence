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

`analytics/src/football_intelligence/metric_catalog/` declares the complete
versioned product registry (with no arbitrary maximum), each a `MetricDefinition`:
key, display name, granularity, category, unit, `raw`/`derived`, per90
eligibility, percentile eligibility, preferred direction, a minimum-sample
policy note, and a semantic version. It spans participation, output,
expected output, shooting, creation, passing, progression, dribbling,
possession security, defending, duels, discipline, goalkeeping, and the
team-level equivalents (performance, possession, set pieces, pressing,
transition), plus a small advanced/contextual namespace.

Declaring a metric here **never implies a live data source exists for it
yet**. Missing is not the same as removed: `coverage_lab` measures the real
provider gap against this catalog (see `docs/ZERO_COST_COVERAGE.md`). Its
denominator is always `len(unique catalog identities) * 10 competitions` and
preserves all nine grains; no grain is collapsed. Player V2 and Team V2 can
consume every numeric analytics-relevant catalog metric when it appears in a
provider-independent observation. Metrics absent from today's sources stay
in the intended profiles and become explicit evidence gaps, never fabricated
zeros.

## Raw vs. derived

Every catalog entry is marked `raw` (a value a provider can report directly,
e.g. `goals`, `shots_total`, `expected_goals`) or `derived` (computed from
one or more raw/other-derived values, e.g. `goals_minus_xg`,
`shots_on_target_pct`, `xg_per_shot`). Derived values are never persisted in
place of the raw evidence they're computed from -- raw provider evidence is
never silently overwritten by a downstream computation.

## Per-90 and percentiles

Player count/output metrics marked `per90_eligible` convert to per 90.
Percentage, ratio, rate and contextual fields do not get nonsensical per-90
projections. Team event counts use per-match rates. Percentiles are computed
within an explicit **comparison group**, never a single universal pool:

- competition (V1 team scoring is competition-scoped only, no cross-league
  ranking);
- season/window (`last_3`/`last_5`/`last_10`/`season` -- unchanged from V1);
- position family (V2, see below) where a fine-enough peer group exists,
  falling back to V1's four broad roles (goalkeeper/defender/midfielder/
  forward) otherwise;
- a minimum-minutes eligibility gate (V1 already shrinks toward the
  population mean by playing time; V2 requires 450 minutes for `season` and
  window-appropriate minimums of 90/180/270 minutes for
  `last_3`/`last_5`/`last_10`). Below-threshold players retain raw, per-90 and
  evidence values but have no percentile and never enter the reference pool.

Team window counts are summed and exposed per match. Percentages and
contextual rates are averaged over the matches where they were observed, with
that observed-match count retained. Formula ratios such as pass accuracy and
xG per shot use aggregate numerators and denominators when those inputs have
complete coverage; they are never formed by averaging per-match ratios.

## Position families (V2)

`analytics/src/football_intelligence/position_profiles/` adds a finer
classification on top of V1's four broad roles: goalkeeper, centre_back,
fullback_wingback, defensive_midfielder, central_midfielder,
attacking_midfielder, winger, forward. `classify_position_family` maps common
`listed_position` tokens to a family and records insufficient V2 evidence
when no fine-grained token is available. The V2 path is independent of V1's
legacy `FEATURE_METRICS` ceiling. It computes catalog-backed feature values
and fine-family comparison percentiles directly.

`PlayerObservation` is match-level evidence and resolves only
`player_match` definitions (plus `goalkeeper_match` for goalkeepers).
Provider-native season aggregates use the separate `PlayerSeasonObservation`
or `GoalkeeperSeasonObservation` contract, so equal metric keys at different
grains keep distinct catalog and persistence identities.

Player V2 scores twelve evidence-aware dimensions: Performance, Underlying
Performance, Finishing, Shot Generation, Creation, Progression, Passing,
1v1, Defence, Ball Winning, Aerial and Goalkeeping. Overall is composed from
position-relevant dimension scores, never a flat metric bag. Goalkeeper
workload (`shots_on_target_faced`, `xg_on_target_faced`) is context only;
skill uses save percentage, goals prevented, cross stopping, sweeper actions
and distribution. Missing profile evidence is never treated as zero or
renormalized into a complete Overall.

Team V2 exposes Attack, Defence, Creation, Finishing, Chance Quality, Shot
Generation, Control, Progression, Penetration, Build-up, Pressing, Offensive
Transition, Defensive Transition and Set Pieces. It never manufactures
pressing from possession, transition from goals, or build-up from pass volume.

## Statistical product chain and lifecycle

The implemented path is:

`Metric → Feature → Derived Metric → Percentile → Dimension → Overall → Diagnostic`

- **DECLARED**: the versioned catalog defines the ideal-product metric.
- **OBSERVED**: a real provider supplied a raw observation.
- **DERIVED**: all formula inputs existed and denominators were non-zero.
- **SCORED**: a comparison percentile exists and the evidence threshold passed.
- **PUBLISHED**: confidence, evidence and real-context product gates passed.

The inspectable `derived-v2.0` registry never divides by zero or emits a
derived metric from incomplete inputs. Evidence exposes intended metrics,
core metrics, available metrics and missing metrics separately.

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
`results_below_process` / `aligned` / `insufficient_data`. Player finishing
uses the direct residual `goals - xG`, preferring `non_penalty_goals - npxG`
when both non-penalty inputs exist, with an optional per-90 view. It never
subtracts two percentiles. Findings require meaningful expected-output
opportunity and residual magnitude, plus minutes/shots gates when those
inputs are available; confidence is capped by opportunity. A 1-goal result
on 0.5 xG cannot become a high-confidence regression signal, while +7 on
15 xG with a mature sample can. Missing xG always yields `insufficient_data`.

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

The primary non-synthetic snapshot is the completed ENG_PL 2025/26 season:
380 Football-Data.co.uk matches with selected team-level observations. Its
redistribution permission is recorded as unknown, so it is not described as
certified. The former automated FPL collector/client and derived player files
were removed because FPL's terms prohibit automated extraction.

**Block 18** adds a second, independent, public-domain (CC0) current source
(OpenFootball) and reconciles it against Football-Data.co.uk through the
existing Data Mesh pipeline: all 380 real matches agree on result/status
between the two sources (1,140/1,140 agreed decisions, 0 conflicts on match
facts). This validates the primary snapshot's correctness with real
independent evidence; it does not change what `load_real_snapshot.py` loads.
Full detail, reproduction steps and the resulting Metric Catalog V2 coverage
report: [`REAL_DATA_SNAPSHOT_V2.md`](REAL_DATA_SNAPSHOT_V2.md) and
[`REAL_DATA_SOURCE_AUDIT_V2.md`](REAL_DATA_SOURCE_AUDIT_V2.md).

`football-intelligence-load-real-snapshot` loads only match/team evidence.
`football-intelligence-score-real-snapshot` reports `insufficient_data`, zero
player scores and zero finishing findings because no permitted rich domestic
player source is present. This is the truthful real validation result, not a
target count. If permitted player-match observations become available, the
normal player analytics job persists V2 scores to the same real snapshots
read by Home, Rankings and Player pages.

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

- No permitted player-level data of any kind is present in the primary real
  domestic snapshot; league-wide player rankings are unavailable.
- No team-level xG/xGA for ENG_PL 2025/26 -- team diagnostics that require it
  (`sterile_possession`, `few_but_high_quality_chances_allowed`) correctly
  return no finding for this snapshot rather than a fabricated one.
- No cross-league strength calibration (unchanged V1 limitation).
- No daily automation -- this is a one-off, manually-run curated snapshot,
  per explicit Block 16 scope (see `AI/prompts` Block 16 brief SS26).
