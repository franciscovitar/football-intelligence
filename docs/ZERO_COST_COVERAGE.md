# Zero-Cost Coverage Lab

Block 14 evolved Block 13's reconciliation PoC into a real coverage
measurement tool. Block 15 deepens the two zero-auth *current* sources
(TheSportsDB event-stats/lineup, plus a new Football-Data.co.uk CSV
provider) to move the product's verified current coverage materially above
the Block 14 baseline, without shrinking the 48-metric target catalog. It
answers, for every metric Football Intelligence wants and every one of the
10 target competitions:

> Which free source can provide this metric, for this competition, at what
> freshness, how complete, and when was that last verified?

Objective data/statistics remain the core of Football Intelligence. This
block never shrinks the statistical scope to fit what free providers happen
to offer -- it measures the gap honestly instead.

## Target metric catalog

`analytics/.../coverage_lab/target_metrics.py` derives the catalog from the
existing statistical DTOs (`normalization.models`) via `dataclasses.fields()`
-- `MatchRecord`, `TeamMatchStatsRecord`, `TeamLineupRecord`,
`PlayerAppearanceRecord`, `PlayerMatchStatsRecord` -- plus an explicit
`advanced.*` namespace (currently `advanced.xg`) for metrics that don't have
a DTO field yet. This is what the product *wants*, never a duplicate,
hand-maintained list that could silently drift or shrink. Adding a new
`advanced.*` metric never requires a database migration: coverage rows key
on `metric_name` as free text.

**Block 16 update**: `target_metrics.build_target_metric_catalog()` is now
sourced from `metric_catalog.METRIC_CATALOG_V2` (`analytics/.../metric_catalog/`)
instead of deriving purely from the 5 normalization DTOs -- the target
catalog grew from **48 metrics** (denominator 480) to **127 metrics**
(denominator 1270) to represent the full statistical product spec, not just
what those 5 DTOs happen to carry. The original 48 keep the exact same
`(metric_name, granularity)` identity (never renamed); every number below
that still says "48" or "480" describes the pre-Block-16 catalog accurately
as historical record of what Block 14/15 measured against at the time, not a
live figure.

## Target competitions

`analytics/.../coverage_lab/target_competitions.py` reuses `CORE_LEAGUES` (6)
and the World Radar competition config (4) rather than declaring a third
list -- 10 total. Coverage is modeled for all 10 even when a source's
coverage is zero; a competition a source doesn't cover is a real, reportable
result (`not_probed` or `missing`), never silently dropped from the report.

## Coverage state model

Eight states (`analytics/.../coverage_lab/models.py`), because a simple
yes/no would hide real distinctions that matter:

| State | Meaning |
| --- | --- |
| `current_available` | Probed this run; the metric is present for essentially the whole sample, for a *current* source, and the probe verified the TRUE current season/period |
| `previous_season` | Probed this run, from a `current`-role provider -- but the probe only verified the latest *completed* season/period, not the true current one (Block 15) |
| `historical_only` | Probed; present, but the source is historical/deep -- it can never satisfy a *current*-data need, no matter how complete |
| `partial` | Probed; present for only part of the sample |
| `token_required` | The provider needs a token that isn't configured; deliberately not probed |
| `not_probed` | No live probe was attempted this run for this provider/competition (out of the bounded scope, or a transient probe error) |
| `missing` | Probed; the source structurally could report this but returned nothing for this competition |
| `unsupported` | The provider can never structurally report this metric, independent of any specific probe |

Only `current_available` satisfies a *current*-data need
(`satisfies_current()`). `historical_only` never does, even though the
underlying metric is genuinely supported; neither does `previous_season`,
even though the evidence can be completely real and complete -- verifying
the wrong season is not the same as verifying no season. `provider.
freshness_role` ("can this provider ever report current data") and
`ProbeResult.is_current_period` ("did THIS probe verify the true current
season, not just the latest completed one") are deliberately separate
signals in `engine.py`'s `_resolve_entry` -- conflating them was a real bug
in the initial Block 15 implementation (see "TheSportsDB season labels"
below).

Percentages are never blended: current, previous-season, and historical/deep
coverage are always reported as separate numerator/denominator pairs, never
combined into one misleading ratio.

### Product coverage vs provider diagnostics

`compute_coverage` (`engine.py`) produces one `CoverageEntry` per (provider,
competition, metric) combination -- real evidence about what any single
provider does, but the wrong denominator for the product question. Its row
count scales with provider count (e.g. 4 providers x 10 competitions x 48
metrics = 1920 rows), so adding a provider that supports nothing would make
a naive "numerator / all rows" percentage look *worse* even though nothing
about real coverage changed.

`product_coverage.py` answers the actual product question instead: "can
Football Intelligence cover this metric, for this competition, from ANY
free source of the relevant freshness role?" A requirement -- identified by
`(competition_code, metric.granularity, metric.metric_name)`, not bare
`metric_name` alone, since the same name can exist at two granularities --
is satisfied when AT LEAST ONE provider of that freshness role has a
satisfying state for it. The denominator is always
`target_metric_count x target_competition_count` (48 x 10 = 480),
independent of how many providers exist. Adding a provider that supports
nothing leaves this number exactly unchanged; adding a provider that covers
something new can only ever raise it.

The job report exposes three product-level fractions, all sharing the fixed
480 denominator and never blended into each other: `product_current_coverage`
(true current-period evidence only), `product_recent_season_coverage`
(`previous_season` evidence -- a `current`-role provider verified the latest
*completed* season, real but never current), and
`product_historical_deep_coverage` (StatsBomb-style historical/deep). The
provider-row-count evidence lives separately under
`provider_diagnostics.current_entries` /
`provider_diagnostics.historical_entries`. `missing_critical_current_metrics`
at the top level is
product-level (a gap key like `GER_BL1:match:home_score` means no current
provider covers it); the provider-qualified equivalent
(`football-data-org:GER_BL1:home_score`) lives under
`provider_diagnostics.missing_critical_current_metrics` as evidence, not as
the product-level answer. `CoverageEntry.granularity` is stored explicitly
(not inferred from the coarser `entity_type` bucket, which collapses
`player_appearance` and `player_match` into one value) so this grouping is
precise by construction rather than by incidental non-collision.

## Provider capability manifests

`analytics/.../coverage_lab/provider_capabilities.py` is a small, explicit,
documented table of what each provider can *structurally* ever report --
independent of any single live probe. Every entry has been verified against
a real payload during Block 14/15 implementation (see below); nothing is
guessed from documentation alone.

`supported_metrics` is keyed by `(metric_name, granularity)`, matching the
target catalog's true identity -- not bare `metric_name` (a Block 14 V0
simplification, corrected in Block 15). The same name can mean two different
things at two granularities: StatsBomb derives both a team-level
`shots_total` (a match rollup) and a player-level `shots_total` (one
player's own shots) from the same event log, and TheSportsDB's Free
event-stats endpoint only ever supports the team-level one. A bare-name key
would have silently claimed TheSportsDB supports player-level shot counts it
has never returned. `ProbeResult.metric_observed_counts` /
`metric_sample_sizes` in `engine.py` use the same tuple key, and
`target_metrics.build_metric_granularity_index()` provides the
`(entity_type, metric_name) -> granularity` lookup every probe needs to
build it (entity_type alone is ambiguous for "player": it could mean
`player_appearance` or `player_match`; the index resolves this from the real
catalog rather than guessing).

### TheSportsDB v1 Free (current, zero-auth)

**Match results** (unchanged from Block 13): `home_score`, `away_score`
(full), `status` (partial -- reports a boolean finished/not-finished
signal, not `MatchRecord.status`'s full vocabulary). `eventsseason.php`
runs for all 10 target competitions in Block 15 (previously Bundesliga
only), using a documented, per-competition league id
(`data_mesh/entity_resolution.py`'s `COMPETITION_MAPPINGS`) verified live
via `lookupleague.php?id=<id>` during implementation -- `all_leagues.php`
and `search_all_leagues.php` on the shared Free test key only ever return a
small curated subset, not a full searchable catalog, so ids for Argentina/
Portugal/Brazil/MLS were verified individually rather than discovered by
listing.

**Event stats** (`lookupeventstats.php`, Block 15): verified live to return
at most **5 stat rows per match** -- a real Free-tier cap, not a
documentation guess. A real finished Bundesliga match returned exactly:
"Shots on Goal", "Shots off Goal", "Total Shots", "Blocked Shots",
"Shots insidebox". Only the 4 with unambiguous, exact `TeamMatchStatsRecord`
semantics are mapped:

| TheSportsDB field | Target metric |
| --- | --- |
| `Shots on Goal` | `shots_on_target` (team) |
| `Total Shots` | `shots_total` (team) |
| `Blocked Shots` | `blocked_shots` (team) |
| `Shots insidebox` | `shots_inside_box` (team) |

`Shots off Goal` is deliberately **not** mapped to `shots_outside_box`:
off-target and outside-the-penalty-box are different classifications, not
the same statistic under a different name. All 4 mapped fields are
reliably present whenever the endpoint returns data at all, so they are
capability-mapped `full`, not capped like the lineup below.

**Lineups** (`lookuplineup.php`, Block 15): verified live to return at most
**5 player rows per match** (a real finished match returned exactly 5, all
one team). Real, useful evidence -- player identity (`idPlayer`/
`strPlayer`), `strPosition` -> `listed_position`, `strHome`, `strSubstitute`
-> `started` (true for confirmed starters, false for confirmed
substitutes), `intSquadNumber` -> `shirt_number` when present -- but never
provably a complete lineup (a real squad has ~18-23 rows). These 3 metrics
are capability-mapped `partial` **permanently**, regardless of any single
probe's observed/sample ratio, so `current_available` can never be claimed
from a structurally incomplete payload.

### OpenLigaDB (current, zero-auth)

Unchanged from Block 13: `home_score`, `away_score` (full), `status`
(partial), Bundesliga only.

### football-data.org (current, optional token)

Environment variable: `FOOTBALL_DATA_ORG_KEY`. **CI never requires this
token.** Without it, every football-data.org coverage row is
`token_required` -- never a failure, zero requests spent. Free tier only:
`home_score`, `away_score`, `status`. No deep player statistics are claimed
(the Free tier does not expose them). Verified: base URL
`https://api.football-data.org/v4`, `X-Auth-Token` header, 10
requests/minute free-tier limit, `GET /v4/competitions` and
`GET /v4/competitions/{code}/matches` endpoints.

`status` is capability-mapped `partial`, not `full`: the adapter only ever
proxies a cross-source finished/not-finished boolean (`FINISHED` ->
finished; `SCHEDULED`/`TIMED`/`IN_PLAY`/`PAUSED` -> not finished), never the
provider's full status vocabulary. `SUSPENDED`/`POSTPONED`/`CANCELLED`/
`AWARDED` and any unrecognized value produce no status observation at all
(missing, never a guessed `not_finished`) -- the same discipline
TheSportsDB's adapter already applies to its own status vocabulary.

**Token-present path actually probes matches, not just the competitions
catalog.** A `GET /v4/competitions` response alone is discovery evidence --
it proves a competition is *listed*, not that its match facts were
fetched -- so a token-present run also confirms which of an explicit,
reviewed table of football-data.org competition codes
(`data_mesh/entity_resolution.py`'s `COMPETITION_MAPPINGS`, e.g. `BL1` ->
`GER_BL1`, `PL` -> `ENG_PL`, `PD` -> `ESP_LL`, `SA` -> `ITA_SA`, `FL1` ->
`FRA_L1`, `DED` -> `NED_ED`, `PPL` -> `POR_PL`, `BSA` -> `BRA_A`) are
actually present in that run's live response, then spends one bounded
`GET /v4/competitions/{code}/matches` request for the job's canonical probe
competition (GER_BL1/`BL1`, matching the other current sources). `ARG_LPF`
and `USA_MLS` are deliberately absent from that table: football-data.org's
Free tier does not expose Liga Profesional Argentina or MLS, and a mapping
with no live-confirmed entry is never treated as coverage. A target
competition that is mapped but not live-confirmed, or a matches request
that fails, stays `not_probed` for this run -- never fabricated.

### Football-Data.co.uk (current, zero-auth, Block 15)

Provider code `football-data-uk`. This is **structured file ingestion, not
scraping**: every file fetched is one of the site's own explicitly
published, directly-linked downloadable CSV files
(`https://www.football-data.co.uk/mmz4281/<season>/<division>.csv`), never
a presentation webpage. No authentication.

**Coverage**: 7 of the 10 target competitions publish a results file --
`ENG_PL`/`ESP_LL`/`ITA_SA`/`GER_BL1`/`FRA_L1`/`NED_ED`/`POR_PL`. The site
does not cover `ARG_LPF`, `BRA_A`, or `USA_MLS` at all; no mapping exists
for those three, and they are never fabricated as coverage.

**Season discovery**: the job computes two candidate 4-digit season codes
from the run date (e.g. in August 2026: `"2627"` then `"2526"`) and tries
the newer one first, falling back to the older one -- a real per-run HTTP
discovery, never an assumption that either file exists. Verified live
during implementation: a season/division combination with no published
file **redirects to an HTML "300 Multiple Choices" page** rather than
404ing, so the client checks the response actually starts with a `Div`
CSV header before treating it as real data, raising
`FootballDataUkNotFoundError` otherwise.

**Column semantics**: verified against the site's own published key
(`https://www.football-data.co.uk/notes.txt`) and real current-season CSV
downloads.

| CSV columns | Target metric |
| --- | --- |
| `FTHG` / `FTAG` | `home_score` / `away_score` (match) |
| `HS` / `AS` | `shots_total` (team) |
| `HST` / `AST` | `shots_on_target` (team) |
| `HF` / `AF` | `fouls` (team) |
| `HC` / `AC` | `corners` (team) |
| `HY` / `AY` | `yellow_cards` (team) |
| `HR` / `AR` | `red_cards` (team) |

Every row is a completed result (the site's own description: "Current
results (full time, half time)"), so `status` is set to `"finished"` for
every row -- `full` reliability, not a live-score proxy like the other
current sources. `HO`/`AO` (offsides) is a documented column but was not
present in any current-season file probed during implementation -- left
unmapped, never guessed. Odds/betting columns (the majority of each file's
columns) are never mapped into objective performance metrics.

**Serie A shots caveat**: the site's own acknowledgements name a different
original source for Italian match statistics (Gazzetta.it) than for most
other leagues (BBC, Flashscore, ESPN Soccer, Bundesliga.de, Football.fr).
Italian Serie A `shots_total`/`shots_on_target` observations carry a
distinct `semantic_version` (`football-data-uk-shots-ITA-v1` vs the default
`football-data-uk-v1`) so they are never blindly treated as directly
comparable to another league's shot counts from the same file format.

**No native identifiers**: the site publishes no numeric match or team id.
`entity_source_id` values are deterministic composite keys built from
fields the CSV actually provides -- the raw team name for a team, and
`"{division}:{kickoff_date}:{home_team}:{away_team}"` for a match --
reproducible from real published data, not invented. Team-stat
observations carry a `name` identity hint (matching every other adapter's
convention) so they resolve through the *existing* `entity_resolution`
pipeline exactly like TheSportsDB/OpenLigaDB team names do; no bespoke
comparison logic.

### StatsBomb Open Data (historical/deep)

Role: **`historical_deep`**, never current. StatsBomb Open Data
(https://github.com/statsbomb/open-data) is StatsBomb's official public
release of static JSON files for research -- read only, no scraping, no
authentication, no hidden endpoints.

Verified live during Block 14 implementation against Bundesliga 2023/24
(`competition_id=9`, `season_id=281`, `competition_gender=male`):

- `data/competitions.json` lists 80 competition/season entries; located
  dynamically by exact `competition_name` + `season_name` + `male` match,
  never a hardcoded id.
- `data/matches/{competition_id}/{season_id}.json` published **34 of an
  expected 306** Bundesliga matches for that season -- a real subset, so
  match-level coverage correctly reports `partial`
  (`BUNDESLIGA_FULL_SEASON_MATCH_COUNT = 306`), not full historical
  coverage.
- `data/events/{match_id}.json` is a full event log (~3,800 events for one
  match). Every metric below has a verified event-field derivation:

| Metric | Derivation |
| --- | --- |
| `shots_total` / `shots_on_target` / `goals` | Count of `Shot` events; on-target = outcome in `{Goal, Saved}`; goal = outcome `Goal` |
| `advanced.xg` | Sum of `shot.statsbomb_xg` per player per match |
| `key_passes` | Count of `Pass` events with `pass.shot_assist == true` |
| `passes_total` / `passes_accurate` | Count of `Pass` events; accurate = `pass.outcome` absent (StatsBomb omits `outcome` for completed passes) |
| `interceptions` / `clearances` / `blocks` | Count of `Interception` / `Clearance` / `Block` events |
| `dribbles_attempted` / `dribbles_successful` | Count of `Dribble` events; successful = `dribble.outcome.name == "Complete"` |
| `tackles` | Count of `Duel` events where `duel.type.name == "Tackle"` |
| `fouls_committed` / `fouls_drawn` | Count of `Foul Committed` / `Foul Won` events |
| `yellow_cards` / `red_cards` | From `Foul Committed` events with `foul_committed.card.name` in `{Yellow Card}` / `{Red Card, Second Yellow}` |
| `saves` | Count of `Goal Keeper` events where `goalkeeper.type.name == "Shot Saved"` |
| `formation` / `started` / `shirt_number` / `listed_position` | From the `Starting XI` event's `tactics.formation` + `tactics.lineup` |

**Deliberately NOT derived** (no verified, reliable event-field mapping):
`minutes`, `duels_total`/`duels_won` (only `Tackle`-type duel semantics were
verified), `assists` (would require cross-referencing a shot-assist pass to
a goal outcome across two events -- not implemented in V0), `advanced.xa`.
These stay genuinely missing, never fabricated.

**Missing vs zero, rigorously**: a player is only credited a metric
observation -- including a real `0` -- when they are confirmed to have
appeared in the match (tagged on at least one event). Every appeared player
gets an explicit `0` for every count metric they never triggered (a
striker with zero tackles has `tackles = 0`, not a missing observation); a
player never mentioned in the event log has no observation at all. The same
applies to `started`: `true` for confirmed `Starting XI` members, `false`
for confirmed substitutes who appeared, and no observation at all for a
player never seen in the match.

**Request economics**: 1 (`competitions.json`) + 1 (`matches/...json`) + 2
(`events/{match_id}.json`, one small bounded deep sample) = 4 requests for
the whole StatsBomb probe.

## Coverage engine

`analytics/.../coverage_lab/engine.py` is a pure, deterministic state machine:
target metric x target competition x provider capability x live probe
result -> exactly one `CoverageEntry`. No network I/O. The precedence is:
unsupported > token_required > not_probed > (from the probe) missing >
partial > historical_only/current_available. This ordering is what
guarantees a historical source can never satisfy a current query and a
zero-observation probe can never be reported as coverage. Each entry stores
`granularity` explicitly (from the originating `TargetMetric`), because the
true requirement identity is `(metric_name, granularity)` -- the same name
can exist at two granularities (e.g. `shots_total` at both `team` and
`player_match`) -- not the coarser, lossy `entity_type` bucket that
`player_appearance` and `player_match` both collapse into.

`analytics/.../coverage_lab/product_coverage.py` is a second, equally pure
function that takes the full list of provider-level `CoverageEntry` rows and
computes the product-level union answer described above (see "Product
coverage vs provider diagnostics").

## Live probes and request budget

The CLI (`football-intelligence-zero-cost-coverage`) probes, per run:

- **TheSportsDB**: `eventsseason.php` for all 10 target competitions (1
  request each = 10), plus a bounded `lookupeventstats.php` sample for 3
  competitions (`GER_BL1`, `ENG_PL`, `ITA_SA` -- chosen to overlap with
  Football-Data.co.uk's coverage) and a bounded `lookuplineup.php` sample
  for 1 competition (`GER_BL1`) = 14 requests.
- **OpenLigaDB**: 1 request (Bundesliga, unchanged from Block 13).
- **StatsBomb Open Data**: 4 requests (unchanged from Block 14 --
  competitions + matches + 2 bounded event samples).
- **Football-Data.co.uk**: up to 2 attempts (newer season, older-season
  fallback) per covered competition x 7 competitions = up to 14 requests.
- **football-data.org**: 0 requests without a token (never required by CI);
  up to 2 if `FOOTBALL_DATA_ORG_KEY` is configured.

Planned total: 33 without a football-data.org token, 35 with one -- checked
against `--request-budget` (default and hard cap: **35**, the task's
explicit request budget) **before any network call**. Each provider's
*actual* request count is typically lower than its worst-case planned
count (e.g. Football-Data.co.uk only needs a fallback attempt for
competitions whose newer season file is not yet published).

### TheSportsDB season labels

`eventsseason.php` needs an explicit season string per competition, and the
format differs by competition: European leagues use a cross-year
`"YYYY-YYYY"` label, Argentina/Brazil/MLS use a single calendar year.

**Corrected in the Block 15 review pass.** The first implementation used
`THESPORTSDB_SEASON_BY_COMPETITION`, a hardcoded table picking whichever
season label happened to already have finished matches at implementation
time (e.g. `"2025-2026"` for 5 European leagues whose true `"2026-2027"`
season had not started yet) -- and reported that data as `current_available`.
That conflated "a season this provider can structurally report" with "the
season we actually verified is the current one": real evidence, wrongly
labeled. `run_zero_cost_coverage.expected_current_season(competition_code,
as_of_date)` replaces the hardcoded table with a computed, deterministic
derivation (calendar-year competitions: `str(as_of_date.year)`; cross-year
competitions: the Aug-May window containing `as_of_date`) -- verified live to
match TheSportsDB's own `strCurrentSeason` field for every target
competition. The job queries only this season; if it has produced no
finished match yet, the honest result is `missing`, not a silently-borrowed
prior season passed off as current.

Football-Data.co.uk's existing newer-then-older-season fallback already
carried the right signal without needing extra requests: `_probe_football_data_uk`
tags which season code actually succeeded, and `_build_probe_results` sets
`ProbeResult.is_current_period = (used_season == newer_code)` accordingly --
the engine reports `previous_season`, never `current_available`, whenever
the fallback (older) season is what was actually found.

## Reconciliation (TheSportsDB x Football-Data.co.uk)

Block 15 feeds both sources' observations through the *existing* Block 13
resolve-then-reconcile pipeline -- extracted into
`data_mesh/pipeline.py` (`resolve_and_reconcile`, `resolve_logical_key`,
`build_match_date_clusters`) so the Coverage Lab job and the original Data
Mesh PoC job (`run_data_mesh_poc.py`) share one implementation instead of
two copies of the same entity-resolution logic. Team names differing by
spelling (e.g. "Bayern Munich" vs "FC Bayern München") still converge on
one logical team through the same deterministic normalization Block 13
already proved; where both sources report the same metric for the same
resolved entity, agreement raises confidence and disagreement is retained
as an explicit `conflict`, never averaged. Where only one source reports a
metric (e.g. team-level shots, which OpenLigaDB/football-data.org never
report), the decision is correctly `single_source`. None of this writes to
`football.*` or auto-promotes anything.

**Team-match-scoped identity (corrected in the Block 15 review pass).**
`team.name` is a team-identity property -- one fact per team, ever. Every
other metric an `entity_type == "team"` observation can report (shots,
cards, fouls, formation -- every `TeamMatchStatsRecord`/`TeamLineupRecord`
field, derived from those DTOs via `dataclasses.fields()` so the set can
never drift, see `pipeline.TEAM_MATCH_SCOPED_METRIC_NAMES`) is a
**team-match-scoped** fact instead: Bayern's `shots_total` against Leipzig
and Bayern's `shots_total` against Dortmund are two different real facts,
not two observations of one fact. The first implementation resolved every
team-entity observation to the same bare `team:GER_BL1:bayern...` logical
key regardless of metric, which silently merged different matches' stats
into one (false) reconciliation group.

`resolve_logical_key` now routes team-match-scoped metrics through
`_resolve_team_match_scoped`, which produces a composite
`team-match:<canonical-match-key>:<canonical-team-key>` logical key instead.
TheSportsDB's event-stat observations only ever carry a provider-scoped team
id and match id (never a team name or full match identity) -- resolving them
still requires no provider-specific logic or fuzzy matching:
`build_source_local_indexes` builds a `(source_code, provider-scoped id) ->
canonical logical key` bridge once per reconciliation run from the
observations that DO carry full identity (the season-event `name`/match
rows already fetched for the same competition), and every team-match-scoped
observation from the same source resolves through that index.

## Persistence

`ingestion.coverage_snapshots` (new migration, `ingestion` schema, not
`football.*`), keyed on `(provider_id, competition_code, metric_name,
granularity, freshness_role)`. **Not** an extension of the existing
`ingestion.data_capabilities` table: that table is scoped per
`(provider, entity_type, metric_name)` with no competition dimension (it
summarizes core-league sync capability across all core leagues combined),
and altering its primary key/constraints would risk the write path
`sync_core_leagues.py` already depends on. A small, purpose-built table
keeps both concepts correct without duplicating logic -- see the migration
file for the full reasoning. Idempotent upsert on
`(provider_id, competition_code, metric_name, granularity, freshness_role)`.

## Future promotion contract (not implemented in Block 14)

Coverage Lab and the Block 13 reconciliation engine both stop short of
writing to `football.matches` / `football.team_match_stats` /
`football.player_match_stats`. A future promotion path must respect all of:

- a `conflict` decision never auto-promotes;
- the entity must be strongly resolved (not a PoC-scoped logical key);
- an exact, reviewed semantic metric mapping (not a name-string match);
- correct freshness (a `historical_only` row can never overwrite current
  state, and a stale current row can't silently overwrite a fresher one);
- single-source promotion requires an explicit, reviewed per-source,
  per-metric policy -- it is not a default.

Block 14 measures and documents this contract; it does not enable it.

## Web

`/sources` shows product-level coverage stats (current, previous-season, and
historical/deep, each its own `numerator/denominator` against the fixed
480-requirement target catalog, clearly separate from the raw provider-row
count) alongside a competition x
provider coverage matrix. Each matrix cell shows every non-zero state it
actually has (e.g. `2 ACTUAL · 1 PARCIAL · 45 NO SOPORTADO`), never a single
majority-derived verdict -- a provider that covers 2 of 48 metrics and
structurally lacks the other 46 must show both facts, not collapse to one
"NO SOPORTADO" badge that hides the 2 it does cover. This sits alongside the
existing Block 13 reconciliation health. No fake percentages are shown when
no coverage snapshot exists -- an honest empty state instead. Player/Team/
Rating pages do not consume Coverage Lab values.

The registered-providers table also discloses, per source, static documented
facts that never depend on any single live probe: cost/free status,
current/historical role, known response or file limits (TheSportsDB's 5-row
event-stats/lineup caps; Football-Data.co.uk's CSV-per-season nature), and
provenance (which documented API or published file the data comes from).

## Scheduling

`.github/workflows/zero-cost-coverage.yml` is `workflow_dispatch` only --
no cron. `FOOTBALL_DATA_ORG_KEY` is an optional secret; the job runs and
succeeds without it. No API-Football calls.

## Source policy (why StatsBomb Open Data and not scraping)

Football Intelligence prefers documented free APIs, explicitly open
datasets, and public feeds designed for programmatic use over scraping.
StatsBomb Open Data is an explicitly published, official open dataset
intended for exactly this kind of use. This block does not add FBref/
Sports-Reference scraping, Bundesliga.com scraping, CAPTCHA bypassing,
login automation, or reverse-engineered private APIs -- "publicly viewable"
is not the same thing as "an automated feed the publisher intends to
support."
