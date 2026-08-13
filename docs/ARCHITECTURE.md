# Architecture

## Goal

Football Intelligence is a personal, low-cost web app that explains current football performance using quantitative data, context, and structured qualitative evidence.

The product must remain cheap, explainable, maintainable, and able to evolve its scoring models without rewriting the application.

## Architectural style

Use a **modular monolith with batch analytics**.

Two runtimes exist in one repository:

- **Next.js / TypeScript**: product UI and server-side read paths.
- **Python**: ingestion, normalization, feature engineering, statistical models, and scheduled batch jobs.

They share one PostgreSQL source of truth. Python is not a permanently running service; scheduled jobs start, process work, persist results, and exit.

## Data flow

Football Intelligence's target architecture is a **multi-source data mesh**:
many independent sources feed one reconciled canonical domain, still inside
the same modular monolith + batch system (no microservices, no permanently
running workers, no message queues).

```text
many sources (objective + qualitative)
              |
              v
        raw evidence (replayable, provider-scoped)
              |
              v
        source adapters (provider payload -> normalized observation)
              |
              v
        entity resolution (deterministic identity, UNRESOLVED when unsure)
              |
              v
        reconciliation (agreed / single_source / conflict / unresolved)
              |
              v
        canonical domain (football.* -- fed deliberately, never automatically
                           from an unreviewed PoC)
              |
              v
        analytics (features -> scores, model-versioned)
              |
              v
        persisted read model
              |
              v
        Next.js server -> user
```

A source is never able to write an arbitrary provider-specific payload
straight into the web read model. Every source's data crosses the same
boundary: raw -> normalized observation -> entity resolution ->
reconciliation -> canonical domain. See
[`MULTI_SOURCE_DATA_MESH.md`](MULTI_SOURCE_DATA_MESH.md) for the full
contract, resolution policy, reconciliation policy, and current PoC scope
(Block 13).

### Provenance and conflicts

Every normalized observation keeps its source, source type, and reference so
a fact can always be traced back to where it came from. When independent
objective sources disagree on a value, that disagreement is recorded as an
explicit `conflict` decision with every source's value retained as
evidence -- it is never silently overwritten or averaged. Confidence grows
with independent agreement and shrinks to a single low value when only one
source has reported a fact.

### Qualitative vs objective evidence

Qualitative expert/fan opinion (the existing Perception Intelligence lane)
is a **separate evidence lane**. It can inform product-facing insight and
context, but it must never become the source of an objective statistic or a
quantitative performance value. The reconciliation engine only accepts
objective source types; qualitative observations are rejected defensively
even if a caller passes them by mistake.

## Dependency direction

Provider-specific schemas must stop at the provider/normalization boundary.

```text
provider -> adapter -> normalized observation -> entity resolution ->
reconciliation -> canonical domain -> features -> scores -> application
```

The UI must never depend directly on a provider's raw payload, and LLM
output must never be the source of a quantitative performance score or an
objective statistic. LLM-assisted research belongs exclusively to the
qualitative Perception Intelligence lane (see
[`MULTI_SOURCE_DATA_MESH.md`](MULTI_SOURCE_DATA_MESH.md) for the future
ChatGPT/Google Sheet perception inbox lane), and it converges with objective
data only at the product/insight layer -- never inside canonical statistics.

## Primary modules

### Web

- `app`: routing and page composition.
- `features`: product-facing modules such as players, teams, rankings, tactics.
- `lib/db`: database connection plumbing when introduced.
- `lib/queries`: server-side read queries.
- `lib/types`: web-facing types when useful.

### Analytics

The Python package will grow by coherent responsibility only when each area becomes necessary:

- `providers`: external provider clients and provider schemas.
- `ingestion`: batch orchestration and fetching.
- `normalization`: mapping provider payloads to internal data.
- `data_mesh`: multi-source observation model, entity resolution,
  reconciliation, and a shared resolve-then-reconcile `pipeline` (Block
  13+, extracted Block 15 so multiple jobs reuse one implementation) --
  provider-independent, feeds the canonical domain only through a reviewed
  reconciliation step, never automatically.
- `coverage_lab`: Zero-Cost Coverage Lab (Block 14, deepened Block 15) -- a
  provider-independent target metric catalog, target competition list, and
  a pure state-machine measuring which free source can supply which metric,
  current vs historical, per competition. Capability manifests and probe
  results are keyed by `(metric_name, granularity)`, not bare `metric_name`,
  since the same name can mean different things at different granularities.
  Never a production feed itself.
- `data_quality`: coverage and integrity checks.
- `features`: reusable derived metrics.
- `scoring`: player, team, and meta scores.
- `context`: ELO and team/rival context.
- `perception`: qualitative evidence and perception models.
- `tactics`: tactical profiles based on supported evidence.
- `insights`: natural-language explanations derived from structured evidence.
- `jobs`: executable batch entry points.

Do not create empty modules in advance. Add them as their implementation block begins.

## Persistence principles

- PostgreSQL is the source of truth.
- Database structure changes use explicit migrations.
- Provider IDs are mappings, never internal primary keys.
- Missing data is distinct from zero.
- Critical invariants belong in database constraints where practical.
- Heavy analytics are precalculated; the web primarily reads persisted results.
- Every material score will eventually include `model_version`, `confidence`, and calculation time.

## Raw provider data

Provider responses will be stored separately from normalized relational data once ingestion is implemented. The relational database keeps traceability metadata; raw payloads remain replayable for re-normalization and audits.

## Model evolution

Features and scores are separate concepts. Scoring configurations are versioned. Production model changes follow:

```text
hypothesis -> experiment -> validation -> model version -> recalculation
```

Research must never silently alter production scoring.

## Deliberately excluded for V1 foundation

- microservices;
- Redis;
- queues;
- vector databases;
- ORM abstractions before persistence needs are known;
- client-side state libraries;
- live-score infrastructure;
- advanced ML before sufficient data exists.

Add complexity only when evidence shows a concrete need.
