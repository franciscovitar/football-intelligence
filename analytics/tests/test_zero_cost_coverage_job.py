from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from football_intelligence.data_mesh.adapters.football_data_uk import parse_results_csv
from football_intelligence.ingestion.raw_store import LocalRawStore
from football_intelligence.jobs import run_zero_cost_coverage
from football_intelligence.jobs.run_zero_cost_coverage import (
    MAX_REQUEST_BUDGET,
    PLANNED_REQUESTS_BASE,
    _build_probe_results,
    _competition_external_id,
    _probe_football_data_org,
    expected_current_season,
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


def test_planned_requests_base_respects_hard_cap() -> None:
    # thesportsdb (10 competitions + event-stats + lineup samples) + openligadb
    # + statsbomb + football-data-uk (2 attempts x 7 covered competitions) --
    # a much larger bounded budget than Block 14's, but the task's explicit
    # hard cap (<=35 HTTP requests) must never be exceeded, even before a
    # football-data.org token is added on top.
    assert PLANNED_REQUESTS_BASE <= MAX_REQUEST_BUDGET
    assert MAX_REQUEST_BUDGET == 35


def test_expected_current_season_cross_year_competitions_roll_over_in_august() -> None:
    mid_season = date(2026, 3, 1)
    season_start = date(2026, 8, 13)
    assert expected_current_season("ENG_PL", mid_season) == "2025-2026"
    assert expected_current_season("GER_BL1", mid_season) == "2025-2026"
    assert expected_current_season("ENG_PL", season_start) == "2026-2027"
    assert expected_current_season("GER_BL1", season_start) == "2026-2027"


def test_expected_current_season_calendar_year_competitions_use_the_run_year() -> None:
    assert expected_current_season("ARG_LPF", date(2026, 3, 1)) == "2026"
    assert expected_current_season("ARG_LPF", date(2026, 8, 13)) == "2026"
    assert expected_current_season("USA_MLS", date(2026, 8, 13)) == "2026"
    assert expected_current_season("BRA_A", date(2026, 8, 13)) == "2026"


def _fd_uk_probe_results(*, season_by_competition: dict[str, str], newer_season_code: str):
    observations = parse_results_csv(
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,HF,AF,HC,AC,HY,AY,HR,AR\n"
        "D1,22/08/2025,18:30,Bayern Munich,RB Leipzig,6,0,H,20,5,12,2,8,10,7,3,1,2,0,0\n",
        division_code="D1",
        season_code=season_by_competition["GER_BL1"],
        ingestion_run_id=None,
    )
    return _build_probe_results(
        thesportsdb_statuses={},
        thesportsdb_observations_by_competition={},
        openligadb_status="error: n/a",
        openligadb_observations=[],
        statsbomb_status="error: n/a",
        statsbomb_observations=[],
        statsbomb_match_sample_size=0,
        fd_uk_statuses={"GER_BL1": "ok"},
        fd_uk_observations=observations,
        fd_uk_meta={
            "season_by_competition": season_by_competition,
            "newer_season_code": newer_season_code,
            "older_season_code": "2526",
        },
        fd_org_status="token_required",
        fd_org_observations=[],
        fd_org_meta={},
    )


def test_football_data_uk_fallback_season_is_tagged_not_current_period() -> None:
    probe_results = _fd_uk_probe_results(
        season_by_competition={"GER_BL1": "2526"}, newer_season_code="2627"
    )
    assert probe_results[("football-data-uk", "GER_BL1")].is_current_period is False


def test_football_data_uk_true_current_season_is_tagged_current_period() -> None:
    probe_results = _fd_uk_probe_results(
        season_by_competition={"GER_BL1": "2627"}, newer_season_code="2627"
    )
    assert probe_results[("football-data-uk", "GER_BL1")].is_current_period is True
