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

```text
External providers / web sources
              |
              v
      Python batch pipeline
              |
      raw -> normalize -> validate
              |
              v
          PostgreSQL
              |
      features -> scores
              |
              v
        persisted read model
              |
              v
         Next.js server
              |
              v
             user
```

## Dependency direction

Provider-specific schemas must stop at the provider/normalization boundary.

```text
provider -> normalizer -> domain data -> features -> scores -> application
```

The UI must never depend directly on API-Football payloads, and LLM output must never be the source of a quantitative performance score.

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
