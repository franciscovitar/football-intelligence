# Block 20 — Multi-Source Real Data Expansion

```text
multiple raw sources -> provider-specific acquisition -> normalization
    -> entity resolution -> reconciliation -> canonical evidence
    -> derived metrics -> intelligence -> product
```

Block 20 adds new provider-specific acquisition lanes without replacing any
existing source. Every source keeps its own explicit role
(current/recent vs historical/deep) and its own provenance; nothing is
silently merged across competitions or seasons, and nothing is silently
promoted to a role it does not have.

## Source roles

- **Current / recent** -- continuously updated, can report the true
  in-progress or latest-completed season. Football-Data.co.uk and
  OpenFootball remain the current/recent structured evidence sources for
  ENG_PL (see `docs/REAL_DATA_SOURCE_AUDIT_V2.md`,
  `docs/REAL_DATA_SNAPSHOT_V2.md`). This block does not touch or replace
  either of them.
- **Historical / deep** -- rich, event-level evidence for a fixed past
  season, never presented as current. StatsBomb Open Data already holds
  this role (`docs/ZERO_COST_COVERAGE.md`); Wyscout Open Data (below) is a
  second, independent historical/deep provider. Block 20 is about
  supporting *multiple* historical/deep providers, not swapping one
  dependency for another.

## Wyscout Open Data (Block 20B.1: acquisition + audit)

| Field | Value |
| --- | --- |
| Role | `historical / deep` -- **never current** |
| Initial scope | `ENG_PL` 2017/18 |
| Authoritative source | Figshare collection `4415000` |
| Collection DOI | `10.6084/m9.figshare.c.4415000.v5` |
| Public API | `https://api.figshare.com/v2` (documented, unauthenticated) |
| Licence | CC BY 4.0 (attribution required) |
| Paper | Pappalardo et al., "A public data set of spatio-temporal match events in soccer competitions", *Scientific Data* 6, 236 (2019) |
| Paper DOI | `10.1038/s41597-019-0247-7` |

**Only the original Figshare collection is used.** No Kaggle mirror, no
GitHub mirror, no scraped Wyscout commercial page, and no repackaged
dataset -- consistent with the Block 18 review's rejection of
Kaggle/GitHub repackaged player datasets whose upstream rights cannot be
independently verified (`docs/REAL_DATA_SOURCE_AUDIT_V2.md`, "Sources
investigated and rejected without integration").

**Wyscout Open 2017/18 must never be presented to users as current
Premier League evidence.** It sits alongside StatsBomb Open Data as a
second historical/deep provider; both are explicitly excluded from any
`current_available` coverage state
(`docs/ZERO_COST_COVERAGE.md`'s coverage state model).

### What Block 20B.1 implements

- `analytics/.../providers/wyscout_open.py` -- a minimal, stdlib-only
  client for Figshare's public v2 API: paginated collection-article
  discovery, exact-title article lookup, file metadata parsing, bounded
  retries, and checksum-verified (MD5, matching Figshare's own
  `computed_md5`) file download with cache reuse. A small
  `safe_extract_zip` helper rejects absolute paths, drive-letter paths,
  and `..` traversal before writing anything to disk.
- `analytics/.../jobs/probe_wyscout_open.py` -- a **local-only**
  acquisition/audit CLI
  (`football-intelligence-probe-wyscout-open`). It fetches and caches the
  England 2017/18 matches/events files (plus best-effort
  competitions/teams/players/tag-mapping context), computes match count,
  event count, roster/squad player IDs, event-actor player IDs, and
  distinct team IDs directly from the downloaded payloads, and compares
  match/event/player counts against the paper's published reference facts
  (380 matches / 643,150 events / 603 players). It also audits
  event-schema field coverage (`playerId`/`teamId`/`positions`/`tags`) and
  whether match payloads carry lineup/bench/substitution structures. This
  job never imports `football_intelligence.db`, never requires
  `DATABASE_URL`, and never writes to `football.*` / `ingestion.*` /
  `intelligence.*`.

#### Player-count semantics (verified against the real source)

The article-level Figshare "Matches"/"Events" files are not split per
country -- each publishes a single archive (`matches.zip` / `events.zip`)
covering every competition. `WyscoutOpenDataClient.select_file` first
tries an exact keyword match at the article-file level and, only when
that yields zero matches, falls back to the article's sole `.zip` file so
its contents can be inspected after safe extraction
(`probe_wyscout_open._resolve_content_path`) -- the England-specific JSON
file is only ever identified from the real, downloaded archive contents,
never assumed from an unofficial mirror layout.

A live probe run against the real ENG_PL 2017/18 files, cross-checked
against the paper, established that the published **603 players** is the
competition **roster/squad** population -- every player named in any
match's `teamsData[*].formation.lineup` or `.bench` -- not the narrower
set of players who actually generated a tagged event
(`events_England.json[*].playerId`, **514** players for this dataset; 89
rostered players, e.g. unused substitutes, never appear as an event
actor). The probe reports both, explicitly labeled and never conflated:
`PLAYERS COUNT` verification against the published 603 uses the roster
population; the 514 event-actor count stays a separate informational
metric.

Two further real-source quirks the probe handles defensively, confirmed
against the live cached files rather than assumed:

- `formation.substitutions` is sometimes the literal string `"null"`
  instead of `[]` when a team made zero substitutions in a match (seen
  even with `hasFormation == 1` and normal `lineup`/`bench` data) -- any
  non-list value is treated as "no substitutions", never a structural
  error.
- 4 of the 603 roster player IDs (`379199`, `447214`, `470819`, `532900`)
  do not resolve to any entry in `players.json`. This is reported as an
  informational source-data-quality gap (`roster players missing from
  players.json`) and never reduces the roster population or fabricates
  replacement player data.
- `teams.json`'s `area.name` field is **not** a reliable way to enumerate
  ENG_PL's 20 teams -- it files Swansea City under `area.name == "Wales"`
  despite Swansea playing in the English top flight that season. Team
  identity is derived from the teams that actually appear in the England
  match/event payloads, never from a `teams.json` area filter.

### What Block 20B.1 deliberately does NOT implement

No Wyscout event -> `NormalizedObservation` adapter exists yet, and no
metric mapping (`passes_total`, `progressive_passes`, `advanced.xg`,
`tackles`, `duels_won`, `key_passes`, `pressures`, etc.) is guessed from
memory or unofficial documentation. Block 20B.2 will only add such
mappings after this probe's real, live output confirms the actual field
names, tag semantics, and structural shape of the England 2017/18 files --
the same discipline already applied to StatsBomb Open Data's verified
event-field derivations.

### Cache hygiene

Downloaded/extracted Wyscout files are never committed. `data/cache/` is
git-ignored (`.gitignore`); the probe's default cache directory is
`data/cache/wyscout-open/`.

## Real data source policy

This block does not relax the Block 18 source-review conclusions in
`docs/REAL_DATA_SOURCE_AUDIT_V2.md`. Rejected sources (FBref/Sports-
Reference, SofaScore/FotMob, Understat, Transfermarkt, ESPN hidden
endpoints, Bundesliga.com scraping, Fantasy Premier League, Kaggle/GitHub
repackaged datasets) stay rejected; nothing here re-opens that review.
`analytics/tests/test_real_data_source_policy.py`'s approved-provider
allowlist is unchanged by Block 20B.1 -- the Wyscout Open provider client
is acquisition/audit tooling only and is not yet registered as a Data Mesh
adapter or Coverage Lab provider.

## Block 20B.2a — empirical Wyscout -> Metric Catalog mapping audit

With Block 20B.1's real cached ENG_PL 2017/18 source in hand, Block 20B.2a
built an **empirical semantic audit** -- not the adapter itself -- of which
Metric Catalog V2 identities Wyscout Open Data can support, and how:

- `docs/WYSCOUT_METRIC_MAPPING.md` -- the full empirical source-semantics
  inventory (every `eventName`/`subEventName`, the authoritative 59-tag
  vocabulary resolved from the real `tags2name.csv`, verified match/roster
  structure) plus the mapping table itself, organized by the same
  participation/output/creation/passing/dribbling/defending/goalkeeping/
  team categories the product spec uses.
- `analytics/.../providers/wyscout_open_mapping.py` -- the machine-readable
  version (`WYSCOUT_METRIC_MAPPINGS`, data/metadata only, no adapter
  behavior). A follow-up pass closed the full catalog accounting: **190**
  provider mapping entries (43 DIRECT / 67 DERIVABLE / 35 REQUIRES_MODEL /
  25 UNSUPPORTED / 20 AMBIGUOUS) plus **4** entries in
  `WYSCOUT_PROVIDER_OUT_OF_SCOPE_METRICS` (internal analytics-engine
  outputs such as `team_strength_elo` that were never a Wyscout-data
  question and must never be misclassified as Wyscout UNSUPPORTED) account
  for all **194** real `METRIC_CATALOG_V2` identities, enforced at import
  time by `validate_full_catalog_coverage()` (the two sets must be
  disjoint and their union must equal the full catalog). See
  `docs/WYSCOUT_METRIC_MAPPING.md` section 6 for the exact accounting and
  the verified goal-reconciliation exception (match `wyId 2499781`).
- `analytics/.../jobs/audit_wyscout_metric_mapping.py`
  (`football-intelligence-audit-wyscout-mapping`) -- a local-only,
  no-network, no-database regression job that re-derives the exact counts
  and tag/label pairs the mapping's classifications depend on directly
  from the cached files, so a future edit that quietly stops matching
  reality fails loudly instead of drifting.

**Headline findings** (see `docs/WYSCOUT_METRIC_MAPPING.md` for full
evidence): `goals`/`assists`/`shots_total`/`shots_on_target`/`passes_total`/
`passes_accurate`/`key_passes`/`duels_total`/`duels_won`/`interceptions`/
`clearances`/`yellow_cards`/`saves` are all DIRECT from verified event tags.
`expected_goals`/`xa`/`xThreat`/pressing metrics are all REQUIRES_MODEL --
Wyscout provides shot/pass features a model could use, never a value
itself. `tackles`, `dribbles_attempted`, `dispossessed`/`miscontrols`, and
`big_chances(_created)` are AMBIGUOUS: the source has an adjacent tag, but
not precise enough semantics to safely equate. `carries`/`progressive_carries`,
`blocks`, `fouls_drawn`, `formation` (team shape), and player
`captain`/`shirt_number`/`listed_position` are UNSUPPORTED -- verified
absent from the real schema, not assumed missing. Progression/spatial
metrics (`progressive_passes`, `final_third_entries`, box entries, pass-
length buckets) are DERIVABLE but explicitly **methodology pending**: the
repository has no existing attack-direction/threshold convention to reuse,
and this audit does not invent one.

## Block 20B.2b — Wyscout Open adapter (NormalizedObservation, no ingestion)

`analytics/.../data_mesh/adapters/wyscout_open.py` converts already-loaded
ENG_PL 2017/18 payloads into `NormalizedObservation` rows, scoped
**exactly** to `adapter_safe_mappings()` -- the 77-identity adapter-safe
subset (43 DIRECT + 34 DERIVABLE_READY). This is transform-only: no HTTP
requests, no Figshare downloads, no database writes, no canonical
ingestion. `source_code = "wyscout-open"` (matching the existing
hyphenated provider-code convention -- `statsbomb-open`,
`football-data-org`, `football-data-uk`), `source_type =
"objective_structured"`, scope `competition_external_id = "ENG_PL"` /
`season_label = "2017/18"` on every observation's identity hints.

**Emission is allowlist-enforced at both import time and runtime**: the
module's own `_EMITTED_IDENTITIES` constant is validated against
`adapter_safe_mappings()` at import (an accidental non-safe identity fails
immediately), and every single observation additionally passes through a
runtime `(metric_name, entity_type)` guard before construction --
DERIVABLE_METHODOLOGY_PENDING, REQUIRES_MODEL, UNSUPPORTED, AMBIGUOUS, and
provider-out-of-scope identities can never be emitted, proven by
`football-intelligence-audit-wyscout-adapter` (local-only, no network, no
DB) against the real cached source: all 77 safe identities produced real
observations, zero unexpected identities, zero conflicting duplicates.

**Participation universe** (stronger than StatsBomb Open Data's adapter):
a player only receives a `player_match`/`goalkeeper_match` observation --
including a real `0` -- when the match's own verified
`formation.lineup`/`bench`/`substitutions` structure confirms they
actually took the field. An unused bench player gets a `started=False`
squad-membership fact but no performance-stat observation at all.

**Goal reconciliation rule preserved exactly as diagnosed**: player
`goals` come from event-tag attribution (988 for the full season, verified
against the real cache); team/match score totals
(`goals_for`/`goals_against`/`home_score`/`away_score`) always come from
the native `teamsData[*].score` field (1018), never from summing
player-tagged goal events. Match `wyId 2499781` (Chelsea 0-1 Manchester
City) -- the one real match with no shot-type event for the scoring team,
only the conceding goalkeeper's failed `Save attempt` carrying the Goal
tag -- is handled exactly as required: the team-level score is still
correct (native), and no player is ever credited an invented goal.

**Goalkeeper identity**: exclusively `players.json`'s global
`role.code2 == "GK"`, never shirt number, event type, listed position, or
formation slot. `goals_conceded`/`clean_sheets`/`shots_on_target_faced`/
`save_pct` are only emitted for a team-match with exactly one GK-role
participant, so a mid-match goalkeeper substitution (which would need
event-timestamp attribution this block does not implement) stays missing
rather than mis-attributed.

**Verified against the real cache** (`football-intelligence-audit-wyscout-adapter
--cache-dir data/cache/wyscout-open`): 411,844 observations; 380 matches,
20 teams, 603 players; 0 conflicting duplicates; 0 unexpected identities;
all 77 adapter-safe identities produced real observations.

## Next step: Block 20B.3

No canonical ingestion, entity resolution, or reconciliation exists yet
for Wyscout Open. A future block will:

- feed the adapter's observations through the existing entity-resolution /
  reconciliation pipeline (`data_mesh/entity_resolution.py`,
  `data_mesh/reconciliation.py`), reusing it rather than building a
  second one;
- decide a promotion policy before anything ever reaches `football.*`
  (the existing "future promotion contract" in `docs/ZERO_COST_COVERAGE.md`
  already states the invariants any such policy must respect);
- only then consider reconciling Wyscout against StatsBomb Open Data for
  competitions/seasons where both exist -- not attempted in this block;
- extend the mapping to DERIVABLE_METHODOLOGY_PENDING identities only
  after an explicit, reviewed spatial/threshold methodology is defined
  (never invented ad hoc inside the adapter).

## Block 20C — StatsBomb Open Data brought to the Wyscout evidence standard

StatsBomb Open Data already held a `historical/deep` role since Block 14
(`docs/ZERO_COST_COVERAGE.md`), but its adapter pre-dates the Block 20
methodology. Block 20C re-audits it under the same discipline, without
assuming the existing code is correct merely because it already exists.

### Block 20C.1 — real-source audit and target-scope selection (diagnosis only)

Selected **Premier League 2015/16** (`competition_id=2`, `season_id=27`) as
the primary scope: the only genuinely full season (380/380 matches, 20
teams) among the candidates measured directly against the live source --
correcting an implicit assumption that Bundesliga 2023/24 (in fact 34/306,
already documented in `docs/ZERO_COST_COVERAGE.md`) or La Liga 2017/18 (in
fact 36/380) might be usable "full seasons". Found the existing adapter's
event-tag-presence participation assumption weaker than the real lineup
file's data, a verified undercounting gap in card derivation (`Bad
Behaviour` events never read), and an unresolved saves-semantics question --
all diagnosed, none fixed in that block. No repository files were modified.

### Block 20C.2a — reproducible source layer + empirical mapping

See `docs/STATSBOMB_METRIC_MAPPING.md` for the full evidence trail. Summary:

- **Reproducible acquisition**: `providers/statsbomb_open.py` now pins to a
  fixed commit SHA (`DEFAULT_PINNED_REVISION`) by default, never `master`;
  `providers/statsbomb_open_cache.py` adds a local SHA-256-verified cache;
  `providers/statsbomb_open_manifest.py` records a machine-readable
  snapshot manifest; `jobs/fetch_statsbomb_open.py` populated the full,
  real, pinned Premier League 2015/16 season (762 files, ~1.14 GB,
  hash-verified) used as the evidence base for every classification below.
- **Compliance**: `providers/statsbomb_open_policy.py` marks StatsBomb
  evidence `internal_only` for Block 20C -- StatsBomb's User Agreement is
  materially stricter than Wyscout's CC BY 4.0 and its commercial-use
  implications for derived analysis remain an open product/legal question,
  not resolved by this repository.
- **Mapping**: `providers/statsbomb_open_mapping.py` accounts for all 194
  real `METRIC_CATALOG_V2` identities (190 provider mappings + 4
  provider-out-of-scope, identical out-of-scope set to Wyscout's) --
  65 DIRECT, 45 DERIVABLE_READY, 48 DERIVABLE_METHODOLOGY_PENDING, 15
  REQUIRES_MODEL, 12 UNSUPPORTED, 5 AMBIGUOUS. The adapter-safe subset
  (DIRECT + DERIVABLE_READY) is **110 identities** -- larger than Wyscout's
  77, reflecting StatsBomb's genuinely richer event vocabulary (dedicated
  `Carry`/`Pressure`/`Ball Recovery`/`Dispossessed`/`Miscontrol` event
  types, player-attributed `Block`/goalkeeper events, native
  `pass.goal_assist`/`statsbomb_xg`), verified per-metric against the real
  full season, never assumed.
- **Four hard semantic questions resolved with full-season evidence**:
  cards must come from the lineup file's `cards` array (not `Foul
  Committed` alone -- 15% of real carded incidents are `Bad Behaviour`-
  sourced and invisible to the old adapter); saves/goals_conceded/
  shots_on_target_faced have a corrected, exactly-arithmetic-validated
  derivation (the old adapter undercounts saves by 3.6%); `assists` is
  DIRECT from `pass.goal_assist` (contradicting the old adapter's
  cross-event-reconstruction claim); `minutes` stays
  DERIVABLE_METHODOLOGY_PENDING -- lineup position intervals are real but
  their boundaries do not cleanly reduce to a single deterministic rule,
  verified against real edge cases, not assumed either way.
- `football-intelligence-audit-statsbomb-mapping` re-derives every
  regression count above from the real pinned cache and PASSES.

No `NormalizedObservation` emission, database write, or user-facing
exposure happened in Block 20C.1 or 20C.2a.

### Block 20C.2b — certified StatsBomb Open adapter

`data_mesh/adapters/statsbomb_open.py` was rewritten (same file, no
parallel second adapter) to emit `NormalizedObservation` rows for exactly
the 110 adapter-safe identities, using `adapter_safe_mappings()` as the
sole emission allowlist (validated at import time and at every observation
construction). It consumes already-loaded `MatchBundle`s (match summary +
events + lineups) -- no HTTP, no filesystem access, no database.

Every Block 20C.1/20C.2a semantic finding is now implemented: the lineup
file is the authoritative participation universe (starters/used subs get
real performance data including legitimate zeros; unused substitutes get
only roster-membership facts, never a fabricated performance zero; players
referenced only by an event and absent from the lineup get nothing at
all); cards come exclusively from the lineup file's `cards` array; saves/
goals_conceded use the full certified Goal Keeper type set;
`pass.goal_assist` drives `assists`; own-goal events never touch a
player's `goals`; team `goals_for`/`goals_against` always come from the
native match score; `match_status`/`home_score`/`away_score`/etc. are read
natively rather than synthesized; team/competition `name` facts moved into
`entity_identity_hints`, no longer emitted as a metric with no catalog
identity. `minutes`/`minutes_per_appearance` remain unimplemented, exactly
as certified. `providers.statsbomb_open_policy.STATSBOMB_INTERNAL_ONLY` is
asserted at the season entry point.

**Legacy Coverage Lab compatibility**: `jobs/run_zero_cost_coverage.py`
(Block 14/15, live generic probe against Bundesliga 2023/24) and
`jobs/collect_validation_snapshot.py` (Block 16, FIFA World Cup 2022
validation snapshot) both depend on the pre-existing adapter's generic,
any-competition `find_competition_season`/`parse_match_list`/
`parse_match_events` functions -- entirely outside Block 20C's certified
Premier League 2015/16 scope. Rewriting their semantics was not part of
this block's objective; those three functions are preserved byte-for-byte
(internals renamed `_legacy_`/`_LEGACY_`-prefixed so they can never be
accidentally reused by the certified path), in a clearly separated,
documented section of the same module.

**Real full-season audit** (`football-intelligence-audit-statsbomb-adapter
--cache-dir data/cache/statsbomb-open`, zero network calls): 643,628
observations across 380 matches / 20 teams; 110/110 adapter-safe
identities produced real observations, 0 unexpected, 0 conflicting
duplicates, 0 participation-universe violations. Every acceptance
invariant passed: native score 988 (shooter) + 38 (own goals) = 1026 with
zero residual; assists 669 exactly matching `pass.goal_assist`; cards
1,203 (lineup-authoritative) vs. 1,015 the old Foul-Committed-only rule
would have produced; saves 2,277 (full type set) vs. 2,194 the old
`"Shot Saved"`-only rule would have produced.

No canonical ingestion, entity resolution, or reconciliation exists yet.
StatsBomb evidence remains `internal_only` until the commercial-use
compliance question is explicitly resolved by a product/legal decision
this repository does not make. See `docs/STATSBOMB_METRIC_MAPPING.md` for
the full evidence trail.

## Block 20D — Entity Resolution & Reconciliation V2

### Block 20D.1 — real multi-source entity resolution diagnosis (diagnosis only)

Audited the V0 entity resolver (`data_mesh/entity_resolution.py`,
`data_mesh/pipeline.py`) against the two now-certified historical adapters
and found it could not resolve either: team resolution depended on an
`entity_type == "team", metric_name == "name"` observation neither
certified adapter emits (identity lives only in `entity_identity_hints`
now); `COMPETITION_MAPPINGS` had no `wyscout-open`/`statsbomb-open`
entries at all; and nothing in `NormalizedObservation` distinguished a
metric's Metric Catalog granularity, so `saves`/player_match and
`saves`/goalkeeper_match -- both projecting to `entity_type == "player"`
-- were information-theoretically indistinguishable once resolved.

Empirically investigated the real Wyscout Open x StatsBomb Open Spain/La
Liga 2017/18 overlap directly against both providers' real cached data.
**Finding, stated precisely because it is easy to get wrong**: Wyscout's
Spain 2017/18 file is a genuine full season (380/380 matches). StatsBomb's
"La Liga 2017/18" file is **not** a partial league season -- it is all 36
of one club's matches: **Barcelona 2017/18, 36 of Barcelona's 38 league
matches** (2 fixtures StatsBomb does not carry: Málaga v Barcelona
2018-03-10, Levante v Barcelona 2018-05-13). All 36 StatsBomb matches have
an exact-date Wyscout counterpart; 20 real opponent/team identities are
represented; zero date mismatches. This description -- "Wyscout La Liga
2017/18 full season x StatsBomb Barcelona 2017/18, 36 matches" -- must be
used verbatim; "StatsBomb's partial La Liga 2017/18" is not an accurate
characterization of the real data and must never be written that way.

Also found, empirically, a real Wyscout source-data defect: some fields in
the official Figshare `teams.json`/`players.json` files (`name`,
`officialName`, `firstName`, `lastName`) are JSON-escaped twice for
non-ASCII characters -- after one normal `json.loads()`, the resulting
string still contains the literal `\uXXXX` text sequence instead of the
intended character (verified at the raw-byte level, e.g. `"Atlético
Madrid"` should read "Atlético Madrid").

No repository files were modified in this diagnosis.

### Block 20D.2 — Entity Resolution V2 foundation

Implemented the foundation the 20D.1 diagnosis identified as missing,
purely additively -- every existing V0 function and the real
Football-Data.co.uk x OpenFootball ENG_PL 2025/26 baseline (380 matches,
20 teams, 1,140/1,140 agreed match-fact decisions, 0 conflicts, 0
unresolved, idempotent) are unchanged and re-verified passing. Full design
and evidence trail: [`ENTITY_RESOLUTION_V2.md`](ENTITY_RESOLUTION_V2.md).

Summary of what changed:

- `NormalizedObservation` gained an explicit `metric_granularity` field.
  Both certified adapters now set it on every emitted observation
  (verified: `saves` is emitted at both `player_match` and
  `goalkeeper_match`, and the two are now distinguishable). Legacy,
  pre-Metric-Catalog-V2 code paths (each adapter's Coverage-Lab-era generic
  probe functions) keep defaulting it to `None` -- not upgraded, not
  removed, per the same "preserve legacy behavior" discipline as every
  prior Block 20 adapter change.
- A narrow, Wyscout-specific double-escaped-Unicode text repair
  (`providers/wyscout_open_text.py`) fixes the real defect found in
  20D.1 -- deliberately not folded into the generic
  `normalize_team_name()`, since it repairs one provider's raw field
  encoding, not a name-comparison heuristic.
- Two real Spanish team-name convergence gaps found via an empirical
  collision check across the 20 real ESP_LL Wyscout/StatsBomb team names
  (beyond the "RC Deportivo" case anticipated going in): "Celta Vigo" vs
  "Celta de Vigo", and "Levante UD" vs "Levante". Fixed via two new
  `_TEAM_STOPWORDS` entries (`rc`, `ud`) and a narrow, documented
  `_SPANISH_SHORT_NAME_ALIASES` table -- all 20 ESP_LL team names from both
  providers now converge to one identity, verified empirically, not
  assumed.
- Real `wyscout-open`/`statsbomb-open` `CompetitionMapping` entries for
  ENG_PL, plus prepared-but-not-yet-emitted ESP_LL entries -- both scopes
  using each provider's real verified provider-native numeric competition
  identifiers (Wyscout `competitionId=364`/795, StatsBomb
  `competition_id=2`/11), never a guessed or internal canonical value.
- `cluster_match_dates()`'s adjacent-pair-chaining bug fixed: a cluster is
  now bounded to its own representative date, so it can no longer
  transitively span more than `tolerance_days` across three or more close
  dates.
- A new, purely additive module, `data_mesh/entity_resolution_v2.py`:
  `logical_fact_key()` (a granularity-safe logical fact identity builder --
  different matches, different seasons, and different granularities can
  never collapse into one key), a V2 source-local team/match index with
  conflict detection built directly from real `entity_identity_hints`
  (`build_team_index_v2_from_observations`/
  `build_match_index_v2_from_observations`/`resolve_team_v2`/
  `resolve_match_v2`, raising `IdentityConflictError` rather than silently
  picking one of two contradictory mappings), and the player-identity
  crosswalk **contract** (`PlayerCrosswalkEntry`/`PlayerCrosswalk`/
  `resolve_player_v2` -- no entries populated here, no name-only
  resolution, `UNRESOLVED` without an explicit validated entry).

**Completion pass** (re-opened after the initial 20D.2 implementation was
found PARTIAL): both certified adapters now emit the full identity-hint
contract -- `team_external_id`/`team_name`, `home_team_external_id`/
`home_team_name`, `away_team_external_id`/`away_team_name`,
`player_external_id`/`player_name` -- narrowly threading an optional
`teams_payload` parameter into the Wyscout adapter (StatsBomb's own match
summary and lineup file already carried team/player names). The V2 index
reads these hints directly and never depends on `entity_source_id`'s
composite `"{match_id}:{team_id}"` shape. `COMPETITION_MAPPINGS`'
`wyscout-open`/`statsbomb-open` ENG_PL entries were corrected from the
canonical `"ENG_PL"` code (not provider-native) to each adapter's real
numeric id, matching the same discipline already applied to the ESP_LL
entries. `wyscout-open` was also added to
`test_real_data_source_policy.py`'s approved-provider allowlist, reviewed
and documented as an acquisition/registration approval (matching
`statsbomb-open`'s existing precedent), never a canonical/production
promotion decision -- see `docs/ENTITY_RESOLUTION_V2.md` for the full
review. Full detail on every completion-pass change:
[`ENTITY_RESOLUTION_V2.md`](ENTITY_RESOLUTION_V2.md).

**Not done in this block** (by design -- see "Do NOT" list in the block's
own task record): no Spain/ESP_LL scope generalization of either adapter,
no execution of the real Wyscout x StatsBomb rich overlap reconciliation
(20D.3), no change to reconciliation grouping or semantic comparison
policy (`reconcile_metric()` untouched; `resolve_and_reconcile()`'s
grouping still keys on `(logical_key, entity_type, metric_name)` without
`metric_granularity` -- each `NormalizedObservation` already carries its
own `metric_granularity` through unchanged into that grouping, so nothing
is lost, but two observations at different granularities that happen to
share a `(logical_key, entity_type, metric_name)` are not yet grouped
separately; that is Block 20D.4's job), no DB ingestion, no fuzzy or LLM
player matching, no automatic player crosswalk population, and no change
to `STATSBOMB_INTERNAL_ONLY`.

**Review-fix pass and micro-audit** (re-opened twice more after the
completion pass): four independent-review findings were closed --
`_emit()`'s internal dedup/conflict identity now includes
`metric_granularity` (previously only `(source_code, entity_type,
entity_source_id, metric_name)`, unable to distinguish `saves`/player_match
from `saves`/goalkeeper_match); `PlayerCrosswalkEntry` now enforces its own
documented minimum evidence bar at construction time (non-blank
`team_context_key`, at least one non-blank `shared_match_key`) instead of
merely documenting it; `home_away`'s Metric Catalog granularity was
corrected from `"match"` to `"team_match"` (a real classification error
that forced a hand-maintained entity-type override in both adapters and
both audit jobs, now removed, with the full 194-identity accounting
re-verified exact for both providers); and `logical_fact_key()` /
`build_match_index_v2_from_observations()` now treat a blank string
exactly like a missing one everywhere required context is checked.

The micro-audit that followed found the two real-cache audit jobs
themselves (`jobs/audit_wyscout_adapter.py`,
`jobs/audit_statsbomb_adapter.py`) still projected identity coverage
through `(metric_name, entity_type)` -- the exact same blind spot `_emit()`
had, capable of certifying full 77/77 or 110/110 coverage even if
`goalkeeper_match` `saves` was never actually emitted. Fixed: both audits
now key coverage and duplicate/conflict detection directly on the real
`(metric_name, metric_granularity)` field, with a new
`no_missing_metric_granularity` check. Re-running both audits against the
same full real caches Block 20B.2b/20C.2b originally certified against
(found in sibling worktrees, no new downloads) gave real, current, exact
totals under the corrected contract: **Wyscout 412,609 observations**
(net +765 vs. the historical 411,844 -- exactly the newly-emitted
`goalkeeper_match` `saves`) and **StatsBomb 644,396 observations** (net
+768 vs. the historical 643,628), both still 77/77 and 110/110
adapter-safe identities, this time genuinely proven via
`metric_granularity`-aware logic rather than the old projection. StatsBomb's
independently-recomputed `saves` count stayed exactly 2,277 (not doubled),
confirming the audit's own save-total arithmetic was also corrected to
count each real save once. Also bumped both adapters' `SEMANTIC_VERSION`
(`wyscout-open-v0.1` -> `v0.2`, `statsbomb-open-v0.2` -> `v0.3`): this
pass changed observable emission semantics, so old and new observations
must not share a provenance version. Full detail:
[`ENTITY_RESOLUTION_V2.md`](ENTITY_RESOLUTION_V2.md).

## Block 20D.3 -- Rich Overlap Enablement

Enabled one real, rich, same-competition/same-season overlap between
Wyscout Open and StatsBomb Open (ESP_LL/La Liga 2017/18) and built the
first REAL deterministic `PlayerCrosswalk` population from it. This block
prepares evidence for Reconciliation V2; it does not implement
Reconciliation V2 itself (no change to `reconcile_metric()`, no
granularity-aware reconciliation grouping, no DB writes).

**Scope generalization.** Both certified adapters were hard-coded to a
single scope (Wyscout ENG_PL 2017/18, StatsBomb ENG_PL 2015/16). A new
`data_mesh/adapters/scope.py` module adds a small frozen `AdapterScope`
dataclass (`canonical_competition_code`, `season_label`,
`provider_competition_id`, `provider_season_id`) and a `ScopeMismatchError`.
Every certified top-level adapter function now accepts an optional
`scope: AdapterScope = DEFAULT_SCOPE` keyword-only parameter (omitting it
preserves the exact original ENG_PL behavior) and validates each real
per-match record's own native competition/season id against the declared
scope immediately after parsing it, before any observation is emitted --
refusing a mixed-scope batch outright rather than silently accepting or
misattributing part of it. No copy-pasted `wyscout_spain_adapter.py`/
`parse_spain_season_v2()` was created. Wyscout's real Figshare file-naming
convention (`matches_England.json` vs `matches_Spain.json`) is handled by a
small `_SCOPE_FILE_LABELS` lookup used only for `source_reference`
provenance strings. **No `SEMANTIC_VERSION` bump for either adapter**: the
real full-cache ENG_PL audits were rerun after generalization and produced
byte-identical totals to the pre-generalization baseline (Wyscout
412,609/77-77, StatsBomb 644,396/110-110, both `all_passed=True`) --
observable transformation semantics did not change, only became
parameterized.

**Real ESP_LL evidence, verified before coding acceptance logic.** All of
the block's "known evidence to verify" claims were confirmed exactly
against real, freshly-loaded cached data: Wyscout ESP_LL 2017/18
(competitionId=795, seasonId=181144) is 380 matches / 20 teams, fully
consistent; StatsBomb's ESP_LL open-data scope (competition_id=11,
season_id=1) is 36 matches, all involving Barcelona (20 distinct teams
overall across those 36 matches); the real match overlap resolved through
Block 20D.2's V2 identity contract (`build_team_index_v2_from_observations`
/ `build_match_index_v2_from_observations` / `resolve_team_v2` /
`resolve_match_v2` -- never `entity_source_id` parsing) is exactly 36
shared canonical matches, 0 date mismatches, and exactly 2 Wyscout-only
Barcelona league fixtures with no StatsBomb counterpart at all (Malaga vs
Barcelona 2018-03-10, Levante vs Barcelona 2018-05-13) -- matching every
expected fact with zero contradictions. All 20 real La Liga team identities
converge deterministically across both providers with no fuzzy matching.
No cross-source date-tolerance clustering was wired into V2 in this block
(remains deferred to 20D.4, as in 20D.2).

**Player name normalization** (`data_mesh/player_name_normalization.py`,
new): Unicode NFKD accent folding, casefold, punctuation/separator
folding, whitespace collapsing -- deliberately narrower than
`normalize_team_name()`: token order is preserved (never reordered, unlike
club names) and no alias table, nickname dictionary, or fuzzy/edit-distance
equivalence is ever applied. A real, load-bearing finding during
implementation: Wyscout's certified `player_name` hint carries a **short
display name** ("L. Messi") while StatsBomb's carries the **full legal
name** ("Lionel Andres Messi Cuccittini") -- an exact-match join across the
two adapters' existing certified hints would have accepted almost nothing.
The crosswalk audit job builds a separate Wyscout full-name lookup
(`wyscout_full_names_by_id()`, from `players.json`'s `firstName`+
`lastName`, repairing Wyscout's verified double-JSON-escaped Unicode defect
at that provider boundary via `repair_wyscout_double_escaped_unicode()`
before generic normalization) used only for the crosswalk join -- the
certified adapter's own `player_name` hint is untouched and still correct
for its already-certified purpose elsewhere.

**Real player crosswalk** (`jobs/audit_wyscout_statsbomb_overlap.py`, new
job, local-only, no DB writes, no canonical promotion). A candidate pair is
accepted only when both sources independently evidence the same shared
canonical match, the same resolved canonical team, and the same exact
normalized player name (no name-only evidence, no missing-team evidence).
Ambiguity is never resolved by picking "most likely": one provider id
evidenced against more than one counterpart id is excluded from
acceptance entirely and counted separately (`ambiguous_one_to_many`/
`ambiguous_many_to_one`), as is a duplicate-name collision within one
`(match, team, name)` slot. Real run against the full real ESP_LL
scope (36 shared matches): **430 accepted pairs, 860 crosswalk entries
created**, every accepted pair independently verified via
`resolve_player_v2()` to resolve both provider ids to the same canonical
key (`resolution_success_count == accepted_pairs`), 0 crosswalk conflicts,
0 duplicate-name collisions, 0 inconsistent-name-evidence cases.
`unresolved_no_exact_name_counterpart` is large (~15k `(match, team, name)`
slots present on only one side) -- this is real, expected sample coverage
(most Wyscout squad/bench players across 380 matches never appear in
StatsBomb's 36-match Barcelona-only scope at all), not a defect.

**Crosswalk canonical key**: `overlap-player:{competition_code}:
{season_label}:{team_key}:{normalized_name}` -- deterministic,
source-independent, explicitly namespaced `overlap-player:` (never the
bare `player:<name>` global identity, never connected to
`football.players`). Requires resolved canonical team context, not name
alone; the same validated Wyscout/StatsBomb pair always resolves to the
same key; a collision is structurally detectable via the existing
`PlayerCrosswalk.add()` conflict machinery from Block 20D.2.

**Discovered contract gap (section 11 audit, real, not hypothetical): 4
real pairs evidenced under more than one resolved team context** within
the single ESP_LL 2017/18 scope -- e.g. Wyscout id 151 / StatsBomb id 6038
("John Guidetti"), evidenced under both Alaves and Celta de Vigo, matching
Guidetti's real January 2018 loan move between those two clubs; similarly
for Wyscout ids 3970, 3994, and 4332. Per the block's explicit instruction,
these 4 pairs were **not** packed into one `team_context_key`, not
arbitrarily assigned to one team, and not silently discarded -- they are
excluded from crosswalk population entirely and reported by name/id/team
context/match in the audit job's `multi_team_context_cases` output. The
current `PlayerCrosswalkEntry` contract (one `team_context_key` per entry)
was preserved as-is; a redesign to support multiple team contexts per
canonical player (e.g. one entry per team-context per player, or a
richer evidence-list contract) is left for explicit review before Block
20D.4, not decided here.

**Overlapping exact metric-identity inventory** (section 15, INVENTORY
ONLY -- no comparability claim, no value comparison, no reconciliation):
the real intersection of exact `(metric_name, metric_granularity)`
identities observed by both adapters within the 36 shared matches is 65
identities. Block 20D.4 owns everything downstream of this list:
reconciliation grouping, semantic comparability, tolerances,
provider-native-vs-derived comparison policy, source-independence policy,
conflict resolution, and how `STATSBOMB_INTERNAL_ONLY` propagates through
reconciliation.

**Not done in this block** (by design): no Reconciliation V2
implementation, no DB writes or V2 schema migration, no
`football.*`/`intelligence.*` writes, no production/canonical promotion,
no fuzzy/LLM player matching, no cross-league calibration, no change to
`STATSBOMB_INTERNAL_ONLY` (remains `True`) or to the Block 20D.2 DB
fail-closed `MetricGranularityNotPersistableError` boundary. `tests/
integration/test_real_snapshot_v2_idempotency.py` and related
(canonical loading into `football.*`) genuinely require PostgreSQL and
remain correctly `SKIPPED` (DATABASE_URL not configured) -- but see the
Block 20D.3 corrective pass below: the separate, DB-free `resolve_and_
reconcile()` regression this repository has always used to validate the
ENG_PL 2025/26 baseline was re-checked and does NOT require PostgreSQL;
an earlier version of this section conflated the two. (A) the real
Wyscout ENG_PL full adapter audit and (B) the real StatsBomb ENG_PL full
adapter audit were both rerun at final stable state and reproduced their
certified totals exactly.

### Block 20D.3 corrective pass -- Option C multi-team-context crosswalk (complete)

A follow-up implementation pass, requested after the diagnosis above was
accepted as correct: the 4 real multi-team-context pairs are no longer
excluded from the crosswalk. Diagnosis had already established, against
real evidence, that all 4 are genuine clean mid-season transfers, not data
defects -- John Guidetti (Wyscout 151 / StatsBomb 6038, Celta Vigo ->
Alavés), Alejandro Gálvez Jimena (3970 / 6924, Eibar -> Las Palmas), Miguel
Ángel Moyà Rumbo (3994 / 7069, Atlético Madrid -> Real Sociedad), and
Javier Fuego Martínez (4332 / 6751, Espanyol -> Villarreal). The previous
contract's single `team_context_key: str` field could only ever represent
one club per entry, so it structurally could not accept these 4 real
players without either silently packing two teams into one string,
arbitrarily picking one team and destroying the other's evidence, or
excluding them entirely (the choice actually made at the time, and
reported rather than hidden).

**`PlayerTeamContextEvidence`** (new,
`data_mesh/entity_resolution_v2.py`): an immutable
`(team_context_key, shared_match_keys)` pair with its own validation
(non-blank team, at least one non-blank match key, no duplicate match key
within one context -- fail-fast, never silently deduplicated).
`PlayerCrosswalkEntry.team_context_key`/`shared_match_keys` (both `str`/
flat `tuple[str, ...]`) are replaced by
`team_context_evidence: tuple[PlayerTeamContextEvidence, ...]` -- one
entry per team context, so a genuine transfer produces two (or more)
contexts under ONE `PlayerCrosswalkEntry`, never a second registry entry
and never a forced single-team choice. Validated at construction: at
least one context, contexts in canonical ascending `team_context_key`
order (callers must sort deterministically -- never silently re-sorted),
no duplicate team context, and no shared match key may appear under two
different contexts (a single real match can never evidence one player
under two different teams for the same provider pair).
`team_context_keys`/`shared_match_keys`/`shared_match_count` remain
available as properties, now derived purely from
`team_context_evidence` -- never a second stored source of truth. The
registry key is unchanged: `PlayerCrosswalk.entries` is still keyed by
`(source_code, provider_player_id)`, so one provider player id still
resolves to exactly one player identity, never one identity per club.
`resolve_player_v2()`'s confidence formula needed no code change --
`shared_match_count` already aggregates the total genuinely shared match
count across every context, deduplicated, never double-counted.

**Opaque `overlap-player-v2` canonical key** (`jobs/audit_wyscout_
statsbomb_overlap.py`'s `crosswalk_canonical_key()`): the previous
`overlap-player:{competition}:{season}:{team_key}:{normalized_name}`
format is retired -- it could never have supported a validated transfer
(team membership changing mid-season would have to change the player's
own identity key), and Block 20D.3's earlier diagnosis explicitly found
normalized-name uniqueness "collision-free in this sample only," not a
safe global identity component either. The new format,
`overlap-player-v2:{competition_code}:{season_label}:{digest}`, is built
from a SHA-256 hex digest (stdlib `hashlib`, deterministic across
processes -- never the built-in `hash()`, never a random UUID) of the
canonically ordered (sorted by `(source_code, provider_player_id)`),
pipe-delimited, VALIDATED provider refs the pair was actually accepted
against. Team context and normalized-name formatting deliberately do NOT
participate in the digest: a validated transfer must resolve to the same
key regardless of which team(s) back the evidence, and the key is
provider-order-independent (the same pair produces the same key
regardless of which provider is passed first). **This is explicitly not a
global canonical player id** -- never `football.players`, never
persisted, never user-facing; a future canonical-promotion decision must
map these provider refs to an independent football-player identity
rather than treating this overlap key as production identity. Because no
Block 20D.3 crosswalk key has ever been committed, persisted, or exposed,
the format change is a pre-commit correction, not a production migration
-- nothing outside this branch depended on the retired format.

**Name collision remains a resolution safety gate, never an identity
component.** The exact-normalized-name-per-slot check
(`inconsistent_name_evidence_cases`) is unchanged and still rejects a
pair whose evidence disagrees on name across any (match, team) slot,
including across a transferred player's multiple team contexts -- name
no longer participates in `canonical_player_key`, but a name
disagreement is still never resolved, only reported. Re-run against the
same real ESP_LL cache the collision audit remains **collision-free in
this sample only** (0 global duplicate normalized names, 0 same-team
duplicates, 0 same-team+match duplicates) -- this still must never be
read as a global "name is a safe player identity" claim.

**Real re-run against the full ESP_LL cache**: accepted pairs
**430 -> 434** (the 4 real transfers now included), crosswalk entries
**860 -> 868** (2 per accepted pair, unchanged ratio),
`resolution_success_count` **434 == accepted_pairs**, `crosswalk_
conflicts` **0**. Every one of the 4 transfer pairs independently
verified: `resolve_player_v2()` resolves both the Wyscout and StatsBomb
provider id to the identical `canonical_player_key`, each carries exactly
2 `PlayerTeamContextEvidence` contexts, every shared match belongs to
exactly one context, and no evidence was dropped or misattributed
(cross-checked against the raw Wyscout `teamsData[*].formation.lineup`
payload directly, not merely the adapter's own output). All other real
counts this block already certified are unchanged and re-verified: 380
Wyscout matches / 20 teams, 36 StatsBomb matches / 20 teams, 36 shared
canonical matches, 0 date mismatches, 20/20 team convergence, 65
overlapping exact metric identities -- no adapter code changed, so no
`SEMANTIC_VERSION` bump for either adapter.

**Ambiguity count discrepancy, investigated and resolved.** A prior
verbal summary of this block reported 1 one-to-many and 1 many-to-one
ambiguity; the real, current, machine-readable overlap audit reports
`ambiguous_one_to_many = 0` and `ambiguous_many_to_one = 0` against the
full real ESP_LL cache, both before and after this corrective pass. The
machine-readable audit is authoritative. Root cause, traced rather than
assumed: `tests/test_audit_wyscout_statsbomb_overlap.py` contains two
small, deliberately-constructed synthetic fixtures
(`test_one_wyscout_id_matching_multiple_statsbomb_ids_is_unresolved_
ambiguous`, `test_many_wyscout_ids_matching_one_statsbomb_id_is_
unresolved_ambiguous`) that each assert exactly `== 1` for their own
tiny 2-match unit-test scenario -- correct and expected for those unit
tests, which exist specifically to prove the ambiguity-detection code
path works, but unrelated to and never derived from the real 36-match
ESP_LL production data. The earlier summary's "1/1" almost certainly
conflated those unit-test fixture assertions with the real-data audit
output; no committed documentation in this repository ever stated "1
one-to-many ambiguity" as a real-data finding, so no doc text required
correction here beyond this explicit reconciliation.

**Deferred to Block 20D.4, unchanged by this pass**: Reconciliation V2
itself, granularity-aware reconciliation grouping, semantic comparability/
tolerance policy, DB V2 persistence migration, the deferred
cross-source date-tolerance clustering integration into V2, canonical
football-player promotion (including how/whether `overlap-player-v2`
keys ever map to a real `football.players` id), any user-facing StatsBomb
exposure, and any change to `STATSBOMB_INTERNAL_ONLY` (remains `True`) or
the `MetricGranularityNotPersistableError` fail-closed boundary.

## Block 20D.4 -- Reconciliation V2 (minimal, exact-only)

Implements the real, granularity-aware Reconciliation V2 the prior blocks
deliberately deferred -- deliberately minimal: no numeric tolerance
reconciliation, no cross-provider "best guess" winner selection, and
certification scoped to exactly one real, certified provider pair
(Wyscout Open x StatsBomb Open) at exactly the semantic versions this
block reviewed. Everything V0 already proves (the Football-Data.co.uk x
OpenFootball ENG_PL 2025/26 baseline: 380 matches, 20 teams, 1,140/1,140
agreed, 0 unresolved, idempotent) is completely untouched -- `resolve_and_
reconcile()`, `entity_resolution.py`, and `MODEL_VERSION =
"data-mesh-reconciliation-v0.1"` keep their exact existing behavior; every
V2 addition is a new, separate, additive code path.

### Granularity-safe reconciliation

`ReconciliationDecision` gained `metric_granularity: MetricGranularity |
None = None`, mirroring `NormalizedObservation`'s own field exactly. Without
it, a decision for `saves`/`player_match` and one for
`saves`/`goalkeeper_match` were information-theoretically indistinguishable
downstream of reconciliation -- the same risk Block 20D.2 closed for
observations, now closed for decisions. `reconcile_metric()` (the single
shared value-agreement implementation both V0 and V2 use -- never
duplicated) gained two new optional keyword parameters, `metric_granularity`
and `model_version`, both defaulted to reproduce V0's exact existing
behavior when omitted: `MODEL_VERSION` unchanged, `metric_granularity`
stays `None`. V2 passes both explicitly.

### `resolve_and_reconcile_v2()` -- the V2 entry point

A new, purely additive function in `data_mesh/pipeline.py`. It composes:

- `build_team_index_v2_from_observations()` / `build_match_index_v2_from_
  observations()` (Block 20D.2) for id-based team/match resolution --
  never requiring a `team.name` observation neither certified adapter
  emits.
- Bounded cross-source date-tolerance clustering, wired in for the first
  time: `build_match_date_clusters()`/`cluster_match_dates()` (the same
  primitive V0 already uses, Block 20D.2's bounded-span fix, reused
  unchanged) is computed once over the batch and threaded into `build_
  match_index_v2_from_observations()` (which gained an optional
  `match_date_clusters` parameter) so two providers reporting the same
  real fixture on adjacent dates converge on one canonical match, exactly
  like V0.
- `resolve_player_v2()` against an explicitly injected `PlayerCrosswalk` --
  never a global singleton, never name-only resolution. A missing
  crosswalk entry leaves that player `UNRESOLVED`, exactly like V0's
  interface-only `resolve_player()`.
- `logical_fact_key()` (Block 20D.2) for the grouping identity, so facts
  from different matches, seasons, or **granularities** can never collapse
  into one group merely because they share an entity or metric name.

A certified observation reaching this function with `metric_granularity=
None` is treated as a diagnostic failure (counted, reported, excluded from
every group) -- never silently folded into a legacy-shaped group.

### The comparability policy: provider-pair AND semantic-version scoped

`data_mesh/comparability_policy.py` (new): a `MetricComparabilityPolicy`
registry keyed on `(source_refs, metric_name, metric_granularity)`, where
`source_refs` is a canonically-ordered pair of `SourceRef(source_code,
semantic_version)`. Both the provider pair AND each source's exact
`semantic_version` (imported directly from each certified adapter's own
`SEMANTIC_VERSION` constant, never hard-coded) participate in the key --
comparability is a claim about how two *specific* providers' methodologies
relate to each other at exactly the emission semantics this block reviewed
real evidence against; a future adapter version bump automatically and
silently invalidates every entry (they stop matching), and a different
provider pair has zero entries by construction. Lookup is order-
independent (`comparability_policy(a, b, ...) ==
comparability_policy(b, a, ...)`).

Only three modes exist in this block: `exact`, `not_comparable`,
`methodology_pending`. No `tolerated_agreement`, no numeric tolerance, no
averaging, no approximate-disagreement winner selection -- all explicitly
deferred to Block 20D.5.

A dedicated real-data comparability audit (diagnosis-only, not committed)
measured actual per-entity value agreement across the certified 36-match
ESP_LL overlap for all 65 previously-inventoried identities, then this
block's implementation re-derived real per-source value distributions
(nonzero/true rates, not just the "100% empirical agreement" flag) before
seeding the registry -- "same catalog identity" and even "100% observed
agreement" are not by themselves sufficient evidence, especially for
sparse, mostly-zero metrics.

**10 identities certified `exact`** (real 100%-agreement across every
paired entity in the sample, backed by independent semantic evidence --
native/authoritative source fields or an explicitly verified derivation,
never the empirical count alone): `home_score`/match, `away_score`/match,
`round_name`/match, `started`/player_appearance, `goals`/player_match,
`non_penalty_goals`/player_match, `goals_for`/team_match,
`goals_against`/team_match, `home_away`/team_match,
`clean_sheets`/goalkeeper_match.

**6 identities deliberately withheld from `exact` despite 100% empirical
agreement**, because that agreement rested on only 1-6 real positive
examples in the certified sample -- too thin an evidentiary base to
certify, even though nothing contradicts it: `penalties_attempted`,
`penalty_goals`, `penalties_missed`, `red_cards` (player_match),
`red_cards` (team_match), `second_yellow_cards`. These remain
`methodology_pending`, available for promotion once a larger real sample
provides stronger evidence.

**12 identities certified `not_comparable`**: real, substantial, and/or
systematically one-directional disagreement (majority of real paired
entities disagree, and the disagreement is not random noise) indicating
the two providers measure genuinely different things under the same
catalog name -- the `passes_total`/`passes_accurate`/`pass_completion_pct`/
`pass_accuracy_pct` family (a known, documented StatsBomb-vs-Wyscout
pass-counting-scope divergence, present at both player and team
granularity and for goalkeeper `passes`/`distribution_accuracy_pct`),
`duels_total`/`ground_duels` (Wyscout consistently counts more "duels"),
`touches` (near-total disagreement), and `offsides` (systematically
one-directional).

**Everything else fails closed to `methodology_pending`**: the 25
identities with high-but-not-perfect empirical agreement (a real numeric-
tolerance question, deferred to 20D.5), representational (not factual)
mismatches (`status`'s vocabulary, `kickoff_at`'s timezone offset,
`venue_name`'s formatting), and any `(metric_name, metric_granularity)`
combination with no reviewed entry at all.

### Single-source facts are never gated by pairwise policy

A resolved fact group with only one objective source calls `reconcile_
metric()` directly -- `single_source`, exactly like V0 -- regardless of
whether that metric happens to be `not_comparable`/`methodology_pending`
for this provider pair. "No supported cross-provider comparison" is not
the same claim as "this source's observation is invalid" -- a lone
`touches` observation is still real, valid audit evidence even though
`touches` itself is certified `not_comparable` between these two
providers. Comparability policy is consulted **only** when an actual
cross-source comparison is being attempted (exactly 2 objective sources).
More than 2 sources fails closed to `methodology_pending` unconditionally
in this block -- N>2-provider comparison semantics are not invented here,
since only one certified two-provider pair exists.

`not_comparable`/`methodology_pending` decisions never call `reconcile_
metric()` at all (no value comparison is attempted); `candidate_value` is
always `None`, and raw per-source values plus semantic versions and the
policy lookup context are preserved in `evidence` for audit. If a single
source's observations within one resolved group carry inconsistent
`semantic_version` values (a real batch-composition anomaly, not expected
in practice), the group fails closed to `methodology_pending` with the
inconsistency recorded in `evidence` rather than silently picking one
version.

### Database: `UNIQUE NULLS NOT DISTINCT`

`database/migrations/20260820100000_add_data_mesh_v2_persistence.sql` adds
a nullable `metric_granularity` column to both `ingestion.
source_observations` and `ingestion.reconciliation_decisions`, and widens
both natural keys to include it. A plain `UNIQUE` constraint would have
broken legacy upsert idempotence the moment `metric_granularity` (nullable,
`NULL` for every legacy row) joined the key -- standard SQL treats `NULL`
as distinct from `NULL`. `UNIQUE NULLS NOT DISTINCT` (PostgreSQL 15+; this
repository targets PostgreSQL 17) is used instead: two legacy rows collide
exactly as before, while two rows with different non-`NULL`
`metric_granularity` values coexist as distinct facts.
`reconciliation_decisions`' `status` check constraint widened to include
`not_comparable`/`methodology_pending`. No backfill, no destructive
rewrite -- every existing row keeps `metric_granularity = NULL`, its
correct legacy value. `database/tests/015_data_mesh_v2_contract.sql`
proves both invariants (and cross-granularity coexistence) against a real
database; two pre-existing files whose `ON CONFLICT` targets predated this
widening (`database/tests/010_data_mesh_contract.sql`,
`database/fixtures/005_data_mesh_smoke.sql`) were updated to match the new
natural key, or they would have failed against the new schema.
`db.data_mesh_repository.MetricGranularityNotPersistableError` -- the
Block 20D.2 fail-closed guard that refused to persist any V2 observation
at all -- is removed now that the schema safely supports it.

### Real ESP_LL 2017/18 certification

`resolve_and_reconcile_v2()` was run against the full real certified
overlap (Wyscout ESP_LL: 416,407 observations, StatsBomb ESP_LL: 61,247
observations) with a real, freshly-rebuilt `PlayerCrosswalk` (434 accepted
pairs, 868 entries, all 4 real mid-season transfers -- Guidetti, Gálvez,
Moyà, Fuego -- each resolving both providers to one identical canonical
key across their 2 team contexts). All 36 shared matches and all 20 shared
teams resolved; zero date mismatches. `saves`/player_match and
`saves`/goalkeeper_match produced distinct, non-colliding decision groups,
proving the granularity-safe grouping holds under real data, not just
synthetic fixtures.

Across the full real batch, **403,291 total decisions**: 369,153
single-source, and for the 34,138 real two-source groups -- 3,664
`agreed` (every one of them one of the 10 exact-policy identities, zero
leakage), 6,376 `not_comparable` (every one of them one of the 12
not_comparable-policy identities, zero leakage), and 24,098
`methodology_pending`. This exact internal-consistency property (the real
`agreed` count sums precisely across the 10 exact identities' own real
paired-entity counts, and the real `not_comparable` count sums precisely
across the 12 not_comparable identities' own counts) is itself evidence
the policy gate has zero leakage in either direction. Re-running the same
batch twice produced byte-identical decisions (excluding `calculated_at`).
`STATSBOMB_INTERNAL_ONLY` remained `True` throughout; zero writes to
`football.*`/`intelligence.*` -- `resolve_and_reconcile_v2()` is a pure
in-memory function, exactly like V0.

**A real correctness defect found and fixed during this certification**:
the real run initially surfaced 6 additional overlapping `(metric_name,
metric_granularity)` identities at `player_season`/`goalkeeper_season`
granularity (`matches`, `appearances`, `starts`, `sub_appearances`,
`clean_sheets`/goalkeeper_season, `save_pct`/goalkeeper_season) that Block
20D.3's original 65-identity inventory never counted (that inventory's
counting method required a `match_external_id` hint, which season-level
facts structurally never carry). Investigating why revealed a real defect,
not just an uncatalogued identity: `statsbomb_open.parse_premier_league_
season()` -- despite its own docstring's stated assumption "requires every
match, not one" -- had no actual check that its `bundles` argument
genuinely covered a complete season, so it silently aggregated
`ESP_LL_SCOPE`'s real 36-of-38-match Barcelona-only Open Data window as if
it were a real full season for every player who appeared in it (both
Barcelona's own players, missing 2 real matches, and every opponent
player, whose true full 2017/18 season the 36-match cache barely samples
at all) -- structurally indistinguishable from Wyscout's genuinely
complete 380-match ESP_LL season aggregate for the same real person, with
no hint or provenance field recording the difference.

**Fix**: `AdapterScope` gained `season_scope_complete: bool = True`
(default preserves every previously-declared scope's exact behavior --
Wyscout ENG_PL/ESP_LL and StatsBomb ENG_PL are all genuinely complete
seasons). StatsBomb's `ESP_LL_SCOPE` -- the one genuinely incomplete scope
-- now declares `season_scope_complete=False`. `parse_lineup_
participation_observations()` gained an `include_season` parameter
(mirroring the identical existing pattern already used by `parse_
goalkeeper_observations()`), and `parse_premier_league_season()` derives
`include_season=scope.season_scope_complete` for both season-emitting
sub-calls -- the one call site that knows about this distinction; no
provider-specific conditional was added to reconciliation/pipeline code.
No match is faked as zero, no value is extrapolated, and no partial
aggregate is renamed as a full season -- the fact is simply never emitted
for an incomplete scope. `SEMANTIC_VERSION` bumped `statsbomb-open-v0.3 ->
v0.4` (a real observable-emission-semantics change, per this repository's
established convention), which automatically invalidates the
comparability-policy registry's `SourceRef` for any decision built from
the pre-fix adapter version.

After the fix: StatsBomb emits **zero** `player_season`/`goalkeeper_season`
observations for `ESP_LL_SCOPE` (down from the pre-fix 63,063 total
observations to 61,247); every real season-level decision in the ESP_LL
certification is now `single_source`, sourced exclusively from Wyscout's
genuinely complete season -- verified by real re-run, not asserted. The
certified full ENG_PL StatsBomb adapter audit (a genuinely complete
380/380-match scope, `season_scope_complete` stays `True`) is unaffected --
its 110/110 adapter-safe identity baseline is preserved exactly, since
`DEFAULT_SCOPE` keeps the default `True` and nothing about ENG_PL emission
changed.

**Deferred to Block 20D.5**: numeric tolerance reconciliation and a
`tolerated_agreement` status for the 25 deferred identities; re-auditing
the 6 thin-evidence rare-event identities against a larger real sample for
possible `exact` promotion; the `status` vocabulary / `kickoff_at`
timezone / `venue_name` normalization gaps; resolving the `passes`/`duels`
methodology divergence; the newly-found `player_season`/`goalkeeper_season`
overlap identities; any additional provider pair; canonical
`football.players` promotion; product exposure; the StatsBomb
compliance/`STATSBOMB_INTERNAL_ONLY` decision; and production
scheduling/automation. Block 20D.5's own closure review (below) determined
none of this list blocks Block 20 -- see
["Block 20D.5 -- Final Closure Checkpoint"](#block-20d5----final-closure-checkpoint)
for the disposition of each item.

## Block 20D.5 -- Final Closure Checkpoint

**Block 20 status: CLOSED / CERTIFIED.**

This is a documentation-only checkpoint. No adapter, reconciliation,
pipeline, or database code changed in Block 20D.5, and none was needed:
Block 20D.4's real ESP_LL 2017/18 certification (below) already satisfies
Block 20's actual objective -- proving the Data Mesh can acquire,
normalize, resolve, and reconcile evidence from multiple independent
historical/deep providers without disturbing the existing current/recent
V0 pipeline, without inventing unreviewed methodology, and without ever
silently promoting unvetted or restricted evidence to canonical/product
status.

Closing Block 20 does **not** claim the overall product is finished, that
every provider is product-enabled, or that every methodology question is
solved. It closes exactly the scope Block 20 set out to prove.

### Block 20 exit contract

**Supported**:

- multiple independent historical/deep providers supported through the
  Data Mesh;
- Wyscout Open + StatsBomb Open adapters certified against real evidence;
- exact `metric_granularity` preserved end-to-end, including through
  reconciliation grouping;
- team/match identity convergence certified via the id-based V2 index;
- deterministic `PlayerCrosswalk` certified on real overlap -- 434
  accepted player pairs / 868 entries, all 4 genuine mid-season transfer
  cases preserved via multi-team-context evidence;
- Reconciliation V2 certified for exactly the Wyscout Open v0.2 x
  StatsBomb Open v0.4 provider pair, at those pinned semantic versions;
- PostgreSQL V2 persistence certified (`UNIQUE NULLS NOT DISTINCT`,
  legacy rows unaffected);
- the V0 current/recent pipeline preserved and re-verified unchanged
  (`resolve_and_reconcile()`, `entity_resolution.py`,
  `MODEL_VERSION = "data-mesh-reconciliation-v0.1"`, the Football-Data.co.uk
  x OpenFootball ENG_PL 2025/26 baseline).

**Real ESP_LL certification** (canonical figures -- do not conflate with
the separate ENG_PL adapter-audit totals of 412,609 Wyscout / 644,396
StatsBomb observations cited earlier in this document, which are a
different scope):

| | Wyscout ESP_LL 2017/18 | StatsBomb ESP_LL 2017/18 (partial Open Data scope) |
| --- | --- | --- |
| Observations | **416,407** | **61,247** |
| Adapter-safe identities in the full contract | 77/77 | 110/110 |
| Identities legitimately emit-capable for this scope | 77 | **104** (110 minus the 6 season-level identities intentionally suppressed by `season_scope_complete=False`) |

Overlap:

- 36/36 shared canonical matches, 20/20 teams, 0 date mismatches;
- 434 accepted player pairs, 868 crosswalk entries, 4/4 real transfer
  players preserved with correct multi-team-context evidence;
- 65 legitimate shared match-scoped `(metric_name, metric_granularity)`
  identities;
- 0 legitimate shared season-level identities (StatsBomb's incomplete
  ESP_LL scope correctly emits none -- see "already safely resolved"
  below).

Reconciliation (`resolve_and_reconcile_v2()`, full real batch, byte-
identical on re-run):

- **403,291** total decisions;
- **369,153** `single_source`;
- **3,664** `agreed` (all within the 10 `exact`-policy identities, zero
  leakage);
- **6,376** `not_comparable` (all within the 12 `not_comparable`-policy
  identities, zero leakage);
- **24,098** `methodology_pending`;
- zero cross-granularity collapse (`saves`/player_match and
  `saves`/goalkeeper_match remain distinct decision groups throughout).

**Fail-closed contract** (structural, not a promise pending future work):

- an unknown or unreviewed cross-source comparison resolves to
  `methodology_pending`, never a guessed value;
- an unsupported source pair or semantic version falls through to
  `methodology_pending` by construction (the registry is keyed on pinned
  `(source_code, semantic_version)` pairs, never a live/auto-updating
  import);
- a known semantic divergence between providers is certified
  `not_comparable`, never averaged or silently picked;
- more than 2 objective sources fails closed to `methodology_pending`
  unconditionally -- N>2-provider semantics are not invented in Block 20;
- an incomplete season scope (`season_scope_complete=False`) cannot emit a
  full-season aggregate for any player, whether they belong to the
  under-sampled club or an opponent;
- a missing player crosswalk entry leaves that player `UNRESOLVED` --
  never a name-only or fuzzy fallback;
- no cross-source comparison ever produces a guessed consensus value.

**Research backlog -- not Block 20 blockers.** The following remain real,
legitimate future work, but none of them is required for Block 20 to be
considered correct or complete, and none is promised to be implemented on
any particular schedule:

- numeric tolerance reconciliation for the 25 identities currently
  `methodology_pending` on high-but-not-perfect empirical agreement, and
  a possible `tolerated_agreement` status to express it;
- re-auditing the 6 thin-evidence rare-event identities
  (`penalties_attempted`, `penalty_goals`, `penalties_missed`, `red_cards`
  player_match/team_match, `second_yellow_cards`) against a larger real
  sample for possible `exact` promotion;
- `status` vocabulary, `kickoff_at` timezone, and `venue_name`
  representational normalization;
- further `passes`/`duels` methodology research, should a future,
  independently reviewed reconciliation approach ever want to attempt it;
- any additional provider pair beyond the certified Wyscout Open x
  StatsBomb Open ESP_LL 2017/18 pair.

**Already safely resolved -- not open Block 20 defects.** Two items that
earlier Block 20D.4 text described as deferred were, in fact, already
closed by evidence and code already on `main`:

- the `passes`/`duels` provider-methodology divergence is not an
  unresolved gap -- it is already correctly and permanently represented as
  `not_comparable` in `comparability_policy.py`, backed by concrete real
  evidence (e.g. a real sampled pair of 253 vs. 291 passes for the same
  team in the same match), with zero leakage proven in the full real ESP_LL
  certification;
- the partial-StatsBomb-ESP_LL `player_season`/`goalkeeper_season` defect
  (a 36-of-38-match club-only Open Data window silently aggregating as if
  it were a genuine full season) was already found and fixed in Block
  20D.4 via `AdapterScope.season_scope_complete=False` -- verified by real
  re-run, not merely asserted.

**Product future -- explicitly out of Block 20's scope**, moved to the
global product closure track:

- canonical `football.players` promotion (including whether/how
  `overlap-player-v2` crosswalk keys ever map to an independent canonical
  player identity);
- user-facing Wyscout/StatsBomb exposure;
- production scheduling/automation for either historical/deep provider.

**Externally blocked**: the StatsBomb product/commercial-use compliance
question remains unresolved outside this repository.
`providers.statsbomb_open_policy.STATSBOMB_INTERNAL_ONLY` stays `True`;
Block 20 makes and claims no StatsBomb product-rights determination.

**Explicitly not claimed by Block 20**:

- cross-league strength calibration;
- current-season (e.g. 2026/27) player-depth coverage from either
  historical/deep provider;
- product rights for StatsBomb Open Data;
- a canonical, global player identity;
- user-facing multi-provider product exposure;
- full semantic equivalence across providers for any metric outside the
  10 identities certified `exact`.

An unrelated, pre-existing scheduled-job failure in the current/recent V0
sync lane (`ApiFootballResponseError: Your account is suspended`, an
external API-Football account/billing condition) was observed during the
Block 20D.5 closure review. It is not a Block 20 historical/deep
correctness regression and is out of scope for this checkpoint; it belongs
to the later global product/runtime closure review.
