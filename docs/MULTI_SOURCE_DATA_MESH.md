# Multi-Source Data Mesh V0

Block 13 evolves Football Intelligence from a single-provider pipeline
(`provider -> normalize -> canonical DB`) into a multi-source mesh:

```text
many sources -> raw evidence -> source adapters -> normalized observations
             -> entity resolution -> reconciliation -> canonical domain
             -> analytics -> web
```

Objective statistics remain the foundation of the product. Qualitative
expert/fan opinion is a separate evidence lane and must never become the
source of an objective statistic or a quantitative performance value.

This document describes the target contract and the V0 PoC scope. It stays
a modular monolith + batch system: no microservices, no queues, no Redis, no
permanently running workers.

## Motivation

A single provider (API-Football) cannot be the only source of truth
forever: coverage gaps, cost limits, and single-point-of-failure risk all
push toward multiple independent sources. But adding a second provider
naively -- writing its payload straight into the canonical tables -- risks
duplicate entities, silently overwritten facts, and no way to tell which
source said what. Block 13 proves a safer path: every source's data crosses
the same boundary (raw -> normalized observation -> entity resolution ->
reconciliation) before it could ever reach the canonical domain, and V0
deliberately stops one step short of writing to `football.*` so the
reconciliation behavior can be reviewed first.

## Source categories

```text
objective_structured   -- structured JSON/API feeds (TheSportsDB, OpenLigaDB, API-Football)
objective_official     -- official competition/federation sources
objective_web          -- objective facts scraped/parsed from web pages
qualitative_expert     -- expert analysis/opinion (existing Perception Intelligence)
qualitative_fan        -- fan/community sentiment (existing Perception Intelligence)
```

Only `objective_*` source types may participate in objective-stat
reconciliation. The reconciliation engine rejects qualitative observations
defensively, even if a caller passes them by mistake -- that lane belongs to
Perception Intelligence and must never touch objective statistics.

## Observation contract

A `NormalizedObservation` (`analytics/.../data_mesh/models.py`) is one
source's fact claim about one entity/metric:

```text
source_code, source_type, entity_type, entity_source_id,
entity_identity_hints, metric_name, value,
observed_at, source_timestamp, source_reference,
ingestion_run_id, semantic_version
```

`entity_type` supports `competition`, `team`, `match`, `player` at minimum.
`metric_name` is an open string, not a fixed whitelist -- adding a future
metric (xG, xA, progressive passes, ...) never requires a schema change,
only a new adapter mapping.

**Missing vs zero**: a source that does not report a metric produces no
observation for it at all. A reported `0` is a real observation with
`value = 0`. The two are never conflated.

## Resolution policy

Entity resolution (`analytics/.../data_mesh/entity_resolution.py`) is
conservative and deterministic. No fuzzy/similarity-threshold matching and
no LLM resolution for objective data. When identity cannot be established
from strong, explicit evidence, the result is `UNRESOLVED` -- never a
guessed link.

- **Competition**: explicit configured mapping (`COMPETITION_MAPPINGS`),
  `(source_code, external_id) -> canonical_code`.
- **Team**: deterministic normalized-name identity. Names are NFKD-folded,
  casefolded, and a small, explicit stopword/alias table strips generic
  corporate-entity tokens (`fc`, `sv`, `tsg`, ...) and known cross-language
  spelling variants (`munich` -> `munchen`). This is a documented,
  reviewable transformation, not a similarity heuristic -- it is applied
  identically regardless of which two names are being compared. Two
  different providers' team IDs for the same real club converge on one
  logical key without any registry or stateful lookup.
- **Match**: resolved from canonical competition + resolved home/away team
  identity + season + kickoff date. `resolve_match` itself stays a pure
  function of exact inputs so its behavior is easy to test and audit; the
  day-level tolerance (`dates_within_tolerance`, `MATCH_DATE_TOLERANCE_DAYS`)
  is applied one layer up, in `_build_match_date_clusters` /
  `_resolve_and_reconcile` (`analytics/.../jobs/run_data_mesh_poc.py`). That
  step deterministically clusters every kickoff date seen for the same
  (competition, season, home team, away team) group -- using
  `cluster_match_dates()` -- and substitutes each date for its cluster's
  earliest date before calling `resolve_match`. Two providers reporting the
  same real fixture on adjacent dates therefore converge on one logical
  match identity regardless of which provider's observation is processed
  first; dates outside tolerance stay distinct fixtures.
- **Player**: interface/contract only in V0. `resolve_player()` is callable
  and typed today, but always returns `UNRESOLVED` -- no source in this PoC
  supplies corroborated player-level identity, and `UNRESOLVED` is always
  safer than an incorrect link. Strong future identity (normalized name +
  date of birth + team context) is a real, designed capability for a later
  block once player-level multi-source data exists.

Resolved logical keys (`team:...`, `match:...`) are PoC-scoped identifiers.
They deliberately do not point at `football.teams`/`football.matches` rows
-- V0 must not auto-link into the production canonical graph.

## Reconciliation policy

The reconciliation engine (`analytics/.../data_mesh/reconciliation.py`)
receives one or more observations for one entity/metric and returns exactly
one of four states:

- **`agreed`** -- two or more independent objective sources report the same
  value. Confidence increases with the number of agreeing sources.
- **`single_source`** -- only one source reported the value. A candidate
  value is still produced, but with a deliberately low, fixed confidence.
- **`conflict`** -- independent sources disagree. The candidate value is
  `null` by default; counting stats are **never averaged** just because two
  sources disagree (`shots_total = 11` vs `13` is a conflict, not `12`). A
  metric-specific priority rule (`source_priority: {metric_name:
  (source_code, ...)}`) may name an authoritative source for *display*
  purposes only -- the status still stays `conflict`, and every disagreeing
  value remains in the evidence. Source priority is metric-specific, not
  global: an official result source might be authoritative for scores but
  useless for player tackles.
- **`unresolved`** -- defensive/empty case (no objective observations at
  all for this entity/metric).

Every decision keeps `participating_sources`, `source_count`, and an
`evidence` payload (`values_by_source`, whether a priority rule applied)
so a human can audit exactly why a value was or was not trusted.

## Trust / confidence

| Status | Confidence | Rationale |
| --- | --- | --- |
| `agreed` | `0.60` base, `+0.10` per extra agreeing source, capped `0.95` | independent agreement is the strongest signal available |
| `single_source` | fixed `0.35` | one source is real evidence, but unverified |
| `conflict` | fixed `0.20` | disagreement is real; low confidence regardless of any priority rule |
| `unresolved` | `0.0` | no usable evidence |

## Missing vs zero (again, because it matters)

This rule shows up at every layer: adapters never coerce a source's missing
field to `0`; the reconciliation engine treats `0` and `None`/absence as
different things; and per-metric coverage reporting counts *reported*
metrics only. A source lacking a field means **missing**, never `0`.

## PoC scope (Block 13)

Two zero-cost, zero-auth-token providers, one overlapping competition
(Bundesliga), a tiny bounded live sample:

- **TheSportsDB v1 Free** (`https://www.thesportsdb.com/api/v1/json/123/`)
  -- official documented endpoints only, the published free test key `123`,
  no scraping. `GET eventsseason.php?id=4331&s=<season>` (the free tier caps
  results around 15 events per call, which conveniently keeps the PoC
  small on its own).
- **OpenLigaDB** (`https://api.openligadb.de/`) -- public, documented,
  unauthenticated. `GET getmatchdata/bl1/<season-start-year>`.

Exactly **2 live requests** per PoC run (1 per source): no pagination, no
per-team/per-match follow-up calls, no fixture backfill. The CLI enforces a
hard, pre-flight request budget (`--request-budget`, default `4`, hard-capped
at `15`) that is checked **before any network call**.

Both feeds return match results (home/away score, finished status) and team
names for the same real fixtures; neither exposes shots, possession, or
other detailed box-score stats for free, so the PoC's overlapping metric set
is deliberately small (`home_score`, `away_score`, match `is_finished`, team
`name`, competition `name`). The point is not to prove these two sources
cover every statistic -- it is to prove ingestion, normalization, entity
resolution, reconciliation, provenance, coverage measurement, and conflict
handling all work end-to-end.

Provider status vocabularies never cross the adapter boundary as the
normalized objective value: TheSportsDB's `strStatus` (e.g. `"FT"`) and
OpenLigaDB's `matchIsFinished` boolean are each mapped, per-source, onto a
shared `is_finished` boolean metric (`true`/`false`) before reconciliation
ever sees them. A status value with no verified, unambiguous mapping (e.g.
an unrecognized or postponed/cancelled TheSportsDB code) produces no
`is_finished` observation at all -- missing, never a guessed boolean. The
raw provider string is still preserved in the raw payload snapshot
(`--raw-dir`) for audit. This means two sources both reporting "finished"
now correctly reconcile as `agreed` instead of a false `conflict` caused
only by differing provider vocabularies.

Run it: `football-intelligence-data-mesh-poc --season 2025-2026 --raw-dir
<dir> --report <path> [--database-url <url>]`. See
`.github/workflows/data-mesh-poc.yml` (`workflow_dispatch` only, no cron).

## Known limitations

- Only Bundesliga is mapped for the PoC; other competitions need new
  `CompetitionMapping` entries (see below).
- Neither free source exposes detailed match stats (shots, possession,
  cards, ...), so V0's live overlap is limited to scores/status/names.
- Match date tolerance is day-level, not a genuine multi-day search. It is
  wired into the real pipeline and integration-tested (`cluster_match_dates`,
  `dates_within_tolerance`), but the live PoC run itself has not yet observed
  a real multi-day gap between the two sources for the same fixture.
- Player-level resolution is an interface-only contract; no player
  observations are produced or reconciled in V0.
- `ingestion.reconciliation_decisions` and `ingestion.source_observations`
  are audit/evidence tables only. They are never read by the production
  Player/Team/Rating pages, and this PoC never writes to
  `football.matches`/`football.team_match_stats`/`football.player_match_stats`.

## How to add a provider

1. Add a client under `analytics/.../providers/<name>.py` (mirror
   `thesportsdb.py`/`openligadb.py`: bounded retries, explicit timeouts, no
   scraping of undocumented endpoints).
2. Add an adapter under `analytics/.../data_mesh/adapters/<name>.py` that
   parses the provider's payload into `NormalizedObservation`s -- missing
   stays missing, never fabricate a metric the provider does not report.
3. Add a `CompetitionMapping` entry (or a team/player mapping, if needed) to
   `entity_resolution.py`.
4. Seed the provider code in `database/seeds/001_core_catalog.sql`.
5. Wire it into `run_data_mesh_poc.py` (or a dedicated job) with its own
   bounded request budget.

Block 14 followed exactly this recipe to add `football-data.org` (optional
token, current/live) and `statsbomb-open` (zero-auth, historical/deep) --
see [`ZERO_COST_COVERAGE.md`](ZERO_COST_COVERAGE.md) for both.

## Zero-Cost Coverage Lab (Block 14)

Block 13 proves reconciliation works. Block 14 answers a different, equally
important question: for every metric Football Intelligence wants, which
free source can supply it, for which competition, at what freshness, how
complete, and when was that last verified? It adds a provider-independent
target metric catalog (derived from the existing statistical DTOs, never a
shrinking duplicate list), a 7-state coverage model (separating
`current_available` from `historical_only` so a deep historical source like
StatsBomb Open Data can never be mistaken for current coverage), and a
bounded coverage-measurement job. Full detail:
[`ZERO_COST_COVERAGE.md`](ZERO_COST_COVERAGE.md).

## Future qualitative lane

A separate, future lane converges qualitative research into Perception
Intelligence without ever touching objective statistics:

```text
ChatGPT/web research
    -> Google Sheet perception inbox
    -> qualitative source adapter
    -> perception evidence
    -> Supabase
    -> Player/Team context
```

This lane must converge only at the insight/product layer. It must never be
allowed to replace or influence an objective statistical observation or a
reconciliation decision. Block 13 documented this intent; Block 14 adds the
real Sheet contract and pure validation DTOs (see
[`PERCEPTION_INBOX.md`](PERCEPTION_INBOX.md)) without building any Google
infrastructure. Actual Sheet -> Supabase ingestion remains future work.
