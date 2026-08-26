from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from football_intelligence.ingestion.static_snapshot import (
    load_static_snapshot_manifest,
    verify_static_snapshot_files,
)
from football_intelligence.jobs import probe_api_football_free_coverage as probe
from football_intelligence.jobs.probe_api_football_free_coverage import (
    ApiFootballCoverageProbeError,
    collect_probe,
    parse_core_coverage,
)


@pytest.fixture
def api_payload() -> dict[str, object]:
    targets = [
        (128, "Liga Profesional Argentina", "Argentina"),
        (39, "Premier League", "England"),
        (140, "La Liga", "Spain"),
        (61, "Ligue 1", "France"),
        (78, "Bundesliga", "Germany"),
        (135, "Serie A", "Italy"),
    ]
    response = []
    for league_id, league_name, country_name in targets:
        response.append(
            {
                "league": {"id": league_id, "name": league_name, "type": "League"},
                "country": {"name": country_name, "code": None, "flag": None},
                "seasons": [
                    {
                        "year": 2024,
                        "start": "2024-01-01",
                        "end": "2024-12-31",
                        "current": False,
                        "coverage": {
                            "fixtures": {
                                "events": True,
                                "lineups": True,
                                "statistics_fixtures": True,
                                "statistics_players": True,
                            },
                            "standings": True,
                            "players": True,
                        },
                    },
                    {
                        "year": 2025,
                        "start": "2025-01-01",
                        "end": "2025-12-31",
                        "current": True,
                        "coverage": {
                            "fixtures": {
                                "events": True,
                                "lineups": True,
                                "statistics_fixtures": True,
                                "statistics_players": False,
                            },
                            "players": True,
                        },
                    },
                ],
            }
        )
    response.append(
        {
            "league": {"id": 999, "name": "Premier League", "type": "League"},
            "country": {"name": "Exampleland"},
            "seasons": [{"year": 2025, "coverage": {"players": False}}],
        }
    )
    return {
        "get": "leagues",
        "parameters": [],
        "errors": [],
        "results": len(response),
        "paging": {"current": 1, "total": 1},
        "response": response,
    }


def _raw(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()


def test_parse_resolves_exact_six_core_competitions(api_payload: dict[str, object]) -> None:
    report = parse_core_coverage(_raw(api_payload))

    assert [item.competition_code for item in report.competitions] == [
        "ARG_LPF",
        "ENG_PL",
        "ESP_LL",
        "FRA_L1",
        "GER_BL1",
        "ITA_SA",
    ]
    by_code = {item.competition_code: item for item in report.competitions}
    assert by_code["ENG_PL"].provider_league_id == 39
    assert by_code["ESP_LL"].provider_league_id == 140
    assert [season.year for season in by_code["ARG_LPF"].seasons] == [2024, 2025]
    assert by_code["ITA_SA"].seasons[0].players is True
    assert by_code["ITA_SA"].seasons[1].fixture_player_statistics is False


def test_country_is_part_of_exact_resolution(api_payload: dict[str, object]) -> None:
    report = parse_core_coverage(_raw(api_payload))

    premier = next(item for item in report.competitions if item.competition_code == "ENG_PL")
    assert premier.country_name == "England"
    assert premier.provider_league_id == 39


def test_missing_target_fails_closed(api_payload: dict[str, object]) -> None:
    response = api_payload["response"]
    assert isinstance(response, list)
    api_payload["response"] = [
        item
        for item in response
        if not (
            isinstance(item, dict)
            and isinstance(item.get("country"), dict)
            and item["country"].get("name") == "Argentina"
        )
    ]

    with pytest.raises(ApiFootballCoverageProbeError, match="ARG_LPF"):
        parse_core_coverage(_raw(api_payload))


def test_api_errors_fail_closed(api_payload: dict[str, object]) -> None:
    api_payload["errors"] = {"token": "invalid"}

    with pytest.raises(ApiFootballCoverageProbeError, match="returned errors"):
        parse_core_coverage(_raw(api_payload))


def test_missing_coverage_field_remains_none(api_payload: dict[str, object]) -> None:
    response = api_payload["response"]
    assert isinstance(response, list)
    argentina = next(
        item
        for item in response
        if isinstance(item, dict)
        and isinstance(item.get("country"), dict)
        and item["country"].get("name") == "Argentina"
    )
    assert isinstance(argentina, dict)
    seasons = argentina["seasons"]
    assert isinstance(seasons, list)
    first = seasons[0]
    assert isinstance(first, dict)
    coverage = first["coverage"]
    assert isinstance(coverage, dict)
    coverage.pop("players")

    report = parse_core_coverage(_raw(api_payload))
    argentina_report = next(
        item for item in report.competitions if item.competition_code == "ARG_LPF"
    )
    assert argentina_report.seasons[0].players is None


def test_collect_probe_performs_one_fetch_and_freezes_checksummed_files(
    api_payload: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _raw(api_payload)
    calls = 0

    def fake_fetch(*, api_key: str) -> bytes:
        nonlocal calls
        calls += 1
        assert api_key == "test-secret"
        return raw

    monkeypatch.setattr(probe, "_fetch_leagues", fake_fetch)
    result = collect_probe(
        snapshot_id="api-football-free-coverage-test",
        output_dir=tmp_path,
        api_key="test-secret",
    )

    assert calls == 1
    assert result.manifest.source_code == "api_football"
    assert result.manifest.data_grains == ("competition",)
    assert result.manifest.competition_codes == (
        "ARG_LPF",
        "ENG_PL",
        "ESP_LL",
        "FRA_L1",
        "GER_BL1",
        "ITA_SA",
    )
    assert result.manifest.season_labels == ("2024", "2025")
    assert (tmp_path / "leagues.json").read_bytes() == raw
    assert hashlib.sha256(raw).hexdigest() == next(
        file.sha256 for file in result.manifest.files if file.path == "leagues.json"
    )

    loaded = load_static_snapshot_manifest(tmp_path / "manifest.json")
    verification = verify_static_snapshot_files(loaded, base_dir=tmp_path)
    assert verification.passed is True


def test_collect_probe_refuses_overwrite(
    api_payload: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _raw(api_payload)
    monkeypatch.setattr(probe, "_fetch_leagues", lambda *, api_key: raw)
    (tmp_path / "leagues.json").write_text("existing", encoding="utf-8")

    with pytest.raises(ApiFootballCoverageProbeError, match="refusing to overwrite"):
        collect_probe(
            snapshot_id="api-football-free-coverage-test",
            output_dir=tmp_path,
            api_key="test-secret",
        )
