from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from football_intelligence.providers.football_data_uk import (
    FootballDataUkClient,
    FootballDataUkNotFoundError,
)


def _mock_response(body: bytes, status: int = 200) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.read.return_value = body
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def test_get_results_csv_returns_real_csv_text() -> None:
    csv_body = b"Div,Date,Time,HomeTeam,AwayTeam\nE0,15/08/2025,20:00,Liverpool,Bournemouth\n"
    with patch(
        "football_intelligence.providers.football_data_uk.urlopen",
        return_value=_mock_response(csv_body),
    ):
        client = FootballDataUkClient()
        response = client.get_results_csv(division_code="E0", season_code="2526")
    assert response.csv_text.startswith("Div,Date")
    assert response.division_code == "E0"
    assert response.season_code == "2526"


def test_html_error_page_is_not_found_not_fabricated_csv() -> None:
    # A season/division combination with no published file redirects to an
    # HTML "300 Multiple Choices" page (verified live) rather than 404ing --
    # this must be detected as "not found", never parsed as if it were CSV.
    html_body = (
        b"<!DOCTYPE HTML PUBLIC><html><head><title>300 Multiple Choices</title></head></html>"
    )
    with patch(
        "football_intelligence.providers.football_data_uk.urlopen",
        return_value=_mock_response(html_body),
    ):
        client = FootballDataUkClient()
        try:
            client.get_results_csv(division_code="I1", season_code="2627")
            raise AssertionError("expected FootballDataUkNotFoundError")
        except FootballDataUkNotFoundError:
            pass


def test_http_300_is_not_found_triggers_season_fallback() -> None:
    # Verified live during a bounded Coverage Lab run: a season/division
    # combination with no published file raises urllib HTTPError(300)
    # ("Multiple Choices", a redirect urllib does not auto-follow), not a
    # 200-with-HTML-body. This must ALSO be treated as "not found" so the
    # caller's newer-season-then-older-season fallback actually runs,
    # instead of stopping after one failed attempt.
    error = HTTPError(
        "https://www.football-data.co.uk/mmz4281/2627/I1.csv", 300, "Multiple Choices", {}, None
    )  # type: ignore[arg-type]
    with patch(
        "football_intelligence.providers.football_data_uk.urlopen",
        side_effect=error,
    ):
        client = FootballDataUkClient()
        try:
            client.get_results_csv(division_code="I1", season_code="2627")
            raise AssertionError("expected FootballDataUkNotFoundError")
        except FootballDataUkNotFoundError:
            pass
