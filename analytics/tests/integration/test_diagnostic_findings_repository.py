from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from football_intelligence.db.diagnostic_findings_repository import (
    DiagnosticFindingsRepository,
)
from football_intelligence.db.provider_repository import connect
from football_intelligence.diagnostics.models import DiagnosticFinding

_NOW = datetime(2026, 8, 15, tzinfo=UTC)


def _finding(*, entity_id: int, diagnostic_code: str, comparison_group: str) -> DiagnosticFinding:
    return DiagnosticFinding(
        diagnostic_code=diagnostic_code,
        entity_type="team",
        entity_id=entity_id,
        severity="notable",
        confidence=0.5,
        supporting_metrics={"team_name": f"Team {entity_id}"},
        comparison_group=comparison_group,
        window="season",
        model_version="diagnostic-v1.0",
        computed_at=_NOW,
    )


@pytest.mark.integration
def test_replace_scope_is_idempotent_and_isolated_from_other_scopes_and_contexts() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        team_row = connection.execute(
            "insert into football.teams (name) values (%s) returning id",
            ("Diagnostic Findings Repo Team",),
        ).fetchone()
        assert team_row is not None
        team_id = int(team_row[0])

        repository = DiagnosticFindingsRepository(connection)
        scope_key = "competition:ENG_PL:diagnostic-findings-repo-integration"
        other_scope_key = "competition:ENG_PL:diagnostic-findings-repo-other"

        # A row in a different scope must survive untouched.
        repository.replace_scope(
            [
                _finding(
                    entity_id=team_id,
                    diagnostic_code="results_above_process",
                    comparison_group=other_scope_key,
                )
            ],
            entity_type="team",
            data_context="real",
            source_model_version="team-v2.0",
            scope_key=other_scope_key,
        )
        # A `test_smoke` row for the SAME scope_key string must also survive
        # untouched -- isolation is on the full (entity_type, data_context,
        # source_model_version, scope_key) tuple, not scope_key alone.
        repository.replace_scope(
            [
                _finding(
                    entity_id=team_id,
                    diagnostic_code="results_above_process",
                    comparison_group=scope_key,
                )
            ],
            entity_type="team",
            data_context="test_smoke",
            source_model_version="team-v2.0",
            scope_key=scope_key,
        )

        findings = [
            _finding(
                entity_id=team_id,
                diagnostic_code="few_but_high_quality_chances_allowed",
                comparison_group=scope_key,
            )
        ]
        written = repository.replace_scope(
            findings,
            entity_type="team",
            data_context="real",
            source_model_version="team-v2.0",
            scope_key=scope_key,
        )
        assert written == 1
        first_count = repository.count_scope(
            entity_type="team",
            data_context="real",
            source_model_version="team-v2.0",
            scope_key=scope_key,
        )
        assert first_count == 1

        # Rerun with the exact same findings: idempotent, no duplicates.
        repository.replace_scope(
            findings,
            entity_type="team",
            data_context="real",
            source_model_version="team-v2.0",
            scope_key=scope_key,
        )
        second_count = repository.count_scope(
            entity_type="team",
            data_context="real",
            source_model_version="team-v2.0",
            scope_key=scope_key,
        )
        assert second_count == 1

        # Rerun with a DIFFERENT finding set for the same scope: the old
        # finding that no longer fires must be gone, not linger.
        replacement = [
            _finding(
                entity_id=team_id,
                diagnostic_code="high_volume_low_quality_allowed",
                comparison_group=scope_key,
            )
        ]
        repository.replace_scope(
            replacement,
            entity_type="team",
            data_context="real",
            source_model_version="team-v2.0",
            scope_key=scope_key,
        )
        codes = connection.execute(
            """
            select diagnostic_code from analytics.diagnostic_findings
            where entity_type = 'team' and data_context = 'real'
              and source_model_version = 'team-v2.0' and scope_key = %s
            """,
            (scope_key,),
        ).fetchall()
        assert [row[0] for row in codes] == ["high_volume_low_quality_allowed"]

        # The other scope and the test_smoke row for the same scope string
        # were never touched by any of the above.
        other_scope_count = connection.execute(
            """
            select count(*) from analytics.diagnostic_findings
            where scope_key = %s and data_context = 'real'
            """,
            (other_scope_key,),
        ).fetchone()
        assert other_scope_count == (1,)
        smoke_count = connection.execute(
            """
            select count(*) from analytics.diagnostic_findings
            where scope_key = %s and data_context = 'test_smoke'
            """,
            (scope_key,),
        ).fetchone()
        assert smoke_count == (1,)

        connection.rollback()


@pytest.mark.integration
def test_real_and_smoke_findings_sharing_a_natural_key_and_scope_coexist() -> None:
    """Blocker 1 regression: before
    `20260815140000_widen_diagnostic_findings_identity.sql`, the table's
    primary key was only (entity_type, entity_id, diagnostic_code,
    comparison_group, window_key, model_version) -- a real and a
    `test_smoke` finding sharing that natural key, even with the identical
    `scope_key` string, could not coexist; inserting one would `ON
    CONFLICT` overwrite the other's context. This proves both now coexist
    as two distinct rows, that replacing the real scope never touches the
    smoke row, and that the product-safe view still exposes only the real
    one.
    """

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        team_row = connection.execute(
            "insert into football.teams (name) values (%s) returning id",
            ("Context Coexistence Team",),
        ).fetchone()
        assert team_row is not None
        team_id = int(team_row[0])

        # An active real Team V2 scope so `product_team_diagnostic_findings_v2`'s
        # inner join to `product_active_team_scope_v2` has something to match.
        competition_row = connection.execute(
            "select id from football.competitions where code = 'ENG_PL'"
        ).fetchone()
        assert competition_row is not None
        competition_id = int(competition_row[0])
        season_row = connection.execute(
            """
            insert into football.seasons (competition_id, label)
            values (%s, %s)
            on conflict (competition_id, label) do update set updated_at = now()
            returning id
            """,
            (competition_id, "diagnostic-findings-coexistence-integration"),
        ).fetchone()
        assert season_row is not None
        season_id = int(season_row[0])
        scope_key = "competition:ENG_PL:diagnostic-findings-coexistence-integration"
        other_scope_key = "competition:ENG_PL:diagnostic-findings-coexistence-other"
        connection.execute(
            """
            insert into analytics.team_score_snapshots (
                team_id, season_id, scope_key, window_key, matches,
                overall_score, confidence, dimension_scores,
                results_process_delta, results_process_signal, diagnostics,
                reference_sample_size, current_elo, elo_change_last_5,
                model_version, calculated_at, evidence_coverage_pct,
                evidence_state, dimension_evidence, profile_version, data_context
            ) values (
                %s, %s, %s, 'season', 1,
                null, 0.5, '{}'::jsonb,
                null, null, '{}'::jsonb, 1, null, null,
                'team-v2.0', now(), 10.0,
                'partial', '{}'::jsonb, 'team-dimensions-v2.0', 'real'
            )
            """,
            (team_id, season_id, scope_key),
        )

        repository = DiagnosticFindingsRepository(connection)
        diagnostic_code = "few_but_high_quality_chances_allowed"

        # A finding in a different scope/source_model_version, to prove it
        # stays untouched by everything below.
        repository.replace_scope(
            [
                _finding(
                    entity_id=team_id,
                    diagnostic_code=diagnostic_code,
                    comparison_group=other_scope_key,
                )
            ],
            entity_type="team",
            data_context="real",
            source_model_version="team-v2.0",
            scope_key=other_scope_key,
        )

        # The test_smoke finding: same natural key, same scope_key string.
        repository.replace_scope(
            [
                _finding(
                    entity_id=team_id, diagnostic_code=diagnostic_code, comparison_group=scope_key
                )
            ],
            entity_type="team",
            data_context="test_smoke",
            source_model_version="team-v2.0",
            scope_key=scope_key,
        )
        smoke_row_before = connection.execute(
            """
            select severity, confidence, supporting_metrics, computed_at
            from analytics.diagnostic_findings
            where entity_type = 'team' and entity_id = %s and diagnostic_code = %s
              and comparison_group = %s and window_key = 'season'
              and model_version = 'diagnostic-v1.0' and data_context = 'test_smoke'
            """,
            (team_id, diagnostic_code, scope_key),
        ).fetchone()
        assert smoke_row_before is not None

        # The real finding: identical natural key and scope_key, distinct context.
        repository.replace_scope(
            [
                _finding(
                    entity_id=team_id, diagnostic_code=diagnostic_code, comparison_group=scope_key
                )
            ],
            entity_type="team",
            data_context="real",
            source_model_version="team-v2.0",
            scope_key=scope_key,
        )

        base_count = connection.execute(
            """
            select count(*) from analytics.diagnostic_findings
            where entity_type = 'team' and entity_id = %s and diagnostic_code = %s
              and comparison_group = %s and window_key = 'season'
              and model_version = 'diagnostic-v1.0'
            """,
            (team_id, diagnostic_code, scope_key),
        ).fetchone()
        assert base_count == (2,)

        # Rerun replace_scope for the real tuple again: idempotent, the
        # smoke row must not move, and the base-table count stays 2.
        repository.replace_scope(
            [
                _finding(
                    entity_id=team_id, diagnostic_code=diagnostic_code, comparison_group=scope_key
                )
            ],
            entity_type="team",
            data_context="real",
            source_model_version="team-v2.0",
            scope_key=scope_key,
        )
        base_count_after_rerun = connection.execute(
            """
            select count(*) from analytics.diagnostic_findings
            where entity_type = 'team' and entity_id = %s and diagnostic_code = %s
              and comparison_group = %s and window_key = 'season'
              and model_version = 'diagnostic-v1.0'
            """,
            (team_id, diagnostic_code, scope_key),
        ).fetchone()
        assert base_count_after_rerun == (2,)

        smoke_row_after = connection.execute(
            """
            select severity, confidence, supporting_metrics, computed_at
            from analytics.diagnostic_findings
            where entity_type = 'team' and entity_id = %s and diagnostic_code = %s
              and comparison_group = %s and window_key = 'season'
              and model_version = 'diagnostic-v1.0' and data_context = 'test_smoke'
            """,
            (team_id, diagnostic_code, scope_key),
        ).fetchone()
        assert smoke_row_after == smoke_row_before

        # Product-safe view exposes only the real row.
        view_rows = connection.execute(
            """
            select data_context from analytics.product_team_diagnostic_findings_v2
            where entity_id = %s and diagnostic_code = %s
            """,
            (team_id, diagnostic_code),
        ).fetchall()
        assert [row[0] for row in view_rows] == ["real"]

        # The other scope/source_model_version pair is still untouched.
        other_count = connection.execute(
            """
            select count(*) from analytics.diagnostic_findings
            where scope_key = %s and data_context = 'real'
            """,
            (other_scope_key,),
        ).fetchone()
        assert other_count == (1,)

        connection.rollback()


@pytest.mark.integration
def test_wrong_source_model_version_is_invisible_to_the_product_view() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured")

    with connect(database_url) as connection:
        team_row = connection.execute(
            "insert into football.teams (name) values (%s) returning id",
            ("Wrong Source Version Team",),
        ).fetchone()
        assert team_row is not None
        team_id = int(team_row[0])

        # A real-looking Team V2 score row establishes the active scope so
        # the product view's inner join has something to match against.
        competition_row = connection.execute(
            "select id from football.competitions where code = 'ENG_PL'"
        ).fetchone()
        assert competition_row is not None
        competition_id = int(competition_row[0])
        season_row = connection.execute(
            """
            insert into football.seasons (competition_id, label)
            values (%s, %s)
            on conflict (competition_id, label) do update set updated_at = now()
            returning id
            """,
            (competition_id, "diagnostic-findings-view-integration"),
        ).fetchone()
        assert season_row is not None
        season_id = int(season_row[0])
        scope_key = "competition:ENG_PL:diagnostic-findings-view-integration"
        connection.execute(
            """
            insert into analytics.team_score_snapshots (
                team_id, season_id, scope_key, window_key, matches,
                overall_score, confidence, dimension_scores,
                results_process_delta, results_process_signal, diagnostics,
                reference_sample_size, current_elo, elo_change_last_5,
                model_version, calculated_at, evidence_coverage_pct,
                evidence_state, dimension_evidence, profile_version, data_context
            ) values (
                %s, %s, %s, 'season', 1,
                null, 0.5, '{}'::jsonb,
                null, null, '{}'::jsonb, 1, null, null,
                'team-v2.0', now(), 10.0,
                'partial', '{}'::jsonb, 'team-dimensions-v2.0', 'real'
            )
            """,
            (team_id, season_id, scope_key),
        )

        repository = DiagnosticFindingsRepository(connection)
        repository.replace_scope(
            [
                _finding(
                    entity_id=team_id,
                    diagnostic_code="high_volume_low_quality_allowed",
                    comparison_group=scope_key,
                )
            ],
            entity_type="team",
            data_context="real",
            source_model_version="team-v1.0",  # wrong: not "team-v2.0"
            scope_key=scope_key,
        )

        visible = connection.execute(
            """
            select count(*) from analytics.product_team_diagnostic_findings_v2
            where entity_id = %s
            """,
            (team_id,),
        ).fetchone()
        assert visible == (0,)

        connection.rollback()
