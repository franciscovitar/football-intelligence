from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError

import pytest

from football_intelligence.ingestion.static_snapshot import (
    load_static_snapshot_manifest,
    verify_static_snapshot_files,
)
from football_intelligence.jobs import collect_wikipedia_historical_squads
from football_intelligence.jobs.collect_wikipedia_historical_squads import (
    HistoricalRevisionRequest,
    WikipediaHistoricalCollectionError,
)


def _request(title: str = "Example Club", target: str = "2024-09-06T23:59:59Z"):
    return HistoricalRevisionRequest(
        article_title=title,
        snapshot_target=datetime.fromisoformat(target.replace("Z", "+00:00")),
    )


def _response_bytes(
    *,
    title: str = "Example Club",
    revision_id: int = 123456,
    revision_timestamp: str = "2024-09-01T12:00:00Z",
    content: str = "== Current squad ==\n{{fs player\n| no = 1\n| name = [[Player One]]\n}}\n",
) -> bytes:
    return json.dumps(
        {
            "batchcomplete": True,
            "query": {
                "pages": [
                    {
                        "pageid": 101,
                        "ns": 0,
                        "title": title,
                        "revisions": [
                            {
                                "revid": revision_id,
                                "timestamp": revision_timestamp,
                                "slots": {
                                    "main": {
                                        "contentmodel": "wikitext",
                                        "contentformat": "text/x-wiki",
                                        "content": content,
                                    }
                                },
                            }
                        ],
                    }
                ]
            },
        },
        sort_keys=True,
    ).encode("utf-8")


def test_collector_writes_verifiable_raw_snapshot_and_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_by_title = {
        "Club A": _response_bytes(title="Club A", revision_id=111),
        "Club B": _response_bytes(
            title="Club B",
            revision_id=222,
            content="== History ==\nNo active-squad table in this revision.\n",
        ),
    }

    def fake_fetch(request: HistoricalRevisionRequest) -> bytes:
        return raw_by_title[request.canonical_article_title]

    monkeypatch.setattr(collect_wikipedia_historical_squads, "_fetch_revision", fake_fetch)
    manifest = collect_wikipedia_historical_squads.collect_snapshot(
        requests=(
            _request("Club B"),
            _request("Club A"),
            _request("Club A"),
        ),
        snapshot_id="wikipedia-arg-lpf-2024-test",
        competition_codes=("ARG_LPF",),
        season_labels=("2024",),
        output_dir=tmp_path,
    )

    loaded = load_static_snapshot_manifest(tmp_path / "manifest.json")
    verification = verify_static_snapshot_files(loaded, base_dir=tmp_path)
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))

    assert manifest.source_code == "wikipedia"
    assert manifest.data_grains == ("player_season",)
    assert len(manifest.files) == 3
    assert verification.passed
    assert [item["requested_title"] for item in index["requests"]] == ["Club A", "Club B"]
    assert index["requests"][0]["active_squad_evidence"] is True
    assert index["requests"][0]["active_squad_observations"] == 1
    assert index["requests"][1]["active_squad_evidence"] is False
    assert index["requests"][1]["active_squad_observations"] == 0

    raw_files = [path for path in tmp_path.rglob("*.json") if path.parent.name == "revisions"]
    assert len(raw_files) == 2
    assert {path.read_bytes() for path in raw_files} == set(raw_by_title.values())


def test_collector_is_hard_bounded_before_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def fake_fetch(request: HistoricalRevisionRequest) -> bytes:
        nonlocal calls
        del request
        calls += 1
        return _response_bytes()

    monkeypatch.setattr(collect_wikipedia_historical_squads, "_fetch_revision", fake_fetch)
    requests = tuple(_request(f"Club {index}") for index in range(121))

    with pytest.raises(WikipediaHistoricalCollectionError, match="at most 120"):
        collect_wikipedia_historical_squads.collect_snapshot(
            requests=requests,
            snapshot_id="too-large",
            competition_codes=("ARG_LPF",),
            season_labels=("2024",),
            output_dir=tmp_path,
        )

    assert calls == 0


def test_collector_refuses_overwrite_before_network_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    (tmp_path / "manifest.json").write_text("existing evidence\n", encoding="utf-8")

    def fake_fetch(request: HistoricalRevisionRequest) -> bytes:
        nonlocal calls
        del request
        calls += 1
        return _response_bytes()

    monkeypatch.setattr(collect_wikipedia_historical_squads, "_fetch_revision", fake_fetch)

    with pytest.raises(WikipediaHistoricalCollectionError, match="refusing to overwrite"):
        collect_wikipedia_historical_squads.collect_snapshot(
            requests=(_request(),),
            snapshot_id="already-exists",
            competition_codes=("ARG_LPF",),
            season_labels=("2024",),
            output_dir=tmp_path,
        )

    assert calls == 0


def test_fetch_revision_retries_transient_503(monkeypatch: pytest.MonkeyPatch) -> None:
    encoded = _response_bytes()
    calls = 0

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return encoded

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        nonlocal calls
        del request, timeout
        calls += 1
        if calls == 1:
            raise HTTPError(
                "https://en.wikipedia.org/w/api.php",
                503,
                "Service Unavailable",
                {"Retry-After": "0"},
                None,
            )
        return FakeResponse()

    monkeypatch.setattr(collect_wikipedia_historical_squads, "urlopen", fake_urlopen)

    raw = collect_wikipedia_historical_squads._fetch_revision(_request())

    assert calls == 2
    assert raw == encoded


def test_revision_newer_than_snapshot_target_is_rejected() -> None:
    request = _request(target="2024-09-06T23:59:59Z")
    raw = _response_bytes(revision_timestamp="2024-09-07T00:00:00Z")

    with pytest.raises(WikipediaHistoricalCollectionError, match="newer than"):
        collect_wikipedia_historical_squads._parse_revision_response(raw, request)


def test_missing_article_is_rejected() -> None:
    raw = json.dumps(
        {
            "query": {
                "pages": [
                    {
                        "ns": 0,
                        "title": "Missing Club",
                        "missing": True,
                    }
                ]
            }
        }
    ).encode("utf-8")

    with pytest.raises(WikipediaHistoricalCollectionError, match="article is missing"):
        collect_wikipedia_historical_squads._parse_revision_response(raw, _request("Missing Club"))


def test_request_target_must_be_timezone_aware() -> None:
    with pytest.raises(WikipediaHistoricalCollectionError, match="timezone-aware"):
        HistoricalRevisionRequest(
            article_title="Example Club",
            snapshot_target=datetime(2024, 9, 6, 23, 59, 59),
        )


def test_request_ids_are_stable_after_utc_normalization() -> None:
    first = HistoricalRevisionRequest(
        article_title=" Example Club ",
        snapshot_target=datetime(2024, 9, 6, 20, 59, 59, tzinfo=datetime.now().astimezone().tzinfo),
    )
    second = HistoricalRevisionRequest(
        article_title="Example Club",
        snapshot_target=first.canonical_snapshot_target,
    )

    assert second.snapshot_target.tzinfo is UTC
    assert first.stable_request_id == second.stable_request_id
