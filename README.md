# Football Intelligence

Personal football intelligence app that combines quantitative performance, context, and external perception to explain who is playing well, who is underperforming, which teams' results match their process, and where perception diverges from evidence.

## Current status

**Blocks 1-20 complete and certified.** Block 20 (multi-source Data Mesh expansion: Wyscout Open + StatsBomb Open historical/deep adapters, entity resolution V2, granularity-safe reconciliation V2) is closed -- see `docs/BLOCK20_MULTI_SOURCE.md`'s exit contract.

**Current phase: V1 Product Closure / Production Readiness.** The Global Product Closure Review found the app itself ready (honest empty states, secure defaults, green CI, correct deployment) but production database population still pending explicit authorization -- see `docs/PRODUCTION_BOOTSTRAP.md`.

**Known V1 limitation**: the permitted real snapshot is ENG_PL 2025/26 (the latest **completed** season, not a live/current feed), with no approved rich domestic player dataset -- see `docs/REAL_DATA_SNAPSHOT_V2.md`. Team-level intelligence is the real V1 value; player-level surfaces stay honestly unavailable until a compliant source exists.

Detailed per-block history remains in `docs/ROADMAP.md`.

## Architecture at a glance

- `apps/web`: Next.js + TypeScript application.
- `analytics`: Python batch ingestion, feature engineering, and scoring.
- `database`: explicit PostgreSQL migrations and seeds.
- `docs`: architecture, roadmap, and architecture decision records.
- `research`: experiments that must remain isolated from production models until validated.

The system is intentionally a modular monolith with batch analytics, not a microservice architecture.

## Prerequisites

- Node.js 20.9+
- npm
- Python 3.12+
- `uv`

## Setup

```bash
npm install
cd analytics
uv sync --dev
cd ..
```

No secrets are required in Block 1.

## Development

```bash
npm run dev
```

## Quality checks

```bash
npm run check
```

This runs the web lint/typecheck/build gates and Python lint/format/typecheck/tests.

## Canonical engineering instructions

- `AGENTS.md` defines how the software is engineered.
- `WORKFLOW.md` defines how work is orchestrated and verified.
- `CLAUDE.md` only points Claude Code back to those canonical instructions.
