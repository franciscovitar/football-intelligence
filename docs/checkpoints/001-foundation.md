# Checkpoint 001 — Foundation

## Status

**PASS**

## Objective

Establish a healthy, low-complexity repository foundation for the Football Intelligence project before feature implementation.

## Implemented

- canonical `AGENTS.md` and `WORKFLOW.md` instructions;
- `CLAUDE.md` pointer to canonical instructions;
- Next.js/TypeScript web skeleton;
- Python 3.13 analytics package skeleton;
- explicit Hatch wheel mapping for the `src` layout;
- explicit Next.js generated type includes;
- generated Next/TypeScript artifacts excluded from version control;
- root workspace commands;
- environment templates/version hints;
- npm and uv lockfiles;
- CI quality workflow;
- architecture and 12-block roadmap documentation;
- three initial architecture decision records;
- database/research placeholders only where immediately useful.

## Verified

- npm dependency installation and lockfile generation: PASS;
- Next.js ESLint: PASS;
- Next.js TypeScript check: PASS;
- production Next.js build: PASS;
- second local quality pass leaves working tree clean: PASS;
- uv lock and locked environment sync on Python 3.13: PASS;
- Hatch editable package build/install: PASS;
- Ruff lint + format check: PASS;
- mypy strict typecheck: PASS;
- pytest: PASS;
- repository whitespace check: PASS;
- GitHub Actions `Quality` workflow: PASS.

## Evidence

- verified code commit: `cf5095d0d8f2bc9ce1c58123392b07841c7ab8ce`;
- CI run: https://github.com/franciscovitar/football-intelligence/actions/runs/31535810236.

## Repository recovery note

The valid initial foundation remained available in Git history. A later commit that removed it was reversed with a normal `git revert` rather than rewriting history.

## Foundation corrections

Dependency-backed verification exposed two reproducibility issues and both were corrected before certification:

1. Hatch could not infer the import package from the distribution name, so the wheel package is explicitly mapped to `src/football_intelligence`.
2. Next.js/TypeScript generated development route types and incremental build metadata during the quality pass. Their expected generated-file behavior is represented explicitly in configuration and ignore rules.

## Risk

Low. No production systems, real credentials, databases, paid services, destructive history rewrites, or force pushes were introduced.

## Next action

Start Block 2 — Data Foundation from this verified checkpoint. Do not repeat Block 1 validation unless later changes can affect it or contradictory evidence appears.
