# Wyscout Spatial Methodology v1

Status: **specified, under empirical audit, not yet promoted to production evidence**

This document defines the first Football Intelligence spatial methodology for
Wyscout Open Data. Raw Wyscout event positions are objective source evidence;
every metric produced by the rules below is **derived Football Intelligence
evidence**, never a provider-native observed value.

Current methodology id: `fi-wyscout-spatial-v1.1`

Initial validation scope: `ENG_PL` 2017/18 only. Spain, Italy, Germany and France
must not inherit the rules until the England gate is closed.

## Version note

`v1.1` refines the unpromoted `v1.0` specification after the first real England
audit. The audit showed that treating every non-Cross historical pass subtype as
a potential long-ground pass was too broad. `Hand pass` and `Head pass` are now
explicitly non-long for this methodology, while `Simple pass` and `Smart pass`
are the only historical subtypes allowed to become Long Ground from geometry.
No production observation was emitted under `v1.0`.

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

Repository-local empirical evidence is recorded in `docs/WYSCOUT_METRIC_MAPPING.md`.
For ENG_PL 2017/18 it verifies that Wyscout `Pass` events normally contain two
0-100 `positions` coordinates, with `positions[0]` as start and `positions[1]`
as endpoint. The empirically observed `(0, 0)` endpoint sentinel is not treated
as a real location.

Wyscout pitch coordinates are subject-relative: the defended goal is `x=0%`
and attack direction is `x=100%`. Football Intelligence therefore does **not**
flip Wyscout coordinates by home/away side or period.

## 2. Coordinate system

Spatial v1 maps percentage coordinates to a `105 m x 68 m` reference pitch:

```text
x_m = 105 * x_pct / 100
y_m =  68 * y_pct / 100
opponent_goal_center = (105, 34)
```

This is a Football Intelligence methodology convention, not a claim that every
2017/18 venue measured exactly 105 x 68 m. Derived outputs retain the
`fi-wyscout-spatial-v1.1` methodology id.

A coordinate is usable only when:

1. `positions` contains at least two mapping objects;
2. both points contain numeric `x` and `y` values within `[0, 100]`;
3. the endpoint is not the empirically verified `(0, 0)` no-location sentinel.

No coordinate imputation is allowed.

## 3. Pass success

Pass success comes only from Wyscout tag `1801` (`accurate`). Tag `1802` means
unsuccessful. The real ENG_PL mapping audit verifies that these tags are
mutually exclusive and exhaustive for the historical Pass population.

Counts such as `progressive_passes` include attempts regardless of success
unless the metric name explicitly says `accurate`.

## 4. Progressive passes

Canonical FI metric: `progressive_passes` (`player_match`).

For each valid Pass event:

```text
start_goal_distance = hypot(105 - start_x_m, 34 - start_y_m)
end_goal_distance   = hypot(105 - end_x_m,   34 - end_y_m)
goal_distance_gain  = start_goal_distance - end_goal_distance
```

A pass is progressive only when it moves closer to the opponent goal and meets
the Wyscout threshold:

| Start | End | minimum gain |
| --- | --- | ---: |
| own half (`x < 52.5 m`) | own half | 30 m |
| own half | opponent half (`x >= 52.5 m`) | 15 m |
| opponent half | opponent half | 10 m |
| opponent half | own half | never progressive |

`x == 52.5 m` belongs to the opponent half. Threshold comparisons are inclusive.
If required geometry is unavailable, the player-match value is missing rather
than silently treating the pass as non-progressive.

`progressive_pass_distance`, if later activated, is the sum of positive
`goal_distance_gain` for passes satisfying this rule.

## 5. Passes into the final third

Canonical FI metric: `passes_into_final_third` (`player_match`).

The attacking final third starts at `x=70 m` on the reference pitch. A valid
Pass counts when:

```text
start_x_m < 70
end_x_m   >= 70
```

A pass starting inside the final third does not count. Only `eventName == Pass`
is considered, so set-play Throw in / Free Kick events are excluded.

If required geometry is unavailable, the player-match value is missing. The
methodology does not infer an endpoint from the semantic label `Cross`.

## 6. Accurate long passes

Priority FI metric: `long_passes_accurate` (`player_match`).

Current Wyscout semantics define Long Pass as one of:

- `Launch`;
- High Pass longer than 25 m;
- Long Ground Pass longer than 45 m.

Historical Open Data exposes Pass subevents `Cross`, `Hand pass`, `Head pass`,
`High pass`, `Launch`, `Simple pass`, and `Smart pass`, but no independent
`Long Ground Pass` subtype. Spatial v1.1 therefore uses this conservative rule:

1. `Launch` -> long without requiring geometry;
2. `High pass` -> long only when valid path length is strictly greater than 25 m;
3. `Simple pass` -> long ground only when valid path length is strictly greater
   than 45 m;
4. `Smart pass` -> long ground only when valid path length is strictly greater
   than 45 m; Wyscout explicitly states that a Smart pass can be Long Ground;
5. `Cross`, `Hand pass`, and `Head pass` -> not long under this methodology,
   regardless of geometric length, because Wyscout models them as distinct pass
   concepts rather than Long Pass types;
6. any unknown/unverified historical Pass subtype -> missing for long-pass
   classification, even if geometry is present.

Path length is:

```text
pass_length_m = hypot(end_x_m - start_x_m, end_y_m - start_y_m)
```

`long_passes_accurate` counts only classified long passes carrying tag `1801`.
No percentage is persisted redundantly when raw numerator/denominator evidence
can be preserved.

## 7. Missing versus zero

Spatial v1 preserves the project guarantees:

- confirmed participant + safely classifiable source + no qualifying event ->
  real `0`;
- required geometry unavailable -> missing for geometry-dependent rules;
- provider subtype semantics insufficient -> missing, not guessed;
- source events outside the certified canonical participation universe are
  reported as source-quality exclusions and never attributed;
- `playerId=0` is a source sentinel, never a real player;
- ratios are emitted only when the denominator is strictly greater than zero.

No statistical or geometric imputation is permitted.

## 8. Metrics deliberately not activated yet

The following remain methodology/audit pending:

- `passes_into_box`;
- `passes_short` / `passes_medium` and accurate variants;
- `switches`;
- `touches_final_third`;
- `touches_box` / `touches_in_box`;
- `shot_distance`.

The goal is to validate high-impact, well-supported rules before expanding the
surface area.

## 9. Promotion gate

A metric under `fi-wyscout-spatial-v1.1` is promotable only after the ENG_PL
2017/18 audit demonstrates, for that metric:

1. valid/invalid source coverage with correct denominators;
2. player-match and player-season readiness;
3. plausible distributions and extremes;
4. preserved zero-versus-missing behavior;
5. passing source/tag invariants;
6. no impossible count relationships;
7. explicit taxonomy coverage with unknown subtypes remaining missing;
8. quantified Player V2 input-readiness impact.

Promotion is **per metric**, not all-or-nothing. A metric with sufficient exact
evidence may advance while another spatial metric remains blocked. England must
close first; any rule change after promotion requires a new methodology version.
