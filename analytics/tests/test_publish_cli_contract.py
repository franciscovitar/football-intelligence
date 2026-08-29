from __future__ import annotations

from football_intelligence.jobs.publish_match_research import build_parser


def test_validate_only_does_not_require_database_argument_at_parse_time() -> None:
    args = build_parser().parse_args(["package.json", "--validate-only"])
    assert args.validate_only is True
    assert args.database_url is None


def test_remote_write_flags_are_explicit_cli_arguments() -> None:
    args = build_parser().parse_args(
        [
            "package.json",
            "--database-url",
            "postgresql://localhost:5432/test",
            "--allow-remote-write",
            "--confirm-target",
            "production",
            "--production-write-confirmation",
            "confirmation",
            "--confirm-database-target",
            "postgresql://localhost:5432/test",
        ]
    )
    assert args.allow_remote_write is True
    assert args.confirm_target == "production"
    assert args.production_write_confirmation == "confirmation"
    assert args.confirm_database_target == "postgresql://localhost:5432/test"
