# Wyscout Spatial Methodology v1

Status: **v1.1 validated on ENG_PL 2017/18; `long_passes_accurate` promoted only**

This document defines the first Football Intelligence spatial methodology for
Wyscout Open Data. Raw Wyscout event positions are objective source evidence;
every metric produced by the rules below is **derived Football Intelligence
evidence**, never a provider-native observed value.

Current methodology id: `fi-wyscout-spatial-v1.1`

Validation scope: `ENG_PL` 2017/18. The England audit closes the methodology
gate only for `long_passes_accurate`; `progressive_passes` and
`passes_into_final_third` remain non-emitting because their exact season-level
coverage is not yet sufficient. No result here automatically generalizes to
Spain, Italy, Germany, or France.

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

**Production state:** not emitted. The England audit found 87.81% exact
player-match coverage but only 32.6214% exact player-season coverage under the
project's conservative missing propagation, so promotion would currently lose
too much season evidence.

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

**Production state:** not emitted. Its audit coverage is the same as
`progressive_passes`: 87.81% exact player-match, 32.6214% exact player-season.

## 6. Accurate long passes

Promoted FI metric: `long_passes_accurate` (`player_match`).

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
A confirmed participant with fully classifiable Pass evidence and no qualifying
accurate long pass receives a real zero. If any geometry-dependent or unknown
Pass cannot be classified safely, this metric is missing for that player-match.

**Production state:** promoted for ENG_PL 2017/18 only. The real-source audit
produced 97%+ exact player-match coverage and 74.5631% exact player-season
coverage after v1.1's taxonomy refinement, with no unknown historical Pass
subtype. The adapter suppresses this metric for Spain, Italy, Germany and France
until each scope passes its own audit. Promotion is therefore metric- and
scope-specific; it does not activate the other spatial rules.

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

For `long_passes_accurate`, an aggregated Player V2 window is exact only when
the metric is observed in every contributing player-match. If any contributing
match is missing, the aggregate metric stays missing for that window rather
than summing the known matches into a partial value that looks complete.

No statistical or geometric imputation is permitted.

## 8. Metrics deliberately not activated yet

The following remain methodology/audit pending:

- `progressive_passes`;
- `passes_into_final_third`;
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
evidence may advance while another spatial metric remains blocked. Any rule
change after production promotion requires a new methodology version.

## 10. ENG_PL 2017/18 audit decision

The real-source v1.1 audit used all 328,657 Pass events from Wyscout Open Data.
The canonical participation universe excluded 45 source events from attribution:
39 belonged outside the certified starter/sub-in participant universe and 6 used
the `playerId=0` sentinel. They were reported as source-quality exclusions,
never converted into player evidence.

Among the 328,612 attributable Pass events, 326,857 had usable geometry
(99.4659%) and 1,755 had the verified `(0,0)` endpoint sentinel. Source/tag
accounting and count invariants passed. The observed historical Pass subtype
vocabulary was exactly the expected seven subtypes, with no unknown long-pass
semantics.

Promotion decision:

| Metric | exact player-season readiness | decision |
| --- | ---: | --- |
| `long_passes_accurate` | 74.5631% | **PROMOTE** |
| `progressive_passes` | 32.6214% | **BLOCK** |
| `passes_into_final_third` | 32.6214% | **BLOCK** |

Player V2's Passing definition and evidence gate are unchanged. Promoting
`long_passes_accurate` adds one objectively supported input; it does not lower
the 60% minimum dimension evidence threshold, remove the core
`pass_completion_pct` requirement, or force a Passing score when other required
spatial evidence is still missing.