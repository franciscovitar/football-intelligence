from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from urllib.error import HTTPError

import pytest

from football_intelligence.providers.wyscout_open import (
    FigshareArticleDetail,
    FigshareFile,
    WyscoutOpenDataArchiveError,
    WyscoutOpenDataClient,
    WyscoutOpenDataHttpError,
    WyscoutOpenDataResponseError,
    safe_extract_zip,
)


def _md5(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


class _JsonStubClient(WyscoutOpenDataClient):
    """Stub that serves canned JSON keyed by a URL substring."""

    def __init__(self, responses: dict[str, object], *, max_attempts: int = 1) -> None:
        super().__init__(max_attempts=max_attempts)
        self._responses = responses
        self.requested_urls: list[str] = []

    def _request_once(self, url: str) -> tuple[int, bytes]:
        self.requested_urls.append(url)
        for fragment, payload in self._responses.items():
            if fragment in url:
                return 200, json.dumps(payload).encode()
        raise AssertionError(f"unexpected URL {url}")


class _PaginatedArticlesClient(WyscoutOpenDataClient):
    def __init__(self, pages: list[list[dict[str, object]]], *, page_size: int) -> None:
        super().__init__(max_attempts=1, list_page_size=page_size)
        self._pages = pages
        self.requested_urls: list[str] = []

    def _request_once(self, url: str) -> tuple[int, bytes]:
        self.requested_urls.append(url)
        page_number = int(url.split("page=")[1].split("&")[0])
        payload = self._pages[page_number - 1] if page_number <= len(self._pages) else []
        return 200, json.dumps(payload).encode()


class _RecordingDownloadClient(WyscoutOpenDataClient):
    def __init__(self, *, body: bytes = b"hello world") -> None:
        super().__init__(max_attempts=1)
        self._body = body
        self.download_calls = 0

    def _download_once(self, url: str, destination: Path) -> tuple[int, str]:
        self.download_calls += 1
        destination.write_bytes(self._body)
        return len(self._body), _md5(self._body)


# -- Discovery: pagination + exact-title matching -------------------------


def test_list_collection_articles_paginates_until_short_page() -> None:
    page1 = [
        {"id": 1, "title": "A", "doi": None, "url": "u1"},
        {"id": 2, "title": "B", "doi": None, "url": "u2"},
    ]
    page2 = [{"id": 3, "title": "C", "doi": None, "url": "u3"}]
    client = _PaginatedArticlesClient([page1, page2], page_size=2)

    articles = client.list_collection_articles(4415000)

    assert [a.id for a in articles] == [1, 2, 3]
    assert len(client.requested_urls) == 2


def test_find_article_by_title_exact_match_only() -> None:
    client = _JsonStubClient(
        {
            "collections/4415000/articles": [
                {"id": 5, "title": "Events", "doi": None, "url": "u"},
                {"id": 6, "title": "Events (old)", "doi": None, "url": "u"},
            ]
        }
    )

    article = client.find_article_by_title(4415000, "Events")

    assert article.id == 5


def test_find_article_by_title_raises_when_no_exact_match() -> None:
    client = _JsonStubClient({"collections/4415000/articles": []})

    with pytest.raises(WyscoutOpenDataResponseError):
        client.find_article_by_title(4415000, "Events")


# -- Article/file metadata parsing -----------------------------------------


def test_get_article_parses_files() -> None:
    client = _JsonStubClient(
        {
            "articles/10": {
                "id": 10,
                "title": "Events",
                "doi": "10.6084/x",
                "files": [
                    {
                        "id": 100,
                        "name": "events_England.json.zip",
                        "size": 123,
                        "download_url": "https://ndownloader.figshare.com/files/100",
                        "computed_md5": "abc123",
                    }
                ],
            }
        }
    )

    article = client.get_article(10)

    assert article.id == 10
    assert article.doi == "10.6084/x"
    assert len(article.files) == 1
    assert article.files[0].name == "events_England.json.zip"
    assert article.files[0].computed_md5 == "abc123"


def test_get_article_rejects_non_object_payload() -> None:
    client = _JsonStubClient({"articles/10": []})

    with pytest.raises(WyscoutOpenDataResponseError):
        client.get_article(10)


def test_get_article_rejects_missing_files_array() -> None:
    client = _JsonStubClient({"articles/10": {"id": 10, "title": "Events"}})

    with pytest.raises(WyscoutOpenDataResponseError):
        client.get_article(10)


def test_list_collection_articles_rejects_non_list_payload() -> None:
    client = _JsonStubClient({"collections/4415000/articles": {"not": "a list"}})

    with pytest.raises(WyscoutOpenDataResponseError):
        client.list_collection_articles(4415000)


# -- select_file -------------------------------------------------------


def _detail_with_files(*names: str) -> FigshareArticleDetail:
    return FigshareArticleDetail(
        id=1,
        title="Matches",
        doi=None,
        files=tuple(
            FigshareFile(
                id=idx, name=name, size=10, download_url=f"https://x/{idx}", computed_md5=None
            )
            for idx, name in enumerate(names, start=1)
        ),
    )


def test_select_file_returns_only_file_when_unambiguous() -> None:
    article = _detail_with_files("competitions.json")
    file = WyscoutOpenDataClient.select_file(article)
    assert file.name == "competitions.json"


def test_select_file_by_exact_name() -> None:
    article = _detail_with_files("matches_England.json", "matches_Spain.json")
    file = WyscoutOpenDataClient.select_file(article, file_name="matches_Spain.json")
    assert file.name == "matches_Spain.json"


def test_select_file_by_keyword() -> None:
    article = _detail_with_files("matches_England.json", "matches_Spain.json")
    file = WyscoutOpenDataClient.select_file(article, keyword="england")
    assert file.name == "matches_England.json"


def test_select_file_raises_when_ambiguous_without_disambiguator() -> None:
    article = _detail_with_files("matches_England.json", "matches_Spain.json")
    with pytest.raises(WyscoutOpenDataResponseError):
        WyscoutOpenDataClient.select_file(article)


def test_select_file_raises_when_keyword_matches_nothing() -> None:
    article = _detail_with_files("matches_England.json")
    with pytest.raises(WyscoutOpenDataResponseError):
        WyscoutOpenDataClient.select_file(article, keyword="germany")


# -- select_file: archive fallback (real Figshare "Matches"/"Events" shape) --
#
# The authoritative Wyscout Figshare articles do not publish one file per
# country -- they publish a single archive (e.g. `matches.zip`) covering
# every competition, so no article-level file name ever contains "england".
# This reproduces the real probe failure:
# "article 7770422 ('Matches') has 0 files matching keyword 'england';
# expected exactly one".


def test_select_file_falls_back_to_sole_archive_when_keyword_matches_nothing() -> None:
    article = _detail_with_files("matches.zip")

    file = WyscoutOpenDataClient.select_file(article, keyword="england")

    assert file.name == "matches.zip"


def test_select_file_raises_when_keyword_matches_nothing_and_no_archive_exists() -> None:
    article = _detail_with_files("matches.json")

    with pytest.raises(WyscoutOpenDataResponseError):
        WyscoutOpenDataClient.select_file(article, keyword="england")


def test_select_file_raises_when_keyword_matches_nothing_and_archives_are_ambiguous() -> None:
    article = _detail_with_files("matches_part1.zip", "matches_part2.zip")

    with pytest.raises(WyscoutOpenDataResponseError):
        WyscoutOpenDataClient.select_file(article, keyword="england")


def test_fetch_asset_selects_and_downloads_sole_archive_when_keyword_matches_nothing(
    tmp_path: Path,
) -> None:
    """End-to-end reproduction of the real Matches-article acquisition failure."""

    class ArchiveArticleClient(WyscoutOpenDataClient):
        def __init__(self) -> None:
            super().__init__(max_attempts=1)

        def _request_once(self, url: str) -> tuple[int, bytes]:
            if "collections/4415000/articles" in url:
                payload: object = [{"id": 7770422, "title": "Matches", "doi": None, "url": "u"}]
            elif "articles/7770422" in url:
                payload = {
                    "id": 7770422,
                    "title": "Matches",
                    "doi": None,
                    "files": [
                        {
                            "id": 500,
                            "name": "matches.zip",
                            "size": 999,
                            "download_url": "https://ndownloader.figshare.com/files/500",
                            "computed_md5": None,
                        }
                    ],
                }
            else:
                raise AssertionError(f"unexpected URL {url}")
            return 200, json.dumps(payload).encode()

        def _download_once(self, url: str, destination: Path) -> tuple[int, str]:
            body = b"pretend-zip-bytes"
            destination.write_bytes(body)
            return len(body), _md5(body)

    client = ArchiveArticleClient()

    asset = client.fetch_asset(
        collection_id=4415000,
        article_title="Matches",
        cache_dir=tmp_path,
        keyword="england",
    )

    assert asset.file_name == "matches.zip"
    assert asset.article_id == 7770422
    assert asset.local_path.read_bytes() == b"pretend-zip-bytes"


# -- Retry / error behavior -------------------------------------------------


def test_get_json_maps_404_to_response_error() -> None:
    class NotFoundClient(WyscoutOpenDataClient):
        def __init__(self) -> None:
            super().__init__(max_attempts=1)

        def _request_once(self, url: str) -> tuple[int, bytes]:
            raise HTTPError(url, 404, "Not Found", None, None)  # type: ignore[arg-type]

    client = NotFoundClient()
    with pytest.raises(WyscoutOpenDataResponseError):
        client.get_article(999)


def test_get_json_retries_retryable_status_then_succeeds() -> None:
    class FlakyClient(WyscoutOpenDataClient):
        def __init__(self) -> None:
            super().__init__(max_attempts=3)
            self.attempts = 0

        def _request_once(self, url: str) -> tuple[int, bytes]:
            self.attempts += 1
            if self.attempts < 2:
                raise HTTPError(url, 503, "Service Unavailable", None, None)  # type: ignore[arg-type]
            return 200, json.dumps({"id": 1, "title": "x", "doi": None, "files": []}).encode()

    client = FlakyClient()
    article = client.get_article(1)
    assert article.id == 1
    assert client.attempts == 2


def test_get_json_raises_after_max_attempts() -> None:
    class AlwaysFailingClient(WyscoutOpenDataClient):
        def __init__(self) -> None:
            super().__init__(max_attempts=2)

        def _request_once(self, url: str) -> tuple[int, bytes]:
            raise HTTPError(url, 500, "Server Error", None, None)  # type: ignore[arg-type]

    client = AlwaysFailingClient()
    with pytest.raises(WyscoutOpenDataHttpError):
        client.get_article(1)


def test_get_json_rejects_invalid_json_body() -> None:
    class BrokenClient(WyscoutOpenDataClient):
        def __init__(self) -> None:
            super().__init__(max_attempts=1)

        def _request_once(self, url: str) -> tuple[int, bytes]:
            return 200, b"not json"

    client = BrokenClient()
    with pytest.raises(WyscoutOpenDataResponseError):
        client.get_article(1)


# -- Download + cache reuse -------------------------------------------------


def test_download_file_writes_and_verifies_checksum(tmp_path: Path) -> None:
    client = _RecordingDownloadClient()
    body = b"hello world"
    file = FigshareFile(
        id=1, name="x.json", size=len(body), download_url="https://x", computed_md5=_md5(body)
    )
    destination = tmp_path / "x.json"

    outcome = client.download_file(file, destination)

    assert outcome.from_cache is False
    assert outcome.checksum_verified is True
    assert client.download_calls == 1
    assert destination.read_bytes() == body


def test_download_file_reuses_valid_cache_without_downloading_again(tmp_path: Path) -> None:
    client = _RecordingDownloadClient()
    body = b"hello world"
    file = FigshareFile(
        id=1, name="x.json", size=len(body), download_url="https://x", computed_md5=_md5(body)
    )
    destination = tmp_path / "x.json"

    client.download_file(file, destination)
    outcome = client.download_file(file, destination)

    assert outcome.from_cache is True
    assert outcome.checksum_verified is True
    assert client.download_calls == 1


def test_download_file_redownloads_when_cached_checksum_is_stale(tmp_path: Path) -> None:
    destination = tmp_path / "x.json"
    destination.write_bytes(b"stale content")
    client = _RecordingDownloadClient()
    body = b"hello world"
    file = FigshareFile(
        id=1, name="x.json", size=len(body), download_url="https://x", computed_md5=_md5(body)
    )

    outcome = client.download_file(file, destination)

    assert outcome.from_cache is False
    assert client.download_calls == 1
    assert destination.read_bytes() == body


def test_download_file_reuses_cache_by_size_when_no_checksum_available(tmp_path: Path) -> None:
    destination = tmp_path / "x.json"
    body = b"hello world"
    destination.write_bytes(body)
    client = _RecordingDownloadClient(body=body)
    file = FigshareFile(
        id=1, name="x.json", size=len(body), download_url="https://x", computed_md5=None
    )

    outcome = client.download_file(file, destination)

    assert outcome.from_cache is True
    assert outcome.checksum_verified is False
    assert client.download_calls == 0


def test_download_file_rejects_checksum_mismatch(tmp_path: Path) -> None:
    class CorruptClient(WyscoutOpenDataClient):
        def __init__(self) -> None:
            super().__init__(max_attempts=1)

        def _download_once(self, url: str, destination: Path) -> tuple[int, str]:
            destination.write_bytes(b"corrupt")
            return 7, "deadbeefdeadbeefdeadbeefdeadbeef"

    client = CorruptClient()
    file = FigshareFile(
        id=1,
        name="x.json",
        size=11,
        download_url="https://x",
        computed_md5="0" * 32,
    )
    destination = tmp_path / "x.json"

    with pytest.raises(WyscoutOpenDataResponseError):
        client.download_file(file, destination)
    assert not destination.exists()


# -- Safe ZIP extraction -------------------------------------------------


def test_safe_extract_zip_extracts_normal_entries(tmp_path: Path) -> None:
    zip_path = tmp_path / "a.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("data/events_England.json", "[]")

    extracted = safe_extract_zip(zip_path, tmp_path / "out")

    assert len(extracted) == 1
    assert extracted[0].read_text() == "[]"
    assert extracted[0].is_relative_to((tmp_path / "out").resolve())


@pytest.mark.parametrize(
    "member_name",
    [
        "../evil.txt",
        "../../outside.json",
        "/etc/passwd",
        "C:/evil.txt",
        "a/../../evil.txt",
        "a\\..\\..\\evil.txt",
    ],
)
def test_safe_extract_zip_rejects_traversal_and_absolute_paths(
    tmp_path: Path, member_name: str
) -> None:
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr(member_name, "bad")

    with pytest.raises(WyscoutOpenDataArchiveError):
        safe_extract_zip(zip_path, tmp_path / "out")
