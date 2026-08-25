# Sources

Block 18 adds a full, per-source audit in
[`REAL_DATA_SOURCE_AUDIT_V2.md`](REAL_DATA_SOURCE_AUDIT_V2.md) and a
reconciled real ENG_PL 2025/26 snapshot report in
[`REAL_DATA_SNAPSHOT_V2.md`](REAL_DATA_SNAPSHOT_V2.md). This register is not
duplicated there; both documents should be read together.

## Source-compliance register

Unknown permission is not certification. This table records the basis used by
the repository; it is not a legal opinion.

| Source | Permission/licence basis | Automated collection | Redistribution | Method | Scope / completeness | State |
| --- | --- | --- | --- | --- | --- | --- |
| Football-Data.co.uk | Publisher provides direct season CSV downloads and a column key; no explicit redistribution licence was located | Yes | Unknown | Direct `mmz4281/<season>/<division>.csv` download | ENG_PL 2025/26: 380/380 matches, 20 teams; selected match/team fields, no player metrics | Not certified for redistribution |
| OpenFootball (`football.json`) | Repository dedicates schema/data/scripts to the public domain (CC0) | Yes | Yes (CC0) | Direct raw-JSON download (`raw.githubusercontent.com/openfootball/football.json`) | ENG_PL 2025/26: 380/380 matches, 20 teams; match results only, no team-match stats, no player metrics | Certified (public domain); used only to reconcile Football-Data.co.uk, not as the canonical load source |
| Wikidata structured data | Wikidata's current licensing page states that structured data in the main/property/lexeme namespaces is released under CC0 1.0 | Yes, bounded | Yes (CC0) | Official `Special:EntityData/<QID>.json` Linked Data interface for an explicit small list of already-known QIDs; Football Intelligence caps one collection run at 50 entities | Player identity/profile corroboration only. ENG_PL 2017/18 lab: 20/20 clubs resolved and 373 exact+unique candidates across 599 Wyscout source profiles; bounded 50-QID snapshot audited 50/50 labels, exact DOB, citizenship and position. No performance metrics and no measured six-league coverage claim | Approved for bounded static profile-snapshot acquisition; candidate evidence only, no automatic player crosswalk or production promotion |
| Wyscout Open Data | Official Figshare collection `4415000` (DOI `10.6084/m9.figshare.c.4415000.v5`), CC BY 4.0 (attribution required) | Yes | Yes (CC BY 4.0) | Public Figshare v2 API (`api.figshare.com/v2`, documented, unauthenticated) | ENG_PL 2017/18: 380/380 matches, 20 teams, 603 players; 77/77 adapter-safe Metric Catalog V2 identities. **412,609 real observations** -- re-verified against the full real cache under the current `metric_granularity`-aware emission/audit contract (Block 20D.2 review-fix pass); historically certified at 411,844 observations under Block 20B.2b's original (pre-`metric_granularity`) contract, before `goalkeeper_match` `saves` was a distinct emitted identity | Certified adapter (historical/deep, approved for automated acquisition per this table); not current-season data, no canonical/production promotion decision made |
| StatsBomb Open Data | Official repository publishes JSON for research/analysis and requires attribution under its user agreement | Yes | Unknown in this repository (no standalone redistribution licence relied on) | Official GitHub raw JSON, pinned commit SHA | FIFA World Cup 2022 validation sample (Block 16); separately, ENG_PL 2015/16: 380/380 matches, 20 teams; 110/110 adapter-safe Metric Catalog V2 identities. **644,396 real observations** -- re-verified against the full real cache under the current `metric_granularity`-aware emission/audit contract (Block 20D.2 review-fix pass); historically certified at 643,628 observations under Block 20C.2b's original (pre-`metric_granularity`) contract | Certified adapter (historical/deep, approved for automated acquisition per this table) for ENG_PL 2015/16; `STATSBOMB_INTERNAL_ONLY = True` for all StatsBomb evidence -- commercial-use compliance under StatsBomb's stricter User Agreement remains an open product/legal question this repository does not resolve, so no canonical/production promotion decision has been made for either the WC2022 sample or the ENG_PL 2015/16 evidence |
| Fantasy Premier League | FPL terms prohibit automated systems used to access the game and extract information | No | No permission established | None; collector/client and derived files removed | No domestic player coverage | Prohibited for this implementation |
| API-Football | Existing V1 provider integration; plan/credential terms apply | No calls in Block 16 corrective pass | Unknown | Existing authenticated API integration only | Historical V1 paths; not used to fill the Block 16 gap | Not a Block 16 real-snapshot source |

Snapshot retrieval details:

- Football-Data.co.uk: `2026-08-15T00:27:07.021474+00:00`, direct E0 2025/26 CSV.
- OpenFootball: see `data/real/2025-26/eng_pl_matches_openfootball.json`'s
  `provenance.retrieved_at` (Block 18).
- Wikidata: real `ENG_PL` 2017/18 profile-fusion evidence is recorded in
  `docs/audits/wikidata-eng-pl-profile-fusion-2017-18.json`. The verified run
  resolved 20/20 clubs, produced 373 exact+unique profile candidates and then
  froze/audited a bounded 50-QID local snapshot. The raw entity JSON remains
  outside the repository; no snapshot or candidate was production-promoted and
  no automatic crosswalk was created.
- StatsBomb WC2022: see `data/validation/wc2022/wc2022_validation_sample.json` provenance.
- FPL: no retained dataset and no automated retrieval path.
- Wyscout ENG_PL 2017/18 (412,609) / StatsBomb ENG_PL 2015/16 (644,396):
  Block 20D.2's review-fix pass re-ran `football-intelligence-audit-
  wyscout-adapter` / `football-intelligence-audit-statsbomb-adapter`
  (current code, no new downloads) against the same full real caches
  Block 20B.2b/20C.2b originally certified against, all checks PASS
  including the new `no_missing_metric_granularity` check -- no network
  request was made for this re-verification.

### Wikidata profile boundary

The Wikidata foundation deliberately does **not** use WDQS as a product runtime
query layer and does not crawl for players. Collection starts from a bounded
explicit set of known Wikidata item IDs and uses the official Linked Data entity
endpoint. Raw entity JSON stays outside the repository unless a later evidence
policy explicitly approves a small fixture.

The parser preserves provider semantics rather than manufacturing profile facts:

- a Wikidata time with year/month precision remains imprecise; it is not turned
  into a fake January 1 or first-of-month date;
- only one unambiguous day-precision proleptic-Gregorian DOB can enter
  `PlayerIdentityRecord.date_of_birth`;
- citizenship (`P27`) and position (`P413`) remain provider-native QIDs until a
  separate reviewed taxonomy mapping exists;
- team membership (`P54`) contributes a canonical season team context only when
  an explicit QID→FI team mapping exists and one bounded `P580`/`P582` interval
  proves season overlap;
- no Wikidata membership supplies canonical match IDs, so Wikidata profile
  evidence cannot make a candidate `crosswalk_ready` by itself.

Primary references re-verified for this integration on 2026-08-24:

- `https://www.wikidata.org/wiki/Wikidata:Licensing`
- `https://www.wikidata.org/wiki/Wikidata:Data_access`
- `https://www.wikidata.org/wiki/Special:EntityData`
- `https://www.wikidata.org/wiki/Help:Dates`
- `https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits`

## API-Football

API-Football is the first structured football-data provider for V1.

### Boundary

Provider payloads are accepted only inside `analytics/.../providers` and
`analytics/.../normalization`. Provider IDs are persisted through mapping tables
and never become Football Intelligence primary keys.

### Block 3 audit strategy

The certification audit uses Premier League (`league=39`) season `2024`, a
completed season available to the Free plan during Block 3 verification.

The live audit intentionally stays small:

1. `GET /leagues?id=39&season=2024` to inspect provider-declared coverage.
2. `GET /fixtures?league=39&season=2024` to obtain completed fixture IDs.
3. Three `GET /fixtures?id=FIXTURE_ID` requests for the sampled matches.

This is five provider requests total for a three-match sample.

API-Football documents that a single `fixtures?id=FIXTURE_ID` response includes
the fixture's embedded events, lineups, fixture statistics, and player
statistics. The API also supports a multi-fixture `ids` parameter on plans where
that parameter is available; the Free plan used during certification rejected
`ids`, so Football Intelligence deliberately uses the portable single-`id`
path for this audit.

The season is passed explicitly. During Block 3 verification the Free plan also
rejected season `2025` and reported historical access through `2024`; this is a
provider-plan limitation, not a domain assumption.

### Coverage rule

Provider-declared coverage is advisory, not proof of field completeness. The
project therefore records observed non-null coverage from real sampled payloads
before later scoring models depend on a metric.

A missing value stays `NULL`. Zero is only stored when the provider actually
returns zero.

Known V1 examples from the documented fixture-player shape:

- fixture player `passes.accuracy` is a percentage, not a verified accurate-pass
  count, so `player_match_stats.passes_accurate` remains `NULL`;
- a verified player clearance count is not assumed from undocumented fields.

### Raw data

Block 3 stores live audit payloads as deterministic gzip-compressed JSON through
`LocalRawStore`. PostgreSQL stores corresponding traceability metadata when
persistence is enabled.

The production Supabase Storage adapter is deferred to Block 4, where scheduled
sync and live infrastructure are introduced together.
