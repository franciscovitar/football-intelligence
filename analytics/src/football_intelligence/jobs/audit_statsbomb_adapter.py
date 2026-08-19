"""Block 20C.2b audit: run the certified StatsBomb Open adapter against the
real, already-cached, pinned Premier League 2015/16 source and report on
the resulting `NormalizedObservation` rows.

Local-only: reads files already cached by `jobs.fetch_statsbomb_open`
(`data/cache/statsbomb-open/<pinned_sha>/`), performs **zero network
requests** (unlike `jobs.audit_statsbomb_mapping`, which is cache-aware and
will fetch a missing file -- this job fails loudly instead if anything is
missing, since the full season must already be cached before an adapter
audit is meaningful), never connects to PostgreSQL, and never writes
canonical evidence. It exists to prove the adapter
(`data_mesh.adapters.statsbomb_open`) only ever emits adapter-safe
identities and produces internally consistent, source-faithful output
against the real full 380-match dataset before any canonical ingestion is
implemented.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.statsbomb_open import (
    _EMITTED_IDENTITIES,
    _SAFE_METRIC_ENTITY_PAIRS,
    COMPETITION_CODE,
    SEASON_LABEL,
    SOURCE_CODE,
    MatchBundle,
    StatsBombObservationConflictError,
    parse_lineups,
    parse_premier_league_season,
)
from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.providers.statsbomb_open import DEFAULT_PINNED_REVISION
from football_intelligence.providers.statsbomb_open_mapping import adapter_safe_mappings
from football_intelligence.providers.statsbomb_open_policy import STATSBOMB_INTERNAL_ONLY

DEFAULT_CACHE_ROOT = Path("data/cache/statsbomb-open")
COMPETITION_ID = 2
SEASON_ID = 27

_EXPECTED_MATCH_COUNT = 380
_EXPECTED_TEAM_COUNT = 20
_EXPECTED_NATIVE_GOAL_TOTAL = 1026
_EXPECTED_SHOOTER_GOAL_TOTAL = 988
_EXPECTED_OWN_GOAL_TOTAL = 38
_EXPECTED_ASSISTS_TOTAL = 669
_EXPECTED_LINEUP_YELLOW = 1203
_EXPECTED_LINEUP_RED = 34
_EXPECTED_LINEUP_SECOND_YELLOW = 25
_EXPECTED_FOUL_COMMITTED_ONLY_YELLOW = 1015  # what the old, incomplete rule would total
_EXPECTED_SAVES_FULL_TYPE_SET = 2277
_EXPECTED_SAVES_OLD_RULE_ONLY = 2194  # "Shot Saved" only -- the old adapter's undercount


class StatsBombAdapterAuditError(RuntimeError):
    """The adapter audit could not run against the currently cached local files."""


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class AdapterAuditReport:
    total_observations: int
    by_entity_type: dict[str, int]
    by_metric_name: dict[str, int]
    distinct_matches: int
    distinct_teams: int
    distinct_squad_players: int
    distinct_participating_players: int
    distinct_goalkeepers: int
    duplicate_identical_count: int
    duplicate_conflict_count: int
    safe_identity_count: int
    implemented_identity_count: int
    identities_with_observations: int
    safe_identities_with_zero_observations: tuple[tuple[str, str], ...]
    # (metric_name, entity_type) pairs outside `_SAFE_METRIC_ENTITY_PAIRS` --
    # a coarser, defense-in-depth signal kept alongside
    # `unexpected_exact_identities` below, never a substitute for it (an
    # entity_type pair can be valid while the exact granularity is not,
    # e.g. saves/player_season still has entity_type="player").
    unexpected_identities: tuple[tuple[str, str], ...]
    # (metric_name, metric_granularity) pairs observed but absent from the
    # real Metric Catalog adapter-safe set -- the authoritative unexpected-
    # output check (Block 20D.2 review-fix pass).
    unexpected_exact_identities: tuple[tuple[str, str], ...]
    checks: tuple[VerificationCheck, ...]

    @property
    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)


def _revision_dir(cache_root: Path, source_revision: str) -> Path:
    return cache_root / source_revision


def _load_json_local_only(path: Path) -> Any:
    if not path.exists():
        raise StatsBombAdapterAuditError(
            f"required cached file missing: {path} -- run "
            "football-intelligence-fetch-statsbomb-open first (this audit performs no "
            "network requests of its own)"
        )
    with path.open("rb") as handle:
        return json.load(handle)


def load_full_season_bundles(
    cache_root: Path, *, source_revision: str = DEFAULT_PINNED_REVISION
) -> list[MatchBundle]:
    """Loads every one of the 380 real Premier League 2015/16 matches'
    already-cached summary + events + lineups payloads. Zero network calls;
    fails loudly if the pinned local snapshot is incomplete."""

    revision_dir = _revision_dir(cache_root, source_revision)
    matches_payload = _load_json_local_only(
        revision_dir / f"matches/{COMPETITION_ID}/{SEASON_ID}.json"
    )
    if not isinstance(matches_payload, list):
        raise StatsBombAdapterAuditError("cached match list payload is structurally unusable")

    bundles: list[MatchBundle] = []
    for item in matches_payload:
        if not isinstance(item, dict):
            continue
        match_id = item.get("match_id")
        if not isinstance(match_id, int):
            continue
        events_payload = _load_json_local_only(revision_dir / f"events/{match_id}.json")
        lineups_payload = _load_json_local_only(revision_dir / f"lineups/{match_id}.json")
        bundles.append(
            MatchBundle(
                match_id=match_id,
                match_summary=item,
                events_payload=events_payload,
                lineups_payload=lineups_payload,
            )
        )
    return bundles


def run_adapter(
    cache_root: Path, *, source_revision: str = DEFAULT_PINNED_REVISION
) -> list[NormalizedObservation]:
    bundles = load_full_season_bundles(cache_root, source_revision=source_revision)
    try:
        return parse_premier_league_season(bundles, source_revision=source_revision)
    except StatsBombObservationConflictError as exc:
        raise StatsBombAdapterAuditError(
            f"adapter refused conflicting/unsafe observations: {exc}"
        ) from exc


def _independent_source_facts(bundles: list[MatchBundle]) -> dict[str, int]:
    """Re-derives the same regression facts `jobs.audit_statsbomb_mapping`
    verifies, directly from the raw cached payloads -- independent of
    whatever the adapter itself computes, so the acceptance invariants
    below are a real cross-check, not a tautology."""

    native_score_sum = 0
    shooter_goals = 0
    own_goal_for = 0
    assists = 0
    lineup_yellow = 0
    lineup_red = 0
    lineup_second_yellow = 0
    foul_committed_only_yellow = 0
    bad_behaviour_yellow = 0
    saves_full_type_set = 0
    saves_old_rule_only = 0

    old_rule_save_type = "Shot Saved"
    full_save_types = {
        "Shot Saved",
        "Shot Saved Off Target",
        "Shot Saved to Post",
        "Penalty Saved",
        "Penalty Saved to Post",
    }

    for bundle in bundles:
        native_score_sum += (bundle.match_summary.get("home_score") or 0) + (
            bundle.match_summary.get("away_score") or 0
        )
        for event in bundle.events_payload:
            if not isinstance(event, dict):
                continue
            type_name = event.get("type", {}).get("name")
            if (
                type_name == "Shot"
                and event.get("shot", {}).get("outcome", {}).get("name") == "Goal"
            ):
                shooter_goals += 1
            elif type_name == "Own Goal For":
                own_goal_for += 1
            elif type_name == "Pass" and event.get("pass", {}).get("goal_assist") is True:
                assists += 1
            elif type_name == "Foul Committed":
                card_name = event.get("foul_committed", {}).get("card", {}).get("name")
                if card_name == "Yellow Card":
                    foul_committed_only_yellow += 1
            elif type_name == "Bad Behaviour":
                card_name = event.get("bad_behaviour", {}).get("card", {}).get("name")
                if card_name == "Yellow Card":
                    bad_behaviour_yellow += 1
            elif type_name == "Goal Keeper":
                gk_type = event.get("goalkeeper", {}).get("type", {}).get("name")
                if gk_type in full_save_types:
                    saves_full_type_set += 1
                if gk_type == old_rule_save_type:
                    saves_old_rule_only += 1

        for team in bundle.lineups_payload:
            if not isinstance(team, dict):
                continue
            for player in team.get("lineup", []):
                if not isinstance(player, dict):
                    continue
                for card in player.get("cards", []):
                    if not isinstance(card, dict):
                        continue
                    card_type = card.get("card_type")
                    if card_type == "Yellow Card":
                        lineup_yellow += 1
                    elif card_type == "Red Card":
                        lineup_red += 1
                    elif card_type == "Second Yellow":
                        lineup_second_yellow += 1

    return {
        "native_score_sum": native_score_sum,
        "shooter_goals": shooter_goals,
        "own_goal_for": own_goal_for,
        "assists": assists,
        "lineup_yellow": lineup_yellow,
        "lineup_red": lineup_red,
        "lineup_second_yellow": lineup_second_yellow,
        "foul_committed_only_yellow": foul_committed_only_yellow,
        "bad_behaviour_yellow": bad_behaviour_yellow,
        "saves_full_type_set": saves_full_type_set,
        "saves_old_rule_only": saves_old_rule_only,
    }


def _check(name: str, passed: bool, detail: str) -> VerificationCheck:
    return VerificationCheck(name=name, passed=passed, detail=detail)


def _entity_source_id_is_match_scoped(entity_source_id: str) -> bool:
    return ":" in entity_source_id


def _numeric_suffix(entity_source_id: str) -> str:
    return entity_source_id.rsplit(":", maxsplit=1)[-1]


def build_report(
    observations: list[NormalizedObservation], bundles: list[MatchBundle]
) -> AdapterAuditReport:
    by_entity_type: Counter[str] = Counter()
    by_metric_name: Counter[str] = Counter()
    matches_seen: set[str] = set()
    teams_seen: set[str] = set()
    players_seen: set[str] = set()

    # Block 20D.2 review-fix pass: identity keyed on the actual observation
    # field (metric_granularity), never inferred from entity_type. The old
    # (metric_name, entity_type) projection cannot distinguish
    # saves/player_match from saves/goalkeeper_match -- both project to
    # entity_type="player" -- so it could certify 110/110 coverage even if
    # one of the two granularities was never actually emitted.
    seen_identity_values: dict[tuple[str, str, str, str, str | None], Any] = {}
    duplicate_identical = 0
    duplicate_conflicts = 0
    observed_identities: set[tuple[str, str]] = set()
    missing_granularity_count = 0

    unexpected: list[tuple[str, str]] = []
    competitions_seen: set[str] = set()
    seasons_seen: set[str] = set()
    zero_or_malformed_player_ids = 0

    total_home_away_scores = 0
    total_player_goals = 0
    total_player_assists = 0
    total_player_yellow_cards = 0
    total_player_red_cards = 0
    # "saves" is now genuinely emitted at BOTH player_match and
    # goalkeeper_match granularity (the same real per-save-event count,
    # correctly dual-scoped) -- summing every "saves" observation
    # regardless of granularity would silently double-count real saves.
    # Restricted to player_match, matching the original independently
    # recomputed `saves_full_type_set` event count below.
    total_player_saves = 0

    for obs in observations:
        by_entity_type[obs.entity_type] += 1
        by_metric_name[obs.metric_name] += 1

        identity_key = (
            obs.source_code,
            obs.entity_type,
            obs.entity_source_id,
            obs.metric_name,
            obs.metric_granularity,
        )
        if identity_key in seen_identity_values:
            if seen_identity_values[identity_key] != obs.value:
                duplicate_conflicts += 1
            else:
                duplicate_identical += 1
        else:
            seen_identity_values[identity_key] = obs.value

        if (obs.metric_name, obs.entity_type) not in _SAFE_METRIC_ENTITY_PAIRS:
            unexpected.append((obs.metric_name, obs.entity_type))

        # The certified path (`parse_premier_league_season`) must always
        # set `metric_granularity` explicitly -- a `None` here would mean a
        # certified observation was silently built without it, never a
        # case to project through entity_type instead.
        if obs.metric_granularity is None:
            missing_granularity_count += 1
        else:
            observed_identities.add((obs.metric_name, obs.metric_granularity))

        if obs.entity_type == "match":
            matches_seen.add(obs.entity_source_id)
            if obs.metric_name in ("home_score", "away_score"):
                total_home_away_scores += int(obs.value)
        elif obs.entity_type == "team":
            teams_seen.add(_numeric_suffix(obs.entity_source_id))
        elif obs.entity_type == "player":
            player_id = _numeric_suffix(obs.entity_source_id)
            players_seen.add(player_id)
            if player_id == "0" or not player_id.isdigit():
                zero_or_malformed_player_ids += 1
            if obs.metric_name == "goals":
                total_player_goals += int(obs.value)
            elif obs.metric_name == "assists":
                total_player_assists += int(obs.value)
            elif obs.metric_name == "yellow_cards":
                total_player_yellow_cards += int(obs.value)
            elif obs.metric_name == "red_cards":
                total_player_red_cards += int(obs.value)
            elif obs.metric_name == "saves" and obs.metric_granularity == "player_match":
                total_player_saves += int(obs.value)

        competitions_seen.add(obs.entity_identity_hints.get("competition_external_id", ""))
        seasons_seen.add(obs.entity_identity_hints.get("season_label", ""))

    safe_identities = {(m.catalog_key, m.catalog_granularity) for m in adapter_safe_mappings()}
    safe_pairs_with_observations = safe_identities & observed_identities
    zero_observation_identities = tuple(sorted(safe_identities - safe_pairs_with_observations))
    # The authoritative unexpected-output check: an observed
    # (metric_name, metric_granularity) pair that is not adapter-safe.
    # `saves/player_season` is unexpected even though `saves/player_match`
    # is safe -- both project to entity_type="player", so the coarser
    # `unexpected` (entity_type-keyed) list above cannot catch this case.
    unexpected_exact_identities = tuple(sorted(observed_identities - safe_identities))

    # Participation universe cross-checks: every emitted player_match/
    # goalkeeper_match observation must be a confirmed participant (starter
    # or used substitute) in that match's real lineup file -- never an
    # unused bench player, never an event-only phantom.
    participation_violations = 0
    unused_with_performance_obs = 0
    squad_player_ids: set[str] = set()
    participating_player_ids: set[str] = set()
    goalkeeper_ids: set[str] = set()
    match_scoped_performance_metrics = {
        obs.metric_name
        for obs in observations
        if obs.entity_type == "player"
        and _entity_source_id_is_match_scoped(obs.entity_source_id)
        and obs.metric_name not in ("started", "shirt_number", "listed_position")
    }

    for bundle in bundles:
        roster = parse_lineups(bundle.lineups_payload)
        for pid in roster.squad_players():
            squad_player_ids.add(f"{bundle.match_id}:{pid}")
        for pid in roster.participating_players():
            participating_player_ids.add(f"{bundle.match_id}:{pid}")
        for pid in roster.goalkeepers & set(roster.participating_players()):
            goalkeeper_ids.add(f"{bundle.match_id}:{pid}")

    for obs in observations:
        if (
            obs.entity_type == "player"
            and _entity_source_id_is_match_scoped(obs.entity_source_id)
            and obs.metric_name in match_scoped_performance_metrics
            and obs.entity_source_id not in participating_player_ids
        ):
            participation_violations += 1
            if obs.entity_source_id in squad_player_ids:
                unused_with_performance_obs += 1

    facts = _independent_source_facts(bundles)

    checks: list[VerificationCheck] = []
    checks.append(
        _check(
            "distinct_match_count",
            len(matches_seen) == _EXPECTED_MATCH_COUNT,
            f"expected {_EXPECTED_MATCH_COUNT}, got {len(matches_seen)}",
        )
    )
    checks.append(
        _check(
            "distinct_team_count",
            len(teams_seen) == _EXPECTED_TEAM_COUNT,
            f"expected {_EXPECTED_TEAM_COUNT}, got {len(teams_seen)}",
        )
    )
    checks.append(
        _check(
            "competition_scope_is_eng_pl_only",
            # Real provider-native competition_id (Block 20D.2 review-fix
            # pass): `competition_external_id` is the source's own numeric
            # id, verified against every real match record's own
            # `competition.competition_id` field -- never the canonical
            # "ENG_PL" code (see `statsbomb_open._scope_hints()`).
            competitions_seen == {str(COMPETITION_ID)},
            f"expected {{{str(COMPETITION_ID)!r}}} (real provider-native competition_id, "
            f"not the canonical {COMPETITION_CODE!r} code), got {competitions_seen}",
        )
    )
    checks.append(
        _check(
            "season_scope_is_2015_16_only",
            seasons_seen == {SEASON_LABEL},
            f"expected {{{SEASON_LABEL!r}}}, got {seasons_seen}",
        )
    )
    checks.append(
        _check(
            "no_sentinel_or_malformed_player_id",
            zero_or_malformed_player_ids == 0,
            f"found {zero_or_malformed_player_ids} observations keyed on player id 0 or "
            "a malformed (non-numeric) id",
        )
    )
    checks.append(
        _check(
            "no_unexpected_identities_emitted",
            not unexpected,
            f"found {len(unexpected)} unexpected (metric_name, entity_type) pairs: "
            f"{sorted(set(unexpected))[:10]}",
        )
    )
    checks.append(
        _check(
            "no_unexpected_exact_identities_emitted",
            not unexpected_exact_identities,
            f"found {len(unexpected_exact_identities)} unexpected (metric_name, "
            f"metric_granularity) pairs -- observed but not adapter-safe: "
            f"{unexpected_exact_identities[:10]}",
        )
    )
    checks.append(
        _check(
            "no_missing_metric_granularity",
            missing_granularity_count == 0,
            f"found {missing_granularity_count} certified-path observations with "
            "metric_granularity=None -- every certified observation must declare its "
            "granularity explicitly, never silently projected from entity_type",
        )
    )
    checks.append(
        _check(
            "all_adapter_safe_identities_observed",
            not zero_observation_identities,
            f"found {len(zero_observation_identities)} adapter-safe (metric_name, "
            f"metric_granularity) identities with zero real observations this run: "
            f"{zero_observation_identities}",
        )
    )
    checks.append(
        _check(
            "no_conflicting_duplicate_observations",
            duplicate_conflicts == 0,
            f"found {duplicate_conflicts} conflicting duplicate identities",
        )
    )
    checks.append(
        _check(
            "no_participation_universe_violations",
            participation_violations == 0,
            f"found {participation_violations} match-scoped performance observations for a "
            f"player who is not a confirmed lineup participant "
            f"({unused_with_performance_obs} of those are unused bench players)",
        )
    )
    checks.append(
        _check(
            "native_team_score_total",
            total_home_away_scores == _EXPECTED_NATIVE_GOAL_TOTAL,
            f"sum of home_score+away_score: expected {_EXPECTED_NATIVE_GOAL_TOTAL}, "
            f"got {total_home_away_scores}",
        )
    )
    checks.append(
        _check(
            "independent_native_score_matches_adapter_native_score",
            facts["native_score_sum"] == total_home_away_scores,
            f"independently-recomputed native score sum {facts['native_score_sum']} vs. "
            f"adapter-emitted {total_home_away_scores}",
        )
    )
    checks.append(
        _check(
            "adapter_player_goals_are_shooter_attributed_only",
            total_player_goals == _EXPECTED_SHOOTER_GOAL_TOTAL == facts["shooter_goals"],
            f"sum of player 'goals' observations: expected {_EXPECTED_SHOOTER_GOAL_TOTAL} "
            f"(shooter-tagged only, own goals deliberately excluded), got {total_player_goals} "
            f"(independently recomputed: {facts['shooter_goals']})",
        )
    )
    checks.append(
        _check(
            "own_goals_never_corrupt_player_goals_and_score_reconciles_exactly",
            facts["shooter_goals"] + facts["own_goal_for"] == _EXPECTED_NATIVE_GOAL_TOTAL
            and facts["own_goal_for"] == _EXPECTED_OWN_GOAL_TOTAL,
            f"shooter({facts['shooter_goals']}) + own_goal_for({facts['own_goal_for']}) = "
            f"{facts['shooter_goals'] + facts['own_goal_for']}, expected "
            f"{_EXPECTED_NATIVE_GOAL_TOTAL} with zero residual (unlike Wyscout's documented "
            "1-goal gap)",
        )
    )
    checks.append(
        _check(
            "assists_reconcile_to_native_goal_assist_field",
            total_player_assists == _EXPECTED_ASSISTS_TOTAL == facts["assists"],
            f"sum of player 'assists' observations: expected {_EXPECTED_ASSISTS_TOTAL} "
            f"(pass.goal_assist==True), got {total_player_assists} (independently "
            f"recomputed: {facts['assists']})",
        )
    )
    checks.append(
        _check(
            "cards_reconcile_to_lineup_file_not_foul_committed_only",
            total_player_yellow_cards == _EXPECTED_LINEUP_YELLOW == facts["lineup_yellow"],
            f"sum of player 'yellow_cards' observations: expected {_EXPECTED_LINEUP_YELLOW} "
            f"(lineup-authoritative), got {total_player_yellow_cards} (independently "
            f"recomputed from lineup: {facts['lineup_yellow']}); the old Foul-Committed-only "
            f"rule would have totaled only {facts['foul_committed_only_yellow']} "
            f"(missing {facts['bad_behaviour_yellow']} Bad-Behaviour-sourced cards)",
        )
    )
    checks.append(
        _check(
            "bad_behaviour_card_regression_cannot_recur",
            facts["bad_behaviour_yellow"] > 0
            and total_player_yellow_cards > facts["foul_committed_only_yellow"],
            f"{facts['bad_behaviour_yellow']} real Bad-Behaviour-sourced yellow cards exist "
            f"and are correctly included in the adapter's {total_player_yellow_cards} total "
            f"(old Foul-Committed-only rule would have totaled "
            f"{facts['foul_committed_only_yellow']})",
        )
    )
    checks.append(
        _check(
            "saves_use_full_certified_type_set_not_old_undercount",
            total_player_saves == _EXPECTED_SAVES_FULL_TYPE_SET == facts["saves_full_type_set"]
            and total_player_saves > _EXPECTED_SAVES_OLD_RULE_ONLY,
            f"sum of player 'saves' observations: expected {_EXPECTED_SAVES_FULL_TYPE_SET} "
            f"(full certified type set), got {total_player_saves} (independently recomputed: "
            f"{facts['saves_full_type_set']}); the old 'Shot Saved'-only rule would have "
            f"totaled only {facts['saves_old_rule_only']} "
            f"(expected old-rule value {_EXPECTED_SAVES_OLD_RULE_ONLY})",
        )
    )
    checks.append(
        _check(
            "internal_only_policy_is_true",
            STATSBOMB_INTERNAL_ONLY is True,
            f"STATSBOMB_INTERNAL_ONLY = {STATSBOMB_INTERNAL_ONLY!r}",
        )
    )

    return AdapterAuditReport(
        total_observations=len(observations),
        by_entity_type=dict(by_entity_type),
        by_metric_name=dict(sorted(by_metric_name.items())),
        distinct_matches=len(matches_seen),
        distinct_teams=len(teams_seen),
        distinct_squad_players=len(squad_player_ids),
        distinct_participating_players=len(participating_player_ids),
        distinct_goalkeepers=len({pid.split(":")[1] for pid in goalkeeper_ids}),
        duplicate_identical_count=duplicate_identical,
        duplicate_conflict_count=duplicate_conflicts,
        safe_identity_count=len(safe_identities),
        implemented_identity_count=len(_EMITTED_IDENTITIES),
        identities_with_observations=len(safe_pairs_with_observations),
        safe_identities_with_zero_observations=zero_observation_identities,
        unexpected_identities=tuple(sorted(set(unexpected))),
        unexpected_exact_identities=unexpected_exact_identities,
        checks=tuple(checks),
    )


def _print_report(report: AdapterAuditReport) -> None:
    print("=== STATSBOMB ADAPTER AUDIT (Block 20C.2b) ===")
    print(f"source_code: {SOURCE_CODE}")
    print(f"scope: {COMPETITION_CODE} {SEASON_LABEL} (HISTORICAL / DEEP, INTERNAL_ONLY)")
    print(f"total observations: {report.total_observations}")
    print(f"by entity_type: {report.by_entity_type}")
    print(f"distinct matches: {report.distinct_matches}")
    print(f"distinct teams: {report.distinct_teams}")
    print(f"distinct squad players (incl. unused subs): {report.distinct_squad_players}")
    print(f"distinct participating players: {report.distinct_participating_players}")
    print(f"distinct goalkeepers: {report.distinct_goalkeepers}")
    print(f"duplicate identical count: {report.duplicate_identical_count}")
    print(f"duplicate/conflict count: {report.duplicate_conflict_count}")

    print()
    print("=== ADAPTER-SAFE SCOPE ===")
    print(f"adapter-safe identities (65 DIRECT + 45 DERIVABLE_READY): {report.safe_identity_count}")
    print(f"identities implemented by this adapter: {report.implemented_identity_count}")
    print(
        f"identities that produced real observations this run: "
        f"{report.identities_with_observations}"
    )
    print(
        f"safe identities with zero observations this run "
        f"({len(report.safe_identities_with_zero_observations)}): "
        f"{report.safe_identities_with_zero_observations}"
    )
    print(
        f"unexpected (metric_name, entity_type) pairs ({len(report.unexpected_identities)}): "
        f"{report.unexpected_identities}"
    )
    print(
        f"unexpected exact (metric_name, metric_granularity) identities "
        f"({len(report.unexpected_exact_identities)}): {report.unexpected_exact_identities}"
    )

    print()
    print("=== OBSERVATIONS BY METRIC NAME ===")
    for metric_name, count in report.by_metric_name.items():
        print(f"  {metric_name}: {count}")

    print()
    print("=== VERIFICATION ===")
    for check in report.checks:
        status = "PASS" if check.passed else "FAIL"
        print(f"{status}  {check.name}  ({check.detail})")


def _report_to_dict(report: AdapterAuditReport) -> dict[str, Any]:
    return {
        "source_code": SOURCE_CODE,
        "scope": {
            "competition": COMPETITION_CODE,
            "season": SEASON_LABEL,
            "internal_only": STATSBOMB_INTERNAL_ONLY,
        },
        "total_observations": report.total_observations,
        "by_entity_type": report.by_entity_type,
        "by_metric_name": report.by_metric_name,
        "distinct_matches": report.distinct_matches,
        "distinct_teams": report.distinct_teams,
        "distinct_squad_players": report.distinct_squad_players,
        "distinct_participating_players": report.distinct_participating_players,
        "distinct_goalkeepers": report.distinct_goalkeepers,
        "duplicate_identical_count": report.duplicate_identical_count,
        "duplicate_conflict_count": report.duplicate_conflict_count,
        "safe_identity_count": report.safe_identity_count,
        "implemented_identity_count": report.implemented_identity_count,
        "identities_with_observations": report.identities_with_observations,
        "safe_identities_with_zero_observations": list(
            report.safe_identities_with_zero_observations
        ),
        "unexpected_identities": list(report.unexpected_identities),
        "unexpected_exact_identities": list(report.unexpected_exact_identities),
        "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in report.checks],
        "all_checks_passed": report.all_passed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 20C.2b: run the certified StatsBomb Open adapter "
            "(data_mesh.adapters.statsbomb_open) against the real, already-cached, "
            "pinned Premier League 2015/16 source and audit the resulting "
            "NormalizedObservation rows. Local-only, zero network requests, no "
            "database, no canonical ingestion."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--ref", type=str, default=DEFAULT_PINNED_REVISION)
    parser.add_argument("--report", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        bundles = load_full_season_bundles(args.cache_dir, source_revision=args.ref)
        observations = parse_premier_league_season(bundles, source_revision=args.ref)
    except StatsBombAdapterAuditError as exc:
        print(f"STATSBOMB ADAPTER AUDIT: FAIL - {exc}")
        raise SystemExit(1) from exc
    except StatsBombObservationConflictError as exc:
        print(f"STATSBOMB ADAPTER AUDIT: FAIL - adapter refused unsafe/conflicting output: {exc}")
        raise SystemExit(1) from exc

    report = build_report(observations, bundles)
    _print_report(report)

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(_report_to_dict(report), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print()
        print(f"REPORT: {args.report}")

    if not report.all_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
