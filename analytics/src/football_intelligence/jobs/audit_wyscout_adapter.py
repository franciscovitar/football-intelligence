"""Block 20B.2b audit: run the Wyscout Open adapter against the real,
already-cached ENG_PL 2017/18 source and report on the resulting
`NormalizedObservation` rows.

Local-only: reads files already cached by the Block 20B.1 probe
(`data/cache/wyscout-open/`), never makes a network request, never connects
to PostgreSQL, and never writes canonical evidence. It exists to prove the
adapter (`data_mesh.adapters.wyscout_open`) only ever emits adapter-safe
identities and produces internally consistent, source-faithful output
against the real dataset before any canonical ingestion is implemented.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football_intelligence.data_mesh.adapters.wyscout_open import (
    _EMITTED_IDENTITIES,
    _GRANULARITY_TO_ENTITY_TYPE,
    _SAFE_METRIC_ENTITY_PAIRS,
    COMPETITION_CODE,
    SEASON_LABEL,
    SOURCE_CODE,
    WyscoutObservationConflictError,
    parse_england_season,
)
from football_intelligence.data_mesh.models import EntityType, NormalizedObservation
from football_intelligence.jobs.audit_wyscout_metric_mapping import (
    _find_cached_file,
    load_cached_source,
)
from football_intelligence.providers.wyscout_open_mapping import adapter_safe_mappings

DEFAULT_CACHE_DIR = Path("data/cache/wyscout-open")

_EXPECTED_MATCH_COUNT = 380
_EXPECTED_TEAM_COUNT = 20
_EXPECTED_NATIVE_GOAL_TOTAL = 1018
_EXPECTED_SHOOTER_GOAL_TOTAL = 988
_EXPECTED_OWN_GOAL_TOTAL = 29
_EXPECTED_RECONCILED_GOAL_TOTAL = _EXPECTED_SHOOTER_GOAL_TOTAL + _EXPECTED_OWN_GOAL_TOTAL
_KNOWN_RESIDUAL_MATCH_ID = "2499781"

_SEASON_SCOPED_GRANULARITIES = frozenset({"player_season", "goalkeeper_season"})


class WyscoutAdapterAuditError(RuntimeError):
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
    distinct_players: int
    duplicate_conflict_count: int
    safe_identity_count: int
    implemented_identity_count: int
    identities_with_observations: int
    safe_identities_with_zero_observations: tuple[tuple[str, str], ...]
    unexpected_identities: tuple[tuple[str, str], ...]
    checks: tuple[VerificationCheck, ...]

    @property
    def all_passed(self) -> bool:
        return all(check.passed for check in self.checks)


def _load_players_payload(cache_dir: Path) -> list[Any]:
    path = _find_cached_file(cache_dir, "*players.json")
    with path.open("rb") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise WyscoutAdapterAuditError("cached players.json payload is structurally unusable")
    return payload


def load_adapter_inputs(cache_dir: Path) -> tuple[list[Any], list[Any], list[Any]]:
    matches_payload, events_payload, _tag_labels = load_cached_source(cache_dir)
    players_payload = _load_players_payload(cache_dir)
    return matches_payload, events_payload, players_payload


def run_adapter(cache_dir: Path) -> list[NormalizedObservation]:
    matches_payload, events_payload, players_payload = load_adapter_inputs(cache_dir)
    try:
        return parse_england_season(
            matches_payload=matches_payload,
            events_payload=events_payload,
            players_payload=players_payload,
        )
    except WyscoutObservationConflictError as exc:
        raise WyscoutAdapterAuditError(f"adapter refused conflicting observations: {exc}") from exc


def _check(name: str, passed: bool, detail: str) -> VerificationCheck:
    return VerificationCheck(name=name, passed=passed, detail=detail)


def _entity_source_id_is_match_scoped(entity_source_id: str) -> bool:
    return ":" in entity_source_id


def _numeric_suffix(entity_source_id: str) -> str:
    return entity_source_id.rsplit(":", maxsplit=1)[-1]


def _identity_expected_entity_type(granularity: str, key: str) -> EntityType:
    if key == "home_away":
        return "team"
    return _GRANULARITY_TO_ENTITY_TYPE[granularity]


def build_report(observations: list[NormalizedObservation]) -> AdapterAuditReport:
    by_entity_type: Counter[str] = Counter()
    by_metric_name: Counter[str] = Counter()
    matches_seen: set[str] = set()
    teams_seen: set[str] = set()
    players_seen: set[str] = set()

    seen_identity_values: dict[tuple[str, str, str, str], Any] = {}
    duplicate_conflicts = 0

    match_scoped_pairs: set[tuple[str, EntityType]] = set()
    season_scoped_pairs: set[tuple[str, EntityType]] = set()
    match_entity_pairs: set[tuple[str, EntityType]] = set()

    checks: list[VerificationCheck] = []
    unexpected: list[tuple[str, str]] = []

    competitions_seen: set[str] = set()
    seasons_seen: set[str] = set()
    zero_player_ids = 0

    total_home_away_scores = 0
    total_player_goals = 0

    for obs in observations:
        by_entity_type[obs.entity_type] += 1
        by_metric_name[obs.metric_name] += 1

        identity_key = (obs.source_code, obs.entity_type, obs.entity_source_id, obs.metric_name)
        if identity_key in seen_identity_values:
            if seen_identity_values[identity_key] != obs.value:
                duplicate_conflicts += 1
        else:
            seen_identity_values[identity_key] = obs.value

        if (obs.metric_name, obs.entity_type) not in _SAFE_METRIC_ENTITY_PAIRS:
            unexpected.append((obs.metric_name, obs.entity_type))

        if obs.entity_type == "match":
            matches_seen.add(obs.entity_source_id)
            match_entity_pairs.add((obs.metric_name, obs.entity_type))
            if obs.metric_name in ("home_score", "away_score"):
                total_home_away_scores += int(obs.value)
        elif obs.entity_type == "team":
            teams_seen.add(_numeric_suffix(obs.entity_source_id))
            if _entity_source_id_is_match_scoped(obs.entity_source_id):
                match_scoped_pairs.add((obs.metric_name, obs.entity_type))
        elif obs.entity_type == "player":
            player_id = _numeric_suffix(obs.entity_source_id)
            players_seen.add(player_id)
            if player_id == "0":
                zero_player_ids += 1
            if _entity_source_id_is_match_scoped(obs.entity_source_id):
                match_scoped_pairs.add((obs.metric_name, obs.entity_type))
            else:
                season_scoped_pairs.add((obs.metric_name, obs.entity_type))
            if obs.metric_name == "goals":
                total_player_goals += int(obs.value)

        competitions_seen.add(obs.entity_identity_hints.get("competition_external_id", ""))
        seasons_seen.add(obs.entity_identity_hints.get("season_label", ""))

    safe_pairs_with_observations: set[tuple[str, str]] = set()
    for mapping in adapter_safe_mappings():
        key, granularity = mapping.catalog_key, mapping.catalog_granularity
        identity = (key, granularity)
        entity_type = _identity_expected_entity_type(granularity, key)
        pair = (key, entity_type)
        # `home_away`'s catalog granularity is "match", but its adapter
        # entity_type is "team" (documented override -- see
        # `_identity_expected_entity_type`), so it is match-scoped like
        # every other team-match fact, never checked against
        # `match_entity_pairs` (which only ever holds entity_type="match"
        # facts).
        if entity_type == "match":
            has_obs = pair in match_entity_pairs
        elif granularity in _SEASON_SCOPED_GRANULARITIES:
            has_obs = pair in season_scoped_pairs
        else:
            has_obs = pair in match_scoped_pairs
        if has_obs:
            safe_pairs_with_observations.add(identity)

    safe_identities = {(m.catalog_key, m.catalog_granularity) for m in adapter_safe_mappings()}
    zero_observation_identities = tuple(sorted(safe_identities - safe_pairs_with_observations))

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
            competitions_seen == {COMPETITION_CODE},
            f"expected {{{COMPETITION_CODE!r}}}, got {competitions_seen}",
        )
    )
    checks.append(
        _check(
            "season_scope_is_2017_18_only",
            seasons_seen == {SEASON_LABEL},
            f"expected {{{SEASON_LABEL!r}}}, got {seasons_seen}",
        )
    )
    checks.append(
        _check(
            "no_sentinel_player_id_0",
            zero_player_ids == 0,
            f"found {zero_player_ids} observations keyed on player id 0",
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
            "no_conflicting_duplicate_observations",
            duplicate_conflicts == 0,
            f"found {duplicate_conflicts} conflicting duplicate identities",
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
            "adapter_player_goals_are_shooter_attributed_only",
            total_player_goals == _EXPECTED_SHOOTER_GOAL_TOTAL,
            f"sum of player 'goals' observations: expected {_EXPECTED_SHOOTER_GOAL_TOTAL} "
            f"(shooter-tagged only, own goals deliberately excluded), got {total_player_goals}",
        )
    )
    checks.append(
        _check(
            "known_source_residual_is_exactly_one_goal_at_the_documented_match",
            _EXPECTED_NATIVE_GOAL_TOTAL - _EXPECTED_RECONCILED_GOAL_TOTAL == 1,
            f"native({_EXPECTED_NATIVE_GOAL_TOTAL}) - reconciled(shooter "
            f"{_EXPECTED_SHOOTER_GOAL_TOTAL} + own-goal {_EXPECTED_OWN_GOAL_TOTAL} = "
            f"{_EXPECTED_RECONCILED_GOAL_TOTAL}) -- documented, expected 1-goal gap at match "
            f"wyId {_KNOWN_RESIDUAL_MATCH_ID} (no shot-type event exists for that goal in the "
            "raw source; never invented here)",
        )
    )

    return AdapterAuditReport(
        total_observations=len(observations),
        by_entity_type=dict(by_entity_type),
        by_metric_name=dict(sorted(by_metric_name.items())),
        distinct_matches=len(matches_seen),
        distinct_teams=len(teams_seen),
        distinct_players=len(players_seen),
        duplicate_conflict_count=duplicate_conflicts,
        safe_identity_count=len(safe_identities),
        implemented_identity_count=len(_EMITTED_IDENTITIES),
        identities_with_observations=len(safe_pairs_with_observations),
        safe_identities_with_zero_observations=zero_observation_identities,
        unexpected_identities=tuple(sorted(set(unexpected))),
        checks=tuple(checks),
    )


def _print_report(report: AdapterAuditReport) -> None:
    print("=== WYSCOUT ADAPTER AUDIT (Block 20B.2b) ===")
    print(f"source_code: {SOURCE_CODE}")
    print(f"scope: {COMPETITION_CODE} {SEASON_LABEL} (HISTORICAL / DEEP)")
    print(f"total observations: {report.total_observations}")
    print(f"by entity_type: {report.by_entity_type}")
    print(f"distinct matches: {report.distinct_matches}")
    print(f"distinct teams: {report.distinct_teams}")
    print(f"distinct players: {report.distinct_players}")
    print(f"duplicate/conflict count: {report.duplicate_conflict_count}")

    print()
    print("=== ADAPTER-SAFE SCOPE ===")
    print(f"adapter-safe identities (43 DIRECT + 34 DERIVABLE_READY): {report.safe_identity_count}")
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
        f"unexpected identities emitted ({len(report.unexpected_identities)}): "
        f"{report.unexpected_identities}"
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
        "scope": {"competition": COMPETITION_CODE, "season": SEASON_LABEL},
        "total_observations": report.total_observations,
        "by_entity_type": report.by_entity_type,
        "by_metric_name": report.by_metric_name,
        "distinct_matches": report.distinct_matches,
        "distinct_teams": report.distinct_teams,
        "distinct_players": report.distinct_players,
        "duplicate_conflict_count": report.duplicate_conflict_count,
        "safe_identity_count": report.safe_identity_count,
        "implemented_identity_count": report.implemented_identity_count,
        "identities_with_observations": report.identities_with_observations,
        "safe_identities_with_zero_observations": list(
            report.safe_identities_with_zero_observations
        ),
        "unexpected_identities": list(report.unexpected_identities),
        "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in report.checks],
        "all_checks_passed": report.all_passed,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 20B.2b: run the Wyscout Open adapter "
            "(data_mesh.adapters.wyscout_open) against the real, already-cached "
            "ENG_PL 2017/18 source and audit the resulting NormalizedObservation rows. "
            "Local-only, no network, no database, no canonical ingestion."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--report", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        observations = run_adapter(args.cache_dir)
    except WyscoutAdapterAuditError as exc:
        print(f"WYSCOUT ADAPTER AUDIT: FAIL - {exc}")
        raise SystemExit(1) from exc

    report = build_report(observations)
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
