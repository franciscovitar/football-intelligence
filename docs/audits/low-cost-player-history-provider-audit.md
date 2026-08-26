# Low-cost player-history provider audit

Status: bounded source audit only. No provider has been promoted to a Football Intelligence product source.

## Decision question

Can Football Intelligence build a broad player-season history for the six core leagues — ARG_LPF, ENG_PL, ESP_LL, ITA_SA, GER_BL1 and FRA_L1 — while keeping spend at zero or very low, preserving provenance, missing-vs-zero semantics and source-compliance guarantees?

This audit focuses on the two commercial APIs raised as possible mass-history backbones: API-Football and Sportmonks. It does not supersede the existing rejection of Transfermarkt-derived or FBref/Sports-Reference-derived automation, and it does not change Wikipedia/Wikidata's role as membership/profile enrichment rather than a complete season-roster backbone.

## Budget policy

The evaluation order is deliberately cost-first:

1. spend USD/EUR 0 while schema, current/recent coverage and rights can still be tested;
2. do not buy historical access until a free-tier experiment proves the provider schema is materially useful for Football Intelligence;
3. if a paid trial is ever justified, prefer the smallest reversible purchase and freeze raw snapshots with checksums;
4. never assume that a cheap API subscription grants official league publication rights;
5. no provider data is promoted into PostgreSQL or canonical Player IDs until coverage, semantics, identity and rights have passed separate gates.

## API-Football

### Current public pricing and access

As checked on 2026-08-26, API-Football advertises:

- Free: USD 0/month, 100 requests/day, no credit card;
- Pro: USD 19/month, 7,500 requests/day;
- Ultra: USD 29/month, 75,000 requests/day;
- Mega: USD 39/month, 150,000 requests/day.

All plans expose the same endpoint families, but the free plan has a shallower historical range. The provider explicitly describes the free tier as suitable for development/prototyping and says paid plans unlock deeper historical archives.

### Technical fit

The documented `/players?league=<id>&season=<year>` route is a strong match for the desired player-season grain:

- one call returns player profile plus season-stat blocks;
- league+season can enumerate all players in a competition;
- results paginate at 20 players/page;
- documented statistics include appearances, minutes, goals, assists, shots, passes/key passes/accuracy, tackles, dribbles, fouls, cards and penalties;
- `/leagues` exposes season-level `coverage`, including player and player-statistics availability, so coverage can be checked before spending calls on deep endpoints.

For roughly 500 players in one league-season, about 25 paginated calls would be expected. Therefore volume is not the limiting factor for a 6-league x 10-season player-season snapshot; historical availability, semantic quality and rights are.

### Rights/compliance gate

API-Football's public terms permit using the feed to create applications, websites, fantasy products and similar projects and prohibit directly reselling the data. However, the same terms explicitly state that API-Football does **not** provide the licence/permission required to publish the supplied data and that the user must obtain any required permission from competent rights holders.

Decision: API-Football is a technically strong **zero-cost prototype candidate**, but it is not currently certified as a public Football Intelligence product source. Public display rights remain unresolved.

### Zero-spend experiment

Before any purchase:

1. create one free API-Football account only;
2. keep the API key outside Git and outside browser/client code;
3. use at most the free 100 requests/day;
4. freeze `/leagues` responses for the six core competitions and record the exact seasons visible to the free tier plus each season's coverage flags;
5. for every league-season available for free, fetch page 1 of `/players` and record:
   - `paging.total`;
   - fields actually returned;
   - null/zero behaviour;
   - provider player ID stability signals;
   - team/competition grouping semantics;
6. fully paginate only one or two representative league-seasons after the schema passes inspection;
7. compare observed roster/player counts against independent official lower bounds where available.

Stop immediately if player-season coverage is absent, identity/team context is ambiguous, null/zero semantics cannot be preserved, or the response does not contain enough standard metrics to improve the current product.

## Sportmonks

### Current public pricing and access

As checked on 2026-08-26, Sportmonks advertises:

- a forever-free test option, but the documented free competitions are Danish Superliga and Scottish Premiership rather than Football Intelligence's six core leagues;
- Starter: EUR 29/month for 5 selected competitions;
- extra leagues: from EUR 4/month;
- historical data older than the standard three-season window: from EUR 29 as a one-time add-on;
- paid plans include a 14-day trial.

For six target competitions, the published floor is therefore approximately EUR 33/month before any historical add-on, subject to the exact price of the sixth league and any taxes. Historical access older than three seasons starts at an additional one-time EUR 29. These numbers are pricing signals, not a purchase recommendation.

### Technical fit

Sportmonks documents:

- squad lists and player IDs by team/season;
- player and season statistics;
- historical records on the same API model as current data;
- stable team/player entities and season filters;
- detailed match/player statistics, with depth varying by league and season;
- approximately ten years of data at scale, while exact depth must be checked per competition.

This is a strong architectural fit for a tiered Football Intelligence model where CORE/STANDARD coverage can be broad and ADVANCED/SPATIAL coverage remains source-specific.

### Rights/compliance advantage

Sportmonks' current public integrity/terms material is materially clearer for the intended product shape than API-Football's:

- building apps/websites/games on the data is explicitly permitted;
- commercial use is explicitly permitted;
- storing/caching the data in the product's own database is explicitly permitted;
- showing the data to users in the product's own presentation is explicitly permitted;
- reselling or redistributing the raw feed as data requires approval;
- Sportmonks also states it is a data provider, not an official league rights holder, so a product that specifically requires officially licensed competition data would still need a separate rights arrangement.

One point remains to obtain in writing before any one-month historical extraction strategy: whether already acquired historical records may continue to be retained and displayed after cancelling the subscription. The public material clearly permits storage while using the service but does not make this post-cancellation scenario explicit enough for Football Intelligence to assume it.

Decision: Sportmonks is currently the **stronger low-cost product-source candidate on rights and architecture**, but it is not zero-cost for the six target leagues and is not certified until exact historical coverage and post-cancellation rights are proven.

### Zero-spend experiment

Do not buy the historical add-on first.

1. use the forever-free account only to validate response shape, includes, statistic type taxonomy, pagination and missing/null semantics;
2. map that schema against Football Intelligence's existing player-season model and metric tiers;
3. inspect public coverage material for the six target competitions;
4. ask Sportmonks support, before payment, for a written 6 x 10 coverage matrix or exact season list and statistic depth for the six target leagues;
5. ask in the same message whether a one-month subscription plus historical add-on permits continued retention and display of the acquired historical records after cancellation, provided the raw feed is not resold;
6. pay only if those written answers satisfy the product and compliance gates.

## Current ranking under a near-zero budget

### 1. API-Football free tier — use now for technical reconnaissance

Why:

- USD 0;
- no card required;
- all endpoint families available;
- 100 calls/day is enough for bounded schema/coverage experiments;
- `/players` is directly relevant to the desired player-season grain.

Constraint: deeper historical seasons require a paid plan, and publication rights are not granted by API-Football itself.

### 2. Sportmonks — preferred paid candidate only if a tiny spend becomes acceptable

Why:

- stronger explicit product/storage/display permissions;
- player/squad/season data fit the intended architecture;
- historical access is a one-time add-on rather than necessarily a permanent historical surcharge.

Constraint: the six core leagues do not fit the documented forever-free coverage; likely minimum paid access is roughly EUR 33/month plus historical access from EUR 29 one-time. Exact historical depth and post-cancellation rights must be confirmed before spending.

### 3. Continue open/static multi-source enrichment in parallel

OpenFootball, Wikidata/Wikipedia and any source already certified in `docs/SOURCES.md` should continue to fill the grains they legitimately support. They should not be stretched into a complete player-performance source when their evidence does not support that claim.

## Product architecture implication

The proposed data-tier model is compatible with the existing Football Intelligence guarantees and should be retained as a design direction, not yet as a product promise:

- CORE: appearances/minutes/goals/assists/cards and other broadly available direct statistics;
- STANDARD: shots, passing, key passes, tackles, interceptions, duels, dribbles and similar provider statistics when actually supported;
- ADVANCED: derived/event-level metrics only where event data is available and licensed;
- SPATIAL: tracking/360-derived metrics only where spatial data is available.

Every metric must retain source, grain, season/competition scope, direct-vs-derived status, missingness semantics, model/version metadata when applicable, and a coverage/confidence label. A player-season with STANDARD coverage must never imply ADVANCED or SPATIAL evidence exists.

## Immediate next gate

No purchase is justified yet.

The next useful evidence is a **free API-Football coverage/schema snapshot** for the six core competitions plus a **free Sportmonks schema test** on its allowed sample competitions. Only after those two experiments should Football Intelligence decide whether a one-time/minimal paid historical extraction is worth considering.
