from __future__ import annotations

import hashlib
import inspect
import json
import zipfile
from pathlib import Path

import pytest

from football_intelligence.jobs import probe_wyscout_open
from football_intelligence.jobs.probe_wyscout_open import (
    WyscoutProbeError,
    aggregate_england_probe,
    build_parser,
)
from football_intelligence.providers.wyscout_open import WyscoutOpenDataClient

_SYNTHETIC_MATCHES = [
    {
        "wyId": 1,
        "teamsData": {
            "100": {
                "formation": {
                    "lineup": [{"playerId": 11}],
                    "bench": [{"playerId": 12}],
                    "substitutions": [{"playerIn": 12, "playerOut": 11, "minute": 60}],
                }
            },
            "200": {"formation": {"lineup": [{"playerId": 21}], "bench": [], "substitutions": []}},
        },
    },
    {"wyId": 2, "teamsData": {}},
]

_SYNTHETIC_EVENTS = [
    {
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 11,
        "teamId": 100,
        "positions": [{"x": 1, "y": 2}],
        "tags": [{"id": 1801}],
    },
    {
        "eventName": "Duel",
        "subEventName": "Ground duel",
        "playerId": 21,
        "teamId": 200,
        "positions": [{"x": 3, "y": 4}],
        "tags": [{"id": 703}, {"id": 1801}],
    },
    {
        "eventName": "Pass",
        "subEventName": "Simple pass",
        "playerId": 0,
        "teamId": 100,
        "positions": [],
        "tags": [],
    },
]


def test_aggregate_counts_matches_and_events() -> None:
    report = aggregate_england_probe(
        matches_payload=_SYNTHETIC_MATCHES, events_payload=_SYNTHETIC_EVENTS
    )

    assert report.match_count == 2
    assert report.event_count == 3
    # Roster (lineup U bench) is {11, 12, 21}: player 12 is bench-only and
    # never appears as an event actor -- an unused bench player still
    # counts toward the roster/squad population.
    assert report.roster_player_count == 3
    assert report.event_actor_count == 2  # sentinel player id 0 excluded
    assert report.distinct_team_count == 2
    assert report.event_name_distribution == {"Duel": 1, "Pass": 2}
    assert report.sub_event_name_distribution == {"Ground duel": 1, "Simple pass": 2}
    assert report.tag_ids_observed == (703, 1801)


def test_aggregate_field_coverage() -> None:
    report = aggregate_england_probe(
        matches_payload=_SYNTHETIC_MATCHES, events_payload=_SYNTHETIC_EVENTS
    )

    assert report.player_id_coverage.present == 3
    assert report.player_id_coverage.total == 3
    assert report.team_id_coverage.present == 3
    assert report.positions_coverage.present == 2
    assert report.tags_coverage.present == 2


def test_aggregate_detects_lineup_bench_substitutions() -> None:
    report = aggregate_england_probe(
        matches_payload=_SYNTHETIC_MATCHES, events_payload=_SYNTHETIC_EVENTS
    )

    assert report.matches_with_lineup == 1
    assert report.matches_with_bench == 1
    assert report.matches_with_substitutions == 1
    assert report.matches_missing_team_structure == 1


def test_count_checks_report_mismatch_for_small_synthetic_sample() -> None:
    report = aggregate_england_probe(
        matches_payload=_SYNTHETIC_MATCHES, events_payload=_SYNTHETIC_EVENTS
    )

    assert report.counts_verified is False
    mismatched = {check.metric for check in report.count_checks if not check.passed}
    assert mismatched == {"matches", "events", "players"}


def _entries(ids: range) -> list[dict[str, int]]:
    return [{"playerId": pid} for pid in ids]


def _matches_with_603_roster_union() -> list[dict[str, object]]:
    """380 matches whose combined lineup U bench is exactly 603 distinct IDs.

    Only the first match carries formation data; the remaining 379 are
    empty (`teamsData: {}`) -- the roster population is a union across all
    matches, so this still reproduces the real 603 count deterministically
    without needing 380 realistic squads.
    """

    matches: list[dict[str, object]] = [{"wyId": i, "teamsData": {}} for i in range(380)]
    matches[0] = {
        "wyId": 0,
        "teamsData": {
            "100": {
                "formation": {
                    "lineup": _entries(range(1, 301)),  # 300 ids
                    "bench": _entries(range(301, 401)),  # 100 ids
                    "substitutions": [],
                }
            },
            "200": {
                "formation": {
                    "lineup": _entries(range(401, 601)),  # 200 ids
                    "bench": _entries(range(601, 604)),  # 3 ids
                    "substitutions": [],
                }
            },
        },
    }
    return matches


def test_count_checks_pass_when_actual_matches_published_reference() -> None:
    matches_payload = _matches_with_603_roster_union()
    events_payload = [
        {"playerId": (i % 603) + 1, "teamId": 1, "eventName": "Pass"} for i in range(643150)
    ]

    report = aggregate_england_probe(matches_payload=matches_payload, events_payload=events_payload)

    assert report.roster_player_count == 603
    assert report.counts_verified is True
    assert {c.metric: c.passed for c in report.count_checks} == {
        "matches": True,
        "events": True,
        "players": True,
    }


def test_count_checks_pass_with_603_roster_and_different_event_actor_count() -> None:
    """603 published roster players can coexist with a different (514)
    event actor count and the published-count verification still PASSes --
    the two populations are never conflated."""

    matches_payload = _matches_with_603_roster_union()
    events_payload = [
        {"playerId": (i % 514) + 1, "teamId": 1, "eventName": "Pass"} for i in range(643150)
    ]

    report = aggregate_england_probe(matches_payload=matches_payload, events_payload=events_payload)

    assert report.roster_player_count == 603
    assert report.event_actor_count == 514
    assert report.counts_verified is True
    assert {c.metric: c.passed for c in report.count_checks} == {
        "matches": True,
        "events": True,
        "players": True,
    }


def test_sentinel_player_id_never_counted_as_a_real_player() -> None:
    events_payload = [{"playerId": 0, "teamId": 1, "eventName": "Pass"}]
    report = aggregate_england_probe(matches_payload=[], events_payload=events_payload)

    assert report.event_actor_count == 0
    assert report.player_id_coverage.present == 1  # field was present, just sentinel


def test_roster_players_missing_from_players_json_reported_but_not_excluded() -> None:
    """An unresolved players.json reference is a reported data-quality gap,
    never a reason to shrink the roster population."""

    players_payload = [{"wyId": 11}, {"wyId": 21}]  # player 12 deliberately absent

    report = aggregate_england_probe(
        matches_payload=_SYNTHETIC_MATCHES,
        events_payload=_SYNTHETIC_EVENTS,
        players_payload=players_payload,
    )

    assert report.roster_player_count == 3  # unchanged: 11, 12, 21
    assert report.roster_players_missing_from_players_json == (12,)


def test_roster_players_missing_from_players_json_is_none_when_unavailable() -> None:
    report = aggregate_england_probe(
        matches_payload=_SYNTHETIC_MATCHES, events_payload=_SYNTHETIC_EVENTS
    )

    assert report.roster_players_missing_from_players_json is None


def test_event_actor_absent_from_roster_is_reported() -> None:
    matches_payload = [
        {"wyId": 1, "teamsData": {"100": {"formation": {"lineup": _entries(range(11, 12))}}}}
    ]
    events_payload = [{"playerId": 999, "teamId": 100, "eventName": "Pass"}]

    report = aggregate_england_probe(matches_payload=matches_payload, events_payload=events_payload)

    assert report.event_actors_absent_from_roster == (999,)


def test_substitutions_literal_null_string_is_treated_as_no_substitutions() -> None:
    """Real source quirk: `formation.substitutions` can be the literal
    string "null" instead of an empty list when a team made zero
    substitutions -- this must never raise or corrupt the roster count."""

    matches_payload = [
        {
            "wyId": 1,
            "teamsData": {
                "100": {
                    "formation": {
                        "lineup": _entries(range(1, 2)),
                        "bench": _entries(range(2, 3)),
                        "substitutions": "null",
                    }
                }
            },
        }
    ]

    report = aggregate_england_probe(matches_payload=matches_payload, events_payload=[])

    assert report.roster_player_count == 2
    assert report.matches_with_substitutions == 0


def test_resolve_content_path_returns_non_zip_path_unchanged(tmp_path: Path) -> None:
    json_path = tmp_path / "matches_England.json"
    json_path.write_text("[]", encoding="utf-8")

    resolved = probe_wyscout_open._resolve_content_path(json_path, tmp_path, keyword=None)

    assert resolved == json_path


def test_resolve_content_path_extracts_zip_and_finds_json_by_keyword(tmp_path: Path) -> None:
    zip_path = tmp_path / "matches.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("matches_England.json", json.dumps([{"wyId": 1}]))
        archive.writestr("matches_Spain.json", json.dumps([{"wyId": 2}]))

    resolved = probe_wyscout_open._resolve_content_path(zip_path, tmp_path, keyword="england")

    assert resolved.name == "matches_England.json"
    assert json.loads(resolved.read_text()) == [{"wyId": 1}]


def test_resolve_content_path_reuses_previously_extracted_files(tmp_path: Path) -> None:
    zip_path = tmp_path / "matches.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("matches_England.json", "[]")

    first = probe_wyscout_open._resolve_content_path(zip_path, tmp_path, keyword="england")
    first.write_text('["reused"]', encoding="utf-8")
    second = probe_wyscout_open._resolve_content_path(zip_path, tmp_path, keyword="england")

    assert second == first
    assert json.loads(second.read_text()) == ["reused"]


def test_resolve_content_path_extracts_events_zip_and_finds_england_json(tmp_path: Path) -> None:
    zip_path = tmp_path / "events.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("events_England.json", json.dumps([{"eventId": 1}]))
        archive.writestr("events_Spain.json", json.dumps([{"eventId": 2}]))
        archive.writestr("events_Italy.json", json.dumps([{"eventId": 3}]))

    resolved = probe_wyscout_open._resolve_content_path(zip_path, tmp_path, keyword="england")

    assert resolved.name == "events_England.json"
    assert json.loads(resolved.read_text()) == [{"eventId": 1}]


def test_resolve_content_path_raises_when_no_entry_matches_keyword(tmp_path: Path) -> None:
    zip_path = tmp_path / "matches.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("matches_Spain.json", "[]")
        archive.writestr("matches_Italy.json", "[]")

    with pytest.raises(WyscoutProbeError):
        probe_wyscout_open._resolve_content_path(zip_path, tmp_path, keyword="england")


def test_resolve_content_path_raises_when_multiple_entries_match_keyword(tmp_path: Path) -> None:
    zip_path = tmp_path / "matches.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("matches_England.json", "[]")
        archive.writestr("matches_New_England.json", "[]")

    with pytest.raises(WyscoutProbeError):
        probe_wyscout_open._resolve_content_path(zip_path, tmp_path, keyword="england")


def _md5(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


class _ArchiveArticleClient(WyscoutOpenDataClient):
    """Reproduces the real Figshare shape: one archive, no per-country files."""

    def __init__(
        self,
        *,
        article_id: int,
        article_title: str,
        file_id: int,
        file_name: str,
        zip_bytes: bytes,
    ) -> None:
        super().__init__(max_attempts=1)
        self._article_id = article_id
        self._article_title = article_title
        self._file_id = file_id
        self._file_name = file_name
        self._zip_bytes = zip_bytes

    def _request_once(self, url: str) -> tuple[int, bytes]:
        if "collections/4415000/articles" in url:
            payload: object = [
                {"id": self._article_id, "title": self._article_title, "doi": None, "url": "u"}
            ]
        elif f"articles/{self._article_id}" in url:
            payload = {
                "id": self._article_id,
                "title": self._article_title,
                "doi": None,
                "files": [
                    {
                        "id": self._file_id,
                        "name": self._file_name,
                        "size": len(self._zip_bytes),
                        "download_url": f"https://ndownloader.figshare.com/files/{self._file_id}",
                        "computed_md5": None,
                    }
                ],
            }
        else:
            raise AssertionError(f"unexpected URL {url}")
        return 200, json.dumps(payload).encode()

    def _download_once(self, url: str, destination: Path) -> tuple[int, str]:
        destination.write_bytes(self._zip_bytes)
        return len(self._zip_bytes), _md5(self._zip_bytes)


def _build_zip_bytes(entries: dict[str, str], tmp_path: Path, name: str) -> bytes:
    zip_path = tmp_path / name
    with zipfile.ZipFile(zip_path, "w") as archive:
        for entry_name, content in entries.items():
            archive.writestr(entry_name, content)
    return zip_path.read_bytes()


def test_matches_article_archive_fallback_selects_england_end_to_end(tmp_path: Path) -> None:
    """Reproduces and fixes: article 7770422 ('Matches') has 0 files matching
    keyword 'england' -- the real Matches article publishes one `matches.zip`
    archive, not per-country article-level files."""

    zip_bytes = _build_zip_bytes(
        {
            "matches_England.json": json.dumps([{"wyId": 1}, {"wyId": 2}]),
            "matches_Spain.json": json.dumps([{"wyId": 3}]),
        },
        tmp_path,
        "source_matches.zip",
    )
    client = _ArchiveArticleClient(
        article_id=7770422,
        article_title="Matches",
        file_id=500,
        file_name="matches.zip",
        zip_bytes=zip_bytes,
    )
    cache_dir = tmp_path / "cache"

    asset = client.fetch_asset(
        collection_id=4415000, article_title="Matches", cache_dir=cache_dir, keyword="england"
    )
    payload = probe_wyscout_open._load_json_asset(asset.local_path, cache_dir, keyword="england")

    assert asset.file_name == "matches.zip"
    assert payload == [{"wyId": 1}, {"wyId": 2}]


def test_events_article_archive_fallback_selects_england_end_to_end(tmp_path: Path) -> None:
    zip_bytes = _build_zip_bytes(
        {
            "events_England.json": json.dumps([{"eventId": 1}]),
            "events_Germany.json": json.dumps([{"eventId": 2}]),
            "events_France.json": json.dumps([{"eventId": 3}]),
        },
        tmp_path,
        "source_events.zip",
    )
    client = _ArchiveArticleClient(
        article_id=7770423,
        article_title="Events",
        file_id=501,
        file_name="events.zip",
        zip_bytes=zip_bytes,
    )
    cache_dir = tmp_path / "cache"

    asset = client.fetch_asset(
        collection_id=4415000, article_title="Events", cache_dir=cache_dir, keyword="england"
    )
    payload = probe_wyscout_open._load_json_asset(asset.local_path, cache_dir, keyword="england")

    assert asset.file_name == "events.zip"
    assert payload == [{"eventId": 1}]


def test_load_tag_mapping_parses_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "tags2name.csv"
    csv_path.write_text("Tag,Description\n101,Goal\n102,Own goal\n", encoding="utf-8")

    mapping = probe_wyscout_open._load_tag_mapping(csv_path, tmp_path)

    assert mapping.get(101) == "Goal"
    assert mapping.get(102) == "Own goal"


def test_cache_dir_argument_defaults_to_data_cache_wyscout_open() -> None:
    args = build_parser().parse_args([])
    assert args.cache_dir == probe_wyscout_open.DEFAULT_CACHE_DIR


def test_cache_dir_argument_is_overridable(tmp_path: Path) -> None:
    args = build_parser().parse_args(["--cache-dir", str(tmp_path)])
    assert args.cache_dir == tmp_path


def test_probe_module_has_no_database_dependency() -> None:
    source = inspect.getsource(probe_wyscout_open)
    assert "DATABASE_URL" not in source
    assert "psycopg" not in source
    assert "football_intelligence.db" not in source
    assert "import football_intelligence.db" not in source
