# API-Football pre-purchase coverage and rights request

Status: draft only; not sent.

API-Football is technically attractive under a low budget, but its current terms explicitly state that API-Football does not itself grant the licence/permission required to publish supplied data. Before any paid historical extraction, Football Intelligence should obtain written clarification on exact historical coverage and the intended public-product use.

## Draft message

Subject: Player-stat historical coverage and publication/retention clarification

Hello API-Football team,

I am evaluating API-Football for a football analytics application and want to confirm historical player-stat coverage and permitted use before purchasing a paid plan.

Our target competitions are:

- Argentina - Liga Profesional Argentina
- England - Premier League
- Spain - La Liga
- Italy - Serie A
- Germany - Bundesliga
- France - Ligue 1

Our target window is approximately the last ten seasons, roughly 2016 through 2026 depending on each competition's season convention.

Could you please confirm for each competition which seasons support:

1. `/players?league=<id>&season=<year>` with season player statistics;
2. player appearances and minutes;
3. goals and assists;
4. shots;
5. passing / pass accuracy / key passes where available;
6. tackles and interceptions;
7. duels and dribbles;
8. cards and penalties;
9. `/fixtures/players` match-level player statistics;
10. lineups.

A league x season coverage matrix is enough; we do not need bulk sample data before purchasing.

I also want to clarify our intended use against your Terms of Service. The application would:

- store historical API responses/statistics in our own database;
- show selected factual player/team statistics in our own interface;
- calculate proprietary derived metrics, rankings and scores from those statistics;
- never resell or redistribute the raw API feed as a competing data product.

Your current terms state that API-Football does not provide the licence/permission required for publication of supplied data and that any necessary permission must be obtained from the competent rights holders.

Could you clarify:

- For the six competitions above, what specific additional licence or rights-holder permission would you expect an analytics website to obtain in order to display player statistics sourced from API-Football?
- Does your own permission cover storage/caching of historical API data in our database while we are subscribed?
- If we subscribe for one month, collect historical data, and later return to the free plan, may we continue retaining the previously acquired historical records and our derived analytics, subject to any third-party publication rights?
- Is continued display of those previously acquired factual statistics after paid-plan expiry permitted by API-Football itself, again assuming any required third-party rights are separately satisfied?
- Are there competition-specific restrictions for Argentina, Premier League, La Liga, Serie A, Bundesliga or Ligue 1 that you can identify before we purchase?

Our goal is to resolve these questions before spending money or designing a production dependency around the feed.

Thank you.

## Cost rule if coverage and rights pass

Do not upgrade based on convenience alone.

For the player-season backfill estimated for Football Intelligence, the current Pro quota of 7,500 requests/day is already far larger than the expected roughly 1,500 paginated player-season requests across 60 league-seasons. Even a roughly 20k-25k match-player backfill could be distributed across multiple days within one prepaid Pro period.

Therefore Ultra/Mega should not be considered unless an observed workflow genuinely requires their daily throughput. Historical availability and rights, not request volume, are the current bottlenecks.
