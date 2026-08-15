from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from football_intelligence.providers.openfootball import (
    OpenFootballClient,
    OpenFootballError,
    OpenFootballNotFoundError,
)


def _mock_response(body: bytes, status: int = 200) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.read.return_value = body
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def test_get_season_json_returns_parsed_payload() -> None:
    body = json.dumps({"name": "English Premier League 2025/26", "matches": []}).encode("utf-8")
    with patch(
        "football_intelligence.providers.openfootball.urlopen",
        return_value=_mock_response(body),
    ):
        client = OpenFootballClient()
        response = client.get_season_json(competition_file="en.1.json", season_code="2025-26")
    assert response.payload["name"] == "English Premier League 2025/26"
    assert response.competition_file == "en.1.json"
    assert response.season_code == "2025-26"


def test_404_is_not_found() -> None:
    error = HTTPError(
        "https://raw.githubusercontent.com/openfootball/football.json/master/2099-00/en.1.json",
        404,
        "Not Found",
        {},
        None,
    )  # type: ignore[arg-type]
    with patch(
        "football_intelligence.providers.openfootball.urlopen",
        side_effect=error,
    ):
        client = OpenFootballClient()
        try:
            client.get_season_json(competition_file="en.1.json", season_code="2099-00")
            raise AssertionError("expected OpenFootballNotFoundError")
        except OpenFootballNotFoundError:
            pass


def test_payload_missing_matches_key_is_rejected_not_guessed() -> None:
    body = json.dumps({"name": "unexpected shape"}).encode("utf-8")
    with patch(
        "football_intelligence.providers.openfootball.urlopen",
        return_value=_mock_response(body),
    ):
        client = OpenFootballClient()
        try:
            client.get_season_json(competition_file="en.1.json", season_code="2025-26")
            raise AssertionError("expected OpenFootballError")
        except OpenFootballError:
            pass


def test_invalid_json_body_is_rejected() -> None:
    with patch(
        "football_intelligence.providers.openfootball.urlopen",
        return_value=_mock_response(b"not json"),
    ):
        client = OpenFootballClient()
        try:
            client.get_season_json(competition_file="en.1.json", season_code="2025-26")
            raise AssertionError("expected OpenFootballError")
        except OpenFootballError:
            pass
