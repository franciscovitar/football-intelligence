"""Collect immutable historical Wikipedia article revisions for squad evidence.

The collector freezes exact raw MediaWiki API responses for an explicit bounded
set of ``article title + snapshot target`` requests. It never renders historical
pages, expands live templates, searches player names, creates canonical players,
or writes product/database state.

Each collection writes:

- one raw JSON response per requested historical revision;
- ``index.json`` mapping each request to the resolved article/revision and the
  retained parser's active-squad evidence status;
- the provider-independent static snapshot ``manifest.json`` with SHA-256 and
  byte-size integrity metadata for every cached file.

Wikipedia text remains subject to Wikimedia's applicable CC BY-SA attribution
requirements. Source approval/promotion remains a separate repository gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from football_intelligence.ingestion.static_snapshot import (
    SnapshotFile,
    StaticSnapshotManifest,
)
from football_intelligence.providers.wikipedia_historical_squads import (
    LICENCE,
    MEDIAWIKI_REVISIONS_REFERENCE,
    SOURCE_CODE,
    WIKIMEDIA_TERMS_REFERENCE,
    WikipediaHistoricalSquadError,
    parse_historical_active_squad_revision,
)

MEDIAWIKI_API_ENDPOINT = "https://en.wikipedia.org/w/api.php"
MAX_REQUESTS = 120
HTTP_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 4
DEFAULT_RETRY_DELAY_SECONDS = 5.0
MAX_RETRY_DELAY_SECONDS = 30.0
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
USER_AGENT = "FootballIntelligence/0.1 (+https://github.com/franciscovitar/football-intelligence)"


class WikipediaHistoricalCollectionError(RuntimeError):
    """A bounded historical Wikipedia snapshot could not be collected safely."""


@dataclass(frozen=True, slots=True)
class HistoricalRevisionRequest:
    """One explicit article revision lookup at or before a target timestamp."""

    article_title: str
    snapshot_target: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.article_title, str) or not self.article_title.strip():
            raise WikipediaHistoricalCollectionError("article_title must be a non-blank string")
        if self.snapshot_target.tzinfo is None or self.snapshot_target.utcoffset() is None:
            raise WikipediaHistoricalCollectionError("snapshot_target must be timezone-aware")

    @property
    def canonical_article_title(self) -> str:
        return self.article_title.strip()

    @property
    def canonical_snapshot_target(self) -> datetime:
        return self.snapshot_target.astimezone(UTC).replace(microsecond=0)

    @property
    def api_snapshot_target(self) -> str:
        return _format_utc(self.canonical_snapshot_target)

    @property
    def stable_request_id(self) -> str:
        raw = f"{self.canonical_article_title}\n{self.api_snapshot_target}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class _ParsedRevision:
    page_id: int | None
    resolved_title: str
    revision_id: int
    revision_timestamp: str
    wikitext: str
    active_squad_heading: str | None
    active_squad_observations: int


@dataclass(frozen=True, slots=True)
class _FetchedRevision:
    request: HistoricalRevisionRequest
    raw: bytes
    parsed: _ParsedRevision
    raw_file: str


def collect_snapshot(
    *,
    requests: tuple[HistoricalRevisionRequest, ...],
    snapshot_id: str,
    competition_codes: tuple[str, ...],
    season_labels: tuple[str, ...],
    output_dir: Path,
) -> StaticSnapshotManifest:
    """Collect a bounded immutable revision snapshot without overwriting evidence."""

    canonical_requests = _canonical_requests(requests)
    _validate_scope(snapshot_id, competition_codes, season_labels)
    if len(canonical_requests) > MAX_REQUESTS:
        raise WikipediaHistoricalCollectionError(
            f"bounded collector accepts at most {MAX_REQUESTS} revision requests, "
            f"got {len(canonical_requests)}"
        )

    raw_files = tuple(
        f"revisions/{index:03d}-{revision_request.stable_request_id}.json"
        for index, revision_request in enumerate(canonical_requests, start=1)
    )
    _preflight_output_paths(output_dir=output_dir, raw_files=raw_files)

    fetched: list[_FetchedRevision] = []
    for revision_request, raw_file in zip(canonical_requests, raw_files, strict=True):
        raw = _fetch_revision(revision_request)
        parsed = _parse_revision_response(raw, revision_request)
        fetched.append(
            _FetchedRevision(
                request=revision_request,
                raw=raw,
                parsed=parsed,
                raw_file=raw_file,
            )
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    index_path = output_dir / "index.json"

    snapshot_files: list[SnapshotFile] = []
    for item in fetched:
        target = output_dir / item.raw_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.raw)
        snapshot_files.append(_snapshot_file(item.raw_file, item.raw))

    acquired_at = datetime.now(UTC)
    index_payload = _index_payload(
        snapshot_id=snapshot_id.strip(),
        acquired_at=acquired_at,
        fetched=fetched,
    )
    index_bytes = (
        json.dumps(index_payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    index_path.write_bytes(index_bytes)
    snapshot_files.append(_snapshot_file("index.json", index_bytes))

    manifest = StaticSnapshotManifest(
        snapshot_id=snapshot_id.strip(),
        source_code=SOURCE_CODE,
        acquired_at=acquired_at,
        source_reference=MEDIAWIKI_API_ENDPOINT,
        competition_codes=tuple(sorted(set(competition_codes))),
        season_labels=tuple(sorted(set(season_labels))),
        data_grains=("player_season",),
        files=tuple(sorted(snapshot_files, key=lambda item: item.path)),
        notes=(
            f"Exact historical MediaWiki revision snapshot; {LICENCE}; attribution required; "
            f"bounded to {MAX_REQUESTS} explicit revision requests per run; raw API responses "
            f"retained; API contract {MEDIAWIKI_REVISIONS_REFERENCE}; terms "
            f"{WIKIMEDIA_TERMS_REFERENCE}; not a live product dependency."
        ),
    )
    manifest_path.write_text(
        json.dumps(_manifest_payload(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _preflight_output_paths(*, output_dir: Path, raw_files: tuple[str, ...]) -> None:
    """Fail before network access if collection would overwrite existing evidence."""

    protected_paths = (
        output_dir / "manifest.json",
        output_dir / "index.json",
        *(output_dir / raw_file for raw_file in raw_files),
    )
    existing = next((path for path in protected_paths if path.exists()), None)
    if existing is not None:
        raise WikipediaHistoricalCollectionError(
            f"refusing to overwrite existing snapshot evidence {existing}"
        )


def _fetch_revision(revision_request: HistoricalRevisionRequest) -> bytes:
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "maxlag": "5",
        "prop": "revisions",
        "titles": revision_request.canonical_article_title,
        "redirects": "1",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "rvlimit": "1",
        "rvstart": revision_request.api_snapshot_target,
        "rvdir": "older",
    }
    url = f"{MEDIAWIKI_API_ENDPOINT}?{urlencode(params)}"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                return cast(bytes, response.read())
        except HTTPError as exc:
            retry_after = exc.headers.get("Retry-After")
            if exc.code not in RETRYABLE_HTTP_STATUSES or attempt == MAX_ATTEMPTS:
                suffix = f"; Retry-After={retry_after}" if retry_after else ""
                raise WikipediaHistoricalCollectionError(
                    f"{revision_request.canonical_article_title} HTTP {exc.code}{suffix}"
                ) from exc
            time.sleep(_retry_delay(attempt=attempt, retry_after=retry_after))
        except (URLError, TimeoutError) as exc:
            if attempt == MAX_ATTEMPTS:
                reason = exc.reason if isinstance(exc, URLError) else str(exc)
                raise WikipediaHistoricalCollectionError(
                    f"{revision_request.canonical_article_title} network error: {reason}"
                ) from exc
            time.sleep(_retry_delay(attempt=attempt, retry_after=None))

    raise AssertionError("bounded Wikipedia fetch exhausted without returning or raising")


def _parse_revision_response(
    raw: bytes, revision_request: HistoricalRevisionRequest
) -> _ParsedRevision:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WikipediaHistoricalCollectionError("MediaWiki response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise WikipediaHistoricalCollectionError("MediaWiki response root is not a JSON object")

    query = payload.get("query")
    if not isinstance(query, dict):
        raise WikipediaHistoricalCollectionError("MediaWiki response is missing query object")
    pages = query.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
        raise WikipediaHistoricalCollectionError(
            "MediaWiki response must contain exactly one page object"
        )
    page = cast(dict[str, Any], pages[0])
    if page.get("missing") is not None:
        raise WikipediaHistoricalCollectionError(
            f"Wikipedia article is missing: {revision_request.canonical_article_title}"
        )

    resolved_title = page.get("title")
    if not isinstance(resolved_title, str) or not resolved_title.strip():
        raise WikipediaHistoricalCollectionError("MediaWiki page has no usable resolved title")
    page_id_raw = page.get("pageid")
    page_id: int | None = page_id_raw if type(page_id_raw) is int else None

    revisions = page.get("revisions")
    if not isinstance(revisions, list) or len(revisions) != 1 or not isinstance(revisions[0], dict):
        raise WikipediaHistoricalCollectionError(
            f"no unique historical revision at or before {revision_request.api_snapshot_target} "
            f"for {revision_request.canonical_article_title}"
        )
    revision = cast(dict[str, Any], revisions[0])
    revision_id = revision.get("revid")
    if not isinstance(revision_id, int) or isinstance(revision_id, bool) or revision_id <= 0:
        raise WikipediaHistoricalCollectionError("historical revision has no positive revision id")
    revision_timestamp = revision.get("timestamp")
    if not isinstance(revision_timestamp, str) or not revision_timestamp.strip():
        raise WikipediaHistoricalCollectionError("historical revision has no timestamp")
    parsed_revision_timestamp = _parse_datetime(
        revision_timestamp, field_name="historical revision timestamp"
    )
    if parsed_revision_timestamp > revision_request.canonical_snapshot_target:
        raise WikipediaHistoricalCollectionError(
            "MediaWiki returned a revision newer than the requested snapshot target"
        )

    slots = revision.get("slots")
    if not isinstance(slots, dict):
        raise WikipediaHistoricalCollectionError("historical revision has no slots object")
    main_slot = slots.get("main")
    if not isinstance(main_slot, dict):
        raise WikipediaHistoricalCollectionError("historical revision has no main slot")
    wikitext = main_slot.get("content")
    if not isinstance(wikitext, str):
        raise WikipediaHistoricalCollectionError(
            "historical revision main slot has no string content"
        )

    try:
        snapshot = parse_historical_active_squad_revision(
            wikitext,
            article_title=resolved_title,
            revision_id=revision_id,
            revision_timestamp=revision_timestamp,
            snapshot_target=revision_request.api_snapshot_target,
        )
    except WikipediaHistoricalSquadError as exc:
        raise WikipediaHistoricalCollectionError(
            f"historical squad parser rejected revision {revision_id}: {exc}"
        ) from exc

    return _ParsedRevision(
        page_id=page_id,
        resolved_title=resolved_title.strip(),
        revision_id=revision_id,
        revision_timestamp=revision_timestamp.strip(),
        wikitext=wikitext,
        active_squad_heading=snapshot.heading if snapshot is not None else None,
        active_squad_observations=(len(snapshot.observations) if snapshot is not None else 0),
    )


def _canonical_requests(
    requests: tuple[HistoricalRevisionRequest, ...],
) -> tuple[HistoricalRevisionRequest, ...]:
    if not requests:
        raise WikipediaHistoricalCollectionError("at least one revision request is required")
    canonical: dict[tuple[str, str], HistoricalRevisionRequest] = {}
    for request in requests:
        if not isinstance(request, HistoricalRevisionRequest):
            raise WikipediaHistoricalCollectionError(
                "requests must contain only HistoricalRevisionRequest values"
            )
        normalized = HistoricalRevisionRequest(
            article_title=request.canonical_article_title,
            snapshot_target=request.canonical_snapshot_target,
        )
        canonical[(normalized.canonical_article_title, normalized.api_snapshot_target)] = normalized
    return tuple(
        sorted(
            canonical.values(),
            key=lambda item: (
                item.canonical_article_title.casefold(),
                item.canonical_article_title,
                item.api_snapshot_target,
            ),
        )
    )


def _retry_delay(*, attempt: int, retry_after: str | None) -> float:
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), MAX_RETRY_DELAY_SECONDS)
    exponential = DEFAULT_RETRY_DELAY_SECONDS
    for _ in range(attempt - 1):
        exponential *= 2.0
    return min(exponential, MAX_RETRY_DELAY_SECONDS)


def _validate_scope(
    snapshot_id: str,
    competition_codes: tuple[str, ...],
    season_labels: tuple[str, ...],
) -> None:
    if not isinstance(snapshot_id, str) or not snapshot_id.strip():
        raise WikipediaHistoricalCollectionError("snapshot_id must be non-blank")
    if not competition_codes or any(
        not isinstance(value, str) or not value.strip() for value in competition_codes
    ):
        raise WikipediaHistoricalCollectionError(
            "at least one non-blank competition code is required"
        )
    if not season_labels or any(
        not isinstance(value, str) or not value.strip() for value in season_labels
    ):
        raise WikipediaHistoricalCollectionError("at least one non-blank season label is required")


def _snapshot_file(path: str, raw: bytes) -> SnapshotFile:
    return SnapshotFile(
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
    )


def _index_payload(
    *,
    snapshot_id: str,
    acquired_at: datetime,
    fetched: list[_FetchedRevision],
) -> dict[str, object]:
    return {
        "snapshot_id": snapshot_id,
        "source_code": SOURCE_CODE,
        "source_reference": MEDIAWIKI_API_ENDPOINT,
        "acquired_at": acquired_at.isoformat(),
        "licence": LICENCE,
        "attribution_required": True,
        "requests": [
            {
                "request_id": item.request.stable_request_id,
                "requested_title": item.request.canonical_article_title,
                "resolved_title": item.parsed.resolved_title,
                "snapshot_target": item.request.api_snapshot_target,
                "page_id": item.parsed.page_id,
                "revision_id": item.parsed.revision_id,
                "revision_timestamp": item.parsed.revision_timestamp,
                "raw_file": item.raw_file,
                "active_squad_evidence": item.parsed.active_squad_heading is not None,
                "active_squad_heading": item.parsed.active_squad_heading,
                "active_squad_observations": item.parsed.active_squad_observations,
            }
            for item in fetched
        ],
    }


def _manifest_payload(manifest: StaticSnapshotManifest) -> dict[str, object]:
    return {
        "snapshot_id": manifest.snapshot_id,
        "source_code": manifest.source_code,
        "acquired_at": manifest.acquired_at.isoformat(),
        "source_reference": manifest.source_reference,
        "competition_codes": list(manifest.competition_codes),
        "season_labels": list(manifest.season_labels),
        "data_grains": list(manifest.data_grains),
        "files": [asdict(file) for file in manifest.files],
        "notes": manifest.notes,
    }


def _parse_request_file(path: Path) -> tuple[HistoricalRevisionRequest, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise WikipediaHistoricalCollectionError("request file must be a JSON array")
    requests: list[HistoricalRevisionRequest] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, dict):
            raise WikipediaHistoricalCollectionError(
                f"request file item {index} must be a JSON object"
            )
        raw_dict = cast(dict[str, Any], raw)
        unknown = set(raw_dict) - {"article_title", "snapshot_target"}
        if unknown:
            raise WikipediaHistoricalCollectionError(
                f"request file item {index} contains unknown fields: {sorted(unknown)!r}"
            )
        article_title = raw_dict.get("article_title")
        target_raw = raw_dict.get("snapshot_target")
        if not isinstance(article_title, str) or not article_title.strip():
            raise WikipediaHistoricalCollectionError(
                f"request file item {index}.article_title must be a non-blank string"
            )
        if not isinstance(target_raw, str) or not target_raw.strip():
            raise WikipediaHistoricalCollectionError(
                f"request file item {index}.snapshot_target must be an ISO-8601 string"
            )
        requests.append(
            HistoricalRevisionRequest(
                article_title=article_title,
                snapshot_target=_parse_datetime(
                    target_raw,
                    field_name=f"request file item {index}.snapshot_target",
                ),
            )
        )
    return tuple(requests)


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise WikipediaHistoricalCollectionError(
            f"{field_name} must be ISO-8601, got {value!r}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WikipediaHistoricalCollectionError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC).replace(microsecond=0)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect a bounded immutable historical Wikipedia revision snapshot."
    )
    parser.add_argument(
        "--request-file",
        type=Path,
        required=True,
        help="JSON array of {article_title, snapshot_target} requests",
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--competition", action="append", required=True)
    parser.add_argument("--season", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        requests = _parse_request_file(args.request_file)
        manifest = collect_snapshot(
            requests=requests,
            snapshot_id=args.snapshot_id,
            competition_codes=tuple(args.competition),
            season_labels=tuple(args.season),
            output_dir=args.output_dir,
        )
    except (OSError, json.JSONDecodeError, WikipediaHistoricalCollectionError) as exc:
        raise SystemExit(f"WIKIPEDIA HISTORICAL COLLECTION: FAIL - {exc}") from exc

    print(
        f"WIKIPEDIA HISTORICAL COLLECTION: PASS snapshot={manifest.snapshot_id} "
        f"files={len(manifest.files)} manifest={args.output_dir / 'manifest.json'}"
    )


if __name__ == "__main__":
    main()
