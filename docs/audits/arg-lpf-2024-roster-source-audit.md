# ARG_LPF 2024 roster / player-season source audit

Audit date: 2026-08-25  
Canonical base: `main@e994c24ff7ce09c2c7c5499d27ed30fc1774ddfd`  
Status: technical/source-compliance spike; no source promoted to product by this document.

## Decision question

Can Football Intelligence acquire a legitimate static or historical source that is sufficiently complete to establish who belonged to, or at minimum actually played for, each of the 28 `ARG_LPF` clubs during the 2024 Torneo LPF, while preserving provenance and without weakening the project's source-compliance or identity rules?

This audit follows the existing multi-source invariants:

- a technically accessible source is not automatically product-approved;
- publication on a website is not evidence of bulk-reuse permission;
- downstream mirrors do not cure upstream data-rights problems;
- `registered roster`, `matchday roster`, and `players actually used` are different grains;
- missing roster evidence is not equivalent to absence from the roster;
- no fuzzy name matching may create canonical player identity.

## Relevant prior evidence

The separate lab branch `lab/wikidata-arg-lpf-2024-roster` measured whether Wikidata `P54` could establish the 2024 roster from temporal club-membership evidence. Run `32911618200` on commit `72764bac9ce5e0888cdfa653c353e9f040cc1179` found only 15 unique players whose bounded `P580`/`P582` evidence guaranteed overlap with the Torneo LPF 2024 window. The lab decision was `C_insufficient` for roster construction. Wikidata remains useful as a profile/identity enrichment source after player names are known.

That lab is not merged to `main` and this source audit does not promote its experimental code.

## Roster semantics established by AFA

AFA's 2024 regulations establish an authoritative roster concept even though no public season-wide export was located during this audit.

AFA Boletín 6542, dated 2024-08-21, modified the Torneo LPF 2024 registration window and states that player registrations must be made through COMET and FIFA TMS. Its Article 19.2 says clubs incorporating players between 2024-05-09 and 2024-09-06 had to expressly request their inclusion in the `Lista de Buena Fe` through AFA's COMET department.

Primary reference:

- https://assets1.afa.com.ar/torneo/Stefi/Boletin-Resoluciones-6542-%2821-08-2024%29.pdf

Interpretation for Football Intelligence:

- the AFA/COMET `Lista de Buena Fe` is the best authoritative concept for a **registered / eligible roster**;
- no public, league-wide 2024 named export of that COMET list was found;
- therefore COMET is a semantic/validation authority, not currently an acquireable ingestion source.

## Official LPF static validation evidence

LPF publishes an official final static report for Torneo LPF 2024:

- https://www.ligaprofesional.ar/wp-content/uploads/2025/01/LPF-Data-Datos-Oficiales-Torneo-LPF-2024.pdf

The report identifies Atenea Inteligencia Deportiva as the official processing/analysis provider and Opta - Stats Perform as the official data provider.

The report includes an official `JUGADORES UTILIZADOS` count for all 28 clubs:

| Club | Players used |
| --- | ---: |
| Central Córdoba (SE) | 44 |
| Banfield | 43 |
| Newell's Old Boys | 43 |
| Godoy Cruz | 40 |
| Boca Juniors | 39 |
| Gimnasia La Plata | 39 |
| Independiente Rivadavia | 38 |
| San Lorenzo | 38 |
| Defensa y Justicia | 37 |
| Estudiantes de La Plata | 37 |
| River Plate | 37 |
| Sarmiento | 37 |
| Deportivo Riestra | 36 |
| Rosario Central | 36 |
| Belgrano | 35 |
| Platense | 35 |
| Tigre | 35 |
| Barracas Central | 34 |
| Lanús | 34 |
| Talleres de Córdoba | 34 |
| Independiente | 33 |
| Vélez Sarsfield | 33 |
| Argentinos Juniors | 32 |
| Racing Club | 32 |
| Atlético Tucumán | 29 |
| Huracán | 29 |
| Unión Santa Fe | 28 |
| Instituto | 26 |

Sum across clubs: **993 club-player usages**.

This is not a list of names and is not equivalent to the registered `Lista de Buena Fe`. It is, however, a high-value official validation target for any reconstructed **players actually used** roster: after resolving transfers/team contexts, a candidate source should be explainable against these club-level totals rather than being accepted solely because it returns many rows.

The same LPF Data series publishes other official aggregate player/team metrics and leaderboards, but the public reports do not establish a licence to ingest or redistribute the underlying Opta/Stats Perform structured feed.

## Source matrix

| Source / path | What was verified for ARG_LPF 2024 | Provenance / rights | Roster role | Audit decision |
| --- | --- | --- | --- | --- |
| OpenFootball | Static 2024 Primera División fixture/result coverage: 28 clubs, 378 matches; club aliases available separately | Open/public-domain path already accepted by the repository | Fixture/team spine only; no players | **Keep** as deterministic competition/team/match context |
| AFA COMET `Lista de Buena Fe` | Official regulations prove the registered-roster concept and 2024 inclusion workflow | Primary AFA authority, but no public league-wide named export found | Ideal registered-roster authority if an authorized export becomes available | **Authority, not ingestible source today** |
| LPF final Torneo 2024 report | Official static report; exact player-used counts for all 28 clubs; selected player/team leaderboards | Primary LPF publication; underlying data explicitly credits Opta/Stats Perform | Validation for used-player roster and selected published facts; not a complete named roster | **Use as validation/reference evidence only** unless structured reuse rights are separately established |
| LPF match sheets / embedded data modules | Public match pages can expose starters/substitutes/positions and therefore could technically reconstruct observed matchday participation | Current LPF modules are supplied through commercial data infrastructure; publication does not establish bulk extraction/reuse rights | Potentially enough to reconstruct observed matchday/appearance roster | **Do not build a scraper/collector without explicit permission/licensed feed** |
| DataFactory commercial feed/widgets | DataFactory markets licensed football data products; current terms reserve copying/reproduction/distribution/derivative use without written consent | Commercial contract required; website terms are restrictive | Possible licensed historical lineup/roster route if a suitable export/feed exists | **Commercial inquiry candidate**, not a scraping source |
| FootyStats CSV/API | Public dataset catalogue explicitly lists Argentina Primera División `2024/2024`: 378 match rows, 28 team rows, **1120 Players CSV rows**. The 2024 player download link uses `comp=11212`. Public schema docs describe 45+ player CSV fields including name, position, club, minutes, nationality, appearances, goals and assists. The `league-players` API is season-scoped and paginated at 200 players/page. | API terms allow using data to create websites/apps but prohibit resale/redistribution. Site terms prohibit systematic site extraction; FootyStats itself directs programmatic downloads to its API. Paid Argentina access still requires subscription. | Strongest currently visible bounded trial candidate for player-season/used-player coverage | **Next empirical trial candidate; not approved until ARG_LPF 2024 payload is actually acquired/audited** |
| Transfermarkt / Transfermarkt-derived datasets | Broad profile/career datasets exist and AR1N-derived data can be found publicly | Existing repo review rejects Transfermarkt as automated product backbone; third-party mirrors do not cure upstream rights | Technically useful but compliance boundary fails | **Reject as product backbone** |
| FBref / Sports-Reference-derived snapshots | Player metrics can be found through libraries/mirrors | Existing repo review rejects automated product use under current Sports-Reference restrictions | Technically useful but compliance boundary fails | **Reject as product backbone** |
| Sofascore / scraping libraries | Argentina player statistics are technically obtainable through community scraping tools | No reusable product licence established by this audit | Could populate player-season/performance fields | **Do not use as product backbone without rights audit/permission** |
| Kaggle / generic open datasets located in this audit | Public Argentina datasets located were match-only, outdated, video-game-style, or downstream from restricted sources; no qualifying clean 2024 player-season source found | Varies; downstream licence labels do not automatically establish upstream rights | None currently defensible | **No qualifying source found** |

## FootyStats: why it is now the highest-leverage next trial

Current public evidence is materially stronger than documentation alone:

1. The Argentina Primera División dataset catalogue has a concrete historical `2024/2024` entry.
2. It reports exactly **378 matches** and **28 teams**, matching the known Torneo LPF 2024 competition footprint.
3. It advertises a historical **Players CSV with 1120 rows**.
4. The player CSV schema explicitly includes `full_name`, `position`, `current_club`, minutes, nationality, appearances, goals, assists, discipline and per-90 fields.
5. The API `league-players` contract is explicitly season-scoped and says it returns players who participated in that league/season.
6. Programmatic use has a sanctioned API path rather than requiring site scraping.

Primary references:

- https://footystats.org/argentina/primera-division/datasets
- https://footystats.org/api/documentations/league-players
- https://footystats.org/api/documentations/player-individual
- https://footystats.org/api/documentations/terms-of-use-and-legal
- https://footystats.org/api

### Important unresolved discrepancy

The official LPF report sums to **993 club-player usages**, while FootyStats advertises **1120 player CSV rows** for the same 28-team/378-match 2024 league footprint.

That difference of **127 rows** must not be explained away before inspecting the real data. Plausible causes include, among others:

- players listed despite zero Torneo appearances;
- duplicate/team-transfer representations;
- different competition scope or roster semantics;
- historical/current-club semantics in the static export;
- source errors.

The existence of 1120 rows is therefore evidence that a rich historical player file exists, **not** proof that it is a clean Torneo-LPF-used-player roster.

The repository also already has an earlier FootyStats experiment (PR #42) showing that a public example `league-players` response can return hundreds of players but did not expose the advanced metrics being sought, and that the individual-player endpoint did not work with the tested real IDs. That prior result remains a reason to require empirical schema proof before purchase/integration.

## Exact bounded FootyStats trial gate

If spending is approved, the cheapest useful next experiment is one month of the smallest sanctioned API tier that can include Argentina Primera División. Do not build an adapter first.

Acquire only enough ARG_LPF 2024 data to answer these questions:

1. Does `comp=11212` correspond to the API season ID for Argentina Primera División 2024, or is a separate season ID required?
2. Does the complete paginated `league-players` result contain the advertised historical population?
3. How many rows have `appearances_overall > 0` and/or `minutes_played_overall > 0`?
4. After grouping by provider team context, how do used-player counts compare to LPF's official 28 club totals above?
5. How are intra-season transfers represented (`club_team_id`, `club_team_2_id`, duplicate rows, or another mechanism)?
6. Are player IDs stable/unique and usable for provider-local identity records?
7. What is real non-null coverage for DOB, nationality, position, minutes, appearances, goals and assists?
8. Are zero and missing distinguishable in the raw payload?
9. Which advertised `include=stats` fields are actually present for ARG_LPF 2024?
10. Do the API terms permit the exact intended Football Intelligence internal evidence/use pattern without redistributing the raw feed?

### Trial stop conditions

Stop and do not integrate if any of these is true:

- Argentina 2024 cannot be retrieved through the sanctioned API/export;
- team/player scope cannot be reconciled to the 28-club Torneo footprint;
- player-team season context is too ambiguous to validate against LPF counts;
- raw data terms are incompatible with the intended product use;
- missing/zero semantics cannot be preserved;
- identity fields are too weak to support conservative cross-source review.

Passing the roster trial would still not certify advanced Player V2 metric coverage. Performance fields require a separate empirical Metric Catalog audit.

## DataFactory / official-feed fallback

If FootyStats fails, the next defensible route is not scraping LPF widgets. It is a commercial inquiry to LPF/DataFactory/Stats Perform asking specifically for a **historical static Torneo LPF 2024 export** with explicit reuse terms.

The request should ask for, at minimum:

- provider player ID;
- full player name;
- date of birth if licensed;
- nationality;
- position;
- team ID/name;
- player-team effective dates or match-level lineup contexts;
- appearances/minutes;
- match IDs and lineups if available;
- delivery format and immutable snapshot capability;
- commercial/internal analytics rights;
- whether derived public metrics are permitted while raw redistribution remains prohibited.

DataFactory current public contact path:

- sales@datafactory.la
- https://www.datafactory.la/soporte/

Do not infer that the commercial product includes these fields until a schema/sample confirms them.

## Decision

### What we can say now

- **No zero-cost source found in this audit satisfies all roster gates**: named 2024 player-season scope, all 28 clubs, deterministic team context, acquireable static/history path, and sufficiently clear automated reuse rights.
- AFA/COMET defines the authoritative **registered roster**, but the league-wide 2024 list is not publicly acquireable from the evidence found.
- LPF provides strong official **validation evidence**, especially the 28 `players used` counts, but its public final report does not provide the full named roster.
- Scraping LPF/DataFactory, Transfermarkt, FBref or Sofascore to manufacture a free roster would weaken the project's compliance/provenance guarantees and is not approved.
- **FootyStats is the strongest next bounded trial candidate** because its public catalogue proves a concrete Argentina 2024 player file exists, with 378 matches, 28 teams and 1120 player rows, and because it offers a sanctioned API path. It is not yet a certified source.

### Recommended sequence

```text
OpenFootball 2024 fixture/team spine (already defensible)
    +
FootyStats ARG_LPF 2024 bounded paid trial
    -> empirical roster/player-season schema audit
    -> compare every club against official LPF players-used totals
    -> if acceptable: freeze immutable snapshot + manifest
    -> Wikidata profile/identity enrichment
    -> separate performance Metric Catalog audit

if FootyStats fails
    -> licensed historical export inquiry: LPF / DataFactory / Stats Perform
```

Do not expand Europe before this Argentina roster gate is resolved.
