# Wikipedia historical roster lab — ARG_LPF 2024

Audit date: 2026-08-25  
Canonical base: `main@e994c24ff7ce09c2c7c5499d27ed30fc1774ddfd`  
Status: technical/source-compliance spike; no source is promoted by this document.

## Decision question

Can a zero-cost Wikimedia path provide defensible historical player-to-club membership evidence for the 28 `ARG_LPF` clubs during Torneo LPF 2024 after the strict Wikidata `P54` temporal-membership lab proved insufficient as a roster source?

The intended evidence grain is **historical active-squad listing at a dated revision**, not `player used in Torneo LPF`, not AFA `Lista de Buena Fe`, and not canonical Football Intelligence player identity.

## Source and rights boundary

Wikipedia article text is reusable subject to Wikimedia's current Terms of Use and the applicable CC BY-SA attribution/share-alike requirements. Historical revisions are read through the official MediaWiki Action API with an identified User-Agent, bounded serial requests, `maxlag`, and bounded retries.

Primary references:

- https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use
- https://www.mediawiki.org/wiki/API:Revisions
- https://www.mediawiki.org/wiki/API:Etiquette
- https://www.mediawiki.org/wiki/API:FAQ

A critical temporal constraint was found during the spike: old article rendering is not sufficient evidence when the page transcludes templates, because MediaWiki transclusions are not versioned with the parent page. Therefore the accepted lab reads the **exact raw wikitext stored in each historical article revision** and counts only player rows physically present in that revision. Current/live template expansion is never treated as historical evidence.

## Snapshots

The English-Wikipedia lab samples the latest revision at or before:

- `2024-05-10T23:59:59Z` — Torneo LPF start;
- `2024-07-15T23:59:59Z`;
- `2024-09-06T23:59:59Z` — end of the reviewed AFA registration-window extension;
- `2024-12-16T23:59:59Z` — immediately after the final league date.

The parser accepts only explicit active-squad headings:

- `Current squad`;
- `First-team squad` / `First team squad`;
- `Senior squad`;
- `First team`;
- `Squad`.

It rejects the generic `Players` heading and stops before reserve, youth, academy, out-on-loan, former-player and notable-player subsections.

This stricter rule was added after the first immutable-wikitext run demonstrated a real false-positive: a broad `Players` section could represent notable/historical players rather than the active squad.

## Real run

Accepted strict run:

- branch commit: `9b5c46be8713847a20a597d09763b79d0fdbab12`;
- workflow run: `32914758141`;
- job: `98016043048`;
- artifact: `9587758988`;
- artifact digest: `sha256:a45e6191cf5ab314099614fc70f57549841855696499ebf8bddcf49ff6759e5e`;
- result: PASS as a technical experiment.

Repository Quality for the same commit was run `32914758033` / Quality #645 and completed successfully in Analytics, Database, and Web. This verifies repository health only; it does not certify the external data semantics.

## Aggregate result

- clubs in Torneo LPF 2024: **28**;
- clubs with exact-revision active-squad evidence: **26/28**;
- clubs without accepted English historical active-squad evidence: **Independiente Rivadavia** and **Vélez Sarsfield**;
- union of observed active-squad names across the four snapshots for the 26 covered clubs: **1,075 club-player memberships**;
- official LPF `JUGADORES UTILIZADOS` total for those same 26 clubs: **922**;
- clubs whose observed active-squad union is within ±20% of the LPF players-used count: **13/26**.

The `1,075` versus `922` difference is not treated as an error by itself because the two concepts differ. A player may be listed in an active squad without appearing in Torneo LPF, and the four-snapshot union deliberately retains players who entered or left the squad during the season window.

LPF's official player-used counts remain an independent reasonableness check, not an equality target.

## Per-club observed union

| Club | Wikipedia active-squad union | Official LPF players used |
| --- | ---: | ---: |
| Argentinos Juniors | 42 | 32 |
| Atlético Tucumán | 35 | 29 |
| Banfield | 37 | 43 |
| Barracas Central | 35 | 34 |
| Belgrano | 45 | 35 |
| Boca Juniors | 51 | 39 |
| Central Córdoba (SE) | 50 | 44 |
| Defensa y Justicia | 43 | 37 |
| Deportivo Riestra | 52 | 36 |
| Estudiantes de La Plata | 40 | 37 |
| Gimnasia La Plata | 39 | 39 |
| Godoy Cruz | 36 | 40 |
| Huracán | 31 | 29 |
| Independiente | 42 | 33 |
| Independiente Rivadavia | 0 | 38 |
| Instituto | 34 | 26 |
| Lanús | 43 | 34 |
| Newell's Old Boys | 39 | 43 |
| Platense | 58 | 35 |
| Racing Club | 39 | 32 |
| River Plate | 41 | 37 |
| Rosario Central | 45 | 36 |
| San Lorenzo | 41 | 38 |
| Sarmiento | 43 | 37 |
| Talleres de Córdoba | 41 | 34 |
| Tigre | 45 | 35 |
| Unión Santa Fe | 28 | 28 |
| Vélez Sarsfield | 0 | 33 |

## Spanish-Wikipedia probe for the two English gaps

A separate disposable branch, `lab/wikipedia-es-missing-arg-lpf-roster`, probed exact 2024 Spanish-Wikipedia revisions for the two missing clubs.

Run `32914968790` / commit `fb8444db0c6bbf2f4fc9d3ed7f753c70546c5c4f` completed successfully. Its first parser under-counted both sections because Spanish pages use a different table/template structure, so its raw counts (`7` and `6`) are **not coverage measurements**.

The probe still yielded an important provenance distinction:

- Independiente Rivadavia's `Plantel y cuerpo técnico 2024` section explicitly cites Transfermarkt as its roster source. Under the repository's current source policy, a downstream Wikipedia representation must not be used to bypass the already-rejected Transfermarkt backbone/compliance boundary. It remains unresolved from this route.
- Vélez Sarsfield's `Plantel 2024` section explicitly cites the club's official `Plantel profesional y Cuerpo técnico` page. This is a potentially usable gap-filling path, but a correct Spanish-table extractor or another primary historical snapshot is still required before claiming coverage.

Quality run `32914968703` / #647 also completed successfully across Analytics, Database, and Web for that isolated probe branch.

## Decision

### Accepted conclusion

Historical Wikipedia revisions are **useful zero-cost player-to-club membership evidence** for ARG_LPF 2024.

They are not certified as:

- the AFA registered `Lista de Buena Fe`;
- the complete set of players used in Torneo LPF;
- match-level participation evidence;
- a performance-statistics source;
- an automatic canonical-player crosswalk.

The current measured coverage is strong but partial: **26/28 clubs** have defensible exact-revision active-squad evidence on the English-Wikipedia path.

### Source role

If retained after a production-oriented source review, the intended role is:

```text
OpenFootball
  -> competition / club / fixture spine

Wikipedia exact historical revisions
  -> dated observed active-squad membership evidence
  -> preserve page title, revision id, revision timestamp, acquisition timestamp,
     licence/attribution metadata, raw name/article target, team context

LPF official final report
  -> independent per-club players-used validation totals

Wikidata
  -> profile / identity enrichment after an explicit Wikipedia article/QID bridge
```

A Wikipedia squad observation must remain source-scoped and dated. Absence from a snapshot is **missing evidence**, never proof that the player was not registered or did not play.

## Highest-leverage next experiment

Do not spend money and do not build a production adapter yet.

The next bounded experiment should retain each Wikipedia player's linked article target and resolve its `wikibase_item` through the MediaWiki API. This can create a deterministic Wikipedia-article → Wikidata-QID bridge without fuzzy player-name matching, then reuse the already-audited Wikidata profile parser for DOB/citizenship/position/height coverage.

That experiment should report:

1. unique observed squad memberships and unique article targets;
2. article-target uniqueness inside each club/snapshot;
3. percentage with a Wikidata QID;
4. QID conflicts or redirects;
5. profile-field coverage after the bridge;
6. the unresolved clubs separately, with no synthetic completion.

Only after that identity/profile gate should Football Intelligence decide whether to turn this lab into a retained source adapter.