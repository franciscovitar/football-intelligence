from football_intelligence.config.core_leagues import CORE_LEAGUES, league_by_code


def test_core_league_catalog_is_exact() -> None:
    assert [league.code for league in CORE_LEAGUES] == [
        "ARG_LPF",
        "ENG_PL",
        "ESP_LL",
        "ITA_SA",
        "GER_BL1",
        "FRA_L1",
    ]
    assert len({league.provider_league_id for league in CORE_LEAGUES}) == 6
    assert league_by_code("ENG_PL").provider_league_id == 39
