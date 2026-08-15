from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from football_intelligence.providers.fpl import FplClient, FplElementNotFoundError


def _mock_response(body: bytes) -> MagicMock:
    response = MagicMock()
    response.read.return_value = body
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def test_get_bootstrap_static_extracts_expected_lists() -> None:
    payload = {
        "elements": [{"id": 1, "web_name": "Raya"}],
        "teams": [{"id": 1, "name": "Arsenal"}],
        "element_types": [{"id": 1, "singular_name": "Goalkeeper"}],
        "events": [],
    }
    body = json.dumps(payload).encode("utf-8")
    with patch(
        "football_intelligence.providers.fpl.urlopen",
        return_value=_mock_response(body),
    ):
        client = FplClient()
        response = client.get_bootstrap_static()

    assert response.elements == ({"id": 1, "web_name": "Raya"},)
    assert response.teams == ({"id": 1, "name": "Arsenal"},)
    assert response.element_types == ({"id": 1, "singular_name": "Goalkeeper"},)


def test_get_element_summary_extracts_history_past() -> None:
    payload = {
        "fixtures": [],
        "history": [],
        "history_past": [{"season_name": "2025/26", "minutes": 3330}],
    }
    body = json.dumps(payload).encode("utf-8")
    with patch(
        "football_intelligence.providers.fpl.urlopen",
        return_value=_mock_response(body),
    ):
        client = FplClient()
        response = client.get_element_summary(1)

    assert response.element_id == 1
    assert response.history_past == ({"season_name": "2025/26", "minutes": 3330},)


def test_get_element_summary_404_raises_typed_not_found_error() -> None:
    error = HTTPError(
        "https://fantasy.premierleague.com/api/element-summary/99999/",
        404,
        "Not Found",
        {},
        None,
    )  # type: ignore[arg-type]
    with patch(
        "football_intelligence.providers.fpl.urlopen",
        side_effect=error,
    ):
        client = FplClient()
        try:
            client.get_element_summary(99999)
            raise AssertionError("expected FplElementNotFoundError")
        except FplElementNotFoundError:
            pass


def test_element_id_must_be_positive() -> None:
    client = FplClient()
    try:
        client.get_element_summary(0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
