from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from football_intelligence.providers.rsssf import (
    RSSSFArgentina2016Client,
    RSSSFSchemaError,
    parse_argentina_2016_document,
)


def _complete_document() -> str:
    teams = [f"Team {index:02d}" for index in range(30)]
    pairs = [(teams[index], teams[index + 1]) for index in range(0, 30, 2)]
    lines = [
        "<html><body><h4>Campeonato de Primera División 2016</h4><pre>",
    ]
    for round_number in range(1, 17):
        lines.append(f"Round {round_number}:")
        match_date = 4 + round_number
        if round_number == 8:
            lines.append("Intergroup")
            lines.append(f"[Feb {match_date} Mon]")
            for pair_index, (home, away) in enumerate(pairs):
                lines.append(f"{home} 1-0 {away} [Venue {round_number}-{pair_index}]")
            continue

        lines.append("Group 1")
        lines.append(f"[Feb {match_date} Mon]")
        for pair_index, (home, away) in enumerate(pairs[:7]):
            lines.append(f"{home} 1-0 {away} [Venue {round_number}-{pair_index}]")
        lines.append("Group 2")
        lines.append(f"[Feb {match_date} Mon]")
        for pair_index, (home, away) in enumerate(pairs[7:14], start=7):
            lines.append(f"{home} 1-0 {away} [Venue {round_number}-{pair_index}]")
        lines.append("Intergroup")
        lines.append(f"[Feb {match_date} Mon]")
        home, away = pairs[14]
        lines.append(f"{home} 1-0 {away} [Venue {round_number}-14]")

    lines.extend(
        [
            "Round 17:",
            "Match between the second of each group",
            "[May 28 Sat]",
            "Team 00 0-1 Team 01 [Third Place Venue]",
            "Final",
            "[May 29 Sun]",
            "Team 02 0-4 Team 03 [Final Venue]",
            "</pre><h4>Relegation</h4></body></html>",
        ]
    )
    return "\n".join(lines)


def _mock_response(body: bytes, *, content_type: str) -> MagicMock:
    response = MagicMock()
    response.status = 200
    response.read.return_value = body
    response.headers = {"Content-Type": content_type}
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    return response


def test_parse_complete_argentina_2016_document_passes_hard_structure_gates() -> None:
    raw = _complete_document().encode("windows-1252")
    snapshot = parse_argentina_2016_document(
        raw,
        content_type="text/html; charset=windows-1252",
        fetched_at=datetime(2026, 8, 27, tzinfo=UTC),
    )

    assert len(snapshot.matches) == 242
    assert len({match.external_id for match in snapshot.matches}) == 242
    assert snapshot.decoded_charset.casefold() == "windows-1252"
    assert snapshot.matches[-2].phase == "third_place_playoff"
    assert snapshot.matches[-2].match_date.isoformat() == "2016-05-28"
    assert snapshot.matches[-1].phase == "final"
    assert snapshot.matches[-1].match_date.isoformat() == "2016-05-29"


def test_incomplete_tournament_fails_closed_instead_of_returning_partial_backbone() -> None:
    document = _complete_document()
    document = document.replace("Team 00 1-0 Team 01 [Venue 1-0]\n", "", 1)

    with pytest.raises(RSSSFSchemaError, match="completeness gate failed"):
        parse_argentina_2016_document(
            document.encode("windows-1252"),
            content_type="text/html; charset=windows-1252",
        )


def test_provider_local_match_identity_does_not_change_when_score_is_corrected() -> None:
    original = parse_argentina_2016_document(
        _complete_document().encode("windows-1252"),
        content_type="text/html; charset=windows-1252",
    )
    corrected_document = _complete_document().replace(
        "Team 00 1-0 Team 01 [Venue 1-0]",
        "Team 00 2-0 Team 01 [Venue 1-0]",
        1,
    )
    corrected = parse_argentina_2016_document(
        corrected_document.encode("windows-1252"),
        content_type="text/html; charset=windows-1252",
    )

    assert original.matches[0].external_id == corrected.matches[0].external_id
    assert original.matches[0].home_score == 1
    assert corrected.matches[0].home_score == 2


def test_client_uses_declared_windows_1252_charset_and_returns_certified_snapshot() -> None:
    body = _complete_document().encode("windows-1252")
    response = _mock_response(body, content_type="text/html; charset=windows-1252")
    with patch("football_intelligence.providers.rsssf.urlopen", return_value=response):
        client = RSSSFArgentina2016Client(max_attempts=1)
        snapshot = client.fetch()

    assert len(snapshot.matches) == 242
    assert snapshot.content_type == "text/html; charset=windows-1252"
    assert snapshot.raw_sha256.startswith("sha256:")


def test_client_retries_one_transient_503_then_succeeds() -> None:
    error = HTTPError(
        "https://www.rsssf.org/tablesa/arg2016.html",
        503,
        "Service Unavailable",
        {},
        None,
    )  # type: ignore[arg-type]
    response = _mock_response(
        _complete_document().encode("windows-1252"),
        content_type="text/html; charset=windows-1252",
    )
    with (
        patch("football_intelligence.providers.rsssf.urlopen", side_effect=[error, response]),
        patch("football_intelligence.providers.rsssf.time.sleep"),
    ):
        snapshot = RSSSFArgentina2016Client(max_attempts=2).fetch()

    assert len(snapshot.matches) == 242
