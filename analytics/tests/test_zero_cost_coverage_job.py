from __future__ import annotations

from pathlib import Path

from football_intelligence.ingestion.raw_store import LocalRawStore
from football_intelligence.jobs.run_zero_cost_coverage import (
    PLANNED_REQUESTS_BASE,
    _competition_external_id,
    _probe_football_data_org,
)


def test_probe_football_data_org_without_token_is_token_required_and_makes_no_request(
    tmp_path: Path,
) -> None:
    raw_store = LocalRawStore(tmp_path)
    status, requests, observations = _probe_football_data_org(raw_store=raw_store, token="")
    assert status == "token_required"
    assert requests == 0
    assert observations == []


def test_competition_external_id_resolves_configured_providers() -> None:
    assert _competition_external_id("thesportsdb") == "4331"
    assert _competition_external_id("openligadb") == "bl1"


def test_planned_requests_base_is_small_and_bounded() -> None:
    # thesportsdb(1) + openligadb(1) + statsbomb(competitions + matches + N events)
    assert 4 <= PLANNED_REQUESTS_BASE <= 10
