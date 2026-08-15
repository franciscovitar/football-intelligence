# Product Experience V2

Block 17 exposes the statistical engines through two deliberately different read contracts.

## Detail and ranking contracts

- Detail reads `analytics.product_player_detail_v2` and `analytics.product_team_detail_v2`. They contain only `data_context = real`, exact V2 model snapshots, and preserve `ready`, `partial`, and `insufficient_data` states.
- Ranking candidates read `analytics.product_player_ranking_candidates_v2` and `analytics.product_team_ranking_candidates_v2`. UI queries additionally require `ready` evidence and a numeric score in the selected dimension.
- Player candidate thresholds are 450 season minutes, 270 for last 10, 180 for last 5, and 90 for last 3, with confidence at least 0.40. User filters may make these gates stricter, never weaker.
- No product read falls back to V1 or `test_smoke`.

Feature rows carry the same `data_context` as their score snapshot, so partial or missing values stay distinguishable from zero. Player percentiles remain nullable when the sample is ineligible.

## Product surfaces

The primary navigation exposes Home, player and team rankings, Compare, Radar, Watchlist, Results vs Performance, and Sources/Data Coverage. Player and team detail pages render evidence state, coverage, confidence, sample, dimensions, and supporting metrics. Missing evidence is explained in product language.

World Radar remains explicitly V1 because its provider depth is not equivalent to the V2 domestic engines. Perception stays separate from objective performance. Cross-league comparison carries a limitation until league-strength adjustment exists.

## Watchlist

`analytics.player_watchlist_entries` is a minimal single-user persistence contract. The product view and write action require the player to exist in the real V2 detail path, preventing test-only entities from appearing as recommendations.

## Current real-data limitation

The permitted snapshot is ENG_PL 2025/26 with 20 teams and 380 matches, but without an approved rich domestic player dataset. Empty player rankings are therefore an expected and correct state. Product pages describe the evidence that would make each section available; they do not seed or fabricate replacement players.
