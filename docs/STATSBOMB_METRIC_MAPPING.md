# StatsBomb Open Data — Empirical Metric Catalog V2 Mapping (Block 20C.2a)

This document records the empirical evidence behind
`analytics/src/football_intelligence/providers/statsbomb_open_mapping.py`
and the reproducible, pinned local source layer
(`providers/statsbomb_open.py`, `providers/statsbomb_open_cache.py`,
`providers/statsbomb_open_manifest.py`, `jobs/fetch_statsbomb_open.py`).
It applies the same rigor already established for Wyscout Open Data
(`docs/WYSCOUT_METRIC_MAPPING.md`) retroactively to StatsBomb, whose original
adapter (Block 14) pre-dates the Block 20 methodology and was audited, not
assumed correct, in `docs/BLOCK20_MULTI_SOURCE.md`'s Block 20C.1 diagnosis.

No `NormalizedObservation` adapter changes happen in this block. This is
acquisition + empirical mapping only; Block 20C.2b will build the adapter
using exactly the `adapter_safe_mappings()` subset defined here.

## 1. Pinned, reproducible source

| Field | Value |
| --- | --- |
| Provider | StatsBomb Open Data (`https://github.com/statsbomb/open-data`) |
| Role | `historical_deep` — never current |
| Pinned commit SHA | `b0bc9f22dd77c206ddedc1d742893b3bbe64baec` (`DEFAULT_PINNED_REVISION`) |
| Effective raw base URL | `https://raw.githubusercontent.com/statsbomb/open-data/<ref>/data` |
| Exposure policy | **`internal_only`** (`providers/statsbomb_open_policy.py`) |

`StatsBombOpenDataClient` defaults to the pinned SHA, never `master` — the
upstream repository is a live, mutable branch (its HEAD moved substantially,
adding/updating thousands of match files, between the Block 20C.1 audit and
this block). Callers may pass an explicit `ref` for tests or a deliberate
future revision upgrade; nothing in the client silently falls back to
`master` when a pinned ref fails.

### Local cache

`analytics/data/cache/statsbomb-open/<pinned_sha>/` (git-ignored, mirrors the
existing `data/cache/` convention). Every cached file has a `.sha256`
sidecar recording the SHA-256 of the exact bytes downloaded — **local
reproducibility/integrity metadata only**, never presented as a
provider-authenticated checksum (StatsBomb/GitHub does not expose one, unlike
Wyscout's Figshare `computed_md5`). A hash mismatch on reuse raises
`StatsBombCacheCorruptionError` immediately — no silent re-fetch, no silent
reuse of altered bytes.

A `manifest.json` at the cache root records: provider, upstream repository,
pinned commit SHA, competition/season identity, role, exposure policy, fetch
timestamp, expected match count, and every cached file's path/SHA-256/size.

### Full local snapshot fetched for this block

`football-intelligence-fetch-statsbomb-open` was run against the pinned
revision and cached the complete season: `competitions.json`,
`matches/2/27.json`, and every one of the 380 matches' `events/{id}.json` +
`lineups/{id}.json` (three-sixty deliberately **not** cached — Block 20C.1
verified none exist for this scope). Result: **762 files, ~1.14 GB**,
all SHA-256 hash-verified.

## 2. Scope

**Premier League 2015/16** (`competition_id=2`, `season_id=27`) — confirmed
in Block 20C.1 and re-confirmed here against the full pinned cache: **380
matches, 20 teams, weeks 1–38, a genuinely full league season** (20 × 19 × 2
= 380). No StatsBomb 360 coverage for this scope.

## 3. Compliance state (Block 20C.1 finding, unchanged — no legal conclusion made here)

StatsBomb's User Agreement is materially stricter than Wyscout's CC BY 4.0:

- **Attribution**: any published analysis must carry the StatsBomb brand
  logo, not just a text citation.
- **Redistribution**: raw data may not be distributed/reproduced/provided to
  any third party; all data remains StatsBomb's property.
- **Commercial-use ambiguity**: the Agreement prohibits commercially
  exploiting "the data or any analysis derived from the use of the Service"
  without defining "commercially exploit" — whether this covers Football
  Intelligence surfacing StatsBomb-derived intelligence to end users is
  **unresolved by the document itself** and requires an explicit
  product/legal decision, not a code-level assumption.

`providers/statsbomb_open_policy.py` makes this structural:
`STATSBOMB_INTERNAL_ONLY = True` and `assert_internal_only_evidence()` exist
purely to prevent a future code path from accidentally wiring StatsBomb data
into a user-facing surface before that decision is made.

## 4. Real schema findings re-confirmed / extended this block

All Block 20C.1 event-schema findings (Shot/Pass/Duel/Interception/Block/
Dribble/Carry/Ball Recovery/Pressure/Foul Committed/Foul Won/Goal Keeper/
Substitution/Starting XI/Tactical Shift/Own Goal For/Against) stand. This
block additionally resolved four semantic questions Block 20C.1 explicitly
left open, against the **full 380-match season**, not a 3-match sample:

### Cards — lineup file is authoritative, not Foul Committed alone

| Source | Yellow | Red | Second Yellow |
| --- | --- | --- | --- |
| `lineups[*].lineup[*].cards` (authoritative) | 1203 | 34 | 25 |
| `Foul Committed` events only (old adapter) | 1015 | 29 | 25 |
| `Bad Behaviour` events only | 188 | 5 | — |

**187 of 1234 real carded (match, player) incidents (15%) are issued via
`Bad Behaviour` events the old adapter never reads** — verified to be
exactly the gap between `Foul Committed`-only and the full lineup-carded
set (0 lineup-carded entries are absent from either event source; the
187-entry `Bad Behaviour`-only gap fully explains it). The lineup file's
`cards` array is the exact union of both event pathways and is simpler and
complete. **Decision: Block 20C.2b must source cards from the lineup file,
never from `Foul Committed` alone.**

### Saves / goals_conceded / shots_on_target_faced — resolved with exact full-season arithmetic

| Check | Value |
| --- | --- |
| Shot events with outcome in {Saved, Saved Off Target, Saved to Post} | 2277 |
| Goal Keeper events with type in {Shot Saved, Shot Saved Off Target, Shot Saved to Post, Penalty Saved, Penalty Saved to Post} | **2277** (exact match) |
| Shot events with outcome == Goal | 988 |
| Goal Keeper events with type in {Goal Conceded, Penalty Conceded} | **988** (exact match: 914 + 74) |
| shots_on_target (988 + 2277) | 3265 |
| saves + goals_conceded (2277 + 988) | **3265** (exact match) |

Three independent full-season arithmetic identities all close exactly. The
old adapter's `_SAVE_GOALKEEPER_TYPE = "Shot Saved"` only counts 2194/2277
real saves (**3.6% undercount** — misses `Shot Saved Off Target` (45),
`Shot Saved to Post` (27), `Penalty Saved` (10), `Penalty Saved to Post` (1)).
`goals_conceded` is directly player-attributed on the Goal Keeper event
itself — no scoreline/substitution-window cross-referencing needed, simpler
than both Wyscout's equivalent and the old StatsBomb adapter's approach.

### Assists — `pass.goal_assist` is DIRECT, correcting the old adapter's docstring claim

`pass.goal_assist == True`: **669** verified across the full season, always
disjoint from `pass.shot_assist` (0/669 overlap) — a genuine source category
boundary (shot_assist = created a non-scoring shot; goal_assist = created
the goal), not a bug. This **contradicts** the pre-existing adapter's
docstring claim that assists "would require cross-referencing a shot-assist
pass to a goal outcome across two events" — the real source carries it as a
native boolean. `key_passes` continues to use `shot_assist` as-is (excluding
the assist itself), matching Wyscout's identical tag-disjointness handling;
`chances_created = key_passes + assists`.

### Minutes — genuinely DERIVABLE_METHODOLOGY_PENDING, not silently resolved

Lineup `positions` intervals are real and detailed (13,678 player-lineup
entries: 8349–8350 starters, ~2120 used substitutes, 3209 unused), but
**1,920 of 13,678 entries (14%) carry more than one position interval**, and
the boundaries are not cleanly attributable to a single substitution event.
Verified example (match 3754217, player 3437): three intervals where the
second interval's `end_reason` is `"Substitution - Off (Tactical)"` yet a
**third** interval for the same player in the same match continues to Final
Whistle — `end_reason` values do not reliably mean "this player left the
pitch" (`"Player Off"`/`"Player On"` appear to be broadcast camera-visibility
bookkeeping, distinct from real substitutions). Only 2 intervals leaguewide
end with `"Foul Committed (Second Yellow)"` despite 25 real second-yellow
dismissals, and 0 end with a literal `"Red Card"` reason despite 34 real
red cards. Stoppage-time overrun is tracked (`to` timestamps up to `96:35`
observed), so a naive fixed-90-minute fallback would also be wrong. **No
single deterministic rule reconciling all of this was verified — `minutes`
stays `DERIVABLE_METHODOLOGY_PENDING`, excluded from the adapter-safe
subset**, per the task's explicit instruction that missing is preferable to
a wrong value.

### Native score reconciliation — cleaner than Wyscout

`988` (shooter goals) `+ 38` (Own Goal For events) `= 1026`, exactly matching
the summed native `home_score + away_score` across all 380 matches. **No
residual gap**, unlike Wyscout's documented 1-goal shortfall for ENG_PL
2017/18 (match wyId 2499781). Team/match goal totals still always come from
the native score field, never reconstructed from summed player events.

## 5. Full 194/194 catalog accounting

`STATSBOMB_METRIC_MAPPINGS` (190 entries) ∪ `STATSBOMB_PROVIDER_OUT_OF_SCOPE_METRICS`
(4 entries, identical to Wyscout's — provider-agnostic internal engine
outputs: `league_strength`, `team_strength_elo`, `opponent_strength`,
`minutes_confidence`) = all 194 real `METRIC_CATALOG_V2` identities,
enforced disjoint and exhaustive at import time by `validate_full_catalog_coverage()`.

| Classification | Count | (Wyscout, for comparison) |
| --- | --- | --- |
| DIRECT | 65 | 43 |
| DERIVABLE_READY | 45 | 34 |
| DERIVABLE_METHODOLOGY_PENDING | 48 | 33 |
| REQUIRES_MODEL | 15 | 35 |
| UNSUPPORTED | 12 | 25 |
| AMBIGUOUS | 5 | 20 |
| **Adapter-safe (DIRECT + DERIVABLE_READY)** | **110** | **77** |

StatsBomb's richer event vocabulary (dedicated `Carry`, `Pressure`, `Ball
Recovery`, `Dispossessed`, `Miscontrol`, `Dribbled Past`, `Foul Won` event
types; per-event `player`-attributed `Block`; player-attributed goalkeeper
events; native `pass.goal_assist`/`pass.switch`/`pass.through_ball`/
`pass.cross` booleans; native `statsbomb_xg`) genuinely supports more
identities directly than Wyscout does — this was verified per-metric against
real full-season data, never assumed from "StatsBomb sounds richer."
Conversely, StatsBomb's duel/tackle outcome vocabulary
(`Success In Play`/`Success Out`/`Won`/`Lost...`) is genuinely more
ambiguous than initially expected, driving `tackles_won`/`duels_won`/
`ground_duels_won`/`tackle_success_pct`/`duel_win_pct` to `AMBIGUOUS` here —
not classified UNSUPPORTED merely for consistency with Wyscout's
higher AMBIGUOUS count, but independently re-derived from StatsBomb's own
real outcome values.

### Notable REQUIRES_MODEL → not-required-for-StatsBomb reclassifications vs Wyscout

`advanced.xg` is **DIRECT** here (a direct read of the provider-native
`shot.statsbomb_xg`), not REQUIRES_MODEL as it necessarily is for Wyscout
(which has no native xG value at all). This is a **read**, never a
recomputation — `shot.statsbomb_xg` must always be labelled a StatsBomb-
native model output in provenance, never "Football Intelligence's own
model." `xa`/`expected_assists_open_play`/`xa_per90`/`assists_minus_xa`
remain REQUIRES_MODEL — StatsBomb Open Data has no native xA field, verified.
`pressures` is **DIRECT** (dedicated `Pressure` event type, ~10x more
frequent than `Duel`) where Wyscout has no pressing signal at all
(REQUIRES_MODEL there); `successful_pressures`/`pressure_success_pct`/`ppda`
remain `DERIVABLE_METHODOLOGY_PENDING` — a time-window/success-correlation
rule and a defensive-third spatial boundary are still undefined, never
invented here.

### The 110-identity adapter-safe subset (Block 20C.2b scope)

7 match, 3 player_appearance, 4 player_season, 58 player_match, 10
goalkeeper_match, 2 goalkeeper_season, 26 team_match. Full list is
reproducible via `adapter_safe_mappings()`; see
`analytics/src/football_intelligence/providers/statsbomb_open_mapping.py`
for the exact per-identity source primitive and evidence.

## 6. Provider client audit — resolved this block

The pre-existing `providers/statsbomb_open.py` kept its good behavior
(official-endpoint-only, bounded retries, timeout, invalid-JSON/404
handling, explicit User-Agent, no auth, no scraping) unchanged. What Block
20C.1 flagged as missing vs. the Wyscout pattern is now addressed:

| Gap (Block 20C.1) | Resolution (this block) |
| --- | --- |
| No commit-SHA pinning (`master`-tracking) | `DEFAULT_PINNED_REVISION`, `ref` parameter, never silently substituted |
| No local disk cache | `providers/statsbomb_open_cache.py`, per-revision cache directories |
| No integrity verification | Self-computed SHA-256 sidecars, fail-loud on mismatch |
| No cache-reuse logic | `fetch_json_cached()` reuses hash-verified bytes without a network call |
| No source-revision provenance | `StatsBombOpenDataResponse.source_revision`, recorded in every cached fetch and the manifest |

## 7. Next step: Block 20C.2b

Rewrite the `NormalizedObservation` adapter (`data_mesh/adapters/statsbomb_open.py`)
scoped **exactly** to `adapter_safe_mappings()` (110 identities), using:

- the **lineup file** as the participation universe (matchday squad, starters,
  used/unused substitutes, shirt numbers) — never event-tag presence;
- the **lineup file's `cards` array** for yellow/red/second-yellow cards —
  never `Foul Committed` alone;
- the corrected, full-type-set `saves`/`goals_conceded`/`shots_on_target_faced`
  derivation;
- `pass.goal_assist` for `assists`;
- native `match_status`/`home_score`/`away_score` as authoritative, never a
  synthetic `"finished"` constant;
- `providers.statsbomb_open_policy.STATSBOMB_INTERNAL_ONLY` respected
  throughout — no emission path may be wired to any user-facing surface in
  that block either, until the compliance question in §3 is explicitly
  resolved.

This block does not touch Wyscout, does not reconcile the two providers, and
does not modify `data_mesh/adapters/statsbomb_open.py`.
