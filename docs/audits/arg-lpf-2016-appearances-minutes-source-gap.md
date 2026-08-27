# ARG_LPF 2016 appearances/minutes source-gap audit

Status: **bounded source review closed — no zero-cost, reusable appearances/minutes backbone identified for V1**.

Date: `2026-08-27`

## Decision question

After closing the AFA Stats Center, PlayerElo, and Wikipedia routes for the short Argentine Primera División 2016 tournament, is there another source that can provide broad player appearances and ideally minutes while satisfying Football Intelligence's zero-cost-first, provenance, identity, semantic, and compliance guarantees?

This audit is a sourcing decision only. It creates no `PlayerCrosswalk`, no PostgreSQL rows, no production adapter, and no canonical player-season facts.

## Project constraints

The governing project decisions remain:

- `docs/V1_ZERO_COST_HISTORICAL_DATA_STRATEGY.md`: V1 should not depend on recurring paid data-provider cost when a defensible free multi-source solution is sufficient;
- `docs/MULTI_SOURCE_PLAYER_EXPANSION.md`: a source may be technically ingestible but remain blocked from product promotion by licence/compliance; missing is never silently converted to zero; player identity cannot be resolved by fuzzy/name-only matching;
- existing source prohibitions for FBref/Sports Reference and other presentation-site scraping remain in force unless deliberately re-audited.

The target competition is the short `ARG_LPF` 2016 tournament, February-May 2016, preserving regular-season/final/playoff scope instead of collapsing all calendar-2016 football into one value.

## Sources already closed before this review

### AFA official material

AFA's surviving `#NúmerosDePrimera` prose remains a **GO for official, source-scoped partial evidence**. The prior audit is `docs/AFA_ARG_2016_REFINED_SIGNALS_AUDIT.md` on its dedicated lab branch.

It can establish isolated appearance denominators where explicitly printed, for example Gerónimo Poblete `61 / 14 = 4.4` in the recoveries article. It is not a full player-population appearance/minutes table.

The extinct Stats Center embedded by those articles was already closed as **NO-GO for V1 archive reconstruction** after bounded live/Wayback probes returned no player-row payload.

### PlayerElo

`context=full` is technically capable of match/player context and minutes where coverage exists, but real probes for Iván Marcone and Gerónimo Poblete showed no rows during the February-May 2016 tournament. Lanús club history did not recover the missing fixtures.

Therefore PlayerElo remains **technical GO where covered, period-specific NO-GO for short ARG 2016**.

### Wikipedia individual player pages

The dedicated audit `docs/audits/wikipedia-arg-lpf-2016-player-appearances-audit.md` measured only `272 / 903 = 30.12%` exact-competition, single-value parseable candidates from the historical roster population and found current/historical/official conflicts.

Wikipedia remains **CONDITIONAL GO for source-scoped corroboration**, **NO-GO as automatic appearance/minutes backbone**.

### FBref / Sports Reference

FBref exposes exactly the type of season playing-time fields required, but the repository already rejects Sports Reference presentation-site data as an automated product backbone under its current use restrictions. This review does not reopen or bypass that decision.

## Bounded new source review

### RSSSF — reusable and useful, but not a full participation backbone

Source:

`https://www.rsssf.org/tablesa/arg2016.html`

The RSSSF Argentina 2016 document is unusually useful from a compliance perspective. Its document notice states that the document may be copied in whole or in part provided proper acknowledgement is given to the author.

Observed useful scope:

- full short-tournament fixture/results chronology;
- final tables and competition structure;
- explicit separation of the May 28 third-place/Libertadores playoff and May 29 final;
- a detailed Lanús-San Lorenzo final match sheet containing starters, substitutes, substitution times, cards, captaincy and officials.

Limitation:

The document does **not** expose equivalent detailed lineups/substitution times for the full 242-match competition. It therefore cannot produce complete player appearances/minutes by itself.

Decision:

**GO for match/competition structure and the individual detailed match records it actually publishes; NO-GO as full player appearances/minutes backbone.** Preserve RSSSF author attribution for any retained evidence.

### OpenFootball — rights-friendly, wrong grain for this gap

Authoritative project family:

`https://github.com/openfootball`

OpenFootball is already treated by the repository as a permissively licensed/public-domain match/result reconciliation source, with separate player-profile repositories considered only as profile corroboration.

Its current Football Intelligence role is fixture/result/team evidence rather than complete player participation/minutes for this competition.

Decision:

**RIGHTS GO / TECHNICAL NO-GO for the ARG_LPF 2016 player appearances/minutes gap.** Do not manufacture player participation from team fixtures.

### FootyStats — technically strong, V1/compliance blocked

Dataset catalogue:

`https://footystats.org/argentina/primera-division/datasets`

API documentation / terms:

`https://footystats.org/api/`

Observed technical fit:

- the catalogue explicitly lists `2016/2016` with `242` match rows, `30` team rows and `864` player rows;
- its player API schema documents `appearances_overall` and `minutes_played_overall` plus team/competition identity and other player-season fields.

Current compliance/cost findings:

- the public-site terms prohibit automated/non-human access and systematic retrieval to build a database without written permission;
- the supported programmatic route is the API;
- API access is a subscription product rather than a zero-recurring-cost V1 source;
- API terms restrict resale/redistribution of API data.

Decision:

**TECHNICAL GO / V1 ZERO-COST + AUTOMATED ACQUISITION NO-GO.** Keep as a future paid/provider fallback only. Do not scrape the public CSV/page route to evade the API product.

### Football-Lineups — technically relevant, licence blocked

Example family:

`https://www.football-lineups.com/`

Observed technical fit:

The site contains exact short-2016 competition pages and historical match lineups/substitution events.

Current terms state that the site/content licence is for personal, non-commercial purposes and restrict copying/reproduction/commercial exploitation and automated scripts without permission.

Decision:

**TECHNICAL POSSIBLE / PRODUCT RIGHTS NO-GO without written permission.** No automated acquisition or production promotion.

### BDFutbol — useful historical product, paid API

Player example:

`https://www.bdfutbol.com/es/j/j15095.html`

API:

`https://www.bdfutbol.com/es/c/api2.html`

Observed technical fit:

BDFutbol publishes season participation/minutes and operates a formal historical JSON API.

Current cost finding:

The current API v2 is subscription-based; the published tiers include paid historical access (for example 20 seasons and an all-history tier). No open licence was found that would justify systematic extraction of the presentation site as a free substitute for the API.

Decision:

**TECHNICAL GO / V1 ZERO-COST NO-GO.** Future paid fallback only unless BDFutbol grants a suitable licence.

### oGol / zerozero — rich historical match data, no open reuse grant established

Example:

`https://www.ogol.com.br/jogador/ivan-marcone/86922/jogos?competicao_id=70&epoca_id=145`

Observed technical fit:

The player competition view can expose appearances, starts/sub appearances and minutes for Campeonato Argentino 2016.

Compliance finding:

The site identifies its database as ZOS-owned and displays `Todos os direitos reservados`. This review did not find an explicit open-data licence or product reuse grant permitting Football Intelligence to systematically copy the database.

Decision:

**TECHNICAL GO / LICENCE NOT ESTABLISHED => NO-GO for automated V1 ingestion.** Re-open only with explicit reuse permission or a provider agreement.

### Global Sports Archive / Data Sports Group — technically rich commercial candidate

Competition page:

`https://globalsportsarchive.com/en/soccer/competition/primera-division-2016/11227`

Provider API:

`https://datasportsgroup.com/products-api/`

Observed technical fit:

Global Sports Archive resolves the exact Primera División 2016 competition and exposes competition-specific fixtures and multiple player leader/stat families. The site is powered by Data Sports Group. DSG markets an authenticated sports-data API and directs product integrators to sign up for an API key or contact its sales team.

This bounded review did not establish a zero-cost open-data licence allowing Football Intelligence to persist and redistribute the historical player dataset.

Decision:

**TECHNICALLY STRONG / COMMERCIAL-LICENCE REVIEW REQUIRED.** Treat as a future provider candidate, not an approved zero-cost source. Do not infer that a free signup/demo equals a free production-data licence.

## Cross-source disagreement proves scope matters

The source gap is not just a coverage problem. Even high-quality commercial/statistical sites can disagree on the same player-season label.

Example: Iván Marcone / Lanús / `2016`:

- FBref domestic league presentation: `13` MP / `986` minutes;
- BDFutbol presentation: `13` appearances / `989` minutes;
- oGol Campeonato Argentino 2016 view: `14` matches / `1081` minutes.

These values must **not** be averaged or silently reconciled. The discrepancy may involve competition scope, inclusion of the final, minute conventions, source corrections, or another provider-semantic difference. Until match-level provenance resolves it, Football Intelligence must preserve each claim as provider-scoped evidence rather than select a convenient canonical number.

The same principle was already demonstrated by Gerónimo Poblete:

- Wikipedia historical revision: `12`;
- Wikipedia current revision: `15`;
- AFA official prose denominator: `14`.

## Official AFA planillas: authoritative evidence exists, public corpus not found

AFA disciplinary material confirms the semantics of an official match sheet: players may be registered on the front, while substitutions/entries are recorded on the reverse; merely signing the sheet does not prove that a player actually entered the match.

This is important because it establishes that AFA's underlying match paperwork could, in principle, resolve participation accurately.

However, this bounded search did **not** find a publicly downloadable, competition-complete corpus of the 2016 Primera match sheets. References to sheets inside disciplinary case files are not equivalent to an open dataset.

Decision:

**AUTHORITATIVE IN PRINCIPLE / ACQUISITION NOT AVAILABLE.** Re-open only if AFA/LPF exposes the actual historical sheets or provides an export/access route.

## Final decision

### Complete zero-cost appearances/minutes backbone for ARG_LPF 2016

**NO-GO with the currently identified sources.**

No reviewed source simultaneously satisfies all of:

1. the exact short-2016 competition scope;
2. broad player-population coverage;
3. appearances plus preferably minutes;
4. stable player/team identity context;
5. automated acquisition allowed;
6. zero recurring provider cost for V1;
7. reuse/persistence rights defensible for Football Intelligence.

Do not weaken the gates merely to fill the column.

### What Football Intelligence can safely retain

The V1 can still assemble useful ARG_LPF 2016 evidence from multiple source roles:

- historical roster snapshot: Spanish Wikipedia historical revisions, with CC BY-SA revision attribution and no appearance claim;
- official refined partial facts / isolated appearance denominators: surviving AFA prose;
- exact competition fixtures/results and competition structure: RSSSF with author acknowledgement and/or an already-approved permissive match source where available;
- detailed final-match participation/substitution evidence: RSSSF final record;
- partial player appearance corroboration: exact competition-linked Wikipedia rows, revision-scoped and subordinate to stronger evidence;
- missing appearances/minutes: remain unknown for the remainder.

There is still **no defensible complete minutes layer** for this competition in the zero-cost V1 evidence set.

## Deferred paid/provider shortlist

If V1 later permits recurring provider spend or a special historical acquisition, the most promising reviewed candidates are:

1. FootyStats — strongest explicit player-row/appearance/minute fit observed in this review;
2. Data Sports Group / Global Sports Archive — broad historical competition/player coverage, commercial integration path;
3. BDFutbol — formal historical API and season participation/minutes;
4. PlayerElo — valuable match/minute context where historical coverage actually exists, but not this tournament and with persistence/licensing questions still requiring resolution.

Any future paid choice still requires a written licence/storage/persistence/redistribution review before promotion.

## Stop condition and next action

The bounded search is closed. Do **not** spend more V1 time scraping additional proprietary presentation sites for the same 2016 minute totals.

Re-open the ARG_LPF 2016 minutes gap only if one of these changes occurs:

- AFA/LPF exposes historical official match sheets or a structured export;
- a genuinely open/licensed academic dataset covering the tournament is discovered;
- a candidate provider grants suitable persistence/product rights at an accepted cost;
- API-Football or another provider answers the existing rights questions in a way that makes an already-identified historical dataset defensible.

Otherwise, move the zero-cost expansion effort to the next competition/season/data dimension with a higher expected evidence return while retaining ARG_LPF 2016 missingness explicitly.