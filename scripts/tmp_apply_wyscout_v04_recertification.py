from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement, found {count}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_exact_count(path: str, old: str, new: str, expected: int) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(f"{path}: expected {expected} replacements, found {count}")
    file.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    policy = "analytics/src/football_intelligence/data_mesh/comparability_policy.py"
    replace_once(
        policy,
        "`wyscout-open-v0.4` still agrees the same way",
        "`wyscout-open-v0.5` still agrees the same way",
    )
    replace_once(
        policy,
        '''# v0.3 was explicitly re-certified on 2026-08-25 by running v0.2 and v0.3
# over the complete real ESP_LL 2017/18 Wyscout source. All 416,407
# NormalizedObservation rows were identical field-by-field except semantic_version
# (canonical SHA-256: 29b23d96326fb82b94e6529ad951e4c1b3812d0617fff79a5d34d23bc2763eb5).
# The new long_passes_accurate identity is scope-gated to ENG_PL and emitted zero
# observations in ESP_LL, so the reviewed provider-pair policies remain
# observationally valid for v0.3 rather than being assumed so.
WYSCOUT_CERTIFIED_POLICY_VERSION = "wyscout-open-v0.3"''',
        '''# v0.4 was explicitly re-certified on 2026-08-25 by running v0.3 and v0.4
# over the complete real ESP_LL 2017/18 Wyscout source. All 416,407
# NormalizedObservation rows were identical field-by-field except semantic_version
# (canonical SHA-256: 29b23d96326fb82b94e6529ad951e4c1b3812d0617fff79a5d34d23bc2763eb5).
# Both ENG_PL-only spatial identities (long_passes_accurate and
# passes_into_final_third) emitted zero observations in ESP_LL, so the reviewed
# provider-pair policies remain observationally valid for v0.4 rather than being
# assumed so.
WYSCOUT_CERTIFIED_POLICY_VERSION = "wyscout-open-v0.4"''',
    )

    adapter_test = "analytics/tests/test_data_mesh_adapters_wyscout_open.py"
    replace_once(
        adapter_test,
        '''def test_semantic_version_tracks_current_certified_adapter_semantics() -> None:
    # v0.2 introduced Block 20D.2's review fixes. v0.3 adds the independently
    # audited ENG_PL-only long_passes_accurate emission and was explicitly
    # re-certified as observationally equivalent to v0.2 in ESP_LL 2017/18,
    # the Wyscout x StatsBomb comparability-policy scope.
    assert wyscout_open.SEMANTIC_VERSION != "wyscout-open-v0.1"
    assert wyscout_open.SEMANTIC_VERSION != "wyscout-open-v0.2"
    assert wyscout_open.SEMANTIC_VERSION == "wyscout-open-v0.3"
''',
        '''def test_semantic_version_tracks_current_certified_adapter_semantics() -> None:
    # v0.3 promoted ENG_PL-only long_passes_accurate. v0.4 additionally promotes
    # ENG_PL-only passes_into_final_third under spatial v1.2 and was explicitly
    # re-certified as observationally equivalent to v0.3 in ESP_LL 2017/18,
    # the Wyscout x StatsBomb comparability-policy scope.
    assert wyscout_open.SEMANTIC_VERSION != "wyscout-open-v0.1"
    assert wyscout_open.SEMANTIC_VERSION != "wyscout-open-v0.2"
    assert wyscout_open.SEMANTIC_VERSION != "wyscout-open-v0.3"
    assert wyscout_open.SEMANTIC_VERSION == "wyscout-open-v0.4"
''',
    )

    mapping_test = "analytics/tests/test_wyscout_open_mapping.py"
    replace_once(
        mapping_test,
        '''def test_derivable_ready_and_pending_totals_match_final_accounting() -> None:
    assert len(derivable_ready_mappings()) == 35
    assert len(derivable_methodology_pending_mappings()) == 32
''',
        '''def test_derivable_ready_and_pending_totals_match_final_accounting() -> None:
    assert len(derivable_ready_mappings()) == 36
    assert len(derivable_methodology_pending_mappings()) == 31
''',
    )
    replace_once(
        mapping_test,
        '''def test_adapter_safe_subset_totals_78() -> None:
    safe = adapter_safe_mappings()
    assert len(safe) == 78
''',
        '''def test_adapter_safe_subset_totals_79() -> None:
    safe = adapter_safe_mappings()
    assert len(safe) == 79
''',
    )

    comp_test = "analytics/tests/test_comparability_policy.py"
    replace_once(
        comp_test,
        '_CERTIFIED_WYSCOUT_VERSION = "wyscout-open-v0.3"',
        '_CERTIFIED_WYSCOUT_VERSION = "wyscout-open-v0.4"',
    )
    replace_once(
        comp_test,
        "# wyscout-open-v0.3 + statsbomb-open-v0.4 -> current policies match.",
        "# wyscout-open-v0.4 + statsbomb-open-v0.4 -> current policies match.",
    )
    replace_once(
        comp_test,
        '''    # wyscout-open-v0.4 + statsbomb-open-v0.4 (real, certified StatsBomb
    # side, only Wyscout bumped) -> no old policy match, methodology_pending
''',
        '''    # wyscout-open-v0.5 + statsbomb-open-v0.4 (real, certified StatsBomb
    # side, only Wyscout bumped) -> no old policy match, methodology_pending
''',
    )
    replace_once(
        comp_test,
        '''    # wyscout-open-v0.3 (real, certified Wyscout side) + statsbomb-open-v0.5
''',
        '''    # wyscout-open-v0.4 (real, certified Wyscout side) + statsbomb-open-v0.5
''',
    )
    replace_once(
        comp_test,
        '''    # wyscout-open-v0.4 + statsbomb-open-v0.5 -> no old policy match.
''',
        '''    # wyscout-open-v0.5 + statsbomb-open-v0.5 -> no old policy match.
''',
    )
    replace_exact_count(
        comp_test,
        'semantic_version="wyscout-open-v0.4"',
        'semantic_version="wyscout-open-v0.5"',
        2,
    )

    spatial = "docs/WYSCOUT_SPATIAL_METHODOLOGY_V1.md"
    replace_once(
        spatial,
        "Status: **v1.1 validated on ENG_PL 2017/18; `long_passes_accurate` promoted only**",
        "Status: **v1.2 validated on ENG_PL 2017/18; `long_passes_accurate` and `passes_into_final_third` promoted**",
    )
    replace_once(
        spatial,
        "Current methodology id: `fi-wyscout-spatial-v1.1`",
        "Current methodology id: `fi-wyscout-spatial-v1.2`",
    )
    replace_once(
        spatial,
        '''Validation scope: `ENG_PL` 2017/18. The England audit closes the methodology
gate only for `long_passes_accurate`; `progressive_passes` and
`passes_into_final_third` remain non-emitting because their exact season-level
coverage is not yet sufficient. No result here automatically generalizes to
Spain, Italy, Germany, or France.
''',
        '''Validation scope: `ENG_PL` 2017/18. England now closes the methodology gate for
`long_passes_accurate` and `passes_into_final_third`; `progressive_passes`
remains non-emitting because exact evidence is still insufficient. No result
here automatically generalizes to Spain, Italy, Germany, or France.
''',
    )
    replace_once(
        spatial,
        '''`v1.1` refines the unpromoted `v1.0` specification after the first real England
audit. The audit showed that treating every non-Cross historical pass subtype as
a potential long-ground pass was too broad. `Hand pass` and `Head pass` are now
explicitly non-long for this methodology, while `Simple pass` and `Smart pass`
are the only historical subtypes allowed to become Long Ground from geometry.
No production observation was emitted under `v1.0`.
''',
        '''`v1.1` refined the unpromoted `v1.0` long-pass taxonomy after the first real
England audit. `v1.2` keeps those long-pass rules unchanged and promotes
`passes_into_final_third` after a second England exactness audit established a
safe asymmetric rule for missing endpoints: a pass that already starts inside
the attacking final third is an exact negative even when its endpoint is the
historical `(0,0)` sentinel; a pass starting outside the final third with an
unavailable endpoint remains ambiguous and therefore missing. No endpoint is
imputed. No production observation was emitted under `v1.0`.
''',
    )
    replace_exact_count(spatial, "`fi-wyscout-spatial-v1.1`", "`fi-wyscout-spatial-v1.2`", 2)
    replace_once(
        spatial,
        '''If required geometry is unavailable, the player-match value is missing. The
methodology does not infer an endpoint from the semantic label `Cross`.

**Production state:** not emitted. Its audit coverage is the same as
`progressive_passes`: 87.81% exact player-match, 32.6214% exact player-season.
''',
        '''If the pass starts inside the final third, it is an exact negative even when the
endpoint is unavailable because it cannot satisfy the required outside-to-inside
transition. If the pass starts outside the final third and its endpoint is
unavailable, the player-match value is missing. The methodology does not infer
an endpoint from the semantic label `Cross` or any other subtype.

**Production state:** promoted for ENG_PL 2017/18 only. The post-fix real runtime
observed exact player-match values for 10,249 of 10,443 participant rows
(98.1423%): 8,629 positive and 1,620 confirmed zero, with 194 rows remaining
missing. Strict all-contributing-match propagation produced an exact season
feature for 377 of 512 Player V2 season players (73.6328%); 135 stayed missing.
Among the 385 players meeting the season percentile-minutes gate, 255 had an
exact final-third percentile input. No endpoint imputation or partial-window sum
is published as complete.
''',
    )
    replace_once(
        spatial,
        '''For `long_passes_accurate`, an aggregated Player V2 window is exact only when
the metric is observed in every contributing player-match. If any contributing
match is missing, the aggregate metric stays missing for that window rather
than summing the known matches into a partial value that looks complete.
''',
        '''For `long_passes_accurate` and `passes_into_final_third`, an aggregated Player
V2 window is exact only when the metric is observed in every contributing
player-match. If any contributing match is missing, the aggregate metric stays
missing for that window rather than summing known matches into a partial value
that looks complete.
''',
    )
    replace_once(
        spatial,
        "- `passes_into_final_third`;\n",
        "",
    )
    replace_once(
        spatial,
        "A metric under `fi-wyscout-spatial-v1.1` is promotable only after the ENG_PL",
        "A metric under `fi-wyscout-spatial-v1.2` is promotable only after the ENG_PL",
    )
    replace_once(
        spatial,
        '''Promotion decision:

| Metric | exact player-season readiness | decision |
| --- | ---: | --- |
| `long_passes_accurate` | 74.5631% | **PROMOTE** |
| `progressive_passes` | 32.6214% | **BLOCK** |
| `passes_into_final_third` | 32.6214% | **BLOCK** |

Player V2's Passing definition and evidence gate are unchanged. Promoting
`long_passes_accurate` adds one objectively supported input; it does not lower
the 60% minimum dimension evidence threshold, remove the core
`pass_completion_pct` requirement, or force a Passing score when other required
spatial evidence is still missing.
''',
        '''Promotion decision after v1.2 production-path verification:

| Metric | exact season evidence | decision |
| --- | ---: | --- |
| `long_passes_accurate` | 384 / 512 Player V2 season features | **PROMOTED (v1.1)** |
| `passes_into_final_third` | 377 / 512 Player V2 season features | **PROMOTE (v1.2)** |
| `progressive_passes` | 32.6214% exact player-season readiness in the spatial audit | **BLOCK** |

The post-fix Player V2 runtime produced 231 `passing=partial`, 281
`passing=insufficient_data`, and **0 `passing=ready`** season rows. This is the
intended result: Player V2's Passing definition and evidence gates are unchanged.
The new metric improves supported evidence without lowering the 60% minimum
dimension evidence threshold, removing the core `pass_completion_pct`
requirement, or forcing a Passing score while `progressive_passes` is still
missing. The complete v0.4 runtime was idempotent across two Player V2 runs.
''',
    )

    bridge = "docs/WYSCOUT_HISTORICAL_PLAYER_BRIDGE.md"
    replace_once(
        bridge,
        '''The counts below are the observed `wyscout-open-v0.2` baseline from that
runtime. The later v0.3 long-pass promotion deliberately requires a fresh
post-promotion runtime before replacing these historical counts.
''',
        '''The first block below preserves the observed `wyscout-open-v0.2` baseline for
historical traceability. A later 2026-08-25 post-promotion runtime separately
verified the current v0.4 adapter and Player V2 path; those current counts are
recorded immediately after the baseline rather than rewriting history.
''',
    )
    replace_once(
        bridge,
        '''Full-load idempotency was then verified by executing the same loader a second time against the same temporary database. All scoped counts remained identical, `football.teams` remained at 20 rows, Wyscout team-provider mappings remained at 20, and all 20 teams were recognized as already linked. Runtime evidence: GitHub Actions run `32596409687`.
''',
        '''Full-load idempotency was then verified by executing the same loader a second time against the same temporary database. All scoped counts remained identical, `football.teams` remained at 20 rows, Wyscout team-provider mappings remained at 20, and all 20 teams were recognized as already linked. Runtime evidence: GitHub Actions run `32596409687`.

Current v0.4 post-promotion verification (2026-08-25, ephemeral PostgreSQL 17):

- historical load: 380 matches, 20 teams, 515 participating players — PASS;
- 10,443 `player_appearances` and 10,443 `player_match_stats` rows;
- 433,126 Data Mesh `source_observations`;
- `long_passes_accurate`: 10,268 known player-match rows, 175 missing;
- `passes_into_final_third`: 10,249 known player-match rows, 194 missing;
- exact Player V2 season features: 384 `long_passes_accurate`, 377 `passes_into_final_third`;
- Passing dimension: 231 partial, 281 insufficient-data, 0 ready/scored;
- `progressive_passes` remained absent;
- repeated Player V2 calculation produced byte-identical reports — PASS.

A separate ESP_LL 2017/18 recertification compared `wyscout-open-v0.3` and
`wyscout-open-v0.4` over all 416,407 observations and found every field identical
except `semantic_version`; both ENG-only spatial metrics emitted zero observations
in Spain. Canonical payload SHA-256 remained
`29b23d96326fb82b94e6529ad951e4c1b3812d0617fff79a5d34d23bc2763eb5`.
''',
    )
    replace_once(
        bridge,
        "3. runs the current certified Wyscout adapter (`wyscout-open-v0.3` after the spatial v1.1 promotion);",
        "3. runs the current certified Wyscout adapter (`wyscout-open-v0.4` after the spatial v1.2 final-third promotion);",
    )

    recert = Path("docs/WYSCOUT_V04_RECERTIFICATION.md")
    if recert.exists():
        raise SystemExit(f"{recert}: already exists")
    recert.write_text(
        '''# Wyscout v0.4 recertification\n\nStatus: **PASS — ESP_LL 2017/18 observational equivalence certified**\n\nOn 2026-08-25 Football Intelligence re-ran the complete Wyscout Open ESP_LL\n2017/18 adapter output under the previously certified `wyscout-open-v0.3` and\nthe candidate `wyscout-open-v0.4`. The official Wyscout Figshare source was\nre-acquired and its five core European league files passed the repository's\nsource audit before comparison.\n\n## Result\n\n- baseline: `wyscout-open-v0.3`;\n- candidate: `wyscout-open-v0.4`;\n- scope: `ESP_LL` 2017/18;\n- observations per version: **416,407**;\n- comparison rule: every `NormalizedObservation` field must be identical except\n  `semantic_version`;\n- result: **all 416,407 canonical rows identical**;\n- candidate `long_passes_accurate` observations in ESP_LL: **0**;\n- candidate `passes_into_final_third` observations in ESP_LL: **0**;\n- canonical payload SHA-256:\n  `29b23d96326fb82b94e6529ad951e4c1b3812d0617fff79a5d34d23bc2763eb5`.\n\nThis is evidence that v0.4's new final-third emission is correctly scope-gated\nto the separately audited ENG_PL 2017/18 path. It does **not** infer that the\nmetric is valid for Spain, Italy, Germany or France.\n\n## Comparability consequence\n\nThe existing Wyscout Open x StatsBomb Open ESP_LL provider-pair policies were\nreviewed against v0.3. Because v0.4 is now proven observationally equivalent in\nthat exact comparability scope, the Wyscout certified policy pin may move from\n`wyscout-open-v0.3` to `wyscout-open-v0.4` without silently inheriting an\nuntested semantic version. Any future Wyscout semantic bump must fail closed\nagain until separately re-certified.\n''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
