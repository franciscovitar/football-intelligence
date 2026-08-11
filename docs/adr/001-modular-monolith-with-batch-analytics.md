# ADR-001: Modular monolith with batch analytics

## Context

The application is personal, low-traffic, cost-sensitive, and analytics-heavy. It needs two ecosystems: Next.js for the product and Python for data work.

## Decision

Use one repository and one PostgreSQL source of truth. Run the Next.js app continuously when deployed; run Python analytics as short-lived batch jobs.

## Alternatives

- Python API service plus Next.js client.
- Multiple microservices.
- All logic in TypeScript.

## Trade-offs

This avoids network/service orchestration and idle compute while preserving Python for statistical work. The main cost is maintaining two language toolchains in one repository.

## Consequences

Do not introduce service-to-service APIs until an actual independent deployment or scaling requirement appears.
