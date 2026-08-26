# V1 Zero-Cost Historical Data Strategy

Status: product/data strategy decision for Football Intelligence V1.

## Decision

Football Intelligence V1 should be built with a **zero-cost-first data strategy**.

The V1 may combine many free APIs, open datasets, academic datasets, official reports, static historical snapshots and other legally/technically supportable sources. Source count is not itself a problem. The priority is broad, defensible coverage of the six core leagues while preserving the existing provenance, identity, semantic and quality guarantees.

Core competitions remain:

- `ARG_LPF` — Liga Profesional;
- `ENG_PL` — Premier League;
- `ESP_LL` — LaLiga;
- `ITA_SA` — Serie A;
- `GER_BL1` — Bundesliga;
- `FRA_L1` — Ligue 1.

Paid providers may be reconsidered later, but V1 should not depend on them if equivalent or sufficient evidence can be assembled for free.

This decision extends `docs/MULTI_SOURCE_PLAYER_EXPANSION.md`; it does not weaken any of its provenance, compliance, identity-resolution, missing-vs-zero, metric-mapping or reconciliation rules.

## Key principle: do not reconstruct raw inputs when a defensible refined result already exists

Historical Football Intelligence does **not** require every dimension to be rebuilt from the lowest-level raw statistics.

If a trustworthy free source already publishes a useful derived evaluation — for example a role-aware performance score, xG estimate, defensive rating, possession-value model output, player ranking, dimension score or other refined analytical result — Football Intelligence may ingest that result directly instead of reproducing the source model from all of its raw inputs.

Example:

A defensive assessment might ideally be derivable from tackles, interceptions, duel outcomes, blocks, errors, pressures, progression prevention and contextual variables. If a defensible source already publishes the final defensive/performance result for the relevant player, match or season, Football Intelligence may use that refined output without requiring all seven underlying inputs to be available independently.

The objective is to recover the strongest available historical evidence, not to force every historical period through the same raw-data pipeline.

## Evidence hierarchy for V1

For each desired Football Intelligence fact or dimension, prefer the cheapest valid path in this order:

1. **Direct free evidence** — goals, minutes, cards, lineups, appearances, shots, passes, tackles, etc. when semantics are known.
2. **Refined external evidence** — a published model/rating/score already computed by a defensible source.
3. **Football Intelligence derived result** — compute the result ourselves when enough compatible direct evidence exists and the methodology is approved/versioned.
4. **Qualitative/recognition evidence** — awards, team-of-the-season selections, authoritative scouting or other explicitly qualitative signals where they legitimately support a product question.
5. **Missing/unknown** — if evidence is insufficient, preserve absence rather than invent a value or treat it as zero.

This is a sourcing priority, not a claim that the evidence classes are interchangeable.

## Refined external evidence contract

A precomputed external result is acceptable only when Football Intelligence can preserve enough information to understand what it is.

At minimum retain:

- source/provider;
- original metric/model/rating name;
- player/team/competition/season or match scope;
- grain (`player_match`, `player_season`, etc.);
- source reference and acquisition/snapshot provenance;
- direct-vs-derived-vs-model evidence class;
- methodology or paper/version when available;
- scale and direction (`0-1`, `0-10`, higher-is-better, etc.);
- role/position dependence when applicable;
- known limitations;
- licence/compliance state;
- missingness semantics.

A provider model must remain provider-scoped unless a reviewed methodology proves comparability.

For example, `0.82` from one academic model, `7.8/10` from a platform rating and an internally derived `84` dimension score are **not** the same metric and must never be silently normalized into one universal truth merely because all appear to measure performance.

## Historical asymmetry is allowed

V1 may have different evidence depth across seasons and leagues.

Examples:

- one season may have event-level open data and allow Football Intelligence to derive many dimensions;
- another season may only have player-season aggregates;
- an older season may only have a trustworthy external performance model or ranking;
- some competition-season-dimension combinations may remain unknown.

Coverage tiers must describe what evidence actually exists rather than imply uniform depth.

The product may therefore use a mixture of:

- `CORE` direct statistics;
- `STANDARD` broader direct statistics;
- `ADVANCED` external or Football Intelligence model outputs where defensible;
- `SPATIAL` evidence only where true spatial/tracking data exists.

A higher-level historical score must never imply that all lower-level raw inputs are available.

## Source discovery policy

When researching free historical sources, do not search only for raw fields such as `tackles`, `interceptions` or `shots`.

Also search explicitly for already-refined outputs such as:

- player performance ratings;
- role-aware ratings;
- defensive/offensive contribution scores;
- xG/xA and expected-value models;
- possession-value or action-value metrics;
- player rankings/percentiles;
- academic football analytics datasets;
- historical team-of-the-season / award / expert-evaluation evidence where useful;
- published model outputs that can answer a Football Intelligence dimension directly.

This can dramatically reduce the raw-data burden for historical seasons.

## Candidate example: PlayeRank

PlayeRank is a concrete example of the type of source this strategy intends to evaluate: an academic role-aware player-performance model with published outputs. It is a **candidate for audit**, not an automatically approved Football Intelligence source.

Before promotion, verify its exact dataset scope, competitions/seasons, identity fields, methodology/version, licence, reproducibility, grain and compatibility with Football Intelligence's source and metric contracts.

The same rule applies to StatsBomb Open, Wyscout Open and any future academic/open dataset: useful does not automatically mean complete, comparable or product-approved.

## V1 operational rule

For every desired Football Intelligence dimension, ask:

```text
Is there a defensible free refined result already available?
  -> yes: ingest it as provider/model-scoped evidence.
  -> no: do we have enough free direct evidence to derive it ourselves?
       -> yes: derive it with an explicit versioned methodology.
       -> no: keep the dimension missing/unknown.
```

Do not purchase a provider merely to make historical coverage uniform if a defensible zero-cost multi-source solution is sufficient for V1.

## Non-goals

This decision does not:

- approve scraping prohibited sources;
- make incompatible ratings comparable;
- allow fuzzy/name-only player identity resolution;
- turn absence into zero;
- replace source provenance with a single opaque Football Intelligence number;
- claim that external model outputs are objective ground truth;
- require every league-season to expose the same data depth;
- prohibit future paid providers once V1 has validated what additional value they would provide.

## Success criterion

The V1 succeeds if Football Intelligence can provide useful historical player intelligence for the six core leagues with **zero recurring data-provider cost**, even if achieving that requires many heterogeneous sources and uneven historical depth, as long as every displayed conclusion remains traceable to defensible evidence and its limitations are explicit.
