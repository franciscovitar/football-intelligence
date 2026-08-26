# Futbol360 — Argentina 2016 feasibility

Status: **technical value observed / automated acquisition NO-GO without permission**.

## Decision question

Can Futbol360 provide a zero-cost, defensible player-data source for the early-2016 Argentina gap that remains after the public soccer data-lake audit?

## Public evidence

Futbol360 publicly describes itself as a project intended to collect, publish and share football information and says that it wants statistical information to be accessible in a complete and free way. Public team/player pages expose useful historical fields such as:

- appearances (`PJ`);
- minutes (`MJ`);
- starts (`Tit.`);
- substitute usage (`Sup.`);
- goals;
- penalties;
- yellow/red cards;
- `Puntaje medios`, a media-derived rating signal.

The site also explicitly warns that displayed statistics can be relative/incomplete when relevant tournaments have not yet been entered into its database. Historical player-season rows can aggregate multiple teams or competitions, so a generic season row cannot be assumed to equal one league season.

No formal machine-data licence, terms granting automated reuse, or explicit commercial redistribution permission was found during the bounded public documentation review. Statements about sharing/free access are therefore not treated as a product licence.

## Bounded runtime probe

Branch: `lab/futbol360-arg-2016-feasibility`.

GitHub Actions run: `32996812616`.

The experiment made one request only, to the public Lanús team page, for the purpose of inspecting historical selector semantics. It identified itself as a Football Intelligence source audit and did not attempt login, hidden endpoints, proxying, CAPTCHA bypass, or rate-limit evasion.

Observed result:

- `GET https://www.futbol360.com.ar/equipos/argentina/lanus/`
- HTTP `403`

Because the site rejects the automated request, the spike stopped immediately. No alternative user agents, IP rotation, mirror scraping, browser impersonation, or hidden API discovery was attempted.

## Decision

Futbol360 remains useful as a **manual/public corroboration candidate** and its media-rating concept is aligned with Football Intelligence's policy of preserving provider/model outputs as source-specific evidence. However, it is not an approved automated source.

Current source state:

`rejected_automated_access_permission_required`

Do not:

- automate crawling/scraping against the observed 403;
- treat search-engine cached/indexed text as a bulk acquisition route;
- promote season aggregates to league-season facts without competition-level scope;
- treat `Puntaje medios` as an objective event statistic;
- infer commercial/republication rights from the site's community/free-access philosophy.

Reconsider only if Futbol360 explicitly grants permission for automated historical extraction/reuse and clarifies the scope/methodology of its tournament filters and media ratings.

## Useful manual observations retained for future comparison

Publicly indexed pages demonstrate that the source may contain:

- player/team historical appearances and minutes;
- starts/substitution evidence;
- goals/cards;
- media-derived average ratings;
- tournament-labelled match pages.

These observations justify contacting the publisher if the remaining Argentina gap cannot be solved by a source with clearer open-data rights.
