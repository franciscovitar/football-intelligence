# Real season snapshot: ENG_PL 2025/26

This directory holds the primary, non-synthetic Block 16 season snapshot:
the Premier League's 2025/26 season, the most recently completed core-league
season as of the August 2026 collection date. Every value here is a real,
provider-reported observation, collected by
`analytics/src/football_intelligence/jobs/collect_real_snapshot.py`
(`uv run football-intelligence-collect-real-snapshot`). No synthetic,
fabricated, or placeholder entities are present.

## Files

- `eng_pl_player_identity.json` -- 587 current (2026/27) FPL squad entries:
  `player_external_id`, `display_name`, `team_name`, `listed_position`.
- `eng_pl_player_season_stats.json` -- 459 real season-aggregate player
  records for 2025/26 specifically (the other 128 of the 587 current
  elements have no matching `2025/26` entry in their `history_past` -- most
  commonly players who joined a Premier League club from outside the league
  over the 2026 summer transfer window, so they have no PL history to
  report).
- `eng_pl_matches.json` -- 6,460 normalized observations covering the full
  380-match 2025/26 season (results, and team-level shots/shots-on-target/
  fouls/corners/cards per match).

## Sources

| File | Source | URL pattern | Auth |
| --- | --- | --- | --- |
| identity, season stats | Official Fantasy Premier League API | `https://fantasy.premierleague.com/api/bootstrap-static/`, `https://fantasy.premierleague.com/api/element-summary/{id}/` | None (public, unauthenticated JSON -- the same origin the PL's own FPL app consumes, not a hidden/private endpoint) |
| matches | Football-Data.co.uk | `https://www.football-data.co.uk/mmz4281/2526/E0.csv` | None (an explicitly published, directly-linked CSV file; a certified adapter since Block 15) |

Collected 2026-08-14/15 (see each file's `provenance.retrieved_at` for the
exact timestamp; `source`/`source_url`/`semantic_version` are repeated on
every individual record, not just the file-level provenance block).

## What this snapshot can and cannot support

The official FPL API is the richest zero-cost source for a *current*
domestic league found during Block 16 research -- it is the only one that
supplies real player-level **xG, xA, expected goal involvements, expected
goals conceded**, plus partial defensive counts (`tackles`, `recoveries`,
`clearances_blocks_interceptions`, `defensive_contribution`). No existing
zero-cost adapter in this repository had ever supplied player-level xG/xA
before Block 16.

It genuinely cannot supply, and this snapshot honestly shows as
`not_available` rather than a fabricated value or a silent zero:

- passing volume/accuracy, progressive passes/carries, key passes, crosses;
- dribbles/take-ons, duels, touches;
- team-level xG/xGA, possession, pass accuracy;
- match-by-match granularity for any FPL-sourced field -- `history_past` is
  a **season aggregate only**. Last-3/last-5/last-10 *form* windows cannot
  be computed from this snapshot; only a `season` window is valid, per the
  product rule that a window must never be manufactured from aggregate data.

## Known caveats

- **Team label currency**: `eng_pl_player_identity.json`'s `team_name`
  reflects each player's **current (2026/27)** FPL squad, not necessarily
  their 2025/26 club. A player transferred during the 2026 summer window
  will show their *new* club here while their `eng_pl_player_season_stats.json`
  totals remain correctly scoped to the 2025/26 season they actually played.
  This is a display-label caveat only -- it never affects which season a
  statistic is attributed to.
- **Population is current-squad-scoped**: `history_past` is only reachable
  through a player's *current* FPL element id. A player who played
  meaningful 2025/26 minutes but is no longer registered with any Premier
  League club by 2026/27 (mainly players at the three relegated clubs who
  did not move to another PL club) will not appear in this snapshot at all
  -- a real, honestly-reported population gap, not a silent exclusion.
- **Serie A-style shot-source caveat does not apply here**: `E0.csv` (the
  English top flight) is not the file `football-data-uk`'s adapter flags
  with the alternate Italian shots semantic version; this snapshot's shot
  counts use the default `football-data-uk-v1` semantic version throughout.

## Loading into the database

`uv run football-intelligence-load-real-snapshot` (reads this directory by
default; see `analytics/src/football_intelligence/jobs/load_real_snapshot.py`)
upserts these files into `football.players`, `football.teams`,
`football.seasons`, `football.matches`, `football.team_match_stats`, and the
new `football.player_season_stats` table. Idempotent -- safe to re-run.

## Related: secondary validation dataset

A separate, much smaller **FIFA World Cup 2022** sample (StatsBomb Open
Data) lives under `data/validation/wc2022/` -- it exists only to validate
that Metric Catalog V2 / the diagnostic engine / position-family scoring
correctly handle genuinely rich match-level data (passing, defending,
dribbling, event-derived xG) that this ENG_PL snapshot cannot supply. It is
**not** part of the product's core-league catalog and must never be
displayed as ENG_PL or any other core-league data.
