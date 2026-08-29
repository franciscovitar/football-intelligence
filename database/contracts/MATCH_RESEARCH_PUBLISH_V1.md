# Match Research Publish V1

Status: implementation contract for Football App V1.

Machine-readable schema: `database/contracts/match-research-publish.schema.json`.

## Purpose

Define the exact private handoff between Football Intelligence research and PostgreSQL publication.

The web is not a participant in this contract. It reads only verified facts and `PUBLISHED` intelligence after this contract has passed QA.

## Lifecycle

```text
research package
  -> schema validation
  -> identity resolution/upsert
  -> RESEARCHING research_run
  -> facts + source provenance + private evidence
  -> QA reviews
  -> database integrity checks
  -> atomic PUBLISHED transition
  -> deterministic public read model
```

A package with `research.qa_status != PASS` must never be promoted to `PUBLISHED`.

## Stable identity

Two keys prevent retry-driven duplication:

- `match.identity_key`: stable natural identity for the fixture. Recommended shape: `competition:season:YYYY-MM-DD:home-slug:away-slug`.
- `research.run_key`: stable idempotency key for one research attempt/version.

Internal PostgreSQL identities remain UUIDs. External/provider IDs are evidence metadata, not canonical entity identity.

## Idempotency

Publishing the same valid package twice must not create a second match, team, player, source document or same review version.

Use natural/unique keys for upserts:
- competition `slug`;
- season `(competition_id, label)`;
- team/player/manager `slug`;
- match `external_identity_key`;
- source `(name, source_type)`;
- document normalized URL;
- appearance `(match_id, player_id)`;
- review entity + match + `review_version`.

A materially changed football judgment is a new review version, not a destructive update of an already published review.

## Missingness

`null` means the value is not available/compatible for this package. It is never converted to zero without provider-specific evidence that zero was observed.

Examples:
- `xg: null` = no compatible xG value persisted;
- `xg: 0` = observed/modelled xG exactly zero under the identified provider/model;
- `fan_score: null` = fan evidence was not coherent enough to summarize numerically.

The package may still contain a final FI score when a channel score is null, provided the evidence status, coverage and confidence explain the basis.

## Evidence separation

Persist separately:
- observed/official facts;
- provider-derived metrics;
- expert/tactical claims;
- fan themes;
- Football Intelligence estimates/inference.

Do not convert an external provider rating into an FI score. Do not relabel external xG/xA as FI metrics.

The research package may use a provider rating as diagnostic evidence only.

## Facts / Experts / Fans

Channel scores are optional diagnostics, not mandatory weights.

The final score must follow the current Football Intelligence methodology:
- direct measurable evidence dominates well-observed processes;
- expert/tactical evidence can dominate poorly measured mechanisms;
- fan themes primarily corroborate, challenge or expose perception gaps;
- convergence raises confidence;
- disagreement lowers confidence and remains visible.

There is no canonical fixed arithmetic formula such as `40/45/15`.

## Transaction boundary

Publication of one match should be treated as one logical transaction.

Recommended write order:
1. competition / season / stage / round;
2. teams / managers / players / tenures;
3. source profiles / source documents;
4. match identity and result;
5. appearances / observed events;
6. compatible team/player statistics;
7. `research_runs` row in `RESEARCHING`/`QA`;
8. private `evidence_items` and `fan_themes`;
9. `match_reviews`, `team_match_reviews`, `manager_match_reviews`, `player_match_reviews` in `QA`;
10. QA/integrity queries;
11. atomically set current package records and `research_run` to `PUBLISHED` with `published_at`.

If a blocker is found, keep the run non-public (`NEEDS_RESEARCH`, `DATA_CONFLICT`, `IDENTITY_BLOCKED` or `REJECTED`).

## Publication gate

At minimum verify:
- correct competition, season, date and home/away identity;
- final score;
- player participation/minutes where material;
- manager in charge;
- provider identity for refined metrics;
- no conflicting value silently averaged;
- role/context considered before player ratings;
- result is not used as the rating formula;
- match scores use the common absolute 0–10 scale;
- score/confidence both inside valid ranges;
- every public review has current methodology/rating/benchmark versions;
- public summary is supported by stored evidence;
- no full copyrighted source text is stored.

See the canonical `PUBLISHING_QA_PROTOCOL_V1.md` in `personal-ai-system`.

## Source storage

Store public source metadata and concise normalized claims. Do not store full articles, full Reddit threads or copied video transcripts.

`match_review.evidence_mix.source_document_ids` is the public evidence drawer bridge. The frontend resolves those IDs against `source_documents`.

Raw research evidence and fan-theme records remain private.

## Revision semantics

Published intelligence is historical evidence.

When new evidence or methodology changes a rating:
1. keep the old review;
2. insert a new review with `review_version + 1`;
3. set `supersedes_review_id`;
4. record `rating_revisions` reason;
5. run QA again;
6. publish the replacement.

Never silently update the old published score in place.

## Public web contract

The web may perform only deterministic transformations over persisted public records, including:
- sorting/filtering;
- means/medians;
- last-5/10 windows;
- volatility;
- frequency thresholds;
- chart coordinates;
- display formatting.

It must not:
- infer a match/player/team/manager FI score;
- invent missing channel scores;
- infer tactical style from raw statistics;
- create `underrated`, `breakout`, `rising` or other intelligence labels;
- call an LLM to complete missing football analysis.

## First implementation checkpoint

The first production-calibration fixture uses this contract for Barcelona vs Athletic Club on 2026-08-27. It is a calibration fixture, not proof that the scale is already cross-league stable.
