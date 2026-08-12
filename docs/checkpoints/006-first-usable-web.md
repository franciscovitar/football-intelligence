# Checkpoint 006 — First Usable Web

## Status

**PASS**

## Objective

Expose the persisted Player Analytics V1 read model through the first usable
product surface without moving scoring logic into the browser or fabricating
fallback data.

## Implemented

- server-side PostgreSQL read path using Postgres.js;
- request-time rendering with Next.js `connection()`;
- `/` dashboard with Performance, Form, and rising-player views;
- `/rankings` with window, broad-role, confidence, and name filters;
- `/player/[id]` with score trend, dimensions, confidence, per-90 evidence,
  contextual adjustments, and explicit V1 limitations;
- `/lab` diagnostics for scopes, role/window populations, and persisted metrics;
- production gate for `/lab` through `INTERNAL_LAB_ENABLED=true`;
- explicit unconfigured, empty, error, and not-found states;
- responsive no-client-state UI;
- deterministic PostgreSQL smoke fixture used only in CI;
- full-stack CI smoke verification against PostgreSQL 17.

## Verified

- Web ESLint: PASS;
- Web TypeScript: PASS;
- production Next.js build without `DATABASE_URL`: PASS;
- existing Python lint/typecheck/tests: PASS;
- all migrations: PASS;
- database contracts: PASS;
- Python PostgreSQL integrations: PASS;
- real Next.js server reading ephemeral PostgreSQL: PASS;
- `/` renders persisted ranking data: PASS;
- `/rankings` filters and renders persisted score snapshots: PASS;
- `/player/[id]` renders persisted score/feature evidence: PASS;
- `/lab` renders persisted diagnostics: PASS;
- Web / Analytics / Database GitHub Actions jobs: PASS.

## Evidence

- implementation commit: `5ede37956de8bdd7dda35e40273e5e9e04470cb7`;
- CI run validating the implementation: https://github.com/franciscovitar/football-intelligence/actions/runs/31551103504.

## Security and data-integrity boundaries

- `DATABASE_URL` remains server-side and is never exposed through a
  `NEXT_PUBLIC_` variable.
- SQL values use tagged-template parameters rather than string interpolation.
- UI error states do not expose connection strings or database credentials.
- `/lab` is available in development but returns 404 in production unless
  explicitly enabled.
- The UI reads versioned snapshots and does not recalculate quantitative model
  scores.

## Product/model boundaries

- No fake ranking fallback is shown when PostgreSQL is missing.
- League filtering is not offered because Player Analytics V1 currently persists
  one multi-league core scope rather than league-specific score snapshots.
- The "latest team" label on player detail is explicitly the latest team recorded,
  not a guarantee that it belongs to the active historical scope.
- Block 5 model limitations still apply: no xG/xA, opponent-strength adjustment,
  detailed sub-roles, or mature goalkeeper model.

## Not verified / not claimed

- production Supabase/Vercel runtime configuration is not yet operationally
  certified;
- current-season API-Football access remains constrained by the provider plan;
- no claim is made that the public/live product currently contains 2026 data;
- automated CI validates rendered HTML and database reads, not visual pixel-level
  browser QA.

## Next action

Start Block 7 — Team Intelligence.
