# PlayerElo provider audit

Status: public-source gate complete; authenticated free-tier runtime gate pending.

## Decision question

Can PlayerElo provide zero-cost or very-low-cost, model-scoped player history for Football Intelligence's six target leagues from roughly 2016 onward, with stable identity linkage and defensible usage terms?

## Why this matters

The remaining V1 gap is not simply match results. We need broad historical player evidence for:

- `ARG_LPF` — Argentina Liga Profesional;
- `ENG_PL` — Premier League;
- `ESP_LL` — La Liga;
- `ITA_SA` — Serie A;
- `GER_BL1` — Bundesliga;
- `FRA_L1` — Ligue 1.

Open event datasets are excellent where they exist but do not provide complete six-league coverage across every target season. A provider that already computes a player-level historical strength signal could therefore add useful `STANDARD`/model evidence without pretending that Football Intelligence independently observed every underlying action.

## Current public-source evidence

Verified 2026-08-26 from PlayerElo's own current public pages.

### Provider scope

PlayerElo currently reports:

- 78K+ rated players;
- 6K+ rated coaches;
- 176 competitions;
- 262K+ processed matches;
- daily updates;
- individual player Elo;
- Elo Above Replacement (`EAR`) as a separate recent/career contribution signal;
- full match-by-match player rating history;
- playing-style/per-90 profiles;
- computed market values and other derived recruitment analytics.

These are provider/model outputs. They must never be represented as direct Football Intelligence observations or as raw source statistics.

### Model shape

The provider says player Elo updates are based on actual lineups and substitutions, opponent/team strength, result, minutes, margin/upset magnitude and ageing. Player and coach ratings are aggregated into lineup strength for match prediction.

Public coach pages explicitly describe lineup/coach attribution and league-season style baselines as beginning in `2016+`. This is useful evidence that the underlying tracked-history system reaches the historical window of interest, but it is **not** yet proof that every one of the six target leagues has complete player history for every season since 2016.

### API

Base URL documented by provider:

`https://data-api.playerelo.football`

Relevant endpoints:

- `GET /v1/players`
- `GET /v1/players/{id}`
- `GET /v1/players/{id}/history`
- `GET /v1/players/{id}/trend`
- `GET /v1/players/{id}/style`
- `GET /v1/clubs/{id}/players`
- `GET /v1/clubs/{id}/history`
- `GET /v1/leagues`
- `GET /v1/leagues/{id}/players`
- `GET /v1/usage`

The provider states that `/v1/players/{id}/history` returns full match-by-match Elo and EAR history.

### Identity linkage

PlayerElo explicitly states that player, club, league and fixture IDs match API-Football IDs exactly. Coach IDs use the same raw API-Football coach ID with a `coach_` prefix.

This is high-leverage for provider-to-provider linkage because Football Intelligence already has real API-Football evidence. It does **not** make either provider ID canonical; canonical identity policy remains unchanged.

Known API-Football player IDs already observed in our bounded live probes provide a no-fuzzy-match test matrix:

| Target | Representative | Provider player ID | Why useful |
| --- | --- | ---: | --- |
| `ARG_LPF` | Miguel Borja | `9933` | active Argentina 2024; long senior career |
| `ENG_PL` | Manuel Akanji | `5` | active Premier 2024; senior European career through target window |
| `ESP_LL` | Kylian Mbappé | `278` | active La Liga 2024; senior career begins before/around target window |
| `ITA_SA` | Lautaro Martínez | `217` | active Serie A 2024; Argentina/Europe career spans target window |
| `GER_BL1` | Harry Kane | `184` | active Bundesliga 2024; long Premier/Bundesliga history |
| `FRA_L1` | Ousmane Dembélé | `153` | active Ligue 1 2024; multi-league history through target window |

An authenticated test can therefore query six history endpoints directly without name matching.

### Current six-league presence

The public league table currently exposes all six target competitions and reports rated-player breadth approximately as follows:

- Premier League: 591;
- La Liga: 675;
- Serie A: 597;
- Bundesliga: 500;
- Ligue 1: 550;
- Argentina Liga Profesional: 1,049.

Public Argentina club/player pages confirm active Liga Profesional coverage.

These are current provider population counts, **not historical roster-completeness counts**.

## Pricing / quota

Current provider pricing on 2026-08-26:

| Plan | Price | Requests/month | Stated role |
| --- | ---: | ---: | --- |
| Free | €0 | 500 | Evaluation & hobby use |
| Pro | €19/mo | 10,000 | Production apps & dashboards |
| Ultra | €49/mo | 50,000 | Daily full-dataset refresh & backtesting |
| Business | €199/mo | 300,000 | Daily top-league Elo/EAR history + commercial licence & SLA |

The provider states that every plan includes all standard endpoints and differs by request volume. `/v1/usage` does not count against quota.

No payment should be made for this audit. The Free tier is sufficient for the bounded runtime gate.

## Rights / usage state

Public API FAQ says:

- Free is for evaluation/hobby use;
- paid plans permit commercial use;
- Business adds a commercial licence and SLA;
- PlayerElo describes the exposed data as its own computed ratings and derived analytics rather than raw third-party feeds resold 1:1.

This is promising but still leaves important questions before product promotion:

1. May Free-tier responses be stored/cached internally for evaluation?
2. May data acquired under Pro/Ultra remain stored and displayed after cancellation?
3. Is Pro's `Production apps & dashboards` wording itself sufficient commercial-use permission for a public product, or is the explicit Business commercial licence required for our use case?
4. Are historical ratings retained after subscription expiry?
5. Are there attribution requirements?
6. Are derived Football Intelligence features trained/calculated from PlayerElo allowed to persist after cancellation?

Until clarified, PlayerElo can be evaluated technically but is **not certified for public product display**.

## Bulk-route search

Older indexed PlayerElo pages referenced a `Kaggle dataset` navigation item. Current pages no longer expose that link, and current web/Kaggle searches did not locate an official PlayerElo-published bulk dataset.

Therefore no defensible zero-cost bulk snapshot has been found yet. The REST API remains the current official machine-readable route.

## Authenticated Free-tier runtime gate

### Credential handling

A free PlayerElo API key must be obtained by email from the provider.

Do not put the key in source, workflow YAML, logs, artifacts or chat. Store it as a GitHub Actions repository secret named:

`PLAYERELO_API_KEY`

### Bounded test

Once the secret exists, run only the smallest useful experiment:

1. call `GET /v1/usage` (provider says this does not consume quota);
2. call `GET /v1/players/{id}/history` for the six known provider IDs above — exactly six quota-consuming history calls;
3. freeze raw response bytes + deterministic summary + manifest/checksums;
4. verify the secret is absent from artifacts;
5. record for each player:
   - total history rows;
   - earliest/latest match date;
   - competition/league identifiers present;
   - fixture IDs;
   - Elo/EAR fields and null semantics;
   - minutes and team/opponent context if present;
   - paging/truncation metadata if present;
6. specifically verify whether at least one history in each target competition reaches 2016-2021 where the representative actually played there.

Do not paginate or enumerate whole leagues until this six-call gate passes.

## Success criteria

Technical **GO** requires:

- all six known IDs resolve without fuzzy matching;
- history endpoint returns stable structured rows;
- history is not unexpectedly truncated to recent seasons;
- at least representative histories demonstrate real target-window depth;
- null/zero semantics can be preserved;
- quota behaviour matches documented Free plan.

Broad historical-backfill **GO** additionally requires evidence that target-league coverage is not limited to isolated players/matches.

Product **GO** additionally requires explicit rights/retention clarification.

## Current conclusion

**CONDITIONAL GO to authenticated free-tier evaluation.**

PlayerElo is currently the strongest newly discovered candidate for a refined historical player layer because:

- the model output is exactly the kind of already-computed evidence V1 can use honestly;
- all six target competitions are present;
- the system publicly indicates history beginning around 2016;
- IDs align directly with our existing API-Football provider IDs;
- the technical evaluation costs €0 and only six counted requests.

It is **not yet approved as a historical backbone or public product source** because exact six-league historical completeness and post-acquisition usage rights have not been runtime/contractually verified.
