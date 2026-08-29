# Match Research Publish V1

Status: implementation contract for Football App V1.

Machine-readable schema: `database/contracts/match-research-publish.schema.json`.

## Purpose

Define the exact private handoff between Football Intelligence research and PostgreSQL publication.

The web is not a participant in this contract. It reads only verified facts and `PUBLISHED` intelligence after this contract has passed QA.

## Lifecycle

```text
fixture universe already registered
  -> research package
  -> schema validation
  -> catalog/identity resolution
  -> RESEARCHING research_run
  -> facts + source provenance + private evidence
  -> QA reviews
  -> database integrity checks
  -> atomic PUBLISHED transition
  -> deterministic public read model
```

A package with `research.qa_status != PASS` must never be promoted to `PUBLISHED`.

## Fixture-catalog prerequisite

Fixture discovery and football evaluation are separate responsibilities.

Before a research package can be published, its competition/season/stage/round context must already be represented by the fixture-universe layer:
- `match.competition_slug` must resolve to an active `competitions` row;
- `(competition, match.season_label)` must resolve to a non-archived `seasons` row;
- a non-null `match.stage_name` must resolve to an existing `competition_stages` row;
- a non-null `match.round_label` must resolve to an existing `rounds` row in the same season/stage.

The research publisher must **not invent** competition metadata, season lifecycle state or stage type from one researched match. Those semantics belong to fixture ingestion. Missing catalog context is a fail-closed publication error, not a reason to manufacture defaults.

Teams, players, managers, sources and source documents may be resolved/upserted by the publisher because the package contains the identity fields required by this V1 contract.

## Stable identity

Two keys prevent retry-driven duplication:

- `match.identity_key`: stable natural identity for the fixture. Recommended shape: `competition:season:YYYY-MM-DD:home-slug:away-slug`.
- `research.run_key`: stable idempotency key for one research attempt/version.

Internal PostgreSQL identities remain UUIDs. External/provider IDs are evidence metadata, not canonical entity identity.

## Idempotency

Publishing the same valid package twice must not create a second match, team, player, source document or same review version.

The V1 publisher stores a canonical SHA-256 digest of the full package in `research_runs.metadata` together with `research.run_key`:
- same `run_key` + same digest + already `PUBLISHED` -> return the existing publication with no new writes;
- same `run_key` + different digest -> hard idempotency conflict;
- same `run_key` in a non-published state -> fail closed rather than guessing how to resume an interrupted research attempt.

Use natural/unique keys for resolution/upserts:
- competition `slug` (catalog-owned, resolve only);
- season `(competition_id, label)` (catalog-owned, resolve only);
- stage/round in their season context (catalog-owned, resolve only);
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

For same-provider stat upserts, an incoming `null` must not erase a previously persisted non-null fact. A conflicting non-null same-provider value requires an explicit revision/correction path rather than a silent overwrite.

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

Publication of one match is one logical PostgreSQL transaction.

Recommended write order:
1. resolve competition / season / stage / round from the existing fixture catalog;
2. teams / managers / players;
3. source profiles / source documents;
4. match identity and result;
5. `research_runs` row in `RESEARCHING`;
6. appearances and compatible team/player statistics;
7. private `evidence_items` and `fan_themes`, plus candidate intelligence signals;
8. `match_reviews`, `team_match_reviews`, `manager_match_reviews`, `player_match_reviews` in `QA`;
9. QA/integrity queries;
10. atomically supersede prior current reviews when this is a documented revision;
11. atomically set the new package records and `research_run` to `PUBLISHED` with `published_at`.

If any step fails, the whole transaction rolls back.

`--dry-run` executes the same write/integrity path inside a transaction and then rolls the transaction back deliberately.

If a blocker is found, no partial public package may survive.

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

Document URLs are normalized for retry-safe identity without retaining URL fragments. URLs containing embedded credentials are rejected.

## Revision semantics

Published intelligence is historical evidence.

The first publication for a match uses `review_version = 1`.

Within one V1 package, `match_review`, team reviews, manager reviews and player reviews use the same `review_version`. When a new package replaces current published intelligence:
1. use a higher package review version;
2. supply an explicit revision reason;
3. keep every previously published entity review represented (new reviewed entities may be added, but old reviews may not silently disappear);
4. insert new reviews in `QA` with `supersedes_review_id` where applicable;
5. pass QA again;
6. mark the previous current records `REVISED`;
7. publish the replacements;
8. record `rating_revisions` audit rows.

Never silently update an old published score in place.

## Publisher CLI

Canonical command:

```text
football-intelligence-publish-match PACKAGE.json
```

Safety modes:
- `--validate-only`: schema + reference + QA validation, no database connection;
- `--dry-run`: complete database/integrity exercise, transaction rolled back;
- `--revision-reason`: mandatory when replacing existing published intelligence.

The command never reads a generic `DATABASE_URL` implicitly. Local PostgreSQL targets can be supplied directly. Remote/production writes must pass the repository-wide explicit multi-signal confirmation in `db.production_write_guard`; the publisher must never weaken or bypass that guard.

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

The first production-calibration fixture remains Barcelona vs Athletic Club on 2026-08-27. It was originally published through controlled SQL before this automated publisher existed and remains a calibration fixture, not proof that the scale is already cross-league stable.
