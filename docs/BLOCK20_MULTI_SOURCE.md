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
