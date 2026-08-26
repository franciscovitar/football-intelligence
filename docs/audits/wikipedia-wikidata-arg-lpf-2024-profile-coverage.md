# Wikipedia → Wikidata profile coverage — ARG_LPF 2024

Audit date: 2026-08-25  
Canonical base: `main@e994c24ff7ce09c2c7c5499d27ed30fc1774ddfd`  
Status: source/identity enrichment lab; no canonical-player or product promotion.

## Question

Given the zero-cost historical Wikipedia active-squad evidence already measured for ARG_LPF 2024, how useful is a deterministic Wikipedia-article → Wikidata-QID bridge for player profile enrichment?

The intended role is **provider-local identity/profile enrichment only**. It does not prove AFA registration, Torneo appearance, performance, or Football Intelligence canonical identity.

## Real run

- branch commit: `b20e8f6fd0dd2aa8962c0a789a55aa454ebd67e5`;
- workflow run: `32917109880`;
- job: `98023011779`;
- artifact: `9588560623`;
- artifact digest: `sha256:109142ac06dc497606b770905c0c262ba4bfeb776024dec353bee1b3ab7c81ea`;
- technical result: SUCCESS;
- repository Quality for the same commit: run `32917109828` / Quality #651, Analytics + Database + Web all SUCCESS.

The run reused the repository's conservative `parse_wikidata_entity_document` parser.

## Raw measured candidate set

- observed club-membership rows: **1,087**;
- rows with a Wikidata candidate QID: **748**;
- unique candidate QIDs: **673**;
- parser errors: **0**.

Raw profile counts over the 673 candidates were:

- P31 human: 670;
- explicit association-football-player occupation: 669;
- display label: 673;
- any DOB: 670;
- exact DOB: 649;
- citizenship: 651;
- position: 584;
- positive height quantity claim: 609.

The fixed pre-run heuristic returned `B_useful_profile_enrichment`, because position coverage was below the 90% threshold required for `A`.

## Identity-safety finding

The run exposed a real bridge bug that must not be promoted into production.

One Barracas Central name field represented an unlinked player followed by a loan annotation:

`Lucas Lopez (on loan from [[CA Nueva Chicago]])`

The generic link extractor selected the linked club and produced Wikidata QID `Q744555`. This item is not P31 human and therefore must never become a player identity.

Two additional Wikipedia article targets resolved to Wikidata items that were not P31 human:

- `Q27097277` from the linked article for Joaquín Pereyra;
- `Q135692974` from the linked article for Oscar Salomón.

These are evidence that an article link and a `wikibase_item` value are still not sufficient by themselves. The bridge must fail closed unless the resulting Wikidata item is explicitly a human.

A separate human item, `Q129262238`, had no explicit association-football-player occupation. That is incomplete profile evidence, not enough by itself to reject the identity: the source row is already an active-squad player observation and the Wikidata item is human. Its missing occupation must remain missing rather than being inferred.

## Accepted human-QID interpretation

Applying the mandatory P31-human gate to the measured candidate set leaves **670 unique accepted human QIDs**.

Profile coverage over those 670 accepted human QIDs is:

| Field | Count | Coverage |
| --- | ---: | ---: |
| Display name | 670 | 100.00% |
| Any DOB | 670 | 100.00% |
| Exact DOB | 649 | 96.87% |
| Citizenship | 651 | 97.16% |
| Position | 584 | 87.16% |
| Height quantity claim | 609 | 90.90% |
| Explicit football-player occupation | 669 | 99.85% |

The decision remains **B — useful profile enrichment** because position is 87.16%, below the fixed 90% `A` threshold.

## Required bridge contract before any retained adapter

A production-oriented implementation must be stricter than the completed lab:

1. only a Wikipedia link syntactically representing the player-name token may become an article target;
2. annotation links such as loan/source clubs must never become player identity;
3. MediaWiki redirects/normalization may be followed explicitly;
4. the resulting Wikidata QID must be P31 human;
5. missing P106 football-player occupation is preserved as missing and may trigger review, not synthetic rejection or inference;
6. QIDs remain Wikidata provider IDs, never Football Intelligence canonical IDs;
7. current Wikidata profile facts must be stamped with revision/acquisition metadata and must not be treated as historical 2024 facts unless the property itself has historical evidence;
8. no fuzzy or LLM name matching is introduced silently.

## Decision

The zero-cost Wikipedia → Wikidata path is **accepted as useful identity/profile enrichment evidence**, conditional on the stricter human/leading-player-link contract above.

It is not a complete roster backbone and it is not ready to merge as a production adapter from this lab branch. The next production decision should happen only after the remaining roster-source gaps and source-role boundaries are closed.