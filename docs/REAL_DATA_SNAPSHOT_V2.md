# Real Data Snapshot V2 (Block 18)

Block 16/17 already produced a real, single-source ENG_PL 2025/26 match/team
snapshot from Football-Data.co.uk (see `docs/STATISTICAL_MODEL_V2.md`'s "Real
season snapshot" section and `data/real/2025-26/README.md`). Block 18 turns
that into an **auditable, reconciled, reproducible** snapshot: it adds a
second, independent, public-domain current source (OpenFootball), runs both
through the existing Data Mesh resolve-then-reconcile pipeline, and reports
real coverage against the full, dynamic Metric Catalog V2 in a
machine-readable manifest. It does not change what `load_real_snapshot.py`
loads into `football.*` -- that remains the single already-trusted
Football-Data.co.uk source, unchanged.

## What we have

- **Match facts, fully real, for the whole completed season.** 380/380
  ENG_PL 2025/26 matches, 20/20 clubs, from Football-Data.co.uk's published
  `mmz4281/2526/E0.csv`.
- **A second, independent real source for the same matches.** OpenFootball's
  public-domain (CC0) `football.json` repository (`2025-26/en.1.json`), 380
  matches, 20 clubs, fetched and normalized the same way.
- **Real, measured cross-source agreement.** Running both sources through
  the existing `data_mesh.pipeline.resolve_and_reconcile` produces **1,140
  agreed decisions out of 1,140 real match-fact observations** (`home_score`,
  `away_score`, `status` for all 380 matches) -- both independent sources
  report identical results for every match. Zero conflicts on match facts,
  zero unresolved identities. This is concrete evidence the primary
  Football-Data.co.uk snapshot `load_real_snapshot.py` already loads is
  correct, not merely assumed correct.
- **20 real, documented team-name conflicts.** The two sources use different
  exact strings for the same real club (Football-Data.co.uk's short form,
  e.g. "Wolves", vs OpenFootball's official long form, "Wolverhampton
  Wanderers FC"). Both resolve to one logical team identity (see "Entity
  resolution" below) -- the mismatch is on the literal `name` string, not on
  which real club is meant, and is recorded as a real `conflict` decision,
  never silently picked or hidden.
- **Team-match statistics from Football-Data.co.uk only.** `shots_total`,
  `shots_on_target`, `fouls`, `corners`, `yellow_cards`, `red_cards` -- 4,560
  observations, correctly `single_source` (OpenFootball publishes no
  team-match statistics at all).
- **Zero player-level data of any kind.** Neither real source publishes it;
  see "Rich player data decision" below.

## What we still do not have

- Any domestic ENG_PL 2025/26 **player**-level statistics (shots, passes,
  defensive actions, minutes, or advanced metrics such as xG/xA at player
  grain).
- Team-level `possession_pct`, `passes_total`/`passes_accurate`,
  `shots_inside_box`/`shots_outside_box`, `blocked_shots`, `offsides`,
  `goalkeeper_saves`, or any expected-output (xG/xGA) metric for ENG_PL
  2025/26 -- Football-Data.co.uk's published columns do not include them,
  and OpenFootball publishes match results only.
- Cross-league strength calibration (unchanged, documented V1/V2
  limitation).

## Metric Catalog V2 coverage (this snapshot only)

Computed live from `metric_catalog.METRIC_CATALOG_V2` every run -- never a
hardcoded denominator that could drift from the real catalog. As of this
implementation the live catalog reports **194 identities** (154 raw, 40
derived) across all 9 grains; this number is read from the code, not fixed
in this document.

| | Count | Identities |
| --- | --- | --- |
| Catalog identities (total) | 194 | -- |
| Available from a real current source (this snapshot) | **9** | `home_score@match`, `away_score@match`, `status@match`, `shots_total@team_match`, `shots_on_target@team_match`, `fouls@team_match`, `corners@team_match`, `yellow_cards@team_match`, `red_cards@team_match` |
| Historical/deep only (StatsBomb Open Data, never current) | 22 | see `coverage_lab.provider_capabilities` |
| Unavailable | 163 | everything else -- overwhelmingly player-level (finishing, creation, progression, passing, 1v1, defence, ball-winning, aerial, goalkeeping) and team process/tactical (pressing, transition, build-up, set pieces, chance quality) |

These three figures are never blended into one percentage (per
`docs/ZERO_COST_COVERAGE.md`'s coverage-state discipline) -- "available now",
"only ever available from a historical/deep source", and "unavailable" answer
different questions and must stay legible separately.

**Player V2's twelve scoring dimensions** (Performance, Underlying
Performance, Finishing, Shot Generation, Creation, Progression, Passing, 1v1,
Defence, Ball Winning, Aerial, Goalkeeping) and **all fourteen Team V2
dimensions except Attack/Defence's most basic shot-count inputs** remain
`insufficient_data` for this real snapshot -- exactly as Block 16 already
found and Block 18 reconfirms with a second independent source, not a
smaller-scope re-measurement.

## Rich player data decision

Block 18 re-ran the source search from `AGENTS.md` section 5 /this block's
brief section 18 seriously, not ceremonially (full detail:
`docs/REAL_DATA_SOURCE_AUDIT_V2.md`):

- **Fantasy Premier League**: rejected. Terms explicitly prohibit automated
  extraction; re-verified 2026-08-15, unchanged since Block 16.
- **StatsBomb Open Data**: does not publish ENG_PL 2025/26 at all (its
  domestic-league coverage is historical and partial; only FIFA World Cup
  2022 is fully published). Confirmed not usable for this snapshot's player
  gap, only for validating that the engine's richer metric families work
  against real event data (`data/validation/wc2022/`).
- **OpenFootball**: publishes match results only, no player data.
- **FBref, SofaScore, FotMob, Understat, Transfermarkt, ESPN hidden
  endpoints, Bundesliga.com scraping, repackaged Kaggle/GitHub datasets**:
  all rejected on the same source-policy grounds as `AGENTS.md` section 5 --
  scraping, unofficial/private endpoints, or unverifiable upstream rights.
  None was implemented, none was even trialled for data extraction.
- **API-Football**: existing authenticated V1 integration, out of scope for
  a zero-cost real-snapshot block; not called in Block 18.

**Result: rich player source found = NO.** This is the honest, evidence-based
Block 18 finding, not a target count that was missed. Player-level Metric
Catalog V2 cells stay `unavailable`, never fabricated.

## Reproducing the snapshot

```
cd analytics
uv run football-intelligence-build-real-snapshot-v2
```

This is the single reproducible command for Block 18. It:

1. fetches Football-Data.co.uk's published `mmz4281/2526/E0.csv` and writes
   `data/real/2025-26/eng_pl_matches.json` (unchanged file/format from
   Block 16 -- `football-intelligence-collect-real-snapshot`'s own logic,
   reused, not duplicated);
2. fetches OpenFootball's published `2025-26/en.1.json` and writes
   `data/real/2025-26/eng_pl_matches_openfootball.json` in the same
   provenance-tagged shape;
3. normalizes both into `NormalizedObservation`s through the existing
   adapters;
4. resolves entity identity and reconciles the two sources through the
   existing `data_mesh.pipeline.resolve_and_reconcile` (the same pipeline
   the Block 13 PoC and Zero-Cost Coverage Lab already use);
5. measures coverage against the live Metric Catalog V2;
6. writes `data/manifests/real/ENG_PL/2025-26.json`.

Only `--competition ENG_PL --season "2025/26"` (the defaults) are
implemented; any other value exits with an explicit error rather than
silently reporting coverage that was never acquired.

Pass `--database-url postgresql://...` (or set `DATABASE_URL`) to also
persist the reconciliation evidence to the `ingestion` schema's audit
tables (`ingestion.source_observations`, `ingestion.reconciliation_decisions`)
-- the same audit-only boundary the Block 13 PoC and Coverage Lab already
use. **This job never writes to `football.*`.** The canonical load remains a
separate, unchanged step:

```
uv run football-intelligence-load-real-snapshot
```

No token/auth is required for any step. Total live requests per run: 2
(one CSV, one JSON) -- bounded, zero-auth, well under any provider's
documented rate limit.

## Idempotency (verified against a real local PostgreSQL 17 instance)

Running the full pipeline (`build-real-snapshot-v2` then
`load-real-snapshot`) twice against a fresh database, back to back:

| | Run 1 | Run 2 |
| --- | --- | --- |
| `football.matches` | 380 | 380 |
| `football.teams` | 20 | 20 |
| `football.team_match_stats` | 760 | 760 |
| `ingestion.reconciliation_decisions` | 5,720 | 5,720 |

Canonical state and reconciliation decisions are exactly stable across
reruns -- no duplicate entities, no duplicate canonical facts. The raw
`ingestion.source_observations` audit table is an append-only, per-fetch
observation log keyed on `(provider, entity, metric, observed_at)`; because
`observed_at` is the real timestamp of that fetch, a rerun legitimately logs
a new observation event per run (the same behavior the existing Block 13 PoC
job already has) rather than a duplicate of the same fact. This is by
design for an audit trail, not a defect in the canonical snapshot.

## Entity resolution notes (Block 18 addition)

Football-Data.co.uk's short club names ("Man City", "Nott'm Forest",
"Wolves", ...) do not share tokens with OpenFootball's official long names
("Manchester City FC", "Nottingham Forest FC", "Wolverhampton Wanderers
FC", ...) even after the existing generic stopword-stripping
(`fc`/`sc`/`sv`/...). `data_mesh/entity_resolution.py` adds:

- `afc` to the generic corporate-suffix stopword list (fixes "AFC
  Bournemouth" / "Sunderland AFC" automatically, same mechanism as the
  existing `fc` handling);
- a small, explicit, reviewed alias table
  (`_ENGLISH_SHORT_NAME_ALIASES`) for the 9 real ENG_PL clubs whose short
  form does not converge with the long form through stopword-stripping
  alone (Brighton, Leeds, Man City, Man United, Newcastle, Nott'm Forest,
  Tottenham, West Ham, Wolves) -- verified against all 20 real committed
  club names from both sources, never a fuzzy/edit-distance guess, in the
  same spirit as the existing `munich` -> `munchen` cross-language alias.

All 20 real clubs resolve to one logical team identity across both sources;
0 unresolved entities in the combined 8,360-observation snapshot.

## Handoff to Block 19

- The canonical `football.*` ENG_PL 2025/26 snapshot (match + team-stat
  evidence only) is real, reproducible, idempotent, and now cross-validated
  by a second independent source with 100% match-fact agreement.
- `football-intelligence-score-real-snapshot` continues to correctly report
  `insufficient_data` for player scoring -- there is still no permitted
  player-match evidence to score. Block 19 must not treat this as a bug to
  route around; it is the accurate state of available real data.
- If a compliant rich player-data source becomes available in the future,
  the existing `player_analytics` V2 job and `analytics.player_score_snapshots`
  read path (already built, Block 16) apply unchanged -- no new pipeline is
  needed on the scoring side, only a new adapter feeding real
  `player_match`/`goalkeeper_match` observations through the existing
  entity-resolution and load path.
- Team V2 dimensions that need xG/xGA or team process stats
  (`sterile_possession`, `few_but_high_quality_chances_allowed`, chance
  quality, pressing, transition, build-up) remain `insufficient_data` for
  ENG_PL 2025/26 real data; this is unchanged by Block 18 and is not a
  regression.
