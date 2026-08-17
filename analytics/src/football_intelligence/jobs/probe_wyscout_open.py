"""Block 20B.1 local acquisition/audit probe for Wyscout Open Data.

Fetches, caches, and structurally audits the England Premier League
2017/18 Wyscout Open Data files (Figshare collection 4415000) and reports
whether the published reference counts (380 matches / 643150 events / 603
players) are reproduced from the real source. This is acquisition + audit
only: it never connects to PostgreSQL, never writes to `football.*` /
`ingestion.*` / `intelligence.*`, and never maps events to the Metric
Catalog (that is Block 20B.2). Missing stays missing -- nothing here
fabricates a zero or a mapped metric.

**Player semantics (verified empirically against the real source, not
guessed from the paper alone):** the paper's published "603 players" is the
competition *roster/squad* population -- every player named in any match's
`teamsData[*].formation.lineup` or `.bench` -- not the narrower set of
players who actually acted in at least one event. That narrower,
event-derived population (514 for ENG_PL 2017/18) is a real and useful, but
different, metric and is reported separately, never conflated with the
603 published reference.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from football_intelligence.providers.wyscout_open import (
    WyscoutOpenAsset,
    WyscoutOpenDataArchiveError,
    WyscoutOpenDataClient,
    WyscoutOpenDataError,
    safe_extract_zip,
)

FIGSHARE_COLLECTION_ID = 4415000
COLLECTION_DOI = "10.6084/m9.figshare.c.4415000.v5"
PAPER_DOI = "10.1038/s41597-019-0247-7"
LICENCE = "CC BY 4.0"
COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2017/18"
ENGLAND_KEYWORD = "england"

_ARTICLE_MATCHES = "Matches"
_ARTICLE_EVENTS = "Events"
_ARTICLE_COMPETITIONS = "Competitions"
_ARTICLE_TEAMS = "Teams"
_ARTICLE_PLAYERS = "Players"
_ARTICLE_TAG_MAPPING = "Mapping of tag identifiers to tag names"

_EXPECTED_MATCH_COUNT = 380
_EXPECTED_EVENT_COUNT = 643150
_EXPECTED_PLAYER_COUNT = 603
_SENTINEL_PLAYER_ID = 0
_LINEUP_STRUCTURE_KEYS = ("lineup", "bench", "substitutions")
_MAX_STRUCTURE_SEARCH_DEPTH = 3
_SOURCE_QUALITY_ID_LIST_LIMIT = 25

DEFAULT_CACHE_DIR = Path("data/cache/wyscout-open")


class WyscoutProbeError(RuntimeError):
    """The probe could not complete a required acquisition/audit step."""


@dataclass(frozen=True)
class FieldCoverage:
    present: int
    total: int

    @property
    def percentage(self) -> float:
        return round(100.0 * self.present / self.total, 2) if self.total else 0.0


@dataclass(frozen=True)
class CountCheck:
    metric: str
    expected: int
    actual: int

    @property
    def passed(self) -> bool:
        return self.expected == self.actual


@dataclass(frozen=True)
class EnglandProbeReport:
    match_count: int
    event_count: int
    roster_player_count: int
    event_actor_count: int
    distinct_team_count: int
    event_name_distribution: dict[str, int]
    sub_event_name_distribution: dict[str, int]
    tag_ids_observed: tuple[int, ...]
    player_id_coverage: FieldCoverage
    team_id_coverage: FieldCoverage
    positions_coverage: FieldCoverage
    tags_coverage: FieldCoverage
    matches_with_lineup: int
    matches_with_bench: int
    matches_with_substitutions: int
    matches_missing_team_structure: int
    roster_players_missing_from_players_json: tuple[int, ...] | None
    event_actors_absent_from_roster: tuple[int, ...]
    count_checks: tuple[CountCheck, ...]

    @property
    def counts_verified(self) -> bool:
        return all(check.passed for check in self.count_checks)


def aggregate_england_probe(
    *,
    matches_payload: list[Any],
    events_payload: list[Any],
    players_payload: list[Any] | None = None,
) -> EnglandProbeReport:
    event_name_counter: Counter[str] = Counter()
    sub_event_name_counter: Counter[str] = Counter()
    tag_ids: set[int] = set()
    event_actor_ids: set[int] = set()
    distinct_team_ids: set[int] = set()

    player_id_present = 0
    team_id_present = 0
    positions_present = 0
    tags_present = 0

    for event in events_payload:
        if not isinstance(event, dict):
            continue

        event_name = event.get("eventName")
        if isinstance(event_name, str) and event_name:
            event_name_counter[event_name] += 1
        sub_event_name = event.get("subEventName")
        if isinstance(sub_event_name, str) and sub_event_name:
            sub_event_name_counter[sub_event_name] += 1

        player_id = event.get("playerId")
        if isinstance(player_id, int):
            player_id_present += 1
            if player_id != _SENTINEL_PLAYER_ID:
                event_actor_ids.add(player_id)

        team_id = event.get("teamId")
        if isinstance(team_id, int):
            team_id_present += 1
            distinct_team_ids.add(team_id)

        positions = event.get("positions")
        if isinstance(positions, list) and positions:
            positions_present += 1

        tags = event.get("tags")
        if isinstance(tags, list) and tags:
            tags_present += 1
            for tag in tags:
                if isinstance(tag, dict):
                    tag_id = tag.get("id")
                    if isinstance(tag_id, int):
                        tag_ids.add(tag_id)

    event_count = len(events_payload)
    match_count = len(matches_payload)

    matches_with_lineup = 0
    matches_with_bench = 0
    matches_with_substitutions = 0
    matches_missing_team_structure = 0

    for match in matches_payload:
        teams_data = match.get("teamsData") if isinstance(match, dict) else None
        if not isinstance(teams_data, dict) or not teams_data:
            matches_missing_team_structure += 1
            continue
        match_found = {key: False for key in _LINEUP_STRUCTURE_KEYS}
        for team_entry in teams_data.values():
            found = _detect_lineup_structure(team_entry)
            for key, value in found.items():
                match_found[key] = match_found[key] or value
        if match_found["lineup"]:
            matches_with_lineup += 1
        if match_found["bench"]:
            matches_with_bench += 1
        if match_found["substitutions"]:
            matches_with_substitutions += 1

    # Published-count verification uses the roster/squad population, not
    # event actors -- verified empirically: the paper's "603 players" is
    # every player named in `teamsData[*].formation.lineup` or `.bench`
    # across the 380 matches, a broader population than the 514 players who
    # actually generated a tagged event (89 rostered players, e.g. unused
    # substitutes, never appear as an event actor).
    lineup_ids, bench_ids = _extract_roster_player_ids(matches_payload)
    roster_player_ids = lineup_ids | bench_ids

    roster_players_missing_from_players_json: tuple[int, ...] | None = None
    if players_payload is not None:
        players_json_ids = {
            item["wyId"]
            for item in players_payload
            if isinstance(item, dict) and isinstance(item.get("wyId"), int)
        }
        roster_players_missing_from_players_json = tuple(
            sorted(roster_player_ids - players_json_ids)
        )
    event_actors_absent_from_roster = tuple(sorted(event_actor_ids - roster_player_ids))

    count_checks = (
        CountCheck(metric="matches", expected=_EXPECTED_MATCH_COUNT, actual=match_count),
        CountCheck(metric="events", expected=_EXPECTED_EVENT_COUNT, actual=event_count),
        CountCheck(
            metric="players", expected=_EXPECTED_PLAYER_COUNT, actual=len(roster_player_ids)
        ),
    )

    return EnglandProbeReport(
        match_count=match_count,
        event_count=event_count,
        roster_player_count=len(roster_player_ids),
        event_actor_count=len(event_actor_ids),
        distinct_team_count=len(distinct_team_ids),
        event_name_distribution=dict(sorted(event_name_counter.items())),
        sub_event_name_distribution=dict(sorted(sub_event_name_counter.items())),
        tag_ids_observed=tuple(sorted(tag_ids)),
        player_id_coverage=FieldCoverage(present=player_id_present, total=event_count),
        team_id_coverage=FieldCoverage(present=team_id_present, total=event_count),
        positions_coverage=FieldCoverage(present=positions_present, total=event_count),
        tags_coverage=FieldCoverage(present=tags_present, total=event_count),
        matches_with_lineup=matches_with_lineup,
        matches_with_bench=matches_with_bench,
        matches_with_substitutions=matches_with_substitutions,
        matches_missing_team_structure=matches_missing_team_structure,
        roster_players_missing_from_players_json=roster_players_missing_from_players_json,
        event_actors_absent_from_roster=event_actors_absent_from_roster,
        count_checks=count_checks,
    )


def _detect_lineup_structure(node: Any, *, depth: int = 0) -> dict[str, bool]:
    found = {key: False for key in _LINEUP_STRUCTURE_KEYS}
    if depth > _MAX_STRUCTURE_SEARCH_DEPTH or not isinstance(node, dict):
        return found
    for key, value in node.items():
        if isinstance(key, str):
            folded = key.casefold()
            if folded in _LINEUP_STRUCTURE_KEYS and isinstance(value, list):
                found[folded] = True
        nested = _detect_lineup_structure(value, depth=depth + 1)
        for nested_key, nested_value in nested.items():
            found[nested_key] = found[nested_key] or nested_value
    return found


def _extract_roster_player_ids(matches_payload: list[Any]) -> tuple[set[int], set[int]]:
    """Distinct non-zero player IDs from `teamsData[*].formation.{lineup,bench}`.

    This is the verified real field path for the published roster/squad
    population (competition team sheet), deliberately narrower than the
    generic recursive `_detect_lineup_structure` search used only for
    presence auditing. `coachId` is a sibling field of `formation` (never
    nested inside it) and `referees` is a top-level match field, so neither
    can leak into a player-id set built this way.
    """

    lineup_ids: set[int] = set()
    bench_ids: set[int] = set()
    for match in matches_payload:
        if not isinstance(match, dict):
            continue
        teams_data = match.get("teamsData")
        if not isinstance(teams_data, dict):
            continue
        for team_entry in teams_data.values():
            if not isinstance(team_entry, dict):
                continue
            formation = team_entry.get("formation")
            if not isinstance(formation, dict):
                continue
            for entry in _as_entry_list(formation.get("lineup")):
                _add_player_id(entry, "playerId", lineup_ids)
            for entry in _as_entry_list(formation.get("bench")):
                _add_player_id(entry, "playerId", bench_ids)
    return lineup_ids, bench_ids


def _as_entry_list(value: Any) -> list[Any]:
    # Real source quirk: `formation.substitutions` (and, defensively, other
    # formation fields) can be the literal string "null" instead of an
    # empty list when a team had nothing to report. Any non-list value
    # means "nothing here", never a structural error.
    return value if isinstance(value, list) else []


def _add_player_id(entry: Any, field: str, target: set[int]) -> None:
    if not isinstance(entry, dict):
        return
    player_id = entry.get(field)
    if isinstance(player_id, int) and player_id != _SENTINEL_PLAYER_ID:
        target.add(player_id)


# -- Acquisition + local loading ------------------------------------------


def _resolve_content_path(local_path: Path, cache_dir: Path, *, keyword: str | None) -> Path:
    if local_path.suffix.lower() != ".zip":
        return local_path

    extract_dir = cache_dir / "extracted" / local_path.stem
    candidates: list[Path] = []
    if extract_dir.exists():
        candidates = [path for path in extract_dir.rglob("*") if path.is_file()]
    if not candidates:
        try:
            extracted = safe_extract_zip(local_path, extract_dir)
        except WyscoutOpenDataArchiveError as exc:
            raise WyscoutProbeError(f"unsafe archive contents in {local_path.name}: {exc}") from exc
        candidates = [path for path in extracted if path.is_file()]

    if keyword is not None:
        needle = keyword.casefold()
        filtered = [path for path in candidates if needle in path.name.casefold()]
        if not filtered:
            raise WyscoutProbeError(
                f"archive {local_path.name} contains no entry matching keyword {keyword!r} "
                f"({len(candidates)} total entries inspected)"
            )
        candidates = filtered

    data_candidates = [path for path in candidates if path.suffix.lower() in {".json", ".csv"}]
    if data_candidates:
        candidates = data_candidates

    if len(candidates) != 1:
        keyword_label = f" matching keyword {keyword!r}" if keyword is not None else ""
        raise WyscoutProbeError(
            f"archive {local_path.name} resolved to {len(candidates)} candidate files"
            f"{keyword_label} (expected exactly one)"
        )
    return candidates[0]


def _load_json_asset(local_path: Path, cache_dir: Path, *, keyword: str | None) -> Any:
    target = _resolve_content_path(local_path, cache_dir, keyword=keyword)
    with target.open("rb") as handle:
        return json.load(handle)


def _load_tag_mapping(local_path: Path, cache_dir: Path) -> dict[int, str]:
    try:
        target = _resolve_content_path(local_path, cache_dir, keyword=None)
    except WyscoutProbeError:
        return {}

    raw_text = target.read_text(encoding="utf-8", errors="replace")
    mapping: dict[int, str] = {}

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = None

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            tag_id: int | None = None
            name: str | None = None
            for key, value in item.items():
                if not isinstance(key, str):
                    continue
                folded = key.casefold()
                if tag_id is None and "tag" in folded and isinstance(value, int):
                    tag_id = value
                is_name_column = folded in {"description", "name", "label"}
                if name is None and is_name_column and isinstance(value, str):
                    name = value
            if tag_id is not None and name is not None:
                mapping[tag_id] = name
        return mapping

    for row in csv.reader(io.StringIO(raw_text)):
        if len(row) < 2:
            continue
        raw_id = row[0].strip()
        if raw_id.isdigit():
            mapping[int(raw_id)] = row[1].strip()
    return mapping


@dataclass(frozen=True)
class ProbeExtras:
    competitions_entries: int | None
    england_competition_name: str | None
    teams_json_total: int | None
    players_json_total: int | None
    tag_mapping_size: int


def _best_effort_json(
    client: WyscoutOpenDataClient,
    *,
    article_title: str,
    cache_dir: Path,
) -> Any | None:
    try:
        asset = client.fetch_asset(
            collection_id=FIGSHARE_COLLECTION_ID,
            article_title=article_title,
            cache_dir=cache_dir,
        )
        return _load_json_asset(asset.local_path, cache_dir, keyword=None)
    except (WyscoutOpenDataError, WyscoutProbeError, OSError, json.JSONDecodeError):
        return None


def _find_england_competition_name(payload: Any) -> str | None:
    if not isinstance(payload, list):
        return None
    for item in payload:
        if not isinstance(item, dict):
            continue
        area = item.get("area")
        area_name = area.get("name") if isinstance(area, dict) else None
        name = item.get("name")
        if isinstance(area_name, str) and "england" in area_name.casefold():
            return str(name) if isinstance(name, str) else str(item.get("wyId"))
        if isinstance(name, str):
            folded = name.casefold()
            if "england" in folded and "premier" in folded:
                return name
    return None


@dataclass(frozen=True)
class ProbeRunResult:
    report: EnglandProbeReport
    matches_asset: WyscoutOpenAsset
    events_asset: WyscoutOpenAsset
    extras: ProbeExtras


def run_probe(*, cache_dir: Path) -> ProbeRunResult:
    client = WyscoutOpenDataClient()
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        matches_asset = client.fetch_asset(
            collection_id=FIGSHARE_COLLECTION_ID,
            article_title=_ARTICLE_MATCHES,
            cache_dir=cache_dir,
            keyword=ENGLAND_KEYWORD,
        )
        events_asset = client.fetch_asset(
            collection_id=FIGSHARE_COLLECTION_ID,
            article_title=_ARTICLE_EVENTS,
            cache_dir=cache_dir,
            keyword=ENGLAND_KEYWORD,
        )
    except WyscoutOpenDataError as exc:
        raise WyscoutProbeError(f"England matches/events acquisition failed: {exc}") from exc

    try:
        matches_payload = _load_json_asset(
            matches_asset.local_path, cache_dir, keyword=ENGLAND_KEYWORD
        )
        events_payload = _load_json_asset(
            events_asset.local_path, cache_dir, keyword=ENGLAND_KEYWORD
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise WyscoutProbeError(f"could not load downloaded England payload: {exc}") from exc

    if not isinstance(matches_payload, list) or not matches_payload:
        raise WyscoutProbeError(
            "England matches payload is structurally unusable (empty/not a list)"
        )
    if not isinstance(events_payload, list) or not events_payload:
        raise WyscoutProbeError(
            "England events payload is structurally unusable (empty/not a list)"
        )

    competitions_payload = _best_effort_json(
        client, article_title=_ARTICLE_COMPETITIONS, cache_dir=cache_dir
    )
    teams_payload = _best_effort_json(client, article_title=_ARTICLE_TEAMS, cache_dir=cache_dir)
    players_payload = _best_effort_json(client, article_title=_ARTICLE_PLAYERS, cache_dir=cache_dir)

    tag_mapping: dict[int, str] = {}
    try:
        tag_asset = client.fetch_asset(
            collection_id=FIGSHARE_COLLECTION_ID,
            article_title=_ARTICLE_TAG_MAPPING,
            cache_dir=cache_dir,
        )
        tag_mapping = _load_tag_mapping(tag_asset.local_path, cache_dir)
    except WyscoutOpenDataError:
        tag_mapping = {}

    competitions_entries = (
        len(competitions_payload) if isinstance(competitions_payload, list) else None
    )
    teams_json_total = len(teams_payload) if isinstance(teams_payload, list) else None
    players_json_total = len(players_payload) if isinstance(players_payload, list) else None
    extras = ProbeExtras(
        competitions_entries=competitions_entries,
        england_competition_name=_find_england_competition_name(competitions_payload),
        teams_json_total=teams_json_total,
        players_json_total=players_json_total,
        tag_mapping_size=len(tag_mapping),
    )

    report = aggregate_england_probe(
        matches_payload=matches_payload,
        events_payload=events_payload,
        players_payload=players_payload if isinstance(players_payload, list) else None,
    )
    return ProbeRunResult(
        report=report,
        matches_asset=matches_asset,
        events_asset=events_asset,
        extras=extras,
    )


def _print_report(
    report: EnglandProbeReport,
    matches_asset: WyscoutOpenAsset,
    events_asset: WyscoutOpenAsset,
    extras: ProbeExtras,
) -> None:
    print("=== SOURCE ===")
    print("source name: Wyscout Open Data")
    print(f"Figshare collection ID: {FIGSHARE_COLLECTION_ID}")
    print(f"collection DOI: {COLLECTION_DOI}")
    print(f"licence: {LICENCE}")
    print(f"paper DOI: {PAPER_DOI}")
    print(
        f"matches asset: article={matches_asset.article_title!r} (id={matches_asset.article_id}) "
        f"file={matches_asset.file_name!r} (id={matches_asset.file_id}) "
        f"checksum_verified={matches_asset.checksum_verified} from_cache={matches_asset.from_cache}"
    )
    print(
        f"events asset: article={events_asset.article_title!r} (id={events_asset.article_id}) "
        f"file={events_asset.file_name!r} (id={events_asset.file_id}) "
        f"checksum_verified={events_asset.checksum_verified} from_cache={events_asset.from_cache}"
    )

    print()
    print("=== SCOPE ===")
    print(f"competition: {COMPETITION_CODE}")
    print(f"season: {SEASON_LABEL}")
    print("role: HISTORICAL / DEEP")
    print("NOT CURRENT-SEASON EVIDENCE")
    print(f"competitions.json England entry: {extras.england_competition_name!r}")

    print()
    print("=== COUNTS ===")
    print(f"England match count: {report.match_count}")
    print(f"England event count: {report.event_count}")
    print(f"distinct roster/squad player IDs (lineup U bench): {report.roster_player_count}")
    print(f"distinct event actor player IDs (sentinel 0 excluded): {report.event_actor_count}")
    print(f"distinct England team IDs (from events): {report.distinct_team_count}")
    print(f"players.json total entries (informational): {extras.players_json_total}")
    print(f"teams.json total entries (informational): {extras.teams_json_total}")
    print(f"tag-id mapping entries loaded (informational): {extras.tag_mapping_size}")

    print()
    print("=== EVENT SCHEMA AUDIT ===")
    print(f"eventName distribution: {report.event_name_distribution}")
    print(f"subEventName distribution: {report.sub_event_name_distribution}")
    print(f"tag IDs observed ({len(report.tag_ids_observed)}): {list(report.tag_ids_observed)}")
    for label, coverage in (
        ("playerId", report.player_id_coverage),
        ("teamId", report.team_id_coverage),
        ("positions", report.positions_coverage),
        ("tags", report.tags_coverage),
    ):
        print(f"{label} coverage: {coverage.present}/{coverage.total} ({coverage.percentage}%)")

    print()
    print("=== MATCH STRUCTURE AUDIT ===")
    print(f"matches with lineup structure found: {report.matches_with_lineup}/{report.match_count}")
    print(f"matches with bench structure found: {report.matches_with_bench}/{report.match_count}")
    print(
        f"matches with substitutions structure found: "
        f"{report.matches_with_substitutions}/{report.match_count}"
    )
    print(f"matches missing team structure entirely: {report.matches_missing_team_structure}")

    print()
    print("=== SOURCE QUALITY ===")
    if report.roster_players_missing_from_players_json is None:
        print("roster players missing from players.json: unavailable (players.json not loaded)")
    else:
        missing = report.roster_players_missing_from_players_json
        print(f"roster players missing from players.json: {len(missing)}")
        if 0 < len(missing) <= _SOURCE_QUALITY_ID_LIST_LIMIT:
            print(f"  ids: {list(missing)}")
    absent = report.event_actors_absent_from_roster
    print(f"event actors absent from roster/squad population: {len(absent)}")
    if 0 < len(absent) <= _SOURCE_QUALITY_ID_LIST_LIMIT:
        print(f"  ids: {list(absent)}")

    print()
    print("=== PUBLISHED COUNT VERIFICATION ===")
    for check in report.count_checks:
        if check.passed:
            print(f"{check.metric.upper()} COUNT: PASS")
        else:
            print(
                f"{check.metric.upper()} COUNT: MISMATCH expected={check.expected} "
                f"actual={check.actual}"
            )


def _report_to_dict(
    report: EnglandProbeReport,
    matches_asset: WyscoutOpenAsset,
    events_asset: WyscoutOpenAsset,
    extras: ProbeExtras,
) -> dict[str, Any]:
    return {
        "source": {
            "name": "Wyscout Open Data",
            "figshare_collection_id": FIGSHARE_COLLECTION_ID,
            "collection_doi": COLLECTION_DOI,
            "licence": LICENCE,
            "paper_doi": PAPER_DOI,
        },
        "scope": {
            "competition": COMPETITION_CODE,
            "season": SEASON_LABEL,
            "role": "HISTORICAL_DEEP",
            "current_season_evidence": False,
            "competitions_json_england_entry": extras.england_competition_name,
        },
        "assets": {
            "matches": {
                "article_id": matches_asset.article_id,
                "article_title": matches_asset.article_title,
                "file_id": matches_asset.file_id,
                "file_name": matches_asset.file_name,
                "checksum_verified": matches_asset.checksum_verified,
                "from_cache": matches_asset.from_cache,
            },
            "events": {
                "article_id": events_asset.article_id,
                "article_title": events_asset.article_title,
                "file_id": events_asset.file_id,
                "file_name": events_asset.file_name,
                "checksum_verified": events_asset.checksum_verified,
                "from_cache": events_asset.from_cache,
            },
        },
        "counts": {
            "match_count": report.match_count,
            "event_count": report.event_count,
            "roster_player_count": report.roster_player_count,
            "event_actor_count": report.event_actor_count,
            "distinct_team_count": report.distinct_team_count,
            "players_json_total_informational": extras.players_json_total,
            "teams_json_total_informational": extras.teams_json_total,
            "tag_mapping_size_informational": extras.tag_mapping_size,
        },
        "event_schema_audit": {
            "event_name_distribution": report.event_name_distribution,
            "sub_event_name_distribution": report.sub_event_name_distribution,
            "tag_ids_observed": list(report.tag_ids_observed),
            "player_id_coverage": {
                "present": report.player_id_coverage.present,
                "total": report.player_id_coverage.total,
                "percentage": report.player_id_coverage.percentage,
            },
            "team_id_coverage": {
                "present": report.team_id_coverage.present,
                "total": report.team_id_coverage.total,
                "percentage": report.team_id_coverage.percentage,
            },
            "positions_coverage": {
                "present": report.positions_coverage.present,
                "total": report.positions_coverage.total,
                "percentage": report.positions_coverage.percentage,
            },
            "tags_coverage": {
                "present": report.tags_coverage.present,
                "total": report.tags_coverage.total,
                "percentage": report.tags_coverage.percentage,
            },
        },
        "match_structure_audit": {
            "matches_with_lineup": report.matches_with_lineup,
            "matches_with_bench": report.matches_with_bench,
            "matches_with_substitutions": report.matches_with_substitutions,
            "matches_missing_team_structure": report.matches_missing_team_structure,
        },
        "source_quality": {
            "roster_players_missing_from_players_json": (
                list(report.roster_players_missing_from_players_json)
                if report.roster_players_missing_from_players_json is not None
                else None
            ),
            "event_actors_absent_from_roster": list(report.event_actors_absent_from_roster),
        },
        "published_count_verification": [
            {
                "metric": check.metric,
                "expected": check.expected,
                "actual": check.actual,
                "status": "PASS" if check.passed else "MISMATCH",
            }
            for check in report.count_checks
        ],
        "counts_verified": report.counts_verified,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 20B.1 local acquisition/audit probe for Wyscout Open Data "
            "(Figshare collection 4415000, ENG_PL 2017/18 historical/deep). "
            "Fetches, caches, and structurally audits the England matches/events "
            "files -- never connects to a database."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--report", type=Path, default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    try:
        result = run_probe(cache_dir=args.cache_dir)
    except WyscoutProbeError as exc:
        print(f"WYSCOUT PROBE: FAIL - {exc}")
        raise SystemExit(1) from exc

    _print_report(result.report, result.matches_asset, result.events_asset, result.extras)

    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        payload = _report_to_dict(
            result.report, result.matches_asset, result.events_asset, result.extras
        )
        args.report.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print()
        print(f"REPORT: {args.report}")

    if not result.report.counts_verified:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
