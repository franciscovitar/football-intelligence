from pathlib import Path


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text()
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} exact match(es), found {actual}")
    target.write_text(text.replace(old, new, count))


# Spatial methodology: v1.2 adds metric-specific exactness for final-third passes.
path = "analytics/src/football_intelligence/providers/wyscout_spatial_v1.py"
replace(
    path,
    "The rules here implement ``fi-wyscout-spatial-v1.1``.",
    "The rules here implement ``fi-wyscout-spatial-v1.2``.",
)
replace(
    path,
    'METHODOLOGY_ID = "fi-wyscout-spatial-v1.1"',
    'METHODOLOGY_ID = "fi-wyscout-spatial-v1.2"',
)
replace(
    path,
    'LongPassClassification = Literal["long", "not_long", "ambiguous"]\n',
    'LongPassClassification = Literal["long", "not_long", "ambiguous"]\n'
    'FinalThirdClassification = Literal[\n'
    '    "into_final_third", "not_into_final_third", "ambiguous"\n'
    ']\n',
)
replace(
    path,
    'def is_pass_into_final_third(start: PitchPoint, end: PitchPoint) -> bool:\n'
    '    return start.x_m < FINAL_THIRD_X_M and end.x_m >= FINAL_THIRD_X_M\n\n\n'
    'def pass_length_m',
    'def is_pass_into_final_third(start: PitchPoint, end: PitchPoint) -> bool:\n'
    '    return start.x_m < FINAL_THIRD_X_M and end.x_m >= FINAL_THIRD_X_M\n\n\n'
    'def classify_pass_into_final_third(\n'
    '    coordinates: CoordinateParseResult,\n'
    ') -> FinalThirdClassification:\n'
    '    """Classify only when source evidence makes final-third entry exact.\n\n'
    '    Wyscout defines the metric as a pass that originates outside the final\n'
    '    third and whose next touch occurs inside it. Therefore a pass already\n'
    '    starting inside the final third is an exact negative even when its\n'
    '    endpoint is unavailable. Missing endpoints for starts outside the final\n'
    '    third remain ambiguous; no endpoint is reconstructed or imputed.\n'
    '    """\n\n'
    '    start = coordinates.start\n'
    '    if start is None:\n'
    '        return "ambiguous"\n'
    '    if start.x_m >= FINAL_THIRD_X_M:\n'
    '        return "not_into_final_third"\n'
    '    if not coordinates.valid or coordinates.end is None:\n'
    '        return "ambiguous"\n'
    '    return (\n'
    '        "into_final_third"\n'
    '        if is_pass_into_final_third(start, coordinates.end)\n'
    '        else "not_into_final_third"\n'
    '    )\n\n\n'
    'def pass_length_m',
)

# Mapping: promote only passes_into_final_third; progressive stays blocked.
path = "analytics/src/football_intelligence/providers/wyscout_open_mapping.py"
replace(
    path,
    '    _mapping(\n'
    '        "passes_into_final_third",\n'
    '        "player_match",\n'
    '        "DERIVABLE",\n'
    '        "eventName=Pass, spatial rule over positions[0]/positions[1]",\n'
    '        "Methodology pending -- see \'Spatial metrics\'.",\n'
    '        methodology_pending=True,\n'
    '    ),',
    '    _mapping(\n'
    '        "passes_into_final_third",\n'
    '        "player_match",\n'
    '        "DERIVABLE",\n'
    '        "fi-wyscout-spatial-v1.2 final-third exact classification",\n'
    '        "Promoted after the real ENG_PL 2017/18 audit. Valid geometry uses "\n'
    '        "the observed start/end boundary rule; an unavailable endpoint is an "\n'
    '        "exact non-qualifier only when the observed start is already inside "\n'
    '        "the final third. Starts outside with unavailable endpoint stay missing.",\n'
    '        caveats=(\n'
    '            "Promotion is deliberately metric- and scope-specific: only ENG_PL "\n'
    '            "2017/18 is audited for emission. No endpoint reconstruction, "\n'
    '            "missing-to-zero coercion, or progressive-pass activation is implied."\n'
    '        ),\n'
    '    ),',
)
replace(
    path,
    '            "suppressed until their own audit passes. progressive_passes and "\n'
    '            "passes_into_final_third remain methodology/audit blocked and are not emitted."\n',
    '            "suppressed until their own audit passes. progressive_passes remains "\n'
    '            "methodology/audit blocked and is not emitted."\n',
)

# Adapter: v0.4 emits exact final-third counts only in the audited ENG scope.
path = "analytics/src/football_intelligence/data_mesh/adapters/wyscout_open.py"
replace(path, "the 78-identity adapter-safe subset", "the 79-identity adapter-safe subset")
replace(path, "the 43 DIRECT + 35 DERIVABLE_READY", "the 43 DIRECT + 36 DERIVABLE_READY")
replace(
    path,
    'from football_intelligence.providers.wyscout_spatial_v1 import (\n'
    '    classify_long_pass,\n'
    '    is_accurate,\n'
    '    parse_pass_coordinates,\n'
    ')',
    'from football_intelligence.providers.wyscout_spatial_v1 import (\n'
    '    classify_long_pass,\n'
    '    classify_pass_into_final_third,\n'
    '    is_accurate,\n'
    '    parse_pass_coordinates,\n'
    ')',
)
replace(
    path,
    'SEMANTIC_VERSION = "wyscout-open-v0.3"',
    'SEMANTIC_VERSION = "wyscout-open-v0.4"',
)
replace(
    path,
    '# Spatial v1.1 has completed its real-source promotion audit only for\n'
    '# England 2017/18. Other otherwise-certified Wyscout league scopes must\n'
    '# keep this metric absent until their own audit closes the same gate.\n'
    '_SPATIAL_V1_1_VALIDATED_SCOPES = frozenset({("ENG_PL", "2017/18")})',
    '# Spatial v1.2 has completed its real-source promotion audit only for\n'
    '# England 2017/18. Other otherwise-certified Wyscout league scopes must\n'
    '# keep spatial-v1.2 metrics absent until their own audit closes the same gate.\n'
    '_SPATIAL_V1_2_VALIDATED_SCOPES = frozenset({("ENG_PL", "2017/18")})',
)
replace(
    path,
    '        ("pass_completion_pct", "player_match"),\n'
    '        ("long_passes_accurate", "player_match"),',
    '        ("pass_completion_pct", "player_match"),\n'
    '        ("long_passes_accurate", "player_match"),\n'
    '        ("passes_into_final_third", "player_match"),',
)
replace(
    path,
    '    return accurate_long, frozenset(ambiguous)\n\n\n'
    'def _observation(',
    '    return accurate_long, frozenset(ambiguous)\n\n\n'
    'def _accumulate_passes_into_final_third(\n'
    '    events_payload: list[Any],\n'
    ') -> tuple[dict[tuple[int, int], int], frozenset[tuple[int, int]]]:\n'
    '    """Return exact final-third counts plus unknown player-matches.\n\n'
    '    An observed start already inside the final third is an exact negative\n'
    '    even when the endpoint is unavailable. Missing endpoints for starts\n'
    '    outside the final third remain ambiguous for only this metric.\n'
    '    """\n\n'
    '    counts: dict[tuple[int, int], int] = defaultdict(int)\n'
    '    ambiguous: set[tuple[int, int]] = set()\n'
    '    for event in events_payload:\n'
    '        if not isinstance(event, dict) or event.get("eventName") != "Pass":\n'
    '            continue\n'
    '        match_id = event.get("matchId")\n'
    '        player_id = event.get("playerId")\n'
    '        if (\n'
    '            not isinstance(match_id, int)\n'
    '            or not isinstance(player_id, int)\n'
    '            or player_id == _SENTINEL_PLAYER_ID\n'
    '        ):\n'
    '            continue\n'
    '        pair = (match_id, player_id)\n'
    '        classification = classify_pass_into_final_third(\n'
    '            parse_pass_coordinates(event)\n'
    '        )\n'
    '        if classification == "ambiguous":\n'
    '            ambiguous.add(pair)\n'
    '        elif classification == "into_final_third":\n'
    '            counts[pair] += 1\n'
    '    return counts, frozenset(ambiguous)\n\n\n'
    'def _observation(',
)
replace(
    path,
    '    counts: _ZeroDict,\n'
    '    long_passes_accurate: int | None,\n'
    '    observed_at: datetime,',
    '    counts: _ZeroDict,\n'
    '    long_passes_accurate: int | None,\n'
    '    passes_into_final_third: int | None,\n'
    '    observed_at: datetime,',
)
replace(
    path,
    '    if long_passes_accurate is not None:\n'
    '        emit("long_passes_accurate", long_passes_accurate)\n',
    '    if long_passes_accurate is not None:\n'
    '        emit("long_passes_accurate", long_passes_accurate)\n'
    '    if passes_into_final_third is not None:\n'
    '        emit("passes_into_final_third", passes_into_final_third)\n',
)
replace(
    path,
    '    """Up to 39 player_match identities in the adapter-safe subset.\n'
    '    `long_passes_accurate` is emitted only for spatial-v1.1-audited scopes;\n'
    '    currently that is ENG_PL 2017/18. `players_payload` (the official\n',
    '    """Up to 40 player_match identities in the adapter-safe subset.\n'
    '    Spatial-v1.2 metrics are emitted only for audited scopes; currently that\n'
    '    is ENG_PL 2017/18. `players_payload` (the official\n',
)
replace(
    path,
    '    spatial_v1_1_enabled = (\n'
    '        scope.canonical_competition_code,\n'
    '        scope.season_label,\n'
    '    ) in _SPATIAL_V1_1_VALIDATED_SCOPES\n'
    '    if spatial_v1_1_enabled:\n'
    '        accurate_long, ambiguous_long = _accumulate_long_pass_accurate(events_payload)\n'
    '    else:\n'
    '        accurate_long, ambiguous_long = {}, frozenset()\n',
    '    spatial_v1_2_enabled = (\n'
    '        scope.canonical_competition_code,\n'
    '        scope.season_label,\n'
    '    ) in _SPATIAL_V1_2_VALIDATED_SCOPES\n'
    '    if spatial_v1_2_enabled:\n'
    '        accurate_long, ambiguous_long = _accumulate_long_pass_accurate(events_payload)\n'
    '        final_third, ambiguous_final_third = _accumulate_passes_into_final_third(\n'
    '            events_payload\n'
    '        )\n'
    '    else:\n'
    '        accurate_long, ambiguous_long = {}, frozenset()\n'
    '        final_third, ambiguous_final_third = {}, frozenset()\n',
)
replace(
    path,
    '            long_passes_accurate = (\n'
    '                None\n'
    '                if not spatial_v1_1_enabled or pair in ambiguous_long\n'
    '                else accurate_long.get(pair, 0)\n'
    '            )\n'
    '            hints = _player_scoped_hints(info, roster, player_id, player_names, scope)\n',
    '            long_passes_accurate = (\n'
    '                None\n'
    '                if not spatial_v1_2_enabled or pair in ambiguous_long\n'
    '                else accurate_long.get(pair, 0)\n'
    '            )\n'
    '            passes_into_final_third = (\n'
    '                None\n'
    '                if not spatial_v1_2_enabled or pair in ambiguous_final_third\n'
    '                else final_third.get(pair, 0)\n'
    '            )\n'
    '            hints = _player_scoped_hints(info, roster, player_id, player_names, scope)\n',
)
replace(
    path,
    '                counts=counts,\n'
    '                long_passes_accurate=long_passes_accurate,\n'
    '                observed_at=observed_at,',
    '                counts=counts,\n'
    '                long_passes_accurate=long_passes_accurate,\n'
    '                passes_into_final_third=passes_into_final_third,\n'
    '                observed_at=observed_at,',
)

# Canonical bridge and DB read/write path.
path = "analytics/src/football_intelligence/normalization/models.py"
replace(
    path,
    '    aerial_duels: int | None = None\n'
    '    aerial_duels_won: int | None = None\n'
    '    long_passes_accurate: int | None = None\n',
    '    aerial_duels: int | None = None\n'
    '    aerial_duels_won: int | None = None\n'
    '    long_passes_accurate: int | None = None\n'
    '    passes_into_final_third: int | None = None\n',
)

path = "analytics/src/football_intelligence/normalization/wyscout_historical.py"
replace(
    path,
    '    "passes_accurate",\n'
    '    "long_passes_accurate",\n'
    '    "key_passes",',
    '    "passes_accurate",\n'
    '    "long_passes_accurate",\n'
    '    "passes_into_final_third",\n'
    '    "key_passes",',
)
replace(
    path,
    '        passes_accurate=values["passes_accurate"],\n'
    '        long_passes_accurate=values["long_passes_accurate"],\n'
    '        key_passes=values["key_passes"],',
    '        passes_accurate=values["passes_accurate"],\n'
    '        long_passes_accurate=values["long_passes_accurate"],\n'
    '        passes_into_final_third=values["passes_into_final_third"],\n'
    '        key_passes=values["key_passes"],',
)

path = "analytics/src/football_intelligence/db/provider_repository.py"
replace(
    path,
    '                duels_total, duels_won, aerial_duels, aerial_duels_won,\n'
    '                long_passes_accurate, fouls_drawn, fouls_committed, yellow_cards, red_cards, saves\n',
    '                duels_total, duels_won, aerial_duels, aerial_duels_won,\n'
    '                long_passes_accurate, passes_into_final_third, fouls_drawn,\n'
    '                fouls_committed, yellow_cards, red_cards, saves\n',
)
replace(
    path,
    '                %(aerial_duels)s, %(aerial_duels_won)s, %(long_passes_accurate)s,\n'
    '                %(fouls_drawn)s, %(fouls_committed)s, %(yellow_cards)s, %(red_cards)s, %(saves)s\n',
    '                %(aerial_duels)s, %(aerial_duels_won)s, %(long_passes_accurate)s,\n'
    '                %(passes_into_final_third)s, %(fouls_drawn)s, %(fouls_committed)s,\n'
    '                %(yellow_cards)s, %(red_cards)s, %(saves)s\n',
)
replace(
    path,
    '                long_passes_accurate = excluded.long_passes_accurate,\n'
    '                fouls_drawn = excluded.fouls_drawn,',
    '                long_passes_accurate = excluded.long_passes_accurate,\n'
    '                passes_into_final_third = excluded.passes_into_final_third,\n'
    '                fouls_drawn = excluded.fouls_drawn,',
)

path = "analytics/src/football_intelligence/db/player_analytics_repository.py"
replace(
    path,
    '    "passes_accurate",\n'
    '    "long_passes_accurate",\n'
    '    "key_passes",',
    '    "passes_accurate",\n'
    '    "long_passes_accurate",\n'
    '    "passes_into_final_third",\n'
    '    "key_passes",',
)
replace(
    path,
    '                pms.passes_accurate,\n'
    '                pms.long_passes_accurate,\n'
    '                pms.key_passes,',
    '                pms.passes_accurate,\n'
    '                pms.long_passes_accurate,\n'
    '                pms.passes_into_final_third,\n'
    '                pms.key_passes,',
)

# Existing long-pass promotion assertions reflect the new safe identity/version.
path = "analytics/tests/test_wyscout_long_pass_promotion.py"
replace(
    path,
    '    assert ("passes_into_final_third", "player_match") not in safe\n'
    '    assert ("long_passes_accurate", "player_match") in _EMITTED_IDENTITIES\n'
    '    assert SEMANTIC_VERSION == "wyscout-open-v0.3"\n',
    '    assert ("passes_into_final_third", "player_match") in safe\n'
    '    assert ("long_passes_accurate", "player_match") in _EMITTED_IDENTITIES\n'
    '    assert ("passes_into_final_third", "player_match") in _EMITTED_IDENTITIES\n'
    '    assert SEMANTIC_VERSION == "wyscout-open-v0.4"\n',
)

# Remove temporary mechanism from the product diff before committing.
Path(".github/workflows/tmp-final-third-implementation.yml").unlink()
Path(".github/tmp_apply_final_third_patch.py").unlink()
