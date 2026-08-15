# Real snapshot: ENG_PL 2025/26

This directory contains real match/team evidence only. It does not contain a
domestic player dataset and cannot support league-wide player rankings.

## Committed data

`eng_pl_matches.json` contains 6,460 normalized observations covering all
380 completed Premier League matches and 20 clubs: results plus team shots,
shots on target, fouls, corners and cards. It was retrieved from
Football-Data.co.uk's published `mmz4281/2526/E0.csv` file; the exact UTC
timestamp is in `provenance.retrieved_at`.

The file declares:

- automated collection: `yes` (direct published CSV download);
- redistribution permission: `unknown` (no explicit redistribution licence
  was located during this pass);
- certification state: `not_certified` while permission remains unknown;
- scope: `ENG_PL`, season `2025/26`, grains `match` and `team_match`;
- rich domestic player coverage: `unavailable`.

Unknown permission is never presented as certified. The collector may refresh
the local snapshot, but publication/redistribution must be reviewed separately.

`eng_pl_matches_openfootball.json` (Block 18) contains 1,900 normalized
observations for the same 380 matches and 20 clubs -- team identity and
full-time match results only, no team-match statistics -- retrieved from
OpenFootball's public-domain (CC0) `football.json` repository
(`2025-26/en.1.json`). Its `provenance.redistribution_permission` is
`public_domain_cc0`, `certification_state` is `certified`. It is used
exclusively to reconcile match results against `eng_pl_matches.json` through
the existing Data Mesh pipeline (see `docs/REAL_DATA_SNAPSHOT_V2.md`) -- it
is never the canonical `football.*` load source, which stays
Football-Data.co.uk only.

## Explicitly excluded

The former Fantasy Premier League collector, client and derived player files
were removed. The FPL terms prohibit automated systems used to access the game
and extract information. Public visibility or unauthenticated JSON is not
permission for automated collection or redistribution.

No replacement was fabricated from FBref scraping, API-Football, paid sources,
or third-party mirrors with unclear provenance. Consequently Home/Rankings must
show an insufficient-data state until a permitted, complete rich ENG_PL player
source is connected.

## Loading

`uv run football-intelligence-load-real-snapshot` loads only the
Football-Data.co.uk match/team file into `football.seasons`,
`football.teams`, `football.matches` and `football.team_match_stats`. It
does not create player rows or player scores.

`uv run football-intelligence-build-real-snapshot-v2` (Block 18) refreshes
`eng_pl_matches_openfootball.json`, fetches a fresh Football-Data.co.uk copy
**in memory only** (never rewriting `eng_pl_matches.json` -- that file's
redistribution permission is unknown, so this job never extends an
unreviewed redistribution claim by silently rewriting it), reconciles both,
and writes `data/manifests/real/ENG_PL/2025-26.json`. It never writes to
`football.*` itself, and it never connects to any database unless an
explicit, validated-local `--database-url` is passed -- see
`docs/REAL_DATA_SNAPSHOT_V2.md`.

## Separate validation evidence

`data/validation/wc2022/` is a StatsBomb Open Data FIFA World Cup 2022 sample.
It validates rich event-derived metrics and scoring behavior only. It is never
labelled, loaded or displayed as Premier League evidence.
