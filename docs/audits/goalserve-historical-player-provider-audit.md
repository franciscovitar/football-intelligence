# Goalserve historical player-data provider audit

Status: public-source audit complete; trial/runtime gate blocked pending written rights/retention clarification.

## Decision question

Can Goalserve be used as a zero-cost trial or very-low-cost one-time historical backfill source for Football Intelligence's six target leagues from roughly 2016 onward, while preserving legally defensible storage and display rights after access ends?

## Current public evidence

Verified 2026-08-26 from Goalserve's current official pages.

### Historical depth and player fields

Goalserve states that its soccer API provides:

- historical results back to 2006;
- historical lineups, cards, goals and substitutions;
- detailed player statistics history since 2016;
- detailed team statistics history since 2016;
- player profiles and squad lists.

The documented player-stat field family includes, among others:

- appearances and minutes;
- starts and substitutions;
- goals and assists;
- total shots and shots on goal;
- fouls drawn/committed;
- tackles and interceptions;
- blocks and clearances;
- total/accurate crosses;
- total duels and duels won;
- aerials won;
- dribble attempts and successes;
- yellow/red cards;
- total passes and key passes;
- goalkeeper saves and related fields;
- average rating.

An official player-profile sample currently shows Wayne Rooney with detailed Premier League season rows for 2016/17 and 2017/18, including minutes, appearances, goals, assists, shots, passes, key passes, defensive actions, duels, dribbles and rating. This is direct provider evidence that the historical schema is not merely a current-season marketing claim.

### Competition presence

The current Goalserve soccer coverage page explicitly lists all six Football Intelligence targets or their equivalent provider naming:

- England — Premier League;
- Spain — Primera Division / La Liga;
- Germany — Bundesliga;
- Italy — Serie A;
- France — Ligue 1;
- Argentina — Primera División.

Current coverage presence does **not** prove that every one of those competitions has complete player-stat history for every season since 2016. That exact matrix remains unverified.

### Trial

Goalserve states publicly that it provides a **30-day free trial** and another current official page describes the trial as providing full access to its data.

However, the general Terms and Conditions say:

- a free trial is discretionary;
- billing information may be required;
- when billing information is entered, the account may be automatically charged when the trial ends unless the subscription is cancelled;
- trial terms may be changed or cancelled by the provider.

Therefore Football Intelligence must not activate the trial automatically or treat it as a zero-risk free route without explicit user approval and cancellation controls.

### Pricing

Current published soccer pricing is far above the project's normal zero/low-cost target. Examples shown on the current pricing page include roughly:

- live-score package: about USD 150/month;
- match/results package: about USD 150/month;
- live statistics package: about USD 200/month;
- full statistics package: about USD 300/month;
- broader full soccer package: higher still.

Exact inclusion of historical player-profile feeds by package should be confirmed before any purchase. **No paid plan is justified at this stage.**

## Rights and retention state

Goalserve's public marketing says its feeds can be integrated into applications and its site is designed for commercial data-feed use. It also states elsewhere that raw feeds may not be directly resold/redistributed while integrated application display is permitted for some sports feeds.

The general Terms and Conditions do **not** clearly answer the historical-backfill question that matters here:

1. whether raw/normalized soccer data may be cached in our database;
2. whether historical data acquired during a free trial may remain stored after the trial ends;
3. whether data acquired under a paid subscription may remain stored/displayed after cancellation;
4. whether derived Football Intelligence analytics may persist after cancellation;
5. whether there are league-specific restrictions for the six target competitions;
6. whether attribution is required;
7. whether the free trial specifically includes the historical player-stat/profile endpoints from 2016 onward.

Until those points are answered in writing, Goalserve is **not certified for backfill retention or public-product display**.

## Current technical value

If historical completeness and retention rights pass, Goalserve could be unusually valuable because it exposes a broad `STANDARD` player-season layer from 2016 onward in one provider, including Argentina, rather than requiring Football Intelligence to reconstruct every metric from event data.

The provider's own historical sample demonstrates that its season rows can already carry exactly the kind of normalized fields V1 needs: identity/profile context, minutes/appearances, attacking, passing, defensive, dueling, dribbling, cards and provider rating.

This must remain provider-scoped evidence. Goalserve rating is a provider output and must not be presented as an objectively ground-truthed Football Intelligence rating.

## Runtime gate — do not execute yet

A Goalserve trial/runtime test should happen only after written confirmation of the rights questions below and explicit user approval if billing information or automatic conversion to a paid plan is involved.

If approved, the smallest useful runtime gate is:

1. obtain a trial credential without putting it in chat/source;
2. store it only as a repository secret;
3. query one known historical player-season in each of the six target competitions where possible;
4. freeze raw bytes + deterministic summaries + checksums;
5. verify exact season depth and field null semantics;
6. test whether provider player/team IDs are stable across historical seasons;
7. do not bulk-enumerate until the six-target gate passes.

## Current conclusion

**TECHNICAL CONDITIONAL GO.**

**COST NO-GO for normal paid use at current published prices.**

**TRIAL HOLD until retention/licensing and billing behaviour are clarified in writing.**

Goalserve is materially more complete-looking than the fragmented open sources for the 2016-2021 gap, but the project should not exploit a free trial as a one-time bulk dump unless the provider explicitly confirms that retained historical use is permitted after access ends.
