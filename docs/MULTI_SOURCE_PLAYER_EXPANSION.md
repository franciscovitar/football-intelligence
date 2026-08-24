# Multi-Source Player Data Expansion

## Objective

Populate Football Intelligence's six core leagues with the broadest defensible
player information obtainable from multiple static or historical sources while
preserving source provenance, source-specific semantics, `missing != zero`, and
strict cross-provider identity evidence.

Core competitions remain:

- `ARG_LPF` — Liga Profesional;
- `ENG_PL` — Premier League;
- `ESP_LL` — LaLiga;
- `ITA_SA` — Serie A;
- `GER_BL1` — Bundesliga;
- `FRA_L1` — Ligue 1.

This initiative extends Block 20's multi-source architecture. It does **not**
replace the Data Mesh, Metric Catalog V2, Entity Resolution V2, reconciliation,
or existing Wyscout historical promotion path.

## Product direction

The target is curated **static snapshots**, not day-to-day synchronization.
A source may publish new versions frequently; Football Intelligence may freeze a
specific acquired version and keep it immutable as evidence.

The product should use as many independent sources as are technically and
legally supportable. "Use all sources" means extracting each source's valid
facts into the common evidence model, not averaging incompatible provider
metrics or hiding provenance.

## Non-negotiable invariants

1. Raw/original source evidence is never overwritten by cleaning or derived data.
2. Every promoted fact retains provider, scope, granularity, source reference,
   acquisition time, and model/semantic version where applicable.
3. Missing values remain missing unless a documented provider-specific semantic
   contract proves that missing represents zero for that field.
4. A direct observation, a derived metric, and a model output are different
   evidence classes.
5. Provider IDs never become canonical Football Intelligence IDs.
6. Players are never cross-provider matched by fuzzy name, edit distance, or LLM
   judgment.
7. Exact normalized name alone is insufficient identity evidence.
8. Conflicting facts are preserved and reconciled by explicit policy; they are
   never silently averaged.
9. Identically named metrics from different providers are not assumed to have
   identical definitions.
10. A source can be technically ingestible while remaining unavailable for
    product promotion because of provenance/licence/compliance.

## Intake pipeline

```text
source discovery
  -> source/compliance review
  -> immutable static snapshot + manifest
  -> checksum verification
  -> provider-specific schema audit
  -> provider-specific adapter
  -> identity candidate generation
  -> validated player crosswalk
  -> Metric Catalog mapping
  -> NormalizedObservation
  -> reconciliation
  -> canonical evidence
  -> derived metrics
  -> Player/Team Intelligence
  -> coverage + quality report
  -> promotion decision
```

No stage may be skipped merely to obtain more filled cells.

## Static snapshot contract

`football_intelligence.ingestion.static_snapshot` now provides the common
metadata contract for every new static dataset.

A snapshot manifest records at minimum:

- stable snapshot id;
- source/provider code;
- timezone-aware acquisition timestamp;
- authoritative/upstream source reference;
- competition codes;
- season labels;
- data grains;
- every cached file path;
- SHA-256 checksum per file;
- optional expected byte size.

Cached files are verified before an adapter consumes them:

```bash
football-intelligence-validate-static-snapshot \
  --manifest /path/to/manifest.json \
  --base-dir /path/to/cache \
  --report /path/to/report.json
```

Heavy/original datasets remain in their authoritative source/evidence store or
local cache according to repository/PAS storage policy; the repository should
commit only safe metadata, adapters, mappings, tests, small certified fixtures,
and durable reports when appropriate.

## Player identity cleaning

`data_mesh.player_identity_candidates` is a pre-resolution evidence stage. It
never creates canonical players itself.

Each provider-local record can contribute:

- provider player id;
- raw player name;
- competition + season;
- canonical team contexts when resolved;
- canonical shared matches when the source exposes enough detail;
- date of birth;
- nationality;
- position;
- height.

Candidate states:

### `crosswalk_ready`

Requires:

- exact deterministic normalized name;
- no hard date-of-birth contradiction;
- exactly one shared canonical team context in the candidate record; and
- at least one shared canonical match.

This means the pair has enough generic evidence for a caller to build the
existing explicit `PlayerCrosswalkEntry`. The crosswalk itself remains the
resolver contract and can still reject invalid evidence.

### `review_required`

Used when evidence is strong but cannot satisfy the crosswalk automatically,
for example:

- same name + same date of birth + same team/season but no shared match ids;
- multiple shared team contexts after a real transfer, before each match is
  attributed to its exact team context;
- season-level profile datasets that cannot expose match-level identity.

### `insufficient_evidence`

Examples:

- exact name only;
- weak profile coincidence without team/match context;
- normalized-name mismatch.

No automatic player link is created.

### `conflict`

A hard identity contradiction was observed. The first implemented hard conflict
is differing non-null dates of birth for the exact normalized name pair.
The evidence stays visible for diagnosis and cannot be silently promoted.

Nationality, position and small height differences are corroboration/quality
signals rather than hard identity blockers because real sources may differ in
nationality representation, role taxonomy, rounding, or stale profile data.

## Cleaning policy by field family

### Identity/profile fields

Normalize representation only:

- Unicode/provider-specific text defects at the provider boundary;
- deterministic player-name normalization for comparison;
- ISO dates;
- consistent numeric units (for example height in centimetres);
- explicit provider-native vs canonical ids.

Never manufacture aliases globally. A reviewed alias/crosswalk is explicit
evidence, not generic normalization.

### Countable match facts

Examples: goals, cards, minutes, shots.

If multiple sources claim the same semantic metric/granularity/scope:

- keep every source observation;
- compare exact values where the semantic contract is compatible;
- mark agreement/conflict;
- select canonical evidence only through explicit source/reconciliation policy.

Never average conflicting counts.

### Provider models

Examples: xG, xA, platform rating, market value.

Provider models remain provider-scoped unless a reviewed methodology proves they
are comparable. `xG(provider A)` and `xG(provider B)` can both be useful while
remaining two source-specific observations.

### Derived Football Intelligence metrics

Per-90 rates, ratios, percentiles, dimensions, diagnostics, and other derived
features are computed only after canonical/source-policy decisions. They never
replace original observations.

## Source onboarding states

Existing source-compliance guardrails remain authoritative until deliberately
re-audited. This initiative does not remove any current prohibition merely
because a dataset is useful.

The working source families are:

| Source/family | Intended value | Current onboarding treatment |
| --- | --- | --- |
| Wyscout Open | historical/deep event and player evidence | existing certified historical path; reuse |
| StatsBomb Open | historical/deep event evidence | existing `internal_only` restrictions remain |
| Football-Data.co.uk | match/team facts | existing path; no deep player layer |
| OpenFootball | independent fixture/result reconciliation | existing path |
| Transfermarkt-derived static dataset | broad six-league player profiles, career/appearance/market context | candidate; re-audit provenance/licence before adapter/promotion |
| FBref/Sports-Reference-derived static snapshot | deep five-European-league player season metrics | candidate; current prohibition remains until a new source/compliance review closes it |
| LPF official data/reports | authoritative Argentina enrichment/validation | candidate; audit exact reusable fields and acquisition method |
| FootyStats static export | possible Argentina/europe player enrichment | candidate; requires current licence/cost/use review before acquisition/promotion |

A candidate can be investigated, schema-audited, and mapped without automatically
becoming product-approved evidence. Any raw acquisition must still respect the
current source policy and terms.

## Metric mapping

Every new provider gets an empirical mapping against the full Metric Catalog V2,
using the Wyscout/StatsBomb precedent:

- `DIRECT` — exact source field/event with verified semantics;
- `DERIVABLE_READY` — deterministic methodology already defined;
- `DERIVABLE_METHODOLOGY_PENDING` — source has enough evidence but methodology
  is not yet approved;
- `REQUIRES_MODEL` — would require a separate model;
- `AMBIGUOUS` — adjacent provider concept is not safely equivalent;
- `UNSUPPORTED` — verified absent;
- provider-out-of-scope for internal analytics outputs.

An adapter may emit only the reviewed safe subset.

## Data-quality gates

Before a snapshot can be promoted, produce at least:

### Snapshot integrity

- files present;
- SHA-256 matches manifest;
- schema/version recorded;
- source reference recorded;
- competition and season scopes explicit.

### Entity integrity

- provider player ids unique or conflicts explained;
- duplicate rows quantified;
- player candidate states counted;
- unresolved and conflicting identities retained;
- no global name-only canonical players.

### Metric integrity

- field-to-Metric-Catalog mapping complete/accounted for;
- null vs zero semantics documented per source;
- units and percentages verified;
- impossible/out-of-range values rejected or reported;
- duplicate logical observations reported;
- cross-source disagreements quantified.

### Coverage

Report per competition/season:

- roster/player count;
- identity resolution rate;
- profile-field coverage;
- metric identity coverage;
- Player V2 intended/core/available/missing metrics;
- dimension readiness;
- number of ranking-eligible players;
- conflicts and review-required identities.

Coverage is descriptive evidence, never a reason to weaken gates.

## Rollout order

1. Foundation (this document): static snapshot provenance/integrity contract +
   conservative identity-candidate layer.
2. Re-audit candidate sources against current primary terms/provenance.
3. Select the first source with the best six-league player-coverage leverage.
4. Acquire one bounded snapshot outside the repository and generate its manifest.
5. Audit its real schema/row quality before mapping metrics.
6. Build the provider adapter and identity records.
7. Run one competition as the fusion laboratory.
8. Resolve/review identity conflicts and validate coverage.
9. Expand the same certified adapter to all supported core competitions.
10. Add the next source and reconcile/enrich, never replacing trustworthy evidence.

The preferred first target is the source that can provide broad player identity
coverage across all six leagues, because that becomes the common crosswalk spine
for subsequent richer European and Argentina-specific performance sources. Which
candidate wins that role is a source-audit decision, not assumed here.

## Acceptance criteria for this foundation

- static snapshots have a reusable immutable provenance/checksum contract;
- malformed/unsafe manifests fail closed;
- cached-file integrity can be verified by a deterministic CLI;
- cross-source player candidates never use fuzzy/name-only resolution;
- exact-name-only candidates remain insufficient;
- hard DOB contradictions surface as conflicts;
- match/team-supported pairs can be distinguished from review-only season-level
  candidates;
- no existing source-compliance prohibition is silently relaxed;
- no production/database mutation is part of this foundation.
