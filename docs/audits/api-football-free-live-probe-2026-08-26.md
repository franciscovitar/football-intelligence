# API-Football Free live probe — 2026-08-26

Status: live authenticated technical evidence on `lab/low-cost-player-history-provider-audit`. API-Football is **not** promoted to a Football Intelligence product source by this document.

## Decision summary

The API-Football Free account is active and technically useful for recent player-season reconnaissance across Football Intelligence's six core leagues.

Observed directly:

- the authenticated `/leagues` catalogue resolves all six core competitions;
- `/players` returns real player profiles and season-statistic blocks for season parameter `2024` in all six core competitions;
- the Free plan rejects season `2016` on `/players` and explicitly says Free access is limited to seasons `2022` through `2024`;
- therefore API-Football Free **cannot** be the 2016–2021 historical backbone for the zero-cost V1;
- it can remain a recent-period enrichment/prototyping candidate while older coverage is assembled from open/static sources;
- publication/licensing rights remain unresolved under the existing API-Football terms audit, so technical availability does not equal product approval.

## Account/runtime gate

The first authenticated attempt, while the account was suspended, failed with provider error:

`Your account is suspended, check on https://dashboard.api-football.com.`

After the dashboard showed the Football Free subscription as `Active`, the exact same bounded job succeeded. This distinguishes the earlier failure from an implementation/parser failure.

The GitHub secret `API_FOOTBALL_KEY` was available to Actions and was never persisted in the probe outputs. Every temporary workflow included a post-run secret-leak check.

## Catalogue snapshot

Run: `32969730337`

Artifact:

- name: `api-football-free-coverage-32969730337`
- id: `9607100061`
- artifact digest: `sha256:6955dc7ad70e61ae43e4cc9da39db181c5e079189177649fa64e785261d7f4f6`

The retained job `football-intelligence-probe-api-football-free-coverage` made exactly one `GET /leagues` request and wrote the raw response, normalized six-league `coverage.json`, and generic checksum manifest.

Resolved provider league IDs:

| FI competition | API-Football league ID |
| --- | ---: |
| `ARG_LPF` | 128 |
| `ENG_PL` | 39 |
| `ESP_LL` | 140 |
| `ITA_SA` | 135 |
| `GER_BL1` | 78 |
| `FRA_L1` | 61 |

For the target historical window, the provider catalogue reports `players=true` and fixture player-statistics coverage for all six competitions throughout 2016–2025. This is **catalogue evidence only**. It does not prove the current subscription can query those seasons.

A concrete example of the distinction is the 2016 access probe below: the catalogue advertises historical coverage, while the Free subscription refuses that season on `/players`.

## Two page-1 `/players` probes for 2024

Run: `32969326342`

Artifact:

- name: `api-football-player-page1-32969326342`
- id: `9606942861`
- artifact digest: `sha256:6211f251114a7b576feb6cada0b9234ef7c3ae816f3545cbc1d79adafce9e6a2`

Exactly two requests were made:

### `ARG_LPF`, season 2024

- HTTP 200;
- provider errors: none;
- 20 response rows on page 1;
- `paging.total = 85`;
- player profile fields include provider ID, name components, birth, age, nationality, height, weight, injury state and photo;
- statistic blocks expose `games`, `shots`, `goals`, `passes`, `tackles`, `duels`, `dribbles`, `fouls`, `cards`, `penalty`, `substitutes`, team and league context.

All statistic counts in this particular page-1 sample were null. The names showed that many records represented players no longer active for those clubs in the 2024 league season. This page therefore cannot be interpreted as evidence that Argentina statistics are absent.

### `ENG_PL`, season 2024

- HTTP 200;
- provider errors: none;
- 20 response rows on page 1;
- `paging.total = 57`;
- the same broad statistic schema was returned;
- real non-null season statistics were present for active players.

One player returned two statistic blocks for two teams in the same season. This is useful confirmation that a single provider player can carry multiple team contexts and must not be flattened to one team-season row without preserving that context.

The page counts are not certified unique-player counts. Transfers, inactive/stale memberships and multiple statistic blocks mean `pages × 20` must not be presented as the number of active players.

## Targeted active Argentina player

Run: `32969539557`

Artifact:

- name: `api-football-arg-known-player-32969539557`
- id: `9607025279`
- artifact digest: `sha256:4f1b22ff0342480774d642fc0c4a2436f9c0489da0d80f1831db1eff3375dfaf`

One request was made:

`/players?league=128&season=2024&search=Borja`

The provider returned real season statistics. Example provider observation for `M. Borja` / River Plate:

- appearances: 35;
- minutes: 2221;
- goals: 24;
- assists: 1;
- shots: 84;
- passes: 430;
- tackles: 25;
- duels: 207;
- provider rating: `7.261764`.

These values prove response depth and access. They have **not** been independently validated here as canonical Football Intelligence facts.

## Remaining four leagues — direct 2024 statistics

Run: `32969842249`

Artifact:

- name: `api-football-four-leagues-2024-32969842249`
- id: `9607142383`
- artifact digest: `sha256:e89f73e65a6fbc3f117547583763b88a9ce3d67b6b69322e1198ed38ce67998c`

Exactly four requests confirmed real statistics in the other four competitions:

| Competition | Search/sample | Apps | Minutes | Goals | Assists | Shots | Passes | Tackles | Duels | Provider rating |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ESP_LL` | Kylian Mbappé / Real Madrid | 34 | 2917 | 31 | 3 | 122 | 1093 | 9 | 307 | 7.717647 |
| `ITA_SA` | Lautaro Martínez / Inter | 32 | 2577 | 12 | 3 | 83 | 611 | 30 | 288 | 7.222580 |
| `GER_BL1` | H. Kane / Bayern München | 31 | 2389 | 26 | 8 | 90 | 617 | 14 | 164 | 7.696774 |
| `FRA_L1` | O. Dembélé / Paris Saint Germain | 30 | 1736 | 21 | 7 | 78 | 977 | 11 | 176 | 7.724137 |

Again, these are provider observations used to prove endpoint/schema utility, not independently validated canonical facts.

Together with the Argentina and Premier probes, direct player-stat access for season parameter `2024` is now observed in all six Football Intelligence core competitions.

## Free historical access limit

Run: `32969627531`

Artifact:

- name: `api-football-2016-access-32969627531`
- id: `9607060327`
- artifact digest: `sha256:0e62f2249379a76d9e86df96e2080d019644fe951d760fe2e3b571aebadf21ff`

Exactly three 2016 requests were made:

- `ENG_PL` / Agüero;
- `ESP_LL` / Messi;
- `ARG_LPF` / Tévez.

All three returned HTTP 200 with zero results and the same provider-level error object:

`Free plans do not have access to this season, try from 2022 to 2024.`

Implementation consequence: an API-Football client **must inspect the response `errors` object even when HTTP status is 200**. HTTP success alone is not a successful provider query.

Product consequence: Free access is insufficient for the desired ~2016–2026 historical window. Do not spend pagination quota trying older seasons on this Free account unless the plan changes.

## Null vs zero finding

The live data confirms that null and zero coexist in count fields and cannot be globally collapsed.

Observed patterns include:

- some roster/statistic blocks with `appearences = 0` and `minutes = 0`;
- other membership-like blocks with appearances/minutes null;
- count fields such as goals, shots, assists, tackles or duels may be null while other fields in the same statistic block are populated;
- provider rating is a string when present and null when absent;
- the provider field is spelled `appearences` in the raw API schema and should be preserved at the provider boundary rather than silently treated as a canonical name.

No global rule such as `null = 0` is approved. Field-specific semantics require documentation/corroboration before Metric Catalog promotion.

## Request budget used by this live audit

After account activation, the evidence runs used 12 authenticated provider calls in total:

- two `/leagues` calls (the first successful reconnaissance and the later artifact-preserving snapshot);
- two page-1 `/players` calls;
- one targeted Argentina `/players` call;
- three 2016 access probes;
- four remaining-league 2024 probes.

This remains well inside the Free plan's advertised 100 requests/day. No full competition pagination was performed.

## Current source role decision

API-Football Free is useful, but its role is bounded:

### Useful now

- recent 2022–2024 technical/player-stat enrichment candidate;
- broad player profile/schema reconnaissance;
- cross-source validation and completeness experiments;
- provider rating as explicitly provider-scoped model evidence if later approved;
- direct stats where semantics and rights separately pass review.

### Does not solve

- free 2016–2021 player-stat history;
- publication/licensing requirements;
- null/zero semantics by itself;
- complete active-roster semantics solely from `/players` pagination;
- canonical player identity.

### V1 implication

Continue the zero-cost multi-source strategy. Use API-Football Free only for the recent window it actually exposes, and search open/static/academic sources — including already-refined historical outputs — for 2016–2021 rather than paying merely to make one provider uniform across the decade.

No database write, canonical-player creation, product promotion, merge to `main`, deployment or public-display approval is performed by this live probe.
