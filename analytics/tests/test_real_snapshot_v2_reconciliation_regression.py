"""Block 20D.3 corrective pass, section 11: the real Football-Data.co.uk x
OpenFootball ENG_PL 2025/26 `resolve_and_reconcile()` regression Block
20D.2 documented (`docs/ENTITY_RESOLUTION_V2.md`, "Regression verification")
does NOT require PostgreSQL -- that assumption, carried into an earlier
Block 20D.3 summary, was checked against the actual code rather than
repeated. `resolve_and_reconcile()` is a pure, in-memory function; the only
genuinely DB-backed step in this repository's ENG_PL 2025/26 pipeline is
canonical loading into `football.*` (`jobs/load_real_snapshot.py`,
`tests/integration/test_real_snapshot_v2_idempotency.py`), a different,
separate operation this test never touches.

This test reads the two already-committed, real real snapshot files
(`data/real/2025-26/eng_pl_matches.json`, `eng_pl_matches_openfootball.json`
-- both pre-existing, accepted evidence, unrelated to Wyscout/StatsBomb)
directly off disk, deserializes their `records` back into
`NormalizedObservation`s (the exact shape `jobs/collect_real_snapshot.py`'s
`build_matches_output()` / `jobs/build_real_snapshot_v2.py`'s
`_build_openfootball_output()` serialize), and calls the real
`resolve_and_reconcile()` -- no network request, no database connection, no
`DATABASE_URL`."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from football_intelligence.data_mesh.models import NormalizedObservation
from football_intelligence.data_mesh.pipeline import resolve_and_reconcile

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "real" / "2025-26"


def _load_observations(filename: str) -> list[NormalizedObservation]:
    payload = json.loads((_DATA_DIR / filename).read_text(encoding="utf-8"))
    observations = []
    for record in payload["records"]:
        observations.append(
            NormalizedObservation(
                source_code=record["source_code"],
                source_type=record["source_type"],
                entity_type=record["entity_type"],
                entity_source_id=record["entity_source_id"],
                entity_identity_hints=record["entity_identity_hints"],
                metric_name=record["metric_name"],
                value=record["value"],
                observed_at=datetime.fromisoformat(record["observed_at"]),
                source_timestamp=(
                    datetime.fromisoformat(record["source_timestamp"])
                    if record["source_timestamp"]
                    else None
                ),
                source_reference=record["source_reference"],
                ingestion_run_id=record["ingestion_run_id"],
                semantic_version=record["semantic_version"],
                metric_granularity=record.get("metric_granularity"),
            )
        )
    return observations


def _real_snapshot_files_present() -> bool:
    return (_DATA_DIR / "eng_pl_matches.json").exists() and (
        _DATA_DIR / "eng_pl_matches_openfootball.json"
    ).exists()


pytestmark = pytest.mark.skipif(
    not _real_snapshot_files_present(),
    reason="committed real ENG_PL 2025/26 snapshot files not present in this worktree",
)


def _real_observations() -> list[NormalizedObservation]:
    return _load_observations("eng_pl_matches.json") + _load_observations(
        "eng_pl_matches_openfootball.json"
    )


def _decisions_without_wall_clock(decisions: list[Any]) -> list[tuple]:
    # `calculated_at` is `datetime.now(UTC)` at call time by construction --
    # excluded here so idempotence is checked on the actual data content,
    # not incidentally defeated by two calls landing in different
    # microseconds.
    return sorted(
        (
            d.logical_entity_key,
            d.entity_type,
            d.metric_name,
            d.candidate_value,
            d.status,
            d.confidence,
            d.winning_source_code,
            d.participating_sources,
            d.source_count,
        )
        for d in decisions
    )


def test_real_eng_pl_2025_26_reconciliation_matches_the_certified_baseline() -> None:
    decisions, meta = resolve_and_reconcile(_real_observations())

    match_decisions = [d for d in decisions if d.entity_type == "match"]
    team_name_decisions = [
        d for d in decisions if d.entity_type == "team" and d.metric_name == "name"
    ]

    assert len({d.logical_entity_key for d in match_decisions}) == 380
    assert len(team_name_decisions) == 20
    assert len(match_decisions) == 1140
    assert all(d.status == "agreed" for d in match_decisions)
    assert meta["unresolved_observation_count"] == 0


def test_real_eng_pl_2025_26_reconciliation_is_idempotent() -> None:
    observations = _real_observations()
    decisions_first, meta_first = resolve_and_reconcile(observations)
    decisions_second, meta_second = resolve_and_reconcile(observations)

    assert _decisions_without_wall_clock(decisions_first) == _decisions_without_wall_clock(
        decisions_second
    )
    assert meta_first == meta_second


def test_real_eng_pl_2025_26_team_name_conflicts_are_the_pre_existing_known_20() -> None:
    # Pre-existing, documented, short-vs-official-long-form team name string
    # conflicts (e.g. "Wolves" vs "Wolverhampton Wanderers FC") -- real,
    # honest evidence of a naming difference between the two sources, never
    # silently picked/averaged away. This test pins the count so a future
    # regression (e.g. new team entering the league with a genuine naming
    # convergence gap) is noticed rather than silently absorbed.
    decisions, _meta = resolve_and_reconcile(_real_observations())
    name_conflicts = [
        d
        for d in decisions
        if d.entity_type == "team" and d.metric_name == "name" and d.status == "conflict"
    ]
    assert len(name_conflicts) == 20
