"""Collect a bounded Wikidata player-profile snapshot from known item IDs.

This job deliberately uses Wikidata's ``Special:EntityData`` Linked Data
interface for a small, explicit list of already-known QIDs. It is not a search
crawler and does not make Wikidata a runtime dependency of Football
Intelligence. The downloaded entity documents remain local evidence and are
covered by the generic static-snapshot manifest/checksum contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from football_intelligence.ingestion.static_snapshot import (
    SnapshotFile,
    StaticSnapshotManifest,
)
from football_intelligence.providers.wikidata_profiles import (
    ENTITY_DATA_REFERENCE,
    LICENCE,
    SOURCE_CODE,
    WikidataProfileError,
    parse_wikidata_entity_document,
    validate_qid,
)

MAX_QIDS = 50
HTTP_TIMEOUT_SECONDS = 30
MAX_ATTEMPTS = 4
DEFAULT_RETRY_DELAY_SECONDS = 5.0
MAX_RETRY_DELAY_SECONDS = 30.0
RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
USER_AGENT = "FootballIntelligence/0.1 (+https://github.com/franciscovitar/football-intelligence)"


class WikidataCollectionError(RuntimeError):
    """A bounded Wikidata snapshot could not be collected safely."""


def collect_snapshot(
    *,
    qids: tuple[str, ...],
    snapshot_id: str,
    competition_codes: tuple[str, ...],
    season_labels: tuple[str, ...],
    output_dir: Path,
) -> StaticSnapshotManifest:
    canonical_qids = _canonical_qids(qids)
    _validate_scope(snapshot_id, competition_codes, season_labels)
    if len(canonical_qids) > MAX_QIDS:
        raise WikidataCollectionError(
            f"bounded collector accepts at most {MAX_QIDS} QIDs per snapshot, "
            f"got {len(canonical_qids)}"
        )

    fetched: list[tuple[str, bytes]] = []
    for qid in canonical_qids:
        raw = _fetch_entity(qid)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WikidataCollectionError(f"{qid} response is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise WikidataCollectionError(f"{qid} response root is not a JSON object")
        try:
            parse_wikidata_entity_document(payload, expected_qid=qid)
        except WikidataProfileError as exc:
            raise WikidataCollectionError(f"{qid} entity validation failed: {exc}") from exc
        fetched.append((qid, raw))

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        raise WikidataCollectionError(f"refusing to overwrite existing manifest {manifest_path}")

    snapshot_files: list[SnapshotFile] = []
    for qid, raw in fetched:
        filename = f"{qid}.json"
        target = output_dir / filename
        if target.exists():
            raise WikidataCollectionError(f"refusing to overwrite existing entity file {target}")
        target.write_bytes(raw)
        snapshot_files.append(
            SnapshotFile(
                path=filename,
                sha256=hashlib.sha256(raw).hexdigest(),
                byte_size=len(raw),
            )
        )

    manifest = StaticSnapshotManifest(
        snapshot_id=snapshot_id.strip(),
        source_code=SOURCE_CODE,
        acquired_at=datetime.now(UTC),
        source_reference=ENTITY_DATA_REFERENCE,
        competition_codes=tuple(sorted(set(competition_codes))),
        season_labels=tuple(sorted(set(season_labels))),
        data_grains=("player_profile",),
        files=tuple(sorted(snapshot_files, key=lambda item: item.path)),
        notes=(
            f"Known-QID Linked Data snapshot; {LICENCE}; bounded to {MAX_QIDS} entities per run; "
            "not a live product dependency."
        ),
    )
    manifest_path.write_text(
        json.dumps(_manifest_payload(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _fetch_entity(qid: str) -> bytes:
    url = f"{ENTITY_DATA_REFERENCE}/{qid}.json"
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
                raise WikidataCollectionError(f"{qid} HTTP {exc.code}{suffix}") from exc
            time.sleep(_retry_delay(attempt=attempt, retry_after=retry_after))
        except (URLError, TimeoutError) as exc:
            if attempt == MAX_ATTEMPTS:
                reason = exc.reason if isinstance(exc, URLError) else str(exc)
                raise WikidataCollectionError(f"{qid} network error: {reason}") from exc
            time.sleep(_retry_delay(attempt=attempt, retry_after=None))

    raise AssertionError("bounded Wikidata fetch exhausted without returning or raising")


def _retry_delay(*, attempt: int, retry_after: str | None) -> float:
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), MAX_RETRY_DELAY_SECONDS)
    exponential = DEFAULT_RETRY_DELAY_SECONDS
    for _ in range(attempt - 1):
        exponential *= 2.0
    return min(exponential, MAX_RETRY_DELAY_SECONDS)


def _canonical_qids(qids: tuple[str, ...]) -> tuple[str, ...]:
    if not qids:
        raise WikidataCollectionError("at least one QID is required")
    try:
        return tuple(sorted({validate_qid(qid) for qid in qids}))
    except WikidataProfileError as exc:
        raise WikidataCollectionError(str(exc)) from exc


def _validate_scope(
    snapshot_id: str,
    competition_codes: tuple[str, ...],
    season_labels: tuple[str, ...],
) -> None:
    if not snapshot_id.strip():
        raise WikidataCollectionError("snapshot_id must be non-blank")
    if not competition_codes or any(not value.strip() for value in competition_codes):
        raise WikidataCollectionError("at least one non-blank competition code is required")
    if not season_labels or any(not value.strip() for value in season_labels):
        raise WikidataCollectionError("at least one non-blank season label is required")


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


def _load_qid_file(path: Path) -> tuple[str, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise WikidataCollectionError("QID file must be a JSON array of strings")
    qids: list[str] = []
    for item in payload:
        if not isinstance(item, str):
            raise WikidataCollectionError("QID file must be a JSON array of strings")
        qids.append(item)
    return tuple(qids)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect a small static Wikidata player-profile snapshot from known QIDs."
    )
    parser.add_argument("--qid", action="append", default=[], help="Known Wikidata QID; repeatable")
    parser.add_argument("--qid-file", type=Path, default=None, help="JSON array of known QIDs")
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--competition", action="append", required=True)
    parser.add_argument("--season", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    qids = tuple(args.qid)
    if args.qid_file is not None:
        try:
            qids += _load_qid_file(args.qid_file)
        except (OSError, json.JSONDecodeError, WikidataCollectionError) as exc:
            raise SystemExit(f"WIKIDATA COLLECTION: FAIL - {exc}") from exc
    try:
        manifest = collect_snapshot(
            qids=qids,
            snapshot_id=args.snapshot_id,
            competition_codes=tuple(args.competition),
            season_labels=tuple(args.season),
            output_dir=args.output_dir,
        )
    except (OSError, WikidataCollectionError) as exc:
        raise SystemExit(f"WIKIDATA COLLECTION: FAIL - {exc}") from exc

    print(
        f"WIKIDATA COLLECTION: PASS snapshot={manifest.snapshot_id} "
        f"entities={len(manifest.files)} manifest={args.output_dir / 'manifest.json'}"
    )


if __name__ == "__main__":
    main()
