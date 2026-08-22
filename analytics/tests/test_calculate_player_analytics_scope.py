from __future__ import annotations

import pytest

from football_intelligence.jobs.calculate_player_analytics import resolve_analysis_scope


def test_competition_scope_defaults_to_explicit_competition_key() -> None:
    competition_codes, scope_key, competition = resolve_analysis_scope(
        season="2017/18",
        competition="eng_pl",
        scope_key=None,
    )

    assert competition_codes == ("ENG_PL",)
    assert scope_key == "competition:ENG_PL:2017/18"
    assert competition == "ENG_PL"


def test_legacy_core_scope_remains_backward_compatible() -> None:
    competition_codes, scope_key, competition = resolve_analysis_scope(
        season="2025/26",
        competition=None,
        scope_key=None,
    )

    assert "ENG_PL" in competition_codes
    assert len(competition_codes) > 1
    assert scope_key == "core:2025/26"
    assert competition is None


def test_explicit_scope_key_is_preserved_with_competition_filter() -> None:
    competition_codes, scope_key, competition = resolve_analysis_scope(
        season="2017/18",
        competition="ENG_PL",
        scope_key="historical:verified:eng-pl-2017-18",
    )

    assert competition_codes == ("ENG_PL",)
    assert scope_key == "historical:verified:eng-pl-2017-18"
    assert competition == "ENG_PL"


def test_unknown_competition_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unsupported --competition"):
        resolve_analysis_scope(
            season="2017/18",
            competition="NOT_A_LEAGUE",
            scope_key=None,
        )
