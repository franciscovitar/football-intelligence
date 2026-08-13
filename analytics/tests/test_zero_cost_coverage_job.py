from __future__ import annotations

import json
from pathlib import Path

import pytest

from football_intelligence.ingestion.raw_store import LocalRawStore
from football_intelligence.jobs import run_zero_cost_coverage
from football_intelligence.jobs.run_zero_cost_coverage import (
    PLANNED_REQUESTS_BASE,
    _competition_external_id,
    _probe_football_data_org,
)
from football_intelligence.providers.football_data_org import FootballDataOrgClient


class _StubFootballDataOrgClient(FootballDataOrgClient):
    """Deterministic fixture client: no network I/O, matches by URL suffix."""

    def __init__(self, responses: dict[str, dict[str, object]]) -> None:
        super().__init__("test-token", max_attempts=1)
        self._responses = responses

    def _request_once(self, url: str) -> tuple[int, bytes]:
        for suffix, body in self._responses.items():
            if url.endswith(suffix):
                return 200, json.dumps(body).encode()
        raise AssertionError(f"unexpected url for stub client: {url}")


def test_probe_football_data_org_without_token_is_token_required_and_makes_no_request(
    tmp_path: Path,
) -> None:
    raw_store = LocalRawStore(tmp_path)
    status, requests, observations, meta = _probe_football_data_org(raw_store=raw_store, token="")
    assert status == "token_required"
    assert requests == 0
    assert observations == []
    assert meta == {}


def test_probe_football_data_org_with_token_probes_bundesliga_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_store = LocalRawStore(tmp_path)
    competitions_payload = {"competitions": [{"id": 2002, "name": "Bundesliga", "code": "BL1"}]}
    matches_payload = {
        "matches": [
            {
                "id": 1,
                "utcDate": "2025-08-22T18:30:00Z",
                "status": "FINISHED",
                "homeTeam": {"name": "Sample United"},
                "awayTeam": {"name": "Sample City"},
                "score": {"fullTime": {"home": 2, "away": 1}},
            }
        ]
    }
    stub = _StubFootballDataOrgClient(
        {"v4/competitions": competitions_payload, "v4/competitions/BL1/matches": matches_payload}
    )
    monkeypatch.setattr(run_zero_cost_coverage, "FootballDataOrgClient", lambda token: stub)

    status, requests, observations, meta = _probe_football_data_org(
        raw_store=raw_store, token="secret"
    )

    assert status == "ok"
    assert requests == 2
    assert meta["matches_probed_competition"] == "GER_BL1"
    assert "GER_BL1" in meta["supported_target_competitions"]
    match_metric_names = {obs.metric_name for obs in observations if obs.entity_type == "match"}
    assert match_metric_names == {"status", "home_score", "away_score"}


def test_probe_football_data_org_skips_matches_when_target_competition_not_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_store = LocalRawStore(tmp_path)
    competitions_payload = {"competitions": [{"id": 2021, "name": "Premier League", "code": "PL"}]}
    stub = _StubFootballDataOrgClient({"v4/competitions": competitions_payload})
    monkeypatch.setattr(run_zero_cost_coverage, "FootballDataOrgClient", lambda token: stub)

    status, requests, observations, meta = _probe_football_data_org(
        raw_store=raw_store, token="secret"
    )

    assert status == "ok"
    assert requests == 1
    assert meta["matches_probed_competition"] is None
    assert "GER_BL1" not in meta["supported_target_competitions"]
    assert "ENG_PL" in meta["supported_target_competitions"]
    assert all(obs.entity_type != "match" for obs in observations)


def test_competition_external_id_resolves_configured_providers() -> None:
    assert _competition_external_id("thesportsdb") == "4331"
    assert _competition_external_id("openligadb") == "bl1"


def test_planned_requests_base_is_small_and_bounded() -> None:
    # thesportsdb(1) + openligadb(1) + statsbomb(competitions + matches + N events)
    assert 4 <= PLANNED_REQUESTS_BASE <= 10
