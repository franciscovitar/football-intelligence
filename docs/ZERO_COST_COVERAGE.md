# Zero-Cost Coverage Lab

Block 14 evolves Block 13's reconciliation PoC into a real coverage
measurement tool. It answers, for every metric Football Intelligence wants
and every one of the 10 target competitions:

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

## Target competitions

`analytics/.../coverage_lab/target_competitions.py` reuses `CORE_LEAGUES` (6)
and the World Radar competition config (4) rather than declaring a third
list -- 10 total. Coverage is modeled for all 10 even when a source's
coverage is zero; a competition a source doesn't cover is a real, reportable
result (`not_probed` or `missing`), never silently dropped from the report.

## Coverage state model

Seven states (`analytics/.../coverage_lab/models.py`), because a simple
yes/no would hide real distinctions that matter:

| State | Meaning |
| --- | --- |
| `current_available` | Probed this run; the metric is present for essentially the whole sample, for a *current* source |
| `historical_only` | Probed; present, but the source is historical/deep -- it can never satisfy a *current*-data need, no matter how complete |
| `partial` | Probed; present for only part of the sample |
| `token_required` | The provider needs a token that isn't configured; deliberately not probed |
| `not_probed` | No live probe was attempted this run for this provider/competition (out of the bounded scope, or a transient probe error) |
| `missing` | Probed; the source structurally could report this but returned nothing for this competition |
| `unsupported` | The provider can never structurally report this metric, independent of any specific probe |

Only `current_available` satisfies a *current*-data need
(`satisfies_current()`). `historical_only` never does, even though the
underlying metric is genuinely supported -- that is the entire point of
separating the two.

Percentages are never blended: current and historical/deep coverage are
always reported as separate numerator/denominator pairs, never combined
into one misleading ratio.

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

The job report exposes both concepts explicitly and never conflates them:
`product_current_coverage` / `product_historical_deep_coverage` (the
480-denominator product answer) and `provider_diagnostics.current_entries` /
`provider_diagnostics.historical_entries` (the provider-row-count
evidence). `missing_critical_current_metrics` at the top level is
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
a real payload during Block 14 implementation (see below); nothing is
guessed from documentation alone.

### TheSportsDB v1 Free / OpenLigaDB (current, zero-auth)

Unchanged from Block 13: `home_score`, `away_score` (full), `status`
(partial -- both report a boolean finished/not-finished signal, not
`MatchRecord.status`'s full vocabulary).

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

The CLI (`football-intelligence-zero-cost-coverage`) reuses Block 13's
Bundesliga `CompetitionMapping` for TheSportsDB/OpenLigaDB (current data),
adds the bounded StatsBomb deep sample above, and optionally probes
football-data.org if a token is configured (competitions catalog, then one
bounded matches request -- see above). Total planned requests:
`2 (current) + 4 (StatsBomb) + [2 if token]` = 6 or 8, checked against
`--request-budget` (default 8, hard-capped 20) **before any network call**.

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

`/sources` shows product-level coverage stats (current and historical/deep,
`numerator/denominator` against the fixed 480-requirement target catalog,
clearly separate from the raw provider-row count) alongside a competition x
provider coverage matrix. Each matrix cell shows every non-zero state it
actually has (e.g. `2 ACTUAL · 1 PARCIAL · 45 NO SOPORTADO`), never a single
majority-derived verdict -- a provider that covers 2 of 48 metrics and
structurally lacks the other 46 must show both facts, not collapse to one
"NO SOPORTADO" badge that hides the 2 it does cover. This sits alongside the
existing Block 13 reconciliation health. No fake percentages are shown when
no coverage snapshot exists -- an honest empty state instead. Player/Team/
Rating pages do not consume Coverage Lab values.

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
