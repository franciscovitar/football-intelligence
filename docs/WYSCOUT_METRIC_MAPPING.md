# Wyscout Open Data -> Metric Catalog V2 Mapping (Block 20B.2a)

This is an **empirical semantic audit**, not an implementation of the
Wyscout -> `NormalizedObservation` adapter. It records exactly what the real,
already-downloaded ENG_PL 2017/18 Wyscout Open Data source
(`data/cache/wyscout-open/`, acquired in Block 20B.1) actually contains, and
classifies which Metric Catalog V2 identities it can support and how.
Nothing below is guessed from memory, the Pappalardo et al. paper's prose,
or unofficial Kaggle/GitHub documentation -- every field name, tag id, and
count is read directly from the cached files, and every exact count is
reproduced by `analytics/.../jobs/audit_wyscout_metric_mapping.py` as a
regression check against the same cached data.

**Scope reminder**: ENG_PL 2017/18 only, role `historical/deep`. Never
current Premier League evidence; never mixed with 2025/26 or 2026/27.

## 1. Empirical source semantics inventory

### Event schema

Every event in `events_England.json` (643,150 total) is a flat record --
unlike StatsBomb's nested `event["shot"]`/`event["pass"]` sub-objects,
Wyscout encodes all semantics through `eventName`, `subEventName`, a
`tags` list of `{id}` objects, and a 2-point `positions` array:

```json
{
  "eventId": 8, "subEventName": "Simple pass",
  "tags": [{"id": 1801}],
  "playerId": 25413,
  "positions": [{"y": 49, "x": 49}, {"y": 78, "x": 31}],
  "matchId": 2499719, "eventName": "Pass", "teamId": 1609,
  "matchPeriod": "1H", "eventSec": 2.76, "subEventId": 85, "id": 177959171
}
```

**eventNames observed (10):** Duel, Foul, Free Kick, Goalkeeper leaving
line, Interruption, Offside, Others on the ball, Pass, Save attempt, Shot.

**subEventNames observed (35), grouped by eventName:**

| eventName | subEventNames |
| --- | --- |
| Duel | Air duel, Ground attacking duel, Ground defending duel, Ground loose ball duel |
| Foul | Foul, Hand foul, Late card foul, Out of game foul, Protest, Simulation, Time lost foul, Violent Foul |
| Free Kick | Corner, Free Kick, Free kick cross, Free kick shot, Goal kick, Penalty, Throw in |
| Goalkeeper leaving line | Goalkeeper leaving line |
| Interruption | Ball out of the field, Whistle |
| Offside | (blank) |
| Others on the ball | Acceleration, Clearance, Touch |
| Pass | Cross, Hand pass, Head pass, High pass, Launch, Simple pass, Smart pass |
| Save attempt | Reflexes, Save attempt |
| Shot | Shot |

**Important structural fact**: free-kick/corner/throw-in/goal-kick/penalty
deliveries live under the `Free Kick` eventName, structurally separate
from `Pass`. `passes_total` in this mapping counts `Pass` eventName only
-- a deliberate, documented choice, not an oversight. Likewise, penalty
and direct free-kick shots (`Free Kick`/`Penalty`, `Free Kick`/`Free kick
shot`) are shot attempts but live outside `Shot`; this mapping unions all
three categories for `shots_total`.

**`positions`**: always 0-100 normalized `x`/`y`. `positions[1]` (the
event's end point) is `(0, 0)` for 55.7% of `Shot` events and 41.8%/53.4%
of `Interruption`/`Offside` events -- a non-tracked-location sentinel, not
a real coordinate at that corner. For `Pass` events it is `(0,0)` only
0.5% of the time, so pass end-coordinates are reliable; shot end-coordinates
are not.

### Tag mapping (authoritative, from the cached `tags2name.csv`)

59 tags are defined; 57 are actually observed in ENG_PL 2017/18 events.
**Never observed even once**: `802` (low) and `1501` (clearance) -- the
clearance *tag* is vestigial; the real clearance signal is the distinct
`subEventName == "Clearance"`.

| Tag | Label | Verified real meaning |
| --- | --- | --- |
| 101 | Goal | Present on the shot-type event that scored |
| 102 | own_goal | Present on the (non-shot) event that put the ball in the player's own net |
| 201 | opportunity | Present on 70% of all `Shot` events -- too broad to mean "big chance" |
| 301 | assist | Pass that directly created a goal; verified disjoint from 302 |
| 302 | keyPass | Pass that created a shot, not a goal; verified disjoint from 301 |
| 401/402/403 | Left/Right/head-body | Shot body part; covers 100% of `Shot` events |
| 701/702/703 | lost/neutral/won | Duel outcome |
| 901 | through | Through ball; only on `Smart pass`/`High pass` |
| 1101/1102 | direct/indirect | Free-kick delivery type |
| 1201-1209 | Position: Goal ... | Shot landed within the goal frame (on target) |
| 1210-1216 | Position: Out ... | Shot missed the frame (off target) |
| 1217-1223 | Position: Post ... | Shot struck the woodwork |
| 1401 | interception | Spans almost every eventName, not one category |
| 1601 | sliding_tackle | Only within Duel sub-events (ground duels) |
| 1701/1702/1703 | red_card/yellow_card/second_yellow_card | Verified to appear only on `Foul`-eventName events |
| 1801/1802 | accurate/not accurate | On `Pass`: completed to a teammate. On shot-type events: reached the goal frame (on target), regardless of save/goal. On `Save attempt`: the keeper's attempt succeeded |
| 1901 | counter_attack | Marks an individual event as happening during a counter-attack (not a discrete sequence count) |
| 2001 | dangerous_ball_lost | Possession lost in a dangerous area; does not distinguish cause (opponent challenge vs. own error) |
| 2101 | blocked | On the *shooter's* shot event; never identifies the blocking defender |
| 501-504 | free_space_l/r, take_on_l/r | Scoped to Duel sub-events, shared by both participants -- not a standalone dribble-attempt event |

### Match / roster structure

`matches_England.json` (380 matches). Top-level keys: `competitionId`,
`date`, `dateutc`, `duration` (always `"Regular"` -- no extra time in
league play), `gameweek`, `label`, `referees`, `roundId`, `seasonId`,
`status` (always `"Played"`), `teamsData`, `venue`, `winner`, `wyId`.

`teamsData[<teamId>]` keys: `coachId`, `formation`, `hasFormation`,
`score`, `scoreET`, `scoreHT`, `scoreP`, `side`, `teamId`. **Verified: no
formation-shape label (e.g. `"4-4-2"`) exists anywhere** -- `formation` is
only ever `{lineup, bench, substitutions}`.

`formation.lineup[*]` / `formation.bench[*]` entries carry **only**
`{playerId, ownGoals, redCards, goals, yellowCards}` -- verified across
all 380 matches, no exceptions. **No captain flag, shirt number, or
listed position exists anywhere in the match schema.**

**Open question, deliberately not resolved in this pass**: the
`ownGoals`/`redCards`/`yellowCards`/`goals` fields on lineup/bench entries
are *not* simple per-match counts. `redCards`/`yellowCards` values include
large integers (e.g. `"91"`, `"88"`, `"56"`) that look like match minutes
rather than counts; `goals` is `"null"` for roughly half of even *starting*
lineup entries, which doesn't match "did not score = 0". This mapping does
**not** use these fields as a primitive for `goals`/`yellow_cards`/
`red_cards` -- it uses the independently verified event-tag derivation
instead (see the table below), and flags this field family as an open,
disclosed empirical question for a future pass, not a resolved source.

`formation.substitutions` is sometimes the literal string `"null"` instead
of `[]` when a team made zero substitutions (even with `hasFormation == 1`
and normal lineup/bench data) -- treated as "no substitutions", never a
structural error. Substitution `minute` values observed range 3-95
(stoppage time included).

### `players.json` / `teams.json`

`players.json` (3603 entries) carries a global `role.code2`/`code3`/`name`
(e.g. `"GK"`/`"GKP"`/`"Goalkeeper"`) -- the only source of goalkeeper
identity, since match payloads never state on-pitch role. `teams.json`'s
`area.name` is **not reliable** for ENG_PL team membership (Swansea City is
filed under `area.name == "Wales"` despite playing in the English top
flight); team identity comes from the 20 team ids actually observed in
`matches_England.json`/`events_England.json`.

## 2. Mapping table

Full machine-readable source:
`analytics/src/football_intelligence/providers/wyscout_open_mapping.py`
(`WYSCOUT_METRIC_MAPPINGS`, 190 entries as of the final catalog-accounting
pass -- see section 6). Every `(catalog_key, catalog_granularity)` pair is
validated at import time against the real `METRIC_CATALOG_V2` registry --
an invented identity raises `AssertionError` immediately. The table below
was written during the initial empirical pass (then 172 entries); section
6 records the 18 identities added afterward to reach full 194/194 catalog
coverage without rewriting this table's original findings.

Legend: **D**=DIRECT, **DV**=DERIVABLE, **RM**=REQUIRES_MODEL,
**U**=UNSUPPORTED, **A**=AMBIGUOUS.

### Participation (player_appearance / player_season)

| Metric | Granularity | Class | Notes |
| --- | --- | --- | --- |
| started | player_appearance | D | in `formation.lineup` |
| minutes | player_appearance | DV | lineup/bench + substitutions; full-match end point for non-subbed players is an open methodology question (no final-whistle timestamp) |
| captain | player_appearance | U | no flag exists |
| shirt_number | player_appearance | U | no field exists |
| listed_position | player_appearance | U | no field exists |
| matches | player_season | DV | count of matches in roster |
| appearances | player_season | DV | lineup, or bench + `playerIn` |
| starts | player_season | DV | count of matches in lineup |
| sub_appearances | player_season | DV | appearances - starts |
| minutes_per_appearance | player_season | DV | inherits `minutes` |

### Output

| Metric | Granularity | Class | Notes |
| --- | --- | --- | --- |
| goals | player_match | D | shot-type event tagged Goal(101); 988 shooter-goals + 29 own_goals = 1017/1018 real goals (99.9%, disclosed 1-goal gap) |
| assists | player_match | D | Pass tagged assist(301) |
| non_penalty_goals | player_match | DV | goals excluding Penalty |
| goal_contributions | player_match | DV | goals + assists |
| penalty_goals | player_match | D | Penalty tagged Goal |
| penalties_attempted | player_match | D | Penalty subEventName count (80) |
| penalties_missed | player_match | DV | attempted - scored |

### Shooting

| Metric | Granularity | Class | Notes |
| --- | --- | --- | --- |
| shots_total | player_match | D | Shot ∪ Free-kick-shot ∪ Penalty (8881) |
| shots_on_target | player_match | D | shots_total tagged accurate(1801) |
| shots_off_target | player_match | D | shots_total tagged not_accurate(1802) |
| blocked_shots | player_match | D | shots_total tagged blocked(2101) |
| shots_inside_box | player_match | DV | spatial rule, pending |
| headed_shots | player_match | D | Shot tagged head/body(403) |
| shots_on_target_pct | player_match | DV | ratio |
| goals_per_shot(_on_target) | player_match | DV | ratio |
| big_chances(_missed) | player_match | A | Opportunity(201) tag too broad/undefined |
| shot_distance | player_match | DV | spatial, pending; shot end-position unreliable (55.7% sentinel) |
| touches_in_box | player_match | DV | spatial, pending |
| advanced.xg / npxg / xg_per_shot | player_match | RM | features available (position, body part, on/off-target, free-kick/penalty context, outcome); no xG value in source |

### Creation

| Metric | Granularity | Class | Notes |
| --- | --- | --- | --- |
| key_passes | player_match | D | Pass tagged keyPass(302); verified disjoint from assist |
| chances_created | player_match | DV | key_passes + assists (convention, not native) |
| big_chances_created | player_match | A | same Opportunity-tag reasoning |
| passes_into_box / passes_into_final_third | player_match | DV | spatial, pending |
| through_balls | player_match | D | Pass tagged through(901) |
| crosses | player_match | D | Pass/Cross subEventName |
| shot_creating_actions / goal_creating_actions | player_match | RM | needs possession-chain linkage; events aren't sequence-linked |
| expected_threat_pass / expected_threat_created / expected_assists_open_play | player_match | RM | xThreat/xA models |

### Passing

| Metric | Granularity | Class | Notes |
| --- | --- | --- | --- |
| passes_total | player_match | D | Pass eventName (328,657) |
| passes_accurate | player_match | D | tagged accurate; 271,280/328,657 (82.6%), 1801/1802 verified mutually exclusive and exhaustive |
| pass_completion_pct | player_match | DV | ratio |
| passes_short/medium/long, (short/medium/long)_passes_accurate, progressive_passes, progressive_pass_distance, switches | player_match | DV | Euclidean-distance/spatial rule, pending -- see "Spatial metrics" |
| passes_under_pressure | player_match | RM | no "under pressure" state in source |
| passes_received / progressive_passes_received | player_match | RM | Pass records only the passer; identifying the receiver requires inferring linkage to a later event |

### Dribbling / possession security

| Metric | Granularity | Class | Notes |
| --- | --- | --- | --- |
| dribbles_attempted/successful, dribble_success_pct, take_ons_attempted/successful, take_on_success_pct | player_match | A | take_on_l/r(503/504) scoped to Duel sub-events shared by both participants, not a standalone dribble event |
| players_beaten | player_match | U | no primitive |
| dispossessed, miscontrols, possession_losses, turnovers | player_match | A | dangerous_ball_lost(2001) blends both causes and only covers "dangerous area" losses, not all turnovers |
| receiving_errors | player_match | U | no primitive |

### Ball progression / carrying

| Metric | Granularity | Class | Notes |
| --- | --- | --- | --- |
| carries, progressive_carries, carries_into_final_third, carries_into_box, carry_distance, progressive_carry_distance | player_match | U | no carry event exists (unlike e.g. StatsBomb); Acceleration is a narrower, different concept |
| touches | player_match | D | every event carrying the player's id |
| touches_final_third, touches_box | player_match | DV | spatial, pending |
| progressive_actions, ball_progressions | player_match | DV | composition; inherits progressive_carries' UNSUPPORTED status |

### Defending / duels

| Metric | Granularity | Class | Notes |
| --- | --- | --- | --- |
| tackles, tackles_won, tackle_success_pct | player_match | A | no tackle event; sliding_tackle(1601) only marks one technique within ground duels |
| blocks, shot_blocks, pass_blocks | player_match | U | blocked(2101) never identifies the blocking player |
| interceptions | player_match | D | tag 1401, spans nearly every eventName |
| clearances | player_match | D | Others on the ball/Clearance subEventName (11,784); tag 1501 is defined but never observed |
| recoveries | player_match | U | no primitive |
| pressures | player_match | RM | no pressing event; needs proximity/time modeling |
| errors_leading_to_shot/goal | player_match | U | no error attribution |
| duels_total | player_match | D | Duel eventName (176,688) |
| duels_won | player_match | D | tagged won(703); 701/702/703 cover 99.9% (161 unclassified, never assumed) |
| duel_win_pct | player_match | DV | ratio |
| aerial_duels | player_match | D | Duel/Air duel (37,760) |
| aerial_duels_won, aerial_duel_win_pct | player_match | DV | subtype ∩ won-tag |
| ground_duels | player_match | D | 3 ground-duel subtypes (138,928) |
| ground_duels_won | player_match | DV | subtype ∩ won-tag |
| fouls_committed | player_match | D | Foul eventName (8138) |
| fouls_drawn | player_match | U | Foul events record only the committer, never the victim |
| yellow_cards | player_match | D | Foul tagged yellow_card(1702); 1180 verified |
| red_cards | player_match | DV | Foul tagged red_card(1701) ∪ second_yellow_card(1703); 22 + 19 |
| second_yellow_cards | player_match | D | Foul tagged second_yellow_card(1703) |
| saves | player_match / goalkeeper_match | D | Save attempt tagged accurate(1801); 2330/3349 |

### Goalkeeping

| Metric | Granularity | Class | Notes |
| --- | --- | --- | --- |
| shots_on_target_faced | goalkeeper_match | DV | opponent shots_on_target, cross-referenced to who was in goal |
| save_pct | goalkeeper_match/season | DV | ratio |
| goals_conceded | goalkeeper_match | DV | needs scoreline + lineup/sub cross-reference (Save-attempt tags alone undercount goals with no save attempt) |
| clean_sheets | goalkeeper_match/season | DV | goals_conceded == 0 |
| goals_prevented | goalkeeper_match | RM | needs xG on shots faced |
| claims | goalkeeper_match | A | Goalkeeper leaving line event exists, but no tag distinguishes a successful claim |
| distribution_accuracy_pct, passes, long_passes | goalkeeper_match | DV | player passing metrics scoped to `players.json` role.code2=="GK" |
| launches | goalkeeper_match | D | Pass/Launch, scoped to GK role |
| average_distance_from_goal, crosses_stopped, sweeper_actions | goalkeeper_match | U | no primitive |
| xg_on_target_faced, psxg | goalkeeper_match | RM | xG model |

### Team / team_match

| Metric | Class | Notes |
| --- | --- | --- |
| goals_for / goals_against | D | native `teamsData[teamId].score` field |
| shots_total / shots_on_target (team) | DV | player-level shot events grouped by teamId |
| shots_inside/outside_box (team) | DV | spatial, pending |
| shots_allowed / shots_on_target_allowed | DV | opponent's team-level figures |
| passes_total / passes_accurate (team) | D | player-level events grouped by teamId |
| pass_accuracy_pct | DV | ratio |
| possession_pct | DV | proxy computable (share of Pass events); no explicit time-based possession state, methodology pending |
| progressive_passes, final_third_entries, field_tilt, box_entries, touches_in_box, deep_completions (team) | DV | spatial, pending |
| corners | D | Free Kick/Corner grouped by teamId (3910) |
| set_piece_shots, set_piece_xg | RM | needs possession-chain linkage back to the set piece |
| recoveries | U | no primitive |
| pressures, ppda, successful_pressures, transition_xg | RM | pressing/xG modeling |
| counter_attacks | DV | needs sequence-grouping of individually-tagged(1901) events |
| counter_attack_shots | DV | shots_total tagged counter_attack(1901); 425 observed |
| big_chances(_allowed) | A | Opportunity-tag reasoning |
| high_turnovers | A | dangerous_ball_lost + undefined "high" threshold |
| offsides | D | Offside eventName grouped by teamId (1558) |
| fouls | D | player-level fouls_committed grouped by teamId |
| yellow_cards (team) | D | grouped by teamId |
| red_cards (team) | DV | grouped by teamId |
| goalkeeper_saves | DV | sum of the team's goalkeeper(s) saves |
| formation | U | no formation-shape label exists |
| coach_name | U | coachId present, no name lookup acquired in this block |
| xg, xga, npxg, npxga, xg_per_shot, xga_per_shot | RM | xG model |

## 3. Spatial metrics -- methodology pending

The repository does not yet define an attack-direction/threshold
convention for progression (final third, penalty area, pass-length
buckets). `positions` are verified 0-100 normalized coordinates, reliable
for `Pass` (99.5% real end points) but not for `Shot` (55.7% sentinel end
points). Every metric marked DERIVABLE with "methodology pending" above is
therefore genuinely computable once (and only once) such a rule is
explicitly defined and reviewed -- this audit deliberately does not invent
one (per the task instruction: "if the catalog already defines a
threshold, reuse it; otherwise mark methodology as pending").

## 4. Minutes / participation methodology

`duration` is `"Regular"` for all 380 matches (no extra time in league
play) and `status` is always `"Played"`. Substitution `minute` values
range 3-95. A deterministic rule is available for starters who are
substituted (sub-out minute) and substitutes who come on (match-end minus
sub-in minute), and unused bench players are a genuine, confirmable `0`.
The one open gap: Wyscout gives no explicit final-whistle timestamp, so
the exact minutes for a starter who is *never* substituted require
assuming a match-end point (commonly 90 + stoppage) the source itself does
not state -- this is disclosed as an open methodology question, never
silently resolved to a fixed 90.

## 5. Verification

`football-intelligence-audit-wyscout-mapping` re-derives the exact counts
and tag/label pairs this document cites directly from the cached files and
fails loudly if they ever stop matching (see
`analytics/src/football_intelligence/jobs/audit_wyscout_metric_mapping.py`).

## 6. Final catalog accounting (194/194)

A follow-up diagnosis compared the 172-entry mapping above against every
real `METRIC_CATALOG_V2` identity (194 total) and found 18 unaccounted
for: 14 genuinely provider-applicable but overlooked, and 4 that are not a
provider-mapping question at all (internal analytics-engine outputs).
Both gaps are now closed.

### 14 overlooked entries added

| Metric | Granularity | Class | Source |
| --- | --- | --- | --- |
| home_score | match | D | `teamsData[<home teamId>].score` |
| away_score | match | D | `teamsData[<away teamId>].score` |
| home_away | team_match (corrected Block 20D.2) | D | `teamsData[*].side` (`"home"`/`"away"`) |
| status | match | D | native `status` field (verified always `"Played"`) |
| kickoff_at | match | D | native `dateutc` field |
| round_name | match | D | native `gameweek` field (1-38) |
| venue_name | match | D | native `venue` field (20 distinct real stadium names) |
| formation_stability | team | DV (pending) | season-level lineup comparison; no turnover-rate rule defined yet |
| lineup_stability | team | DV (pending) | season-level membership comparison; no stability rule defined yet |
| non_penalty_goals_minus_npxg | player_match | RM | depends on npxg |
| pressure_success_pct | player_match | RM | depends on pressures/successful_pressures |
| successful_pressures | player_match | RM | same pressing-primitive gap as `pressures` |
| xa_per90 | player_match | RM | depends on xa |
| positional_peer_group | player_season | U | depends on `listed_position`, itself UNSUPPORTED |

### 4 identities explicitly out of provider-mapping scope

Recorded in `WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS` -- **never** classified
Wyscout UNSUPPORTED, because UNSUPPORTED means "the real source was
inspected and lacks this"; these were never a source-data question at all:

| Metric | Granularity | Reason |
| --- | --- | --- |
| league_strength | competition | Cross-league calibration model output; not sourced from any single provider |
| team_strength_elo | team | Computed by this repo's own `team_analytics.engine` Elo history from match results over time |
| opponent_strength | team_match | Derived from team_strength_elo, itself an internal engine output |
| minutes_confidence | player_season | Meta-confidence signal from this repo's own scoring pipeline |

### Final counts

| | Count |
| --- | --- |
| Metric Catalog V2 total | 194 |
| Provider mapping (`WYSCOUT_METRIC_MAPPINGS`) | 190 |
| Provider out-of-scope | 4 |
| DIRECT | 43 |
| DERIVABLE | 67 |
| — DERIVABLE_READY (rule fully specified) | 34 |
| — DERIVABLE_METHODOLOGY_PENDING (primitives exist, rule undefined) | 33 |
| REQUIRES_MODEL | 35 |
| UNSUPPORTED | 25 |
| AMBIGUOUS | 20 |

`validate_full_catalog_coverage()` enforces this at import time: the
provider mapping and provider-out-of-scope identity sets must be disjoint,
and their union must equal every real `METRIC_CATALOG_V2` identity --
never more, never less.

### DERIVABLE_READY -- adapter-safe today (34)

`matches`, `appearances`, `starts`, `sub_appearances` (player_season);
`non_penalty_goals`, `goal_contributions`, `penalties_missed`,
`shots_on_target_pct`, `goals_per_shot`, `goals_per_shot_on_target`,
`chances_created`, `pass_completion_pct`, `duel_win_pct`,
`aerial_duels_won`, `aerial_duel_win_pct`, `ground_duels_won`, `red_cards`
(player_match); `shots_on_target_faced`, `save_pct`, `goals_conceded`,
`clean_sheets`, `distribution_accuracy_pct`, `passes` (goalkeeper_match);
`clean_sheets`, `save_pct` (goalkeeper_season); `shots_total`,
`shots_on_target`, `blocked_shots`, `shots_allowed`,
`shots_on_target_allowed`, `pass_accuracy_pct`, `counter_attack_shots`,
`red_cards`, `goalkeeper_saves` (team_match).

### DERIVABLE_METHODOLOGY_PENDING -- must not be emitted yet (33)

`minutes`, `minutes_per_appearance` -- no final-whistle timestamp defined;
`shots_inside_box`, `shot_distance`, `touches_in_box`, `passes_into_box`,
`passes_into_final_third`, `passes_short`, `passes_medium`, `passes_long`,
`short_passes_accurate`, `medium_passes_accurate`, `long_passes_accurate`,
`progressive_passes`, `progressive_pass_distance`, `switches`,
`touches_final_third`, `touches_box`, `progressive_actions`,
`ball_progressions` (player_match) -- no attack-direction/spatial
threshold convention defined; `long_passes` (goalkeeper_match) -- inherits
`passes_long`; `shots_inside_box`, `shots_outside_box`, `possession_pct`,
`progressive_passes`, `final_third_entries`, `field_tilt`, `box_entries`,
`touches_in_box`, `counter_attacks`, `deep_completions` (team_match) --
same spatial/sequencing gap; `formation_stability`, `lineup_stability`
(team) -- no lineup-turnover/stability rule defined.

**Note on `minutes`/`ball_progressions`/`progressive_actions`**: these
were briefly and incorrectly counted as "ready" during an intermediate
diagnosis pass, because a first-pass text search only checked
`derivation_note` for the word "pending" and missed cases where the same
open-methodology problem was stated in `caveats` instead, or was
inherited transitively from another pending/unsupported metric. This is
now encoded as an explicit `methodology_pending` field on
`WyscoutMetricMapping` (validated to only ever be set on DERIVABLE
entries) rather than inferred from free text, so this class of gap cannot
recur silently.

### Adapter-safe initial subset (77 = 43 DIRECT + 34 DERIVABLE_READY)

`adapter_safe_mappings()` in the mapping module returns exactly this set.
Everything else (DERIVABLE_METHODOLOGY_PENDING, REQUIRES_MODEL,
UNSUPPORTED, AMBIGUOUS, and every provider-out-of-scope identity) must
remain non-emitting when Block 20B.2b implements the adapter.

### Goal reconciliation rule (verified, real-source exception)

**Player `goals`** stays DIRECT: event-tag attribution (shot-type event
tagged `Goal(101)`) is the authoritative primitive for *who* scored -- no
better source exists.

**Team/match score totals** (`goals_for`, `goals_against`, `home_score`,
`away_score`) must treat the native `teamsData[*].score` field as
authoritative, never the event-tag reconstruction. Event-derived goal
counts are a parity/audit signal only, cross-checked against `score`, with
any mismatch logged rather than silently trusted or silently corrected.

**Verified real exception**: match `wyId 2499781` (Chelsea 0-1 Manchester
City, 30 September 2017, gameweek 7) is the sole case across all 380
matches where event-derived team goals (0-0) disagree with the official
score (0-1). The only goal-related event in the match is Chelsea's own
goalkeeper's `Save attempt` (`id 192260282`, `teamId 1610`,
`matchPeriod "2H"`, `eventSec 1280.97`, tags `{101 Goal, 1206 Position:
Goal center right, 1802 not accurate}`) -- there is no `Shot`/`Free kick
shot`/`Penalty` event anywhere in the match for Manchester City. This is a
genuine, isolated (1 of 1018 real goals, 0.098%) event-log completeness
gap in the raw source, not an own-goal, not a penalty/free-kick
misclassification, and not a scoreline error. No shooter is invented for
this goal; the scoreline-authoritative rule above is exactly why team/
match totals must never be read purely from event tags.

## 7. Block 20B.2b — adapter implemented

The 77-identity adapter-safe subset (section 6) is now implemented:
`analytics/src/football_intelligence/data_mesh/adapters/wyscout_open.py`
converts already-loaded ENG_PL 2017/18 payloads into `NormalizedObservation`
rows, emitting **only** `adapter_safe_mappings()`'s 77 identities (verified
against the real cache: all 77 produced real observations, 0 unexpected
identities, 0 conflicting duplicates -- see
`football-intelligence-audit-wyscout-adapter`). The goal-reconciliation
rule and the `wyId 2499781` exception above are implemented exactly as
diagnosed: player `goals` from event-tag attribution, team/match score
totals from the native `teamsData[*].score` field. See
`docs/BLOCK20_MULTI_SOURCE.md`'s "Block 20B.2b" section for the full
implementation summary. **No canonical ingestion, entity resolution, or
reconciliation exists yet** -- the adapter produces observations only; it
does not write to `football.*`, `ingestion.*`, or `intelligence.*`, and
the 33 DERIVABLE_METHODOLOGY_PENDING / 35 REQUIRES_MODEL / 25 UNSUPPORTED
/ 20 AMBIGUOUS / 4 provider-out-of-scope identities remain exactly as
classified in section 6 -- none of them are implemented by this adapter.
