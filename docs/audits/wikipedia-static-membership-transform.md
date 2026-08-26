# Wikipedia historical membership transform validation

Status: validated in isolated lab branch; not merged and not promoted to PostgreSQL/product state.

## Purpose

Retain the useful part of the ARG_LPF 2024 Wikipedia historical experiment after Wikipedia was rejected as a complete season-roster backbone.

The transform consumes only previously frozen historical MediaWiki revision snapshots and emits source-local dated `player_membership` observations. It does not call Wikipedia/Wikidata, create canonical players, infer AFA/COMET registration, infer match participation, write PostgreSQL, or convert missing evidence into zero.

## Safety contracts

The transform fails closed unless all of the following hold:

- the generic static-snapshot manifest is valid;
- every declared file checksum passes;
- the source is `wikipedia` and the grain includes `player_membership`;
- `index.json` is itself manifest-declared;
- every request's raw file is manifest-declared;
- `request_id` deterministically matches article title + snapshot target;
- raw MediaWiki bytes agree with index metadata for resolved title, page/revision ID and revision timestamp;
- raw active-squad evidence agrees with the index heading/count flags;
- selected revision timestamp is not newer than the requested historical target;
- annotation-only links such as `on loan from [[Club]]` are never promoted to player identity;
- loan annotation text is retained in `raw_name` but stripped from `display_name` before name-based provider identity fallback.

Provider-local keys are deterministic and are explicitly not Football Intelligence canonical player IDs.

## Quality validation

Commit `6f5c31aa3320e7fd30b4823d345c6f1e0340af71` passed Quality run `32957659168` (#687):

- Analytics: PASS
  - Ruff lint: PASS
  - Ruff format: PASS
  - mypy strict: PASS
  - pytest: PASS
- Database: PASS
- Web: PASS

The preceding test failure was useful: the link gate correctly rejected the lending club as a player article, but the text `(on loan from CA Nueva Chicago)` still contaminated the name-based fallback key. The parser was tightened so raw provenance keeps the annotation while player display identity does not.

## Real frozen-artifact runtime smoke

A temporary lab workflow then executed the retained CLI against the already-frozen ARG_LPF 2024 opening snapshot from historical collection run `32921437933`.

Runtime smoke:

- run: `32958009294`
- input artifact: `wikipedia-arg-lpf-2024-opening-32921437933`
- input artifact ID: `9589975259`
- input artifact digest: `sha256:ccf2efca9ef7a047a54a1908a98345b3ec78d026ab2e91f47d0f34a04a4c30bc`
- generic snapshot checksum verification: PASS
- requests transformed: 26
- requests with active-squad evidence: 26
- membership observations emitted: 752
- observations with leading player article identity: 538
- provider keys containing `on loan from`: 0
- transform executed twice against the same frozen bytes: byte-for-byte output equality PASS
- output smoke artifact: `wikipedia-membership-transform-real-smoke-32958009294`
- output artifact ID: `9602730783`
- output artifact digest: `sha256:522e7225ab86827859096bd223c31e202049a69d42b3bbfe72fc2656bc5bd467`

This validates the runtime path `frozen snapshot -> checksum verification -> offline transform -> deterministic provider-local membership JSON` on real previously collected evidence.

## Explicit non-claims

This validation does **not** establish:

- complete ARG_LPF 2024 season rosters;
- AFA registration/eligibility;
- player appearance or minutes;
- canonical PlayerCrosswalk identity;
- completeness of Wikipedia's active-squad sections;
- database ingestion readiness;
- public product promotion.

The earlier ten-cut experiment remains controlling evidence that Wikipedia is insufficient as a complete roster-season backbone for this task.

## Retained role

Wikipedia historical revisions may be retained as a low-cost, source-local membership/identity-enrichment signal when their licence/attribution requirements are preserved. A separate player-season/statistics source is still required for broad historical performance coverage.
