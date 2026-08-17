"""Block 20C.2a acquisition job: populate the pinned, cached StatsBomb Open
Data local snapshot for Premier League 2015/16.

Fetches (through `StatsBombOpenDataClient`, pinned to
`DEFAULT_PINNED_REVISION` unless `--ref` overrides it -- never a
master-tracking fetch), caches with SHA-256 integrity metadata
(`providers.statsbomb_open_cache`), and writes a source-snapshot manifest
(`providers.statsbomb_open_manifest`) recording exactly what was cached.

This is acquisition only: no NormalizedObservation rows, no database
connection, no ingestion. `jobs.audit_statsbomb_mapping` reads the resulting
cache to validate the empirical Metric Catalog mapping.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from football_intelligence.providers.statsbomb_open import (
    DEFAULT_PINNED_REVISION,
    StatsBombOpenDataClient,
)
from football_intelligence.providers.statsbomb_open_cache import (
    CachedFetch,
    StatsBombCacheError,
    fetch_json_cached,
    revision_cache_dir,
)
from football_intelligence.providers.statsbomb_open_manifest import (
    EXPOSURE_POLICY_INTERNAL_ONLY,
    PROVIDER_NAME,
    ROLE_HISTORICAL_DEEP,
    UPSTREAM_REPOSITORY,
    CachedFileRecord,
    SourceSnapshotManifest,
    write_manifest,
)

COMPETITION_ID = 2
SEASON_ID = 27
COMPETITION_NAME = "Premier League"
SEASON_NAME = "2015/2016"
EXPECTED_MATCH_COUNT = 380

DEFAULT_CACHE_ROOT = Path("data/cache/statsbomb-open")
_DOWNLOAD_WORKERS = 8


class StatsBombFetchError(RuntimeError):
    """The acquisition job could not complete a required step."""


def _match_ids(matches_payload: Any) -> list[int]:
    if not isinstance(matches_payload, list):
        return []
    ids: list[int] = []
    for item in matches_payload:
        if isinstance(item, dict) and isinstance(item.get("match_id"), int):
            ids.append(item["match_id"])
    return ids


def run_fetch(
    *,
    cache_root: Path,
    ref: str = DEFAULT_PINNED_REVISION,
    limit: int | None = None,
    workers: int = _DOWNLOAD_WORKERS,
) -> tuple[SourceSnapshotManifest, Path]:
    client = StatsBombOpenDataClient(ref=ref)

    try:
        competitions_fetch = fetch_json_cached(client, "competitions.json", cache_root=cache_root)
        matches_fetch = fetch_json_cached(
            client, f"matches/{COMPETITION_ID}/{SEASON_ID}.json", cache_root=cache_root
        )
    except StatsBombCacheError as exc:
        raise StatsBombFetchError(f"could not acquire competitions/matches: {exc}") from exc

    match_ids = _match_ids(matches_fetch.payload)
    if limit is not None:
        match_ids = match_ids[:limit]

    cached: list[CachedFetch] = [competitions_fetch, matches_fetch]
    errors: list[str] = []

    def _fetch_match_files(match_id: int) -> list[CachedFetch]:
        results: list[CachedFetch] = []
        for api_path in (f"events/{match_id}.json", f"lineups/{match_id}.json"):
            results.append(fetch_json_cached(client, api_path, cache_root=cache_root))
        return results

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_match_files, match_id): match_id for match_id in match_ids}
        for future in as_completed(futures):
            match_id = futures[future]
            try:
                cached.extend(future.result())
            except StatsBombCacheError as exc:
                errors.append(f"match {match_id}: {exc}")

    if errors:
        raise StatsBombFetchError(
            f"{len(errors)} match file(s) failed to fetch/cache: {errors[:5]}"
            + (" ..." if len(errors) > 5 else "")
        )

    revision_dir = revision_cache_dir(cache_root, client.source_revision)
    manifest = SourceSnapshotManifest(
        provider=PROVIDER_NAME,
        upstream_repository=UPSTREAM_REPOSITORY,
        pinned_commit_sha=client.source_revision,
        competition_id=COMPETITION_ID,
        season_id=SEASON_ID,
        competition_name=COMPETITION_NAME,
        season_name=SEASON_NAME,
        role=ROLE_HISTORICAL_DEEP,
        exposure_policy=EXPOSURE_POLICY_INTERNAL_ONLY,
        fetched_at=datetime.now(UTC),
        expected_match_count=EXPECTED_MATCH_COUNT,
        files=tuple(
            sorted(
                (
                    CachedFileRecord(
                        api_path=fetch.api_path, sha256=fetch.sha256, byte_size=fetch.byte_size
                    )
                    for fetch in cached
                ),
                key=lambda record: record.api_path,
            )
        ),
    )
    manifest_file = write_manifest(revision_dir, manifest)
    return manifest, manifest_file


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Block 20C.2a acquisition job: fetch and cache the pinned StatsBomb "
            "Open Data Premier League 2015/16 snapshot (competitions.json, the "
            "match list, and every match's events+lineups). Never fetches "
            "master -- pinned to a fixed commit SHA."
        )
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--ref", type=str, default=DEFAULT_PINNED_REVISION)
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only fetch this many matches (for quick/partial runs); omit for the full season.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        manifest, manifest_file = run_fetch(
            cache_root=args.cache_dir, ref=args.ref, limit=args.limit
        )
    except StatsBombFetchError as exc:
        print(f"STATSBOMB FETCH: FAIL - {exc}")
        raise SystemExit(1) from exc

    print("=== STATSBOMB OPEN DATA FETCH (Block 20C.2a) ===")
    print(f"pinned commit sha: {manifest.pinned_commit_sha}")
    print(f"competition: {manifest.competition_name} ({manifest.competition_id})")
    print(f"season: {manifest.season_name} ({manifest.season_id})")
    print(f"role: {manifest.role}")
    print(f"exposure policy: {manifest.exposure_policy}")
    print(f"files cached: {len(manifest.files)}")
    print(f"manifest: {manifest_file}")


if __name__ == "__main__":
    main()
