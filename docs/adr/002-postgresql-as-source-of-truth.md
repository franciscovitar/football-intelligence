# ADR-002: PostgreSQL as source of truth

## Context

The domain is strongly relational: competitions, seasons, teams, players, matches, appearances, statistics, model versions, and evidence.

## Decision

Use PostgreSQL as the canonical normalized data store. Raw provider payloads will be stored separately once ingestion begins, with relational traceability metadata.

## Alternatives

- MongoDB/document-first persistence.
- Google Sheets.
- Provider API as the effective source of truth.

## Trade-offs

PostgreSQL requires schema migrations but gives strong constraints, joins, transactions, and reproducible analytics.

## Consequences

Database changes are explicit migrations and critical invariants should be enforced at the database layer when practical.
