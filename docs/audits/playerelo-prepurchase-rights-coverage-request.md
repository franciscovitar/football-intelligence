# PlayerElo pre-purchase rights and historical coverage request

Status: draft only — not sent.

## Purpose

Clarify the minimum questions Football Intelligence needs answered before any paid PlayerElo plan or public-product use is considered.

## Draft message

Subject: Historical player-Elo coverage and data-retention questions before subscription

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

Could you please confirm:

1. Historical depth
   - Does `GET /v1/players/{id}/history` expose the full available career history in one response, or is it paginated/truncated?
   - For each of the six competitions above, from which season is player match-by-match Elo/EAR history broadly available?
   - Is coverage intended to be league-wide for those historical seasons, or are some seasons/clubs only partially covered?

2. IDs
   - Your public FAQ says player, club, league and fixture IDs match API-Football IDs. Is that mapping intended to be stable for historical records as well as current records?

3. Storage and retention
   - May API responses be stored/cached in our own database while a subscription is active?
   - If we subscribe to Pro or Ultra for a historical backfill and later cancel, may the previously acquired historical Elo/EAR data remain stored and displayed in our product?
   - May analytics or derived features calculated from PlayerElo data remain stored after cancellation?

4. Commercial use / licence
   - The pricing page says Pro is for `Production apps & dashboards`, while Business includes `commercial licence & SLA`, and the FAQ says paid plans permit commercial use. For a public commercial analytics website that displays PlayerElo-derived historical player ratings, is Pro sufficient, or is Business required?
   - Are there attribution, logo or source-link requirements?
   - Are there any league-specific restrictions for the six competitions listed above?

5. Bulk history
   - Do Pro or Ultra provide a bulk export/snapshot option for historical player Elo/EAR, or must histories be requested player-by-player?
   - Older indexed pages appeared to reference a Kaggle dataset. Is there still an official bulk/open dataset available?

We are not looking to resell a raw API feed; the goal is to combine model-scoped PlayerElo evidence with other sources inside our own analytics product while preserving provenance.

Thank you.
