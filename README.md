# Football Intelligence

Personal football intelligence app that combines quantitative performance, context, and external perception to explain who is playing well, who is underperforming, which teams' results match their process, and where perception diverges from evidence.

## Current status

**Block 1 — Foundation (in progress)**

The source/configuration foundation is established. Dependency-backed web/Python quality gates remain pending because the current execution environment cannot reach package registries. Football data ingestion starts in Block 2/3 according to `docs/ROADMAP.md`.

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
