# Entity Resolution V2 (Block 20D.2)

Block 13's entity resolver (`data_mesh/entity_resolution.py`,
`data_mesh/pipeline.py`) was designed and proven against sources that all
share one convention: a `entity_type == "team", metric_name == "name"`
observation carries a provider's team identity, and every other metric is
information-theoretically unambiguous once resolved. Block 20D.1's real,
evidence-based audit (diagnosis only, no files changed) found that
convention does not hold for the two certified historical adapters --
Wyscout Open (Block 20B) and StatsBomb Open (Block 20C) -- and that the
`NormalizedObservation` schema itself was missing information the Metric
Catalog V2 requires. This document records what Block 20D.2 built to close
those gaps, and what it deliberately left for later blocks.

## Why V0 stopped being sufficient

1. **Team identity.** Neither certified adapter emits a `team.name`
   observation -- team identity lives entirely in `entity_identity_hints`
   (composite `entity_source_id` shapes like `"{match_id}:{team_id}"`).
   V0's `build_source_local_indexes()` bridges provider-scoped ids to
   logical keys only by scanning for that `team.name` row, so it can never
   populate a bridging index for either adapter.
2. **Competition identity.** `COMPETITION_MAPPINGS` had no
   `wyscout-open`/`statsbomb-open` entries at all -- every observation from
   either adapter was `UNRESOLVED` before resolution even reached team or
   match logic.
3. **Metric granularity.** The Metric Catalog V2 explicitly permits the
   same `metric_name` at more than one granularity. `saves` exists at both
   `player_match` and `goalkeeper_match`; both project to `entity_type ==
   "player"` and can share the same match-scoped `entity_source_id` shape.
   `NormalizedObservation` had no field recording which granularity a given
   observation belonged to, so the two were indistinguishable once
   resolved -- a real risk of silently merging two different facts into one
   logical bucket. **This could not be safely reconstructed later** from
   `entity_source_id`, `metric_name`, or `entity_type` alone (an earlier,
   incorrect diagnostic conclusion this block explicitly corrects): none of
   those three carries enough information in the general catalog to
   recover granularity after the fact.

## What Block 20D.2 built

### 1. Explicit metric granularity on `NormalizedObservation`

`data_mesh/models.py` gained `metric_granularity: MetricGranularity | None
= None` (imported from `metric_catalog.types`, no cyclic import --
`metric_catalog` has zero imports from `data_mesh`). Both certified
adapters (`wyscout_open.py`, `statsbomb_open.py`) now set it explicitly on
every observation their certified emission path produces, derived from
each closure's own known catalog mapping -- never inferred after
construction. Verified against real cached data: `saves` is emitted at
both `player_match` and `goalkeeper_match`, now distinguishable.

Each adapter also contains a pre-existing **legacy** code path (Coverage
Lab-era generic probe functions, predating Metric Catalog V2) that calls
the lower-level `_observation()` helper directly, bypassing the
certified-path `_emit()`/`_guard()` helpers. `_observation()`'s
`metric_granularity` parameter stays optional (default `None`) so those
legacy functions keep working unchanged; `_emit()`/`_guard()` (used only by
the certified path) require it. This asymmetry is intentional, not an
oversight.

### 2. Wyscout source-specific Unicode repair

`providers/wyscout_open_text.py` (`repair_wyscout_double_escaped_unicode`)
fixes a real, verified defect in Wyscout Open Data's official Figshare
`teams.json`/`players.json`: some `name`/`officialName`/`firstName`/
`lastName` fields were JSON-escaped twice for non-ASCII characters, so
after one normal `json.loads()` pass the string still contains the literal
six-character text `\uXXXX` instead of the intended character (verified at
the raw-byte level: two literal backslashes in the raw file). This lives
at the Wyscout provider/text boundary, not in the generic
`normalize_team_name()` -- it repairs one provider's raw field encoding, not
a general name-comparison heuristic, and must only ever be applied to
`name`/`officialName`/`firstName`/`lastName`-style fields, never to ids,
URLs, or `source_reference` values.

### 3. Team-name convergence fixes

An empirical collision check across the real 20 ESP_LL team names from
both Wyscout and StatsBomb (Block 20D.1's real overlap discovery) found
three genuine convergence gaps, not just the one anticipated going in:

| StatsBomb | Wyscout | Fix |
| --- | --- | --- |
| `RC Deportivo La Coruña` | `Deportivo La Coruña` | `rc` added to `_TEAM_STOPWORDS` |
| `Levante UD` | `Levante` | `ud` added to `_TEAM_STOPWORDS` |
| `Celta Vigo` | `Celta de Vigo` | `"celta vigo" -> "celta de vigo"` in a new `_SPANISH_SHORT_NAME_ALIASES` table |

`de` was deliberately **not** added as a generic stopword -- it is a
genuine Spanish preposition, not a corporate-entity-type token like `fc`/
`rc`/`ud`, and stripping it generically would be far riskier than the
narrow alias above. All fixes remain deterministic, table-driven
transformations -- no fuzzy/edit-distance/LLM matching was introduced.
Re-verified: all 20 real ESP_LL team names from both providers now
converge to exactly one logical identity each.

### 4. Real competition mappings -- provider-native identifiers

`COMPETITION_MAPPINGS` gained real, provider-native numeric entries for
both certified adapters, in both cases read directly from the adapter's
own real cached source data:

- `wyscout-open`: `competitionId=364` (verified against every match record
  in the real cached `matches_England.json`), never our internal canonical
  `"ENG_PL"` code.
- `statsbomb-open`: `competition_id=2` (verified against every match
  record's own `competition.competition_id` field in the real cached
  `matches/2/27.json`).
- Prepared, **not yet emitted**, ESP_LL entries using the same discipline:
  Wyscout `competitionId=795`/`seasonId=181144`; StatsBomb
  `competition_id=11`/`season_id=1`, discovered live during Block 20D.1's
  investigation, never assumed equal between providers. Neither adapter
  emits Spain-scoped observations yet -- these entries exist so Block
  20D.3 does not need to re-derive the ids.

An earlier pass of this block had put the canonical `"ENG_PL"` code itself
into `competition_external_id` for both certified adapters -- reasoned at
the time as "the adapter's own already-resolved value", but not a genuine
provider-native identifier the source itself uses. Corrected in the same
block's completion pass, once both adapters were updated (see section 6
below) to read and emit their real `competitionId`/`competition_id` field
directly from each match record.

### 5. Bounded match-date clustering

`cluster_match_dates()` compared each date against the *immediately
preceding* date, which could transitively chain day 1 -> day 2 -> day 3
into one cluster even when day 1 and day 3 were 2 days apart (a real risk
for congested festive-period or cup-replay fixture lists). Fixed to
compare every date against its cluster's own fixed representative (the
cluster's earliest member) instead, guaranteeing a cluster's span can never
exceed `tolerance_days` regardless of how many intermediate dates exist.
Input-order independence and duplicate-date independence are unchanged and
now additionally regression-tested.

### 6. Certified adapters now emit the full identity-hint contract

Both `wyscout_open.py` and `statsbomb_open.py` were narrowly extended
(Block 20D.2 completion pass) to populate every standard identity-hint key
the source genuinely supplies, never inventing one:

- **Match-scoped observations** (`home_score`, `away_score`, `status`,
  `kickoff_at`, `round_name`, `venue_name`): `match_external_id`,
  `home_team_external_id`/`home_team_name`,
  `away_team_external_id`/`away_team_name`, `kickoff_date`,
  `competition_external_id` (provider-native), `season_label`.
- **Team_match-scoped observations** (`shots_total`, etc.) and the
  per-team `home_away` fact: `match_external_id`, `team_external_id`,
  `team_name` when the source's separate teams reference is supplied.
- **Player_match/goalkeeper_match-scoped observations**:
  `match_external_id`, `player_external_id`, `player_name` when the
  source's separate players reference is supplied, `team_external_id`
  from the match roster.
- **Player_season/goalkeeper_season-scoped observations**:
  `player_external_id`, `player_name`, `competition_external_id`,
  `season_label` -- never a match or team (a season fact is not scoped to
  either).

StatsBomb's own match summary already carries team ids/names directly
(`home_team`/`away_team` blocks) and its lineup file carries player names
(`player_name`) -- no new payload parameter was needed. Wyscout's
`matches_England.json` carries neither; the adapter's certified functions
gained an optional `teams_payload` parameter (the official `teams.json`
reference file, already fetched and cached, just never previously
consumed) alongside the existing `players_payload`, so team/player names
populate when that reference is supplied and stay correctly absent
(missing, never invented) when it is not. Enriching hints never changes
what metric value/count an observation reports -- verified by a dedicated
regression test comparing full-season output with and without the
optional name references supplied.

`data_mesh/entity_resolution_v2.py` (new, purely additive module) reads
these hints directly -- never `entity_source_id`'s composite
`"{match_id}:{team_id}"` shape:

- **`logical_fact_key()`** -- builds the correctly match/season-scoped
  logical fact identity for every Metric Catalog granularity
  (`competition`, `team`, `match`, `team_match`, `player_appearance`,
  `player_match`, `player_season`, `goalkeeper_match`,
  `goalkeeper_season`). Returns `None`, never a degraded/partial key, when
  required context is missing. Enforces the essential invariants: different
  matches never share one `player_match` key; different seasons never share
  one `player_season` key; `player_match` and `goalkeeper_match` never
  share one fact key even for the same player in the same match;
  `team_match` never collapses into a bare `team` key.
- **`build_team_index_v2_from_observations()` /
  `build_match_index_v2_from_observations()` / `resolve_team_v2()` /
  `resolve_match_v2()`** -- the primary V2 mechanism: scans real
  `NormalizedObservation.entity_identity_hints` for
  `team_external_id`/`team_name` (and the match-level
  `home_team_*`/`away_team_*` pairs) to build a `(source_code,
  provider_id) -> logical key` index, then resolves matches by reusing
  V0's own pure `resolve_match()` with the hints' `match_external_id`,
  team keys, `season_label`, and `kickoff_date` -- never a second match-
  identity algorithm, never `entity_source_id`. Proven end-to-end against
  the real certified Wyscout adapter's actual output, not just synthetic
  fixtures. Raises `IdentityConflictError` the moment the same provider id
  resolves to two different logical entities across accumulated evidence --
  never silently picks one. **`kickoff_date` is passed through raw, without
  cross-source day-level tolerance canonicalization** (`resolve_match()` is
  a pure function with no clustering of its own; the correct bounded
  clustering primitive, `cluster_match_dates()`/`build_match_date_clusters()`,
  lives in `data_mesh/pipeline.py` and is not yet wired into this V2 path --
  see "Review-fix pass" below).
- **`build_team_index_v2()` / `build_match_index_v2()`** -- lower-level
  primitives retained for a caller that already has id-to-name evidence
  from elsewhere (e.g. a provider's own separate reference file scanned
  directly); they never touch `entity_source_id` either.
- **`PlayerCrosswalkEntry` / `PlayerCrosswalk` / `resolve_player_v2()`** --
  the player-identity crosswalk **contract only**. No entries are populated
  by this block. A valid entry records the source refs, resolved team
  context, shared-match evidence, the normalized exact name used, and
  optional corroborating nationality/position -- never generated from name
  similarity alone. `resolve_player_v2()` returns `UNRESOLVED` without an
  explicit, validated crosswalk entry, exactly like V0's
  `resolve_player()`, and never constructs `player:<normalized-name>` as a
  canonical identity. `PlayerCrosswalk.add()` raises
  `PlayerCrosswalkConflictError` on a genuine conflicting entry for the
  same `(source_code, provider_player_id)`.

## What is unchanged

`reconcile_metric()` and the semantic comparison policy are untouched.
`resolve_and_reconcile()`'s grouping still keys on `(logical_key,
entity_type, metric_name)` without `metric_granularity` -- each
`NormalizedObservation` already carries its own `metric_granularity`
through unchanged into that grouping (nothing is lost), but two
observations at different granularities that happen to share a
`(logical_key, entity_type, metric_name)` are not yet grouped separately.
Extending the grouping key and adding a granularity-aware semantic
comparison policy is Block 20D.4's job, not this block's.
`providers.statsbomb_open_policy.STATSBOMB_INTERNAL_ONLY` is unchanged.
Neither adapter's scope was generalized to Spain/ESP_LL. No DB ingestion,
fuzzy matching, LLM resolution, or automatic player crosswalk population
was performed.

## Source-compliance allowlist (Block 20D.2 completion pass)

`tests/test_real_data_source_policy.py`'s `_APPROVED_PROVIDER_CODES` had
never included `wyscout-open`, even though Wyscout Open was already
certified to the same evidentiary bar as `statsbomb-open` (which was
already listed) back in Block 20B.2b. Reviewed rather than assumed: the
allowlist's own docstring and comments (`test_real_data_source_policy.py`,
Block 18 / AGENTS.md section 5) define it as approval for "automated,
zero-cost, documented/official acquisition" -- registration as a real,
reviewed data source, never a canonical/user-facing promotion decision.
`statsbomb-open`'s own presence on the same list, while remaining
`internal_only` (`providers.statsbomb_open_policy.STATSBOMB_INTERNAL_ONLY`,
unchanged, never promoted to production), is direct existing proof that
allowlist membership does not imply promotion. Wyscout's CC BY 4.0 licence
is materially less restrictive than StatsBomb's terms, and it already has
a full certified adapter with a real audit trail (411,844 observations,
Block 20B.2b) -- by the same reasoning already applied to StatsBomb, its
absence was an oversight, not a deliberate exclusion. Added `wyscout-open`
to the allowlist and to the source-compliance register
(`docs/SOURCES.md`), documenting the exact rationale rather than treating
it as an incidental test fix. Both certified adapters remain
historical/deep only; neither this addition nor anything else in this
block changes that or opens a production-promotion path for either.

## Regression verification

The real Football-Data.co.uk x OpenFootball ENG_PL 2025/26 baseline
(`data/real/2025-26/eng_pl_matches.json` +
`eng_pl_matches_openfootball.json`, both pre-existing committed real
snapshots) was re-run end-to-end through `resolve_and_reconcile()` after
every change in this block: 380/380 matches, 20/20 teams, **1,140/1,140
agreed match-fact decisions, 0 conflicts, 0 unresolved observations**, and
identical results across two runs of the same input (idempotent). The
pre-existing 20 real team-name string `conflict` decisions (short vs.
official long form, e.g. "Wolves" vs "Wolverhampton Wanderers FC") are
unchanged.

Team-name normalization was re-verified against all four real scopes the
task requires, using real cached provider data (never synthetic names):
ENG_PL 2025/26 (Football-Data.co.uk, 20/20 distinct), Wyscout ENG_PL
2017/18 (real `teams.json`, 20/20 distinct), StatsBomb ENG_PL 2015/16
(real `matches/2/27.json`, 20/20 distinct, 17 clubs common with the
2017/18 Wyscout season all converging), and the ESP_LL 2017/18 diagnosis
set (real Wyscout `teams.json` Spain-scope, 20/20 distinct, plus the 3 real
StatsBomb-side spellings from Block 20D.1's original diagnosis --
`RC Deportivo La Coruña`, `Celta Vigo`, `Levante UD` -- all still
converging with their Wyscout counterparts). Committed as a permanent
regression test, `tests/test_entity_resolution_spanish_short_names.py`,
mirroring the existing `test_entity_resolution_english_short_names.py`.

Full repository test suite: `uv run pytest` (the exact command, not a
`-m "not integration"` restriction) -- **826 passed, 22 skipped**. Every
skip self-reports the identical reason, `DATABASE_URL not configured`:
these are `@pytest.mark.integration` tests genuinely requiring a real
Postgres connection this block correctly never provisions (no production
services). `ruff check .`, `ruff format --check .`, and `mypy src` all
pass with zero issues.

## Review-fix pass

An independent review of the actual diff found four concrete issues,
closed in a follow-up pass without redesigning the block:

1. **Emission identity did not include `metric_granularity`.** Both
   certified adapters validate the exact `(metric_name,
   metric_granularity)` pair via `_guard()`, but `_emit()`'s internal
   dedup/conflict identity was still `(source_code, entity_type,
   entity_source_id, metric_name)` -- missing granularity. Fixed in both
   adapters (`seen` keyed on the 5-tuple including
   `metric_granularity`). While adding the required regression test
   (`saves`/player_match and `saves`/goalkeeper_match coexisting under one
   shared `seen` dict), found that `goalkeeper_match`-granularity `saves`
   was declared adapter-safe but never actually emitted by either
   adapter -- a real gap between declaration and implementation. Fixed:
   both adapters now genuinely emit `saves` at `goalkeeper_match` (the
   same real event-derived count already emitted at `player_match`,
   correctly dual-scoped, not double-counted).
2. **Player crosswalk did not enforce its own documented validation
   bar.** `PlayerCrosswalkEntry` allowed an empty `shared_match_keys` and
   an absent `team_context_key`, after which `resolve_player_v2()` would
   still resolve it with positive confidence -- violating the block's own
   stated minimum evidence bar. Fixed: `team_context_key` is now a
   required (non-optional) field, and `PlayerCrosswalkEntry.__post_init__`
   validates every field non-blank and requires at least one non-blank
   `shared_match_key` -- an invalid entry can never be constructed, so it
   can never enter the crosswalk or be resolved. `PlayerCrosswalk.add()`
   now also rejects re-adding a different entry for an already-populated
   `(source_code, provider_player_id)` key unless it is exactly equal to
   what is already stored (the simpler exact-idempotent contract, per the
   review's own preference, rather than a merge policy).
3. **`home_away`'s Metric Catalog granularity was wrong.** Declared
   `granularity="match"` in `metric_catalog/domains/context.py`, but both
   certified adapters correctly treat it as a per-team-in-this-match fact
   (`entity_type="team"`, `entity_source_id="{match}:{team}"`), which
   required a hand-maintained entity-type override in each adapter (and
   the audit jobs) specifically because the catalog was misclassified.
   Corrected the catalog to `granularity="team_match"`, updated both
   provider mappings (`wyscout_open_mapping.py`,
   `statsbomb_open_mapping.py`) to match, updated both certified adapters'
   emission granularity, and removed the now-unnecessary entity-type
   overrides in both adapters and both audit jobs
   (`jobs/audit_wyscout_adapter.py`, `jobs/audit_statsbomb_adapter.py`).
   Re-verified the full 194-identity catalog accounting stays exact for
   both providers (`validate_full_catalog_coverage()` passes at import for
   both mapping modules). This was a purely internal reclassification --
   `home_away` had never been ingested into any committed real snapshot or
   database, so nothing outside this branch depended on the old
   classification.
4. **`logical_fact_key()` and `build_match_index_v2_from_observations()`
   treated a blank string as present context.** `if x is None: return
   None` never caught `x == ""`. Fixed with a shared `_blank()` helper
   (`None` or whitespace-only) used everywhere `logical_fact_key()` checks
   required context, and an explicit blank-`season_label` guard in
   `build_match_index_v2_from_observations()` (V0's `resolve_match()`
   itself is not guarded against a blank season, and was deliberately left
   unchanged rather than touching a pure V0 function for a V2-only gap).

Two additional, smaller corrections from the same review:

- **Misleading `kickoff_date` documentation.** Docstrings had implied
  `resolve_match()` itself performs date-tolerance clustering. Corrected:
  `resolve_match()` is a pure function with no clustering of its own; the
  real bounded-clustering primitive
  (`cluster_match_dates()`/`build_match_date_clusters()`) lives in
  `data_mesh/pipeline.py`. `build_match_index_v2_from_observations()`
  currently passes each observation's raw `kickoff_date` straight through
  -- cross-source date-tolerance canonicalization for the certified
  adapters is explicitly **not yet wired into V2** and remains deferred to
  Block 20D.4's pipeline/Reconciliation V2 wiring (assessed and
  deliberately not attempted here: reusing `build_match_date_clusters()`
  cleanly would require re-deriving the exact same grouping key it
  computes internally via name-based `resolve_team()`, while this V2 path
  can instead use id-based `team_index` resolution -- reconciling the two
  without risking a subtly-wrong parallel clustering algorithm is real
  integration work for a later block, not a one-line fix).
- **Stale `docs/SOURCES.md` StatsBomb row.** Described StatsBomb Open Data
  as FIFA World Cup 2022 validation-only, never ENG_PL -- stale after Block
  20C's certified Premier League 2015/16 historical/deep evidence (110/110
  adapter-safe identities, 643,628 real observations). Updated to record
  both real roles (the WC2022 validation sample and the ENG_PL 2015/16
  certified adapter), with `STATSBOMB_INTERNAL_ONLY = True` and no
  canonical/production promotion decision stated explicitly for both.
  StatsBomb's licensing policy itself is unchanged.

## Final micro-audit

An independent review of the review-fix pass itself found two remaining
provenance/audit questions.

### 1. The real adapter audits were not granularity-aware

`jobs/audit_wyscout_adapter.py` and `jobs/audit_statsbomb_adapter.py`
projected catalog identity coverage through `(metric_name, entity_type)`
-- the exact same blind spot `_emit()`'s dedup identity had before the
review-fix pass, and for the exact same reason:
`saves`/`player_match` and `saves`/`goalkeeper_match` both project to
`entity_type="player"`, so a `(metric_name, entity_type)`-keyed coverage
set cannot tell them apart. This meant the audits could have certified
77/77 or 110/110 "full coverage" even if `goalkeeper_match` `saves` had
never actually been emitted -- exactly the false-certification risk the
review flagged, and (before this fix) a real, not merely theoretical, gap:
the audits had not yet been re-run against the review-fix pass code at
all, so this blind spot had never been exercised against the corrected
adapters.

Fixed in both audit jobs: coverage and duplicate/conflict identity are now
keyed directly on the real `(metric_name, metric_granularity)` field read
from each observation -- never inferred from `entity_type`, never a second
projection table. This let the old `_GRANULARITY_TO_ENTITY_TYPE`-based
projection logic (`match_scoped_pairs`/`season_scoped_pairs`/
`match_entity_pairs`, `_SEASON_SCOPED_GRANULARITIES`) be deleted entirely
rather than patched -- the granularity-keyed version is both correct and
simpler. Added a `no_missing_metric_granularity` check: a certified-path
observation with `metric_granularity=None` is now explicitly reported as a
failure, never silently projected through `entity_type` as a fallback.
StatsBomb's audit also had a second, related bug the review's reasoning
predicted: `total_player_saves` summed every `"saves"` observation
regardless of granularity, which would have silently doubled once
`goalkeeper_match` `saves` started being genuinely emitted (both
granularities carry the identical real value for a goalkeeper). Fixed by
restricting that sum to `metric_granularity == "player_match"` --
confirmed correct by the real full-cache re-run below, which reproduces
the exact historical `2,277` saves count, not `4,554`.

Focused unit tests (`tests/test_audit_wyscout_adapter.py`,
`tests/test_audit_statsbomb_adapter.py`, new files, synthetic
observations, no real cache needed) prove: (A) a `player_match`-only
`saves` observation does not count as evidence `goalkeeper_match` was
observed; (B) both granularities present means both count; (C) the
duplicate/conflict identity distinguishes two different granularities at
the same `(source, entity_type, entity_source_id, metric_name)` (no false
conflict) while still catching a genuine same-identity-including-
granularity conflict; (D) a `metric_granularity=None` observation is
reported by the new check and excluded from coverage, never silently
projected.

### 2. Real full-cache re-certification

The historical totals (Wyscout 411,844, StatsBomb 643,628) were produced
before `goalkeeper_match` `saves` became a distinct emitted identity, so
they could not honestly be presented as the review-fix pass's current
output without re-running the real audit. Per the task's explicit
instruction, only plausible existing local cache locations were searched
(no crawling, no downloads): the two providers' `DEFAULT_CACHE_DIR`
locations inside this worktree (Wyscout's events archive was missing here
-- matches/teams/players only), and the sibling worktrees where the
original Block 20B.2b/20C.2b certifications were performed
(`block20-multi-source` for Wyscout, `block20c-statsbomb` for StatsBomb),
which is where each provider's own certification work originally
downloaded and cached its full dataset. Both were found complete
(Wyscout: 380/380 matches with a real `events_England.json`, 643,150 raw
events; StatsBomb: 380/380 matches, all 760 real events+lineups files).
Re-ran both real audit CLIs read-only against those existing caches (
`--cache-dir <sibling-worktree-path>`), using the current worktree's code
-- zero network requests, zero writes to the sibling worktrees.

**FULL REAL-CACHE CERTIFICATION VERIFIED**, both adapters, all checks
PASS:

| | Wyscout | StatsBomb |
| --- | --- | --- |
| Total observations (current) | **412,609** | **644,396** |
| Total observations (historical, pre-review-fix-pass) | 411,844 | 643,628 |
| Net delta | +765 | +768 |
| Adapter-safe identities with real observations | 77/77 | 110/110 |
| `no_missing_metric_granularity` | PASS (0 missing) | PASS (0 missing) |
| Duplicate/conflict count | 0 | 0 |

The net delta in both cases is exactly the count of resolved
goalkeeper-match instances that now additionally receive a
`goalkeeper_match`-granularity `saves` observation (previously only
`player_match`-granularity existed) -- confirmed by cross-referencing
against each adapter's own goalkeeper-scoped metric counts (e.g. Wyscout's
`passes`/`launches` goalkeeper_match counts are also exactly 765;
StatsBomb's `claims`/`passes` goalkeeper_match counts are also exactly
768). StatsBomb's `saves` total, restricted to `player_match` granularity
per the audit fix above, independently re-verified at exactly **2,277** --
identical to the historical certified value, proving the new
dual-granularity emission does not corrupt the count.

One additional stale check was found and fixed while re-running: both
audits' `competition_scope_is_eng_pl_only` check still expected the
canonical `"ENG_PL"`/internal competition code, which the completion pass
had already correctly changed the adapters to stop emitting as
`competition_external_id` (replaced with the real provider-native
`competitionId`/`competition_id`). Updated both checks to expect the real
values (`"364"` for Wyscout, `"2"` for StatsBomb) -- both now PASS.

### CODE/UNIT CONTRACT VERIFIED vs. FULL REAL-CACHE CERTIFICATION VERIFIED

Distinguished explicitly, everywhere counts are cited in this repository's
docs (`docs/SOURCES.md`, `docs/STATSBOMB_METRIC_MAPPING.md`,
`docs/BLOCK20_MULTI_SOURCE.md`): CODE/UNIT CONTRACT VERIFIED means the
targeted fixture-level tests in this repository's own test suite pass
(always true after this pass, `uv run pytest`). FULL REAL-CACHE
CERTIFICATION VERIFIED means a real, complete, 380-match local cache was
actually re-processed end-to-end by the real adapter and the real audit
job -- true for both providers as of this micro-audit, using the caches
found in the sibling worktrees above, not merely assumed from the
historical Block 20B.2b/20C.2b results. The historical 411,844/643,628
figures remain valid evidence of what those specific, earlier blocks
certified under their own (pre-`metric_granularity`) contract -- they are
preserved in the historical narrative sections of `docs/BLOCK20_MULTI_
SOURCE.md` and `docs/STATSBOMB_METRIC_MAPPING.md`, explicitly labelled as
such, never erased or silently overwritten.

## Final integrity fixes (PR #18 review)

A further independent review of the committed PR found four narrow
integrity gaps, closed without redesigning anything above.

### 1 & 2. The audit coverage gate and unexpected-identity check were not wired to fail

The two real audit jobs already computed `safe_identities_with_zero_
observations` correctly (the granularity-aware set from the earlier
micro-audit), but nothing turned a non-empty set into a failing
`VerificationCheck` -- a future real audit could have printed "76/77" and
still exited `0`. Added `all_adapter_safe_identities_observed` to both
audits, `passed = not safe_identities_with_zero_observations`, detail
listing the exact missing `(metric_name, metric_granularity)` identities.

Separately, `no_unexpected_identities_emitted` still checked
`(metric_name, entity_type)` against `_SAFE_METRIC_ENTITY_PAIRS` -- too
coarse after Block 20D.2: `saves`/`player_season` has a perfectly valid
`entity_type="player"` (same as the safe `saves`/`player_match`), so this
check alone could never flag it as unexpected. Added a new, authoritative
`unexpected_exact_identities` (`observed_identities - safe_identities`,
keyed on the real `metric_granularity` field) and a new
`no_unexpected_exact_identities_emitted` check in both audits. The
original entity_type-keyed check and field are kept, explicitly documented
as a coarser defense-in-depth signal, never a substitute.

### 3. `metric_granularity` had no DB persistence safeguard

`db/data_mesh_repository.py`'s `persist_observations()` writes to
`ingestion.source_observations`, a Block 13 table with no column or
natural key for `metric_granularity`. Persisting a V2 observation there
would silently upsert `saves`/`player_match` and `saves`/`goalkeeper_match`
onto the same row (same `entity_type`, same `entity_source_id`) --
destroying real evidence, not merely mislabeling it. No schema migration
was made (deliberately out of scope for this block). Instead,
`persist_observations()` now pre-scans the whole batch and raises
`MetricGranularityNotPersistableError` before executing any SQL statement
-- including the provider-id lookup -- the moment any observation carries
a non-`None` `metric_granularity`. A batch mixing legacy and V2
observations fails entirely, never partially persisting the legacy item
first. Legacy (`metric_granularity=None`) observations are completely
unaffected -- `tests/integration/test_data_mesh_pipeline.py`'s existing
real-Postgres test already covers that path and needed no changes.
Real V2-aware persistence (a genuine schema change: a new column and a
widened natural key) remains deferred to the Reconciliation V2 / Block
20D.4 work -- this is an explicit, documented, temporary boundary, not a
silently unsupported gap.

### 4. The Metric Catalog release version still described the old `home_away` identity

`home_away`'s true catalog identity is `(key="home_away",
granularity="team_match")` since the earlier fix in this document, but
`CATALOG_V2_VERSION` ("metric-catalog-v2.0") -- the single release version
every `MetricDefinition` in the catalog shares, by this catalog's own
existing convention -- still described the catalog as it stood before that
identity changed. Bumped to `"metric-catalog-v2.1"`. No other adapter/model
version changed as a result; `SEMANTIC_VERSION` for the two certified
adapters and `MODEL_VERSION` for the reconciliation engine are unaffected
by this catalog-level bump.

### 5. One stale comment

A comment above `_SAFE_METRIC_ENTITY_PAIRS` in `wyscout_open.py` still
said `NormalizedObservation cannot fully express catalog granularity` --
false since Block 20D.2 added the `metric_granularity` field. Corrected to
describe `_SAFE_METRIC_ENTITY_PAIRS` accurately: a coarser, entity_type-only
defense-in-depth check, never the reason granularity can't be expressed.

## Block 20D.3 -- Rich Overlap Enablement (complete)

Generalized both certified adapters to an explicit `AdapterScope` contract,
verified the real Barcelona 2017/18 overlap evidence (36 shared canonical
matches, 0 date mismatches, exactly 2 Wyscout-only Barcelona fixtures) via
the V2 identity contract, and populated the first REAL deterministic
`PlayerCrosswalk` from that overlap, including a genuine discovered
contract gap: 4 real player pairs evidenced under more than one resolved
team context (real January 2018 mid-season transfers), which the
single-team-context `PlayerCrosswalkEntry` shape at the time could not
represent without either destroying evidence or forcing an arbitrary
choice -- excluded from the crosswalk and reported rather than either of
those, pending explicit review.

### Block 20D.3 corrective pass -- Option C multi-team-context crosswalk (complete)

A diagnosis-only follow-up (real-cache re-run, no repository files
changed) confirmed all 4 excluded pairs are genuine, clean,
non-overlapping mid-season transfers -- not name collisions, not
resolution bugs. This corrective pass then implemented the redesign that
diagnosis left open: `PlayerCrosswalkEntry.team_context_key: str` /
`shared_match_keys: tuple[str, ...]` were replaced by a new
`PlayerTeamContextEvidence(team_context_key, shared_match_keys)` value
object and `team_context_evidence: tuple[PlayerTeamContextEvidence, ...]`
(N>=1 contexts per entry, validated for canonical ordering, no duplicate
team context, and no shared match key claimed by two different contexts).
The registry key (`PlayerCrosswalk.entries: dict[(source_code,
provider_player_id), PlayerCrosswalkEntry]`) and `resolve_player_v2()`'s
signature are both unchanged -- one provider player id still resolves to
exactly one player identity, never one identity per club.
`crosswalk_canonical_key()` was redesigned to a versioned, opaque,
SHA-256-digest-based `overlap-player-v2:{competition}:{season}:{digest}`
key over the validated, canonically-ordered provider refs -- team-context-
and name-independent, so a transfer no longer changes a player's own
identity key, and explicitly documented as never a global canonical
player id. All 4 real transfers now resolve
(`resolve_player_v2(wyscout_id) == resolve_player_v2(statsbomb_id)`, each
with 2 correctly-scoped team contexts, no evidence dropped or
misattributed): accepted pairs **430 -> 434**, crosswalk entries
**860 -> 868**. A separately reported "1 one-to-many / 1 many-to-one"
ambiguity figure was traced to two synthetic unit-test fixtures
(`tests/test_audit_wyscout_statsbomb_overlap.py`) that correctly assert
`== 1` for their own tiny constructed scenarios -- unrelated to the real
data, which the authoritative machine audit has always reported as `0`/`0`
both before and after this pass. Full detail:
[`BLOCK20_MULTI_SOURCE.md`](BLOCK20_MULTI_SOURCE.md#block-20d3-corrective-pass----option-c-multi-team-context-crosswalk-complete).

Also corrected in this pass: the assumption that the real ENG_PL 2025/26
`resolve_and_reconcile()` regression (380 matches, 20 teams, 1,140/1,140
agreed match-fact decisions, 0 unresolved, idempotent) requires
PostgreSQL was checked against the actual code and found wrong --
`resolve_and_reconcile()` is pure and in-memory; only canonical loading
into `football.*` is genuinely DB-backed. A new regression test,
`tests/test_real_snapshot_v2_reconciliation_regression.py`, reads the
already-committed real snapshot files directly and reproduces the exact
historical baseline with zero network access and zero database
connection.

## Next step: Block 20D.4

Execute the rich multi-source Reconciliation V2 this block deliberately
did not attempt: granularity-aware reconciliation grouping, semantic
comparability policy, tolerances, provider-native-vs-derived comparison
policy, source-independence policy, conflict resolution, how
`STATSBOMB_INTERNAL_ONLY` propagates through reconciliation, the deferred
cross-source date-tolerance clustering integration into V2, and a
decision on whether/how `overlap-player-v2` crosswalk keys ever map to an
independent, canonical `football.players` identity (the corrective pass
above resolved the multi-team-context contract shape itself, not this
separate production-promotion question).
