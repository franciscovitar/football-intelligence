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

`uv run football-intelligence-load-real-snapshot` loads only the match/team
file into `football.seasons`, `football.teams`, `football.matches` and
`football.team_match_stats`. It does not create player rows or player scores.

## Separate validation evidence

`data/validation/wc2022/` is a StatsBomb Open Data FIFA World Cup 2022 sample.
It validates rich event-derived metrics and scoring behavior only. It is never
labelled, loaded or displayed as Premier League evidence.
