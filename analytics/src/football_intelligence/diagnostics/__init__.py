"""Deterministic Diagnostic Rule Engine (Block 16, model version `diagnostic-v1.0`).

Pure, no I/O: every rule consumes already-computed evidence from
`player_analytics`/`team_analytics`/`meta_analytics`/`rating_intelligence`
and never raw provider payloads. `evaluate_player_diagnostics` /
`evaluate_team_diagnostics` are the entry points most callers want.
"""

from __future__ import annotations

from football_intelligence.diagnostics.models import (
    MODEL_VERSION,
    DiagnosticEntityType,
    DiagnosticFinding,
    DiagnosticSeverity,
)
from football_intelligence.diagnostics.orchestrator import (
    PlayerDiagnosticInputs,
    TeamDiagnosticInputs,
    evaluate_player_diagnostics,
    evaluate_team_diagnostics,
)

__all__ = [
    "MODEL_VERSION",
    "DiagnosticEntityType",
    "DiagnosticFinding",
    "DiagnosticSeverity",
    "PlayerDiagnosticInputs",
    "TeamDiagnosticInputs",
    "evaluate_player_diagnostics",
    "evaluate_team_diagnostics",
]
