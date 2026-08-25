# Wyscout Spatial Methodology v1

Status: **`fi-wyscout-spatial-v1.2` validated for `long_passes_accurate` and `passes_into_final_third` on the five Wyscout Open core domestic leagues in 2017/18; `progressive_passes` remains blocked.**

This document defines Football Intelligence's first spatial methodology for Wyscout Open Data. Raw Wyscout event positions are objective source evidence; every metric produced by the rules below is **derived Football Intelligence evidence**, never a provider-native observed value.

Current methodology id: `fi-wyscout-spatial-v1.2`.

Exact validated scopes:

- `ENG_PL` `2017/18`;
- `ESP_LL` `2017/18`;
- `FRA_L1` `2017/18`;
- `GER_BL1` `2017/18`;
- `ITA_SA` `2017/18`.

No result here generalizes to another competition or season. `wyscout-open-v0.5` may emit the two promoted metrics only when the declared adapter scope matches one of those exact competition-season tuples. Code/adapter support is separate from production-database state: a scope is not "live" until an explicitly authorized production promotion and post-write QA are observed.

## Version history

`v1.0` specified the first candidate geometry and was never promoted.

`v1.1` refined the long-pass taxonomy after the first real England audit. It removed the unsafe generic `>45 m` fallback for distinct `Hand pass` and `Head pass` types and promoted only `long_passes_accurate` for the audited England scope.

`v1.2` keeps the v1.1 long-pass taxonomy unchanged and adds an exact asymmetric rule for `passes_into_final_third` when a historical pass endpoint is unavailable: a pass that already starts inside the attacking final third is an exact negative because it cannot satisfy an outside-to-inside transition; a pass starting outside the final third with unavailable endpoint remains ambiguous/missing. No endpoint is imputed.

The same v1.2 rules were then independently audited on Spain, Italy, Germany and France before the v0.5 scope-expansion candidate was created.

## 1. Evidence and provenance

Primary semantic references:

- Wyscout Pitch coordinates: <https://dataglossary.wyscout.com/pitch_coordinates/>
- Wyscout Progressive pass: <https://dataglossary.wyscout.com/progressive_pass/>
- Wyscout Pass into final third: <https://dataglossary.wyscout.com/pass_to_final_third/>
- Wyscout Long pass: <https://dataglossary.wyscout.com/long_pass/>
- Wyscout Smart pass: <https://dataglossary.wyscout.com/smart_pass/>
- Wyscout Cross: <https://dataglossary.wyscout.com/cross/>
- Wyscout Hand pass: <https://dataglossary.wyscout.com/hand_pass/>
- Wyscout Head pass: <https://dataglossary.wyscout.com/head_pass/>
- Historical event/sub-event ids: <https://support.wyscout.com/matches-wyid-events>

Repository-local empirical evidence is recorded in `docs/WYSCOUT_METRIC_MAPPING.md` and in the real-source audit/runtime evidence used by the promotion contracts.

Wyscout pitch coordinates are subject-relative: the defended goal is `x=0%` and attack direction is `x=100%`. Football Intelligence therefore does **not** flip Wyscout coordinates by home/away side or period.

The historical Open Data normally exposes Pass start/end coordinates in `positions[0]` / `positions[1]`. The empirically observed endpoint `(0, 0)` sentinel is treated as unavailable location, not as a real point on the pitch.

## 2. Coordinate system

Spatial v1 maps percentage coordinates to a `105 m x 68 m` reference pitch:

```text
x_m = 105 * x_pct / 100
y_m =  68 * y_pct / 100
opponent_goal_center = (105, 34)
```

This is a Football Intelligence methodology convention, not a claim that every 2017/18 venue measured exactly 105 x 68 m.

A coordinate path is fully usable only when:

1. `positions` contains at least two mapping objects;
2. both points contain numeric `x` and `y` in `[0, 100]`;
3. the endpoint is not the verified `(0, 0)` no-location sentinel.

The start point may still be usable independently for a rule that does not require an endpoint. No coordinate imputation is allowed.

## 3. Pass success

Pass success comes only from Wyscout tag `1801` (`accurate`). Tag `1802` means unsuccessful. The real audits require these tags to remain mutually exclusive/exhaustive for the historical Pass population.

Metrics such as `progressive_passes` and `passes_into_final_third` count qualifying attempts regardless of success unless the metric name explicitly says `accurate`.

## 4. Progressive passes

Canonical FI metric: `progressive_passes` (`player_match`).

For each Pass with fully usable geometry:

```text
start_goal_distance = hypot(105 - start_x_m, 34 - start_y_m)
end_goal_distance   = hypot(105 - end_x_m,   34 - end_y_m)
goal_distance_gain  = start_goal_distance - end_goal_distance
```

A pass is progressive only when it moves closer to the opponent goal and meets the Wyscout threshold:

| Start | End | minimum gain |
| --- | --- | ---: |
| own half (`x < 52.5 m`) | own half | 30 m |
| own half | opponent half (`x >= 52.5 m`) | 15 m |
| opponent half | opponent half | 10 m |
| opponent half | own half | never progressive |

`x == 52.5 m` belongs to the opponent half. Threshold comparisons are inclusive. If required geometry is unavailable, the player-match value is missing rather than silently negative.

**Production/code state:** deliberately non-emitting. In the England audit, exact player-match coverage was high but strict player-season exactness was only 32.6214%. No later audit authorizes relaxing that missing propagation or the Player V2 evidence gates.

## 5. Passes into the final third

Canonical FI metric: `passes_into_final_third` (`player_match`).

The attacking final third starts at `x=70 m` on the FI reference pitch. A pass counts when:

```text
start_x_m < 70
end_x_m   >= 70
```

Only `eventName == Pass` is considered, so Throw in / Free Kick event families are not reclassified as ordinary passes.

Missing-endpoint semantics are asymmetric and exact:

- start already inside final third -> exact negative, even if endpoint is unavailable;
- start outside final third + usable endpoint inside -> positive;
- start outside final third + usable endpoint outside -> exact negative;
- start outside final third + endpoint unavailable -> ambiguous/missing.

No endpoint is inferred from `Cross`, the next event, or another subtype. A dedicated control audit rejected event-sequence endpoint reconstruction because it was not accurate enough on known endpoints.

`wyscout-open-v0.5` enables this metric only for the five exact validated `2017/18` scopes above. Other seasons remain suppressed even for the same competition.

## 6. Accurate long passes

Canonical FI metric: `long_passes_accurate` (`player_match`).

Current Wyscout semantics define Long Pass as one of:

- `Launch`;
- High Pass longer than 25 m;
- Long Ground Pass longer than 45 m.

Historical Open Data exposes Pass subevents `Cross`, `Hand pass`, `Head pass`, `High pass`, `Launch`, `Simple pass`, and `Smart pass`, but no independent `Long Ground Pass` subtype. Spatial v1.1/v1.2 therefore uses:

1. `Launch` -> long without requiring geometry;
2. `High pass` -> long only when valid path length is strictly greater than 25 m;
3. `Simple pass` -> long ground only when valid path length is strictly greater than 45 m;
4. `Smart pass` -> long ground only when valid path length is strictly greater than 45 m; Wyscout explicitly allows Smart pass to be Long Ground;
5. `Cross`, `Hand pass`, `Head pass` -> explicitly not long under this methodology;
6. unknown/unverified historical Pass subtype -> missing for long-pass classification even if geometry exists.

Path length is:

```text
pass_length_m = hypot(end_x_m - start_x_m, end_y_m - start_y_m)
```

`long_passes_accurate` counts only classified long passes carrying tag `1801`.

`wyscout-open-v0.5` enables this metric only for the five exact validated `2017/18` scopes above. No other season inherits the rule automatically.

## 7. Missing versus zero

Spatial v1.2 preserves the project guarantees:

- confirmed participant + fully classifiable evidence + no qualifying event -> real `0`;
- geometry required but unavailable -> missing;
- provider subtype semantics insufficient -> missing, never guessed;
- events outside the certified canonical starter/sub-in participation universe are reported as source-quality exclusions and never attributed;
- `playerId=0` is a source sentinel, never a real player;
- ratios are emitted only when denominator is strictly greater than zero.

For `long_passes_accurate` and `passes_into_final_third`, a Player V2 aggregate window is exact only when the metric is observed in every contributing player-match. A single contributing missing match keeps that metric missing for the window; known matches are never summed into a partial total that looks complete.

No statistical or geometric imputation is permitted.

## 8. Multileague real-source audit

Each non-England league was audited independently over the official Wyscout Open 2017/18 source. `PM exact` means exact player-match evidence. `Season exact` is the strict all-contributing-match audit readiness, before the product runtime's additional conservative minutes policy.

| Scope | usable geometry | long PM exact | final-third PM exact | long season exact | final-third season exact |
| --- | ---: | ---: | ---: | ---: | ---: |
| `ESP_LL` | 99.4418% | 98.3420% | 98.3704% | 74.3268% | 75.7630% |
| `ITA_SA` | 99.4897% | 97.9949% | 97.9665% | 69.8502% | 68.7266% |
| `GER_BL1` | 99.5478% | 98.1061% | 98.0708% | 74.3644% | 75.4237% |
| `FRA_L1` | 99.4780% | 97.9553% | 97.8031% | 70.8487% | 71.7712% |

All four audits had zero pass-outcome tag invariant errors and zero unknown historical Pass subtypes. Source events outside the canonical participant universe and `playerId=0` sentinels remained exclusions, not evidence.

Observed exclusions were:

- ESP: 10 outside canonical participation + 9 sentinel actors;
- ITA: 91 + 6;
- GER: 44 + 4;
- FRA: 21 + 6.

The production-path runtime subsequently exercised adapter -> normalization -> PostgreSQL -> Player Analytics read path -> Player V2 for the four scopes and produced stable v0.5 fingerprints. Product-runtime exact season-feature coverage may be slightly lower than the geometric audit because the canonical minutes policy deliberately withholds unsafe exposure for red-card and zero-duration standardized appearances. That difference is expected and must not be "fixed" by inventing minutes.

## 9. England audit/runtime decision

The original real-source England audit used all 328,657 Pass events. The canonical participation universe excluded 45 source events from attribution: 39 outside the certified starter/sub-in universe and 6 `playerId=0` sentinels.

Among 328,612 attributable Pass events, 326,857 had usable geometry (99.4659%) and 1,755 had the verified `(0,0)` endpoint sentinel. The observed historical Pass vocabulary was exactly the expected seven subtypes, with no unknown long-pass semantics.

After the v1.2 exact-negative refinement, the real product path observed:

- `long_passes_accurate`: 10,268 known player-match rows, 175 missing; 384 exact Player V2 season features;
- `passes_into_final_third`: 10,249 known player-match rows (98.1423%), 194 missing; 377 exact Player V2 season features;
- final-third exact rows split into 8,629 positive and 1,620 confirmed zero;
- among 385 players meeting the season percentile-minutes gate, 255 had an exact final-third percentile input;
- Passing state: 231 `partial`, 281 `insufficient_data`, 0 `ready`/scored;
- `progressive_passes`: absent;
- repeated Player V2 calculation: idempotent PASS.

This is the intended outcome. More exact evidence does not imply a publishable Passing score while an expected input remains unsupported.

## 10. Metrics deliberately not activated

The following remain methodology/audit pending:

- `progressive_passes`;
- `passes_into_box`;
- `passes_short` / `passes_medium` and accurate variants;
- `switches`;
- `touches_final_third`;
- `touches_box` / `touches_in_box`;
- `shot_distance`.

## 11. Promotion gate

Promotion is **per metric and per exact competition-season scope**, never all-or-nothing and never league-name-only.

Before a spatial metric is enabled for a scope, evidence must establish:

1. valid/invalid source coverage with correct denominators;
2. player-match and strict player-season readiness;
3. plausible distributions/extremes;
4. preserved zero-versus-missing behavior;
5. source/tag invariants;
6. no impossible count relationships;
7. explicit taxonomy coverage with unknown subtypes remaining missing;
8. quantified Player V2 input-readiness impact;
9. product-path runtime through canonical persistence/read layers;
10. semantic-version bump/recertification when observable adapter scope changes.

A rule change after promotion requires a new methodology version. A scope expansion that changes observable adapter output requires a new adapter semantic version even if the spatial formula itself remains v1.2.

## 12. Production-state boundary

Methodology validation and adapter emission are not production deployment.

The exact current Data Mesh/Player V2 fingerprints and accepted historical predecessor states live in `docs/HISTORICAL_PLAYER_PRODUCTION_PROMOTION.md` and `analytics/src/football_intelligence/jobs/historical_player_promotion_spec.py`.

A historical scope may be called production-live only after:

1. explicit production-write authorization;
2. guarded promotion against the intended database;
3. post-write read-only verification;
4. real browser QA against the deployed product.

Until those observations exist, documentation must say the scope is **supported/validated**, not live.
