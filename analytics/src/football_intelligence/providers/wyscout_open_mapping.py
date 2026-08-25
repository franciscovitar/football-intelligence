"""Block 20B.2a: empirical Wyscout Open Data -> Metric Catalog V2 mapping.

DATA ONLY. This module records, for a curated set of Metric Catalog V2
identities Wyscout Open Data could plausibly support, how each maps to real,
observed ENG_PL 2017/18 source primitives -- verified against the actual
downloaded `matches_England.json` / `events_England.json` / tag mapping
(`docs/WYSCOUT_METRIC_MAPPING.md` records the underlying empirical evidence,
including exact real counts backing every classification below). Nothing
here is guessed from memory, unofficial documentation, or "what the product
wants" -- an entry is only DIRECT/DERIVABLE when the real cached source
demonstrably supports it.

This module does **not** produce `NormalizedObservation` rows and is not a
provider adapter -- that is a later sub-block. It is intentionally
data/metadata only, mirroring how `metric_catalog/catalog.py` is a plain
registry with no behavior beyond validating its own shape.

## Classification definitions

- **DIRECT** -- the source directly contains an event/state whose semantics
  match the catalog metric, read as a single native primitive (one
  eventName/subEventName-category count, or one tag's presence over its
  full natural event scope). No arithmetic beyond counting.
- **DERIVABLE** -- deterministically calculable by combining two or more
  verified source primitives (a ratio, a sum/subtraction, a subtype-tag
  intersection, or a spatial rule over the verified 0-100 `positions`
  coordinates). Where a derivation additionally needs a threshold or
  attack-direction convention this repository has not yet defined, the
  `derivation_note` says so explicitly ("methodology pending") rather than
  inventing one.
- **REQUIRES_MODEL** -- the source has relevant raw material, but the
  catalog metric itself is a model/methodology output (xG, xA, xThreat,
  pressing intensity, sequence/possession-chain reconstruction), not a
  deterministic read of source primitives.
- **UNSUPPORTED** -- the source structurally lacks the needed information
  (verified by inspecting every real field the relevant events/entries
  carry, not assumed).
- **AMBIGUOUS** -- the source has something adjacent, but its documented
  semantics are not precise enough to safely equate with the catalog
  metric without inventing meaning beyond what the tag mapping states.
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
class WyscoutMetricMapping:
    catalog_key: str
    catalog_granularity: MetricGranularity
    classification: MappingClassification
    source_primitive: str
    derivation_note: str
    caveats: str = ""
    # Only meaningful when classification == "DERIVABLE". True means source
    # primitives exist but a threshold/rule/methodology this repository has
    # not yet defined (e.g. a spatial boundary) is still required -- Block
    # 20B.2b must never emit these. False ("DERIVABLE_READY") means the
    # deterministic rule is already fully specified by verified source
    # semantics and/or existing Metric Catalog semantics. Kept as an
    # explicit field rather than inferred from free-text notes, since a
    # prior text-search heuristic missed pending metrics whose caveat (not
    # derivation_note) carried the "pending" language, and transitively
    # pending metrics built on top of them.
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
) -> WyscoutMetricMapping:
    return WyscoutMetricMapping(
        catalog_key=catalog_key,
        catalog_granularity=catalog_granularity,
        classification=classification,
        source_primitive=source_primitive,
        derivation_note=derivation_note,
        caveats=caveats,
        methodology_pending=methodology_pending,
    )


@dataclass(frozen=True, slots=True)
class WyscoutProviderOutOfScopeMetric:
    """A Metric Catalog V2 identity that is intentionally not a provider-mappable
    primitive at all -- an internal analytics-engine output, never a Wyscout field.
    Never classify these as Wyscout UNSUPPORTED: UNSUPPORTED means "we looked at
    the real source and it lacks this"; these were never a source-data question."""

    catalog_key: str
    catalog_granularity: MetricGranularity
    reason: str


WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS: tuple[WyscoutProviderOutOfScopeMetric, ...] = (
    WyscoutProviderOutOfScopeMetric(
        "league_strength",
        "competition",
        "Cross-league calibration model output (catalog's own note: 'not calibrated in "
        "V1'); not sourced from any single provider's raw data.",
    ),
    WyscoutProviderOutOfScopeMetric(
        "team_strength_elo",
        "team",
        "Computed by this repository's own team_analytics.engine Elo history from match "
        "results over time, not read from any provider field.",
    ),
    WyscoutProviderOutOfScopeMetric(
        "opponent_strength",
        "team_match",
        "Derived from team_strength_elo, itself an internal engine output rather than a "
        "provider primitive.",
    ),
    WyscoutProviderOutOfScopeMetric(
        "minutes_confidence",
        "player_season",
        "A meta-confidence signal produced by this repository's own scoring pipeline "
        "about how much real minutes data exists, not a provider field.",
    ),
)


# -- Participation / availability -------------------------------------------
_PARTICIPATION_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "started",
        "player_appearance",
        "DIRECT",
        "matches_England.json[*].teamsData[*].formation.lineup[*].playerId",
        "True if playerId in that team's lineup for the match; false if only in bench.",
    ),
    _mapping(
        "minutes",
        "player_appearance",
        "DERIVABLE",
        "formation.lineup/bench + formation.substitutions[*].{playerIn,playerOut,minute}",
        "Starter subbed off: sub-out minute. Sub who comes on: match-end minute minus "
        "sub-in minute. Unused bench: a real 0, not missing.",
        caveats=(
            "No explicit final-whistle timestamp exists per match (only discrete event "
            "timestamps and integer substitution minutes, observed range 3-95). Minutes "
            "for a player who was NOT substituted therefore require assuming a match-end "
            "point (e.g. 90 + stoppage) that Wyscout does not itself state -- an open, "
            "disclosed methodology question, never silently resolved to a fixed 90."
        ),
        methodology_pending=True,
    ),
    _mapping(
        "captain",
        "player_appearance",
        "UNSUPPORTED",
        "n/a",
        "No captain flag exists anywhere in the schema.",
        caveats=(
            "Verified: every real lineup/bench entry across all 380 matches only ever "
            "carries {playerId, ownGoals, redCards, goals, yellowCards}."
        ),
    ),
    _mapping(
        "shirt_number",
        "player_appearance",
        "UNSUPPORTED",
        "n/a",
        "No shirt/squad-number field exists on lineup/bench entries (same verified key set).",
    ),
    _mapping(
        "listed_position",
        "player_appearance",
        "UNSUPPORTED",
        "n/a",
        "No listed position/role field exists on lineup/bench entries (same verified key set).",
        caveats=(
            "players.json does carry a global `role.code2/code3/name` (e.g. 'GK'), but "
            "that is the player's general role, not a match-specific listed position."
        ),
    ),
    _mapping(
        "matches",
        "player_season",
        "DERIVABLE",
        "count of matches where playerId in lineup UNION bench",
        "Squad membership, whether or not the player actually took the field.",
    ),
    _mapping(
        "appearances",
        "player_season",
        "DERIVABLE",
        "count of matches where playerId in lineup, OR in bench with a "
        "substitutions[*].playerIn entry",
        "Matches actually played, excluding unused bench listings.",
    ),
    _mapping(
        "starts",
        "player_season",
        "DERIVABLE",
        "count of matches where playerId in lineup",
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
        "Inherits the `minutes` open methodology question above.",
        methodology_pending=True,
    ),
    _mapping(
        "positional_peer_group",
        "player_season",
        "UNSUPPORTED",
        "n/a",
        "The repository's own deterministic classifier "
        "(position_profiles.classify_position_family) requires `listed_position`, "
        "already verified UNSUPPORTED for Wyscout -- no listed position/role field "
        "exists anywhere in the match schema.",
    ),
)

# -- Match identity -----------------------------------------------------------
_MATCH_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "home_score",
        "match",
        "DIRECT",
        "teamsData[<home teamId>].score, home identified by teamsData[*].side == 'home'",
        "Native pre-aggregated field, same primitive already verified for team_match "
        "goals_for/goals_against.",
    ),
    _mapping(
        "away_score",
        "match",
        "DIRECT",
        "teamsData[<away teamId>].score, away identified by teamsData[*].side == 'away'",
        "Native pre-aggregated field, same primitive already verified for team_match "
        "goals_for/goals_against.",
    ),
    _mapping(
        "home_away",
        "team_match",
        "DIRECT",
        "teamsData[*].side",
        "Verified observed values: 'home', 'away'. Catalog granularity corrected to "
        "team_match (Block 20D.2 review-fix pass) -- the primitive is per-team-in-"
        "this-match, not a single match-wide value.",
    ),
    _mapping(
        "status",
        "match",
        "DIRECT",
        "native match `status` field",
        "Verified always 'Played' across all 380 ENG_PL 2017/18 matches -- Wyscout Open "
        "Data only ever publishes completed historical matches, the same reasoning "
        "StatsBomb Open Data's adapter already applies to its own `status` mapping.",
    ),
    _mapping(
        "kickoff_at",
        "match",
        "DIRECT",
        "native match `dateutc` field",
        "Verified clean ISO-like timestamp string (e.g. '2018-05-13 14:00:00').",
    ),
    _mapping(
        "round_name",
        "match",
        "DIRECT",
        "native match `gameweek` field",
        "Verified integer range 1-38 across the 380 matches.",
    ),
    _mapping(
        "venue_name",
        "match",
        "DIRECT",
        "native match `venue` field",
        "Verified real stadium name string (e.g. 'Turf Moor', 'Emirates Stadium'); 20 "
        "distinct venues observed, matching the 20 teams.",
    ),
)

# -- Output (goals/assists) ---------------------------------------------------
_OUTPUT_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "goals",
        "player_match",
        "DIRECT",
        "eventName in {Shot} or (eventName=Free Kick and subEventName in "
        "{Free kick shot, Penalty}), tag 101 (Goal)",
        "Count of shot-type events carrying the Goal tag, attributed to the shooter's playerId.",
        caveats=(
            "Verified: 988 such shooter-tagged goals vs. 1018 real goals from "
            "teamsData[*].score summed across all 380 matches. The 29 separately-tagged "
            "own_goal(102) events (recorded on Touch/Clearance/Head-pass events, never on "
            "a shot-type event) bring the total to 1017/1018 (99.9%) -- a small, disclosed "
            "1-goal residual gap in the raw source, never silently reconciled. own_goal(102) "
            "events must never be added to a player's own `goals`."
        ),
    ),
    _mapping(
        "assists",
        "player_match",
        "DIRECT",
        "eventName=Pass, tag 301 (assist)",
        "",
        caveats="Verified disjoint from keyPass(302) in the observed data (0 overlap).",
    ),
    _mapping(
        "non_penalty_goals",
        "player_match",
        "DERIVABLE",
        "goals excluding (Free Kick, Penalty) events tagged 101",
        "",
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
        "eventName=Free Kick, subEventName=Penalty, tag 101 (Goal)",
        "",
    ),
    _mapping(
        "penalties_attempted",
        "player_match",
        "DIRECT",
        "eventName=Free Kick, subEventName=Penalty",
        "Count regardless of outcome (80 observed for ENG_PL 2017/18).",
    ),
    _mapping(
        "penalties_missed",
        "player_match",
        "DERIVABLE",
        "penalties_attempted - penalty_goals",
        "",
    ),
)

# -- Shooting -----------------------------------------------------------------
_SHOOTING_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "shots_total",
        "player_match",
        "DIRECT",
        "eventName=Shot, or (eventName=Free Kick and subEventName in {Free kick shot, Penalty})",
        "8881 shot-type events verified for ENG_PL 2017/18 (8451 Shot + 350 free-kick + "
        "80 penalty).",
        caveats=(
            "Wyscout itself keeps free-kick/penalty shots under the 'Free Kick' eventName, "
            "distinct from 'Shot' -- this mapping unions all 3, a deliberate, documented "
            "choice, not an assumption."
        ),
    ),
    _mapping(
        "shots_on_target",
        "player_match",
        "DIRECT",
        "shots_total events tagged 1801 (accurate)",
        "",
        caveats=(
            "Verified: 'accurate' on a shot-type event means the ball reached the goal "
            "frame (i.e. on target), independent of whether it was saved or scored -- "
            "confirmed by cross-tabulating the zone tags (1201-1209 'g*' Goal-zone) "
            "against 1801/1802 across all 8881 real shots. A tiny disclosed anomaly: 20 "
            "shots (0.2%) carry a Goal-zone position tag yet are marked not_accurate."
        ),
    ),
    _mapping(
        "shots_off_target",
        "player_match",
        "DIRECT",
        "shots_total events tagged 1802 (not accurate)",
        "",
    ),
    _mapping(
        "blocked_shots",
        "player_match",
        "DIRECT",
        "shots_total events tagged 2101 (blocked)",
        "",
        caveats=(
            "This tag lives on the shooter's own shot event -- Wyscout records that a "
            "shot was blocked, but never identifies which defender blocked it."
        ),
    ),
    _mapping(
        "shots_inside_box",
        "player_match",
        "DERIVABLE",
        "shots_total events, spatial rule over positions[0]",
        "Methodology pending -- see docs/WYSCOUT_METRIC_MAPPING.md 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "headed_shots",
        "player_match",
        "DIRECT",
        "shots_total events tagged 403 (head/body)",
        "Body-part tags {401 left, 402 right, 403 head/body} cover 100% of the 8451 Shot events.",
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
        "AMBIGUOUS",
        "tag 201 (Opportunity)",
        "",
        caveats=(
            "The 'Opportunity' tag appears on 5917/8451 (70%) of Shot events -- far too "
            "broad a share of all shots to represent a distinct 'big chance' subset, and "
            "the tag mapping gives no definition beyond the bare label 'Opportunity'. "
            "Equating it with big_chances would invent semantics the source does not state."
        ),
    ),
    _mapping(
        "big_chances_missed",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Depends on big_chances, itself AMBIGUOUS.",
    ),
    _mapping(
        "shot_distance",
        "player_match",
        "DERIVABLE",
        "Euclidean distance from positions[0] to the goal, per shot",
        "Methodology pending -- see 'Spatial metrics'.",
        caveats=(
            "positions[1] (the shot's end point) is (0,0) -- a non-tracked-location "
            "sentinel, not a real coordinate -- for 55.7% of real Shot events, so only "
            "positions[0] (the shot's start point) is reliably usable."
        ),
        methodology_pending=True,
    ),
    _mapping(
        "touches_in_box",
        "player_match",
        "DERIVABLE",
        "all events for the player, spatial rule over positions[0]",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "advanced.xg",
        "player_match",
        "REQUIRES_MODEL",
        "shots_total events: positions[0], body-part tag, on/off-target tag, "
        "penalty/free-kick/open-play context, goal outcome",
        "Wyscout provides shot events and the features an xG model would need, never an "
        "xG value itself.",
        caveats=(
            "Per task instruction: never mapped directly to expected_goals/advanced.xg. "
            "Verified available shot-level features for a future model: start position "
            "(positions[0], 0-100 normalized), body part (401/402/403, 100% coverage on "
            "Shot events), on/off-target/blocked/post outcome zone (1201-1223, 2101), "
            "direct/indirect free-kick context (1101/1102), assist/key-pass context on the "
            "preceding pass, and the eventual goal outcome (tag 101)."
        ),
    ),
    _mapping(
        "npxg",
        "player_match",
        "REQUIRES_MODEL",
        "same features as advanced.xg, excluding penalty shots",
        "Requires an xG model.",
    ),
    _mapping(
        "non_penalty_goals_minus_npxg",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires npxg, itself REQUIRES_MODEL (no xG value in source).",
    ),
    _mapping(
        "xg_per_shot",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xG model.",
    ),
    _mapping(
        "xa",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xA model.",
    ),
    _mapping(
        "xg_plus_xa",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires both an xG and an xA model.",
    ),
    _mapping(
        "goals_minus_xg",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xG model.",
    ),
    _mapping(
        "assists_minus_xa",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xA model.",
    ),
)

# -- Creation -------------------------------------------------------------------
_CREATION_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "key_passes",
        "player_match",
        "DIRECT",
        "eventName=Pass, tag 302 (keyPass)",
        "1749 Pass events tagged keyPass for ENG_PL 2017/18.",
        caveats=(
            "Verified disjoint from assist(301) in the observed data (0 overlap) -- "
            "Wyscout's own keyPass tag already excludes the pass that became an assist. "
            "Whether a product-level 'key pass' should also include the assist itself is "
            "a definitional choice, not a data-availability question; this mapping uses "
            "Wyscout's own tag as-is (keyPass only)."
        ),
    ),
    _mapping(
        "chances_created",
        "player_match",
        "DERIVABLE",
        "key_passes + assists",
        "A conventional definition, not a distinct native Wyscout tag.",
    ),
    _mapping(
        "big_chances_created",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Same Opportunity-tag reasoning as big_chances.",
    ),
    _mapping(
        "passes_into_box",
        "player_match",
        "DERIVABLE",
        "eventName=Pass, spatial rule over positions[1]",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "passes_into_final_third",
        "player_match",
        "DERIVABLE",
        "eventName=Pass, spatial rule over positions[0]/positions[1]",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "through_balls",
        "player_match",
        "DIRECT",
        "eventName=Pass, tag 901 (through)",
        "Verified scoped to Smart pass/High pass subEventNames only (3109 + 2776 observed).",
    ),
    _mapping(
        "crosses",
        "player_match",
        "DIRECT",
        "eventName=Pass, subEventName=Cross",
        "12251 observed for ENG_PL 2017/18.",
    ),
    _mapping(
        "shot_creating_actions",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires linking events into possession chains preceding a shot; Wyscout events "
        "are not sequence-linked.",
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
        "Requires an xA model.",
    ),
    _mapping(
        "xa_per90",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires xa, itself REQUIRES_MODEL (no xA value in source).",
    ),
)

# -- Passing --------------------------------------------------------------------
_PASSING_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "passes_total",
        "player_match",
        "DIRECT",
        "eventName=Pass",
        "328657 Pass events verified for ENG_PL 2017/18 (all 7 Pass subEventNames).",
        caveats=(
            "Wyscout structurally separates 'Free Kick' eventName (corners, throw-ins, "
            "goal kicks, free kicks) from 'Pass' -- this mapping counts 'Pass' eventName "
            "only, never silently merging in restart deliveries the source itself keeps "
            "as a distinct category."
        ),
    ),
    _mapping(
        "passes_accurate",
        "player_match",
        "DIRECT",
        "passes_total events tagged 1801 (accurate)",
        "271280 of 328657 (82.6%) verified accurate; 1801/1802 verified mutually exclusive "
        "and always present (0 'neither', 0 'both').",
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
        "passes_total, spatial rule (Euclidean distance over positions[0]/[1])",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "passes_medium",
        "player_match",
        "DERIVABLE",
        "passes_total, spatial rule (Euclidean distance over positions[0]/[1])",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "passes_long",
        "player_match",
        "DERIVABLE",
        "passes_total, spatial rule (Euclidean distance over positions[0]/[1])",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "short_passes_accurate",
        "player_match",
        "DERIVABLE",
        "passes_short intersected with passes_accurate",
        "Inherits passes_short's pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "medium_passes_accurate",
        "player_match",
        "DERIVABLE",
        "passes_medium intersected with passes_accurate",
        "Inherits passes_medium's pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "long_passes_accurate",
        "player_match",
        "DERIVABLE",
        "fi-wyscout-spatial-v1.1 long-pass classification intersected with tag 1801",
        "Promoted after the real ENG_PL 2017/18 spatial audit: Launch; High pass >25 m; "
        "Simple/Smart pass >45 m; Cross/Hand/Head explicitly non-long; unknown or "
        "geometry-dependent unclassifiable events remain missing.",
        caveats=(
            "Promotion is deliberately metric- and scope-specific: only ENG_PL 2017/18 "
            "is currently audited for emission. Other Wyscout core-league scopes remain "
            "suppressed until their own audit passes. progressive_passes and "
            "passes_into_final_third remain methodology/audit blocked and are not emitted."
        ),
    ),
    _mapping(
        "progressive_passes",
        "player_match",
        "DERIVABLE",
        "passes_total, spatial rule over positions[0]/[1]",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "progressive_pass_distance",
        "player_match",
        "DERIVABLE",
        "passes_total, spatial distance rule",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "switches",
        "player_match",
        "DERIVABLE",
        "passes_total, spatial rule (lateral distance over positions[0]/[1])",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "passes_under_pressure",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Wyscout has no 'under pressure' tag; would require proximity/time modeling "
        "against opponent positions, which are not recorded per-event.",
    ),
    _mapping(
        "passes_received",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Pass events record only the passer's playerId, never a recipient. Identifying "
        "the receiver requires inferring linkage to a later event by a teammate near the "
        "pass's end coordinates -- a reconstruction methodology, not a verified primitive.",
    ),
    _mapping(
        "progressive_passes_received",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Same receiver-identification gap as passes_received.",
    ),
)

# -- Dribbling / possession security --------------------------------------------
_DRIBBLING_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "dribbles_attempted",
        "player_match",
        "AMBIGUOUS",
        "tags 503/504 (take_on_l/take_on_r)",
        "",
        caveats=(
            "take_on_l/take_on_r are scoped to Duel sub-events (Ground attacking/"
            "defending duel), shared by both participants, not a distinct dribble-attempt "
            "event -- using them would conflate a dribble count with the duels_total/"
            "ground_duels count already covered separately."
        ),
    ),
    _mapping(
        "dribbles_successful",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Same reasoning as dribbles_attempted.",
    ),
    _mapping(
        "dribble_success_pct",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Depends on dribbles_attempted/successful, both AMBIGUOUS.",
    ),
    _mapping(
        "take_ons_attempted",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Same reasoning as dribbles_attempted.",
    ),
    _mapping(
        "take_ons_successful",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Same reasoning as dribbles_attempted.",
    ),
    _mapping(
        "take_on_success_pct",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Depends on take_ons_attempted/successful, both AMBIGUOUS.",
    ),
    _mapping(
        "players_beaten",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "No tag or event marks 'this action beat an opponent'.",
    ),
    _mapping(
        "dispossessed",
        "player_match",
        "AMBIGUOUS",
        "tag 2001 (dangerous_ball_lost)",
        "",
        caveats=(
            "dangerous_ball_lost marks losing the ball in a dangerous area from any "
            "cause -- it does not distinguish 'dispossessed by an opponent' from "
            "'miscontrolled', so it cannot be safely split into these two distinct "
            "catalog metrics."
        ),
    ),
    _mapping(
        "miscontrols",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Same blended-tag reasoning as dispossessed.",
    ),
    _mapping(
        "possession_losses",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Catalog defines this as dispossessed + miscontrols, both themselves AMBIGUOUS.",
    ),
    _mapping(
        "turnovers",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "dangerous_ball_lost only flags losses in dangerous areas, a narrower concept "
        "than all turnovers -- using it would systematically undercount.",
    ),
    _mapping(
        "receiving_errors",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "No tag or event marks a receiving/control error distinct from dangerous_ball_lost.",
    ),
)

# -- Ball progression / carrying --------------------------------------------------
_PROGRESSION_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "carries",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Wyscout has no dedicated carry/dribble-progression event (unlike e.g. StatsBomb's "
        "explicit Carry type).",
        caveats=(
            "'Acceleration' (Others on the ball, 4892 observed) marks a player speeding "
            "up on the ball, not a general carry; reconstructing carries from consecutive "
            "same-player touch positions is conceivable but was not verified in this pass "
            "and would itself be a reconstruction methodology, not a direct primitive."
        ),
    ),
    _mapping(
        "progressive_carries",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Depends on carries, itself UNSUPPORTED.",
    ),
    _mapping(
        "carries_into_final_third",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Depends on carries, itself UNSUPPORTED.",
    ),
    _mapping(
        "carries_into_box",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Depends on carries, itself UNSUPPORTED.",
    ),
    _mapping(
        "carry_distance",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Depends on carries, itself UNSUPPORTED.",
    ),
    _mapping(
        "progressive_carry_distance",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Depends on carries, itself UNSUPPORTED.",
    ),
    _mapping(
        "touches",
        "player_match",
        "DIRECT",
        "count of every event carrying a playerId for that player",
        "Every event is itself one on-ball action; a raw touch count is a straightforward "
        "event-stream count.",
        caveats="Not equivalent to a dedicated 'Touch' subEventName, which is narrower.",
    ),
    _mapping(
        "touches_final_third",
        "player_match",
        "DERIVABLE",
        "touches, spatial rule over positions[0]",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "touches_box",
        "player_match",
        "DERIVABLE",
        "touches, spatial rule over positions[0]",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "progressive_actions",
        "player_match",
        "DERIVABLE",
        "progressive_passes + progressive_carries",
        "Inherits progressive_passes' pending methodology and progressive_carries' "
        "UNSUPPORTED status.",
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
_DEFENDING_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "tackles",
        "player_match",
        "AMBIGUOUS",
        "eventName=Duel, subEventName in {Ground attacking duel, Ground defending duel, "
        "Ground loose ball duel}; tag 1601 (sliding_tackle)",
        "",
        caveats=(
            "Wyscout has no distinct 'tackle' event. sliding_tackle(1601) only marks one "
            "specific technique within ground duels (verified: 2495 + 1594 + 21 across the "
            "3 ground-duel subtypes), and a defending duel is a broader shoulder-to-"
            "shoulder-or-otherwise challenge concept, not equivalent to a tackle."
        ),
    ),
    _mapping(
        "tackles_won",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Depends on tackles, itself AMBIGUOUS.",
    ),
    _mapping(
        "tackle_success_pct",
        "player_match",
        "AMBIGUOUS",
        "n/a",
        "Depends on tackles, itself AMBIGUOUS.",
    ),
    _mapping(
        "blocks",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "The blocked(2101) tag lives on the shooter's own shot event and never identifies "
        "the blocking defender's playerId.",
    ),
    _mapping(
        "shot_blocks",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Same reasoning as blocks.",
    ),
    _mapping(
        "pass_blocks",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "No blocked-pass tag or blocking-player attribution exists.",
    ),
    _mapping(
        "interceptions",
        "player_match",
        "DIRECT",
        "tag 1401 (interception), any eventName",
        "Verified: the interception tag spans essentially every eventName (Pass, Others "
        "on the ball, Duel, Shot), not one canonical event category.",
    ),
    _mapping(
        "clearances",
        "player_match",
        "DIRECT",
        "eventName=Others on the ball, subEventName=Clearance",
        "11784 observed for ENG_PL 2017/18.",
        caveats=(
            "The dedicated clearance(1501) TAG is defined in the tag mapping but was "
            "never once observed on any real event -- the actual signal is the distinct "
            "subEventName, not the vestigial tag."
        ),
    ),
    _mapping(
        "recoveries",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "No tag or event marks winning back a loose/contested ball as a 'recovery'.",
    ),
    _mapping(
        "pressures",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "No pressing/pressure event exists; would require proximity/time modeling against "
        "an opponent in possession, not a native primitive.",
    ),
    _mapping(
        "successful_pressures",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Pressure semantics are not directly supplied -- same reasoning as pressures.",
    ),
    _mapping(
        "pressure_success_pct",
        "player_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires pressures and successful_pressures, both REQUIRES_MODEL.",
    ),
    _mapping(
        "errors_leading_to_shot",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "No error attribution or shot-chain linkage exists.",
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
        "eventName=Duel",
        "176688 observed for ENG_PL 2017/18.",
    ),
    _mapping(
        "duels_won",
        "player_match",
        "DIRECT",
        "Duel events tagged 703 (won)",
        "Outcome tags {701 lost, 702 neutral, 703 won} verified to cover 176527/176688 "
        "(99.9%); 161 duels (0.09%) carry no outcome tag and are left unclassified, "
        "never assumed won or lost.",
    ),
    _mapping(
        "duel_win_pct",
        "player_match",
        "DERIVABLE",
        "duels_won / duels_total",
        "",
    ),
    _mapping(
        "aerial_duels",
        "player_match",
        "DIRECT",
        "eventName=Duel, subEventName=Air duel",
        "37760 observed for ENG_PL 2017/18.",
    ),
    _mapping(
        "aerial_duels_won",
        "player_match",
        "DERIVABLE",
        "aerial_duels tagged 703 (won)",
        "",
    ),
    _mapping(
        "aerial_duel_win_pct",
        "player_match",
        "DERIVABLE",
        "aerial_duels_won / aerial_duels",
        "",
    ),
    _mapping(
        "ground_duels",
        "player_match",
        "DIRECT",
        "eventName=Duel, subEventName in {Ground attacking duel, Ground defending duel, "
        "Ground loose ball duel}",
        "138928 observed for ENG_PL 2017/18 (53859 + 53737 + 31332).",
    ),
    _mapping(
        "ground_duels_won",
        "player_match",
        "DERIVABLE",
        "ground_duels tagged 703 (won)",
        "",
    ),
    _mapping(
        "fouls_committed",
        "player_match",
        "DIRECT",
        "eventName=Foul",
        "8138 observed for ENG_PL 2017/18, attributed to the fouling player's playerId.",
    ),
    _mapping(
        "fouls_drawn",
        "player_match",
        "UNSUPPORTED",
        "n/a",
        "Foul events record only the committing player's playerId -- there is no field "
        "identifying which player was fouled.",
    ),
    _mapping(
        "yellow_cards",
        "player_match",
        "DIRECT",
        "Foul events tagged 1702 (yellow_card)",
        "1180 verified for ENG_PL 2017/18.",
        caveats=(
            "Uses the event-tag derivation, not the roster-summary "
            "teamsData[*].formation.{lineup,bench}[*].yellowCards field -- that field's "
            "values (e.g. '91', '88', '56') look like match minutes rather than counts and "
            "were not resolved to a confident semantic in this pass; flagged as an open "
            "question in docs/WYSCOUT_METRIC_MAPPING.md, never used as a primitive here."
        ),
    ),
    _mapping(
        "red_cards",
        "player_match",
        "DERIVABLE",
        "Foul events tagged 1701 (red_card) union 1703 (second_yellow_card)",
        "A definitional choice (a second yellow is a real dismissal); 22 straight reds + "
        "19 second yellows verified for ENG_PL 2017/18.",
    ),
    _mapping(
        "second_yellow_cards",
        "player_match",
        "DIRECT",
        "Foul events tagged 1703 (second_yellow_card)",
        "19 verified for ENG_PL 2017/18.",
    ),
    _mapping(
        "saves",
        "player_match",
        "DIRECT",
        "eventName=Save attempt, tag 1801 (accurate)",
        "2330 of 3349 Save attempt events (Save attempt + Reflexes subtypes) verified "
        "accurate; the remaining 1019 are tagged not_accurate + Goal (a goal was conceded).",
    ),
)

# -- Goalkeeping (goalkeeper_match/season) ------------------------------------------
_GOALKEEPING_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "saves",
        "goalkeeper_match",
        "DIRECT",
        "same as player_match saves, scoped to players.json role.code2 == 'GK'",
        "",
        caveats=(
            "Wyscout match payloads never state a player's on-pitch role; the goalkeeper "
            "identity used to scope this metric comes from players.json's global "
            "`role.code2` field, not a match-specific signal."
        ),
    ),
    _mapping(
        "shots_on_target_faced",
        "goalkeeper_match",
        "DERIVABLE",
        "opponent shots_total events tagged accurate, cross-referenced to which keeper "
        "was on the pitch",
        "Requires combining shot events, the goalkeeper's lineup/substitution window, and "
        "the opposing team's teamId for the match.",
    ),
    _mapping(
        "save_pct",
        "goalkeeper_match",
        "DERIVABLE",
        "saves / shots_on_target_faced",
        "Inherits shots_on_target_faced's cross-referencing requirement.",
    ),
    _mapping(
        "goals_conceded",
        "goalkeeper_match",
        "DERIVABLE",
        "team goals-against for the match, attributed to whichever keeper was on the "
        "pitch when each goal was scored",
        "",
        caveats=(
            "'Save attempt' events tagged not_accurate+Goal only capture goals where the "
            "keeper attempted a save (1019 verified); goals scored with no save attempt at "
            "all (e.g. an open net) require using the match scoreline plus lineup/"
            "substitution timing instead -- deterministic in principle, non-trivial to "
            "implement."
        ),
    ),
    _mapping(
        "clean_sheets",
        "goalkeeper_match",
        "DERIVABLE",
        "goals_conceded == 0 for the match",
        "Inherits goals_conceded's cross-referencing requirement.",
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
        "Catalog's own note: requires shot-quality (xG) data on shots faced.",
    ),
    _mapping(
        "claims",
        "goalkeeper_match",
        "AMBIGUOUS",
        "eventName=Goalkeeper leaving line",
        "",
        caveats=(
            "1266 such events exist, but the tag vocabulary gives no way to distinguish a "
            "successful claim of a cross from an unrelated/failed sweeper action."
        ),
    ),
    _mapping(
        "distribution_accuracy_pct",
        "goalkeeper_match",
        "DERIVABLE",
        "goalkeeper's passes_accurate / passes_total",
        "Same players.json role-based goalkeeper scoping as saves.",
    ),
    _mapping(
        "passes",
        "goalkeeper_match",
        "DERIVABLE",
        "goalkeeper's passes_total",
        "Same players.json role-based goalkeeper scoping as saves.",
    ),
    _mapping(
        "long_passes",
        "goalkeeper_match",
        "DERIVABLE",
        "goalkeeper's passes_long",
        "Inherits passes_long's pending spatial methodology.",
        methodology_pending=True,
    ),
    _mapping(
        "launches",
        "goalkeeper_match",
        "DIRECT",
        "goalkeeper's eventName=Pass, subEventName=Launch",
        "10247 Launch events observed for ENG_PL 2017/18 (across all players); scoping to "
        "goalkeepers only needs the same players.json role cross-reference as saves.",
    ),
    _mapping(
        "average_distance_from_goal",
        "goalkeeper_match",
        "UNSUPPORTED",
        "n/a",
        "No systematic goalkeeper position-tracking exists beyond discrete 'Goalkeeper "
        "leaving line' events.",
    ),
    _mapping(
        "crosses_stopped",
        "goalkeeper_match",
        "UNSUPPORTED",
        "n/a",
        "No tag distinguishes a stopped cross from any other goalkeeper action.",
    ),
    _mapping(
        "sweeper_actions",
        "goalkeeper_match",
        "UNSUPPORTED",
        "n/a",
        "No distinct sweeper-action tag or event exists.",
    ),
    _mapping(
        "xg_on_target_faced",
        "goalkeeper_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xG model applied to shots faced.",
    ),
    _mapping(
        "psxg",
        "goalkeeper_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires a post-shot xG model.",
    ),
)

# -- Team / team_match -----------------------------------------------------------
_TEAM_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
    _mapping(
        "goals_for",
        "team_match",
        "DIRECT",
        "matches_England.json[*].teamsData[<teamId>].score",
        "Native pre-aggregated field; cross-validated against summed shot/save goal tags.",
    ),
    _mapping(
        "goals_against",
        "team_match",
        "DIRECT",
        "the opponent team's teamsData[*].score in the same match",
        "Deterministic: exactly 2 teams per match.",
    ),
    _mapping(
        "shots_total",
        "team_match",
        "DERIVABLE",
        "player-level shots_total events grouped by teamId",
        "",
    ),
    _mapping(
        "shots_on_target",
        "team_match",
        "DERIVABLE",
        "player-level shots_on_target events grouped by teamId",
        "",
    ),
    _mapping(
        "shots_inside_box",
        "team_match",
        "DERIVABLE",
        "team shots_total, spatial rule over positions[0]",
        "Methodology pending -- see 'Spatial metrics'.",
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
        "player-level blocked_shots events grouped by teamId",
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
        "player-level passes_total events grouped by teamId",
        "",
    ),
    _mapping(
        "passes_accurate",
        "team_match",
        "DIRECT",
        "player-level passes_accurate events grouped by teamId",
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
        "share of Pass-eventName events (or on-ball event time) per team",
        "Methodology pending: Wyscout has no explicit possession-duration state; a "
        "proxy is computable but does not match a time-based possession% without an "
        "explicit, agreed convention -- not invented here.",
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
        "team passes_total, spatial rule over positions[0]/[1]",
        "Methodology pending -- see 'Spatial metrics'.",
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
        "team passes_total, spatial rule over positions[1]",
        "Methodology pending -- see 'Spatial metrics'.",
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
        "eventName=Free Kick, subEventName=Corner, grouped by teamId",
        "3910 observed for ENG_PL 2017/18.",
    ),
    _mapping(
        "set_piece_shots",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires linking a shot back to a preceding corner/free-kick within the same "
        "possession sequence; Wyscout events are not sequence-linked.",
    ),
    _mapping(
        "set_piece_xg",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires both an xG model and the set_piece_shots sequence-linkage above.",
    ),
    _mapping(
        "recoveries",
        "team_match",
        "UNSUPPORTED",
        "n/a",
        "Same reasoning as player_match recoveries: no recovery tag or event exists.",
    ),
    _mapping(
        "pressures",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Same reasoning as player_match pressures.",
    ),
    _mapping(
        "ppda",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires a defined defensive-third boundary (pending spatial methodology) plus "
        "an opponent-passes-allowed model; not a deterministic read of primitives.",
    ),
    _mapping(
        "counter_attacks",
        "team_match",
        "DERIVABLE",
        "grouping consecutive tag 1901 (counter_attack) events into distinct sequences, per team",
        "Methodology pending: the tag marks individual events, not discrete attacking "
        "sequences; a sequence-grouping rule is needed to count 'a counter-attack' rather "
        "than 'an event that happened during one'.",
        methodology_pending=True,
    ),
    _mapping(
        "counter_attack_shots",
        "team_match",
        "DERIVABLE",
        "team shots_total events tagged 1901 (counter_attack)",
        "425 Shot-eventName events tagged counter_attack observed for ENG_PL 2017/18.",
    ),
    _mapping(
        "big_chances",
        "team_match",
        "AMBIGUOUS",
        "n/a",
        "Same Opportunity-tag reasoning as player-level big_chances.",
    ),
    _mapping(
        "big_chances_allowed",
        "team_match",
        "AMBIGUOUS",
        "n/a",
        "Depends on big_chances, itself AMBIGUOUS.",
    ),
    _mapping(
        "high_turnovers",
        "team_match",
        "AMBIGUOUS",
        "tag 2001 (dangerous_ball_lost) intersected with a high-pitch-position rule",
        "",
        caveats=(
            "Inherits the dangerous_ball_lost blended-cause ambiguity from player-level "
            "turnovers, compounded by a not-yet-defined 'high' pitch-position threshold."
        ),
    ),
    _mapping(
        "successful_pressures",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Same reasoning as player_match pressures.",
    ),
    _mapping(
        "transition_xg",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires both an xG model and counter-attack sequence linkage.",
    ),
    _mapping(
        "deep_completions",
        "team_match",
        "DERIVABLE",
        "team passes_total, spatial rule over positions[1]",
        "Methodology pending -- see 'Spatial metrics'.",
        methodology_pending=True,
    ),
    _mapping(
        "offsides",
        "team_match",
        "DIRECT",
        "eventName=Offside, grouped by teamId",
        "1558 observed for ENG_PL 2017/18.",
    ),
    _mapping(
        "fouls",
        "team_match",
        "DIRECT",
        "player-level fouls_committed events grouped by teamId",
        "",
    ),
    _mapping(
        "yellow_cards",
        "team_match",
        "DIRECT",
        "player-level yellow_cards events grouped by teamId",
        "",
    ),
    _mapping(
        "red_cards",
        "team_match",
        "DERIVABLE",
        "player-level red_cards events grouped by teamId",
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
        "UNSUPPORTED",
        "n/a",
        "No formation-shape label (e.g. '4-4-2') exists anywhere in the match schema -- "
        "verified: teamsData[*].formation only ever contains {lineup, bench, "
        "substitutions}, never a shape string.",
    ),
    _mapping(
        "coach_name",
        "team_match",
        "UNSUPPORTED",
        "n/a",
        "teamsData[*].coachId is present (a numeric id), but no coach-name lookup file "
        "was part of this block's acquisition scope.",
    ),
    _mapping(
        "formation_stability",
        "team",
        "DERIVABLE",
        "season-level comparison of teamsData[*].formation.lineup across a team's matches",
        "Source primitives exist (every match's real, verified lineup) but no "
        "turnover/stability rule is defined -- catalog's own note: 'not wired into "
        "scoring yet; declared for future starting-XI turnover analysis'.",
        methodology_pending=True,
    ),
    _mapping(
        "lineup_stability",
        "team",
        "DERIVABLE",
        "season-level comparison of teamsData[*].formation.lineup membership across a "
        "team's matches",
        "Source primitives exist (same verified lineup data) but no membership-"
        "stability rule is defined -- catalog's own note: 'declared for future "
        "tactical-identity analysis'.",
        methodology_pending=True,
    ),
    _mapping(
        "xg",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xG model.",
    ),
    _mapping(
        "xga",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xG model.",
    ),
    _mapping(
        "npxg",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xG model.",
    ),
    _mapping(
        "npxga",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xG model.",
    ),
    _mapping(
        "xg_per_shot",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xG model.",
    ),
    _mapping(
        "xga_per_shot",
        "team_match",
        "REQUIRES_MODEL",
        "n/a",
        "Requires an xG model.",
    ),
)

WYSCOUT_METRIC_MAPPINGS: tuple[WyscoutMetricMapping, ...] = (
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
    for metric in WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS
)


def validate_mappings(mappings: tuple[WyscoutMetricMapping, ...]) -> None:
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
    mappings: tuple[WyscoutMetricMapping, ...],
    out_of_scope: tuple[WyscoutProviderOutOfScopeMetric, ...],
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


validate_mappings(WYSCOUT_METRIC_MAPPINGS)
validate_full_catalog_coverage(WYSCOUT_METRIC_MAPPINGS, WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS)


def mappings_by_classification(
    classification: MappingClassification,
) -> tuple[WyscoutMetricMapping, ...]:
    return tuple(m for m in WYSCOUT_METRIC_MAPPINGS if m.classification == classification)


def derivable_ready_mappings() -> tuple[WyscoutMetricMapping, ...]:
    """DERIVABLE entries whose deterministic rule is already fully specified."""
    return tuple(
        m
        for m in WYSCOUT_METRIC_MAPPINGS
        if m.classification == "DERIVABLE" and not m.methodology_pending
    )


def derivable_methodology_pending_mappings() -> tuple[WyscoutMetricMapping, ...]:
    """DERIVABLE entries whose source primitives exist but whose threshold/rule/
    methodology is not yet defined. Block 20B.2b must never emit these."""
    return tuple(
        m
        for m in WYSCOUT_METRIC_MAPPINGS
        if m.classification == "DERIVABLE" and m.methodology_pending
    )


def adapter_safe_mappings() -> tuple[WyscoutMetricMapping, ...]:
    """DIRECT + DERIVABLE_READY: the only identities Block 20B.2b may emit initially.
    Everything else (DERIVABLE_METHODOLOGY_PENDING, REQUIRES_MODEL, UNSUPPORTED,
    AMBIGUOUS, and every provider-out-of-scope identity) must stay non-emitting."""
    return mappings_by_classification("DIRECT") + derivable_ready_mappings()
