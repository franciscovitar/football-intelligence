# First Usable Web

Block 6 turns the persisted Player Analytics V1 read model into the first product-facing web surface.

## Routes

- `/` — dashboard with Performance leaders, Form leaders, and Form-vs-Performance movers.
- `/rankings` — role/window/confidence/name filters over real persisted score snapshots.
- `/player/[id]` — player trend, skill dimensions, confidence, and metric evidence.
- `/teams` — competition-relative Team Performance/Form explorer with confidence,
  Elo, and Results-vs-Process context.
- `/team/[id]` — team windows, Elo history, score dimensions, diagnostics, and
  underlying metric evidence.
- `/lab` — internal diagnostics for player and team snapshot scopes, populations,
  and feature coverage.

## Read path

The web reads PostgreSQL server-side only.

```text
analytics.player_score_snapshots
analytics.player_feature_snapshots
analytics.team_score_snapshots
analytics.team_feature_snapshots
analytics.team_elo_history
          |
          v
Next.js Server Components
          |
          v
rendered UI
```

The UI never reads API-Football payloads directly and does not calculate model scores in the browser.

`DATABASE_URL` is a server-only environment variable. It must never be exposed through a `NEXT_PUBLIC_` variable.

The Node read client is Postgres.js. It is configured with a small pool, bounded connection timeout, and prepared statements disabled for compatibility with transaction-pooling deployments.

## Rendering

Data pages call Next.js `connection()` so database work is tied to an incoming request rather than attempted during `next build`.

This keeps CI/build reproducible without a production database while still rendering fresh persisted snapshots at request time.

## Empty and failure states

No fake ranking data is used.

- missing `DATABASE_URL` → explicit configuration state;
- connected database with no snapshots → explicit empty state;
- read failure → generic operational error without credentials or connection-string details.

## Rankings

The active read context is the most recently calculated `(scope_key, model_version)` pair.

V1 filters:

- Performance / last 3 / Form last 5 / last 10;
- broad role;
- minimum confidence;
- player name.

League filtering is intentionally absent because Block 5 currently persists one core multi-league scope rather than league-specific score snapshots.

## Player detail

The page exposes:

- season Performance;
- recent-window score trend;
- confidence per window;
- role-aware skill dimensions;
- high-percentile feature evidence;
- raw vs context-adjusted per-90 values;
- explicit V1 model limitations.

The page describes the latest team as the **latest team registered**, not as a guaranteed team inside the active historical scope.

## Team Intelligence

Team rankings are scoped to one competition and season. The `/teams` filters
select competition, window, minimum confidence, and team name; no global
cross-league Elo sort is exposed.

The `/team/[id]` page shows season Performance, recent Form windows, Elo and
five-match trend, score dimensions, Results-vs-Process language, confidence, and
raw/stabilized feature evidence. It explicitly describes generation as volume
rather than xG and control as a proxy rather than tactical dominance.

All team scores are read from `team-v1.0` snapshots. See
`docs/TEAM_ANALYTICS.md` for exact formulas and model boundaries.

## Diagnostics Lab

`/lab` intentionally exposes only model/read-model diagnostics, never secrets or database connection details.

In production, `/lab` returns 404 unless:

```text
INTERNAL_LAB_ENABLED=true
```

Development keeps the route available for local diagnostics.

## Verification

CI uses its ephemeral PostgreSQL 17 service to:

1. apply all migrations and seeds;
2. run database contracts and Python integrations;
3. insert deterministic web smoke snapshots;
4. start the real Next.js app in development mode against that database;
5. verify `/`, `/rankings`, `/player/[id]`, `/teams`, `/team/[id]`, and `/lab`
   return expected persisted data.

The normal Web job still runs lint, TypeScript checking, and a production build without requiring `DATABASE_URL`.

## Operational boundary

Block 6 certifies the web read path and UI against PostgreSQL.

It does **not** claim that a production Supabase/Vercel environment is already configured, nor that current-season API-Football access is available. Those infrastructure/provider constraints remain explicit.
