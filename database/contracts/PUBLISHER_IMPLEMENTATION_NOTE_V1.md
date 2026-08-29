# Match Publisher V1 — Implementation Boundary

The automated match publisher is intentionally downstream of fixture-universe ingestion.

It may resolve/upsert match-local identities (teams, players, managers, sources/documents) when the `MATCH_RESEARCH_PUBLISH_V1` package contains enough identity evidence, but it does not invent competition, season, stage or round semantics.

Remote writes use the existing repository-wide `production_write_guard`; no weaker publisher-specific production bypass exists.

The implementation is exercised against PostgreSQL in integration tests before any real Supabase publication is attempted.
