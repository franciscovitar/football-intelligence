# ARG_LPF 2024 zero-cost roster gap audit

Audit date: 2026-08-25  
Canonical base: `main@e994c24ff7ce09c2c7c5499d27ed30fc1774ddfd`  
Status: source feasibility/gap audit; no source promoted to canonical product storage by this document.

## Constraint

Football Intelligence must continue this Argentina coverage work with **zero paid-data spend**. Free access alone is not sufficient: a source must also have defensible provenance, temporal meaning, and a source role that does not silently bypass provider rights or existing project policy.

## Starting point

The strict English-Wikipedia historical-revision lab produced defensible dated active-squad observations for **26/28** Torneo LPF 2024 clubs.

The two English-path gaps were:

- Vélez Sarsfield;
- Independiente Rivadavia.

This audit determines whether either gap can be closed without paying and without weakening provenance rules.

---

## Vélez Sarsfield — accepted primary-source gap fill

Vélez's own website published dated first-team convocation lists across Torneo LPF 2024. These are primary club evidence that named players were selected into the competitive first-team group for specific league matches.

Bounded season-spanning sample:

1. 2024-05-20 — Fecha 2 vs Newell's  
   https://velez.com.ar/futbol/notas/2024/05/20/151533_convocados-vs-newells
2. 2024-06-13 — Fecha 5 vs Boca  
   https://velez.com.ar/futbol/notas/2024/06/13/183759_convocados-vs-boca
3. 2024-08-10 — Fecha 10 vs Banfield  
   https://velez.com.ar/futbol/notas/2024/08/10/175817_convocados-vs-banfield
4. 2024-09-22 — Fecha 15 vs Estudiantes  
   https://velez.com.ar/futbol/notas/2024/09/22/154131_convocados-vs-estudiantes
5. 2024-10-17 — Fecha 18 vs River  
   https://velez.com.ar/futbol/notas/2024/10/17/162457_convocados-vs-river
6. 2024-11-10 — vs Deportivo Riestra  
   https://velez.com.ar/futbol/notas/2024/11/10/122635_convocados-vs-dep-riestra
7. 2024-12-14 — final league match vs Huracán  
   https://velez.com.ar/futbol/notas/2024/12/14/153037_convocados-vs-huracan

The union of the seven observed convocation lists contains **37 unique players**:

- Aarón Quirós
- Agustín Bouzat
- Agustín Lagos
- Alejo Sarco
- Benjamín Bosch
- Braian Romero
- Christian Ordóñez
- Claudio Aquino
- Damián Fernández
- Elías Cabrera
- Elías Gómez
- Emanuel Mammana
- Felipe Bussio
- Francisco Montoro
- Francisco Pizzini
- Jalil Elías
- Joaquín García
- Juan Ignacio Méndez
- Lautaro Garzón
- Lenny Lobato
- Leo Jara
- Leonel Roldán
- Maher Carrizo
- Matías Pellegrini
- Michael Santos
- Nicolás Garayalde
- Patricio Pernicone
- Randall Rodríguez
- Rodrigo Piñeiro
- Santiago Cáseres
- Thiago Fernández
- Thiago Vecino
- Tomás Cavanagh
- Tomás Guidara
- Tomás Marchiori
- Valentín Gómez
- Álvaro Montoro

The independent LPF final-report reasonableness count for Vélez was **33 players used**. The observed 37-player convocation union is not required to equal 33 because `convoked for at least one match` and `actually used in the competition` are different facts.

### Vélez source role

Accepted for the gap audit as:

`dated first-team competitive convocation evidence`

Not claimed as:

- complete AFA registration list;
- exact complete Torneo player-used set;
- proof that every convoked player appeared;
- performance statistics;
- an open-licensed bulk dataset.

The club's 2024 audited balance also contains an Anexo I titled `Plantel profesional de fútbol` at 2024-06-30, which supports the existence of a first-party professional-squad record. It is accounting/professional-squad context, not a match-roster substitute:

https://velez.com.ar/pdf/2024-balance-general.pdf

### Vélez decision

**Gap sufficiently closed for dated zero-cost first-team membership/selection evidence.**

---

## Independiente Rivadavia — remains unresolved

### Current club page rejected as historical 2024 evidence

The club's current football page contains a table labelled:

`Plantilla del Club Sportivo Independiente Rivadavia de la temporada 2024`

Source:

https://independienterivadavia.com.ar/csir/futbol

The page fails the temporal-integrity gate. The alleged 2024 table substantially mirrors current/later roster content, includes present-style ages and contract dates extending through 2025–2027, and conflicts with contemporary May 2024 official LPF match evidence.

A concrete counterexample is the official LPF Sarmiento vs Independiente Rivadavia match sheet from 2024-05-26, which records players including Mauro Maidana, Ezequiel Ham, Matías Reali, Tobías Ostchega, Lautaro Ríos, Francisco Petrasso, Franco Romero, Mauricio Asenjo, Gonzalo Marinelli, Matías Ruiz Díaz and Tomás Palacios, plus used substitutes Gastón Gil Romero, Victorio Ramis, Juan Cavallaro and Antonio Napolitano:

https://www.ligaprofesional.ar/ficha-partido?competition=724&match=2420290&season=2024

Therefore the current club table is not accepted merely because its heading says `2024`.

### Spanish Wikipedia route rejected

The exact-2024 Spanish-Wikipedia probe found that the Independiente Rivadavia 2024 squad section cited Transfermarkt as its source. Football Intelligence must not use a downstream Wikipedia representation to bypass the already-recorded Transfermarkt compliance/provenance boundary.

### LPF match-sheet route not promoted to backbone

LPF official match sheets are strong primary evidence for individual match participation and can be used as bounded validation observations. In principle, unioning all match sheets could reconstruct the exact set of players used.

However, LPF's published General Regulations reserve/commercialize official statistical data and the joint exploitation of official match statistics. The website's privacy policy does not grant a reusable data licence. Therefore this audit does **not** promote bulk LPF match-sheet/statistical ingestion as a zero-cost reusable backbone without separate permission/licence clarification.

### Other free web/repository candidates

A directed search found historical roster/stat pages on ESPN, FBref, UniversoFútbol and public GitHub repositories containing scraped/provider-derived football data. Free access or public GitHub hosting does not establish reusable rights over the underlying provider data.

At least one candidate repository explicitly documents scraping Sofascore, FotMob and FBref to create its CSV files. Such repositories are not accepted as provenance-safe substitutes for the original providers.

### Independiente Rivadavia decision

**Unresolved from a clean zero-cost reusable historical roster source.**

Missing evidence remains missing. No synthetic roster completion is permitted.

---

## Aggregate zero-cost decision

Current defensible ARG_LPF 2024 membership coverage is:

- **26/28** clubs from exact historical English-Wikipedia active-squad revisions;
- **+ Vélez Sarsfield** from dated primary club convocation evidence;
- **Independiente Rivadavia unresolved**.

Therefore the current defensible zero-cost coverage is **27/28 clubs**, not 28/28.

This is membership/selection evidence, not a certified complete player-used dataset.

## Recommended architecture

```text
OpenFootball
  -> competition / clubs / fixtures / results spine

Wikipedia exact historical revisions (26 clubs)
  -> dated active-squad membership observations
  -> CC BY-SA attribution/provenance retained

Vélez official dated convocation posts
  -> first-party match-selection evidence for the English-Wikipedia gap

Independiente Rivadavia
  -> explicit missing source coverage until a clean historical source appears

Wikipedia article -> Wikidata human-QID bridge
  -> identity/profile enrichment where deterministic and P31-human validated

Wikidata
  -> provider-local DOB / citizenship / position / height enrichment
  -> current fact timestamps/revisions preserved

LPF official material
  -> bounded validation / reasonableness checks unless reuse rights are separately cleared
```

## Next decision

Do **not** block the Argentina pipeline on one unresolved club and do not pay for a provider merely to hide that gap.

The highest-leverage next engineering step is to design a retained evidence adapter for the accepted zero-cost source roles while preserving source-specific licensing/provenance and leaving Independiente Rivadavia as explicit missing coverage. Before implementation, the Wikipedia article→Wikidata bridge must incorporate the stricter human/player-link gate documented in `docs/audits/wikipedia-wikidata-arg-lpf-2024-profile-coverage.md`.
