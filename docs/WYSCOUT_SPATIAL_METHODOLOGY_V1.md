# Wyscout Spatial Methodology v1

Status: **specified, not yet promoted to production evidence**

This document defines the first Football Intelligence spatial methodology for
Wyscout Open Data. It is intentionally narrow and versioned. Raw Wyscout event
positions are objective source evidence; every metric produced by the rules
below is **derived Football Intelligence evidence**, never a provider-native
observed value.

Methodology id: `fi-wyscout-spatial-v1.0`

Initial validation scope: `ENG_PL` 2017/18 only. The exact same rules may be
reused for `ESP_LL`, `ITA_SA`, `GER_BL1`, and `FRA_L1` only after the England
audit passes.

## 1. Evidence and provenance

Primary semantic references:

- Wyscout Pitch coordinates: <https://dataglossary.wyscout.com/pitch_coordinates/>
- Wyscout Progressive pass: <https://dataglossary.wyscout.com/progressive_pass/>
- Wyscout Pass into final third: <https://dataglossary.wyscout.com/pass_to_final_third/>
- Wyscout Long pass: <https://dataglossary.wyscout.com/long_pass/>

Repository-local empirical evidence is recorded in `docs/WYSCOUT_METRIC_MAPPING.md`.
For ENG_PL 2017/18 it verifies that Wyscout `Pass` events normally contain two
0-100 `positions` coordinates, with `positions[0]` as the start and
`positions[1]` as the event endpoint. It also records the small set of invalid
`(0, 0)` pass endpoints that must not be silently treated as real locations.

The current Wyscout glossary states that pitch coordinates are subject-relative:
the subject's defended goal is always `x=0%` and the attack direction is always
`x=100%`. Therefore Football Intelligence does **not** flip coordinates by home/
away team or by period.

## 2. Coordinate system

Wyscout positions are percentages. Spatial v1 maps them to a standard
`105 m x 68 m` reference pitch:

```text
x_m = 105 * x_pct / 100
y_m =  68 * y_pct / 100
opponent_goal_center = (105, 34)
```

This standardization is a methodology convention. It does not claim that every
2017/18 venue had exactly 105 x 68 metre playing dimensions. Metric provenance
must therefore retain `fi-wyscout-spatial-v1.0` rather than presenting the
result as a provider-native physical measurement.

A coordinate is usable only when:

1. `positions` contains at least two mapping objects;
2. both points contain numeric `x` and `y` values within `[0, 100]`;
3. the endpoint is not the empirically verified Wyscout `(0, 0)` no-location
   sentinel for the event types where that sentinel can occur.

If a required position is unusable, the spatial metric for that event is
**missing**, not zero. No coordinate imputation is allowed.

## 3. Pass success

For pass-derived metrics, success is read from Wyscout tag `1801` (`accurate`).
Tag `1802` means unsuccessful. The repository's empirical mapping has already
verified that those tags are mutually exclusive and exhaustive for ENG_PL
2017/18 `Pass` events.

Counts such as `progressive_passes` include attempts regardless of success unless
the metric name explicitly says `accurate`.

## 4. Progressive passes

Canonical FI metric: `progressive_passes` (`player_match`).

For each valid `Pass` event, compute distance to the opponent goal centre:

```text
start_goal_distance = hypot(105 - start_x_m, 34 - start_y_m)
end_goal_distance   = hypot(105 - end_x_m,   34 - end_y_m)
goal_distance_gain  = start_goal_distance - end_goal_distance
```

A pass is progressive only when it moves closer to the opponent goal and meets
the Wyscout threshold for the start/end halves:

| Start | End | minimum `goal_distance_gain` |
| --- | --- | ---: |
| own half (`x < 52.5 m`) | own half (`x < 52.5 m`) | 30 m |
| own half | opponent half (`x >= 52.5 m`) | 15 m |
| opponent half | opponent half | 10 m |
| opponent half | own half | never progressive |

This operationalizes Wyscout's documented wording "closer to the opponent's
goal" as the reduction in Euclidean distance to the goal centre. That geometric
interpretation is also the established implementation used in the Soccermatics
teaching reference for the Wyscout definition; it is recorded here explicitly
so Football Intelligence never relies on an implicit convention.

Boundary policy is deterministic: `x == 52.5 m` belongs to the opponent half.
Threshold comparison is inclusive (`>=`).

### Progressive pass distance

`progressive_pass_distance`, if activated after audit, is the sum of
`goal_distance_gain` across passes that satisfy the progressive-pass rule. It
is a derived distance workload, not raw path length and not a provider-native
metric.

## 5. Passes into the final third

Canonical FI metric: `passes_into_final_third` (`player_match`).

On a 105 m reference pitch, the attacking final third begins at `x=70 m`
(`2/3 * 105`, equivalent to `66.666...%` of Wyscout x).

A valid `Pass` counts when:

```text
start_x_m < 70
end_x_m   >= 70
```

The start must be outside and the endpoint inside the final third. A pass that
starts inside the final third does not count. Because only `eventName == Pass`
is considered, Wyscout `Free Kick`/`Throw in` events are excluded, matching the
current Wyscout glossary's explicit exclusion of throw-ins.

This metric counts attempts. A future accurate-final-third metric must
additionally require tag `1801`; it must not redefine the base count.

## 6. Accurate long passes

Priority FI metric: `long_passes_accurate` (`player_match`).

Wyscout's current glossary defines a long pass as:

- a ground pass longer than 45 m; or
- a high pass longer than 25 m; and
- also includes the provider's `Launch` long-pass type.

Wyscout Open 2017/18 has `Pass` sub-events including `High pass` and `Launch`
but no dedicated `Long ground pass` sub-event in the empirically observed
schema. Spatial v1 therefore uses this conservative hybrid rule:

1. `subEventName == "Launch"` -> long pass;
2. `subEventName == "High pass"` -> long pass only when valid Euclidean path
   length is greater than 25 m;
3. any other non-cross `Pass` -> long ground pass only when valid Euclidean
   path length is greater than 45 m;
4. `subEventName == "Cross"` is not reclassified as a long pass from geometry
   alone because Wyscout represents crosses as their own source subtype and
   the Open Data does not expose a second independent long-pass flag.

Path length is:

```text
pass_length_m = hypot(end_x_m - start_x_m, end_y_m - start_y_m)
```

`long_passes_accurate` counts only long passes that also carry tag `1801`.
The strict `>` comparisons follow the glossary wording "longer than".

Before production promotion the England audit must report the distribution of
path lengths by `subEventName`, especially `High pass`, `Launch`, and `Cross`,
to detect any semantic mismatch between the historical Open Data taxonomy and
the current glossary.

## 7. Missing versus zero

Spatial v1 preserves the project's core semantics:

- a confirmed participant with valid source coverage and no qualifying event ->
  real `0` count;
- an event whose required coordinates are invalid -> that event contributes
  neither a positive count nor a fabricated zero-valued spatial observation;
- if source coverage for a player-match cannot establish the metric safely ->
  `missing`;
- ratios are emitted only when their denominator is strictly greater than zero.

No statistical imputation is permitted.

## 8. Metrics deliberately not activated by v1 yet

The following remain methodology/audit pending even though the coordinates may
support them:

- `passes_into_box`;
- `passes_short` / `passes_medium` and their accurate variants;
- `switches`;
- `touches_final_third`;
- `touches_box` / `touches_in_box`;
- `shot_distance`.

Reason: v1 should validate the highest-impact, best-supported rules first rather
than turn every spatially plausible field into production evidence at once.

## 9. Promotion gate

`fi-wyscout-spatial-v1.0` is ready for production use only after an ENG_PL
2017/18 audit demonstrates all of the following:

1. valid/invalid coordinate coverage by event and metric;
2. player and player-match coverage;
3. distribution, percentiles, and extreme values;
4. zero-versus-missing behavior;
5. cross-checks against known event/sub-event/tag invariants;
6. no impossible negative counts or ratios;
7. impact on Player V2 evidence states and dimensions;
8. historical promotion invariants updated only from observed outputs, never
   guessed in advance.

Only after England passes may the exact same methodology id and rules be applied
to Spain, Italy, Germany, and France. Any rule change requires a new methodology
version.