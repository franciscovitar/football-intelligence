"""V1 Closure Pass A/B preparation: read-only production-state preflight.

Reports safe, credential-free metadata about a given PostgreSQL target's
current canonical/V2 product/Data Mesh state, so a human can decide what --
if anything -- the production bootstrap sequence documented in
`docs/PRODUCTION_BOOTSTRAP.md` still needs to do, before any write is ever
authorized.

This command NEVER writes: PostgreSQL itself is told `SET TRANSACTION READ
ONLY` as the very first statement of the transaction, before any inspection
query -- so an accidental INSERT/UPDATE/DELETE/DDL introduced into this
module later would be refused by the database engine, not merely omitted by
convention. The transaction is always rolled back, never committed, even on
success.

Requires an explicit `--database-url`; `DATABASE_URL` is never read from the
environment. Unlike the write-capable jobs, no local-only restriction is
enforced here -- inspecting the real production database read-only is
exactly the point -- but the target is only ever reported as a safe
`postgresql://<host>[:<port>]/<dbname>` string
(`db.production_write_guard.safe_target_description`, resolved through the
same libpq-aware, environment-fallback-aware `db.target_parsing.parse_database_target`
the write-capable jobs use), never the full DSN, user, password, or query
string. Because this command never writes, it does not require (and does
not accept) the production-write confirmation flags the write-capable jobs
use -- but its reported `target` is exactly the value a human should later
copy into one of those jobs' `--confirm-database-target`, and the printed
target is guaranteed to equal the actually-connected target (see
"Post-connection verification" below), never merely a pre-connect guess.

## Post-connection verification (defense in depth)

After actually connecting, this command asks libpq itself -- via psycopg's
`Connection.info` (`PQhost`/`PQhostaddr`/`PQdb`) -- what target it really
used, and compares that against what `parse_database_target` validated
before connecting. A disagreement raises immediately rather than silently
printing a target that may not be the one actually reached.

The comparison follows real `PQhost`/`PQhostaddr` semantics, not a single
collapsed "connected host" value: `PQhost()` returns the host name/
parameter that was SUPPLIED (identity/SNI), while `PQhostaddr()` returns
the real resolved server IP -- and libpq populates `PQhostaddr()` with a
real DNS-resolved IP even for an ordinary hostname-only connection where
`hostaddr` was never supplied at all. Comparing that resolved IP against
the hostname string would therefore fail every normal DNS-based
connection; the check instead verifies `host` against `host` when no
explicit `hostaddr` was ever part of the target, and verifies `hostaddr`
against `hostaddr` (plus `host` as a separate identity check) only when
`hostaddr` genuinely was part of the resolved target. Port and dbname are
compared directly.

This is defense in depth only, for the read-only preflight specifically
(where a mismatch is merely reported and this command was never going to
write anyway) -- it is deliberately NOT relied on as a substitute for the
write-capable jobs' pre-connect fail-closed validation, since by the time a
post-connect check could run there, a connection to an unintended database
would already have happened.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from football_intelligence.db.production_write_guard import (
    safe_target_description,
    validate_database_url_scheme,
)
from football_intelligence.db.provider_repository import connect
from football_intelligence.db.target_parsing import ParsedDatabaseTarget, parse_database_target

COMPETITION_CODE = "ENG_PL"
SEASON_LABEL = "2025/26"

_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_REPORT_PATH = _REPO_ROOT / "data" / "manifests" / "production" / "preflight.json"

_V2_PRODUCT_VIEWS = (
    "product_team_detail_v2",
    "product_team_ranking_candidates_v2",
    "product_team_diagnostic_findings_v2",
    "product_player_detail_v2",
    "product_player_ranking_candidates_v2",
    "product_player_diagnostic_findings_v2",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only preflight: report safe metadata about a PostgreSQL target's "
            "current canonical/V2 product/Data Mesh state. Never writes; always "
            "rolls back, even on success."
        )
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help=(
            "Explicit PostgreSQL URL to inspect (local or remote). Never read from the "
            "DATABASE_URL environment variable. This command is read-only regardless of "
            "target, so no production-write confirmation flags are required or accepted."
        ),
    )
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser


def _scalar(connection: Any, sql: str, params: tuple[Any, ...] = ()) -> Any:
    row = connection.execute(sql, params).fetchone()
    return row[0] if row is not None else None


def _inspect_canonical(connection: Any) -> dict[str, Any]:
    competition_id = _scalar(
        connection, "select id from football.competitions where code = %s", (COMPETITION_CODE,)
    )
    teams_count = int(_scalar(connection, "select count(*) from football.teams") or 0)
    if competition_id is None:
        return {
            "eng_pl_competition_exists": False,
            "eng_pl_2025_26_season_exists": False,
            "teams_count": teams_count,
            "matches_count_scope": 0,
            "team_match_stats_count_scope": 0,
            "latest_match_updated_at": None,
        }

    season_id = _scalar(
        connection,
        "select id from football.seasons where competition_id = %s and label = %s",
        (competition_id, SEASON_LABEL),
    )
    if season_id is None:
        return {
            "eng_pl_competition_exists": True,
            "eng_pl_2025_26_season_exists": False,
            "teams_count": teams_count,
            "matches_count_scope": 0,
            "team_match_stats_count_scope": 0,
            "latest_match_updated_at": None,
        }

    matches_count = int(
        _scalar(
            connection, "select count(*) from football.matches where season_id = %s", (season_id,)
        )
        or 0
    )
    team_match_stats_count = int(
        _scalar(
            connection,
            """
            select count(*) from football.team_match_stats tms
            join football.matches m on m.id = tms.match_id
            where m.season_id = %s
            """,
            (season_id,),
        )
        or 0
    )
    latest_match_updated_at = _scalar(
        connection,
        "select max(updated_at) from football.matches where season_id = %s",
        (season_id,),
    )

    return {
        "eng_pl_competition_exists": True,
        "eng_pl_2025_26_season_exists": True,
        "teams_count": teams_count,
        "matches_count_scope": matches_count,
        "team_match_stats_count_scope": team_match_stats_count,
        "latest_match_updated_at": (
            latest_match_updated_at.isoformat() if latest_match_updated_at is not None else None
        ),
    }


def _inspect_v2_product(connection: Any) -> dict[str, Any]:
    view_row_counts: dict[str, int] = {}
    for view in _V2_PRODUCT_VIEWS:
        count = _scalar(connection, f"select count(*) from analytics.{view}")
        view_row_counts[view] = int(count or 0)

    def _active_scope(view: str) -> dict[str, Any] | None:
        row = connection.execute(
            f"select scope_key, model_version from analytics.{view}"
        ).fetchone()
        if row is None:
            return None
        return {"scope_key": row[0], "model_version": row[1]}

    return {
        "view_row_counts": view_row_counts,
        "active_team_scope": _active_scope("product_active_team_scope_v2"),
        "active_player_scope": _active_scope("product_active_player_scope_v2"),
    }


def _inspect_data_mesh(connection: Any) -> dict[str, Any]:
    observations_count = int(
        _scalar(connection, "select count(*) from ingestion.source_observations") or 0
    )
    decisions_count = int(
        _scalar(connection, "select count(*) from ingestion.reconciliation_decisions") or 0
    )
    latest_observed_at = _scalar(
        connection, "select max(observed_at) from ingestion.source_observations"
    )
    # A test/smoke fixture writing to production would leave its marker in
    # source_reference (the same field committed test fixtures use, e.g.
    # "test_smoke") -- a defensive sanity check, not a claim any product view
    # itself is contaminated (Product V2's own real/test_smoke discipline is
    # enforced at read time; see docs/PRODUCT_EXPERIENCE_V2.md).
    possible_test_smoke_leakage = int(
        _scalar(
            connection,
            "select count(*) from ingestion.source_observations where source_reference ilike %s",
            ("%test_smoke%",),
        )
        or 0
    )

    return {
        "source_observations_count": observations_count,
        "reconciliation_decisions_count": decisions_count,
        "latest_observed_at": (
            latest_observed_at.isoformat() if latest_observed_at is not None else None
        ),
        "possible_test_smoke_leakage_count": possible_test_smoke_leakage,
    }


def _verify_connected_target_matches(connection: Any, expected: ParsedDatabaseTarget) -> None:
    """Defense in depth: compare what libpq actually connected to
    (`Connection.info`, backed by `PQhost`/`PQhostaddr`/`PQdb`) against what
    `parse_database_target` validated pre-connect. Only meaningful for a
    remote target -- a local Unix-socket connection's `PQhost()` returns
    the socket directory path, not `"localhost"`, so comparing it here
    would be a false-positive trap, not a real check.

    The comparison must follow real libpq/PQ* semantics, not a naive single
    "connected host" value:

    - `PQhost()` returns the host name/parameter that was SUPPLIED (for
      identity/TLS verification/SNI), not the resolved network address.
    - `PQhostaddr()` returns the real server IP address libpq connects
      to. Critically, when only `host` was supplied (the ordinary
      DNS-hostname case -- no explicit `hostaddr`), libpq still resolves
      and reports a real IP via `PQhostaddr()` even though `hostaddr` was
      never part of the connection string. Comparing that DNS-resolved IP
      against the hostname string would fail EVERY ordinary DNS-based
      connection -- a false-positive trap, not a real check.

    So the check branches on which of `expected.host`/`expected.hostaddr`
    was actually part of the resolved target (DSN or environment):

    - `expected.hostaddr` was supplied: libpq was explicitly routed by
      `hostaddr` -- verify `info.hostaddr` matches it exactly, and (as a
      separate identity/SNI sanity check) `info.host` matches
      `expected.host` when that was also supplied.
    - Only `expected.host` was supplied (no `hostaddr`): verify `info.host`
      matches it. `info.hostaddr` is deliberately NOT compared here -- it
      is DNS's resolved IP doing its normal job, not a discrepancy.
    """

    if expected.is_local:
        return

    info = connection.info

    if expected.hostaddr is not None:
        if info.hostaddr != expected.hostaddr:
            raise RuntimeError(
                "Post-connection verification failed: pre-connect validation expected "
                f"hostaddr {expected.hostaddr!r} but libpq actually connected to "
                f"hostaddr {info.hostaddr!r}. Do not trust this preflight's printed target "
                "-- investigate before using it for --confirm-database-target."
            )
        if expected.host is not None and info.host != expected.host:
            raise RuntimeError(
                "Post-connection verification failed: pre-connect validation expected host "
                f"{expected.host!r} but libpq actually connected with host {info.host!r} "
                "(hostaddr matched, but the host/SNI identity did not). Do not trust this "
                "preflight's printed target."
            )
    elif expected.host is not None and info.host != expected.host:
        raise RuntimeError(
            "Post-connection verification failed: pre-connect validation expected host "
            f"{expected.host!r} but libpq actually connected to {info.host!r}. Do not "
            "trust this preflight's printed target -- investigate before using it for "
            "--confirm-database-target."
        )

    if expected.port is not None and str(info.port) != expected.port:
        raise RuntimeError(
            "Post-connection verification failed: pre-connect validation expected port "
            f"{expected.port!r} but libpq actually connected on port {info.port!r}. Do not "
            "trust this preflight's printed target."
        )
    if expected.dbname is not None and info.dbname != expected.dbname:
        raise RuntimeError(
            "Post-connection verification failed: pre-connect validation expected dbname "
            f"{expected.dbname!r} but libpq actually connected to {info.dbname!r}. Do not "
            "trust this preflight's printed target."
        )


def run_preflight(database_url: str) -> dict[str, Any]:
    expected_target = parse_database_target(database_url)
    report: dict[str, Any] = {
        "target": safe_target_description(database_url),
        "ambient_env_vars_used": list(expected_target.ambient_env_vars_used),
        "competition_code": COMPETITION_CODE,
        "season_label": SEASON_LABEL,
        "writes_performed": False,
    }
    with connect(database_url) as connection:
        try:
            # `connection.info` is pure libpq client-side metadata
            # (PQhost/PQhostaddr/PQdb) already known from the connection
            # handshake -- it sends no SQL statement to the server, so
            # `SET TRANSACTION READ ONLY` immediately below remains
            # genuinely the FIRST statement of the transaction.
            _verify_connected_target_matches(connection, expected_target)
            # PostgreSQL itself now refuses any INSERT/UPDATE/DELETE/DDL for
            # the remainder of this transaction, regardless of what a
            # future inspection query added here might accidentally
            # attempt -- a database-enforced guarantee, not merely an
            # application-level "we only SELECT" convention.
            connection.execute("SET TRANSACTION READ ONLY")
            report["canonical"] = _inspect_canonical(connection)
            report["v2_product"] = _inspect_v2_product(connection)
            report["data_mesh"] = _inspect_data_mesh(connection)
        finally:
            # Always rolled back, never committed -- this command performs
            # no writes on any path, success or failure.
            connection.rollback()
    return report


def main() -> None:
    args = build_parser().parse_args()
    database_url = validate_database_url_scheme(args.database_url)

    report = run_preflight(database_url)

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"PRODUCTION PREFLIGHT (read-only, no writes): target={report['target']}")
    if report["ambient_env_vars_used"]:
        print(
            "NOTE: this target was partly resolved from ambient environment variables "
            f"({', '.join(report['ambient_env_vars_used'])}), not entirely from "
            "--database-url itself. A write-capable job's remote path requires a fully "
            "explicit --database-url and will reject this target as-is."
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"REPORT: {args.report_path}")
    print(
        "\nIf a write-capable job's remote path is later authorized against this exact "
        f"target, copy this into --confirm-database-target:\n  {report['target']}"
    )


if __name__ == "__main__":
    main()
