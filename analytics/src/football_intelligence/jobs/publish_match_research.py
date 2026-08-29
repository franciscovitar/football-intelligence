"""CLI for safe publication of MATCH_RESEARCH_PUBLISH_V1 packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg

from football_intelligence.db.production_write_guard import resolve_database_target
from football_intelligence.publishing.package import (
    load_match_publish_package,
    match_publish_package_digest,
    require_publishable_package,
)
from football_intelligence.publishing.publisher import publish_match_research


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and atomically publish one Football Intelligence "
            "MATCH_RESEARCH_PUBLISH_V1 package."
        )
    )
    parser.add_argument("package", type=Path, help="Path to the researched match JSON package.")
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Explicit PostgreSQL URL. Required unless --validate-only is used. "
            "DATABASE_URL is never read implicitly. Remote writes require every "
            "production confirmation enforced by db.production_write_guard."
        ),
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate schema, cross references and QA status without opening a database connection.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exercise the complete database transaction and publication gates, then roll it back.",
    )
    parser.add_argument(
        "--revision-reason",
        default=None,
        help="Required when replacing already-published match intelligence with a higher review version.",
    )
    parser.add_argument("--allow-remote-write", action="store_true")
    parser.add_argument("--confirm-target", default=None)
    parser.add_argument("--production-write-confirmation", default=None)
    parser.add_argument("--confirm-database-target", default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    payload = load_match_publish_package(args.package)
    require_publishable_package(payload)
    digest = match_publish_package_digest(payload)

    if args.validate_only:
        print(
            json.dumps(
                {
                    "status": "VALID",
                    "contract_version": payload["contract_version"],
                    "run_key": payload["research"]["run_key"],
                    "package_sha256": digest,
                },
                sort_keys=True,
            )
        )
        return

    if args.database_url is None:
        raise SystemExit("--database-url is required unless --validate-only is used")

    target = resolve_database_target(
        args.database_url,
        allow_remote_write=args.allow_remote_write,
        confirm_target=args.confirm_target,
        production_write_confirmation=args.production_write_confirmation,
        confirm_database_target=args.confirm_database_target,
    )
    assert target is not None

    with psycopg.connect(target.database_url, autocommit=False) as connection:
        result = publish_match_research(
            connection,
            payload,
            dry_run=args.dry_run,
            revision_reason=args.revision_reason,
        )

    print(
        json.dumps(
            {
                "status": result.status,
                "match_id": result.match_id,
                "research_run_id": result.research_run_id,
                "review_version": result.review_version,
                "package_sha256": result.package_sha256,
                "database_target": target.safe_description,
                "database_is_local": target.is_local,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
