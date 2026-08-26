# Strict Wikipedia → Wikidata bridge — ARG_LPF 2024

Audit date: 2026-08-25  
Canonical base: `main@e994c24ff7ce09c2c7c5499d27ed30fc1774ddfd`  
Status: completed identity/profile enrichment lab on an isolated branch; no canonical-player, database, product, or source-promotion write.

## Question

After the first Wikipedia → Wikidata experiment exposed an annotation-link false positive, how much deterministic identity/profile coverage remains when Football Intelligence uses the retained historical-squad parser, accepts only a Wikipedia article link that syntactically starts the player name, and then requires the resolved Wikidata item to be explicitly `P31 = human`?

The evidence role remains narrow:

- Wikipedia exact historical revision: dated active-squad membership observation;
- Wikipedia article target: provider-local identity evidence;
- Wikidata QID: provider-local identity/profile enrichment;
- no AFA registration claim;
- no Torneo appearance claim;
- no performance-statistics claim;
- no Football Intelligence canonical-player claim.

## Retained parser gate

The run imports and uses `analytics/src/football_intelligence/providers/wikipedia_historical_squads.py`, rather than carrying forward the looser bridge regex.

The parser contract relevant to this run is:

1. raw wikitext must come from the exact historical article revision;
2. only explicit active-squad headings are accepted;
3. reserve/youth/notable/former/out-on-loan child sections are excluded;
4. a player article target is retained only when a wiki link begins the player-name value;
5. annotation-only links such as `Lucas Lopez (on loan from [[CA Nueva Chicago]])` are not player links;
6. a resolved Wikidata item is accepted only when a non-deprecated `P31 = Q5` statement proves it is human;
7. missing evidence remains missing;
8. QIDs remain Wikidata provider IDs.

The parser and its tests were verified by repository Quality run `32917969596` / Quality #657:

- Analytics: `ruff check`, `ruff format --check`, `mypy`, `pytest` — SUCCESS;
- Database: migrations, seeds, schema contracts, PostgreSQL integrations, deterministic smoke calculations and Next.js PostgreSQL read path — SUCCESS;
- Web: dependency audit, lint, typecheck, build — SUCCESS.

Quality verifies repository/code health. It does not certify external source semantics beyond the evidence measured below.

## Real strict run

- workflow: `Strict Wikipedia to Wikidata ARG_LPF 2024 bridge lab`;
- workflow run: `32918132393`;
- job: `98026035347`;
- branch head for the run: `991d61fb2fd81311bc2c8995ca81e4630bd4cfa2`;
- artifact: `9588917728`;
- artifact name: `wikipedia-wikidata-arg-lpf-2024-strict-bridge-32918132393`;
- artifact digest: `sha256:3963aaebd0828d9b6639d1f407db1c379ffd8f137c22a3b1e6ff1e84a813948d`;
- technical result: SUCCESS.

## Final strict identity result

| Measure | Result |
| --- | ---: |
| Target clubs | 28 |
| Clubs with accepted historical Wikipedia squad entries | 26 |
| Observed club-membership rows | 1,087 |
| Rows with a leading player-article link | 764 |
| Rows with a Wikidata QID candidate | 747 |
| Rows with an accepted human QID | 745 |
| Unique Wikipedia article titles | 709 |
| Unique QID candidates | 676 |
| Unique accepted human QIDs | **670** |
| Rows rejected because QID was not human | 2 |
| Accepted QIDs observed in more than one target club | 67 |

Ratios:

- leading-player-article coverage over membership rows: **70.29%**;
- accepted human-QID coverage over all membership rows: **68.54%**;
- accepted human-QID coverage among linked rows: **97.51%**.

The 67 QIDs appearing in more than one target club are not automatically conflicts. The four-snapshot union spans a transfer window, so a player may legitimately appear for more than one ARG_LPF club. Team and time context must remain attached to each observation.

## False-positive correction confirmed

The earlier loose bridge had interpreted the club link in:

`Lucas Lopez (on loan from [[CA Nueva Chicago]])`

as if it were the player's article and produced non-player QID `Q744555`.

The strict retained parser now returns no player article for this value. The real strict run therefore reduced:

- linked membership rows: `765 → 764`;
- rows with QID candidates: `748 → 747`.

The erroneous Nueva Chicago item is absent from the strict accepted identity set.

## Two remaining linked rows rejected by the human gate

The strict run found two leading player-article links whose current `wikibase_item` did not satisfy `P31 = human`:

1. Atlético Tucumán — `Joaquín Pereyra` → `Q27097277`;
2. Platense — `Oscar Salomón` → `Q135692974`.

They remain unresolved from this deterministic bridge. Football Intelligence must not repair them by silently trusting the label or by fuzzy/LLM matching.

## Profile enrichment over the 670 accepted human QIDs

All 670 accepted QIDs parsed successfully through the repository's conservative Wikidata profile parser.

| Profile field | Count | Coverage |
| --- | ---: | ---: |
| Parsed profile | 670 | 100.00% |
| Display name | 670 | 100.00% |
| Any DOB evidence | 670 | 100.00% |
| Exact DOB | 649 | 96.87% |
| Citizenship | 651 | 97.16% |
| Position | 584 | 87.16% |

The earlier fixed enrichment heuristic therefore remains **B — useful profile enrichment**, not A, because position coverage remains below the 90% A threshold.

Current Wikidata profile facts are current-source evidence at acquisition/revision time. They must not be relabelled as historical 2024 facts unless the underlying property has explicit historical evidence.

## Decision

The strict zero-cost Wikipedia → Wikidata identity/profile path is **validated as useful provider-local enrichment evidence** for the 26 clubs covered by historical English-Wikipedia squad revisions.

The final accepted strict identity count is **670 unique human QIDs**. Earlier looser candidate figures must not be used as certified identity coverage.

This does not change the broader zero-cost roster-source result:

- 26/28 clubs: exact historical English-Wikipedia active-squad evidence;
- Vélez Sarsfield: separate first-party dated club convocation evidence;
- Independiente Rivadavia: explicit unresolved historical roster-source gap;
- defensible current zero-cost membership/selection coverage: **27/28 clubs**.

## Next engineering step

A production-oriented change should be a bounded collector/snapshot layer around the retained transform-only parser, preserving:

- article title;
- historical revision id and timestamp;
- requested snapshot target;
- acquisition timestamp;
- raw player-name value;
- leading Wikipedia article target when present;
- CC BY-SA attribution/licence metadata;
- resolved Wikidata QID only after the human gate;
- Wikidata entity revision/acquisition metadata for profile enrichment;
- explicit unresolved state for rows without deterministic identity.

It must remain separate from canonical player resolution and must not ingest the separate Vélez/LPF evidence as though it had the same reuse/licence contract.