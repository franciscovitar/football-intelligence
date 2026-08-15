# Real Data Source Audit V2 (Block 18)

This audit records the basis Football Intelligence relies on for every
source evaluated for the Block 18 real ENG_PL 2025/26 snapshot. It
supplements, and does not replace, the existing `docs/SOURCES.md`
source-compliance register and the per-source detail already recorded in
`docs/ZERO_COST_COVERAGE.md` and `docs/MULTI_SOURCE_DATA_MESH.md`. Unknown
permission is never treated as certification -- it is recorded as exactly
that: unknown.

All "date verified" entries below reflect the Block 18 implementation pass
(2026-08-15), re-checked against each source's own current published
material, not carried over from an earlier block's audit without
re-verification.

## Legend

- **APPROVED** -- automated, zero-cost acquisition is used as a live product
  provider.
- **APPROVED_LOCAL_ONLY** -- acceptable to fetch/inspect, but not committed
  or promoted as certified redistribution.
- **CONDITIONAL** -- usable for a narrower purpose than "current domestic
  player data" (e.g. historical/deep validation only).
- **REJECTED** -- not used, with a documented reason.

## Football-Data.co.uk

| Field | Value |
| --- | --- |
| Official URL | https://www.football-data.co.uk/englandm.php |
| Terms/notes URL | https://www.football-data.co.uk/notes.txt |
| Date verified | 2026-08-15 |
| Acquisition method | Direct download of the site's own published `mmz4281/<season>/<division>.csv` file |
| Authentication | None |
| Cost | Free |
| Freshness role | Current (updated through the season) |
| Competitions/seasons | ENG_PL 2025/26 (division `E0`), 7 of 10 target competitions publish a results file overall |
| Granularity | `match`, `team_match` |
| Potential Metric Catalog identities | `home_score`/`away_score`/`status` (match); `shots_total`, `shots_on_target`, `fouls`, `corners`, `yellow_cards`, `red_cards` (team_match) |
| Automated acquisition permission | The site publishes the CSV as a direct, explicitly linked download with its own documented column key (`notes.txt`) -- there is no login wall, no scraping of rendered HTML, and no terms page prohibiting programmatic fetches of the published files. Treated as acquisition-permitted on that basis. |
| Redistribution permission | **Unknown.** `notes.txt` and the site's pages contain no explicit redistribution/licence statement (re-verified 2026-08-15: no terms-of-use or licence page was found). |
| Attribution requirements | None documented |
| Product role | Primary current-season match/team-stat source for the ENG_PL 2025/26 real snapshot; already the source `load_real_snapshot.py` loads into `football.*` |
| **Status** | **APPROVED** for acquisition; **APPROVED_LOCAL_ONLY** for the specific question of redistribution, which stays `not_certified` in the committed file's own provenance block until an explicit licence is located |

## OpenFootball (`openfootball/football.json`)

| Field | Value |
| --- | --- |
| Official URL | https://github.com/openfootball/football.json |
| Terms/licence URL | https://github.com/openfootball/football.json (repository root; licence text reproduced below) |
| Date verified | 2026-08-15 |
| Acquisition method | Direct download of the repository's own published raw JSON file (`raw.githubusercontent.com/openfootball/football.json/master/<season>/en.1.json`) |
| Authentication | None |
| Cost | Free |
| Freshness role | Current (the repository publishes the in-progress/current season alongside completed ones; ENG_PL 2025/26 is a completed season here) |
| Competitions/seasons | ENG_PL 2025/26 verified live (380/380 matches, 20 clubs). The wider `openfootball` organisation covers many more leagues/seasons across sibling repositories (`world`, `europe`, `england`), not all individually verified in this pass -- only `en.1.json` in `football.json` was acquired and used |
| Granularity | `match` only (team identity + full-time score). No team-match statistics (shots, cards, corners) and no player-level data of any kind |
| Potential Metric Catalog identities | `home_score`, `away_score`, `status` (match) |
| Automated acquisition permission | Repository dedicated to exactly this kind of programmatic use; raw file fetches, no scraping |
| Redistribution permission | **Public domain / CC0.** The repository's own stated terms: *"The football.db schema, data and scripts are dedicated to the public domain. Use as you please with no restrictions whatsoever."* Verified live on 2026-08-15. |
| Attribution requirements | None (CC0 explicitly waives attribution) |
| Product role | Secondary, independent current-season source used to reconcile match results against Football-Data.co.uk through the existing Data Mesh pipeline (`resolve_and_reconcile`) -- proves real cross-source agreement on the canonical snapshot, never used as a canonical `football.*` load source itself |
| **Status** | **APPROVED** |

## StatsBomb Open Data

| Field | Value |
| --- | --- |
| Official URL | https://github.com/statsbomb/open-data |
| Date verified | 2026-08-15 (re-confirmed; role unchanged since Block 14/16) |
| Acquisition method | Official GitHub raw JSON |
| Authentication | None |
| Cost | Free |
| Freshness role | **Historical/deep only** -- never current |
| Competitions/seasons | FIFA World Cup 2022 is the only competition-season verified fully complete (64/64 matches) and used as the validation sample (`data/validation/wc2022/`). Domestic league samples in this dataset (e.g. Bundesliga 2023/24) are partial (34/306 matches) and ENG_PL 2025/26 is not published by this dataset at all |
| Redistribution permission | Requires attribution under StatsBomb's user agreement; no separate redistribution licence relied on |
| Product role | Validates that Metric Catalog V2's richer event-derived families (passing, defending, dribbling, xG) work correctly against real match-level data. **Never** used or presented as ENG_PL or any other core-league current data |
| **Status** | **CONDITIONAL** -- validation-only, not a Block 18 ENG_PL 2025/26 source |

## football-data.org

| Field | Value |
| --- | --- |
| Official URL | https://www.football-data.org |
| Date verified | 2026-08-15 (role unchanged since Block 14/15) |
| Authentication | Optional API token (`FOOTBALL_DATA_ORG_KEY`); CI never requires it |
| Cost | Free tier |
| Freshness role | Current |
| Granularity | `match` only (`home_score`, `away_score`, `status`); Free tier does not expose player statistics |
| Product role | Registered current-source provider in the Zero-Cost Coverage Lab; not used for the Block 18 ENG_PL 2025/26 snapshot itself (Football-Data.co.uk + OpenFootball already cover match facts without a token) |
| **Status** | **APPROVED** (existing role, unchanged) |

## TheSportsDB / OpenLigaDB

Unchanged from Block 13/15 (`docs/ZERO_COST_COVERAGE.md`). Both remain
**APPROVED** current-role providers in the Coverage Lab; neither was
re-probed for the ENG_PL 2025/26 snapshot itself in Block 18 (TheSportsDB's
event-stats/lineup endpoints are structurally capped and were already fully
characterised; adding them would not change the domestic player-data gap
below).

## Fantasy Premier League

| Field | Value |
| --- | --- |
| Official URL | https://fantasy.premierleague.com |
| Date verified | 2026-08-15 (re-confirmed; unchanged since Block 16) |
| Terms | The FPL terms of use prohibit automated systems used to access the game and extract information |
| Automated acquisition permission | **No.** Publicly reachable JSON does not imply permission -- the terms explicitly forbid automated extraction |
| Product role | None. No collector, client, or derived file exists in this repository |
| **Status** | **REJECTED** |

## API-Football

| Field | Value |
| --- | --- |
| Date verified | 2026-08-15 |
| Automated acquisition permission | Existing authenticated V1 provider integration; plan/credential terms apply |
| Product role | Not used for the Block 18 real-snapshot gap. Not called during this block's implementation |
| **Status** | Existing integration, **not a Block 18 source** -- excluded from the real ENG_PL 2025/26 snapshot pipeline entirely |

## Sources investigated and rejected without integration

Investigated during the Block 18 rich-player-data search (see
`docs/REAL_DATA_SNAPSHOT_V2.md` section "Rich player data decision") and
rejected on the same grounds documented in `AGENTS.md` section 5 -- scraping,
unofficial/private endpoints, or repackaged datasets whose original upstream
rights cannot be proven:

| Source | Reason rejected |
| --- | --- |
| FBref / Sports-Reference | Scraping a presentation website, not an official structured feed |
| SofaScore / FotMob | Unofficial/private JSON endpoints, no documented public API |
| Understat | Unofficial/private endpoint |
| Transfermarkt | Scraping; no official public data feed |
| ESPN hidden endpoints | Reverse-engineered private API, not documented/public |
| Bundesliga.com | Scraping a presentation website |
| Kaggle/GitHub repackaged player datasets | Original upstream provider's rights cannot be verified through a third-party mirror; a permissive wrapper licence does not override the source data's real terms |
| Paid APIs (API-Football premium tiers, etc.) | Out of scope: this block is zero-cost only |

## Net result

No source satisfying provenance + terms + reliability was found for rich
ENG_PL 2025/26 **player-level** data (shots, passes, defensive actions,
advanced metrics such as xG/xA at player grain). This gap is not
overridden by relaxing the source policy; see
`docs/REAL_DATA_SNAPSHOT_V2.md` for the full coverage report and the exact
Metric Catalog V2 identities this leaves unavailable.
