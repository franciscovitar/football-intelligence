from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}; old={old[:120]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    adapter = "analytics/src/football_intelligence/data_mesh/adapters/wyscout_open.py"
    replace_once(adapter, 'SEMANTIC_VERSION = "wyscout-open-v0.4"', 'SEMANTIC_VERSION = "wyscout-open-v0.5"')
    replace_once(
        adapter,
        '''# Spatial v1.2 has completed its real-source promotion audit only for
# England 2017/18. Other otherwise-certified Wyscout league scopes must
# keep spatial-v1.2 metrics absent until their own audit closes the same gate.
_SPATIAL_V1_2_VALIDATED_SCOPES = frozenset({("ENG_PL", "2017/18")})''',
        '''# Spatial v1.2 completed independent real-source audits and ephemeral
# PostgreSQL product-path verification for all five supported 2017/18 core
# leagues. Promotion remains scope-specific: no other season/competition may
# inherit these derived metrics without its own audit.
_SPATIAL_V1_2_VALIDATED_SCOPES = frozenset(
    {
        ("ENG_PL", "2017/18"),
        ("ESP_LL", "2017/18"),
        ("FRA_L1", "2017/18"),
        ("GER_BL1", "2017/18"),
        ("ITA_SA", "2017/18"),
    }
)''',
    )
    replace_once(
        adapter,
        '''    """Up to 40 player_match identities in the adapter-safe subset.
    Spatial-v1.2 metrics are emitted only for audited scopes; currently that
    is ENG_PL 2017/18. `players_payload` (the official''',
        '''    """Up to 40 player_match identities in the adapter-safe subset.
    Spatial-v1.2 metrics are emitted only for independently audited scopes;
    currently that is the five Wyscout Open core leagues in 2017/18.
    `players_payload` (the official''',
    )

    policy = "analytics/src/football_intelligence/data_mesh/comparability_policy.py"
    replace_once(
        policy,
        '`wyscout-open-v0.5` still agrees the same way -- so every entry is keyed on',
        '`wyscout-open-v0.6` still agrees the same way -- so every entry is keyed on',
    )
    replace_once(
        policy,
        '''# v0.4 was explicitly re-certified on 2026-08-25 by running v0.3 and v0.4
# over the complete real ESP_LL 2017/18 Wyscout source. All 416,407
# NormalizedObservation rows were identical field-by-field except semantic_version
# (canonical SHA-256: 29b23d96326fb82b94e6529ad951e4c1b3812d0617fff79a5d34d23bc2763eb5).
# Both ENG_PL-only spatial identities (long_passes_accurate and
# passes_into_final_third) emitted zero observations in ESP_LL, so the reviewed
# provider-pair policies remain observationally valid for v0.4 rather than being
# assumed so.
WYSCOUT_CERTIFIED_POLICY_VERSION = "wyscout-open-v0.4"''',
        '''# v0.5 was explicitly re-certified on 2026-08-25 against v0.4 over the
# complete real ESP_LL 2017/18 Wyscout source. All 416,407 previously emitted
# non-spatial NormalizedObservation facts were identical after excluding only
# semantic_version; v0.5 added exactly the two independently audited spatial
# identities (10,380 long_passes_accurate + 10,383 passes_into_final_third).
# The non-spatial canonical digest was identical on both sides:
# 7594f0bf71c6c0deffee5c0d44d8784aaa4b04edf7d1d9766801cbbdabbb5c69.
# Existing Wyscout x StatsBomb comparability policies therefore carry forward
# only for identities already reviewed under v0.4; the new spatial identities
# still have no cross-provider policy and fail closed to methodology_pending.
WYSCOUT_CERTIFIED_POLICY_VERSION = "wyscout-open-v0.5"''',
    )

    spec = "analytics/src/football_intelligence/jobs/historical_player_promotion_spec.py"
    for old, new in (
        ("source_observations=422_877,\n        score_snapshots=2_048,\n        feature_snapshots=38_737,", "source_observations=433_126,\n        score_snapshots=2_048,\n        feature_snapshots=40_513,"),
        ("source_observations=416_407,\n        score_snapshots=2_224,\n        feature_snapshots=29_008,", "source_observations=437_170,\n        score_snapshots=2_224,\n        feature_snapshots=43_881,"),
        ("source_observations=415_230,\n        score_snapshots=2_148,\n        feature_snapshots=28_007,", "source_observations=435_814,\n        score_snapshots=2_148,\n        feature_snapshots=42_300,"),
        ("source_observations=336_265,\n        score_snapshots=1_888,\n        feature_snapshots=24_786,", "source_observations=352_942,\n        score_snapshots=1_888,\n        feature_snapshots=37_413,"),
        ("source_observations=420_506,\n        score_snapshots=2_132,\n        feature_snapshots=27_872,", "source_observations=441_225,\n        score_snapshots=2_132,\n        feature_snapshots=41_996,"),
    ):
        replace_once(spec, old, new)

    old_predecessors = '''# Exact predecessor accepted for the already-promoted ENG_PL v0.2 state.
# The v0.3 runtime changed only the Data Mesh observation count and Player V2
# feature count; every other certified invariant remained identical. Keeping
# the full fingerprint here means a state that differs by even one row from
# the known v0.2 publication still fails closed.
_CERTIFIED_PREDECESSORS: dict[str, tuple[HistoricalPlayerPromotionSpec, ...]] = {
    "ENG_PL": (
        HistoricalPlayerPromotionSpec(
            competition_code="ENG_PL",
            matches=380,
            teams=20,
            players=515,
            player_appearances=10_443,
            player_match_stats=10_443,
            team_match_stats=760,
            source_observations=412_609,
            score_snapshots=2_048,
            feature_snapshots=26_841,
            season_players=512,
            season_players_450_min=385,
            performance_ready=385,
            evidence_states=(("insufficient_data", 1_754), ("partial", 294)),
        ),
    ),
}'''
    new_predecessors = '''# Explicit certified predecessor fingerprints. These are observed publication
# states, not ranges: a state that differs by even one row still fails closed.
# ENG retains both its v0.2 and v0.3 predecessors because v0.4 final-third
# promotion advanced directly from v0.3-era promotion counts. The four other
# leagues retain their exact v0.4 pre-spatial fingerprints for the v0.5 upgrade.
_CERTIFIED_PREDECESSORS: dict[str, tuple[HistoricalPlayerPromotionSpec, ...]] = {
    "ENG_PL": (
        HistoricalPlayerPromotionSpec(
            competition_code="ENG_PL", matches=380, teams=20, players=515,
            player_appearances=10_443, player_match_stats=10_443, team_match_stats=760,
            source_observations=412_609, score_snapshots=2_048, feature_snapshots=26_841,
            season_players=512, season_players_450_min=385, performance_ready=385,
            evidence_states=(("insufficient_data", 1_754), ("partial", 294)),
        ),
        HistoricalPlayerPromotionSpec(
            competition_code="ENG_PL", matches=380, teams=20, players=515,
            player_appearances=10_443, player_match_stats=10_443, team_match_stats=760,
            source_observations=422_877, score_snapshots=2_048, feature_snapshots=38_737,
            season_players=512, season_players_450_min=385, performance_ready=385,
            evidence_states=(("insufficient_data", 1_754), ("partial", 294)),
        ),
    ),
    "ESP_LL": (
        HistoricalPlayerPromotionSpec(
            competition_code="ESP_LL", matches=380, teams=20, players=557,
            player_appearances=10_555, player_match_stats=10_555, team_match_stats=760,
            source_observations=416_407, score_snapshots=2_224, feature_snapshots=29_008,
            season_players=556, season_players_450_min=415, performance_ready=415,
            evidence_states=(("insufficient_data", 1_880), ("partial", 344)),
        ),
    ),
    "FRA_L1": (
        HistoricalPlayerPromotionSpec(
            competition_code="FRA_L1", matches=380, teams=20, players=542,
            player_appearances=10_515, player_match_stats=10_515, team_match_stats=760,
            source_observations=415_230, score_snapshots=2_148, feature_snapshots=28_007,
            season_players=537, season_players_450_min=395, performance_ready=395,
            evidence_states=(("insufficient_data", 1_822), ("partial", 326)),
        ),
    ),
    "GER_BL1": (
        HistoricalPlayerPromotionSpec(
            competition_code="GER_BL1", matches=306, teams=18, players=472,
            player_appearances=8_501, player_match_stats=8_501, team_match_stats=612,
            source_observations=336_265, score_snapshots=1_888, feature_snapshots=24_786,
            season_players=472, season_players_450_min=349, performance_ready=349,
            evidence_states=(("insufficient_data", 1_596), ("partial", 292)),
        ),
    ),
    "ITA_SA": (
        HistoricalPlayerPromotionSpec(
            competition_code="ITA_SA", matches=380, teams=20, players=534,
            player_appearances=10_573, player_match_stats=10_573, team_match_stats=760,
            source_observations=420_506, score_snapshots=2_132, feature_snapshots=27_872,
            season_players=533, season_players_450_min=403, performance_ready=403,
            evidence_states=(("insufficient_data", 1_774), ("partial", 358)),
        ),
    ),
}'''
    replace_once(spec, old_predecessors, new_predecessors)

    long_test = "analytics/tests/test_wyscout_long_pass_promotion.py"
    replace_once(long_test, 'assert SEMANTIC_VERSION == "wyscout-open-v0.4"', 'assert SEMANTIC_VERSION == "wyscout-open-v0.5"')
    replace_once(
        long_test,
        '''def test_long_pass_promotion_does_not_leak_into_unaudited_league_scopes() -> None:
    esp_match = {**_MATCH, "competitionId": 795, "seasonId": 181144}
    observations = parse_player_match_observations([esp_match], _EVENTS, scope=ESP_LL_SCOPE)
    assert any(item.metric_name == "passes_total" for item in observations)
    assert all(item.metric_name != "long_passes_accurate" for item in observations)
''',
        '''def test_long_pass_emission_is_enabled_in_audited_esp_scope() -> None:
    esp_match = {**_MATCH, "competitionId": 795, "seasonId": 181144}
    observations = parse_player_match_observations([esp_match], _EVENTS, scope=ESP_LL_SCOPE)
    assert any(item.metric_name == "passes_total" for item in observations)
    assert any(item.metric_name == "long_passes_accurate" for item in observations)
''',
    )

    final_test = "analytics/tests/test_wyscout_final_third_promotion.py"
    replace_once(
        final_test,
        '''def test_final_third_emission_does_not_leak_into_unaudited_scope() -> None:
    esp_match = {**_MATCH, "competitionId": 795, "seasonId": 181144}
    observations = parse_player_match_observations([esp_match], _EVENTS, scope=ESP_LL_SCOPE)
    assert all(item.metric_name != "passes_into_final_third" for item in observations)
''',
        '''def test_final_third_emission_is_enabled_in_audited_esp_scope() -> None:
    esp_match = {**_MATCH, "competitionId": 795, "seasonId": 181144}
    observations = parse_player_match_observations([esp_match], _EVENTS, scope=ESP_LL_SCOPE)
    assert any(item.metric_name == "passes_into_final_third" for item in observations)
''',
    )

    comp_test = "analytics/tests/test_comparability_policy.py"
    replace_once(comp_test, 'assert WYSCOUT_CERTIFIED_POLICY_VERSION == "wyscout-open-v0.4"', 'assert WYSCOUT_CERTIFIED_POLICY_VERSION == "wyscout-open-v0.5"')
    text = Path(comp_test).read_text(encoding="utf-8")
    text = text.replace('semantic_version="wyscout-open-v0.4"', 'semantic_version="wyscout-open-v0.5"')
    text = text.replace('semantic_version="wyscout-open-v0.5"', 'semantic_version="wyscout-open-v0.6"', 2)
    text = text.replace('# wyscout-open-v0.4 (real, certified Wyscout side) + statsbomb-open-v0.5', '# wyscout-open-v0.5 (real, certified Wyscout side) + statsbomb-open-v0.5')
    Path(comp_test).write_text(text, encoding="utf-8")

    promo_test = "analytics/tests/test_promote_historical_player_v2.py"
    replace_once(
        promo_test,
        '''def test_england_v03_spec_and_v02_predecessor_are_exactly_pinned() -> None:
    current = historical_player_promotion_spec("ENG_PL")
    assert (
        current.matches,
        current.teams,
        current.players,
        current.player_appearances,
        current.source_observations,
        current.score_snapshots,
        current.feature_snapshots,
        current.season_players,
        current.season_players_450_min,
        current.performance_ready,
    ) == (380, 20, 515, 10_443, 422_877, 2_048, 38_737, 512, 385, 385)
    assert current.evidence_state_counts == {"insufficient_data": 1_754, "partial": 294}

    predecessors = certified_predecessor_promotion_specs("ENG_PL")
    assert len(predecessors) == 1
    predecessor = predecessors[0]
    assert (
        predecessor.matches,
        predecessor.teams,
        predecessor.players,
        predecessor.player_appearances,
        predecessor.source_observations,
        predecessor.score_snapshots,
        predecessor.feature_snapshots,
        predecessor.season_players,
        predecessor.season_players_450_min,
        predecessor.performance_ready,
    ) == (380, 20, 515, 10_443, 412_609, 2_048, 26_841, 512, 385, 385)
    assert predecessor.evidence_state_counts == current.evidence_state_counts
''',
        '''def test_england_v05_spec_and_certified_predecessors_are_exactly_pinned() -> None:
    current = historical_player_promotion_spec("ENG_PL")
    assert (
        current.matches, current.teams, current.players, current.player_appearances,
        current.source_observations, current.score_snapshots, current.feature_snapshots,
        current.season_players, current.season_players_450_min, current.performance_ready,
    ) == (380, 20, 515, 10_443, 433_126, 2_048, 40_513, 512, 385, 385)
    assert current.evidence_state_counts == {"insufficient_data": 1_754, "partial": 294}

    predecessors = certified_predecessor_promotion_specs("ENG_PL")
    assert [(item.source_observations, item.feature_snapshots) for item in predecessors] == [
        (412_609, 26_841),
        (422_877, 38_737),
    ]
    assert all(item.evidence_state_counts == current.evidence_state_counts for item in predecessors)
''',
    )
    replace_once(
        promo_test,
        '''    expected = {
        "ESP_LL": (380, 20, 557, 10_555, 416_407, 2_224, 29_008, 556, 415, 415),
        "FRA_L1": (380, 20, 542, 10_515, 415_230, 2_148, 28_007, 537, 395, 395),
        "GER_BL1": (306, 18, 472, 8_501, 336_265, 1_888, 24_786, 472, 349, 349),
        "ITA_SA": (380, 20, 534, 10_573, 420_506, 2_132, 27_872, 533, 403, 403),
    }''',
        '''    expected = {
        "ESP_LL": (380, 20, 557, 10_555, 437_170, 2_224, 43_881, 556, 415, 415),
        "FRA_L1": (380, 20, 542, 10_515, 435_814, 2_148, 42_300, 537, 395, 395),
        "GER_BL1": (306, 18, 472, 8_501, 352_942, 1_888, 37_413, 472, 349, 349),
        "ITA_SA": (380, 20, 534, 10_573, 441_225, 2_132, 41_996, 533, 403, 403),
    }''',
    )
    replace_once(
        promo_test,
        'def test_prewrite_state_accepts_only_exact_certified_england_v02_predecessor() -> None:\n    predecessor = certified_predecessor_promotion_specs("ENG_PL")[0]',
        'def test_prewrite_state_accepts_only_exact_certified_england_predecessor() -> None:\n    predecessor = certified_predecessor_promotion_specs("ENG_PL")[0]',
    )

    bridge = "docs/WYSCOUT_HISTORICAL_PLAYER_BRIDGE.md"
    replace_once(
        bridge,
        'runs the current certified Wyscout adapter (`wyscout-open-v0.4` after the spatial v1.2 final-third promotion);',
        'runs the current certified Wyscout adapter (`wyscout-open-v0.5` after Spatial v1.2 five-league promotion);',
    )

    spatial = "docs/WYSCOUT_SPATIAL_METHODOLOGY_V1.md"
    replace_once(
        spatial,
        '''Validation scope: `ENG_PL` 2017/18. England now closes the methodology gate for
`long_passes_accurate` and `passes_into_final_third`; `progressive_passes`
remains non-emitting because exact evidence is still insufficient. No result
here automatically generalizes to Spain, Italy, Germany, or France.''',
        '''Validation scope: the five Wyscout Open core domestic leagues in 2017/18
(`ENG_PL`, `ESP_LL`, `FRA_L1`, `GER_BL1`, `ITA_SA`) independently close the
methodology gate for `long_passes_accurate` and `passes_into_final_third`.
`progressive_passes` remains non-emitting because exact evidence is still
insufficient. No result here generalizes to another season or competition.''',
    )


if __name__ == "__main__":
    main()
