# Historical Player V2 Context

Status: product/read-path contract for explicitly scoped Player V2 seasons.

## Why this exists

Historical player evidence must never become the implicit current/latest player experience merely because it was calculated most recently.

Player product contexts therefore use an explicit scope identity:

```text
competition:<competition_code>:<season_label>
```

Example:

```text
competition:ENG_PL:2017/18
```

Legacy aggregate scopes such as `core:<season>` remain valid analytics history but are not selectable player product contexts.

## First certified historical context

- competition: `ENG_PL`
- season: `2017/18`
- source: Wyscout Open
- scope: `competition:ENG_PL:2017/18`
- model: `player-v2.0`

The upstream historical bridge is documented in `docs/WYSCOUT_HISTORICAL_PLAYER_BRIDGE.md`.

## Observed Player V2 runtime

The existing Player V2 engine was executed against the full certified Wyscout Premier League 2017/18 dataset in ephemeral PostgreSQL.

Observed output:

- 2,048 Player V2 score snapshots across season / last 10 / last 5 / last 3;
- 26,841 Player V2 feature snapshots;
- 512 players with a season snapshot;
- 385 players with at least 450 standardized minutes;
- 294 total `partial` score snapshots;
- 1,754 total `insufficient_data` score snapshots;
- 0 `ready` overall snapshots;
- 0 overall scores;
- 0 rows in `product_player_ranking_candidates_v2`.

For the season window, the `performance` dimension is ready and scored for 385 players. The other intended Player V2 dimensions remain insufficient under the current canonical evidence. This does **not** authorize a performance-only pseudo-overall or a lower confidence gate.

## Product behavior

The player explorer is context-first:

1. select an explicit competition/season context;
2. attempt the normal publication-safe ranking path;
3. if no ranking candidate exists but Player V2 detail exists, render a neutral **Jugadores analizados** directory;
4. every directory link preserves the context into Player Detail;
5. Player Compare requires one shared explicit context for both players.

The non-ranked directory:

- does not show rank numbers;
- does not show fabricated scores;
- does not require `confidence >= 0.40`;
- does not require overall `ready`;
- may honor user filters such as minimum minutes, position and search;
- orders players neutrally by name.

Player Detail may expose partial/insufficient dimensions and real feature rows. Missing metrics remain missing.

## Current/home isolation

Historical player contexts are not silently promoted into the latest-completed-season Home experience or the current-context Watchlist.

Home may link explicitly to a historical player context, but its main status card continues to derive from the primary team context. Watchlist additions remain fail-closed until a Player V2 context matches that primary team scope.

## Analytics CLI contract

`football-intelligence-player-analytics` accepts `--competition`.

For example:

```bash
uv run football-intelligence-player-analytics \
  --competition ENG_PL \
  --season "2017/18" \
  --database-url postgresql://... \
  --report /tmp/player-v2.json
```

When `--competition ENG_PL` is supplied and no custom `--scope-key` is given, the job derives:

```text
competition:ENG_PL:2017/18
```

Without `--competition`, the existing multi-core-league `core:<season>` behavior is retained for backward compatibility.

## Production boundary

This implementation and its runtime verification do not authorize or perform a production database write.

Before the historical players can appear on the deployed site, a separate production promotion must be explicitly authorized and must:

1. load the certified Wyscout 2017/18 canonical/Data Mesh evidence into production;
2. calculate Player V2 with `--competition ENG_PL --season 2017/18` in the explicit scope;
3. verify counts and historical routing read-only after the write;
4. perform real browser QA against the deployed production site.

The current/day-to-day provider phase is intentionally out of scope and deferred.
