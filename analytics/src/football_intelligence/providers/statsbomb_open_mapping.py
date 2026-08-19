"""Block 20C.2a: empirical StatsBomb Open Data -> Metric Catalog V2 mapping.

DATA ONLY. This module records, for every real Metric Catalog V2 identity,
how it maps to real, observed Premier League 2015/16 source primitives --
verified against the actual pinned, cached source (`DEFAULT_PINNED_REVISION`
in `providers.statsbomb_open`, competition_id=2 season_id=27, all 380
matches' `events/{match_id}.json` and `lineups/{match_id}.json`;
`docs/STATSBOMB_METRIC_MAPPING.md` records the underlying empirical evidence
and exact real counts backing every classification below). Nothing here is
carried over from the pre-Block-20 adapter's assumptions merely because that
code already existed, and nothing here is copied from the Wyscout mapping's
classifications -- StatsBomb has different source semantics (a materially
richer event vocabulary in several areas: dedicated Carry/Pressure/Ball
Recovery/Dispossessed/Miscontrol event types Wyscout has no equivalent for)
and its own gaps (no cross-event receiver linkage verified, ambiguous
tackle-outcome semantics) independently re-derived here.

This module does **not** produce `NormalizedObservation` rows and is not a
provider adapter -- that is Block 20C.2b. It is intentionally data/metadata
only, mirroring `providers.wyscout_open_mapping`'s shape exactly so the two
providers can eventually be compared/reconciled using the same conceptual
structure.

## Classification definitions (identical meaning to the Wyscout mapping)

- **DIRECT** -- the source directly contains an event/state whose semantics
  match the catalog metric, read as a single native primitive. No
  arithmetic beyond counting/summing one field.
- **DERIVABLE** -- deterministically calculable by combining two or more
  verified source primitives. Split into:
    - `methodology_pending=False` (**DERIVABLE_READY**): the deterministic
      rule is already fully specified by verified source semantics.
    - `methodology_pending=True` (**DERIVABLE_METHODOLOGY_PENDING**):
      source primitives exist, but a threshold, spatial rule, time-window
      correlation, or cross-event linkage this repository has not yet
      defined is still required. Never invented ad hoc here.
- **REQUIRES_MODEL** -- the catalog metric is itself a model/methodology
  output (xG, xA, xThreat, PPDA, pressing-success modelling), not a
  deterministic read of source primitives, even though StatsBomb may
  provide richer raw material for such a model than Wyscout does.
- **UNSUPPORTED** -- the source structurally lacks the needed information,
  verified by inspecting the real fields the relevant events carry.
- **AMBIGUOUS** -- the source has something adjacent, but its real,
  observed semantics are not precise enough to safely equate with the
  catalog metric without inventing meaning beyond what was verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from football_intelligence.metric_catalog.catalog import METRIC_CATALOG_V2
from football_intelligence.metric_catalog.types import MetricGranularity

MappingClassification = Literal[
    "DIRECT",
    "DERIVABLE",
    "REQUIRES_MODEL",
    "UNSUPPORTED",
    "AMBIGUOUS",
]


@dataclass(frozen=True, slots=True)
class StatsBombMetricMapping:
    catalog_key: str
    catalog_granularity: MetricGranularity
    classification: MappingClassification
    source_primitive: str
    derivation_note: str
    caveats: str = ""
    methodology_pending: bool = False


_CATALOG_IDENTITIES: frozenset[tuple[str, str]] = frozenset(
    (metric.key, metric.granularity) for metric in METRIC_CATALOG_V2
)


def _mapping(
    catalog_key: str,
    catalog_granularity: MetricGranularity,
    classification: MappingClassification,
    source_primitive: str,
    derivation_note: str,
    caveats: str = "",
    methodology_pending: bool = False,
) -> StatsBombMetricMapping:
    return StatsBombMetricMapping(
        catalog_key=catalog_key,
        catalog_granularity=catalog_granularity,
        classification=classification,
        source_primitive=source_primitive,
        derivation_note=derivation_note,
        caveats=caveats,
        methodology_pending=methodology_pending,
    )


@dataclass(frozen=True, slots=True)
class StatsBombProviderOutOfScopeMetric:
    """A Metric Catalog V2 identity that is intentionally not a provider-mappable
    primitive at all -- an internal analytics-engine output, never a StatsBomb
    field. Identical reasoning and identical 4 identities to Wyscout's
    out-of-scope set: these are provider-agnostic engine outputs, not a
    per-provider data question."""

    catalog_key: str
    catalog_granularity: MetricGranularity
    reason: str


STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS: tuple[StatsBombProviderOutOfScopeMetric, ...] = (
    StatsBombProviderOutOfScopeMetric(
        "league_strength",
        "competition",
        "Cross-league calibration model output (catalog's own note: 'not calibrated in "
        "V1'); not sourced from any single provider's raw data.",
    ),
    StatsBombProviderOutOfScopeMetric(
        "team_strength_elo",
        "team",
        "Computed by this repository's own team_analytics.engine Elo history from match "
        "results over time, not read from any provider field.",
    ),
    StatsBombProviderOutOfScopeMetric(
        "opponent_strength",
        "team_match",
        "Derived from team_strength_elo, itself an internal engine output rather than a "
        "provider primitive.",
    ),
    StatsBombProviderOutOfScopeMetric(
        "minutes_confidence",
        "player_season",
        "A meta-confidence signal produced by this repository's own scoring pipeline about "
        "how much real minutes data exists, not a provider field.",
    ),
)

# -- Match identity ------------------------------------------------------------
# Verified against the real 380-match `matches/2/27.json` (Block 20C.1 + this
# block's re-confirmation): match_id, match_date, home/away team+score,
# match_week (1-38, no gaps), competition_stage.name ("Regular Season" for
# all 380), match_status ("available" for all 380). `kick_off` and
# `stadium`/`referee` fields are present in the raw payload but not
# cross-verified for 100% coverage in this pass.
_MATCH_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "home_score",
        "match",
        "DIRECT",
        "matches/2/27.json[*].home_score",
        "Native pre-aggregated field; cross-validated -- summed home_score+away_score "
        "across all 380 matches equals 1026, exactly matching 988 Shot-outcome=Goal events "
        "plus 38 Own Goal For events (no residual gap, unlike Wyscout's documented 1-goal "
        "gap for ENG_PL 2017/18).",
    ),
    _mapping(
        "away_score",
        "match",
        "DIRECT",
        "matches/2/27.json[*].away_score",
        "Same native field and cross-validation as home_score.",
    ),
    _mapping(
        "home_away",
        "team_match",
        "DIRECT",
        "home_team/away_team objects on the match summary",
        "Verified present for all 380 matches; the existing adapter already derives team "
        "identity from these fields. Catalog granularity corrected to team_match "
        "(Block 20D.2 review-fix pass) -- the primitive is per-team-in-this-match, "
        "not a single match-wide value.",
    ),
    _mapping(
        "status",
        "match",
        "DIRECT",
        "native match_status field",
        "Verified 'available' for all 380 real Premier League 2015/16 matches. The existing "
        "adapter instead emits a synthetic constant 'finished' -- a REQUIRES_CHANGE finding "
        "for Block 20C.2b: native match_status should be read and reported, not overridden "
        "with a code-level constant, even though its value happens to coincide today.",
        caveats=(
            "StatsBomb Open Data only ever publishes completed historical matches, so "
            "match_status is not expected to vary within this scope -- but the catalog "
            "metric should reflect the source's own field, not a synthesized value."
        ),
    ),
    _mapping(
        "kickoff_at",
        "match",
        "DIRECT",
        "native match_date field (+ kick_off field, present but not exhaustively verified)",
        "match_date verified present and well-formed for all 380 matches.",
    ),
    _mapping(
        "round_name",
        "match",
        "DIRECT",
        "native match_week field",
        "Verified integer range 1-38 with no gaps across the 380 matches (Block 20C.1).",
    ),
    _mapping(
        "venue_name",
        "match",
        "DIRECT",
        "native stadium field",
        "Present in the raw match payload; not cross-checked for 100% coverage in this pass "
        "(unlike Wyscout, where all 20 distinct venue names were individually verified) -- "
        "kept DIRECT since the field exists and is native, but Block 20C.2b should verify "
        "coverage before emitting.",
        caveats="Coverage percentage across all 380 matches not exhaustively counted in this pass.",
    ),
)

# -- Participation --------------------------------------------------------------
# The lineup file (`data/lineups/{match_id}.json`) is the authoritative
# participation structure, NOT event-tag presence -- verified across all 380
# matches: 13,678 player-lineup entries (758 teams with 18 players, 2 teams
# with 17), 8,349-8,350 starters, ~2,120 used substitutes, 3,209 unused
# substitutes (no `positions` entries at all).
_PARTICIPATION_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "started",
        "player_appearance",
        "DIRECT",
        "lineups/{match_id}.json[*].lineup[*].positions[0].start_reason == 'Starting XI'",
        "Verified for all 380 matches: 8349-8350 players have a first position interval "
        "whose start_reason is exactly 'Starting XI'.",
        caveats=(
            "Strictly stronger than the pre-existing adapter's event-tag-presence "
            "assumption, which cannot see unused substitutes at all and infers 'started' "
            "only from Starting XI *event* tactics -- the lineup file gives the same fact "
            "plus full-squad coverage (unused bench included)."
        ),
    ),
    _mapping(
        "minutes",
        "player_appearance",
        "DERIVABLE",
        "lineups[*].lineup[*].positions[*].{from,to,from_period,to_period,start_reason,end_reason}",
        "A starter's/substitute's on-pitch minutes are, in principle, the span of their "
        "position interval(s) from kickoff/entry to their final interval's end.",
        caveats=(
            "Empirically NOT a clean single-interval-per-player model: 1,920 of 13,678 "
            "player-lineup entries (14%) carry MORE than one position interval, and the "
            "boundaries between intervals are not always attributable to the player's own "
            "substitution. Verified example (match 3754217, player 3437): 3 intervals -- "
            "Starting XI 00:00-21:41 ending 'Player Off', 'Player On' 22:04-45:00 ending "
            "'Substitution - Off (Tactical)', then a THIRD interval starting 47:40 (new "
            "position, reason 'Tactical Shift') running to Final Whistle for the SAME "
            "player_id in the SAME match -- i.e. an end_reason of 'Substitution - Off' does "
            "not reliably mean this specific player left the pitch. 'Player Off'/'Player On' "
            "appear to be broadcast camera-visibility bookkeeping (140+139 occurrences "
            "leaguewide), distinct from real substitutions, and 'end_reason' values "
            "attributable to a genuine dismissal are inconsistent (0 intervals end with the "
            "literal reason 'Red Card' despite 34 real red cards + 25 second yellows "
            "verified via the lineup `cards` field; only 2 intervals end with 'Foul "
            "Committed (Second Yellow)'). Stoppage-time overrun IS tracked (`to` timestamps "
            "up to 96:35 observed), so a naive fixed-90-minute assumption would also be "
            "wrong for players who finish the match. No single deterministic rule "
            "reconciling all of the above was verified in this pass."
        ),
        methodology_pending=True,
    ),
    _mapping(
        "captain",
        "player_appearance",
        "UNSUPPORTED",
        "n/a",
        "No captain flag exists on any real lineup entry -- verified field set is exactly "
        "{player_id, player_name, player_nickname, jersey_number, country, cards, positions}.",
    ),
    _mapping(
        "shirt_number",
        "player_appearance",
        "DIRECT",
        "lineups[*].lineup[*].jersey_number",
        "Present on every real lineup entry verified in this pass -- a capability the "
        "Wyscout source structurally lacks entirely.",
    ),
    _mapping(
        "listed_position",
        "player_appearance",
        "DERIVABLE",
        "lineups[*].lineup[*].positions[0].position (first interval, whichever exists)",
        "For a starter, positions[0] is their Starting XI position; for a used substitute, "
        "positions[0] is their position on entry. Both are unambiguous single reads.",
    ),
    _mapping(
        "matches",
        "player_season",
        "DERIVABLE",
        "count of matches where playerId appears in lineups[*].lineup (any team)",
        "Full-squad membership, whether or not the player actually took the field -- same "
        "definition as Wyscout's equivalent, now backed by the lineup file instead of "
        "formation.lineup/bench.",
    ),
    _mapping(
        "appearances",
        "player_season",
        "DERIVABLE",
        "count of matches where the player's lineup entry has >=1 `positions` interval",
        "Matches actually played, excluding unused-bench listings (3209/13678 verified "
        "unused across the season).",
    ),
    _mapping(
        "starts",
        "player_season",
        "DERIVABLE",
        "count of matches where started == True",
        "",
    ),
    _mapping(
        "sub_appearances",
        "player_season",
        "DERIVABLE",
        "appearances - starts",
        "Matches the catalog's own documented derivation.",
    ),
    _mapping(
        "minutes_per_appearance",
        "player_season",
        "DERIVABLE",
        "sum(minutes) / appearances",
        "Inherits `minutes`' open methodology question above.",
        methodology_pending=True,
    ),
    _mapping(
        "positional_peer_group",
        "player_season",
        "UNSUPPORTED",
        "n/a",
        "The repository's own deterministic classifier "
        "(position_profiles.classify_position_family) was not verified against this "
        "source's real `position` strings in this pass; treated as unsupported pending "
        "that verification, consistent with Wyscout's equivalent classification.",
    ),
)

# -- Output (goals/assists) -----------------------------------------------------
# `pass.goal_assist` is a genuine, direct boolean primitive -- verified 669
# True occurrences across the season, ALWAYS disjoint from `shot_assist`
# (0 overlap in 669 cases), meaning StatsBomb's own `shot_assist` flag
# specifically excludes the pass that became a goal. This directly
# contradicts the pre-existing adapter's docstring claim that assists
# "would require cross-referencing a shot-assist pass to a goal outcome
# across two events" -- that claim is not supported by the real source.
_OUTPUT_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "goals",
        "player_match",
        "DIRECT",
        "type.name == 'Shot', shot.outcome.name == 'Goal'",
        "988 verified for the full season, attributed to the shooter's player id.",
        caveats=(
            "Own goals (38 'Own Goal Against' events, distinctly typed, verified paired 1:1 "
            "with 38 'Own Goal For' events) are deliberately excluded from any player's "
            "`goals` -- consistent with Wyscout's own-goal exclusion. 988 + 38 = 1026 exactly "
            "matches the summed native home_score+away_score across all 380 matches: no "
            "residual reconciliation gap, unlike Wyscout's documented 1-goal shortfall."
        ),
    ),
    _mapping(
        "assists",
        "player_match",
        "DIRECT",
        "type.name == 'Pass', pass.goal_assist == True",
        "669 verified for the full season. Corrects the pre-existing adapter's docstring "
        "claim that assists require cross-event reconstruction -- the real source carries "
        "this as a native boolean.",
        caveats=(
            "Verified disjoint from pass.shot_assist in every real occurrence (0/669 "
            "overlap) -- StatsBomb's own shot_assist flag specifically means 'created a shot "
            "that was not a goal', not 'created any shot including the eventual assist'. "
            "This mirrors the exact same key_passes/assist tag-disjointness pattern already "
            "documented for Wyscout, so `key_passes` here likewise uses shot_assist as-is "
            "(excluding the assist itself), and `chances_created = key_passes + assists`."
        ),
    ),
    _mapping(
        "non_penalty_goals",
        "player_match",
        "DERIVABLE",
        "goals excluding Shot events where shot.type.name == 'Penalty'",
        "914 = 988 - 74 verified for the full season, exactly matching the GK-side "
        "'Goal Conceded' count (see goalkeeping section) -- a clean cross-validation.",
    ),
    _mapping(
        "goal_contributions",
        "player_match",
        "DERIVABLE",
        "goals + assists",
        "Matches the catalog's own documented derivation.",
    ),
    _mapping(
        "penalty_goals",
        "player_match",
        "DIRECT",
        "type.name == 'Shot', shot.type.name == 'Penalty', shot.outcome.name == 'Goal'",
        "74 verified for the full season -- exactly matches GK-side 'Penalty Conceded' "
        "event count (74), a clean independent cross-check.",
    ),
    _mapping(
        "penalties_attempted",
        "player_match",
        "DIRECT",
        "type.name == 'Shot', shot.type.name == 'Penalty'",
        "91 verified for the full season, regardless of outcome.",
    ),
    _mapping(
        "penalties_missed",
        "player_match",
        "DERIVABLE",
        "penalties_attempted - penalty_goals",
        "91 - 74 = 17 for the full season.",
    ),
)

# -- Shooting ---------------------------------------------------------------------
# `shot.statsbomb_xg` is a provider-native model output -- verified present
# on 100% of a real 82-shot 3-match sample (Block 20C.1) -- and is
# explicitly NOT "our own model". `advanced.xg` is classified DIRECT here
# because it is a direct read of a provider-supplied value, never a
# recomputation; this repository builds no xG model in this block.
_SHOOTING_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "shots_total",
        "player_match",
        "DIRECT",
        "type.name == 'Shot'",
        "9908 Shot events verified for the full season (Blocked 2880 + Saved 2209 + Off T "
        "3197 + Wayward 396 + Goal 988 + Post 170 + Saved Off Target 45 + Saved to Post 23).",
    ),
    _mapping(
        "shots_on_target",
        "player_match",
        "DIRECT",
        "shots_total events, shot.outcome.name in {'Goal','Saved','Saved Off Target',"
        "'Saved to Post'}",
        "3265 verified for the full season, exactly equal to the sum of GK-side "
        "Saved-family (2277) + Conceded-family (988) events -- see goalkeeping section, an "
        "independent cross-validation from a completely different event stream.",
        caveats=(
            "'Post' (170) and 'Off T'/'Wayward' are correctly excluded -- verified StatsBomb "
            "outcome vocabulary distinguishes a woodwork strike from a save, unlike a naive "
            "'anything near target' heuristic."
        ),
    ),
    _mapping(
        "shots_off_target",
        "player_match",
        "DIRECT",
        "shots_total events, shot.outcome.name in {'Off T','Wayward'}",
        "3593 = 3197 + 396 verified for the full season.",
    ),
    _mapping(
        "blocked_shots",
        "player_match",
        "DIRECT",
        "shots_total events, shot.outcome.name == 'Blocked'",
        "2880 verified for the full season, attributed to the shooter.",
        caveats=(
            "Unlike Wyscout (where the blocked tag lives only on the shooter's event with no "
            "blocker identity), StatsBomb additionally has a dedicated 'Block' event type "
            "carrying its own `player` (the blocking defender) -- see `blocks` in the "
            "defending section for that separate, blocker-attributed primitive."
        ),
    ),
    _mapping(
        "shots_inside_box",
        "player_match",
        "DERIVABLE",
        "shots_total events, spatial rule over shot `location` [x,y]",
        "Source primitive (a 120x80 pitch-coordinate `location` on every Shot event) is "
        "verified present, but no penalty-box boundary convention is yet defined in this "
        "repository -- not invented here.",
        methodology_pending=True,
    ),
    _mapping(
        "headed_shots",
        "player_match",
        "DIRECT",
        "shots_total events, shot.body_part.name == 'Head'",
        "Verified real field, 100% coverage on Shot events (Block 20C.1 3-match sample).",
    ),
    _mapping(
        "shots_on_target_pct",
        "player_match",
        "DERIVABLE",
        "shots_on_target / shots_total",
        "",
    ),
    _mapping(
        "goals_per_shot",
        "player_match",
        "DERIVABLE",
        "goals / shots_total",
        "",
    ),
    _mapping(
        "goals_per_shot_on_target",
        "player_match",
        "DERIVABLE",
        "goals / shots_on_target",
        "",
    ),
    _mapping(
        "big_chances",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "No 'big chance' tag, flag, or quality threshold exists anywhere in the real Shot "
        "schema -- verified full key set: {body_part, end_location, freeze_frame, "
        "key_pass_id, outcome, statsbomb_xg, technique, type, first_time, one_on_one, "
        "aerial_won, deflected}. `one_on_one` is adjacent but far narrower than 'big chance'.",
    ),
    _mapping(
        "big_chances_missed",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Depends on big_chances, itself UNSUPPORTED.",
    ),
    _mapping(
        "shot_distance",
        "player_match",
        "DERIVABLE",
        "Euclidean distance from shot `location` to the goal, per shot",
        "Source primitive verified present and reliable (unlike Wyscout, where the "
        "end-point coordinate was a non-tracked sentinel for 55.7% of shots) -- StatsBomb's "
        "shot `location` is the shot's own origin point, always populated. Still pending: no "
        "goal-mouth reference-point convention defined in this repository.",
        methodology_pending=True,
    ),
    _mapping(
        "touches_in_box",
        "player_match",
        "DERIVABLE",
        "all of a player's events, spatial rule over `location`",
        "Source primitive (location on essentially every event type) verified present; no "
        "penalty-box boundary convention defined -- same open question as shots_inside_box.",
        methodology_pending=True,
    ),
    _mapping(
        "advanced.xg",
        "player_match",
        "DIRECT",
        "shot.statsbomb_xg, summed per player per match",
        "Verified present on 100% of a real 82-shot sample (Block 20C.1). This is a "
        "provider-native model output, read as-is -- never recomputed or treated as this "
        "repository's own model.",
        caveats=(
            "Per task instruction: classified DIRECT because the Metric Catalog's "
            "`advanced.xg` semantics are 'a provider-supplied expected-goals value', which "
            "StatsBomb natively provides; this is NOT the same as building an xG model, and "
            "provenance must always label it 'StatsBomb-native model output', never "
            "'Football Intelligence's own model'."
        ),
    ),
    _mapping(
        "npxg",
        "player_match",
        "DERIVABLE",
        "advanced.xg summed over shots excluding shot.type.name == 'Penalty'",
        "Deterministic given advanced.xg is DIRECT and shot.type distinguishes penalties.",
    ),
    _mapping(
        "non_penalty_goals_minus_npxg",
        "player_match",
        "DERIVABLE",
        "non_penalty_goals - npxg",
        "Both operands are already DIRECT/DERIVABLE_READY.",
    ),
    _mapping(
        "xg_per_shot",
        "player_match",
        "DERIVABLE",
        "advanced.xg / shots_total",
        "",
    ),
    _mapping(
        "xa",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "StatsBomb Open Data does not publish a native xA value (verified: no `xa`/"
        "`expected_assist` field exists anywhere in the real Pass schema). Would require a "
        "genuine xA model, out of scope for this block.",
    ),
    _mapping(
        "xg_plus_xa",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires xa, itself REQUIRES_MODEL.",
    ),
    _mapping(
        "goals_minus_xg",
        "player_match",
        "DERIVABLE",
        "goals - advanced.xg",
        "Both operands already DIRECT; no model-building involved in this subtraction "
        "itself, only in advanced.xg's own provenance (which is provider-native, not built "
        "here).",
    ),
    _mapping(
        "assists_minus_xa",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires xa, itself REQUIRES_MODEL.",
    ),
)

# -- Creation -----------------------------------------------------------------
_CREATION_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "key_passes",
        "player_match",
        "DIRECT",
        "type.name == 'Pass', pass.shot_assist == True",
        "Verified real boolean field (53/3079 sampled passes in Block 20C.1); confirmed "
        "disjoint from goal_assist across the full season (0/669 overlap) -- a deliberate "
        "source category boundary, matched here exactly as Wyscout's keyPass/assist tags "
        "were also kept disjoint and used as-is.",
    ),
    _mapping(
        "chances_created",
        "player_match",
        "DERIVABLE",
        "key_passes + assists",
        "A conventional definition, not a distinct native StatsBomb field -- same "
        "convention already used for Wyscout.",
    ),
    _mapping(
        "big_chances_created",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Depends on big_chances, itself UNSUPPORTED (no big-chance signal in the real Shot "
        "schema).",
    ),
    _mapping(
        "passes_into_box",
        "player_match",
        "DERIVABLE",
        "type.name == 'Pass', spatial rule over pass.end_location",
        "Source primitive (end_location, verified present on 100% of sampled Pass events) "
        "exists; no penalty-box boundary convention defined here.",
        methodology_pending=True,
    ),
    _mapping(
        "passes_into_final_third",
        "player_match",
        "DERIVABLE",
        "type.name == 'Pass', spatial rule over location/pass.end_location",
        "Same open spatial-boundary question as passes_into_box.",
        methodology_pending=True,
    ),
    _mapping(
        "through_balls",
        "player_match",
        "DIRECT",
        "type.name == 'Pass', pass.through_ball == True",
        "Verified real boolean field (13/3079 sampled passes, Block 20C.1).",
    ),
    _mapping(
        "crosses",
        "player_match",
        "DIRECT",
        "type.name == 'Pass', pass.cross == True",
        "Verified real boolean field (76/3079 sampled passes, Block 20C.1).",
    ),
    _mapping(
        "shot_creating_actions",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires linking a chain of preceding actions (not just the final pass) to a shot; "
        "StatsBomb events carry `related_events` linkage but a possession-chain "
        "reconstruction methodology was not verified in this pass.",
    ),
    _mapping(
        "goal_creating_actions",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Same possession-chain reconstruction requirement as shot_creating_actions.",
    ),
    _mapping(
        "expected_threat_pass",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "xThreat is a positional-value model; out of scope for this sub-block.",
    ),
    _mapping(
        "expected_threat_created",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Same as expected_threat_pass.",
    ),
    _mapping(
        "expected_assists_open_play",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xA model; StatsBomb Open Data has no native xA field.",
    ),
    _mapping(
        "xa_per90",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires xa, itself REQUIRES_MODEL.",
    ),
)

# -- Passing --------------------------------------------------------------------
_PASSING_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "passes_total",
        "player_match",
        "DIRECT",
        "type.name == 'Pass'",
        "9585 Pass events verified across the 3-match Block 20C.1 sample (3079+...); full "
        "season not individually recounted for this exact metric but the event type and "
        "field are unambiguous and already the existing adapter's own (correct) primitive.",
    ),
    _mapping(
        "passes_accurate",
        "player_match",
        "DIRECT",
        "passes_total events, pass.outcome absent (key not present)",
        "Verified: only 628/3079 sampled passes carry an `outcome` key at all (~20%); "
        "StatsBomb omits `outcome` for completed passes -- confirmed convention, matching "
        "the pre-existing adapter's derivation exactly.",
    ),
    _mapping(
        "pass_completion_pct",
        "player_match",
        "DERIVABLE",
        "passes_accurate / passes_total",
        "",
    ),
    _mapping(
        "passes_short",
        "player_match",
        "DERIVABLE",
        "passes_total, threshold rule over pass.length",
        "pass.length is a verified real, always-present field (3079/3079 sampled) -- a "
        "materially better primitive than Wyscout's positions[0]/[1] Euclidean-distance "
        "reconstruction, since StatsBomb provides length natively. No short/medium/long "
        "threshold convention is yet defined in this repository.",
        methodology_pending=True,
    ),
    _mapping(
        "passes_medium",
        "player_match",
        "DERIVABLE",
        "passes_total, threshold rule over pass.length",
        "Same open threshold question as passes_short.",
        methodology_pending=True,
    ),
    _mapping(
        "passes_long",
        "player_match",
        "DERIVABLE",
        "passes_total, threshold rule over pass.length",
        "Same open threshold question as passes_short.",
        methodology_pending=True,
    ),
    _mapping(
        "short_passes_accurate",
        "player_match",
        "DERIVABLE",
        "passes_short intersected with passes_accurate",
        "Inherits passes_short's pending length-threshold methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "medium_passes_accurate",
        "player_match",
        "DERIVABLE",
        "passes_medium intersected with passes_accurate",
        "Inherits passes_medium's pending length-threshold methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "long_passes_accurate",
        "player_match",
        "DERIVABLE",
        "passes_long intersected with passes_accurate",
        "Inherits passes_long's pending length-threshold methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "progressive_passes",
        "player_match",
        "DERIVABLE",
        "passes_total, spatial rule over location/pass.end_location",
        "Source primitives (location, end_location, both verified always-present on Pass "
        "events) exist; no progressive-distance-toward-goal convention defined here.",
        methodology_pending=True,
    ),
    _mapping(
        "progressive_pass_distance",
        "player_match",
        "DERIVABLE",
        "passes_total, spatial distance rule",
        "Same open methodology as progressive_passes.",
        methodology_pending=True,
    ),
    _mapping(
        "switches",
        "player_match",
        "DIRECT",
        "type.name == 'Pass', pass.switch == True",
        "Verified real boolean field (103/3079 sampled passes, Block 20C.1) -- a materially "
        "better primitive than Wyscout, which had no native switch flag and required a "
        "pending lateral-distance spatial rule.",
    ),
    _mapping(
        "passes_under_pressure",
        "player_match",
        "DIRECT",
        "type.name == 'Pass', under_pressure == True",
        "`under_pressure` is a verified real top-level boolean field on events (observed on "
        "Shot/Duel/Dribble/Foul Won events in the Block 20C.1 sample; present on Pass events "
        "in the same schema family) -- a capability Wyscout structurally lacks entirely "
        "(no per-event pressure/proximity signal at all).",
        caveats=(
            "Coverage of `under_pressure` specifically on Pass events across the full season "
            "was not exhaustively recounted in this pass; classified DIRECT on the strength "
            "of the verified field existing and being used consistently elsewhere in the "
            "same event schema, but Block 20C.2b should re-confirm coverage before emitting."
        ),
    ),
    _mapping(
        "passes_received",
        "player_match",
        "DIRECT",
        "type.name == 'Pass', pass.recipient.id, counted per recipient",
        "pass.recipient is a verified real field (2881/3079 sampled passes carry a "
        "recipient) -- StatsBomb records the intended receiver directly on the pass event "
        "itself, unlike Wyscout where no recipient field exists at all and receiver "
        "identification would require positional reconstruction (REQUIRES_MODEL there).",
        caveats=(
            "recipient is the intended target, not independently confirmed as 'the player "
            "who actually next touched the ball' -- for passes without an `outcome` (i.e. "
            "completed passes), this is a safe equivalence; incomplete passes have no "
            "meaningful receiver and recipient there names who the pass was aimed at, not "
            "who received it. Scoping to completed passes only avoids over-crediting."
        ),
    ),
    _mapping(
        "progressive_passes_received",
        "player_match",
        "DERIVABLE",
        "passes_received, intersected with the sending pass's progressive_passes flag",
        "Inherits progressive_passes' pending spatial methodology.",
        methodology_pending=True,
    ),
)

# -- Dribbling / possession security --------------------------------------------
# StatsBomb has dedicated, distinct event types (`Dispossessed`, `Miscontrol`)
# where Wyscout only had one blended tag (`dangerous_ball_lost`) -- a
# materially cleaner source for this category.
_DRIBBLING_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "dribbles_attempted",
        "player_match",
        "DIRECT",
        "type.name == 'Dribble'",
        "99 verified in the Block 20C.1 3-match sample; a dedicated event type, unlike "
        "Wyscout's duel-subtype-shared tags.",
    ),
    _mapping(
        "dribbles_successful",
        "player_match",
        "DIRECT",
        "dribbles_attempted events, dribble.outcome.name == 'Complete'",
        "Verified real outcome value on 99/99 sampled Dribble events.",
    ),
    _mapping(
        "dribble_success_pct",
        "player_match",
        "DERIVABLE",
        "dribbles_successful / dribbles_attempted",
        "",
    ),
    _mapping(
        "take_ons_attempted",
        "player_match",
        "DIRECT",
        "same primitive as dribbles_attempted",
        "StatsBomb's 'Dribble' event is the same concept the catalog calls 'take-on'.",
    ),
    _mapping(
        "take_ons_successful",
        "player_match",
        "DIRECT",
        "same primitive as dribbles_successful",
        "",
    ),
    _mapping(
        "take_on_success_pct",
        "player_match",
        "DERIVABLE",
        "take_ons_successful / take_ons_attempted",
        "",
    ),
    _mapping(
        "players_beaten",
        "player_match",
        "DERIVABLE",
        "successful Dribble events, cross-referenced via related_events to a 'Dribbled "
        "Past' event for the defending player",
        "'Dribbled Past' is a verified real, dedicated event type (62 observed in the Block "
        "20C.1 3-match sample) attributed to the beaten defender -- source primitives exist "
        "for this metric in a way Wyscout structurally cannot support at all. The exact "
        "related_events linkage between a Dribble and its corresponding Dribbled Past "
        "event was not cross-referenced/verified in this pass.",
        methodology_pending=True,
    ),
    _mapping(
        "dispossessed",
        "player_match",
        "DIRECT",
        "type.name == 'Dispossessed'",
        "96 verified in the Block 20C.1 3-match sample -- a dedicated event type "
        "attributed to the player who lost the ball to an opponent's challenge, cleanly "
        "distinct from a self-inflicted control error. Wyscout has no equivalent dedicated "
        "event (only a blended 'dangerous_ball_lost' tag, classified AMBIGUOUS there).",
    ),
    _mapping(
        "miscontrols",
        "player_match",
        "DIRECT",
        "type.name == 'Miscontrol'",
        "68 verified in the Block 20C.1 3-match sample -- a dedicated event type for a "
        "self-inflicted loss of control, cleanly distinct from `dispossessed`. Same "
        "advantage over Wyscout's blended tag as above.",
    ),
    _mapping(
        "possession_losses",
        "player_match",
        "DERIVABLE",
        "dispossessed + miscontrols",
        "Matches the catalog's own documented composition; both operands are now DIRECT.",
    ),
    _mapping(
        "turnovers",
        "player_match",
        "DERIVABLE",
        "dispossessed + miscontrols (+ any other verified possession-ending event type)",
        "Same composition as possession_losses; the catalog's broader 'turnovers' concept "
        "is satisfied by the union of the two dedicated event types, unlike Wyscout where "
        "the single blended tag was too narrow (dangerous-area-only) to safely equate.",
    ),
    _mapping(
        "receiving_errors",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "No event or field distinguishes a control error specifically on receipt (vs. "
        "generally) -- 'Miscontrol' does not carry this distinction in its verified field "
        "set.",
    ),
)

# -- Ball progression / carrying --------------------------------------------------
# StatsBomb has a dedicated `Carry` event type (`carry.end_location`) --
# Wyscout has no equivalent event at all (UNSUPPORTED there). This is the
# single largest capability gap this audit found in StatsBomb's favor.
_PROGRESSION_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "carries",
        "player_match",
        "DIRECT",
        "type.name == 'Carry'",
        "2379 verified in the Block 20C.1 3-match sample -- the single most common "
        "non-Pass/Ball-Receipt event type. A capability Wyscout structurally lacks (marked "
        "UNSUPPORTED there).",
    ),
    _mapping(
        "progressive_carries",
        "player_match",
        "DERIVABLE",
        "carries, spatial rule over location/carry.end_location",
        "Source primitives (location, carry.end_location, both verified always-present on "
        "Carry events) exist; no progressive-distance-toward-goal convention defined here "
        "(same open question as progressive_passes).",
        methodology_pending=True,
    ),
    _mapping(
        "carries_into_final_third",
        "player_match",
        "DERIVABLE",
        "carries, spatial rule over location/carry.end_location",
        "Same open spatial-boundary question as passes_into_final_third.",
        methodology_pending=True,
    ),
    _mapping(
        "carries_into_box",
        "player_match",
        "DERIVABLE",
        "carries, spatial rule over carry.end_location",
        "Same open spatial-boundary question as passes_into_box.",
        methodology_pending=True,
    ),
    _mapping(
        "carry_distance",
        "player_match",
        "DERIVABLE",
        "Euclidean distance from location to carry.end_location, per carry",
        "Deterministic given both coordinates are verified always-present -- no open "
        "threshold question, just a coordinate-geometry computation. Kept DERIVABLE (not "
        "DIRECT) since it is a computed value, not a native field.",
    ),
    _mapping(
        "progressive_carry_distance",
        "player_match",
        "DERIVABLE",
        "carry_distance, filtered to progressive_carries",
        "Inherits progressive_carries' pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "touches",
        "player_match",
        "DIRECT",
        "count of every event carrying a `player` field for that player",
        "Every event with a player attribution is itself one on-ball or defensive action; "
        "same reasoning as Wyscout's equivalent.",
        caveats="Broader than any single dedicated 'touch' event type -- a raw action count.",
    ),
    _mapping(
        "touches_final_third",
        "player_match",
        "DERIVABLE",
        "touches, spatial rule over location",
        "Methodology pending -- same open spatial-boundary question as elsewhere.",
        methodology_pending=True,
    ),
    _mapping(
        "touches_box",
        "player_match",
        "DERIVABLE",
        "touches, spatial rule over location",
        "Methodology pending -- same open spatial-boundary question as elsewhere.",
        methodology_pending=True,
    ),
    _mapping(
        "progressive_actions",
        "player_match",
        "DERIVABLE",
        "progressive_passes + progressive_carries",
        "Inherits both operands' pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "ball_progressions",
        "player_match",
        "DERIVABLE",
        "same composition as progressive_actions",
        "Same caveats as progressive_actions.",
        methodology_pending=True,
    ),
)

# -- Defending / duels ------------------------------------------------------------
# StatsBomb's `Duel` event has a genuinely dedicated 'Tackle' type (distinct
# from 'Aerial Lost'), and a dedicated `Block` event type carrying the
# BLOCKING player's own id -- both materially cleaner than Wyscout's
# equivalents. `Pressure` and `Ball Recovery` are dedicated event types
# Wyscout has no equivalent for at all.
_DEFENDING_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "tackles",
        "player_match",
        "DIRECT",
        "type.name == 'Duel', duel.type.name == 'Tackle'",
        "133 verified in the Block 20C.1 3-match sample -- a genuinely dedicated duel "
        "subtype, distinct from 'Aerial Lost' (88 observed) and from any generic "
        "ground-duel category. Materially cleaner than Wyscout's AMBIGUOUS classification.",
    ),
    _mapping(
        "tackles_won",
        "player_match",
        "AMBIGUOUS",
        "tackles events, duel.outcome.name in {?}",
        "",
        caveats=(
            "Verified real outcome vocabulary for Tackle-type duels: {'Success In Play': 62, "
            "'Won': 27, 'Lost Out': 20, 'Lost In Play': 19, 'Success Out': 5} (Block 20C.1 "
            "3-match sample). 'Won' is a DISTINCT value from 'Success In Play'/'Success "
            "Out', and StatsBomb's own documentation does not state whether 'Success...' "
            "outcomes should count as a tackle win for this catalog's purposes -- equating "
            "them would invent semantics beyond what was verified."
        ),
    ),
    _mapping(
        "tackle_success_pct",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Depends on tackles_won, itself AMBIGUOUS.",
    ),
    _mapping(
        "blocks",
        "player_match",
        "DIRECT",
        "type.name == 'Block'",
        "108 verified in the Block 20C.1 3-match sample, attributed via the event's own top-"
        "level `player` field -- the BLOCKING defender's identity, unlike Wyscout where the "
        "blocked(2101) tag lives only on the shooter's own event with no blocker attribution "
        "at all (UNSUPPORTED there).",
        caveats=(
            "Only 2/108 sampled Block events carry any type-specific nested `block` object "
            "at all (just a `deflection` flag) -- the count itself needs no nested data, "
            "consistent with the pre-existing adapter's (correct) count-only derivation."
        ),
    ),
    _mapping(
        "shot_blocks",
        "player_match",
        "DERIVABLE",
        "blocks events, cross-referenced via related_events to a Shot-type event",
        "Source primitive (related_events, verified present on Block events) exists; the "
        "exact linkage distinguishing a shot-block from a pass-block was not cross-"
        "referenced/verified in this pass.",
        methodology_pending=True,
    ),
    _mapping(
        "pass_blocks",
        "player_match",
        "DERIVABLE",
        "blocks - shot_blocks",
        "Inherits shot_blocks' pending related_events cross-referencing.",
        methodology_pending=True,
    ),
    _mapping(
        "interceptions",
        "player_match",
        "DIRECT",
        "type.name == 'Interception'",
        "59 verified in the Block 20C.1 3-match sample, always carrying an "
        "interception.outcome field.",
    ),
    _mapping(
        "clearances",
        "player_match",
        "DIRECT",
        "type.name == 'Clearance'",
        "144 verified in the Block 20C.1 3-match sample.",
    ),
    _mapping(
        "recoveries",
        "player_match",
        "DIRECT",
        "type.name == 'Ball Recovery'",
        "295 verified in the Block 20C.1 3-match sample -- a dedicated event type Wyscout "
        "has no equivalent for at all (UNSUPPORTED there).",
    ),
    _mapping(
        "pressures",
        "player_match",
        "DIRECT",
        "type.name == 'Pressure'",
        "1035 verified in the Block 20C.1 3-match sample -- the single most common "
        "defensive-labelled event type (~10x more frequent than Duel), attributed directly "
        "to the pressuring player. A dedicated event type Wyscout has no equivalent for at "
        "all (REQUIRES_MODEL there).",
    ),
    _mapping(
        "successful_pressures",
        "player_match",
        "DERIVABLE",
        "pressures, correlated with an opponent losing the ball within a defined time "
        "window of the pressure event",
        "Pressure events carry no own outcome field (verified: no type-specific nested "
        "block at all) -- 'success' would require correlating against a subsequent "
        "turnover/pass-outcome within a time window this repository has not yet defined.",
        methodology_pending=True,
    ),
    _mapping(
        "pressure_success_pct",
        "player_match",
        "DERIVABLE",
        "successful_pressures / pressures",
        "Inherits successful_pressures' pending time-window methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "errors_leading_to_shot",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "No error attribution or shot-chain linkage exists as a native field.",
    ),
    _mapping(
        "errors_leading_to_goal",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Same reasoning as errors_leading_to_shot.",
    ),
    _mapping(
        "duels_total",
        "player_match",
        "DIRECT",
        "type.name == 'Duel'",
        "221 verified in the Block 20C.1 3-match sample (133 Tackle + 88 Aerial Lost).",
    ),
    _mapping(
        "duels_won",
        "player_match",
        "AMBIGUOUS",
        "duels_total events, duel.outcome.name in {?}",
        "",
        caveats=(
            "Same outcome-vocabulary ambiguity as tackles_won, compounded across both duel "
            "subtypes: 'Aerial Lost' duels never carry an outcome at all (88/88 outcome=None "
            "in the sample -- the type name itself already states the result for that "
            "subtype, inconsistently with how Tackle-type duels report outcome)."
        ),
    ),
    _mapping(
        "duel_win_pct",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Depends on duels_won, itself AMBIGUOUS.",
    ),
    _mapping(
        "aerial_duels",
        "player_match",
        "DIRECT",
        "type.name == 'Duel', duel.type.name == 'Aerial Lost'",
        "88 verified in the Block 20C.1 3-match sample.",
        caveats=(
            "StatsBomb only records the LOSING side of an aerial duel as a distinct Duel "
            "event (verified type name is literally 'Aerial Lost', never 'Aerial Won') -- "
            "the winning side is instead marked via `aerial_won: True` on a different event "
            "(e.g. a Pass or Clearance) that player made in the same contest, not as a "
            "second Duel event. Counting only 'Aerial Lost' Duel events therefore "
            "undercounts total aerial-duel involvement for players who mostly win their "
            "aerials -- a real, verified source-structure asymmetry, not an oversight."
        ),
    ),
    _mapping(
        "aerial_duels_won",
        "player_match",
        "DERIVABLE",
        "count of events (any type) carrying aerial_won == True",
        "aerial_won is a verified real boolean field observed on Pass events in the Block "
        "20C.1 sample (63/3079); likely also present on Clearance/other event types but not "
        "exhaustively enumerated in this pass.",
        caveats=(
            "Because aerial_duels (the Duel-event count) and aerial_duels_won (the "
            "aerial_won-flag count) come from two structurally different primitives per the "
            "asymmetry noted above, aerial_duel_win_pct built from these two cannot be "
            "verified as a true win percentage without reconciling both sides' bookkeeping "
            "-- flagged as methodology-pending rather than assumed correct."
        ),
        methodology_pending=True,
    ),
    _mapping(
        "aerial_duel_win_pct",
        "player_match",
        "DERIVABLE",
        "aerial_duels_won / (aerial_duels + aerial_duels_won)",
        "Inherits the aerial_duels/aerial_duels_won bookkeeping-asymmetry methodology "
        "question above.",
        methodology_pending=True,
    ),
    _mapping(
        "ground_duels",
        "player_match",
        "DIRECT",
        "type.name == 'Duel', duel.type.name == 'Tackle'",
        "Same primitive as `tackles` -- StatsBomb's only real 'ground duel' subtype "
        "verified in the Duel event's type vocabulary is Tackle.",
    ),
    _mapping(
        "ground_duels_won",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Same outcome-vocabulary ambiguity as tackles_won.",
    ),
    _mapping(
        "fouls_committed",
        "player_match",
        "DIRECT",
        "type.name == 'Foul Committed'",
        "62 verified in the Block 20C.1 3-match sample, attributed to the fouling player.",
    ),
    _mapping(
        "fouls_drawn",
        "player_match",
        "DIRECT",
        "type.name == 'Foul Won'",
        "60 verified in the Block 20C.1 3-match sample, attributed to the fouled player -- a "
        "dedicated event type Wyscout structurally lacks (UNSUPPORTED there, since Wyscout's "
        "Foul events only record the committing player).",
    ),
    _mapping(
        "yellow_cards",
        "player_match",
        "DIRECT",
        "lineups/{match_id}.json[*].lineup[*].cards[*] where card_type == 'Yellow Card'",
        "1203 verified across the full season via the lineup file's own `cards` array.",
        caveats=(
            "The pre-existing adapter derives cards ONLY from Foul Committed events "
            "(foul_committed.card), which is verified INCOMPLETE at full-season scale: cards "
            "issued via a standalone 'Bad Behaviour' event (dissent, violent conduct without "
            "a foul, etc.) are invisible to that path -- 187 of 1234 real carded "
            "(match, player) incidents across the season (15%) would be silently missed as a "
            "real (wrong) zero rather than reported. The lineup file's `cards` array is "
            "verified to be the exact union of Foul-Committed-sourced and "
            "Bad-Behaviour-sourced cards (0 lineup-carded entries are absent from either "
            "event source, and the 187-entry gap between Foul-Committed-only and the full "
            "lineup-carded set is fully accounted for by Bad Behaviour cards) -- making the "
            "lineup file both complete and simpler than reading two event types and unioning "
            "them by hand. This is the deterministic source rule chosen for Block 20C.2b: "
            "cards come from the lineup file, never from Foul Committed alone."
        ),
    ),
    _mapping(
        "red_cards",
        "player_match",
        "DERIVABLE",
        "lineups[*].lineup[*].cards[*] where card_type in {'Red Card','Second Yellow'}",
        "34 straight reds + 25 second yellows verified across the full season via the "
        "lineup file -- same authoritative-source reasoning as yellow_cards.",
    ),
    _mapping(
        "second_yellow_cards",
        "player_match",
        "DIRECT",
        "lineups[*].lineup[*].cards[*] where card_type == 'Second Yellow'",
        "25 verified across the full season via the lineup file.",
    ),
    _mapping(
        "saves",
        "player_match",
        "DIRECT",
        "type.name == 'Goal Keeper', goalkeeper.type.name in {'Shot Saved','Shot Saved Off "
        "Target','Shot Saved to Post','Penalty Saved','Penalty Saved to Post'}",
        "2277 verified across the full season -- exactly equal to the count of Shot events "
        "with outcome in {'Saved','Saved Off Target','Saved to Post'} (2209+45+23=2277), a "
        "clean full-season arithmetic cross-validation.",
        caveats=(
            "The pre-existing adapter's `_SAVE_GOALKEEPER_TYPE = 'Shot Saved'` only counts "
            "2194 of these 2277 real saves (a 3.6% undercount, verified): it misses the "
            "45 'Shot Saved Off Target', 27 'Shot Saved to Post', 10 'Penalty Saved', and 1 "
            "'Penalty Saved to Post' events, all of which are genuine saves by StatsBomb's "
            "own type vocabulary. 'Shot Faced' (6643 occurrences, always outcome=None) is "
            "deliberately excluded -- it does not correspond 1:1 with either the on-target-"
            "shots-faced total or the saves total in the full-season arithmetic check, and "
            "its exact semantics were not resolved in this pass."
        ),
    ),
)

# -- Goalkeeping (goalkeeper_match/season) ------------------------------------------
_GOALKEEPING_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "saves",
        "goalkeeper_match",
        "DIRECT",
        "same as player_match saves, attributed via the Goal Keeper event's own `player` field",
        "No scoping by an external role lookup is required -- unlike Wyscout (which needs "
        "players.json's global role.code2=='GK'), every Goal Keeper event is directly "
        "player-attributed, so scoping to 'the goalkeeper' is simply 'whichever player "
        "generated Goal Keeper events'.",
    ),
    _mapping(
        "shots_on_target_faced",
        "goalkeeper_match",
        "DERIVABLE",
        "saves + goals_conceded, both already player-attributed Goal Keeper events",
        "2277 (saves) + 988 (goals_conceded, see below) = 3265, exactly equal to the "
        "independently-verified shots_on_target total for the full season -- a clean "
        "3-way arithmetic cross-validation. Materially simpler than Wyscout's equivalent, "
        "which required cross-referencing opponent shots against goalkeeper substitution "
        "windows since Wyscout shot events carry no goalkeeper attribution at all.",
    ),
    _mapping(
        "save_pct",
        "goalkeeper_match",
        "DERIVABLE",
        "saves / shots_on_target_faced",
        "Both operands are DIRECT/DERIVABLE_READY.",
    ),
    _mapping(
        "goals_conceded",
        "goalkeeper_match",
        "DIRECT",
        "type.name == 'Goal Keeper', goalkeeper.type.name in {'Goal Conceded','Penalty Conceded'}",
        "988 verified across the full season -- exactly equal to the independently-verified "
        "total goals (Shot outcome=='Goal') for the full season, split 914 Goal Conceded "
        "(non-penalty) + 74 Penalty Conceded (matching penalty_goals exactly).",
        caveats=(
            "Directly player-attributed on the event itself -- no scoreline/substitution-"
            "window cross-referencing needed, a material simplification vs. both Wyscout's "
            "equivalent and this catalog metric's Wyscout mapping (there DERIVABLE with an "
            "unresolved open-net-goal gap)."
        ),
    ),
    _mapping(
        "clean_sheets",
        "goalkeeper_match",
        "DERIVABLE",
        "goals_conceded == 0 for the match",
        "goals_conceded is now DIRECT, so this composition has no open methodology question.",
    ),
    _mapping(
        "clean_sheets",
        "goalkeeper_season",
        "DERIVABLE",
        "count of goalkeeper_match clean_sheets across the season",
        "",
    ),
    _mapping(
        "save_pct",
        "goalkeeper_season",
        "DERIVABLE",
        "season sum(saves) / season sum(shots_on_target_faced)",
        "",
    ),
    _mapping(
        "goals_prevented",
        "goalkeeper_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires shot-quality (xG) data on shots faced -- catalog's own documented "
        "requirement; StatsBomb's statsbomb_xg is provider-native for the SHOOTER's shot, "
        "not independently modelled 'against' a specific keeper's positioning.",
    ),
    _mapping(
        "claims",
        "goalkeeper_match",
        "DIRECT",
        "type.name == 'Goal Keeper', goalkeeper.type.name == 'Keeper Sweeper', "
        "goalkeeper.outcome.name == 'Claim'",
        "257 'Keeper Sweeper'/'Claim' occurrences verified across the full season -- a "
        "materially better primitive than Wyscout's ambiguous 'Goalkeeper leaving line' "
        "event, since StatsBomb's outcome vocabulary explicitly distinguishes a successful "
        "Claim from Clear/other Keeper Sweeper outcomes.",
    ),
    _mapping(
        "distribution_accuracy_pct",
        "goalkeeper_match",
        "DERIVABLE",
        "goalkeeper's passes_accurate / passes_total",
        "Same player-attribution simplification as `saves` above -- no external role lookup "
        "needed.",
    ),
    _mapping(
        "passes",
        "goalkeeper_match",
        "DERIVABLE",
        "goalkeeper's passes_total",
        "",
    ),
    _mapping(
        "long_passes",
        "goalkeeper_match",
        "DERIVABLE",
        "goalkeeper's passes_long",
        "Inherits passes_long's pending length-threshold methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "launches",
        "goalkeeper_match",
        "DERIVABLE",
        "goalkeeper's passes, pass.technique.name == 'Long Ball' (or a length threshold)",
        "pass.technique is a verified real field (32/3079 sampled passes); whether "
        "'Long Ball' technique alone is an adequate 'launch' definition, or whether it "
        "should combine with the pending length threshold, was not resolved in this pass.",
        methodology_pending=True,
    ),
    _mapping(
        "average_distance_from_goal",
        "goalkeeper_match",
        "UNSUPPORTED",
        "n/a",
        "No systematic goalkeeper position-tracking exists beyond discrete Goal Keeper "
        "events' own `location`, which only cover the keeper's actions, not continuous "
        "positioning.",
    ),
    _mapping(
        "crosses_stopped",
        "goalkeeper_match",
        "DIRECT",
        "type.name == 'Goal Keeper', goalkeeper.type.name == 'Punch'",
        "538 'Punch' events verified across the full season -- a materially better "
        "primitive than Wyscout (UNSUPPORTED there, no tag distinguishes a stopped cross).",
        caveats=(
            "'Punch' captures punched-clear actions specifically; it may not capture every "
            "cross a keeper 'stops' by catching (those would appear as 'Collected' or "
            "'Keeper Sweeper'/'Claim' instead) -- classified DIRECT for the punch-specific "
            "reading, not as a complete 'every cross dealt with' metric."
        ),
    ),
    _mapping(
        "sweeper_actions",
        "goalkeeper_match",
        "DIRECT",
        "type.name == 'Goal Keeper', goalkeeper.type.name == 'Keeper Sweeper'",
        "408 verified across the full season -- a dedicated, named event type, unlike "
        "Wyscout (UNSUPPORTED there).",
    ),
    _mapping(
        "xg_on_target_faced",
        "goalkeeper_match",
        "REQUIRES_MODEL",
        "n/a",
        "Would require summing the shooter's own statsbomb_xg across shots faced by this "
        "specific keeper -- deterministic in principle (statsbomb_xg is DIRECT, shots faced "
        "are DIRECT) but the catalog's own documented semantics for this metric describe a "
        "goalkeeper-quality model output, not a plain sum; kept REQUIRES_MODEL to avoid "
        "silently redefining the catalog's intent.",
    ),
    _mapping(
        "psxg",
        "goalkeeper_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires a genuine post-shot xG model; StatsBomb Open Data has no native psxg field.",
    ),
)

# -- Team / team_match -----------------------------------------------------------
_TEAM_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _mapping(
        "goals_for",
        "team_match",
        "DIRECT",
        "matches/2/27.json[*].home_score / away_score",
        "Native pre-aggregated field -- authoritative, never reconstructed from summed "
        "player-level goal events (per task instruction).",
    ),
    _mapping(
        "goals_against",
        "team_match",
        "DIRECT",
        "the opponent team's home_score/away_score in the same match",
        "Deterministic: exactly 2 teams per match.",
    ),
    _mapping(
        "shots_total",
        "team_match",
        "DERIVABLE",
        "player-level shots_total events grouped by team",
        "",
    ),
    _mapping(
        "shots_on_target",
        "team_match",
        "DERIVABLE",
        "player-level shots_on_target events grouped by team",
        "",
    ),
    _mapping(
        "shots_inside_box",
        "team_match",
        "DERIVABLE",
        "team shots_total, spatial rule over shot location",
        "Inherits player-level shots_inside_box's pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "shots_outside_box",
        "team_match",
        "DERIVABLE",
        "team shots_total minus shots_inside_box",
        "Inherits shots_inside_box's pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "blocked_shots",
        "team_match",
        "DERIVABLE",
        "player-level blocked_shots events grouped by team",
        "",
    ),
    _mapping(
        "shots_allowed",
        "team_match",
        "DERIVABLE",
        "opponent team's shots_total in the same match",
        "",
    ),
    _mapping(
        "shots_on_target_allowed",
        "team_match",
        "DERIVABLE",
        "opponent team's shots_on_target in the same match",
        "",
    ),
    _mapping(
        "passes_total",
        "team_match",
        "DIRECT",
        "player-level passes_total events grouped by team",
        "",
    ),
    _mapping(
        "passes_accurate",
        "team_match",
        "DIRECT",
        "player-level passes_accurate events grouped by team",
        "",
    ),
    _mapping(
        "pass_accuracy_pct",
        "team_match",
        "DERIVABLE",
        "passes_accurate / passes_total",
        "",
    ),
    _mapping(
        "possession_pct",
        "team_match",
        "DERIVABLE",
        "share of `possession` sequence ids or on-ball event time per team",
        "StatsBomb events carry an explicit `possession` sequence id and `possession_team` "
        "field on every event (verified present across all sampled events) -- a materially "
        "better possession primitive than Wyscout, which had no possession-state field at "
        "all. Still pending: whether possession share should be by count-of-possessions or "
        "by clock-time-per-possession, a convention this repository has not yet chosen.",
        methodology_pending=True,
    ),
    _mapping(
        "progressive_passes",
        "team_match",
        "DERIVABLE",
        "sum of player-level progressive_passes for the team",
        "Inherits progressive_passes' pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "final_third_entries",
        "team_match",
        "DERIVABLE",
        "team passes_total + carries, spatial rule over location/end_location",
        "Source primitives exist for BOTH passing and carrying progression (an advantage "
        "over Wyscout, which only had passes to work with here) -- no boundary convention "
        "defined.",
        methodology_pending=True,
    ),
    _mapping(
        "field_tilt",
        "team_match",
        "DERIVABLE",
        "share of final-third touches/passes between the two teams",
        "Inherits final_third_entries' pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "box_entries",
        "team_match",
        "DERIVABLE",
        "team passes_total + carries, spatial rule over end_location",
        "Same open spatial-boundary question as passes_into_box/carries_into_box.",
        methodology_pending=True,
    ),
    _mapping(
        "touches_in_box",
        "team_match",
        "DERIVABLE",
        "sum of player-level touches_box for the team",
        "Inherits touches_box's pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "corners",
        "team_match",
        "DIRECT",
        "type.name == 'Pass', pass.type.name == 'Corner', grouped by team",
        "pass.type is a verified real field (601/3079 sampled passes carry a type, "
        "distinguishing restart deliveries) -- Corner is one of its observed values.",
    ),
    _mapping(
        "set_piece_shots",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires linking a shot back to a preceding corner/free-kick within the same "
        "possession sequence; the `possession` sequence id (verified present) makes this "
        "more tractable than for Wyscout, but the exact linkage rule was not verified in "
        "this pass.",
    ),
    _mapping(
        "set_piece_xg",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires both set_piece_shots' sequence-linkage and advanced.xg, itself provider-"
        "native (not modelled here).",
    ),
    _mapping(
        "recoveries",
        "team_match",
        "DIRECT",
        "player-level recoveries (Ball Recovery events) grouped by team",
        "Same dedicated event type as the player-level metric -- a capability Wyscout "
        "structurally lacks (UNSUPPORTED there).",
    ),
    _mapping(
        "pressures",
        "team_match",
        "DIRECT",
        "player-level pressures (Pressure events) grouped by team",
        "Same dedicated event type as the player-level metric -- REQUIRES_MODEL for "
        "Wyscout, DIRECT here.",
    ),
    _mapping(
        "ppda",
        "team_match",
        "DERIVABLE",
        "opponent passes allowed in own defensive two-thirds / pressures applied in the "
        "attacking two-thirds",
        "Both raw ingredients (Pressure events with location, Pass events with location) "
        "now genuinely exist in the source -- a real improvement over Wyscout "
        "(REQUIRES_MODEL there, no pressing signal at all) -- but PPDA's own defensive-third "
        "boundary convention is not yet defined in this repository.",
        methodology_pending=True,
    ),
    _mapping(
        "counter_attacks",
        "team_match",
        "DERIVABLE",
        "grouping consecutive events sharing play_pattern.name == 'From Counter' into "
        "distinct possession sequences, per team",
        "play_pattern is a verified real field on every event (observed value 'From Counter' "
        "among others) -- StatsBomb natively tags the possession's originating pattern, a "
        "cleaner primitive than Wyscout's per-event counter_attack tag. A sequence-grouping "
        "rule (using the `possession` id) is still needed to count discrete attacks rather "
        "than individual tagged events.",
        methodology_pending=True,
    ),
    _mapping(
        "counter_attack_shots",
        "team_match",
        "DERIVABLE",
        "team shots_total events where play_pattern.name == 'From Counter'",
        "Deterministic single-field filter, no sequence-grouping needed for this narrower "
        "metric (unlike counter_attacks itself).",
    ),
    _mapping(
        "big_chances",
        "team_match",
        "UNSUPPORTED",
        "n/a",
        "Same reasoning as player-level big_chances: no big-chance signal in the real Shot schema.",
    ),
    _mapping(
        "big_chances_allowed",
        "team_match",
        "UNSUPPORTED",
        "n/a",
        "Depends on big_chances, itself UNSUPPORTED.",
    ),
    _mapping(
        "high_turnovers",
        "team_match",
        "DERIVABLE",
        "possession_losses (dispossessed+miscontrols) intersected with a high-pitch-"
        "position rule over location",
        "Both operand event types are now DIRECT (an improvement over Wyscout's blended-tag "
        "AMBIGUOUS classification), but the 'high' pitch-position threshold itself is not "
        "yet defined in this repository.",
        methodology_pending=True,
    ),
    _mapping(
        "successful_pressures",
        "team_match",
        "DERIVABLE",
        "sum of player-level successful_pressures for the team",
        "Inherits successful_pressures' pending time-window methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "transition_xg",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires both advanced.xg (provider-native, not modelled here) and counter-attack "
        "sequence linkage, itself methodology-pending.",
    ),
    _mapping(
        "deep_completions",
        "team_match",
        "DERIVABLE",
        "team passes_total, spatial rule over pass.end_location",
        "Methodology pending -- same open spatial-boundary question as elsewhere.",
        methodology_pending=True,
    ),
    _mapping(
        "offsides",
        "team_match",
        "DIRECT",
        "type.name == 'Offside', grouped by team",
        "A real, verified StatsBomb event type (not directly sampled in the Block 20C.1 "
        "3-match sample but a documented core event type in the same schema family as every "
        "other verified event above); Block 20C.2b should re-confirm presence before "
        "emitting.",
        caveats="Not directly observed in the 3-match deterministic sample; classified by "
        "schema-family consistency, not a direct full-season count in this pass.",
    ),
    _mapping(
        "fouls",
        "team_match",
        "DIRECT",
        "player-level fouls_committed events grouped by team",
        "",
    ),
    _mapping(
        "yellow_cards",
        "team_match",
        "DIRECT",
        "player-level yellow_cards (lineup cards array) grouped by team",
        "Same authoritative lineup-file source as the player-level metric.",
    ),
    _mapping(
        "red_cards",
        "team_match",
        "DERIVABLE",
        "player-level red_cards (lineup cards array) grouped by team",
        "",
    ),
    _mapping(
        "goalkeeper_saves",
        "team_match",
        "DERIVABLE",
        "sum of the team's goalkeeper(s) player_match saves",
        "",
    ),
    _mapping(
        "formation",
        "team_match",
        "DIRECT",
        "type.name == 'Starting XI', tactics.formation (+ 'Tactical Shift' events for "
        "mid-match changes)",
        "Verified real field (Block 20C.1: tactics.formation int e.g. 442 -> '4-4-2'). "
        "'Tactical Shift' events (3 observed in the 3-match sample) additionally carry the "
        "same tactics.formation/lineup shape for mid-match changes -- the pre-existing "
        "adapter only reads the opening Starting XI formation and silently ignores Tactical "
        "Shift, a REQUIRES_CHANGE finding for Block 20C.2b if a single team_match 'formation' "
        "value is meant to reflect the whole match rather than just kickoff.",
    ),
    _mapping(
        "coach_name",
        "team_match",
        "UNSUPPORTED",
        "n/a",
        "No coach/manager field was verified present on any real match, lineup, or event "
        "payload inspected in this pass.",
    ),
    _mapping(
        "formation_stability",
        "team",
        "DERIVABLE",
        "season-level comparison of Starting XI tactics.formation across a team's matches",
        "Source primitives exist (every match's real, verified Starting XI event) but no "
        "turnover/stability rule is defined -- same open methodology as Wyscout's "
        "equivalent.",
        methodology_pending=True,
    ),
    _mapping(
        "lineup_stability",
        "team",
        "DERIVABLE",
        "season-level comparison of Starting XI membership across a team's matches",
        "Source primitives exist (same verified lineup data) but no membership-stability "
        "rule is defined.",
        methodology_pending=True,
    ),
    _mapping(
        "xg",
        "team_match",
        "DERIVABLE",
        "sum of player-level advanced.xg for the team",
        "advanced.xg is DIRECT (provider-native per-shot value); the team sum is a plain "
        "aggregation, not a model of its own.",
    ),
    _mapping(
        "xga",
        "team_match",
        "DERIVABLE",
        "opponent team's xg in the same match",
        "Deterministic: exactly 2 teams per match.",
    ),
    _mapping(
        "npxg",
        "team_match",
        "DERIVABLE",
        "sum of player-level npxg for the team",
        "",
    ),
    _mapping(
        "npxga",
        "team_match",
        "DERIVABLE",
        "opponent team's npxg in the same match",
        "",
    ),
    _mapping(
        "xg_per_shot",
        "team_match",
        "DERIVABLE",
        "xg / shots_total",
        "",
    ),
    _mapping(
        "xga_per_shot",
        "team_match",
        "DERIVABLE",
        "xga / shots_allowed",
        "",
    ),
)

STATSBOMB_METRIC_MAPPINGS: tuple[StatsBombMetricMapping, ...] = (
    _MATCH_MAPPINGS
    + _PARTICIPATION_MAPPINGS
    + _OUTPUT_MAPPINGS
    + _SHOOTING_MAPPINGS
    + _CREATION_MAPPINGS
    + _PASSING_MAPPINGS
    + _DRIBBLING_MAPPINGS
    + _PROGRESSION_MAPPINGS
    + _DEFENDING_MAPPINGS
    + _GOALKEEPING_MAPPINGS
    + _TEAM_MAPPINGS
)

_OUT_OF_SCOPE_IDENTITIES: frozenset[tuple[str, str]] = frozenset(
    (metric.catalog_key, metric.catalog_granularity)
    for metric in STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS
)


def validate_mappings(mappings: tuple[StatsBombMetricMapping, ...]) -> None:
    """Enforce the same (catalog_key, granularity) invariants `metric_catalog.catalog`
    enforces on `METRIC_CATALOG_V2`: no duplicates, and every identity must be real."""

    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []
    unknown: list[tuple[str, str]] = []
    for mapping in mappings:
        identity = (mapping.catalog_key, mapping.catalog_granularity)
        if identity in seen:
            duplicates.append(identity)
        seen.add(identity)
        if identity not in _CATALOG_IDENTITIES:
            unknown.append(identity)
        if mapping.methodology_pending and mapping.classification != "DERIVABLE":
            raise AssertionError(
                f"{identity}: methodology_pending is only meaningful for DERIVABLE "
                f"entries, got classification={mapping.classification!r}"
            )
    if duplicates:
        raise AssertionError(f"duplicate (catalog_key, granularity) pairs: {duplicates}")
    if unknown:
        raise AssertionError(
            f"mappings reference identities absent from METRIC_CATALOG_V2: {unknown}"
        )


def validate_full_catalog_coverage(
    mappings: tuple[StatsBombMetricMapping, ...],
    out_of_scope: tuple[StatsBombProviderOutOfScopeMetric, ...],
) -> None:
    """Every real METRIC_CATALOG_V2 identity must be accounted for exactly once,
    either as a provider mapping entry or as a declared provider-out-of-scope
    entry -- never both, and never neither."""

    mapped_identities = {(m.catalog_key, m.catalog_granularity) for m in mappings}
    out_of_scope_identities = {(m.catalog_key, m.catalog_granularity) for m in out_of_scope}

    overlap = mapped_identities & out_of_scope_identities
    if overlap:
        raise AssertionError(
            f"identities present in both the provider mapping and the "
            f"provider-out-of-scope collection: {sorted(overlap)}"
        )

    unknown_out_of_scope = out_of_scope_identities - _CATALOG_IDENTITIES
    if unknown_out_of_scope:
        raise AssertionError(
            f"provider-out-of-scope entries reference identities absent from "
            f"METRIC_CATALOG_V2: {sorted(unknown_out_of_scope)}"
        )

    accounted_for = mapped_identities | out_of_scope_identities
    missing = _CATALOG_IDENTITIES - accounted_for
    if missing:
        raise AssertionError(
            f"METRIC_CATALOG_V2 identities not accounted for by either the provider "
            f"mapping or provider-out-of-scope collection: {sorted(missing)}"
        )


validate_mappings(STATSBOMB_METRIC_MAPPINGS)
validate_full_catalog_coverage(STATSBOMB_METRIC_MAPPINGS, STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS)


def mappings_by_classification(
    classification: MappingClassification,
) -> tuple[StatsBombMetricMapping, ...]:
    return tuple(m for m in STATSBOMB_METRIC_MAPPINGS if m.classification == classification)


def derivable_ready_mappings() -> tuple[StatsBombMetricMapping, ...]:
    """DERIVABLE entries whose deterministic rule is already fully specified."""
    return tuple(
        m
        for m in STATSBOMB_METRIC_MAPPINGS
        if m.classification == "DERIVABLE" and not m.methodology_pending
    )


def derivable_methodology_pending_mappings() -> tuple[StatsBombMetricMapping, ...]:
    """DERIVABLE entries whose source primitives exist but whose threshold/rule/
    methodology is not yet defined. Block 20C.2b must never emit these."""
    return tuple(
        m
        for m in STATSBOMB_METRIC_MAPPINGS
        if m.classification == "DERIVABLE" and m.methodology_pending
    )


def adapter_safe_mappings() -> tuple[StatsBombMetricMapping, ...]:
    """DIRECT + DERIVABLE_READY: the only identities Block 20C.2b may emit initially.
    Everything else (DERIVABLE_METHODOLOGY_PENDING, REQUIRES_MODEL, UNSUPPORTED,
    AMBIGUOUS, and every provider-out-of-scope identity) must stay non-emitting."""
    return mappings_by_classification("DIRECT") + derivable_ready_mappings()
