"""StatsBomb Open Data payload -> NormalizedObservation adapter (Block 20C.2b).

Historical/deep role only, **internal-only evidence** (see
`providers.statsbomb_open_policy` -- StatsBomb's User Agreement's
commercial-use implications for derived analysis remain unresolved; nothing
here promotes this data to any user-facing surface). This adapter emits
observations **only** for the 110-identity adapter-safe subset
(`adapter_safe_mappings()` in `providers.statsbomb_open_mapping`: the 65
DIRECT + 45 DERIVABLE_READY Metric Catalog V2 identities Block 20C.2a
verified against the real, pinned, cached Premier League 2015/16 source).
DERIVABLE_METHODOLOGY_PENDING, REQUIRES_MODEL, UNSUPPORTED, AMBIGUOUS, and
provider-out-of-scope identities are never emitted -- see
`_EMITTED_IDENTITIES`, validated against the mapping at import time.

This module consumes already-loaded payloads (`MatchBundle`) -- it performs
no HTTP requests and no filesystem/disk reads of its own. Acquisition and
local caching are the provider layer's job
(`providers.statsbomb_open.StatsBombOpenDataClient`,
`providers.statsbomb_open_cache`); this module only transforms.

## What changed from the pre-Block-20 (Block 14) adapter

Block 20C.1 audited the previous adapter against the real, pinned, full
Premier League 2015/16 season and found several of its assumptions
incorrect or incomplete (`docs/STATSBOMB_METRIC_MAPPING.md` has the full
evidence trail). This rewrite fixes all of them:

- **Participation universe**: the lineup file (`lineups/{match_id}.json`)
  is authoritative, never event-tag presence. A player is a confirmed
  participant only if their lineup entry has at least one `positions`
  interval (starter: first interval's `start_reason == "Starting XI"`;
  used substitute: any other start_reason). Unused substitutes (no
  `positions` entries at all) never receive a performance-stat
  observation -- only the roster-membership facts the certified mapping
  supports (`started`, `shirt_number`).
- **Cards**: sourced exclusively from the lineup file's per-player `cards`
  array, never from `Foul Committed` events alone -- the old adapter missed
  every `Bad Behaviour`-sourced card (15% of real cards, verified).
- **Saves / goals_conceded**: use the full certified Goal Keeper type set
  (`Shot Saved`, `Shot Saved Off Target`, `Shot Saved to Post`,
  `Penalty Saved`, `Penalty Saved to Post` for saves; `Goal Conceded`,
  `Penalty Conceded` for goals_conceded) -- the old adapter's
  `type.name == "Shot Saved"`-only rule undercounted saves by ~3.6%.
- **Assists**: `pass.goal_assist == True`, a direct native field -- the old
  adapter's docstring incorrectly claimed this would require cross-event
  reconstruction.
- **Match status**: the native `match_status` field is read and emitted
  as-is; the old adapter emitted a synthetic `"finished"` constant.
- **Goalkeeper identity**: determined from the lineup file's own
  `positions[*].position == "Goalkeeper"`, never from event occurrence,
  jersey number, or a name/role guess.
- **Own goals**: `Own Goal For`/`Own Goal Against` events are never
  processed into any player's `goals` count (only `Shot`-type events with
  `outcome.name == "Goal"` are). Team `goals_for`/`goals_against` always
  come from the native match score, which already correctly includes own
  goals -- never reconstructed from summed player events.
- **No legacy non-catalog emissions**: team/competition `name` facts now
  live only in `entity_identity_hints`, never as a `NormalizedObservation`
  metric (the old adapter emitted `name` as a metric, which has no
  corresponding certified Metric Catalog identity).

`minutes`/`minutes_per_appearance` remain `DERIVABLE_METHODOLOGY_PENDING`
(lineup position-interval boundaries do not cleanly reduce to a single
deterministic rule -- verified, not assumed) and are never implemented
here, exactly as certified.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from football_intelligence.data_mesh.adapters.scope import AdapterScope, ScopeMismatchError
from football_intelligence.data_mesh.models import EntityType, NormalizedObservation, SourceType
from football_intelligence.metric_catalog.types import MetricGranularity
from football_intelligence.providers.statsbomb_open import DEFAULT_PINNED_REVISION
from football_intelligence.providers.statsbomb_open_mapping import adapter_safe_mappings
from football_intelligence.providers.statsbomb_open_policy import STATSBOMB_INTERNAL_ONLY

SOURCE_CODE = "statsbomb-open"
SOURCE_TYPE: SourceType = "objective_structured"
# Bumped from "statsbomb-open-v0.2" (Block 20C.2b's certified rewrite) in
# Block 20D.2's review-fix pass: observable emission semantics changed
# materially -- every observation now carries an explicit
# `metric_granularity`, `goalkeeper_match`-granularity `saves` is now
# genuinely emitted (previously declared but never produced), `home_away`
# moved from catalog granularity "match" to "team_match", and identity
# hints were materially enriched (explicit `team_external_id`/`team_name`,
# `player_external_id`/`player_name`, `home_team_*`/`away_team_*`,
# `kickoff_date`). Old and new observations must not share a provenance
# version.
SEMANTIC_VERSION = "statsbomb-open-v0.3"
COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2015/16"

# Block 20D.3: the certified adapter's original (and still default) scope,
# unchanged in value from the module constants above -- every existing
# caller that does not pass `scope=` gets byte-for-byte the same ENG_PL
# 2015/16 behavior as before generalization. `provider_competition_id`/
# `provider_season_id` are real, verified against every match record's own
# `competition.competition_id`/`season.season_id` fields (Block 20D.2).
DEFAULT_SCOPE = AdapterScope(
    canonical_competition_code=COMPETITION_CODE,
    season_label=SEASON_LABEL,
    provider_competition_id=2,
    provider_season_id=27,
)

# Prepared for Block 20D.3's rich overlap enablement: real, verified
# provider-native ids for Spain/La Liga 2017/18 (`competition_id=11`,
# `season_id=1`), discovered live during Block 20D.1's investigation. This
# is the real "Barcelona 2017/18" open-data scope (36 of Barcelona's 38
# league matches), never the whole real La Liga season -- see
# `docs/ENTITY_RESOLUTION_V2.md`.
ESP_LL_SCOPE = AdapterScope(
    canonical_competition_code="ESP_LL",
    season_label="2017/18",
    provider_competition_id=11,
    provider_season_id=1,
)

_STARTING_XI_REASON = "Starting XI"
_GOALKEEPER_POSITION_NAME = "Goalkeeper"

_YELLOW_CARD_TYPE = "Yellow Card"
_SECOND_YELLOW_TYPE = "Second Yellow"
_RED_CARD_TYPES = frozenset({"Red Card", _SECOND_YELLOW_TYPE})

_ON_TARGET_SHOT_OUTCOMES = frozenset({"Goal", "Saved", "Saved Off Target", "Saved to Post"})
_OFF_TARGET_SHOT_OUTCOMES = frozenset({"Off T", "Wayward"})
_GOAL_OUTCOME = "Goal"
_BLOCKED_OUTCOME = "Blocked"
_PENALTY_SHOT_TYPE = "Penalty"
_HEAD_BODY_PART = "Head"
_DRIBBLE_COMPLETE_OUTCOME = "Complete"
_TACKLE_DUEL_TYPE = "Tackle"
_AERIAL_LOST_DUEL_TYPE = "Aerial Lost"
_CORNER_PASS_TYPE = "Corner"
_COUNTER_ATTACK_PLAY_PATTERN = "From Counter"

# The certified full save-event type set (Block 20C.2a) -- the old
# adapter's `_SAVE_GOALKEEPER_TYPE = "Shot Saved"`-only rule undercounted
# real saves by ~3.6%.
_SAVE_GOALKEEPER_TYPES = frozenset(
    {
        "Shot Saved",
        "Shot Saved Off Target",
        "Shot Saved to Post",
        "Penalty Saved",
        "Penalty Saved to Post",
    }
)
_CONCEDED_GOALKEEPER_TYPES = frozenset({"Goal Conceded", "Penalty Conceded"})
_KEEPER_SWEEPER_TYPE = "Keeper Sweeper"
_CLAIM_OUTCOME = "Claim"
_PUNCH_TYPE = "Punch"

# Every raw per-player-per-match count this adapter force-zero-fills for a
# confirmed participant (starter or used substitute -- never an unused
# bench player or an event-only phantom). `advanced.xg`/`npxg`/
# `carry_distance` are float accumulators, tracked in the same dict for
# convenience but never zero-filled as if they were plain integer counts
# with no qualifying event (a player who took no shot still legitimately
# gets advanced.xg = 0.0, since "no shot" is a real fact about a confirmed
# participant, not a missing observation).
_PLAYER_MATCH_COUNT_METRICS: tuple[str, ...] = (
    "touches",
    "passes_total",
    "passes_accurate",
    "passes_received",
    "assists",
    "key_passes",
    "through_balls",
    "crosses",
    "switches",
    "passes_under_pressure",
    "shots_total",
    "shots_on_target",
    "shots_off_target",
    "blocked_shots",
    "headed_shots",
    "goals",
    "penalty_goals",
    "penalties_attempted",
    "advanced.xg",
    "npxg",
    "duels_total",
    "aerial_duels",
    "tackles",
    "interceptions",
    "clearances",
    "blocks",
    "dribbles_attempted",
    "dribbles_successful",
    "fouls_committed",
    "fouls_drawn",
    "dispossessed",
    "miscontrols",
    "recoveries",
    "pressures",
    "carries",
    "carry_distance",
    "saves",
    "goals_conceded",
    "claims",
    "crosses_stopped",
    "sweeper_actions",
)

# `goals_conceded`/`claims`/`crosses_stopped`/`sweeper_actions` are
# goalkeeper_match-EXCLUSIVE identities -- unlike `saves` (a real identity
# at both player_match and goalkeeper_match granularity, so every
# participant legitimately gets a real `saves=0` if they made none), these
# four have no player_match counterpart in the certified mapping at all.
# They are accumulated for every participant (harmless, since the raw
# event counts are computed uniformly) but must only ever be *emitted* for
# a confirmed goalkeeper -- `_emit_player_match_metrics`'s generic
# zero-fill loop excludes them; only `parse_goalkeeper_observations`,
# scoped to `roster.goalkeepers`, emits them.
_GOALKEEPER_ONLY_COUNT_METRICS = frozenset(
    {"goals_conceded", "claims", "crosses_stopped", "sweeper_actions"}
)
_PLAYER_MATCH_EMITTED_COUNT_METRICS = tuple(
    name for name in _PLAYER_MATCH_COUNT_METRICS if name not in _GOALKEEPER_ONLY_COUNT_METRICS
)

_GRANULARITY_TO_ENTITY_TYPE: dict[str, EntityType] = {
    "match": "match",
    "player_appearance": "player",
    "player_match": "player",
    "player_season": "player",
    "goalkeeper_match": "player",
    "goalkeeper_season": "player",
    "team_match": "team",
}

_ADAPTER_SAFE_IDENTITIES: frozenset[tuple[str, str]] = frozenset(
    (m.catalog_key, m.catalog_granularity) for m in adapter_safe_mappings()
)

# `home_away`'s catalog granularity was corrected from "match" to
# "team_match" (Block 20D.2 review-fix pass, mirroring `wyscout_open`'s
# identical fix): the primitive (home_team/away_team identity) is
# inherently a per-team-in-this-match fact, and "team_match" already
# projects to entity_type="team" mechanically below -- no special-case
# override needed any more (an earlier pass carried one here specifically
# because the catalog was misclassified).
_SAFE_METRIC_ENTITY_PAIRS: frozenset[tuple[str, EntityType]] = frozenset(
    (key, _GRANULARITY_TO_ENTITY_TYPE[granularity]) for key, granularity in _ADAPTER_SAFE_IDENTITIES
)


def _validate_emission_scope(declared: frozenset[tuple[str, str]]) -> None:
    unsafe = declared - _ADAPTER_SAFE_IDENTITIES
    if unsafe:
        raise AssertionError(
            f"statsbomb_open adapter declares emission of non-adapter-safe identities: "
            f"{sorted(unsafe)}"
        )


# Every (catalog_key, catalog_granularity) this module actually implements --
# validated to be a subset of `adapter_safe_mappings()` (the source of
# truth) at import time below, and additionally validated to cover the
# *entire* 110-identity safe subset (this adapter targets 110/110, not a
# further-reduced slice of it).
_EMITTED_IDENTITIES: frozenset[tuple[str, str]] = frozenset(
    {
        ("home_score", "match"),
        ("away_score", "match"),
        ("home_away", "team_match"),
        ("status", "match"),
        ("kickoff_at", "match"),
        ("round_name", "match"),
        ("venue_name", "match"),
        ("started", "player_appearance"),
        ("shirt_number", "player_appearance"),
        ("listed_position", "player_appearance"),
        ("matches", "player_season"),
        ("appearances", "player_season"),
        ("starts", "player_season"),
        ("sub_appearances", "player_season"),
        ("touches", "player_match"),
        ("passes_total", "player_match"),
        ("passes_accurate", "player_match"),
        ("pass_completion_pct", "player_match"),
        ("passes_received", "player_match"),
        ("passes_under_pressure", "player_match"),
        ("assists", "player_match"),
        ("key_passes", "player_match"),
        ("chances_created", "player_match"),
        ("through_balls", "player_match"),
        ("crosses", "player_match"),
        ("switches", "player_match"),
        ("shots_total", "player_match"),
        ("shots_on_target", "player_match"),
        ("shots_off_target", "player_match"),
        ("blocked_shots", "player_match"),
        ("headed_shots", "player_match"),
        ("shots_on_target_pct", "player_match"),
        ("goals_per_shot", "player_match"),
        ("goals_per_shot_on_target", "player_match"),
        ("goals", "player_match"),
        ("non_penalty_goals", "player_match"),
        ("goal_contributions", "player_match"),
        ("penalty_goals", "player_match"),
        ("penalties_attempted", "player_match"),
        ("penalties_missed", "player_match"),
        ("advanced.xg", "player_match"),
        ("npxg", "player_match"),
        ("xg_per_shot", "player_match"),
        ("goals_minus_xg", "player_match"),
        ("non_penalty_goals_minus_npxg", "player_match"),
        ("duels_total", "player_match"),
        ("aerial_duels", "player_match"),
        ("tackles", "player_match"),
        ("ground_duels", "player_match"),
        ("interceptions", "player_match"),
        ("clearances", "player_match"),
        ("blocks", "player_match"),
        ("dribbles_attempted", "player_match"),
        ("dribbles_successful", "player_match"),
        ("dribble_success_pct", "player_match"),
        ("take_ons_attempted", "player_match"),
        ("take_ons_successful", "player_match"),
        ("take_on_success_pct", "player_match"),
        ("fouls_committed", "player_match"),
        ("fouls_drawn", "player_match"),
        ("dispossessed", "player_match"),
        ("miscontrols", "player_match"),
        ("possession_losses", "player_match"),
        ("turnovers", "player_match"),
        ("recoveries", "player_match"),
        ("pressures", "player_match"),
        ("carries", "player_match"),
        ("carry_distance", "player_match"),
        ("yellow_cards", "player_match"),
        ("red_cards", "player_match"),
        ("second_yellow_cards", "player_match"),
        ("saves", "player_match"),
        ("saves", "goalkeeper_match"),
        ("goals_conceded", "goalkeeper_match"),
        ("shots_on_target_faced", "goalkeeper_match"),
        ("save_pct", "goalkeeper_match"),
        ("clean_sheets", "goalkeeper_match"),
        ("claims", "goalkeeper_match"),
        ("crosses_stopped", "goalkeeper_match"),
        ("sweeper_actions", "goalkeeper_match"),
        ("passes", "goalkeeper_match"),
        ("distribution_accuracy_pct", "goalkeeper_match"),
        ("save_pct", "goalkeeper_season"),
        ("clean_sheets", "goalkeeper_season"),
        ("goals_for", "team_match"),
        ("goals_against", "team_match"),
        ("shots_total", "team_match"),
        ("shots_on_target", "team_match"),
        ("blocked_shots", "team_match"),
        ("shots_allowed", "team_match"),
        ("shots_on_target_allowed", "team_match"),
        ("passes_total", "team_match"),
        ("passes_accurate", "team_match"),
        ("pass_accuracy_pct", "team_match"),
        ("corners", "team_match"),
        ("offsides", "team_match"),
        ("fouls", "team_match"),
        ("yellow_cards", "team_match"),
        ("red_cards", "team_match"),
        ("pressures", "team_match"),
        ("recoveries", "team_match"),
        ("counter_attack_shots", "team_match"),
        ("goalkeeper_saves", "team_match"),
        ("formation", "team_match"),
        ("xg", "team_match"),
        ("xga", "team_match"),
        ("npxg", "team_match"),
        ("npxga", "team_match"),
        ("xg_per_shot", "team_match"),
        ("xga_per_shot", "team_match"),
    }
)

_validate_emission_scope(_EMITTED_IDENTITIES)

_MISSING_SAFE_IDENTITIES = _ADAPTER_SAFE_IDENTITIES - _EMITTED_IDENTITIES
if _MISSING_SAFE_IDENTITIES:
    raise AssertionError(
        f"statsbomb_open adapter does not implement all 110 adapter-safe identities; "
        f"missing: {sorted(_MISSING_SAFE_IDENTITIES)}"
    )


class StatsBombObservationConflictError(RuntimeError):
    """Two observations disagreed for the same source/entity/metric identity, or a
    non-adapter-safe emission was attempted."""


@dataclass(frozen=True)
class MatchBundle:
    """One match's already-loaded StatsBomb Open Data payloads -- the single
    deterministic unit this adapter operates on. Callers (the audit job) are
    responsible for loading these from the pinned local cache; this module
    never touches a filesystem or the network itself."""

    match_id: int
    match_summary: dict[str, Any]
    events_payload: list[Any]
    lineups_payload: list[Any]


@dataclass(frozen=True)
class _MatchInfo:
    match_id: int
    kickoff_at: datetime | None
    home_team_id: int | None
    home_team_name: str | None
    away_team_id: int | None
    away_team_name: str | None
    home_score: int | None
    away_score: int | None
    status: Any
    match_week: Any
    venue_name: Any
    # Provider-native identifiers, read directly from this match's own
    # `competition`/`season` blocks (`match_summary["competition"]
    # ["competition_id"]` / `match_summary["season"]["season_id"]`) --
    # verified real values for England 2015/16: competition_id=2,
    # season_id=27. These are genuinely supplied per-observation, never the
    # canonical "ENG_PL" code (Block 20D.2 completion pass correction: an
    # earlier pass had put the canonical code itself into
    # `competition_external_id`, which is not a provider-native identifier).
    competition_external_id: str | None
    season_external_id: str | None


@dataclass
class _MatchRoster:
    """The lineup-file-authoritative participation universe for one match --
    never derived from event-tag presence."""

    team_of: dict[int, int] = field(default_factory=dict)
    player_name: dict[int, str] = field(default_factory=dict)
    starters: set[int] = field(default_factory=set)
    used_subs: set[int] = field(default_factory=set)
    unused: set[int] = field(default_factory=set)
    goalkeepers: set[int] = field(default_factory=set)
    jersey_number: dict[int, int] = field(default_factory=dict)
    listed_position: dict[int, str] = field(default_factory=dict)
    cards: dict[int, list[str]] = field(default_factory=lambda: defaultdict(list))

    def participating_players(self) -> dict[int, int]:
        """playerId -> teamId for every confirmed participant (starter or used
        substitute) -- never an unused bench player, never an event-only
        player absent from the lineup file entirely."""
        return {pid: self.team_of[pid] for pid in (self.starters | self.used_subs)}

    def squad_players(self) -> dict[int, int]:
        """playerId -> teamId for the full named squad, including unused
        substitutes -- used only for roster-membership facts (`started`,
        `shirt_number`, season `matches`), never for performance stats."""
        return dict(self.team_of)


def parse_lineups(lineups_payload: list[Any]) -> _MatchRoster:
    """Parse one match's `lineups/{match_id}.json` payload into the
    authoritative participation roster."""

    roster = _MatchRoster()
    if not isinstance(lineups_payload, list):
        return roster
    for team in lineups_payload:
        if not isinstance(team, dict):
            continue
        team_id = team.get("team_id")
        if not isinstance(team_id, int):
            continue
        for player in team.get("lineup", []):
            if not isinstance(player, dict):
                continue
            player_id = player.get("player_id")
            if not isinstance(player_id, int):
                continue
            roster.team_of[player_id] = team_id
            name = player.get("player_name")
            if isinstance(name, str):
                roster.player_name[player_id] = name
            jersey = player.get("jersey_number")
            if isinstance(jersey, int):
                roster.jersey_number[player_id] = jersey
            for card in player.get("cards", []):
                if isinstance(card, dict):
                    card_type = card.get("card_type")
                    if isinstance(card_type, str) and card_type.strip():
                        roster.cards[player_id].append(card_type)

            positions = player.get("positions")
            if isinstance(positions, list) and positions:
                first = positions[0]
                if isinstance(first, dict):
                    if first.get("start_reason") == _STARTING_XI_REASON:
                        roster.starters.add(player_id)
                    else:
                        roster.used_subs.add(player_id)
                    position_name = first.get("position")
                    if isinstance(position_name, str):
                        roster.listed_position[player_id] = position_name
                if any(
                    isinstance(interval, dict)
                    and interval.get("position") == _GOALKEEPER_POSITION_NAME
                    for interval in positions
                ):
                    roster.goalkeepers.add(player_id)
            else:
                roster.unused.add(player_id)
    return roster


def _parse_kickoff(match_summary: dict[str, Any]) -> datetime | None:
    match_date = match_summary.get("match_date")
    kick_off = match_summary.get("kick_off")
    if not isinstance(match_date, str) or not match_date.strip():
        return None
    if not isinstance(kick_off, str) or not kick_off.strip():
        try:
            naive = datetime.strptime(match_date.strip(), "%Y-%m-%d")
        except ValueError:
            return None
        return naive.replace(tzinfo=UTC)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            naive = datetime.strptime(f"{match_date.strip()} {kick_off.strip()}", fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=UTC)
    return None


def parse_match(match_summary: dict[str, Any]) -> _MatchInfo | None:
    """Parse one match's summary entry (from `matches/2/27.json`) into the
    native match-identity facts."""

    match_id = match_summary.get("match_id")
    home_team = match_summary.get("home_team")
    away_team = match_summary.get("away_team")
    if (
        not isinstance(match_id, int)
        or not isinstance(home_team, dict)
        or not isinstance(away_team, dict)
    ):
        return None
    home_score = match_summary.get("home_score")
    away_score = match_summary.get("away_score")
    stadium = match_summary.get("stadium")
    venue_name = stadium.get("name") if isinstance(stadium, dict) else None
    home_team_id = home_team.get("home_team_id")
    away_team_id = away_team.get("away_team_id")
    competition = match_summary.get("competition")
    season = match_summary.get("season")
    competition_id = competition.get("competition_id") if isinstance(competition, dict) else None
    season_id = season.get("season_id") if isinstance(season, dict) else None
    return _MatchInfo(
        match_id=match_id,
        kickoff_at=_parse_kickoff(match_summary),
        home_team_id=home_team_id if isinstance(home_team_id, int) else None,
        home_team_name=home_team.get("home_team_name"),
        away_team_id=away_team_id if isinstance(away_team_id, int) else None,
        away_team_name=away_team.get("away_team_name"),
        home_score=home_score if isinstance(home_score, int) else None,
        away_score=away_score if isinstance(away_score, int) else None,
        status=match_summary.get("match_status"),
        match_week=match_summary.get("match_week"),
        venue_name=venue_name,
        competition_external_id=str(competition_id) if isinstance(competition_id, int) else None,
        season_external_id=str(season_id) if isinstance(season_id, int) else None,
    )


def _fallback_now() -> datetime:
    return datetime.now(UTC)


def _observation(
    *,
    entity_type: EntityType,
    entity_source_id: str,
    entity_identity_hints: dict[str, str],
    metric_name: str,
    value: Any,
    observed_at: datetime,
    source_reference: str,
    ingestion_run_id: int | None,
    # Optional here (unlike `_emit`, where it is required) so the legacy
    # Coverage Lab compatibility functions below -- which predate Metric
    # Catalog V2 and call `_observation()` directly, bypassing `_emit`/
    # `_guard` entirely -- can keep constructing observations exactly as
    # before, with `metric_granularity` correctly defaulting to `None`.
    metric_granularity: MetricGranularity | None = None,
) -> NormalizedObservation:
    return NormalizedObservation(
        source_code=SOURCE_CODE,
        source_type=SOURCE_TYPE,
        entity_type=entity_type,
        entity_source_id=entity_source_id,
        entity_identity_hints=entity_identity_hints,
        metric_name=metric_name,
        value=value,
        observed_at=observed_at,
        source_timestamp=observed_at,
        source_reference=source_reference,
        ingestion_run_id=ingestion_run_id,
        semantic_version=SEMANTIC_VERSION,
        metric_granularity=metric_granularity,
    )


def _guard(
    entity_type: EntityType, metric_name: str, metric_granularity: MetricGranularity
) -> None:
    # The exact (catalog_key, catalog_granularity) check is authoritative --
    # it is the only check that can distinguish e.g. `saves`/player_match
    # from `saves`/goalkeeper_match, which the entity_type-only check below
    # cannot (both project to entity_type "player"). The entity_type check
    # stays as defense-in-depth against an internal wiring bug.
    if (metric_name, metric_granularity) not in _ADAPTER_SAFE_IDENTITIES:
        raise StatsBombObservationConflictError(
            f"refusing to build a non-adapter-safe observation: "
            f"metric_name={metric_name!r} metric_granularity={metric_granularity!r}"
        )
    if (metric_name, entity_type) not in _SAFE_METRIC_ENTITY_PAIRS:
        raise StatsBombObservationConflictError(
            f"refusing to build a non-adapter-safe observation: "
            f"metric_name={metric_name!r} entity_type={entity_type!r}"
        )


def _emit(
    observations: list[NormalizedObservation],
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any],
    *,
    entity_type: EntityType,
    entity_source_id: str,
    entity_identity_hints: dict[str, str],
    metric_name: str,
    value: Any,
    observed_at: datetime,
    source_reference: str,
    ingestion_run_id: int | None,
    metric_granularity: MetricGranularity,
) -> None:
    _guard(entity_type, metric_name, metric_granularity)
    identity = (SOURCE_CODE, entity_type, entity_source_id, metric_name, metric_granularity)
    if identity in seen:
        if seen[identity] != value:
            raise StatsBombObservationConflictError(
                f"conflicting duplicate observation for {identity}: {seen[identity]!r} != {value!r}"
            )
        return
    seen[identity] = value
    observations.append(
        _observation(
            entity_type=entity_type,
            entity_source_id=entity_source_id,
            entity_identity_hints=entity_identity_hints,
            metric_name=metric_name,
            value=value,
            observed_at=observed_at,
            source_reference=source_reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity=metric_granularity,
        )
    )


def _validate_scope(info: _MatchInfo, scope: AdapterScope) -> None:
    """Refuses a match whose own real `competition_id`/`season_id` does not
    match the declared `AdapterScope` for this run -- e.g. a batch mixing
    ENG_PL and ESP_LL matches, or an ESP_LL run fed an England match.
    Never silently accepted, silently dropped, or attributed to the wrong
    scope (Block 20D.3)."""

    expected_competition_id = str(scope.provider_competition_id)
    if info.competition_external_id != expected_competition_id:
        raise ScopeMismatchError(
            f"match {info.match_id} has competition_id={info.competition_external_id!r}, "
            f"expected {expected_competition_id!r} for scope "
            f"{scope.canonical_competition_code}/{scope.season_label} -- refusing to emit "
            "observations for a match outside the declared scope"
        )
    if scope.provider_season_id is not None:
        expected_season_id = str(scope.provider_season_id)
        if info.season_external_id != expected_season_id:
            raise ScopeMismatchError(
                f"match {info.match_id} has season_id={info.season_external_id!r}, expected "
                f"{expected_season_id!r} for scope {scope.canonical_competition_code}/"
                f"{scope.season_label} -- refusing to emit observations for a match outside "
                "the declared scope"
            )


def _scope_hints(info: _MatchInfo | None, scope: AdapterScope) -> dict[str, str]:
    """Provider-native competition identity + this run's declared season
    label. `competition_external_id` is the source's own numeric
    `competition_id`, never a canonical code -- only populated when this
    specific match genuinely carries it. `info=None` (season-aggregate call
    sites with no single match in scope) omits `competition_external_id`
    rather than guessing."""

    hints: dict[str, str] = {"season_label": scope.season_label}
    if info is not None and info.competition_external_id is not None:
        hints["competition_external_id"] = info.competition_external_id
    return hints


def _match_hints(info: _MatchInfo, scope: AdapterScope) -> dict[str, str]:
    """Identity hints for a match-granularity observation: provider-native
    match id, home/away team ids and names when the source supplies them,
    and the raw per-observation kickoff date.

    `resolve_match()` (`data_mesh/entity_resolution.py`) is a pure function
    of its exact inputs and performs no clustering of its own. The bounded
    day-level tolerance that lets two providers converge on one logical
    match identity despite reporting adjacent-but-not-identical dates
    (`cluster_match_dates()`, applied via `build_match_date_clusters()` in
    `data_mesh/pipeline.py`) is a separate step one layer up. Block
    20D.2's V2 index builders
    (`entity_resolution_v2.build_match_index_v2_from_observations()`) call
    `resolve_match()` directly with each observation's raw `kickoff_date`
    hint -- cross-source date-tolerance canonicalization for the certified
    Wyscout/StatsBomb adapters is not yet wired into V2 and remains
    explicitly deferred to Block 20D.4's pipeline/Reconciliation V2
    wiring, not implemented a second time here."""

    hints = _scope_hints(info, scope)
    hints["match_external_id"] = str(info.match_id)
    if info.home_team_id is not None:
        hints["home_team_external_id"] = str(info.home_team_id)
    if info.home_team_name:
        hints["home_team_name"] = info.home_team_name
    if info.away_team_id is not None:
        hints["away_team_external_id"] = str(info.away_team_id)
    if info.away_team_name:
        hints["away_team_name"] = info.away_team_name
    if info.kickoff_at is not None:
        hints["kickoff_date"] = info.kickoff_at.date().isoformat()
    return hints


def _team_scoped_hints(info: _MatchInfo, team_id: int, scope: AdapterScope) -> dict[str, str]:
    """Identity hints for a team_match-granularity (or per-team `home_away`)
    observation: the match it belongs to, plus this specific team's own
    provider-native id and name (never the whole match's home/away pair --
    that belongs on the match-granularity observation itself)."""

    hints = _scope_hints(info, scope)
    hints["match_external_id"] = str(info.match_id)
    hints["team_external_id"] = str(team_id)
    name: str | None = None
    if team_id == info.home_team_id:
        name = info.home_team_name
    elif team_id == info.away_team_id:
        name = info.away_team_name
    if name:
        hints["team_name"] = name
    return hints


def _player_season_hints(
    season_scope_hints: dict[str, str] | None,
    player_name_by_id: dict[int, str],
    player_id: int,
    scope: AdapterScope,
) -> dict[str, str]:
    """Identity hints for a player_season/goalkeeper_season observation:
    competition/season scope (captured once from the first match seen, since
    every match in one season-parsing call shares it) plus this player's own
    provider-native id and name -- never a per-match team, since a season
    fact is not scoped to one match."""

    hints: dict[str, str] = (
        dict(season_scope_hints) if season_scope_hints else {"season_label": scope.season_label}
    )
    hints["player_external_id"] = str(player_id)
    name = player_name_by_id.get(player_id)
    if name:
        hints["player_name"] = name
    return hints


def _player_scoped_hints(
    info: _MatchInfo, roster: _MatchRoster, player_id: int, scope: AdapterScope
) -> dict[str, str]:
    """Identity hints for a player_appearance/player_match/goalkeeper_match
    observation: the match, this player's own provider-native id and name
    (from the lineup file), and the team they played for in this match when
    the roster resolves it."""

    hints = _scope_hints(info, scope)
    hints["match_external_id"] = str(info.match_id)
    hints["player_external_id"] = str(player_id)
    name = roster.player_name.get(player_id)
    if name:
        hints["player_name"] = name
    team_id = roster.team_of.get(player_id)
    if team_id is not None:
        hints["team_external_id"] = str(team_id)
    return hints


def _events_reference(match_id: int, source_revision: str) -> str:
    return f"statsbomb/open-data@{source_revision}/data/events/{match_id}.json"


def _lineups_reference(match_id: int, source_revision: str) -> str:
    return f"statsbomb/open-data@{source_revision}/data/lineups/{match_id}.json"


def _matches_reference(source_revision: str, scope: AdapterScope) -> str:
    return (
        f"statsbomb/open-data@{source_revision}/data/matches/"
        f"{scope.provider_competition_id}/{scope.provider_season_id}.json"
    )


# ---------------------------------------------------------------------------
# Match-level observations (6 DIRECT `match`-granularity identities, plus
# `home_away` at `team_match`-granularity -- corrected Block 20D.2
# review-fix pass)
# ---------------------------------------------------------------------------


def parse_match_observations(
    bundles: list[MatchBundle],
    *,
    source_revision: str = DEFAULT_PINNED_REVISION,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}
    reference = _matches_reference(source_revision, scope)

    for bundle in bundles:
        info = parse_match(bundle.match_summary)
        if info is None:
            continue
        _validate_scope(info, scope)
        observed_at = info.kickoff_at or _fallback_now()
        entity_source_id = str(info.match_id)
        hints = _match_hints(info, scope)

        if info.home_score is not None:
            _emit(
                observations,
                seen,
                entity_type="match",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="home_score",
                value=info.home_score,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="match",
            )
        if info.away_score is not None:
            _emit(
                observations,
                seen,
                entity_type="match",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="away_score",
                value=info.away_score,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="match",
            )
        if isinstance(info.status, str) and info.status.strip():
            _emit(
                observations,
                seen,
                entity_type="match",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="status",
                value=info.status,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="match",
            )
        if info.kickoff_at is not None:
            _emit(
                observations,
                seen,
                entity_type="match",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="kickoff_at",
                value=info.kickoff_at.isoformat(),
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="match",
            )
        if isinstance(info.match_week, int):
            _emit(
                observations,
                seen,
                entity_type="match",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="round_name",
                value=str(info.match_week),
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="match",
            )
        if isinstance(info.venue_name, str) and info.venue_name.strip():
            _emit(
                observations,
                seen,
                entity_type="match",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="venue_name",
                value=info.venue_name,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="match",
            )

        # `home_away` (catalog granularity "team_match", corrected Block
        # 20D.2 review-fix pass) is inherently a per-team-in-this-match
        # fact -- emitted per team, same team-match-scoped convention as
        # every other team-match fact in this codebase.
        for team_id, side in ((info.home_team_id, "home"), (info.away_team_id, "away")):
            if team_id is None:
                continue
            _emit(
                observations,
                seen,
                entity_type="team",
                entity_source_id=f"{info.match_id}:{team_id}",
                entity_identity_hints=_team_scoped_hints(info, team_id, scope),
                metric_name="home_away",
                value=side,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="team_match",
            )

    return observations


# ---------------------------------------------------------------------------
# Participation (player_appearance + player_season)
# ---------------------------------------------------------------------------


def _emit_squad_facts(
    observations: list[NormalizedObservation],
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any],
    *,
    roster: _MatchRoster,
    info: _MatchInfo,
    observed_at: datetime,
    reference: str,
    scope: AdapterScope,
    ingestion_run_id: int | None,
) -> None:
    """`started`/`shirt_number` for the full named squad (roster membership
    is a real fact regardless of playing time) + `listed_position` for
    confirmed participants only (unused substitutes have no recorded
    position interval to read)."""

    match_id = info.match_id
    for player_id in roster.squad_players():
        entity_source_id = f"{match_id}:{player_id}"
        hints = _player_scoped_hints(info, roster, player_id, scope)
        _emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id=entity_source_id,
            entity_identity_hints=hints,
            metric_name="started",
            value=player_id in roster.starters,
            observed_at=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity="player_appearance",
        )
        jersey = roster.jersey_number.get(player_id)
        if jersey is not None:
            _emit(
                observations,
                seen,
                entity_type="player",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="shirt_number",
                value=jersey,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="player_appearance",
            )
        listed_position = roster.listed_position.get(player_id)
        if listed_position is not None:
            _emit(
                observations,
                seen,
                entity_type="player",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="listed_position",
                value=listed_position,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="player_appearance",
            )


def parse_lineup_participation_observations(
    bundles: list[MatchBundle],
    *,
    source_revision: str = DEFAULT_PINNED_REVISION,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """`started`/`shirt_number`/`listed_position` (player_appearance) +
    season `matches`/`appearances`/`starts`/`sub_appearances`
    (player_season)."""

    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}

    season_matches: dict[int, int] = defaultdict(int)
    season_starts: dict[int, int] = defaultdict(int)
    season_appearances: dict[int, int] = defaultdict(int)
    latest_contributing_date: dict[int, datetime] = {}
    player_name_by_id: dict[int, str] = {}
    season_scope_hints: dict[str, str] | None = None

    for bundle in bundles:
        info = parse_match(bundle.match_summary)
        if info is None:
            continue
        _validate_scope(info, scope)
        roster = parse_lineups(bundle.lineups_payload)
        observed_at = info.kickoff_at or _fallback_now()
        reference = _lineups_reference(info.match_id, source_revision)

        _emit_squad_facts(
            observations,
            seen,
            roster=roster,
            info=info,
            observed_at=observed_at,
            reference=reference,
            scope=scope,
            ingestion_run_id=ingestion_run_id,
        )
        for player_id in roster.player_name:
            player_name_by_id.setdefault(player_id, roster.player_name[player_id])
        if season_scope_hints is None:
            season_scope_hints = _scope_hints(info, scope)

        for player_id in roster.squad_players():
            season_matches[player_id] += 1
            if info.kickoff_at is not None and info.kickoff_at > latest_contributing_date.get(
                player_id, datetime.min.replace(tzinfo=UTC)
            ):
                latest_contributing_date[player_id] = info.kickoff_at

        for player_id in roster.participating_players():
            season_appearances[player_id] += 1
            if player_id in roster.starters:
                season_starts[player_id] += 1

    season_reference = f"statsbomb/open-data@{source_revision}/data/lineups/*.json"
    for player_id, matches_count in season_matches.items():
        entity_source_id = str(player_id)
        observed_at = latest_contributing_date.get(player_id, _fallback_now())
        season_hints = _player_season_hints(season_scope_hints, player_name_by_id, player_id, scope)
        _emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id=entity_source_id,
            entity_identity_hints=season_hints,
            metric_name="matches",
            value=matches_count,
            observed_at=observed_at,
            source_reference=season_reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity="player_season",
        )
        appearances_count = season_appearances.get(player_id, 0)
        starts_count = season_starts.get(player_id, 0)
        _emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id=entity_source_id,
            entity_identity_hints=season_hints,
            metric_name="appearances",
            value=appearances_count,
            observed_at=observed_at,
            source_reference=season_reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity="player_season",
        )
        _emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id=entity_source_id,
            entity_identity_hints=season_hints,
            metric_name="starts",
            value=starts_count,
            observed_at=observed_at,
            source_reference=season_reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity="player_season",
        )
        _emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id=entity_source_id,
            entity_identity_hints=season_hints,
            metric_name="sub_appearances",
            value=appearances_count - starts_count,
            observed_at=observed_at,
            source_reference=season_reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity="player_season",
        )

    return observations


# ---------------------------------------------------------------------------
# Event accumulation
# ---------------------------------------------------------------------------

_ZeroDict = dict[str, "int | float"]


def _new_counts() -> _ZeroDict:
    counts: _ZeroDict = dict.fromkeys(_PLAYER_MATCH_COUNT_METRICS, 0)
    counts["advanced.xg"] = 0.0
    counts["npxg"] = 0.0
    counts["carry_distance"] = 0.0
    return counts


def _event_player_id(event: dict[str, Any]) -> int | None:
    player = event.get("player")
    if isinstance(player, dict):
        player_id = player.get("id")
        if isinstance(player_id, int):
            return player_id
    return None


def _euclidean_distance(start: Any, end: Any) -> float | None:
    if not (isinstance(start, list) and isinstance(end, list)):
        return None
    if len(start) < 2 or len(end) < 2:
        return None
    try:
        dx = float(end[0]) - float(start[0])
        dy = float(end[1]) - float(start[1])
    except (TypeError, ValueError):
        return None
    return math.sqrt(dx * dx + dy * dy)


@dataclass
class _MatchEventAccumulation:
    counts_by_player: dict[int, _ZeroDict] = field(default_factory=dict)
    passes_received_by_player: dict[int, int] = field(default_factory=lambda: defaultdict(int))
    formation_by_team: dict[int, str] = field(default_factory=dict)


def _accumulate_match_events(events_payload: list[Any]) -> _MatchEventAccumulation:
    """Accumulates one match's already-loaded events file into
    per-player raw counts, a per-player passes-received tally (attributed
    to the pass's *recipient*, not its own `player` field), and each
    team's opening (`Starting XI`) formation."""

    result = _MatchEventAccumulation()

    def bump(player_id: int, metric: str, amount: int | float = 1) -> None:
        if player_id not in result.counts_by_player:
            result.counts_by_player[player_id] = _new_counts()
        result.counts_by_player[player_id][metric] += amount

    for event in events_payload:
        if not isinstance(event, dict):
            continue
        type_name = event.get("type", {}).get("name")

        if type_name == _STARTING_XI_REASON:
            team = event.get("team", {})
            team_id = team.get("id")
            tactics = event.get("tactics", {})
            formation_raw = tactics.get("formation")
            if isinstance(team_id, int) and isinstance(formation_raw, int):
                result.formation_by_team[team_id] = "-".join(str(formation_raw))
            continue

        player_id = _event_player_id(event)
        if player_id is not None:
            bump(player_id, "touches")

        if type_name == "Shot":
            shot = event.get("shot")
            if isinstance(shot, dict) and player_id is not None:
                bump(player_id, "shots_total")
                outcome = shot.get("outcome", {}).get("name")
                if outcome in _ON_TARGET_SHOT_OUTCOMES:
                    bump(player_id, "shots_on_target")
                if outcome in _OFF_TARGET_SHOT_OUTCOMES:
                    bump(player_id, "shots_off_target")
                if outcome == _BLOCKED_OUTCOME:
                    bump(player_id, "blocked_shots")
                if shot.get("body_part", {}).get("name") == _HEAD_BODY_PART:
                    bump(player_id, "headed_shots")
                is_goal = outcome == _GOAL_OUTCOME
                if is_goal:
                    bump(player_id, "goals")
                is_penalty = shot.get("type", {}).get("name") == _PENALTY_SHOT_TYPE
                if is_penalty:
                    bump(player_id, "penalties_attempted")
                    if is_goal:
                        bump(player_id, "penalty_goals")
                xg = shot.get("statsbomb_xg")
                if isinstance(xg, int | float):
                    bump(player_id, "advanced.xg", float(xg))
                    if not is_penalty:
                        bump(player_id, "npxg", float(xg))

        elif type_name == "Pass":
            pass_block = event.get("pass")
            if isinstance(pass_block, dict) and player_id is not None:
                bump(player_id, "passes_total")
                is_accurate = "outcome" not in pass_block
                if is_accurate:
                    bump(player_id, "passes_accurate")
                if pass_block.get("shot_assist") is True:
                    bump(player_id, "key_passes")
                if pass_block.get("goal_assist") is True:
                    bump(player_id, "assists")
                if pass_block.get("through_ball") is True:
                    bump(player_id, "through_balls")
                if pass_block.get("cross") is True:
                    bump(player_id, "crosses")
                if pass_block.get("switch") is True:
                    bump(player_id, "switches")
                if event.get("under_pressure") is True:
                    bump(player_id, "passes_under_pressure")
                if is_accurate:
                    recipient = pass_block.get("recipient")
                    recipient_id = recipient.get("id") if isinstance(recipient, dict) else None
                    if isinstance(recipient_id, int):
                        result.passes_received_by_player[recipient_id] += 1

        elif type_name == "Duel":
            duel = event.get("duel")
            if isinstance(duel, dict) and player_id is not None:
                bump(player_id, "duels_total")
                duel_type = duel.get("type", {}).get("name")
                if duel_type == _AERIAL_LOST_DUEL_TYPE:
                    bump(player_id, "aerial_duels")
                if duel_type == _TACKLE_DUEL_TYPE:
                    bump(player_id, "tackles")

        elif type_name == "Interception":
            if player_id is not None:
                bump(player_id, "interceptions")

        elif type_name == "Clearance":
            if player_id is not None:
                bump(player_id, "clearances")

        elif type_name == "Block":
            if player_id is not None:
                bump(player_id, "blocks")

        elif type_name == "Dribble":
            dribble = event.get("dribble")
            if isinstance(dribble, dict) and player_id is not None:
                bump(player_id, "dribbles_attempted")
                if dribble.get("outcome", {}).get("name") == _DRIBBLE_COMPLETE_OUTCOME:
                    bump(player_id, "dribbles_successful")

        elif type_name == "Foul Committed":
            if player_id is not None:
                bump(player_id, "fouls_committed")

        elif type_name == "Foul Won":
            if player_id is not None:
                bump(player_id, "fouls_drawn")

        elif type_name == "Dispossessed":
            if player_id is not None:
                bump(player_id, "dispossessed")

        elif type_name == "Miscontrol":
            if player_id is not None:
                bump(player_id, "miscontrols")

        elif type_name == "Ball Recovery":
            if player_id is not None:
                bump(player_id, "recoveries")

        elif type_name == "Pressure":
            if player_id is not None:
                bump(player_id, "pressures")

        elif type_name == "Carry":
            carry = event.get("carry")
            if isinstance(carry, dict) and player_id is not None:
                bump(player_id, "carries")
                distance = _euclidean_distance(event.get("location"), carry.get("end_location"))
                if distance is not None:
                    bump(player_id, "carry_distance", distance)

        elif type_name == "Goal Keeper":
            goalkeeper = event.get("goalkeeper")
            if isinstance(goalkeeper, dict) and player_id is not None:
                gk_type = goalkeeper.get("type", {}).get("name")
                if gk_type in _SAVE_GOALKEEPER_TYPES:
                    bump(player_id, "saves")
                elif gk_type in _CONCEDED_GOALKEEPER_TYPES:
                    bump(player_id, "goals_conceded")
                if gk_type == _KEEPER_SWEEPER_TYPE:
                    bump(player_id, "sweeper_actions")
                    if goalkeeper.get("outcome", {}).get("name") == _CLAIM_OUTCOME:
                        bump(player_id, "claims")
                if gk_type == _PUNCH_TYPE:
                    bump(player_id, "crosses_stopped")

    return result


# ---------------------------------------------------------------------------
# player_match observations
# ---------------------------------------------------------------------------


def _card_counts(cards: list[str]) -> tuple[int, int, int]:
    """Returns (yellow_cards, red_cards, second_yellow_cards) from the
    lineup file's authoritative per-player `cards` array -- the sole card
    source; never combined with event-derived Foul Committed/Bad Behaviour
    counts, which would risk double-counting."""

    yellow = sum(1 for c in cards if c == _YELLOW_CARD_TYPE)
    second_yellow = sum(1 for c in cards if c == _SECOND_YELLOW_TYPE)
    red = sum(1 for c in cards if c in _RED_CARD_TYPES)
    return yellow, red, second_yellow


def _emit_cards(
    observations: list[NormalizedObservation],
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any],
    *,
    entity_source_id: str,
    cards: list[str],
    observed_at: datetime,
    reference: str,
    hints: dict[str, str],
    ingestion_run_id: int | None,
) -> None:
    yellow, red, second_yellow = _card_counts(cards)
    for metric_name, value in (
        ("yellow_cards", yellow),
        ("red_cards", red),
        ("second_yellow_cards", second_yellow),
    ):
        _emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id=entity_source_id,
            entity_identity_hints=hints,
            metric_name=metric_name,
            value=value,
            observed_at=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity="player_match",
        )


def _emit_player_match_metrics(
    observations: list[NormalizedObservation],
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any],
    *,
    match_id: int,
    player_id: int,
    counts: _ZeroDict,
    observed_at: datetime,
    reference: str,
    hints: dict[str, str],
    ingestion_run_id: int | None,
) -> None:
    entity_source_id = f"{match_id}:{player_id}"

    def emit(metric_name: str, value: Any) -> None:
        _emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id=entity_source_id,
            entity_identity_hints=hints,
            metric_name=metric_name,
            value=value,
            observed_at=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity="player_match",
        )

    for metric_name in _PLAYER_MATCH_EMITTED_COUNT_METRICS:
        emit(metric_name, counts[metric_name])
    emit("ground_duels", counts["tackles"])
    emit("take_ons_attempted", counts["dribbles_attempted"])
    emit("take_ons_successful", counts["dribbles_successful"])

    xg = float(counts["advanced.xg"])
    npxg = float(counts["npxg"])
    goals = int(counts["goals"])
    penalty_goals = int(counts["penalty_goals"])
    penalties_attempted = int(counts["penalties_attempted"])
    shots_total = int(counts["shots_total"])
    shots_on_target = int(counts["shots_on_target"])
    passes_total = int(counts["passes_total"])
    passes_accurate = int(counts["passes_accurate"])
    key_passes = int(counts["key_passes"])
    assists = int(counts["assists"])
    dispossessed = int(counts["dispossessed"])
    miscontrols = int(counts["miscontrols"])
    dribbles_attempted = int(counts["dribbles_attempted"])
    dribbles_successful = int(counts["dribbles_successful"])

    non_penalty_goals = goals - penalty_goals
    emit("non_penalty_goals", non_penalty_goals)
    emit("goal_contributions", goals + assists)
    emit("penalties_missed", penalties_attempted - penalty_goals)
    emit("chances_created", key_passes + assists)
    emit("goals_minus_xg", round(goals - xg, 4))
    emit("non_penalty_goals_minus_npxg", round(non_penalty_goals - npxg, 4))
    emit("possession_losses", dispossessed + miscontrols)
    emit("turnovers", dispossessed + miscontrols)

    if shots_total > 0:
        emit("shots_on_target_pct", round(100.0 * shots_on_target / shots_total, 4))
        emit("goals_per_shot", round(goals / shots_total, 4))
        emit("xg_per_shot", round(xg / shots_total, 4))
    if shots_on_target > 0:
        emit("goals_per_shot_on_target", round(goals / shots_on_target, 4))
    if passes_total > 0:
        emit("pass_completion_pct", round(100.0 * passes_accurate / passes_total, 4))
    if dribbles_attempted > 0:
        pct = round(100.0 * dribbles_successful / dribbles_attempted, 4)
        emit("dribble_success_pct", pct)
        emit("take_on_success_pct", pct)


def parse_player_match_observations(
    bundles: list[MatchBundle],
    *,
    source_revision: str = DEFAULT_PINNED_REVISION,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """The 58 player_match identities in the adapter-safe subset. Emitted
    only for confirmed participants (starter or used substitute) -- an
    unused bench player, or a player referenced by an event but absent
    from the lineup file, never receives a fabricated performance zero.
    Cards come from the lineup file, never from event aggregation."""

    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}

    for bundle in bundles:
        info = parse_match(bundle.match_summary)
        if info is None:
            continue
        _validate_scope(info, scope)
        roster = parse_lineups(bundle.lineups_payload)
        accumulation = _accumulate_match_events(bundle.events_payload)
        observed_at = info.kickoff_at or _fallback_now()
        events_reference = _events_reference(info.match_id, source_revision)
        lineups_reference = _lineups_reference(info.match_id, source_revision)

        for player_id in roster.participating_players():
            counts = dict(accumulation.counts_by_player.get(player_id, _new_counts()))
            counts["passes_received"] = accumulation.passes_received_by_player.get(player_id, 0)
            player_hints = _player_scoped_hints(info, roster, player_id, scope)
            _emit_player_match_metrics(
                observations,
                seen,
                match_id=info.match_id,
                player_id=player_id,
                counts=counts,
                observed_at=observed_at,
                reference=events_reference,
                hints=player_hints,
                ingestion_run_id=ingestion_run_id,
            )
            _emit_cards(
                observations,
                seen,
                entity_source_id=f"{info.match_id}:{player_id}",
                cards=roster.cards.get(player_id, []),
                observed_at=observed_at,
                reference=lineups_reference,
                hints=player_hints,
                ingestion_run_id=ingestion_run_id,
            )

    return observations


# ---------------------------------------------------------------------------
# Goalkeeper observations (goalkeeper_match + goalkeeper_season)
# ---------------------------------------------------------------------------


def parse_goalkeeper_observations(
    bundles: list[MatchBundle],
    *,
    source_revision: str = DEFAULT_PINNED_REVISION,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
    include_season: bool = True,
) -> list[NormalizedObservation]:
    """The 10 goalkeeper_match identities, plus (when `include_season`) the
    2 goalkeeper_season identities. Goalkeeper identity comes exclusively
    from the lineup file's own `positions[*].position == "Goalkeeper"` for
    a confirmed participant -- never from event occurrence, jersey number,
    or a name guess. `shots_on_target_faced = saves + goals_conceded`,
    both already player-attributed on the Goal Keeper event itself -- no
    team-shots cross-referencing is needed (a material simplification vs.
    the Wyscout adapter's equivalent)."""

    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}

    season_saves: dict[int, int] = defaultdict(int)
    season_shots_faced: dict[int, int] = defaultdict(int)
    season_clean_sheets: dict[int, int] = defaultdict(int)
    season_matches_resolved: dict[int, int] = defaultdict(int)
    latest_date: dict[int, datetime] = {}
    player_name_by_id: dict[int, str] = {}
    season_scope_hints: dict[str, str] | None = None

    for bundle in bundles:
        info = parse_match(bundle.match_summary)
        if info is None:
            continue
        _validate_scope(info, scope)
        roster = parse_lineups(bundle.lineups_payload)
        accumulation = _accumulate_match_events(bundle.events_payload)
        observed_at = info.kickoff_at or _fallback_now()
        reference = _events_reference(info.match_id, source_revision)
        participating = roster.participating_players()
        for player_id in roster.player_name:
            player_name_by_id.setdefault(player_id, roster.player_name[player_id])
        if season_scope_hints is None:
            season_scope_hints = _scope_hints(info, scope)

        for player_id in participating:
            if player_id not in roster.goalkeepers:
                continue
            entity_source_id = f"{info.match_id}:{player_id}"
            hints = _player_scoped_hints(info, roster, player_id, scope)
            counts = accumulation.counts_by_player.get(player_id, _new_counts())
            saves = int(counts["saves"])
            goals_conceded = int(counts["goals_conceded"])
            passes_total = int(counts["passes_total"])
            passes_accurate = int(counts["passes_accurate"])
            shots_on_target_faced = saves + goals_conceded

            def emit(
                metric_name: str,
                value: Any,
                *,
                entity_source_id: str = entity_source_id,
                hints: dict[str, str] = hints,
                observed_at: datetime = observed_at,
                reference: str = reference,
            ) -> None:
                _emit(
                    observations,
                    seen,
                    entity_type="player",
                    entity_source_id=entity_source_id,
                    entity_identity_hints=hints,
                    metric_name=metric_name,
                    value=value,
                    observed_at=observed_at,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                    metric_granularity="goalkeeper_match",
                )

            # Same real event-derived count `_emit_player_match_metrics` already
            # emits at `player_match` granularity -- genuinely two distinct
            # catalog identities (Block 20D.2's canonical example of why
            # `metric_granularity` exists), not a duplicate. `_emit`'s
            # (metric_name, metric_granularity)-inclusive dedup identity keeps
            # these two facts from ever being treated as conflicting or merged.
            emit("saves", saves)
            emit("goals_conceded", goals_conceded)
            emit("clean_sheets", goals_conceded == 0)
            emit("shots_on_target_faced", shots_on_target_faced)
            if shots_on_target_faced > 0:
                emit("save_pct", round(100.0 * saves / shots_on_target_faced, 4))
            emit("passes", passes_total)
            if passes_total > 0:
                emit(
                    "distribution_accuracy_pct",
                    round(100.0 * passes_accurate / passes_total, 4),
                )
            emit("claims", int(counts["claims"]))
            emit("crosses_stopped", int(counts["crosses_stopped"]))
            emit("sweeper_actions", int(counts["sweeper_actions"]))

            season_saves[player_id] += saves
            season_shots_faced[player_id] += shots_on_target_faced
            season_matches_resolved[player_id] += 1
            if goals_conceded == 0:
                season_clean_sheets[player_id] += 1
            if info.kickoff_at is not None:
                latest_date[player_id] = info.kickoff_at

    if not include_season:
        return observations

    season_reference = f"statsbomb/open-data@{source_revision}/data/events+lineups/*.json"
    for player_id, matches_resolved in season_matches_resolved.items():
        if matches_resolved == 0:
            continue
        observed_at = latest_date.get(player_id, _fallback_now())
        entity_source_id = str(player_id)
        season_hints = _player_season_hints(season_scope_hints, player_name_by_id, player_id, scope)
        _emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id=entity_source_id,
            entity_identity_hints=season_hints,
            metric_name="clean_sheets",
            value=season_clean_sheets.get(player_id, 0),
            observed_at=observed_at,
            source_reference=season_reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity="goalkeeper_season",
        )
        shots_faced_total = season_shots_faced.get(player_id, 0)
        if shots_faced_total > 0:
            _emit(
                observations,
                seen,
                entity_type="player",
                entity_source_id=entity_source_id,
                entity_identity_hints=season_hints,
                metric_name="save_pct",
                value=round(100.0 * season_saves.get(player_id, 0) / shots_faced_total, 4),
                observed_at=observed_at,
                source_reference=season_reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="goalkeeper_season",
            )

    return observations


# ---------------------------------------------------------------------------
# team_match observations
# ---------------------------------------------------------------------------


@dataclass
class _TeamMatchCounts:
    shots_total: int = 0
    shots_on_target: int = 0
    blocked_shots: int = 0
    passes_total: int = 0
    passes_accurate: int = 0
    fouls: int = 0
    corners: int = 0
    offsides: int = 0
    pressures: int = 0
    recoveries: int = 0
    counter_attack_shots: int = 0


def _accumulate_team_events(events_payload: list[Any]) -> dict[int, _TeamMatchCounts]:
    team_counts: dict[int, _TeamMatchCounts] = defaultdict(_TeamMatchCounts)
    for event in events_payload:
        if not isinstance(event, dict):
            continue
        team = event.get("team")
        team_id = team.get("id") if isinstance(team, dict) else None
        if not isinstance(team_id, int):
            continue
        type_name = event.get("type", {}).get("name")
        stats = team_counts[team_id]
        play_pattern = event.get("play_pattern", {}).get("name")

        if type_name == "Shot":
            shot = event.get("shot", {})
            stats.shots_total += 1
            outcome = shot.get("outcome", {}).get("name")
            if outcome in _ON_TARGET_SHOT_OUTCOMES:
                stats.shots_on_target += 1
            if outcome == _BLOCKED_OUTCOME:
                stats.blocked_shots += 1
            if play_pattern == _COUNTER_ATTACK_PLAY_PATTERN:
                stats.counter_attack_shots += 1
        elif type_name == "Pass":
            pass_block = event.get("pass", {})
            stats.passes_total += 1
            if "outcome" not in pass_block:
                stats.passes_accurate += 1
            if pass_block.get("type", {}).get("name") == _CORNER_PASS_TYPE:
                stats.corners += 1
        elif type_name == "Foul Committed":
            stats.fouls += 1
        elif type_name == "Offside":
            stats.offsides += 1
        elif type_name == "Pressure":
            stats.pressures += 1
        elif type_name == "Ball Recovery":
            stats.recoveries += 1

    return team_counts


def parse_team_match_observations(
    bundles: list[MatchBundle],
    *,
    source_revision: str = DEFAULT_PINNED_REVISION,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """The 26 team_match identities in the adapter-safe subset. Cards and
    goal totals never come from event aggregation -- cards roll up the
    lineup-authoritative per-player records, and goals use the native
    match score."""

    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}

    for bundle in bundles:
        info = parse_match(bundle.match_summary)
        if info is None:
            continue
        _validate_scope(info, scope)
        if info.home_team_id is None or info.away_team_id is None:
            continue
        roster = parse_lineups(bundle.lineups_payload)
        accumulation = _accumulate_match_events(bundle.events_payload)
        team_counts = _accumulate_team_events(bundle.events_payload)
        observed_at = info.kickoff_at or _fallback_now()
        reference = _events_reference(info.match_id, source_revision)
        participating = roster.participating_players()

        team_yellow: dict[int, int] = defaultdict(int)
        team_red: dict[int, int] = defaultdict(int)
        team_xg: dict[int, float] = defaultdict(float)
        team_npxg: dict[int, float] = defaultdict(float)
        team_goalkeeper_saves: dict[int, int] = defaultdict(int)
        for player_id, team_id in participating.items():
            yellow, red, _second_yellow = _card_counts(roster.cards.get(player_id, []))
            team_yellow[team_id] += yellow
            team_red[team_id] += red
            counts = accumulation.counts_by_player.get(player_id, _new_counts())
            team_xg[team_id] += float(counts["advanced.xg"])
            team_npxg[team_id] += float(counts["npxg"])
            if player_id in roster.goalkeepers:
                team_goalkeeper_saves[team_id] += int(counts["saves"])

        for team_id, opponent_id, own_score, opp_score in (
            (info.home_team_id, info.away_team_id, info.home_score, info.away_score),
            (info.away_team_id, info.home_team_id, info.away_score, info.home_score),
        ):
            entity_source_id = f"{info.match_id}:{team_id}"
            hints = _team_scoped_hints(info, team_id, scope)
            stats = team_counts.get(team_id, _TeamMatchCounts())
            opp_stats = team_counts.get(opponent_id, _TeamMatchCounts())

            def emit(
                metric_name: str,
                value: Any,
                *,
                entity_source_id: str = entity_source_id,
                hints: dict[str, str] = hints,
                observed_at: datetime = observed_at,
                reference: str = reference,
            ) -> None:
                _emit(
                    observations,
                    seen,
                    entity_type="team",
                    entity_source_id=entity_source_id,
                    entity_identity_hints=hints,
                    metric_name=metric_name,
                    value=value,
                    observed_at=observed_at,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                    metric_granularity="team_match",
                )

            if own_score is not None:
                emit("goals_for", own_score)
            if opp_score is not None:
                emit("goals_against", opp_score)
            emit("shots_total", stats.shots_total)
            emit("shots_on_target", stats.shots_on_target)
            emit("blocked_shots", stats.blocked_shots)
            emit("shots_allowed", opp_stats.shots_total)
            emit("shots_on_target_allowed", opp_stats.shots_on_target)
            emit("passes_total", stats.passes_total)
            emit("passes_accurate", stats.passes_accurate)
            if stats.passes_total > 0:
                emit(
                    "pass_accuracy_pct",
                    round(100.0 * stats.passes_accurate / stats.passes_total, 4),
                )
            emit("corners", stats.corners)
            emit("offsides", stats.offsides)
            emit("fouls", stats.fouls)
            emit("pressures", stats.pressures)
            emit("recoveries", stats.recoveries)
            emit("counter_attack_shots", stats.counter_attack_shots)
            emit("yellow_cards", team_yellow.get(team_id, 0))
            emit("red_cards", team_red.get(team_id, 0))
            emit("goalkeeper_saves", team_goalkeeper_saves.get(team_id, 0))

            team_formation = accumulation.formation_by_team.get(team_id)
            if team_formation is not None:
                emit("formation", team_formation)

            xg = round(team_xg.get(team_id, 0.0), 4)
            npxg = round(team_npxg.get(team_id, 0.0), 4)
            xga = round(team_xg.get(opponent_id, 0.0), 4)
            npxga = round(team_npxg.get(opponent_id, 0.0), 4)
            emit("xg", xg)
            emit("npxg", npxg)
            emit("xga", xga)
            emit("npxga", npxga)
            if stats.shots_total > 0:
                emit("xg_per_shot", round(xg / stats.shots_total, 4))
            if opp_stats.shots_total > 0:
                emit("xga_per_shot", round(xga / opp_stats.shots_total, 4))

    return observations


# ---------------------------------------------------------------------------
# Full-season / single-match entry points
# ---------------------------------------------------------------------------


def adapt_match_bundle(
    bundle: MatchBundle,
    *,
    source_revision: str = DEFAULT_PINNED_REVISION,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """Every adapter-safe observation derivable from ONE match alone --
    match, player_appearance, player_match, goalkeeper_match, and
    team_match identities. Deliberately excludes player_season/
    goalkeeper_season, which require the full season's bundles to avoid
    silently treating one match as the whole season."""

    bundles = [bundle]
    observations: list[NormalizedObservation] = []
    observations.extend(
        parse_match_observations(
            bundles, source_revision=source_revision, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )

    info = parse_match(bundle.match_summary)
    if info is not None:
        _validate_scope(info, scope)
        roster = parse_lineups(bundle.lineups_payload)
        seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}
        _emit_squad_facts(
            observations,
            seen,
            roster=roster,
            info=info,
            observed_at=info.kickoff_at or _fallback_now(),
            reference=_lineups_reference(info.match_id, source_revision),
            scope=scope,
            ingestion_run_id=ingestion_run_id,
        )

    observations.extend(
        parse_player_match_observations(
            bundles, source_revision=source_revision, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )
    observations.extend(
        parse_goalkeeper_observations(
            bundles,
            source_revision=source_revision,
            scope=scope,
            ingestion_run_id=ingestion_run_id,
            include_season=False,
        )
    )
    observations.extend(
        parse_team_match_observations(
            bundles, source_revision=source_revision, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )
    return observations


def parse_premier_league_season(
    bundles: list[MatchBundle],
    *,
    source_revision: str = DEFAULT_PINNED_REVISION,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """Full certified adapter entry point: every adapter-safe observation
    for one real competition/season, from already-loaded `MatchBundle`s
    covering the full scope. Despite the historical name (this function
    predates Block 20D.3's generalization and every existing caller still
    gets Premier League 2015/16 behavior by default), it is now the single
    certified season-level entry point for any declared `scope` -- never a
    second, copy-pasted per-scope function. This is the only path that
    correctly computes player_season/goalkeeper_season identities (they
    require every match, not one) -- see `adapt_match_bundle` for the
    single-match subset."""

    if not STATSBOMB_INTERNAL_ONLY:
        raise AssertionError(
            "STATSBOMB_INTERNAL_ONLY was flipped to False without an explicit product/"
            "legal decision -- statsbomb_open adapter refuses to build observations "
            "under that state change unreviewed."
        )

    observations: list[NormalizedObservation] = []
    observations.extend(
        parse_match_observations(
            bundles, source_revision=source_revision, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )
    observations.extend(
        parse_lineup_participation_observations(
            bundles, source_revision=source_revision, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )
    observations.extend(
        parse_player_match_observations(
            bundles, source_revision=source_revision, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )
    observations.extend(
        parse_goalkeeper_observations(
            bundles, source_revision=source_revision, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )
    observations.extend(
        parse_team_match_observations(
            bundles, source_revision=source_revision, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )
    return observations


# ---------------------------------------------------------------------------
# Legacy Coverage Lab generic probe path (Block 14/15) -- NOT the Block 20C
# certified historical adapter above.
#
# `jobs.run_zero_cost_coverage` and `jobs.collect_validation_snapshot` use
# StatsBomb Open Data as a live, *generic* (any competition/season) spot-
# check probe -- Coverage Lab's Bundesliga 2023/24 metric-availability scan
# and Block 16's FIFA World Cup 2022 validation snapshot, both predating and
# entirely independent of Block 20C's pinned, certified Premier League
# 2015/16 evidence pipeline above. Rewriting *their* StatsBomb semantics
# (participation universe, cards, saves, etc.) to the certified rules is out
# of scope for Block 20C.2b -- neither job is part of the certified
# historical/deep evidence path this block targets, and changing their
# behavior would be an unrelated, unscoped change to already-working
# production functionality (`docs/ZERO_COST_COVERAGE.md`).
#
# These functions are kept byte-for-byte equivalent to the pre-Block-20C
# adapter's behavior (including its known, documented limitations -- e.g.
# `_LEGACY_SAVE_GOALKEEPER_TYPE` is still "Shot Saved"-only, and cards still
# come only from `Foul Committed`) so as not to silently change Coverage
# Lab's or the validation snapshot's real output. This is the one deliberate
# exception to "replace old Block-14 semantics" -- see
# `docs/BLOCK20_MULTI_SOURCE.md` Block 20C.2b section for the explicit
# reasoning. All constants/helpers below are prefixed `_LEGACY_`/`_legacy_`
# specifically so they can never be accidentally reused by the certified
# path above.
# ---------------------------------------------------------------------------

from football_intelligence.data_mesh.timeparse import (  # noqa: E402
    parse_utc_timestamp as _legacy_parse_utc_timestamp,
)

_LEGACY_ON_TARGET_SHOT_OUTCOMES = frozenset({"Goal", "Saved"})
_LEGACY_GOAL_SHOT_OUTCOME = "Goal"
_LEGACY_RED_CARD_NAMES = frozenset({"Red Card", "Second Yellow"})
_LEGACY_YELLOW_CARD_NAME = "Yellow Card"
_LEGACY_SAVE_GOALKEEPER_TYPE = "Shot Saved"
_LEGACY_TACKLE_DUEL_TYPE = "Tackle"
_LEGACY_DRIBBLE_COMPLETE_OUTCOME = "Complete"
_LEGACY_SHOT_ASSIST_KIND = "shot_assist"

_LEGACY_COUNT_METRIC_NAMES: tuple[str, ...] = (
    "shots_total",
    "shots_on_target",
    "goals",
    "key_passes",
    "passes_total",
    "passes_accurate",
    "interceptions",
    "clearances",
    "blocks",
    "dribbles_attempted",
    "dribbles_successful",
    "tackles",
    "fouls_committed",
    "fouls_drawn",
    "yellow_cards",
    "red_cards",
    "saves",
    "advanced.xg",
)

_LEGACY_TEAM_ROLLUP_METRICS = frozenset(
    {
        "shots_total",
        "shots_on_target",
        "passes_total",
        "passes_accurate",
        "fouls_committed",
        "yellow_cards",
        "red_cards",
        "saves",
    }
)

_LEGACY_TEAM_METRIC_NAME: dict[str, str] = {
    "fouls_committed": "fouls",
    "saves": "goalkeeper_saves",
}


def find_competition_season(
    payload: Any,
    *,
    competition_name: str,
    season_name: str,
) -> tuple[int, int] | None:
    """Locate (competition_id, season_id) in competitions.json by exact name match."""

    if not isinstance(payload, list):
        return None
    for item in payload:
        if not isinstance(item, dict):
            continue
        if (
            item.get("competition_name") == competition_name
            and item.get("season_name") == season_name
            and item.get("competition_gender") == "male"
        ):
            competition_id = item.get("competition_id")
            season_id = item.get("season_id")
            if isinstance(competition_id, int) and isinstance(season_id, int):
                return competition_id, season_id
    return None


def parse_match_list(
    payload: Any,
    *,
    competition_code: str,
    season_label: str,
    ingestion_run_id: int | None,
    limit: int | None = None,
) -> list[NormalizedObservation]:
    if not isinstance(payload, list):
        return []
    items = payload[:limit] if limit is not None else payload

    observations: list[NormalizedObservation] = []
    competition_name: str | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if competition_name is None:
            name = item.get("competition", {}).get("competition_name")
            if isinstance(name, str) and name.strip():
                competition_name = name.strip()
        observations.extend(
            _legacy_parse_match_summary(
                item,
                competition_code=competition_code,
                season_label=season_label,
                ingestion_run_id=ingestion_run_id,
            )
        )

    if competition_name is not None and items:
        observations.append(
            _observation(
                entity_type="competition",
                entity_source_id=competition_code,
                entity_identity_hints={"name": competition_name},
                metric_name="name",
                value=competition_name,
                observed_at=observations[0].observed_at if observations else _fallback_now(),
                source_reference=f"data/matches/{competition_code}",
                ingestion_run_id=ingestion_run_id,
            )
        )
    return observations


def _legacy_parse_match_summary(
    item: dict[str, Any],
    *,
    competition_code: str,
    season_label: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    match_id = item.get("match_id")
    home_team = item.get("home_team", {}).get("home_team_name")
    away_team = item.get("away_team", {}).get("away_team_name")
    home_score = item.get("home_score")
    away_score = item.get("away_score")
    match_date = item.get("match_date")
    if match_id is None or not isinstance(home_team, str) or not isinstance(away_team, str):
        return []

    observed_at = _legacy_parse_utc_timestamp(f"{match_date}T00:00:00") if match_date else None
    if observed_at is None:
        return []

    reference = f"data/matches/{competition_code}/{season_label}.json"
    identity_hints = {
        "competition_external_id": competition_code,
        "season_label": season_label,
        "home_team_name": home_team,
        "away_team_name": away_team,
        "kickoff_date": observed_at.date().isoformat(),
    }

    observations = [
        _observation(
            entity_type="team",
            entity_source_id=str(item.get("home_team", {}).get("home_team_id", home_team)),
            entity_identity_hints={"name": home_team, "competition_external_id": competition_code},
            metric_name="name",
            value=home_team,
            observed_at=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
        ),
        _observation(
            entity_type="team",
            entity_source_id=str(item.get("away_team", {}).get("away_team_id", away_team)),
            entity_identity_hints={"name": away_team, "competition_external_id": competition_code},
            metric_name="name",
            value=away_team,
            observed_at=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
        ),
        # StatsBomb Open Data only ever publishes completed historical
        # matches -- there is no "scheduled"/"live" state to represent.
        _observation(
            entity_type="match",
            entity_source_id=str(match_id),
            entity_identity_hints=identity_hints,
            metric_name="status",
            value="finished",
            observed_at=observed_at,
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
        ),
    ]
    if isinstance(home_score, int):
        observations.append(
            _observation(
                entity_type="match",
                entity_source_id=str(match_id),
                entity_identity_hints=identity_hints,
                metric_name="home_score",
                value=home_score,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
            )
        )
    if isinstance(away_score, int):
        observations.append(
            _observation(
                entity_type="match",
                entity_source_id=str(match_id),
                entity_identity_hints=identity_hints,
                metric_name="away_score",
                value=away_score,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
            )
        )
    return observations


def parse_match_events(
    payload: Any,
    *,
    match_id: str,
    competition_code: str,
    ingestion_run_id: int | None,
) -> list[NormalizedObservation]:
    """Deep per-player-per-match metrics derived from one match's event log.

    A player only receives a metric observation (including a real `0`) when
    they are known to have appeared in the match (tagged on at least one
    event) -- a player never mentioned in the event log gets no observation
    at all, correctly represented as missing rather than a fabricated zero.

    This is the legacy Coverage Lab generic probe rule (event-tag presence),
    NOT the Block 20C certified lineup-authoritative participation universe
    used by `parse_player_match_observations` above -- see the module
    section header for why this is intentionally preserved as-is.
    """

    if not isinstance(payload, list):
        return []

    reference = f"data/events/{match_id}.json"
    now = _fallback_now()

    player_counts: dict[int, dict[str, int | float]] = defaultdict(lambda: defaultdict(int))
    player_team: dict[int, int] = {}
    player_name: dict[int, str] = {}
    team_name: dict[int, str] = {}
    formation_by_team: dict[int, str] = {}
    lineup_starters: dict[int, set[int]] = defaultdict(set)

    for event in payload:
        if not isinstance(event, dict):
            continue
        _legacy_record_participant(event, player_team, player_name, team_name)
        type_name = event.get("type", {}).get("name")

        if type_name == "Starting XI":
            _legacy_record_starting_xi(
                event, formation_by_team, lineup_starters, player_name, player_team
            )
            continue
        if type_name == "Shot":
            _legacy_count_shot(event, player_counts)
        elif type_name == "Pass":
            _legacy_count_pass(event, player_counts)
        elif type_name == "Interception":
            _legacy_increment(event, player_counts, "interceptions")
        elif type_name == "Clearance":
            _legacy_increment(event, player_counts, "clearances")
        elif type_name == "Block":
            _legacy_increment(event, player_counts, "blocks")
        elif type_name == "Dribble":
            _legacy_count_dribble(event, player_counts)
        elif type_name == "Duel":
            _legacy_count_duel(event, player_counts)
        elif type_name == "Foul Committed":
            _legacy_count_foul_committed(event, player_counts)
        elif type_name == "Foul Won":
            _legacy_increment(event, player_counts, "fouls_drawn")
        elif type_name == "Goal Keeper":
            _legacy_count_goalkeeper(event, player_counts)

    # A player tagged on any event has genuinely "appeared" -- force a real
    # 0 for every count metric they never triggered, so the coverage
    # distinction between "missing" (never appeared) and "a real zero"
    # (appeared, metric simply never happened) holds for every metric, not
    # just the ones a given player happened to record.
    for player_id in player_team:
        counts = player_counts[player_id]
        for metric_name in _LEGACY_COUNT_METRIC_NAMES:
            if metric_name not in counts:
                counts[metric_name] = 0

    observations: list[NormalizedObservation] = []
    team_counts: dict[int, dict[str, int | float]] = defaultdict(lambda: defaultdict(int))

    for player_id, counts in player_counts.items():
        team_id = player_team.get(player_id)
        for metric_name, value in counts.items():
            observations.append(
                _observation(
                    entity_type="player",
                    entity_source_id=f"{match_id}:{player_id}",
                    entity_identity_hints={
                        "name": player_name.get(player_id, ""),
                        "match_external_id": str(match_id),
                        "competition_external_id": competition_code,
                    },
                    metric_name=metric_name,
                    value=value,
                    observed_at=now,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                )
            )
            if team_id is not None and metric_name in _LEGACY_TEAM_ROLLUP_METRICS:
                team_counts[team_id][metric_name] += value

    for team_id, counts in team_counts.items():
        for metric_name, value in counts.items():
            observations.append(
                _observation(
                    entity_type="team",
                    entity_source_id=f"{match_id}:{team_id}",
                    entity_identity_hints={
                        "name": team_name.get(team_id, ""),
                        "match_external_id": str(match_id),
                        "competition_external_id": competition_code,
                    },
                    metric_name=_LEGACY_TEAM_METRIC_NAME.get(metric_name, metric_name),
                    value=value,
                    observed_at=now,
                    source_reference=reference,
                    ingestion_run_id=ingestion_run_id,
                )
            )

    for team_id, formation in formation_by_team.items():
        observations.append(
            _observation(
                entity_type="team",
                entity_source_id=f"{match_id}:{team_id}",
                entity_identity_hints={
                    "name": team_name.get(team_id, ""),
                    "match_external_id": str(match_id),
                    "competition_external_id": competition_code,
                },
                metric_name="formation",
                value=formation,
                observed_at=now,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
            )
        )

    all_starters = {player_id for starters in lineup_starters.values() for player_id in starters}
    for player_id in player_team:
        # Confirmed Starting XI membership is a real True; any other player
        # who is known to have appeared (tagged on an event) is a confirmed
        # substitute, a real False -- never a guess for players we never
        # saw at all.
        started = player_id in all_starters
        observations.append(
            _observation(
                entity_type="player",
                entity_source_id=f"{match_id}:{player_id}",
                entity_identity_hints={
                    "name": player_name.get(player_id, ""),
                    "match_external_id": str(match_id),
                    "competition_external_id": competition_code,
                },
                metric_name="started",
                value=started,
                observed_at=now,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
            )
        )

    return observations


def _legacy_record_participant(
    event: dict[str, Any],
    player_team: dict[int, int],
    player_name: dict[int, str],
    team_name: dict[int, str],
) -> None:
    team = event.get("team")
    if isinstance(team, dict):
        team_id = team.get("id")
        name = team.get("name")
        if isinstance(team_id, int) and isinstance(name, str):
            team_name[team_id] = name
    player = event.get("player")
    if isinstance(player, dict) and isinstance(team, dict):
        player_id = player.get("id")
        name = player.get("name")
        team_id = team.get("id")
        if isinstance(player_id, int) and isinstance(team_id, int):
            player_team[player_id] = team_id
            if isinstance(name, str):
                player_name[player_id] = name


def _legacy_record_starting_xi(
    event: dict[str, Any],
    formation_by_team: dict[int, str],
    lineup_starters: dict[int, set[int]],
    player_name: dict[int, str],
    player_team: dict[int, int],
) -> None:
    team = event.get("team", {})
    team_id = team.get("id")
    tactics = event.get("tactics", {})
    formation_raw = tactics.get("formation")
    if isinstance(team_id, int) and isinstance(formation_raw, int):
        formation_by_team[team_id] = "-".join(str(formation_raw))
    lineup = tactics.get("lineup")
    if isinstance(team_id, int) and isinstance(lineup, list):
        for entry in lineup:
            if not isinstance(entry, dict):
                continue
            player = entry.get("player", {})
            player_id = player.get("id")
            if isinstance(player_id, int):
                lineup_starters[team_id].add(player_id)
                player_team[player_id] = team_id
                name = player.get("name")
                if isinstance(name, str):
                    player_name[player_id] = name


def _legacy_increment(
    event: dict[str, Any],
    counts: dict[int, dict[str, int | float]],
    metric_name: str,
    amount: int = 1,
) -> None:
    player = event.get("player")
    if not isinstance(player, dict):
        return
    player_id = player.get("id")
    if isinstance(player_id, int):
        counts[player_id][metric_name] += amount


def _legacy_count_shot(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    shot = event.get("shot")
    if not isinstance(shot, dict):
        return
    _legacy_increment(event, counts, "shots_total")
    outcome = shot.get("outcome", {}).get("name")
    if outcome in _LEGACY_ON_TARGET_SHOT_OUTCOMES:
        _legacy_increment(event, counts, "shots_on_target")
    if outcome == _LEGACY_GOAL_SHOT_OUTCOME:
        _legacy_increment(event, counts, "goals")
    xg = shot.get("statsbomb_xg")
    if isinstance(xg, int | float):
        player = event.get("player", {})
        player_id = player.get("id")
        if isinstance(player_id, int):
            existing = counts[player_id].get("advanced.xg", 0.0)
            counts[player_id]["advanced.xg"] = round(float(existing) + float(xg), 4)


def _legacy_count_pass(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    pass_block = event.get("pass")
    if not isinstance(pass_block, dict):
        return
    _legacy_increment(event, counts, "passes_total")
    if pass_block.get("outcome") is None:
        _legacy_increment(event, counts, "passes_accurate")
    if pass_block.get(_LEGACY_SHOT_ASSIST_KIND) is True:
        _legacy_increment(event, counts, "key_passes")


def _legacy_count_dribble(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    dribble = event.get("dribble")
    if not isinstance(dribble, dict):
        return
    _legacy_increment(event, counts, "dribbles_attempted")
    if dribble.get("outcome", {}).get("name") == _LEGACY_DRIBBLE_COMPLETE_OUTCOME:
        _legacy_increment(event, counts, "dribbles_successful")


def _legacy_count_duel(event: dict[str, Any], counts: dict[int, dict[str, int | float]]) -> None:
    duel = event.get("duel")
    if not isinstance(duel, dict):
        return
    if duel.get("type", {}).get("name") == _LEGACY_TACKLE_DUEL_TYPE:
        _legacy_increment(event, counts, "tackles")


def _legacy_count_foul_committed(
    event: dict[str, Any], counts: dict[int, dict[str, int | float]]
) -> None:
    _legacy_increment(event, counts, "fouls_committed")
    foul = event.get("foul_committed")
    card_name = foul.get("card", {}).get("name") if isinstance(foul, dict) else None
    if card_name == _LEGACY_YELLOW_CARD_NAME:
        _legacy_increment(event, counts, "yellow_cards")
    elif card_name in _LEGACY_RED_CARD_NAMES:
        _legacy_increment(event, counts, "red_cards")


def _legacy_count_goalkeeper(
    event: dict[str, Any], counts: dict[int, dict[str, int | float]]
) -> None:
    goalkeeper = event.get("goalkeeper")
    if not isinstance(goalkeeper, dict):
        return
    if goalkeeper.get("type", {}).get("name") == _LEGACY_SAVE_GOALKEEPER_TYPE:
        _legacy_increment(event, counts, "saves")
