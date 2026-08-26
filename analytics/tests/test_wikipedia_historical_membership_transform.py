from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from football_intelligence.jobs import collect_wikipedia_historical_squads
from football_intelligence.jobs.collect_wikipedia_historical_squads import (
    HistoricalRevisionRequest,
)
from football_intelligence.jobs.transform_wikipedia_historical_memberships import (
    WikipediaMembershipTransformError,
    transform_snapshot,
)


def _request(title: str, target: str = "2024-09-06T23:59:59Z") -> HistoricalRevisionRequest:
    return HistoricalRevisionRequest(
        article_title=title,
        snapshot_target=datetime.fromisoformat(target.replace("Z", "+00:00")),
    )


def _response_bytes(
    *,
    title: str,
    revision_id: int,
    revision_timestamp: str = "2024-09-01T12:00:00Z",
    content: str | None = None,
) -> bytes:
    if content is None:
        content = (
            "== Current squad ==\n"
            "{{fs player\n| no = 1\n| name = [[Player One]]\n}}\n"
            "{{fs player\n| no = 2\n| name = Player Two\n}}\n"
        )
    return json.dumps(
        {
            "batchcomplete": True,
            "query": {
                "pages": [
                    {
                        "pageid": revision_id + 1000,
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


def _build_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    raw_by_title: dict[str, bytes],
) -> Path:
    def fake_fetch(request: HistoricalRevisionRequest) -> bytes:
        return raw_by_title[request.canonical_article_title]

    monkeypatch.setattr(collect_wikipedia_historical_squads, "_fetch_revision", fake_fetch)
    collect_wikipedia_historical_squads.collect_snapshot(
        requests=tuple(_request(title) for title in reversed(tuple(raw_by_title))),
        snapshot_id="wikipedia-membership-transform-test",
        competition_codes=("ARG_LPF",),
        season_labels=("2024",),
        output_dir=tmp_path,
    )
    return tmp_path / "manifest.json"


def _rewrite_index_and_refresh_manifest(
    root: Path,
    mutate: object,
) -> None:
    index_path = root / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert callable(mutate)
    mutate(index)
    index_bytes = (json.dumps(index, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )
    index_path.write_bytes(index_bytes)

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    index_entry = next(item for item in manifest["files"] if item["path"] == "index.json")
    index_entry["sha256"] = hashlib.sha256(index_bytes).hexdigest()
    index_entry["byte_size"] = len(index_bytes)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_transform_emits_deterministic_memberships_and_missing_evidence_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _build_snapshot(
        tmp_path,
        monkeypatch,
        raw_by_title={
            "Club A": _response_bytes(title="Club A", revision_id=101),
            "Club B": _response_bytes(
                title="Club B",
                revision_id=202,
                content="== History ==\nNo accepted active squad here.\n",
            ),
        },
    )

    first = transform_snapshot(manifest_path=manifest_path, base_dir=tmp_path)
    second = transform_snapshot(manifest_path=manifest_path, base_dir=tmp_path)

    assert first.passed
    assert first == second
    assert first.requests_total == 2
    assert first.requests_with_evidence == 1
    assert first.requests_without_evidence == 1
    assert first.rows_emitted == 2
    assert first.rows_with_player_article == 1
    assert [item.requested_article_title for item in first.requests] == ["Club A", "Club B"]
    assert first.requests[1].active_squad_evidence is False
    assert first.requests[1].active_squad_observations == 0
    assert [item.provider_player_key for item in first.memberships] == [
        "article:player one",
        "name:player two",
    ]
    assert len({item.membership_observation_key for item in first.memberships}) == 2
    assert all(len(item.membership_observation_key) == 24 for item in first.memberships)


def test_transform_fails_before_parsing_when_snapshot_checksum_is_tampered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _build_snapshot(
        tmp_path,
        monkeypatch,
        raw_by_title={"Club A": _response_bytes(title="Club A", revision_id=101)},
    )
    raw_file = next((tmp_path / "revisions").glob("*.json"))
    raw_file.write_bytes(raw_file.read_bytes() + b"\n")

    with pytest.raises(WikipediaMembershipTransformError, match="snapshot integrity failed"):
        transform_snapshot(manifest_path=manifest_path, base_dir=tmp_path)


def test_transform_rejects_raw_file_not_declared_in_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _build_snapshot(
        tmp_path,
        monkeypatch,
        raw_by_title={"Club A": _response_bytes(title="Club A", revision_id=101)},
    )

    def mutate(index: dict[str, object]) -> None:
        requests = index["requests"]
        assert isinstance(requests, list)
        request = requests[0]
        assert isinstance(request, dict)
        request["raw_file"] = "revisions/not-in-manifest.json"

    _rewrite_index_and_refresh_manifest(tmp_path, mutate)

    with pytest.raises(WikipediaMembershipTransformError, match="not listed in manifest"):
        transform_snapshot(manifest_path=manifest_path, base_dir=tmp_path)


def test_transform_rejects_index_revision_id_mismatch_against_raw_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _build_snapshot(
        tmp_path,
        monkeypatch,
        raw_by_title={"Club A": _response_bytes(title="Club A", revision_id=101)},
    )

    def mutate(index: dict[str, object]) -> None:
        requests = index["requests"]
        assert isinstance(requests, list)
        request = requests[0]
        assert isinstance(request, dict)
        request["revision_id"] = 999

    _rewrite_index_and_refresh_manifest(tmp_path, mutate)

    with pytest.raises(WikipediaMembershipTransformError, match="revision id mismatch"):
        transform_snapshot(manifest_path=manifest_path, base_dir=tmp_path)


def test_transform_rejects_index_request_id_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _build_snapshot(
        tmp_path,
        monkeypatch,
        raw_by_title={"Club A": _response_bytes(title="Club A", revision_id=101)},
    )

    def mutate(index: dict[str, object]) -> None:
        requests = index["requests"]
        assert isinstance(requests, list)
        request = requests[0]
        assert isinstance(request, dict)
        request["request_id"] = "0000000000000000"

    _rewrite_index_and_refresh_manifest(tmp_path, mutate)

    with pytest.raises(WikipediaMembershipTransformError, match="request_id does not match"):
        transform_snapshot(manifest_path=manifest_path, base_dir=tmp_path)


def test_transform_does_not_treat_loan_annotation_link_as_player_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _build_snapshot(
        tmp_path,
        monkeypatch,
        raw_by_title={
            "Barracas Central": _response_bytes(
                title="Barracas Central",
                revision_id=303,
                content=(
                    "== Current squad ==\n"
                    "{{fs player\n"
                    "| no = 7\n"
                    "| name = Lucas Lopez (on loan from [[CA Nueva Chicago]])\n"
                    "}}\n"
                ),
            )
        },
    )

    report = transform_snapshot(manifest_path=manifest_path, base_dir=tmp_path)

    assert report.rows_emitted == 1
    assert report.rows_with_player_article == 0
    assert report.memberships[0].player_article_title is None
    assert report.memberships[0].provider_player_key.startswith("name:lucas lopez")
    assert "nueva chicago" not in report.memberships[0].provider_player_key
