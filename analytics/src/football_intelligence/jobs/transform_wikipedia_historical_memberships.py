"""Transform a verified historical Wikipedia snapshot into membership evidence.

Read-only and offline. The transform consumes only bytes already frozen by the
historical Wikipedia collector. It verifies the generic static-snapshot manifest
and checksums before parsing anything, then cross-checks ``index.json`` metadata
against each raw MediaWiki response.

The output remains provider-local dated ``player_membership`` evidence. It never
creates canonical players, infers AFA registration, treats missing evidence as
zero, performs network I/O, or writes PostgreSQL state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from football_intelligence.ingestion.static_snapshot import (
    StaticSnapshotManifestError,
    load_static_snapshot_manifest,
    verify_static_snapshot_files,
)
from football_intelligence.jobs.collect_wikipedia_historical_squads import (
    HistoricalRevisionRequest,
    WikipediaHistoricalCollectionError,
    _parse_revision_response,
)
from football_intelligence.providers.wikipedia_historical_squads import (
    SOURCE_CODE,
    WikipediaHistoricalSquadError,
    parse_historical_active_squad_revision,
)


class WikipediaMembershipTransformError(RuntimeError):
    """A frozen Wikipedia membership snapshot cannot be transformed safely."""


@dataclass(frozen=True, slots=True)
class WikipediaMembershipObservation:
    """One source-local player membership observation from one historical revision."""

    source_code: str
    snapshot_id: str
    requested_article_title: str
    source_article_title: str
    revision_id: int
    revision_timestamp: str
    snapshot_target: str
    heading: str
    raw_name: str
    display_name: str
    player_article_title: str | None
    provider_player_key: str
    membership_observation_key: str
    raw_file: str


@dataclass(frozen=True, slots=True)
class WikipediaMembershipRequestDiagnostic:
    requested_article_title: str
    source_article_title: str
    revision_id: int
    revision_timestamp: str
    snapshot_target: str
    revision_lag_seconds: int
    raw_file: str
    active_squad_evidence: bool
    active_squad_heading: str | None
    active_squad_observations: int


@dataclass(frozen=True, slots=True)
class WikipediaMembershipTransformReport:
    snapshot_id: str
    source_code: str
    requests_total: int
    requests_with_evidence: int
    requests_without_evidence: int
    rows_emitted: int
    rows_with_player_article: int
    max_revision_lag_seconds: int
    requests: tuple[WikipediaMembershipRequestDiagnostic, ...]
    memberships: tuple[WikipediaMembershipObservation, ...]

    @property
    def passed(self) -> bool:
        return self.requests_total > 0


def transform_snapshot(
    *, manifest_path: Path, base_dir: Path
) -> WikipediaMembershipTransformReport:
    """Verify and transform one frozen historical Wikipedia snapshot offline."""

    try:
        manifest = load_static_snapshot_manifest(manifest_path)
    except (OSError, json.JSONDecodeError, StaticSnapshotManifestError) as exc:
        raise WikipediaMembershipTransformError(f"invalid snapshot manifest: {exc}") from exc

    if manifest.source_code != SOURCE_CODE:
        raise WikipediaMembershipTransformError(
            f"expected source_code={SOURCE_CODE!r}, got {manifest.source_code!r}"
        )
    if "player_membership" not in manifest.data_grains:
        raise WikipediaMembershipTransformError(
            "Wikipedia historical snapshot must declare player_membership grain"
        )

    verification = verify_static_snapshot_files(manifest, base_dir=base_dir)
    if not verification.passed:
        failed = [file.path for file in verification.files if not file.passed]
        raise WikipediaMembershipTransformError(
            f"snapshot integrity failed for files {failed!r}"
        )

    manifest_paths = {snapshot_file.path for snapshot_file in manifest.files}
    if "index.json" not in manifest_paths:
        raise WikipediaMembershipTransformError("snapshot manifest must include index.json")

    index_path = base_dir / "index.json"
    try:
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WikipediaMembershipTransformError(f"invalid index.json: {exc}") from exc
    if not isinstance(index_payload, dict):
        raise WikipediaMembershipTransformError("index.json root must be a JSON object")
    index = cast(dict[str, Any], index_payload)
    _validate_index_header(index=index, expected_snapshot_id=manifest.snapshot_id)

    requests_raw = index.get("requests")
    if not isinstance(requests_raw, list) or not requests_raw:
        raise WikipediaMembershipTransformError("index.json requests must be a non-empty array")

    diagnostics: list[WikipediaMembershipRequestDiagnostic] = []
    memberships: list[WikipediaMembershipObservation] = []
    seen_request_ids: set[str] = set()

    for request_index, raw_request in enumerate(requests_raw):
        if not isinstance(raw_request, dict):
            raise WikipediaMembershipTransformError(
                f"index.json requests[{request_index}] must be a JSON object"
            )
        request = cast(dict[str, Any], raw_request)
        diagnostic, rows, request_id = _transform_request(
            snapshot_id=manifest.snapshot_id,
            request_index=request_index,
            request=request,
            manifest_paths=manifest_paths,
            base_dir=base_dir,
        )
        if request_id in seen_request_ids:
            raise WikipediaMembershipTransformError(
                f"duplicate request_id in index.json: {request_id}"
            )
        seen_request_ids.add(request_id)
        diagnostics.append(diagnostic)
        memberships.extend(rows)

    ordered_diagnostics = tuple(
        sorted(
            diagnostics,
            key=lambda item: (
                item.requested_article_title.casefold(),
                item.requested_article_title,
                item.snapshot_target,
            ),
        )
    )
    ordered_memberships = tuple(
        sorted(
            memberships,
            key=lambda item: (
                item.requested_article_title.casefold(),
                item.requested_article_title,
                item.snapshot_target,
                item.provider_player_key,
                item.display_name.casefold(),
            ),
        )
    )
    lags = [item.revision_lag_seconds for item in ordered_diagnostics]

    return WikipediaMembershipTransformReport(
        snapshot_id=manifest.snapshot_id,
        source_code=SOURCE_CODE,
        requests_total=len(ordered_diagnostics),
        requests_with_evidence=sum(item.active_squad_evidence for item in ordered_diagnostics),
        requests_without_evidence=sum(
            not item.active_squad_evidence for item in ordered_diagnostics
        ),
        rows_emitted=len(ordered_memberships),
        rows_with_player_article=sum(
            item.player_article_title is not None for item in ordered_memberships
        ),
        max_revision_lag_seconds=max(lags, default=0),
        requests=ordered_diagnostics,
        memberships=ordered_memberships,
    )


def _transform_request(
    *,
    snapshot_id: str,
    request_index: int,
    request: dict[str, Any],
    manifest_paths: set[str],
    base_dir: Path,
) -> tuple[
    WikipediaMembershipRequestDiagnostic,
    tuple[WikipediaMembershipObservation, ...],
    str,
]:
    expected_keys = {
        "request_id",
        "requested_title",
        "resolved_title",
        "snapshot_target",
        "page_id",
        "revision_id",
        "revision_timestamp",
        "raw_file",
        "active_squad_evidence",
        "active_squad_heading",
        "active_squad_observations",
    }
    unknown = set(request) - expected_keys
    if unknown:
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}] contains unknown fields: {sorted(unknown)!r}"
        )

    request_id = _required_string(request, "request_id", request_index=request_index)
    requested_title = _required_string(
        request, "requested_title", request_index=request_index
    )
    resolved_title = _required_string(request, "resolved_title", request_index=request_index)
    snapshot_target = _required_string(
        request, "snapshot_target", request_index=request_index
    )
    revision_timestamp = _required_string(
        request, "revision_timestamp", request_index=request_index
    )
    raw_file = _required_string(request, "raw_file", request_index=request_index)
    revision_id = _required_positive_int(request, "revision_id", request_index=request_index)
    page_id = _optional_positive_int(request, "page_id", request_index=request_index)
    active_squad_evidence = _required_bool(
        request, "active_squad_evidence", request_index=request_index
    )
    active_squad_heading = _optional_string(
        request, "active_squad_heading", request_index=request_index
    )
    active_squad_observations = _required_non_negative_int(
        request, "active_squad_observations", request_index=request_index
    )

    if raw_file not in manifest_paths:
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}].raw_file is not listed in manifest: {raw_file}"
        )
    if raw_file == "index.json":
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}].raw_file cannot point to index.json"
        )

    target_dt = _parse_datetime(
        snapshot_target,
        field_name=f"index.json requests[{request_index}].snapshot_target",
    )
    historical_request = HistoricalRevisionRequest(
        article_title=requested_title,
        snapshot_target=target_dt,
    )
    if historical_request.stable_request_id != request_id:
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}] request_id does not match title/target"
        )

    raw_path = base_dir / raw_file
    try:
        raw = raw_path.read_bytes()
        parsed = _parse_revision_response(raw, historical_request)
    except (OSError, WikipediaHistoricalCollectionError) as exc:
        raise WikipediaMembershipTransformError(f"{raw_file}: {exc}") from exc

    if parsed.resolved_title != resolved_title:
        raise WikipediaMembershipTransformError(
            f"{raw_file}: resolved title mismatch index={resolved_title!r} "
            f"raw={parsed.resolved_title!r}"
        )
    if parsed.page_id != page_id:
        raise WikipediaMembershipTransformError(
            f"{raw_file}: page id mismatch index={page_id!r} raw={parsed.page_id!r}"
        )
    if parsed.revision_id != revision_id:
        raise WikipediaMembershipTransformError(
            f"{raw_file}: revision id mismatch index={revision_id} raw={parsed.revision_id}"
        )
    if parsed.revision_timestamp != revision_timestamp:
        raise WikipediaMembershipTransformError(
            f"{raw_file}: revision timestamp mismatch index={revision_timestamp!r} "
            f"raw={parsed.revision_timestamp!r}"
        )
    if (parsed.active_squad_heading is not None) != active_squad_evidence:
        raise WikipediaMembershipTransformError(
            f"{raw_file}: active-squad evidence flag does not match raw revision"
        )
    if parsed.active_squad_heading != active_squad_heading:
        raise WikipediaMembershipTransformError(
            f"{raw_file}: active-squad heading does not match raw revision"
        )
    if parsed.active_squad_observations != active_squad_observations:
        raise WikipediaMembershipTransformError(
            f"{raw_file}: active-squad observation count does not match raw revision"
        )

    try:
        snapshot = parse_historical_active_squad_revision(
            parsed.wikitext,
            article_title=parsed.resolved_title,
            revision_id=parsed.revision_id,
            revision_timestamp=parsed.revision_timestamp,
            snapshot_target=historical_request.api_snapshot_target,
        )
    except WikipediaHistoricalSquadError as exc:
        raise WikipediaMembershipTransformError(f"{raw_file}: {exc}") from exc

    revision_dt = _parse_datetime(
        parsed.revision_timestamp,
        field_name=f"{raw_file} revision_timestamp",
    )
    lag_seconds = int((historical_request.canonical_snapshot_target - revision_dt).total_seconds())
    if lag_seconds < 0:
        raise WikipediaMembershipTransformError(
            f"{raw_file}: revision timestamp is newer than snapshot target"
        )

    if snapshot is None:
        if active_squad_evidence or active_squad_observations != 0:
            raise WikipediaMembershipTransformError(
                f"{raw_file}: missing squad evidence conflicts with index metadata"
            )
        diagnostic = WikipediaMembershipRequestDiagnostic(
            requested_article_title=requested_title,
            source_article_title=parsed.resolved_title,
            revision_id=parsed.revision_id,
            revision_timestamp=parsed.revision_timestamp,
            snapshot_target=historical_request.api_snapshot_target,
            revision_lag_seconds=lag_seconds,
            raw_file=raw_file,
            active_squad_evidence=False,
            active_squad_heading=None,
            active_squad_observations=0,
        )
        return diagnostic, (), request_id

    rows = tuple(
        _membership_observation(
            snapshot_id=snapshot_id,
            requested_article_title=requested_title,
            raw_file=raw_file,
            observation=observation,
        )
        for observation in snapshot.observations
    )
    diagnostic = WikipediaMembershipRequestDiagnostic(
        requested_article_title=requested_title,
        source_article_title=snapshot.source_article_title,
        revision_id=snapshot.revision_id,
        revision_timestamp=snapshot.revision_timestamp,
        snapshot_target=snapshot.snapshot_target,
        revision_lag_seconds=lag_seconds,
        raw_file=raw_file,
        active_squad_evidence=True,
        active_squad_heading=snapshot.heading,
        active_squad_observations=len(rows),
    )
    return diagnostic, rows, request_id


def _membership_observation(
    *,
    snapshot_id: str,
    requested_article_title: str,
    raw_file: str,
    observation: Any,
) -> WikipediaMembershipObservation:
    article_title = cast(str | None, observation.player_article_title)
    display_name = cast(str, observation.display_name)
    provider_player_key = _provider_player_key(
        player_article_title=article_title,
        display_name=display_name,
    )
    membership_raw = (
        f"{SOURCE_CODE}\n{observation.source_article_title}\n{observation.revision_id}\n"
        f"{provider_player_key}"
    ).encode("utf-8")
    membership_observation_key = hashlib.sha256(membership_raw).hexdigest()[:24]
    return WikipediaMembershipObservation(
        source_code=SOURCE_CODE,
        snapshot_id=snapshot_id,
        requested_article_title=requested_article_title,
        source_article_title=cast(str, observation.source_article_title),
        revision_id=cast(int, observation.revision_id),
        revision_timestamp=cast(str, observation.revision_timestamp),
        snapshot_target=cast(str, observation.snapshot_target),
        heading=cast(str, observation.heading),
        raw_name=cast(str, observation.raw_name),
        display_name=display_name,
        player_article_title=article_title,
        provider_player_key=provider_player_key,
        membership_observation_key=membership_observation_key,
        raw_file=raw_file,
    )


def _provider_player_key(*, player_article_title: str | None, display_name: str) -> str:
    if player_article_title is not None:
        return f"article:{_normalize_key(player_article_title)}"
    return f"name:{_normalize_key(display_name)}"


def _normalize_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def _validate_index_header(*, index: dict[str, Any], expected_snapshot_id: str) -> None:
    expected_keys = {
        "snapshot_id",
        "source_code",
        "source_reference",
        "acquired_at",
        "licence",
        "attribution_required",
        "requests",
    }
    unknown = set(index) - expected_keys
    if unknown:
        raise WikipediaMembershipTransformError(
            f"index.json contains unknown fields: {sorted(unknown)!r}"
        )
    snapshot_id = index.get("snapshot_id")
    if snapshot_id != expected_snapshot_id:
        raise WikipediaMembershipTransformError(
            f"index snapshot_id mismatch manifest={expected_snapshot_id!r} index={snapshot_id!r}"
        )
    if index.get("source_code") != SOURCE_CODE:
        raise WikipediaMembershipTransformError(
            f"index source_code must be {SOURCE_CODE!r}"
        )
    acquired_at = index.get("acquired_at")
    if not isinstance(acquired_at, str):
        raise WikipediaMembershipTransformError("index acquired_at must be an ISO-8601 string")
    _parse_datetime(acquired_at, field_name="index acquired_at")
    if index.get("attribution_required") is not True:
        raise WikipediaMembershipTransformError(
            "index attribution_required must remain true for Wikipedia text evidence"
        )


def _required_string(payload: dict[str, Any], key: str, *, request_index: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}].{key} must be a non-blank string"
        )
    return value.strip()


def _optional_string(payload: dict[str, Any], key: str, *, request_index: int) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}].{key} must be a non-blank string or null"
        )
    return value.strip()


def _required_bool(payload: dict[str, Any], key: str, *, request_index: int) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}].{key} must be a boolean"
        )
    return value


def _required_positive_int(payload: dict[str, Any], key: str, *, request_index: int) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}].{key} must be a positive integer"
        )
    return value


def _optional_positive_int(
    payload: dict[str, Any], key: str, *, request_index: int
) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}].{key} must be a positive integer or null"
        )
    return value


def _required_non_negative_int(
    payload: dict[str, Any], key: str, *, request_index: int
) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise WikipediaMembershipTransformError(
            f"index.json requests[{request_index}].{key} must be a non-negative integer"
        )
    return value


def _parse_datetime(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise WikipediaMembershipTransformError(
            f"{field_name} must be ISO-8601, got {value!r}"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WikipediaMembershipTransformError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC).replace(microsecond=0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Transform a verified historical Wikipedia snapshot into membership evidence."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--base-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        report = transform_snapshot(manifest_path=args.manifest, base_dir=args.base_dir)
    except WikipediaMembershipTransformError as exc:
        raise SystemExit(f"WIKIPEDIA MEMBERSHIP TRANSFORM: FAIL - {exc}") from exc

    payload = {"status": "PASS" if report.passed else "FAIL", **asdict(report)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    state = "PASS" if report.passed else "FAIL"
    print(
        f"WIKIPEDIA MEMBERSHIP TRANSFORM: {state} snapshot={report.snapshot_id} "
        f"requests={report.requests_total} rows={report.rows_emitted} "
        f"linked={report.rows_with_player_article}"
    )
    print(f"OUTPUT: {args.output}")
    if not report.passed:
        raise SystemExit("WIKIPEDIA MEMBERSHIP TRANSFORM: FAIL")


if __name__ == "__main__":
    main()
