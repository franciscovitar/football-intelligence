"""Minimal, server-side Wyscout Open Data (Figshare) client.

Wyscout Open Data (Pappalardo et al., "A public data set of spatio-temporal
match events in soccer competitions", Scientific Data 6, 236 (2019),
DOI 10.1038/s41597-019-0247-7) is published as Figshare collection
`4415000` (DOI `10.6084/m9.figshare.c.4415000.v5`, CC BY 4.0). This client
only talks to Figshare's own public, documented, unauthenticated API
(https://api.figshare.com/v2) -- no scraping, no hidden endpoints, no
signed S3 URLs hardcoded ahead of time. It is historical/deep evidence
only, never a current-season feed.
"""

from __future__ import annotations

import hashlib
import json
import time
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

JsonValue = Any

_DOWNLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB
_DEFAULT_LIST_PAGE_SIZE = 100
_MAX_LIST_PAGES = 20
_RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


class WyscoutOpenDataError(RuntimeError):
    """Base provider error."""


class WyscoutOpenDataHttpError(WyscoutOpenDataError):
    """HTTP/network error after bounded retries."""


class WyscoutOpenDataResponseError(WyscoutOpenDataError):
    """Figshare returned an unusable/unexpected payload."""


class WyscoutOpenDataArchiveError(WyscoutOpenDataError):
    """A downloaded archive contained an unsafe or unusable entry."""


@dataclass(frozen=True)
class FigshareArticleSummary:
    id: int
    title: str
    doi: str | None
    url: str


@dataclass(frozen=True)
class FigshareFile:
    id: int
    name: str
    size: int
    download_url: str
    computed_md5: str | None


@dataclass(frozen=True)
class FigshareArticleDetail:
    id: int
    title: str
    doi: str | None
    files: tuple[FigshareFile, ...]


@dataclass(frozen=True)
class DownloadOutcome:
    byte_size: int
    from_cache: bool
    checksum_verified: bool


@dataclass(frozen=True)
class WyscoutOpenAsset:
    """Provenance-preserving record of one downloaded Figshare file."""

    collection_id: int
    article_id: int
    article_title: str
    article_doi: str | None
    file_id: int
    file_name: str
    download_url: str
    source_checksum: str | None
    local_path: Path
    byte_size: int
    checksum_verified: bool
    from_cache: bool


class WyscoutOpenDataClient:
    """Small synchronous client for the Figshare public API (v2)."""

    def __init__(
        self,
        *,
        base_url: str = "https://api.figshare.com/v2",
        timeout_seconds: float = 30.0,
        max_attempts: int = 3,
        user_agent: str = "football-intelligence/0.1",
        list_page_size: int = _DEFAULT_LIST_PAGE_SIZE,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if list_page_size < 1:
            raise ValueError("list_page_size must be at least 1")
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_attempts = max_attempts
        self._user_agent = user_agent
        self._list_page_size = list_page_size

    # -- Discovery -----------------------------------------------------

    def list_collection_articles(self, collection_id: int) -> list[FigshareArticleSummary]:
        articles: list[FigshareArticleSummary] = []
        for page in range(1, _MAX_LIST_PAGES + 1):
            payload = self._get_json(
                f"collections/{collection_id}/articles",
                {"page": page, "page_size": self._list_page_size},
            )
            if not isinstance(payload, list):
                raise WyscoutOpenDataResponseError(
                    f"Figshare collection {collection_id} articles response was not a list"
                )
            if not payload:
                break
            articles.extend(_parse_article_summary(item) for item in payload)
            if len(payload) < self._list_page_size:
                break
        return articles

    def find_article_by_title(self, collection_id: int, title: str) -> FigshareArticleSummary:
        target = title.strip()
        for article in self.list_collection_articles(collection_id):
            if article.title == target:
                return article
        raise WyscoutOpenDataResponseError(
            f"no Figshare article titled {title!r} found in collection {collection_id}"
        )

    def get_article(self, article_id: int) -> FigshareArticleDetail:
        payload = self._get_json(f"articles/{article_id}")
        return _parse_article_detail(payload)

    @staticmethod
    def select_file(
        article: FigshareArticleDetail,
        *,
        file_name: str | None = None,
        keyword: str | None = None,
    ) -> FigshareFile:
        if file_name is not None:
            matches = [f for f in article.files if f.name == file_name]
            if len(matches) != 1:
                raise WyscoutOpenDataResponseError(
                    f"article {article.id} ({article.title!r}) has no unique file named "
                    f"{file_name!r} ({len(matches)} matches)"
                )
            return matches[0]
        if keyword is not None:
            needle = keyword.casefold()
            matches = [f for f in article.files if needle in f.name.casefold()]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                raise WyscoutOpenDataResponseError(
                    f"article {article.id} ({article.title!r}) has {len(matches)} files "
                    f"matching keyword {keyword!r}; expected exactly one"
                )
            # No article-level file matches the keyword directly. The
            # authoritative Wyscout Figshare articles (e.g. "Matches",
            # "Events") instead publish one archive covering every
            # competition/country -- fall back to that archive so its
            # contents can be inspected after extraction (see
            # `probe_wyscout_open._resolve_content_path`). The fallback is
            # itself strict: an ambiguous or missing archive still fails
            # clearly rather than silently picking a file.
            archive_matches = [f for f in article.files if f.name.casefold().endswith(".zip")]
            if len(archive_matches) == 1:
                return archive_matches[0]
            if len(archive_matches) > 1:
                raise WyscoutOpenDataResponseError(
                    f"article {article.id} ({article.title!r}) has no file matching keyword "
                    f"{keyword!r} and {len(archive_matches)} ambiguous archive candidates; "
                    "cannot select one deterministically"
                )
            raise WyscoutOpenDataResponseError(
                f"article {article.id} ({article.title!r}) has no file matching keyword "
                f"{keyword!r} and no archive to fall back to"
            )
        if len(article.files) != 1:
            raise WyscoutOpenDataResponseError(
                f"article {article.id} ({article.title!r}) has {len(article.files)} files; "
                "pass file_name or keyword to disambiguate"
            )
        return article.files[0]

    # -- Download --------------------------------------------------------

    def download_file(
        self,
        file: FigshareFile,
        destination: Path,
        *,
        force: bool = False,
    ) -> DownloadOutcome:
        if not force:
            cached = self._reuse_cache(file, destination)
            if cached is not None:
                return cached

        destination.parent.mkdir(parents=True, exist_ok=True)
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                byte_size, digest = self._download_once(file.download_url, destination)
            except (HTTPError, TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise WyscoutOpenDataHttpError(
                        f"Figshare download failed for file {file.id} ({file.name}): {exc}"
                    ) from exc
                time.sleep(float(attempt))
                continue

            if file.computed_md5 is not None and digest != file.computed_md5:
                destination.unlink(missing_ok=True)
                raise WyscoutOpenDataResponseError(
                    f"downloaded file {file.name} checksum mismatch "
                    f"(expected {file.computed_md5}, got {digest})"
                )
            return DownloadOutcome(
                byte_size=byte_size,
                from_cache=False,
                checksum_verified=file.computed_md5 is not None,
            )

        raise WyscoutOpenDataHttpError(f"Figshare download failed for file {file.id}: {last_error}")

    def fetch_asset(
        self,
        *,
        collection_id: int,
        article_title: str,
        cache_dir: Path,
        file_name: str | None = None,
        keyword: str | None = None,
    ) -> WyscoutOpenAsset:
        article_summary = self.find_article_by_title(collection_id, article_title)
        article = self.get_article(article_summary.id)
        file = self.select_file(article, file_name=file_name, keyword=keyword)
        destination = cache_dir / f"{file.id}_{_sanitize_filename(file.name)}"
        outcome = self.download_file(file, destination)
        return WyscoutOpenAsset(
            collection_id=collection_id,
            article_id=article.id,
            article_title=article.title,
            article_doi=article.doi,
            file_id=file.id,
            file_name=file.name,
            download_url=file.download_url,
            source_checksum=file.computed_md5,
            local_path=destination,
            byte_size=outcome.byte_size,
            checksum_verified=outcome.checksum_verified,
            from_cache=outcome.from_cache,
        )

    def _reuse_cache(self, file: FigshareFile, destination: Path) -> DownloadOutcome | None:
        if not destination.exists():
            return None
        if file.computed_md5 is not None:
            if _md5_of_file(destination) == file.computed_md5:
                return DownloadOutcome(
                    byte_size=destination.stat().st_size,
                    from_cache=True,
                    checksum_verified=True,
                )
            return None
        if file.size > 0 and destination.stat().st_size == file.size:
            return DownloadOutcome(byte_size=file.size, from_cache=True, checksum_verified=False)
        return None

    # -- Transport ---------------------------------------------------------

    def _get_json(self, path: str, params: Mapping[str, Any] | None = None) -> JsonValue:
        query_items = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{self._base_url}/{path.strip('/')}"
        if query_items:
            url = f"{url}?{urlencode(query_items)}"

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                _status_code, body = self._request_once(url)
                return self._decode_json(body)
            except HTTPError as exc:
                last_error = exc
                if exc.code == 404:
                    raise WyscoutOpenDataResponseError(
                        f"Figshare has no resource at {path}"
                    ) from exc
                if exc.code not in _RETRYABLE_STATUSES or attempt == self._max_attempts:
                    raise WyscoutOpenDataHttpError(f"Figshare HTTP {exc.code} for {path}") from exc
                time.sleep(float(attempt))
            except (TimeoutError, URLError) as exc:
                last_error = exc
                if attempt == self._max_attempts:
                    raise WyscoutOpenDataHttpError(
                        f"Figshare transport error for {path}: {exc}"
                    ) from exc
                time.sleep(float(attempt))

        raise WyscoutOpenDataHttpError(f"Figshare request failed for {path}: {last_error}")

    def _request_once(self, url: str) -> tuple[int, bytes]:
        request = Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": self._user_agent},
        )
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
            status = int(response.status)
            body = response.read()
        return status, body

    def _download_once(self, url: str, destination: Path) -> tuple[int, str]:
        request = Request(url, method="GET", headers={"User-Agent": self._user_agent})
        tmp_path = destination.with_name(destination.name + ".part")
        hasher = hashlib.md5(usedforsecurity=False)
        byte_size = 0
        with (
            urlopen(request, timeout=self._timeout_seconds) as response,  # noqa: S310
            tmp_path.open("wb") as handle,
        ):
            while True:
                chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                hasher.update(chunk)
                byte_size += len(chunk)
        tmp_path.replace(destination)
        return byte_size, hasher.hexdigest()

    @staticmethod
    def _decode_json(body: bytes) -> JsonValue:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WyscoutOpenDataResponseError("Figshare returned invalid JSON") from exc


def _sanitize_filename(name: str) -> str:
    return name.replace("/", "_").replace("\\", "_")


def _md5_of_file(path: Path) -> str:
    hasher = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_DOWNLOAD_CHUNK_SIZE), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _parse_article_summary(item: JsonValue) -> FigshareArticleSummary:
    if not isinstance(item, dict):
        raise WyscoutOpenDataResponseError("Figshare article summary was not an object")
    article_id = item.get("id")
    title = item.get("title")
    if not isinstance(article_id, int) or not isinstance(title, str) or not title.strip():
        raise WyscoutOpenDataResponseError("Figshare article summary missing id/title")
    doi = item.get("doi")
    url = item.get("url")
    return FigshareArticleSummary(
        id=article_id,
        title=title,
        doi=doi if isinstance(doi, str) and doi.strip() else None,
        url=url if isinstance(url, str) else "",
    )


def _parse_article_detail(payload: JsonValue) -> FigshareArticleDetail:
    if not isinstance(payload, dict):
        raise WyscoutOpenDataResponseError("Figshare article detail was not an object")
    article_id = payload.get("id")
    title = payload.get("title")
    if not isinstance(article_id, int) or not isinstance(title, str):
        raise WyscoutOpenDataResponseError("Figshare article detail missing id/title")
    files_raw = payload.get("files")
    if not isinstance(files_raw, list):
        raise WyscoutOpenDataResponseError(f"Figshare article {article_id} has no files array")
    doi = payload.get("doi")
    files = tuple(_parse_file(item) for item in files_raw)
    return FigshareArticleDetail(
        id=article_id,
        title=title,
        doi=doi if isinstance(doi, str) and doi.strip() else None,
        files=files,
    )


def _parse_file(item: JsonValue) -> FigshareFile:
    if not isinstance(item, dict):
        raise WyscoutOpenDataResponseError("Figshare file entry was not an object")
    file_id = item.get("id")
    name = item.get("name")
    download_url = item.get("download_url")
    if not isinstance(file_id, int):
        raise WyscoutOpenDataResponseError("Figshare file entry missing id/name/download_url")
    if not isinstance(name, str) or not isinstance(download_url, str):
        raise WyscoutOpenDataResponseError("Figshare file entry missing id/name/download_url")
    size = item.get("size")
    computed_md5 = item.get("computed_md5")
    checksum = computed_md5 if isinstance(computed_md5, str) and computed_md5.strip() else None
    return FigshareFile(
        id=file_id,
        name=name,
        size=size if isinstance(size, int) else 0,
        download_url=download_url,
        computed_md5=checksum,
    )


# -- Safe ZIP extraction -------------------------------------------------

_UNSAFE_ZIP_MESSAGE = "unsafe archive entry path"


def safe_extract_zip(zip_path: Path, destination_dir: Path) -> list[Path]:
    """Extract every file entry in `zip_path` under `destination_dir`.

    Rejects absolute paths, drive-letter paths, `..` traversal, and any
    entry that would resolve outside `destination_dir`. Never executes
    anything; extraction is the only side effect.
    """

    destination_root = destination_dir.resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            _validate_zip_member_name(info.filename)
            candidate = (destination_root / info.filename).resolve()
            try:
                candidate.relative_to(destination_root)
            except ValueError as exc:
                raise WyscoutOpenDataArchiveError(
                    f"{_UNSAFE_ZIP_MESSAGE}: {info.filename!r}"
                ) from exc
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, candidate.open("wb") as target:
                while True:
                    chunk = source.read(_DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    target.write(chunk)
            extracted.append(candidate)

    return extracted


def _validate_zip_member_name(member_name: str) -> None:
    if not member_name:
        raise WyscoutOpenDataArchiveError(f"{_UNSAFE_ZIP_MESSAGE}: {member_name!r}")
    if "\\" in member_name:
        raise WyscoutOpenDataArchiveError(f"{_UNSAFE_ZIP_MESSAGE}: {member_name!r}")
    if len(member_name) >= 2 and member_name[1] == ":":
        raise WyscoutOpenDataArchiveError(f"{_UNSAFE_ZIP_MESSAGE}: {member_name!r}")
    posix_path = PurePosixPath(member_name)
    if posix_path.is_absolute():
        raise WyscoutOpenDataArchiveError(f"{_UNSAFE_ZIP_MESSAGE}: {member_name!r}")
    if any(part == ".." for part in posix_path.parts):
        raise WyscoutOpenDataArchiveError(f"{_UNSAFE_ZIP_MESSAGE}: {member_name!r}")
