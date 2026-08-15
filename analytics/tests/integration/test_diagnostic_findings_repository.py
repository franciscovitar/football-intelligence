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
