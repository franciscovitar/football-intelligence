# ADR-003: Internal entity identifiers and provider mappings

## Context

Football providers use incompatible IDs and may be replaced or combined later.

## Decision

Core entities receive internal IDs. Provider-specific IDs live in mapping records at the external boundary.

## Alternatives

- Use API-Football IDs as primary keys.
- Encode provider identity into domain IDs.

## Trade-offs

Mappings add a small amount of ingestion work but sharply reduce provider lock-in and make multi-source reconciliation possible.

## Consequences

Provider payloads must be normalized before business logic consumes them.
