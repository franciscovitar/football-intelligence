from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection

from football_intelligence.db.provider_repository import connect
from football_intelligence.jobs import execute_real_intelligence_v2 as job

_TEAM_NAMES = (
    "Block19 Test City",
    "Block19 Test United",
    "Block19 Test Rovers",
    "Block19 Test Town",
)


def _seed_minimal_real_shaped_snapshot(connection: Connection[Any]) -> tuple[int, ...]:
    """Seeds a small ENG_PL 2025/26 match/team-stat set shaped exactly like
    the real Football-Data.co.uk snapshot this job is built for: goals,
    shots, shots-on-target only -- no xG, no possession, no player rows.
    Reuses the exact `(competition_code, season_label)` this job hardcodes
    (`ENG_PL` / `2025/26`) since the job is a single, scope-fixed entry
    point, not a general-purpose one. Returns the created team ids so the
    caller can clean them up -- unlike the read-only integration tests
    elsewhere, this fixture's own job under test (`main()`) commits for
    real, so the test must tear its own rows back out explicitly.
    """

    competition_row = connection.execute(
        "select id from football.competitions where code = 'ENG_PL'"
    ).fetchone()
    assert competition_row is not None
    competition_id = int(competition_row[0])
    season_row = connection.execute(
        """
        insert into football.seasons (competition_id, label)
        values (%s, '2025/26')
        on conflict (competition_id, label) do update set updated_at = now()
        returning id
        """,
        (competition_id,),
    ).fetchone()
    assert season_row is not None
    season_id = int(season_row[0])

    team_ids: list[int] = []
    for name in _TEAM_NAMES:
        row = connection.execute(
            "insert into football.teams (name) values (%s) returning id",
            (name,),
        ).fetchone()
        assert row is not None
        team_ids.append(int(row[0]))

    kickoff = datetime(2025, 9, 1, tzinfo=UTC)
    pairs = [(0, 1), (2, 3), (1, 2), (3, 0)]
    for index, (home_idx, away_idx) in enumerate(pairs):
        match_row = connection.execute(
            """
            insert into football.matches (
                season_id, home_team_id, away_team_id, kickoff_at,
                status, home_score, away_score
            )
            values (%s, %s, %s, %s, 'finished', 2, 1)
            returning id
            """,
            (
                season_id,
                team_ids[home_idx],
                team_ids[away_idx],
                kickoff + timedelta(days=index * 7),
            ),
        ).fetchone()
        assert match_row is not None
        match_id = int(match_row[0])
        connection.execute(
            """
            insert into football.team_match_stats (
                match_id, team_id, shots_total, shots_on_target, corners
            )
            values
                (%s, %s, 14, 6, 7),
                (%s, %s, 8, 2, 3)
            """,
            (match_id, team_ids[home_idx], match_id, team_ids[away_idx]),
        )

    return tuple(team_ids)


def _delete_seeded_teams(database_url: str, team_ids: tuple[int, ...]) -> None:
    """Removes everything created by `_seed_minimal_real_shaped_snapshot`
    (and anything `job.main()` persisted from it) so this test's real
    commits don't leak into other integration tests sharing the same
    database, e.g. absolute `football.teams` row-count assertions.
    `football.matches` FKs are `on delete restrict`, so matches must go
    before teams; `team_match_stats`/analytics snapshot rows cascade from
    their own `on delete cascade` FKs.
    """

    if not team_ids:
        return
    with connect(database_url) as connection:
        connection.execute(
            """
            delete from analytics.diagnostic_findings
            where entity_id = any(%s) and entity_type = 'team'
            """,
            (list(team_ids),),
        )
        connection.execute(
            """
            delete from football.matches
            where home_team_id = any(%s) or away_team_id = any(%s)
            """,
            (list(team_ids), list(team_ids)),
        )
        connection.execute("delete from football.teams where id = any(%s)", (list(team_ids),))
        connection.commit()


@pytest.fixture
def seeded_real_shaped_snapshot(request: pytest.FixtureRequest) -> Iterator[str]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        team_ids = _seed_minimal_real_shaped_snapshot(connection)
        connection.commit()
    try:
        yield database_url
    finally:
        _delete_seeded_teams(database_url, team_ids)


@pytest.mark.integration
def test_execute_real_intelligence_v2_runs_idempotently_end_to_end(
    seeded_real_shaped_snapshot: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invokes the actual CLI entry point (`job.main()`) twice against the
    same real-shaped data and compares the written reports -- proves the
    full flow (DB safety validation, Team V2 execution, diagnostics,
    product-view verification, report writing) is idempotent, not just the
    inner persistence calls.
    """

    database_url = seeded_real_shaped_snapshot
    report_path = tmp_path / "report.json"
    argv = ["prog", "--database-url", database_url, "--report-path", str(report_path)]

    monkeypatch.setattr("sys.argv", argv)
    job.main()
    report_1 = json.loads(report_path.read_text())

    monkeypatch.setattr("sys.argv", argv)
    job.main()
    report_2 = json.loads(report_path.read_text())

    for report in (report_1, report_2):
        assert report["team_v2_execution"]["score_rows"] > 0
        # Real-shaped evidence (shots_total/shots_on_target only, no xG)
        # never produces a ready overall score -- correctness gate from the
        # engine_v2.py fix, re-verified end-to-end through the report.
        assert report["team_v2_execution"]["overall_score_available"] is False
        assert report["player_v2_execution"]["score_rows"] == 0
        assert report["scoring_correctness"] == {
            "incomplete_evidence_renormalized_into_full_score": False,
            "missing_values_converted_to_zero": False,
            "v1_fallback_used": False,
        }

    assert report_1["team_v2_execution"] == report_2["team_v2_execution"]
    assert report_1["real_diagnostics"] == report_2["real_diagnostics"]
    assert report_1["product_view_counts"] == report_2["product_view_counts"]

    with connect(database_url) as connection:
        overall_scores = connection.execute(
            """
            select overall_score from analytics.team_score_snapshots
            where scope_key = %s and model_version = 'team-v2.0' and data_context = 'real'
            """,
            (job.SCOPE_KEY,),
        ).fetchall()
        connection.rollback()
    assert overall_scores
    assert all(row[0] is None for row in overall_scores)


@pytest.mark.integration
def test_real_diagnostic_findings_carry_correct_product_safety_context(
    seeded_real_shaped_snapshot: str,
) -> None:
    database_url = seeded_real_shaped_snapshot

    with connect(database_url) as connection:
        job._execute_team_v2(connection, calculated_at=datetime(2026, 8, 15, tzinfo=UTC))
        connection.commit()

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            select data_context, source_model_version, scope_key, entity_type
            from analytics.diagnostic_findings
            where scope_key = %s
            """,
            (job.SCOPE_KEY,),
        ).fetchall()
        connection.rollback()

    for data_context, source_model_version, scope_key, entity_type in rows:
        assert data_context == "real"
        assert source_model_version == "team-v2.0"
        assert scope_key == job.SCOPE_KEY
        assert entity_type == "team"
