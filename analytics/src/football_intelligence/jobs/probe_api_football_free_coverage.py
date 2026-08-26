"""Probe API-Football league/season coverage with exactly one authenticated call.

This is a bounded technical-reconnaissance job, not a product ingestion adapter.
It calls only ``GET /leagues`` once, freezes the raw response, resolves the six
Football Intelligence core competitions by exact country + league name, and
writes a provider-local coverage summary plus a generic static-snapshot manifest.

The probe deliberately does not call ``/players`` or any match endpoint. A
successful result proves only what the authenticated ``/leagues`` catalogue
returned at acquisition time; it does not prove that every listed historical
season is accessible through every endpoint on the current account plan.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from football_intelligence.ingestion.static_snapshot import (
    SnapshotFile,
    StaticSnapshotManifest,
)

SOURCE_CODE = "api_football"
SOURCE_REFERENCE = "https://v3.football.api-sports.io/leagues"
HTTP_TIMEOUT_SECONDS = 30
API_KEY_ENV = "API_FOOTBALL_KEY"
USER_AGENT = "FootballIntelligence/0.1 (+https://github.com/franciscovitar/football-intelligence)"

CORE_TARGETS: tuple[tuple[str, str, str], ...] = (
    ("ARG_LPF", "Argentina", "Liga Profesional Argentina"),
    ("ENG_PL", "England", "Premier League"),
    ("ESP_LL", "Spain", "La Liga"),
    ("FRA_L1", "France", "Ligue 1"),
    ("GER_BL1", "Germany", "Bundesliga"),
    ("ITA_SA", "Italy", "Serie A"),
)


class ApiFootballCoverageProbeError(RuntimeError):
    """The bounded API-Football coverage probe could not complete safely."""


@dataclass(frozen=True, slots=True)
class SeasonCoverage:
    year: int
    start: str | None
    end: str | None
    current: bool | None
    players: bool | None
    fixture_player_statistics: bool | None
    fixture_statistics: bool | None
    lineups: bool | None
    events: bool | None


@dataclass(frozen=True, slots=True)
class CompetitionCoverage:
    competition_code: str
    provider_league_id: int
    provider_league_name: str
    country_name: str
    seasons: tuple[SeasonCoverage, ...]


@dataclass(frozen=True, slots=True)
class ApiFootballCoverageReport:
    source_code: str
    competitions: tuple[CompetitionCoverage, ...]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    manifest: StaticSnapshotManifest
    report: ApiFootballCoverageReport


def parse_core_coverage(raw: bytes) -> ApiFootballCoverageReport:
    """Parse the six exact core competitions from one raw ``/leagues`` response."""

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiFootballCoverageProbeError("/leagues response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ApiFootballCoverageProbeError("/leagues response root must be a JSON object")
    root = cast(dict[str, Any], payload)

    errors = root.get("errors")
    if errors not in (None, [], {}):
        raise ApiFootballCoverageProbeError(f"API-Football returned errors: {errors!r}")

    response = root.get("response")
    if not isinstance(response, list):
        raise ApiFootballCoverageProbeError("/leagues response must contain a response array")

    resolved: list[CompetitionCoverage] = []
    for competition_code, expected_country, expected_name in CORE_TARGETS:
        matches: list[dict[str, Any]] = []
        for item in response:
            if not isinstance(item, dict):
                continue
            league = item.get("league")
            country = item.get("country")
            if not isinstance(league, dict) or not isinstance(country, dict):
                continue
            if league.get("name") == expected_name and country.get("name") == expected_country:
                matches.append(cast(dict[str, Any], item))

        if len(matches) != 1:
            raise ApiFootballCoverageProbeError(
                f"{competition_code}: expected exactly one {expected_country}/{expected_name} "
                f"match, got {len(matches)}"
            )
        resolved.append(_competition_coverage(competition_code, matches[0]))

    return ApiFootballCoverageReport(
        source_code=SOURCE_CODE,
        competitions=tuple(sorted(resolved, key=lambda item: item.competition_code)),
    )


def collect_probe(*, snapshot_id: str, output_dir: Path, api_key: str) -> ProbeResult:
    """Make exactly one API call, then freeze and summarize the returned catalogue."""

    if not snapshot_id.strip():
        raise ApiFootballCoverageProbeError("snapshot_id must be non-blank")
    if not api_key.strip():
        raise ApiFootballCoverageProbeError("API-Football key must be non-blank")

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    raw_path = output_dir / "leagues.json"
    coverage_path = output_dir / "coverage.json"
    for path in (manifest_path, raw_path, coverage_path):
        if path.exists():
            raise ApiFootballCoverageProbeError(f"refusing to overwrite existing file {path}")

    raw = _fetch_leagues(api_key=api_key)
    report = parse_core_coverage(raw)
    coverage_raw = (
        json.dumps(_report_payload(report), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()

    raw_path.write_bytes(raw)
    coverage_path.write_bytes(coverage_raw)

    all_seasons = tuple(
        sorted(
            {
                str(season.year)
                for competition in report.competitions
                for season in competition.seasons
            }
        )
    )
    if not all_seasons:
        raise ApiFootballCoverageProbeError("resolved competitions contain no seasons")

    files = tuple(
        sorted(
            (
                SnapshotFile(
                    path="coverage.json",
                    sha256=hashlib.sha256(coverage_raw).hexdigest(),
                    byte_size=len(coverage_raw),
                ),
                SnapshotFile(
                    path="leagues.json",
                    sha256=hashlib.sha256(raw).hexdigest(),
                    byte_size=len(raw),
                ),
            ),
            key=lambda item: item.path,
        )
    )
    manifest = StaticSnapshotManifest(
        snapshot_id=snapshot_id.strip(),
        source_code=SOURCE_CODE,
        acquired_at=datetime.now(UTC),
        source_reference=SOURCE_REFERENCE,
        competition_codes=tuple(code for code, _, _ in CORE_TARGETS),
        season_labels=all_seasons,
        data_grains=("competition",),
        files=files,
        notes=(
            "One-call API-Football /leagues reconnaissance snapshot. Coverage flags are "
            "provider catalogue evidence only and do not certify historical endpoint access, "
            "publication rights, or product-source approval."
        ),
    )
    manifest_path.write_text(
        json.dumps(_manifest_payload(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ProbeResult(manifest=manifest, report=report)


def _fetch_leagues(*, api_key: str) -> bytes:
    request = Request(
        SOURCE_REFERENCE,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "x-apisports-key": api_key,
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return cast(bytes, response.read())
    except HTTPError as exc:
        raise ApiFootballCoverageProbeError(f"/leagues HTTP {exc.code}") from exc
    except (URLError, TimeoutError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else str(exc)
        raise ApiFootballCoverageProbeError(f"/leagues network error: {reason}") from exc


def _competition_coverage(
    competition_code: str, item: dict[str, Any]
) -> CompetitionCoverage:
    league = _required_dict(item, "league", context=competition_code)
    country = _required_dict(item, "country", context=competition_code)
    league_id = _required_positive_int(league, "id", context=competition_code)
    league_name = _required_string(league, "name", context=competition_code)
    country_name = _required_string(country, "name", context=competition_code)

    seasons_raw = item.get("seasons")
    if not isinstance(seasons_raw, list) or not seasons_raw:
        raise ApiFootballCoverageProbeError(f"{competition_code}: seasons must be non-empty")

    seasons = tuple(
        sorted(
            (_season_coverage(competition_code, raw) for raw in seasons_raw),
            key=lambda season: season.year,
        )
    )
    if len({season.year for season in seasons}) != len(seasons):
        raise ApiFootballCoverageProbeError(f"{competition_code}: duplicate season years")

    return CompetitionCoverage(
        competition_code=competition_code,
        provider_league_id=league_id,
        provider_league_name=league_name,
        country_name=country_name,
        seasons=seasons,
    )


def _season_coverage(competition_code: str, raw: object) -> SeasonCoverage:
    if not isinstance(raw, dict):
        raise ApiFootballCoverageProbeError(f"{competition_code}: season entry must be an object")
    season = cast(dict[str, Any], raw)
    year = _required_positive_int(season, "year", context=competition_code)
    coverage = season.get("coverage")
    coverage_dict = cast(dict[str, Any], coverage) if isinstance(coverage, dict) else {}
    fixtures = coverage_dict.get("fixtures")
    fixtures_dict = cast(dict[str, Any], fixtures) if isinstance(fixtures, dict) else {}

    return SeasonCoverage(
        year=year,
        start=_optional_string(season.get("start"), context=f"{competition_code}/{year}/start"),
        end=_optional_string(season.get("end"), context=f"{competition_code}/{year}/end"),
        current=_optional_bool(season.get("current"), context=f"{competition_code}/{year}/current"),
        players=_optional_bool(
            coverage_dict.get("players"), context=f"{competition_code}/{year}/coverage.players"
        ),
        fixture_player_statistics=_optional_bool(
            fixtures_dict.get("statistics_players"),
            context=f"{competition_code}/{year}/coverage.fixtures.statistics_players",
        ),
        fixture_statistics=_optional_bool(
            fixtures_dict.get("statistics_fixtures"),
            context=f"{competition_code}/{year}/coverage.fixtures.statistics_fixtures",
        ),
        lineups=_optional_bool(
            fixtures_dict.get("lineups"),
            context=f"{competition_code}/{year}/coverage.fixtures.lineups",
        ),
        events=_optional_bool(
            fixtures_dict.get("events"),
            context=f"{competition_code}/{year}/coverage.fixtures.events",
        ),
    )


def _report_payload(report: ApiFootballCoverageReport) -> dict[str, object]:
    return {
        "source_code": report.source_code,
        "competitions": [
            {
                "competition_code": competition.competition_code,
                "provider_league_id": competition.provider_league_id,
                "provider_league_name": competition.provider_league_name,
                "country_name": competition.country_name,
                "seasons": [asdict(season) for season in competition.seasons],
            }
            for competition in report.competitions
        ],
    }


def _manifest_payload(manifest: StaticSnapshotManifest) -> dict[str, object]:
    return {
        "snapshot_id": manifest.snapshot_id,
        "source_code": manifest.source_code,
        "acquired_at": manifest.acquired_at.isoformat(),
        "source_reference": manifest.source_reference,
        "competition_codes": list(manifest.competition_codes),
        "season_labels": list(manifest.season_labels),
        "data_grains": list(manifest.data_grains),
        "files": [asdict(file) for file in manifest.files],
        "notes": manifest.notes,
    }


def _required_dict(payload: dict[str, Any], key: str, *, context: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ApiFootballCoverageProbeError(f"{context}: {key} must be an object")
    return cast(dict[str, Any], value)


def _required_string(payload: dict[str, Any], key: str, *, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiFootballCoverageProbeError(f"{context}: {key} must be a non-blank string")
    return value.strip()


def _required_positive_int(payload: dict[str, Any], key: str, *, context: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ApiFootballCoverageProbeError(f"{context}: {key} must be a positive integer")
    return value


def _optional_string(value: object, *, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ApiFootballCoverageProbeError(f"{context} must be a non-blank string or null")
    return value.strip()


def _optional_bool(value: object, *, context: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ApiFootballCoverageProbeError(f"{context} must be a boolean or null")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Make one API-Football /leagues call and freeze six-league coverage evidence."
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    api_key = os.environ.get(API_KEY_ENV, "")
    if not api_key:
        raise SystemExit(
            f"API-FOOTBALL COVERAGE PROBE: FAIL - missing {API_KEY_ENV}; "
            "do not pass API keys on the command line"
        )
    try:
        result = collect_probe(
            snapshot_id=args.snapshot_id,
            output_dir=args.output_dir,
            api_key=api_key,
        )
    except (OSError, ApiFootballCoverageProbeError) as exc:
        raise SystemExit(f"API-FOOTBALL COVERAGE PROBE: FAIL - {exc}") from exc

    print(
        f"API-FOOTBALL COVERAGE PROBE: PASS snapshot={result.manifest.snapshot_id} "
        f"competitions={len(result.report.competitions)} requests=1 "
        f"manifest={args.output_dir / 'manifest.json'}"
    )


if __name__ == "__main__":
    main()
