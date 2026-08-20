"""Wyscout Open Data payload -> NormalizedObservation adapter (Block 20B.2b).

Historical/deep role only (see `docs/BLOCK20_MULTI_SOURCE.md`) -- this
adapter is never a current-season feed. It emits observations **only** for
the 77-identity adapter-safe subset (`adapter_safe_mappings()` in
`providers.wyscout_open_mapping`: the 43 DIRECT + 34 DERIVABLE_READY Metric
Catalog V2 identities Block 20B.2a verified against the real cached ENG_PL
2017/18 source). Every derivation below matches the exact primitive that
module documents; nothing here is guessed from memory or invented beyond
what Block 20B.2a's empirical audit already proved. DERIVABLE_METHODOLOGY_
PENDING, REQUIRES_MODEL, UNSUPPORTED, AMBIGUOUS, and provider-out-of-scope
identities are never emitted -- see `_ADAPTER_SAFE_IDENTITIES`, enforced at
import time.

This module consumes already-loaded payloads (`matches_payload`,
`events_payload`, `players_payload`) -- it performs no HTTP requests, no
Figshare downloads, no database access. Acquisition is the provider
client's job (`providers.wyscout_open.WyscoutOpenDataClient`); this module
only transforms.

**Participation universe** (Block 20B.2a section 7/9's verified rule):
a player only receives a `player_match`/`goalkeeper_match` observation --
including a real `0` -- when the match's own `formation.lineup`/`bench`/
`substitutions` structure confirms they actually took the field (started,
or came on as a substitute). An unused bench player receives no
performance-stat observation at all (not a fabricated zero), though they
still receive a `started=False` participation-type fact, since squad
membership itself is a real, non-missing fact Wyscout does confirm. This is
a stronger aggregation-universe signal than StatsBomb Open Data's adapter
uses (event-tag presence) because Wyscout's roster data is directly
verified, not inferred.

**Goal reconciliation rule** (Block 20B.2a section 8, verified against
match `wyId 2499781`): player-attributed `goals` come from event-tag
attribution (the only source for "who scored"). Team/match score totals
(`goals_for`, `goals_against`, `home_score`, `away_score`) always come from
the native `teamsData[*].score` field, never from summing player-tagged
goal events -- the real source has at least one goal (that match) with no
shot-type event for the scoring team at all.

**Goalkeeper identity**: only `players.json`'s global `role.code2 == "GK"`
is used (never shirt number, event type, listed position, or formation
slot -- none of those exist reliably in the match schema, per Block
20B.2a). `goals_conceded`/`clean_sheets`/`shots_on_target_faced`/
`save_pct` are only emitted for a team-match where *exactly one* GK-role
player participated -- if two GK-role players appear (a mid-match
goalkeeper substitution), attribution would require event-timestamp-level
cross-referencing this block does not implement, so the fact stays
missing rather than guessed.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from football_intelligence.data_mesh.adapters.scope import AdapterScope, ScopeMismatchError
from football_intelligence.data_mesh.models import EntityType, NormalizedObservation, SourceType
from football_intelligence.metric_catalog.types import MetricGranularity
from football_intelligence.providers.wyscout_open_mapping import adapter_safe_mappings
from football_intelligence.providers.wyscout_open_text import repair_wyscout_double_escaped_unicode

SOURCE_CODE = "wyscout-open"
SOURCE_TYPE: SourceType = "objective_structured"
# Bumped from "wyscout-open-v0.1" (Block 20B.2b's original certified
# adapter) in Block 20D.2's review-fix pass: observable emission semantics
# changed materially -- every observation now carries an explicit
# `metric_granularity`, `goalkeeper_match`-granularity `saves` is now
# genuinely emitted (previously declared but never produced), `home_away`
# moved from catalog granularity "match" to "team_match", and identity
# hints were materially enriched (explicit `team_external_id`/`team_name`,
# `player_external_id`/`player_name`, `home_team_*`/`away_team_*`,
# `kickoff_date`). Old and new observations must not share a provenance
# version.
SEMANTIC_VERSION = "wyscout-open-v0.2"
COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2017/18"

# Block 20D.3: the certified adapter's original (and still default) scope,
# unchanged in value from the module constants above -- every existing
# caller that does not pass `scope=` gets byte-for-byte the same ENG_PL
# 2017/18 behavior as before generalization. `provider_competition_id`/
# `provider_season_id` are real, verified against every match record in
# the real cached `matches_England.json` (Block 20D.2).
DEFAULT_SCOPE = AdapterScope(
    canonical_competition_code=COMPETITION_CODE,
    season_label=SEASON_LABEL,
    provider_competition_id=364,
    provider_season_id=181150,
)

# Prepared for Block 20D.3's rich overlap enablement: real, verified
# provider-native ids for Spain/La Liga 2017/18 (`competitionId=795`,
# `seasonId=181144`), discovered live during Block 20D.1's investigation
# and re-verified against the real cached `matches_Spain.json` (380/380
# matches, 20/20 teams, all sharing this exact (competitionId, seasonId)
# pair -- see `jobs/audit_wyscout_adapter.py`'s ESP_LL audit path).
ESP_LL_SCOPE = AdapterScope(
    canonical_competition_code="ESP_LL",
    season_label="2017/18",
    provider_competition_id=795,
    provider_season_id=181144,
)

# Wyscout's own real Figshare file-naming convention keys the country name
# into the filename (`matches_England.json`, `matches_Spain.json`, ...).
# This is a `source_reference` provenance detail specific to this
# provider's real files, not part of the generic `AdapterScope` contract.
_SCOPE_FILE_LABELS: dict[str, str] = {"ENG_PL": "England", "ESP_LL": "Spain"}


def _source_file_label(scope: AdapterScope) -> str:
    label = _SCOPE_FILE_LABELS.get(scope.canonical_competition_code)
    if label is None:
        raise ScopeMismatchError(
            f"no known Wyscout source-file label for {scope.canonical_competition_code!r} -- "
            "add it to _SCOPE_FILE_LABELS before using this scope"
        )
    return label


_SENTINEL_PLAYER_ID = 0

_GOAL_TAG = 101
_ASSIST_TAG = 301
_KEY_PASS_TAG = 302
_HEAD_BODY_TAG = 403
_WON_TAG = 703
_THROUGH_TAG = 901
_INTERCEPTION_TAG = 1401
_RED_CARD_TAG = 1701
_YELLOW_CARD_TAG = 1702
_SECOND_YELLOW_TAG = 1703
_ACCURATE_TAG = 1801
_NOT_ACCURATE_TAG = 1802
_COUNTER_ATTACK_TAG = 1901
_BLOCKED_TAG = 2101

_SHOT_LIKE_KEYS = frozenset(
    {("Shot", "Shot"), ("Free Kick", "Free kick shot"), ("Free Kick", "Penalty")}
)
_PENALTY_KEY = ("Free Kick", "Penalty")
_GROUND_DUEL_SUBTYPES = frozenset(
    {"Ground attacking duel", "Ground defending duel", "Ground loose ball duel"}
)

# Every raw per-player-per-match count this adapter force-zero-fills for a
# confirmed-participating player (mirrors StatsBomb Open Data's adapter
# `_COUNT_METRIC_NAMES` zero-fill philosophy, applied to Wyscout's stronger
# formation-verified participation universe instead of event-tag presence).
_PLAYER_MATCH_COUNT_METRICS: tuple[str, ...] = (
    "touches",
    "passes_total",
    "passes_accurate",
    "assists",
    "key_passes",
    "through_balls",
    "crosses",
    "shots_total",
    "shots_on_target",
    "shots_off_target",
    "blocked_shots",
    "headed_shots",
    "goals",
    "penalty_goals",
    "penalties_attempted",
    "duels_total",
    "duels_won",
    "aerial_duels",
    "aerial_duels_won",
    "ground_duels",
    "ground_duels_won",
    "interceptions",
    "clearances",
    "fouls_committed",
    "yellow_cards",
    "second_yellow_cards",
    "red_cards",
    "saves",
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

# The (metric_name, entity_type) pairs this adapter is allowed to emit --
# every safe catalog identity, projected through entity_type alone (there
# is no distinct "player_match" vs "goalkeeper_match" entity_type; both
# project to entity_type "player", matching how StatsBomb Open Data's
# adapter already emits one "saves" observation that simultaneously
# satisfies both catalog identities). `NormalizedObservation` itself DOES
# fully express catalog granularity via its own `metric_granularity` field
# (Block 20D.2) -- this coarser, entity_type-only check is a secondary,
# defense-in-depth guard kept alongside the exact
# `(metric_name, metric_granularity)` check in `_guard()` below, never a
# substitute for it: any metric_name/entity_type pair not in this set can
# never be safe, catching an internal wiring bug even before the exact
# check runs.
#
# `home_away`'s catalog granularity was corrected from "match" to
# "team_match" (Block 20D.2 review-fix pass): the primitive
# (`teamsData[*].side`) is inherently a per-team-in-this-match fact, and
# "team_match" already projects to entity_type="team" mechanically below --
# no special-case override needed any more (an earlier pass carried one
# here specifically because the catalog was misclassified).
_SAFE_METRIC_ENTITY_PAIRS: frozenset[tuple[str, EntityType]] = frozenset(
    (key, _GRANULARITY_TO_ENTITY_TYPE[granularity]) for key, granularity in _ADAPTER_SAFE_IDENTITIES
)


def _validate_emission_scope(declared: frozenset[tuple[str, str]]) -> None:
    unsafe = declared - _ADAPTER_SAFE_IDENTITIES
    if unsafe:
        raise AssertionError(
            f"wyscout_open adapter declares emission of non-adapter-safe identities: "
            f"{sorted(unsafe)}"
        )


# Every (catalog_key, catalog_granularity) this module actually implements --
# validated to be a subset of `adapter_safe_mappings()` at import time below.
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
        ("matches", "player_season"),
        ("appearances", "player_season"),
        ("starts", "player_season"),
        ("sub_appearances", "player_season"),
        ("touches", "player_match"),
        ("passes_total", "player_match"),
        ("passes_accurate", "player_match"),
        ("pass_completion_pct", "player_match"),
        ("assists", "player_match"),
        ("key_passes", "player_match"),
        ("chances_created", "player_match"),
        ("through_balls", "player_match"),
        ("crosses", "player_match"),
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
        ("duels_total", "player_match"),
        ("duels_won", "player_match"),
        ("duel_win_pct", "player_match"),
        ("aerial_duels", "player_match"),
        ("aerial_duels_won", "player_match"),
        ("aerial_duel_win_pct", "player_match"),
        ("ground_duels", "player_match"),
        ("ground_duels_won", "player_match"),
        ("interceptions", "player_match"),
        ("clearances", "player_match"),
        ("fouls_committed", "player_match"),
        ("yellow_cards", "player_match"),
        ("second_yellow_cards", "player_match"),
        ("red_cards", "player_match"),
        ("saves", "player_match"),
        ("saves", "goalkeeper_match"),
        ("passes", "goalkeeper_match"),
        ("distribution_accuracy_pct", "goalkeeper_match"),
        ("launches", "goalkeeper_match"),
        ("shots_on_target_faced", "goalkeeper_match"),
        ("save_pct", "goalkeeper_match"),
        ("goals_conceded", "goalkeeper_match"),
        ("clean_sheets", "goalkeeper_match"),
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
        ("goalkeeper_saves", "team_match"),
        ("counter_attack_shots", "team_match"),
    }
)

_validate_emission_scope(_EMITTED_IDENTITIES)


class WyscoutObservationConflictError(RuntimeError):
    """Two observations disagreed for the same source/entity/metric identity."""


@dataclass(frozen=True)
class _MatchInfo:
    match_id: int
    kickoff_at: datetime | None
    home_team_id: int | None
    away_team_id: int | None
    home_score: int | None
    away_score: int | None
    status: Any
    gameweek: Any
    venue: Any
    # Provider-native identifiers read directly from this match's own
    # `competitionId`/`seasonId` fields -- verified real values for England
    # 2017/18: competitionId=364, seasonId=181150. Genuinely supplied per
    # match, never the canonical "ENG_PL" code (Block 20D.2 completion pass
    # correction: an earlier pass had put the canonical code itself into
    # `competition_external_id`, which is not a provider-native identifier).
    competition_external_id: str | None
    season_external_id: str | None


@dataclass
class _MatchRoster:
    lineup_by_team: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    bench_by_team: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))
    sub_in_by_team: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))

    def participating_players(self) -> dict[int, int]:
        """playerId -> teamId for every player who actually took the field."""
        result: dict[int, int] = {}
        for team_id, players in self.lineup_by_team.items():
            for player_id in players:
                result[player_id] = team_id
        for team_id, players in self.bench_by_team.items():
            for player_id in players & self.sub_in_by_team.get(team_id, set()):
                result[player_id] = team_id
        return result


def _parse_kickoff(match: dict[str, Any]) -> datetime | None:
    raw = match.get("dateutc")
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        naive = datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=UTC)


def _match_info(match: dict[str, Any]) -> _MatchInfo | None:
    match_id = match.get("wyId")
    teams_data = match.get("teamsData")
    if not isinstance(match_id, int) or not isinstance(teams_data, dict):
        return None
    home_team_id: int | None = None
    away_team_id: int | None = None
    home_score: int | None = None
    away_score: int | None = None
    for raw_team_id, team_entry in teams_data.items():
        if not isinstance(team_entry, dict):
            continue
        try:
            team_id = int(raw_team_id)
        except (TypeError, ValueError):
            continue
        side = team_entry.get("side")
        score = team_entry.get("score")
        if side == "home":
            home_team_id = team_id
            home_score = score if isinstance(score, int) else None
        elif side == "away":
            away_team_id = team_id
            away_score = score if isinstance(score, int) else None
    competition_id = match.get("competitionId")
    season_id = match.get("seasonId")
    return _MatchInfo(
        match_id=match_id,
        kickoff_at=_parse_kickoff(match),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_score=home_score,
        away_score=away_score,
        status=match.get("status"),
        gameweek=match.get("gameweek"),
        venue=match.get("venue"),
        competition_external_id=str(competition_id) if isinstance(competition_id, int) else None,
        season_external_id=str(season_id) if isinstance(season_id, int) else None,
    )


def _as_entry_list(value: Any) -> list[Any]:
    # Real source quirk (Block 20B.1): `formation.substitutions` (and,
    # defensively, other formation fields) can be the literal string "null"
    # instead of an empty list. Any non-list value means "nothing here".
    return value if isinstance(value, list) else []


def _match_roster(match: dict[str, Any]) -> _MatchRoster:
    roster = _MatchRoster()
    teams_data = match.get("teamsData")
    if not isinstance(teams_data, dict):
        return roster
    for raw_team_id, team_entry in teams_data.items():
        if not isinstance(team_entry, dict):
            continue
        try:
            team_id = int(raw_team_id)
        except (TypeError, ValueError):
            continue
        formation = team_entry.get("formation")
        if not isinstance(formation, dict):
            continue
        for entry in _as_entry_list(formation.get("lineup")):
            if isinstance(entry, dict):
                pid = entry.get("playerId")
                if isinstance(pid, int) and pid != _SENTINEL_PLAYER_ID:
                    roster.lineup_by_team[team_id].add(pid)
        for entry in _as_entry_list(formation.get("bench")):
            if isinstance(entry, dict):
                pid = entry.get("playerId")
                if isinstance(pid, int) and pid != _SENTINEL_PLAYER_ID:
                    roster.bench_by_team[team_id].add(pid)
        for entry in _as_entry_list(formation.get("substitutions")):
            if isinstance(entry, dict):
                pin = entry.get("playerIn")
                if isinstance(pin, int) and pin != _SENTINEL_PLAYER_ID:
                    roster.sub_in_by_team[team_id].add(pin)
    return roster


def _team_names_by_id(teams_payload: list[Any] | None) -> dict[int, str]:
    """`wyId -> name` from the official `teams.json` reference file --
    real team names are only available there, never in `matches_England.json`
    itself. Prefers the short `name` field (e.g. "Burnley") over
    `officialName` ("Burnley FC"), matching the short-form convention
    already used elsewhere in this codebase. Applies the verified Wyscout
    double-escaped-Unicode repair (Block 20D.1/20D.2) to whichever field is
    used. `None`/missing stays missing -- never a fabricated name."""

    names: dict[int, str] = {}
    if not teams_payload:
        return names
    for team in teams_payload:
        if not isinstance(team, dict):
            continue
        wy_id = team.get("wyId")
        if not isinstance(wy_id, int):
            continue
        raw_name = team.get("name") or team.get("officialName")
        if isinstance(raw_name, str) and raw_name.strip():
            names[wy_id] = repair_wyscout_double_escaped_unicode(raw_name)
    return names


def _player_names_by_id(players_payload: list[Any]) -> dict[int, str]:
    """`wyId -> shortName` (falling back to "firstName lastName") from the
    official `players.json` reference file. Applies the verified Wyscout
    double-escaped-Unicode repair to whichever field is used."""

    names: dict[int, str] = {}
    for player in players_payload:
        if not isinstance(player, dict):
            continue
        wy_id = player.get("wyId")
        if not isinstance(wy_id, int):
            continue
        short_name = player.get("shortName")
        if isinstance(short_name, str) and short_name.strip():
            names[wy_id] = repair_wyscout_double_escaped_unicode(short_name)
            continue
        first_name = player.get("firstName")
        last_name = player.get("lastName")
        parts = [p for p in (first_name, last_name) if isinstance(p, str) and p.strip()]
        if parts:
            names[wy_id] = repair_wyscout_double_escaped_unicode(" ".join(parts))
    return names


def _goalkeeper_ids(players_payload: list[Any]) -> frozenset[int]:
    ids: set[int] = set()
    for player in players_payload:
        if not isinstance(player, dict):
            continue
        wy_id = player.get("wyId")
        role = player.get("role")
        code2 = role.get("code2") if isinstance(role, dict) else None
        if isinstance(wy_id, int) and code2 == "GK":
            ids.add(wy_id)
    return frozenset(ids)


def _has_tag(event: dict[str, Any], tag_id: int) -> bool:
    return any(t.get("id") == tag_id for t in event.get("tags", []) if isinstance(t, dict))


_ZeroDict = dict[str, int]


def _new_counts() -> _ZeroDict:
    return dict.fromkeys(_PLAYER_MATCH_COUNT_METRICS, 0)


def _accumulate_player_match_events(
    events_payload: list[Any],
) -> tuple[
    dict[tuple[int, int], _ZeroDict],
    dict[tuple[int, int], int],
]:
    """Returns (counts[(match_id, player_id)], launches[(match_id, player_id)])
    purely from the event stream. Team membership for grouping is taken from
    the verified formation roster (`_MatchRoster.participating_players`)
    rather than from event `teamId`, so this accumulator only tracks
    per-player counts."""

    counts: dict[tuple[int, int], _ZeroDict] = {}
    launches: dict[tuple[int, int], int] = defaultdict(int)

    def bump(match_id: int, player_id: int, metric: str, amount: int = 1) -> None:
        key = (match_id, player_id)
        if key not in counts:
            counts[key] = _new_counts()
        counts[key][metric] += amount

    for event in events_payload:
        if not isinstance(event, dict):
            continue
        match_id = event.get("matchId")
        player_id = event.get("playerId")
        if not isinstance(match_id, int):
            continue
        if isinstance(player_id, int) and player_id != _SENTINEL_PLAYER_ID:
            bump(match_id, player_id, "touches")
        else:
            player_id = None

        event_name = event.get("eventName")
        sub_event_name = event.get("subEventName")
        key = (event_name, sub_event_name)

        if player_id is None:
            continue

        if event_name == "Pass":
            bump(match_id, player_id, "passes_total")
            if _has_tag(event, _ACCURATE_TAG):
                bump(match_id, player_id, "passes_accurate")
            if _has_tag(event, _ASSIST_TAG):
                bump(match_id, player_id, "assists")
            if _has_tag(event, _KEY_PASS_TAG):
                bump(match_id, player_id, "key_passes")
            if _has_tag(event, _THROUGH_TAG):
                bump(match_id, player_id, "through_balls")
            if sub_event_name == "Cross":
                bump(match_id, player_id, "crosses")
            if sub_event_name == "Launch":
                launches[(match_id, player_id)] += 1

        if key in _SHOT_LIKE_KEYS:
            bump(match_id, player_id, "shots_total")
            if _has_tag(event, _ACCURATE_TAG):
                bump(match_id, player_id, "shots_on_target")
            if _has_tag(event, _NOT_ACCURATE_TAG):
                bump(match_id, player_id, "shots_off_target")
            if _has_tag(event, _BLOCKED_TAG):
                bump(match_id, player_id, "blocked_shots")
            if _has_tag(event, _HEAD_BODY_TAG):
                bump(match_id, player_id, "headed_shots")
            if _has_tag(event, _GOAL_TAG):
                bump(match_id, player_id, "goals")
            if key == _PENALTY_KEY:
                bump(match_id, player_id, "penalties_attempted")
                if _has_tag(event, _GOAL_TAG):
                    bump(match_id, player_id, "penalty_goals")

        if event_name == "Duel":
            bump(match_id, player_id, "duels_total")
            won = _has_tag(event, _WON_TAG)
            if won:
                bump(match_id, player_id, "duels_won")
            if sub_event_name == "Air duel":
                bump(match_id, player_id, "aerial_duels")
                if won:
                    bump(match_id, player_id, "aerial_duels_won")
            if sub_event_name in _GROUND_DUEL_SUBTYPES:
                bump(match_id, player_id, "ground_duels")
                if won:
                    bump(match_id, player_id, "ground_duels_won")

        if _has_tag(event, _INTERCEPTION_TAG):
            bump(match_id, player_id, "interceptions")

        if event_name == "Others on the ball" and sub_event_name == "Clearance":
            bump(match_id, player_id, "clearances")

        if event_name == "Foul":
            bump(match_id, player_id, "fouls_committed")
            if _has_tag(event, _YELLOW_CARD_TAG):
                bump(match_id, player_id, "yellow_cards")
            is_red = _has_tag(event, _RED_CARD_TAG)
            is_second_yellow = _has_tag(event, _SECOND_YELLOW_TAG)
            if is_second_yellow:
                bump(match_id, player_id, "second_yellow_cards")
            if is_red or is_second_yellow:
                bump(match_id, player_id, "red_cards")

        if event_name == "Save attempt" and _has_tag(event, _ACCURATE_TAG):
            bump(match_id, player_id, "saves")

    return counts, launches


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
    metric_granularity: MetricGranularity,
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


def _fallback_now() -> datetime:
    return datetime.now(UTC)


def _guard(
    entity_type: EntityType, metric_name: str, metric_granularity: MetricGranularity
) -> None:
    # The exact (catalog_key, catalog_granularity) check is authoritative --
    # this is the only check that can distinguish e.g. `saves`/player_match
    # from `saves`/goalkeeper_match, which the entity_type-only check below
    # cannot (both project to entity_type "player"). The entity_type check
    # stays as defense-in-depth: it catches an internal wiring bug where a
    # call site passed a granularity inconsistent with its own entity_type.
    if (metric_name, metric_granularity) not in _ADAPTER_SAFE_IDENTITIES:
        raise WyscoutObservationConflictError(
            f"refusing to build a non-adapter-safe observation: "
            f"metric_name={metric_name!r} metric_granularity={metric_granularity!r}"
        )
    if (metric_name, entity_type) not in _SAFE_METRIC_ENTITY_PAIRS:
        raise WyscoutObservationConflictError(
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
            raise WyscoutObservationConflictError(
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
    """Refuses a match whose own real `competitionId`/`seasonId` does not
    match the declared `AdapterScope` for this run -- e.g. a batch mixing
    ENG_PL and ESP_LL matches, or an ESP_LL run fed an England match.
    Never silently accepted, silently dropped, or attributed to the wrong
    scope (Block 20D.3)."""

    expected_competition_id = str(scope.provider_competition_id)
    if info.competition_external_id != expected_competition_id:
        raise ScopeMismatchError(
            f"match {info.match_id} has competitionId={info.competition_external_id!r}, "
            f"expected {expected_competition_id!r} for scope "
            f"{scope.canonical_competition_code}/{scope.season_label} -- refusing to emit "
            "observations for a match outside the declared scope"
        )
    if scope.provider_season_id is not None:
        expected_season_id = str(scope.provider_season_id)
        if info.season_external_id != expected_season_id:
            raise ScopeMismatchError(
                f"match {info.match_id} has seasonId={info.season_external_id!r}, expected "
                f"{expected_season_id!r} for scope {scope.canonical_competition_code}/"
                f"{scope.season_label} -- refusing to emit observations for a match outside "
                "the declared scope"
            )


def _scope_hints(info: _MatchInfo | None, scope: AdapterScope) -> dict[str, str]:
    """Provider-native competition identity + this run's declared season
    label. `competition_external_id` is the source's own numeric
    `competitionId`, never a canonical code -- only populated when this
    specific match genuinely carries it. `info=None` (season-aggregate call
    sites with no single match in scope) omits `competition_external_id`
    rather than guessing."""

    hints: dict[str, str] = {"season_label": scope.season_label}
    if info is not None and info.competition_external_id is not None:
        hints["competition_external_id"] = info.competition_external_id
    return hints


def _match_hints(
    info: _MatchInfo, team_names: Mapping[int, str], scope: AdapterScope
) -> dict[str, str]:
    """Identity hints for a match-granularity observation: provider-native
    match id, home/away team ids and names when the source supplies them
    (via the separate `teams.json` reference), and the raw per-observation
    kickoff date.

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
        home_name = team_names.get(info.home_team_id)
        if home_name:
            hints["home_team_name"] = home_name
    if info.away_team_id is not None:
        hints["away_team_external_id"] = str(info.away_team_id)
        away_name = team_names.get(info.away_team_id)
        if away_name:
            hints["away_team_name"] = away_name
    if info.kickoff_at is not None:
        hints["kickoff_date"] = info.kickoff_at.date().isoformat()
    return hints


def _team_scoped_hints(
    info: _MatchInfo, team_id: int, team_names: Mapping[int, str], scope: AdapterScope
) -> dict[str, str]:
    """Identity hints for a team_match-granularity (or per-team `home_away`)
    observation: the match it belongs to, plus this specific team's own
    provider-native id and name."""

    hints = _scope_hints(info, scope)
    hints["match_external_id"] = str(info.match_id)
    hints["team_external_id"] = str(team_id)
    name = team_names.get(team_id)
    if name:
        hints["team_name"] = name
    return hints


def _player_scoped_hints(
    info: _MatchInfo,
    roster: _MatchRoster,
    player_id: int,
    player_names: Mapping[int, str],
    scope: AdapterScope,
) -> dict[str, str]:
    """Identity hints for a player_appearance/player_match/goalkeeper_match
    observation: the match, this player's own provider-native id and name
    (from the separate `players.json` reference), and the team they played
    for in this match when the roster resolves it."""

    hints = _scope_hints(info, scope)
    hints["match_external_id"] = str(info.match_id)
    hints["player_external_id"] = str(player_id)
    name = player_names.get(player_id)
    if name:
        hints["player_name"] = name
    team_id = roster.participating_players().get(player_id)
    if team_id is not None:
        hints["team_external_id"] = str(team_id)
    return hints


def _player_season_hints(
    season_scope_hints: dict[str, str] | None,
    player_names: Mapping[int, str],
    player_id: int,
    scope: AdapterScope,
) -> dict[str, str]:
    """Identity hints for a player_season/goalkeeper_season observation:
    competition/season scope (captured once from the first match seen)
    plus this player's own provider-native id and name -- never a per-match
    team, since a season fact is not scoped to one match."""

    hints: dict[str, str] = (
        dict(season_scope_hints) if season_scope_hints else {"season_label": scope.season_label}
    )
    hints["player_external_id"] = str(player_id)
    name = player_names.get(player_id)
    if name:
        hints["player_name"] = name
    return hints


def parse_match_observations(
    matches_payload: list[Any],
    teams_payload: list[Any] | None = None,
    *,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """The 6 DIRECT `match`-granularity identities, plus `home_away`
    (`team_match`-granularity, corrected Block 20D.2 review-fix pass --
    inherently per-team-in-this-match, not a single match-wide value).
    `teams_payload` (the official `teams.json` reference file) is optional
    -- when supplied,
    match/team-scoped observations carry real `home_team_name`/
    `away_team_name`/`team_name` identity hints; when omitted, only the
    provider-native team ids are populated (missing stays missing, never a
    fabricated name). `scope` (Block 20D.3) declares which real
    competition/season this payload is expected to cover -- defaults to
    the original certified ENG_PL 2017/18 scope for full backward
    compatibility; any match whose own native `competitionId`/`seasonId`
    disagrees is refused (`ScopeMismatchError`), never silently accepted
    or silently misattributed."""

    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}
    team_names = _team_names_by_id(teams_payload)
    reference = f"wyscout/matches_{_source_file_label(scope)}.json"

    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        info = _match_info(match)
        if info is None:
            continue
        _validate_scope(info, scope)
        observed_at = info.kickoff_at or _fallback_now()
        entity_source_id = str(info.match_id)
        hints = _match_hints(info, team_names, scope)

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
        if isinstance(info.gameweek, int):
            _emit(
                observations,
                seen,
                entity_type="match",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="round_name",
                value=str(info.gameweek),
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="match",
            )
        if isinstance(info.venue, str) and info.venue.strip():
            _emit(
                observations,
                seen,
                entity_type="match",
                entity_source_id=entity_source_id,
                entity_identity_hints=hints,
                metric_name="venue_name",
                value=info.venue,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="match",
            )

        # `home_away` (catalog granularity "team_match", corrected Block
        # 20D.2 review-fix pass) is, by its own bare description ("Home /
        # Away") and verified primitive (`teamsData[*].side`), inherently a
        # per-team-in-this-match fact, not a single match-wide value -- it
        # is emitted per team the same way every other team-match-scoped
        # fact in this codebase already is
        # (`entity_source_id=f"{match_id}:{team_id}"`).
        for team_id, side in ((info.home_team_id, "home"), (info.away_team_id, "away")):
            if team_id is None:
                continue
            _emit(
                observations,
                seen,
                entity_type="team",
                entity_source_id=f"{info.match_id}:{team_id}",
                entity_identity_hints=_team_scoped_hints(info, team_id, team_names, scope),
                metric_name="home_away",
                value=side,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="team_match",
            )

    return observations


def parse_participation_observations(
    matches_payload: list[Any],
    players_payload: list[Any] | None = None,
    *,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """`started` (player_appearance) + `matches`/`appearances`/`starts`/
    `sub_appearances` (player_season). `minutes`/`minutes_per_appearance`
    are DERIVABLE_METHODOLOGY_PENDING and are never implemented here.
    `players_payload` (the official `players.json` reference file) is
    optional -- when supplied, hints carry real `player_name` identity;
    when omitted, only the provider-native player id is populated. `scope`
    (Block 20D.3): see `parse_match_observations`."""

    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}
    player_names = _player_names_by_id(players_payload or [])
    reference = f"wyscout/matches_{_source_file_label(scope)}.json"

    season_matches: dict[int, int] = defaultdict(int)
    season_starts: dict[int, int] = defaultdict(int)
    season_appearances: dict[int, int] = defaultdict(int)
    latest_contributing_date: dict[int, datetime] = {}
    season_scope_hints: dict[str, str] | None = None

    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        info = _match_info(match)
        if info is None:
            continue
        _validate_scope(info, scope)
        roster = _match_roster(match)
        observed_at = info.kickoff_at or _fallback_now()
        if season_scope_hints is None:
            season_scope_hints = _scope_hints(info, scope)

        started_ids: set[int] = set()
        for players in roster.lineup_by_team.values():
            started_ids |= players
        squad_ids = set(started_ids)
        for players in roster.bench_by_team.values():
            squad_ids |= players
        squad_team_of: dict[int, int] = {}
        for team_id, players in roster.lineup_by_team.items():
            for player_id in players:
                squad_team_of[player_id] = team_id
        for team_id, players in roster.bench_by_team.items():
            for player_id in players:
                squad_team_of.setdefault(player_id, team_id)

        for player_id in squad_ids:
            hints = _player_scoped_hints(info, roster, player_id, player_names, scope)
            squad_team_id = squad_team_of.get(player_id)
            if squad_team_id is not None:
                hints.setdefault("team_external_id", str(squad_team_id))
            _emit(
                observations,
                seen,
                entity_type="player",
                entity_source_id=f"{info.match_id}:{player_id}",
                entity_identity_hints=hints,
                metric_name="started",
                value=player_id in started_ids,
                observed_at=observed_at,
                source_reference=reference,
                ingestion_run_id=ingestion_run_id,
                metric_granularity="player_appearance",
            )
            season_matches[player_id] += 1
            if info.kickoff_at is not None and info.kickoff_at > latest_contributing_date.get(
                player_id, datetime.min.replace(tzinfo=UTC)
            ):
                latest_contributing_date[player_id] = info.kickoff_at

        participating = roster.participating_players()
        for player_id in participating:
            season_appearances[player_id] += 1
            if player_id in started_ids:
                season_starts[player_id] += 1

    for player_id, matches_count in season_matches.items():
        entity_source_id = str(player_id)
        observed_at = latest_contributing_date.get(player_id, _fallback_now())
        season_hints = _player_season_hints(season_scope_hints, player_names, player_id, scope)
        _emit(
            observations,
            seen,
            entity_type="player",
            entity_source_id=entity_source_id,
            entity_identity_hints=season_hints,
            metric_name="matches",
            value=matches_count,
            observed_at=observed_at,
            source_reference=reference,
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
            source_reference=reference,
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
            source_reference=reference,
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
            source_reference=reference,
            ingestion_run_id=ingestion_run_id,
            metric_granularity="player_season",
        )

    return observations


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

    for metric_name in _PLAYER_MATCH_COUNT_METRICS:
        emit(metric_name, counts[metric_name])

    goals = counts["goals"]
    assists = counts["assists"]
    penalty_goals = counts["penalty_goals"]
    penalties_attempted = counts["penalties_attempted"]
    shots_total = counts["shots_total"]
    shots_on_target = counts["shots_on_target"]
    passes_total = counts["passes_total"]
    passes_accurate = counts["passes_accurate"]
    duels_total = counts["duels_total"]
    duels_won = counts["duels_won"]
    aerial_duels = counts["aerial_duels"]
    aerial_duels_won = counts["aerial_duels_won"]
    key_passes = counts["key_passes"]

    emit("goal_contributions", goals + assists)
    emit("non_penalty_goals", goals - penalty_goals)
    emit("penalties_missed", penalties_attempted - penalty_goals)
    emit("chances_created", key_passes + assists)

    if shots_total > 0:
        emit("shots_on_target_pct", round(100.0 * shots_on_target / shots_total, 4))
        emit("goals_per_shot", round(goals / shots_total, 4))
    if shots_on_target > 0:
        emit("goals_per_shot_on_target", round(goals / shots_on_target, 4))
    if passes_total > 0:
        emit("pass_completion_pct", round(100.0 * passes_accurate / passes_total, 4))
    if duels_total > 0:
        emit("duel_win_pct", round(100.0 * duels_won / duels_total, 4))
    if aerial_duels > 0:
        emit("aerial_duel_win_pct", round(100.0 * aerial_duels_won / aerial_duels, 4))


def parse_player_match_observations(
    matches_payload: list[Any],
    events_payload: list[Any],
    players_payload: list[Any] | None = None,
    *,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """The 38 player_match identities in the adapter-safe subset.
    `players_payload` (the official `players.json` reference file) is
    optional -- when supplied, hints carry real `player_name` identity.
    `scope` (Block 20D.3): see `parse_match_observations`."""

    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}
    player_names = _player_names_by_id(players_payload or [])

    counts_by_match_player, _launches = _accumulate_player_match_events(events_payload)

    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        info = _match_info(match)
        if info is None:
            continue
        _validate_scope(info, scope)
        roster = _match_roster(match)
        observed_at = info.kickoff_at or _fallback_now()
        reference = f"wyscout/events_{_source_file_label(scope)}.json#match={info.match_id}"

        for player_id in roster.participating_players():
            counts = counts_by_match_player.get((info.match_id, player_id), _new_counts())
            hints = _player_scoped_hints(info, roster, player_id, player_names, scope)
            _emit_player_match_metrics(
                observations,
                seen,
                match_id=info.match_id,
                player_id=player_id,
                counts=counts,
                observed_at=observed_at,
                reference=reference,
                hints=hints,
                ingestion_run_id=ingestion_run_id,
            )

    return observations


def parse_goalkeeper_observations(
    matches_payload: list[Any],
    events_payload: list[Any],
    players_payload: list[Any],
    *,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """The 8 goalkeeper_match + 2 goalkeeper_season identities. `scope`
    (Block 20D.3): see `parse_match_observations`."""

    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}

    goalkeeper_ids = _goalkeeper_ids(players_payload)
    player_names = _player_names_by_id(players_payload)
    counts_by_match_player, launches_by_match_player = _accumulate_player_match_events(
        events_payload
    )
    team_shots_on_target = _team_match_shots_on_target(matches_payload, events_payload)

    season_saves: dict[int, int] = defaultdict(int)
    season_shots_faced: dict[int, int] = defaultdict(int)
    season_clean_sheets: dict[int, int] = defaultdict(int)
    season_matches_resolved: dict[int, int] = defaultdict(int)
    latest_date: dict[int, datetime] = {}
    season_scope_hints: dict[str, str] | None = None

    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        info = _match_info(match)
        if info is None:
            continue
        _validate_scope(info, scope)
        roster = _match_roster(match)
        observed_at = info.kickoff_at or _fallback_now()
        reference = f"wyscout/events_{_source_file_label(scope)}.json#match={info.match_id}"
        if season_scope_hints is None:
            season_scope_hints = _scope_hints(info, scope)
        participating = roster.participating_players()

        team_goalkeepers: dict[int, list[int]] = defaultdict(list)
        for player_id, team_id in participating.items():
            if player_id in goalkeeper_ids:
                team_goalkeepers[team_id].append(player_id)

        for player_id, team_id in participating.items():
            if player_id not in goalkeeper_ids:
                continue
            entity_source_id = f"{info.match_id}:{player_id}"
            hints = _player_scoped_hints(info, roster, player_id, player_names, scope)
            counts = counts_by_match_player.get((info.match_id, player_id), _new_counts())

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

            emit("passes", counts["passes_total"])
            if counts["passes_total"] > 0:
                emit(
                    "distribution_accuracy_pct",
                    round(100.0 * counts["passes_accurate"] / counts["passes_total"], 4),
                )
            launches = launches_by_match_player.get((info.match_id, player_id), 0)
            emit("launches", launches)
            # Same real event-derived count `_emit_player_match_metrics` already
            # emits at `player_match` granularity -- genuinely two distinct
            # catalog identities (Block 20D.2's canonical example of why
            # `metric_granularity` exists), not a duplicate. `_emit`'s
            # (metric_name, metric_granularity)-inclusive dedup identity keeps
            # these two facts from ever being treated as conflicting or merged.
            emit("saves", counts["saves"])

            # Only attribute team-level goalkeeping outcomes when exactly one
            # GK-role player took the field for this team in this match --
            # otherwise a mid-match goalkeeper substitution would need
            # event-timestamp attribution this block does not implement.
            if len(team_goalkeepers.get(team_id, [])) != 1:
                continue
            opponent_team_id = (
                info.away_team_id if team_id == info.home_team_id else info.home_team_id
            )
            goals_against = info.away_score if team_id == info.home_team_id else info.home_score
            if goals_against is None:
                continue
            emit("goals_conceded", goals_against)
            emit("clean_sheets", goals_against == 0)

            season_saves[player_id] += counts["saves"]
            season_matches_resolved[player_id] += 1
            if goals_against == 0:
                season_clean_sheets[player_id] += 1
            if info.kickoff_at is not None:
                latest_date[player_id] = info.kickoff_at

            if opponent_team_id is None:
                continue
            shots_faced = team_shots_on_target.get((info.match_id, opponent_team_id))
            if shots_faced is None:
                continue
            emit("shots_on_target_faced", shots_faced)
            season_shots_faced[player_id] += shots_faced
            if shots_faced > 0:
                emit("save_pct", round(100.0 * counts["saves"] / shots_faced, 4))

    for player_id, matches_resolved in season_matches_resolved.items():
        if matches_resolved == 0:
            continue
        observed_at = latest_date.get(player_id, _fallback_now())
        season_reference = (
            f"wyscout/matches_{_source_file_label(scope)}.json+"
            f"events_{_source_file_label(scope)}.json"
        )
        entity_source_id = str(player_id)
        season_hints = _player_season_hints(season_scope_hints, player_names, player_id, scope)
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


def _team_match_shots_on_target(
    matches_payload: list[Any],
    events_payload: list[Any],
) -> dict[tuple[int, int], int]:
    result: dict[tuple[int, int], int] = defaultdict(int)
    for event in events_payload:
        if not isinstance(event, dict):
            continue
        match_id = event.get("matchId")
        team_id = event.get("teamId")
        if not isinstance(match_id, int) or not isinstance(team_id, int):
            continue
        key_pair = (event.get("eventName"), event.get("subEventName"))
        if key_pair in _SHOT_LIKE_KEYS and _has_tag(event, _ACCURATE_TAG):
            result[(match_id, team_id)] += 1
    return result


@dataclass
class _TeamMatchCounts:
    shots_total: int = 0
    shots_on_target: int = 0
    blocked_shots: int = 0
    passes_total: int = 0
    passes_accurate: int = 0
    fouls: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    corners: int = 0
    offsides: int = 0
    counter_attack_shots: int = 0


def parse_team_match_observations(
    matches_payload: list[Any],
    events_payload: list[Any],
    players_payload: list[Any],
    teams_payload: list[Any] | None = None,
    *,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """The 17 team_match identities in the adapter-safe subset.
    `teams_payload` (the official `teams.json` reference file) is optional
    -- when supplied, hints carry a real `team_name` identity. `scope`
    (Block 20D.3): see `parse_match_observations`."""

    observations: list[NormalizedObservation] = []
    seen: dict[tuple[str, EntityType, str, str, MetricGranularity], Any] = {}

    goalkeeper_ids = _goalkeeper_ids(players_payload)
    team_names = _team_names_by_id(teams_payload)
    counts_by_match_player, _launches = _accumulate_player_match_events(events_payload)

    team_counts: dict[tuple[int, int], _TeamMatchCounts] = defaultdict(_TeamMatchCounts)
    for event in events_payload:
        if not isinstance(event, dict):
            continue
        match_id = event.get("matchId")
        team_id = event.get("teamId")
        if not isinstance(match_id, int) or not isinstance(team_id, int):
            continue
        key_pair = (event.get("eventName"), event.get("subEventName"))
        event_name = event.get("eventName")
        sub_event_name = event.get("subEventName")
        stats = team_counts[(match_id, team_id)]

        if key_pair in _SHOT_LIKE_KEYS:
            stats.shots_total += 1
            if _has_tag(event, _ACCURATE_TAG):
                stats.shots_on_target += 1
            if _has_tag(event, _BLOCKED_TAG):
                stats.blocked_shots += 1
            if _has_tag(event, _COUNTER_ATTACK_TAG):
                stats.counter_attack_shots += 1
        if event_name == "Pass":
            stats.passes_total += 1
            if _has_tag(event, _ACCURATE_TAG):
                stats.passes_accurate += 1
        if event_name == "Foul":
            stats.fouls += 1
            if _has_tag(event, _YELLOW_CARD_TAG):
                stats.yellow_cards += 1
            if _has_tag(event, _RED_CARD_TAG) or _has_tag(event, _SECOND_YELLOW_TAG):
                stats.red_cards += 1
        if event_name == "Free Kick" and sub_event_name == "Corner":
            stats.corners += 1
        if event_name == "Offside":
            stats.offsides += 1

    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        info = _match_info(match)
        if info is None:
            continue
        _validate_scope(info, scope)
        if info.home_team_id is None or info.away_team_id is None:
            continue
        roster = _match_roster(match)
        observed_at = info.kickoff_at or _fallback_now()
        reference = f"wyscout/events_{_source_file_label(scope)}.json#match={info.match_id}"
        participating = roster.participating_players()

        for team_id, opponent_id, own_score, opp_score in (
            (info.home_team_id, info.away_team_id, info.home_score, info.away_score),
            (info.away_team_id, info.home_team_id, info.away_score, info.home_score),
        ):
            entity_source_id = f"{info.match_id}:{team_id}"
            hints = _team_scoped_hints(info, team_id, team_names, scope)
            stats = team_counts.get((info.match_id, team_id), _TeamMatchCounts())
            opp_stats = team_counts.get((info.match_id, opponent_id), _TeamMatchCounts())

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
            emit("yellow_cards", stats.yellow_cards)
            emit("red_cards", stats.red_cards)
            emit("counter_attack_shots", stats.counter_attack_shots)

            goalkeeper_saves = 0
            for player_id, player_team_id in participating.items():
                if player_team_id == team_id and player_id in goalkeeper_ids:
                    goalkeeper_saves += counts_by_match_player.get(
                        (info.match_id, player_id), _new_counts()
                    )["saves"]
            emit("goalkeeper_saves", goalkeeper_saves)

    return observations


def parse_england_season(
    *,
    matches_payload: list[Any],
    events_payload: list[Any],
    players_payload: list[Any],
    teams_payload: list[Any] | None = None,
    scope: AdapterScope = DEFAULT_SCOPE,
    ingestion_run_id: int | None = None,
) -> list[NormalizedObservation]:
    """Full certified adapter entry point: every adapter-safe observation
    for one real competition/season, from already-loaded payloads. Despite
    the historical name (this function predates Block 20D.3's
    generalization and every existing caller still gets ENG_PL 2017/18
    behavior by default), it is now the single certified entry point for
    any declared `scope` -- never a second, copy-pasted per-scope function.
    `teams_payload` (the official `teams.json` reference file) is optional
    -- when supplied, match/team-scoped hints carry real team names."""

    observations: list[NormalizedObservation] = []
    observations.extend(
        parse_match_observations(
            matches_payload, teams_payload, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )
    observations.extend(
        parse_participation_observations(
            matches_payload, players_payload, scope=scope, ingestion_run_id=ingestion_run_id
        )
    )
    observations.extend(
        parse_player_match_observations(
            matches_payload,
            events_payload,
            players_payload,
            scope=scope,
            ingestion_run_id=ingestion_run_id,
        )
    )
    observations.extend(
        parse_goalkeeper_observations(
            matches_payload,
            events_payload,
            players_payload,
            scope=scope,
            ingestion_run_id=ingestion_run_id,
        )
    )
    observations.extend(
        parse_team_match_observations(
            matches_payload,
            events_payload,
            players_payload,
            teams_payload,
            scope=scope,
            ingestion_run_id=ingestion_run_id,
        )
    )
    return observations
