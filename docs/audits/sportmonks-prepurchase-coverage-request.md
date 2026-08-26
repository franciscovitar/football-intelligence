# Sportmonks pre-purchase coverage request

Status: draft only; not sent.

Sportmonks' current public material says historical depth varies by competition and explicitly invites prospective users to provide the leagues/seasons they need so Sportmonks can confirm what exists **before paying**. This is the correct next gate for Football Intelligence under a near-zero budget.

Contact route: <https://www.sportmonks.com/contact-support/>

## Draft message

Subject: Historical player-stat coverage for 6 leagues before purchase

Hello Sportmonks team,

I am evaluating Sportmonks for a football analytics application and would like to confirm exact historical coverage before purchasing a plan or historical-data add-on.

Our target competitions are:

- Argentina Primera División / Liga Profesional Argentina
- English Premier League
- Spanish La Liga
- Italian Serie A
- German Bundesliga
- French Ligue 1

Our target window is roughly the last ten completed/current seasons, approximately 2016 through 2026 depending on each competition's season convention.

Could you please confirm, for each league and season, whether you have the following data available?

1. Player-season identity/roster context:
   - stable player ID
   - team/club ID
   - season ID
   - position
   - appearances / starts if available
   - minutes played

2. Player-season performance statistics:
   - goals
   - assists
   - shots
   - passes / pass accuracy
   - key passes or chances created if available
   - tackles
   - interceptions
   - duels / duels won
   - dribbles / successful dribbles
   - cards
   - any other standard player statistics available consistently

3. Player-match statistics and lineups for the same seasons, where available.

A simple league x season coverage table is enough; we do not need sample bulk data at this stage.

I also need to clarify the commercial terms for a small analytics product:

- Does the historical-data add-on starting at EUR 29 unlock historical data for all leagues selected in the active plan, or is it priced per league / per package?
- Can historical data be evaluated during the 14-day trial, or does the historical add-on require a separate paid purchase before it becomes accessible?
- If we subscribe for one month, acquire historical records through the API, and later cancel the recurring subscription, may we continue retaining those already-acquired historical records in our own database and displaying them inside our analytics product, provided we do not resell or redistribute the raw API feed?
- Are there any league-specific restrictions, attribution requirements, or third-party publication rights we should know about for the six competitions above?
- Is derived analytics/ranking output calculated from the data allowed to remain in our product after subscription cancellation?

Our use case is an analytics application, not a raw-data resale service. We want to store source provenance and calculate our own derived metrics/rankings from the licensed source data.

Thank you. Exact coverage and these rights questions will determine whether we can justify the purchase.

## Decision rule

Do not buy Sportmonks based only on marketing-level historical claims.

A paid experiment becomes eligible only if the written reply establishes:

- useful player-season coverage across a substantial part of the six-league ten-year target;
- enough identity/team context to reconcile players deterministically;
- useful STANDARD-level metrics rather than only goals/cards;
- historical-add-on pricing that is actually small for the required six leagues;
- acceptable retention/display terms for previously acquired data after cancellation;
- no publication/rights condition that makes the intended Football Intelligence product unusable.
