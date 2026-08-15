"""Persist Diagnostic Rule Engine findings with explicit product-safety context.

`analytics.diagnostic_findings` and its provenance columns
(`data_context`/`source_model_version`/`scope_key`) already exist (see
`database/migrations/20260814100000_create_diagnostic_findings.sql` and
`database/migrations/20260815130000_isolate_diagnostic_findings_v2_context.sql`),
but no Python writer persisted to it before Block 19. `replace_scope` follows
the same delete-then-insert-for-scope shape as
`TeamAnalyticsRepository.replace_v2_snapshots`: it only ever deletes rows
matching the exact `(entity_type, data_context, source_model_version,
scope_key)` tuple being replaced, so a rerun never touches another scope,
another data_context (e.g. the deterministic `test_smoke` fixture), or
another entity_type.

`database/migrations/20260815140000_widen_diagnostic_findings_identity.sql`
widened the table's primary key to include `data_context`,
`source_model_version` and `scope_key` alongside the original natural key
(`entity_type`, `entity_id`, `diagnostic_code`, `comparison_group`,
`window_key`, `model_version`). Before that migration, a real and a
`test_smoke` finding sharing the same natural key could not coexist -- the
narrower original primary key made the insert below silently `ON CONFLICT
... DO UPDATE` one context's row into the other's. The `ON CONFLICT` target
here matches the widened key.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from psycopg import Connection

from football_intelligence.diagnostics.models import DiagnosticFinding


class DiagnosticFindingsRepository:
    """Idempotently replace one entity/data_context/model/scope's findings."""

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def replace_scope(
        self,
        findings: Sequence[DiagnosticFinding],
        *,
        entity_type: str,
        data_context: str,
        source_model_version: str,
        scope_key: str,
    ) -> int:
        if entity_type not in {"player", "team"}:
            raise ValueError(f"unsupported entity_type {entity_type!r}")
        if not scope_key.strip():
            raise ValueError("scope_key must not be blank")
        if any(finding.entity_type != entity_type for finding in findings):
            raise ValueError("all findings must match the given entity_type")

        self._connection.execute(
            """
            delete from analytics.diagnostic_findings
            where entity_type = %s
              and data_context = %s
              and source_model_version = %s
              and scope_key = %s
            """,
            (entity_type, data_context, source_model_version, scope_key),
        )
        for finding in findings:
            self._connection.execute(
                """
                insert into analytics.diagnostic_findings (
                    diagnostic_code, entity_type, entity_id, severity, confidence,
                    supporting_metrics, comparison_group, window_key, model_version,
                    computed_at, data_context, source_model_version, scope_key
                ) values (
                    %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s
                )
                on conflict (
                    entity_type, entity_id, diagnostic_code, comparison_group,
                    window_key, model_version, data_context, source_model_version,
                    scope_key
                )
                do update set
                    severity = excluded.severity,
                    confidence = excluded.confidence,
                    supporting_metrics = excluded.supporting_metrics,
                    computed_at = excluded.computed_at
                """,
                (
                    finding.diagnostic_code,
                    finding.entity_type,
                    finding.entity_id,
                    finding.severity,
                    finding.confidence,
                    json.dumps(dict(finding.supporting_metrics), sort_keys=True),
                    finding.comparison_group,
                    finding.window,
                    finding.model_version,
                    finding.computed_at,
                    data_context,
                    source_model_version,
                    scope_key,
                ),
            )
        return len(findings)

    def count_scope(
        self,
        *,
        entity_type: str,
        data_context: str,
        source_model_version: str,
        scope_key: str,
    ) -> int:
        row = self._connection.execute(
            """
            select count(*) from analytics.diagnostic_findings
            where entity_type = %s
              and data_context = %s
              and source_model_version = %s
              and scope_key = %s
            """,
            (entity_type, data_context, source_model_version, scope_key),
        ).fetchone()
        if row is None:
            raise RuntimeError("failed to count diagnostic findings")
        return int(row[0])
