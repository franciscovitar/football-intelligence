"""Ingest configured RSS/Atom evidence for Perception Intelligence V1."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, cast

from football_intelligence.db.perception_repository import PerceptionRepository
from football_intelligence.db.provider_repository import ProviderRepository, connect
from football_intelligence.perception.engine import (
    MODEL_VERSION,
    build_evidence,
    link_players,
)
from football_intelligence.perception.feed_client import fetch_feed, validate_feed_url
from football_intelligence.perception.feed_parser import parse_feed
from football_intelligence.perception.models import (
    EvidenceDraft,
    SourceDefinition,
    SourceKind,
    StoredSource,
)

_SOURCE_KINDS = {"expert", "media", "fan", "other"}
_SOURCE_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest Perception Intelligence evidence")
    parser.add_argument("--database-url")
    parser.add_argument("--sources-file", type=Path)
    parser.add_argument("--fixture-dir", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--trigger-kind",
        choices=("manual", "schedule", "retry", "test"),
        default="manual",
    )
    parser.add_argument("--max-items-per-source", type=int, default=40)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    if args.max_items_per_source < 1 or args.max_items_per_source > 100:
        raise SystemExit("--max-items-per-source must be between 1 and 100")

    sources_file = args.sources_file or _default_sources_file()
    definitions = load_source_definitions(sources_file)

    with connect(database_url) as connection:
        repository = PerceptionRepository(connection)
        repository.sync_sources(definitions)
        connection.commit()

        run_repository = ProviderRepository(connection, provider_code="perception-web")
        run_id = run_repository.start_run(
            job_name="perception-ingest",
            trigger_kind=args.trigger_kind,
            scope={"source_codes": [source.code for source in definitions]},
        )
        connection.commit()

        active_sources = repository.active_sources()
        players = repository.linkable_players()
        fetched: list[tuple[StoredSource, tuple[EvidenceDraft, ...], int, int]] = []
        failures: list[dict[str, str]] = []

        for source in active_sources:
            try:
                if args.fixture_dir:
                    fixture = args.fixture_dir / f"{source.code}.xml"
                    payload = fixture.read_bytes()
                    base_url = source.feed_url
                else:
                    response = fetch_feed(source.feed_url)
                    payload = response.payload
                    base_url = response.final_url
                items = parse_feed(payload, base_url=base_url)[: args.max_items_per_source]
                prepared: list[EvidenceDraft] = []
                invalid_items = 0
                for item in items:
                    try:
                        prepared.append(build_evidence(item))
                    except ValueError:
                        invalid_items += 1
                fetched.append((source, tuple(prepared), len(items), invalid_items))
            except Exception as exc:
                failures.append(
                    {
                        "source_code": source.code,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        rows_written = 0
        mentions_written = 0
        source_reports: list[dict[str, Any]] = []

        try:
            for source, evidence_items, items_seen, invalid_items in fetched:
                persisted = 0
                mention_count = 0
                for evidence in evidence_items:
                    duplicate_of_id = repository.find_duplicate_root(
                        content_sha256=evidence.content_sha256,
                        source_id=source.id,
                    )
                    evidence_id = repository.upsert_evidence(
                        source_id=source.id,
                        evidence=evidence,
                        duplicate_of_id=duplicate_of_id,
                        ingestion_version=MODEL_VERSION,
                    )
                    mentions = link_players(evidence, players)
                    repository.replace_mentions(evidence_id, mentions)
                    persisted += 1
                    mention_count += len(mentions)

                rows_written += persisted
                mentions_written += mention_count
                source_reports.append(
                    {
                        "source_code": source.code,
                        "items_seen": items_seen,
                        "invalid_items": invalid_items,
                        "evidence_persisted": persisted,
                        "mentions_persisted": mention_count,
                    }
                )

            if active_sources and not fetched:
                status = "failed"
            elif failures:
                status = "partial"
            else:
                status = "succeeded"

            run_repository.finish_run(
                run_id,
                status=status,
                request_count=len(active_sources),
                rows_written=rows_written,
                metadata={
                    "model_version": MODEL_VERSION,
                    "sources": source_reports,
                    "failures": failures,
                    "mentions_written": mentions_written,
                },
                error_code="all_sources_failed" if status == "failed" else None,
                error_message=(
                    "All active perception sources failed" if status == "failed" else None
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            run_repository.finish_run(
                run_id,
                status="failed",
                request_count=len(active_sources),
                rows_written=0,
                metadata={"model_version": MODEL_VERSION, "failures": failures},
                error_code="persistence_failed",
                error_message="Perception persistence failed",
            )
            connection.commit()
            raise

    report = {
        "model_version": MODEL_VERSION,
        "status": status,
        "active_sources": len(active_sources),
        "request_count": len(active_sources),
        "rows_written": rows_written,
        "mentions_written": mentions_written,
        "sources": source_reports,
        "failures": failures,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if status == "failed":
        print("PERCEPTION INGEST: FAIL (all active sources failed)")
        print(f"REPORT: {args.report}")
        raise SystemExit(1)

    label = "PARTIAL" if status == "partial" else "PASS"
    print(f"PERCEPTION INGEST: {label} ({rows_written} evidence items)")
    print(f"REPORT: {args.report}")


def load_source_definitions(path: Path) -> tuple[SourceDefinition, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("perception source config must be a JSON array")

    definitions: list[SourceDefinition] = []
    seen_codes: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each perception source must be an object")

        code = _required_text(item, "code")
        if not _SOURCE_CODE_RE.fullmatch(code):
            raise ValueError(f"invalid source code: {code}")
        if code in seen_codes:
            raise ValueError(f"duplicate source code: {code}")
        seen_codes.add(code)

        source_kind = _required_text(item, "source_kind")
        if source_kind not in _SOURCE_KINDS:
            raise ValueError(f"invalid source_kind for {code}: {source_kind}")

        feed_url = _required_text(item, "feed_url")
        validate_feed_url(feed_url, resolve_dns=False)

        homepage_value = item.get("homepage_url")
        homepage_url = str(homepage_value).strip() if homepage_value else None
        if homepage_url and not homepage_url.startswith(("https://", "http://")):
            raise ValueError(f"invalid homepage_url for {code}")

        definitions.append(
            SourceDefinition(
                code=code,
                display_name=_required_text(item, "display_name"),
                source_kind=cast(SourceKind, source_kind),
                homepage_url=homepage_url,
                feed_url=feed_url,
                is_active=bool(item.get("is_active", True)),
            )
        )

    return tuple(definitions)


def _required_text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-blank string")
    return value.strip()


def _default_sources_file() -> Path:
    return Path(__file__).resolve().parents[4] / "config" / "perception_sources.json"


if __name__ == "__main__":
    main()
