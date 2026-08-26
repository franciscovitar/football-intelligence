# PlayerElo pre-purchase rights and historical coverage request

Status: draft only — not sent.

## Purpose

Clarify the minimum questions Football Intelligence needs answered before any paid PlayerElo plan or public-product use is considered.

## Runtime evidence already observed

A bounded authenticated Free-tier probe on 2026-08-26 confirmed that real player histories reach the 2016-2021 target window and earlier for several careers. However, every observed `GET /v1/players/{id}/history` row contained only:

- `date`;
- `elo`;
- `ear`.

No sampled row exposed fixture, club/team, competition/league, opponent, minutes or season identifiers. This makes historical depth technically useful but prevents independent league-season scoping from the history endpoint alone.

## Draft message

Subject: Historical player-Elo coverage, match context and data-retention questions before subscription

Hello PlayerElo team,

I am evaluating PlayerElo for a football analytics product and would like to confirm a few details before considering a paid plan.

Our target competitions are:

- Argentina Liga Profesional
- English Premier League
- Spanish La Liga
- Italian Serie A
- German Bundesliga
- French Ligue 1

We are primarily interested in player-level Elo / EAR history from approximately the 2016/17 season onward.

We have already tested the Free API successfully with a small bounded sample. The historical depth looks promising, but the history rows we observed contained only `date`, `elo` and `ear`.

Could you please confirm:

1. Historical match context
   - Is there an endpoint, query option or expanded history response that also returns the historical `fixture_id`, `club/team_id`, `league/competition_id`, opponent and/or minutes for each Elo/EAR update?
   - If not, what is the recommended way to map a history row back to the exact API-Football fixture and competition that produced it?
   - Can more than one Elo/EAR update occur on the same calendar date for one player, for example club plus international or multiple competitions? If so, how can those updates be disambiguated?

2. Historical depth and completeness
   - Does `GET /v1/players/{id}/history` expose the full available career history in one response, or is it paginated/truncated?
   - For each of the six competitions above, from which season is player match-by-match Elo/EAR history broadly available?
   - Is coverage intended to be league-wide for those historical seasons, or are some seasons/clubs only partially covered?
   - Is there a way to query the historical player population for a specific league and season, rather than only the current league population?

3. IDs
   - Your public FAQ says player, club, league and fixture IDs match API-Football IDs. Is that mapping intended to be stable for historical records as well as current records?
   - Are the IDs used internally for each history update available anywhere through the API even though they are not present in the sampled `/history` rows?

4. Storage and retention
   - May API responses be stored/cached in our own database while a subscription is active?
   - If we subscribe to Pro or Ultra for a historical backfill and later cancel, may the previously acquired historical Elo/EAR data remain stored and displayed in our product?
   - May analytics or derived features calculated from PlayerElo data remain stored after cancellation?

5. Commercial use / licence
   - The pricing page says Pro is for `Production apps & dashboards`, while Business includes `commercial licence & SLA`, and the FAQ says paid plans permit commercial use. For a public commercial analytics website that displays PlayerElo-derived historical player ratings, is Pro sufficient, or is Business required?
   - Are there attribution, logo or source-link requirements?
   - Are there any league-specific restrictions for the six competitions listed above?

6. Bulk history
   - Do Pro or Ultra provide a bulk export/snapshot option for historical player Elo/EAR, or must histories be requested player-by-player?
   - Is there any bulk route that includes fixture/team/competition context with the rating history?
   - Older indexed pages appeared to reference a Kaggle dataset. Is there still an official bulk/open dataset available?

We are not looking to resell a raw API feed; the goal is to combine model-scoped PlayerElo evidence with other sources inside our own analytics product while preserving provenance.

Thank you.
