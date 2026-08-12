# Roadmap

Each block ends with focused verification and a checkpoint. A block is not complete merely because code exists.

## Progress

- [x] **Block 1 ? Foundation** ? PASS
- [x] **Block 2 ? Data Foundation** ? PASS
- [x] **Block 3 ? Provider + Data Audit** ? PASS
- [x] **Block 4 ? Core League Sync** ? PASS
- [x] **Block 5 ? Player Analytics V1** ? PASS
- [x] **Block 6 ? First Usable Web** ? PASS
- [x] **Block 7 ? Team Intelligence** ? PASS
- [x] **Block 8 ? Expectation & Meta Intelligence** ? PASS
- [ ] **Block 9 ? Perception Intelligence**
- [ ] **Block 10 ? Overrated / Underrated Intelligence**
- [ ] **Block 11 ? Tactical Intelligence**
- [ ] **Block 12 ? World Radar + Calibration + V1 Hardening**

## Block 1 ? Foundation

**Goal:** establish a healthy repository before feature work.

Includes:

- canonical engineering instructions;
- Next.js + TypeScript app;
- Python analytics package;
- formatting/lint/typecheck/test/build gates;
- CI workflow;
- environment template;
- architecture and roadmap documentation;
- initial ADRs.

**PASS:** web lint/typecheck/build pass, Python lint/format/typecheck/tests pass, and CI configuration is syntactically coherent.

## Block 2 ? Data Foundation

Create PostgreSQL/Supabase persistence using explicit migrations, internal entity IDs, provider mappings, match/player/team stats, constraints, and ingestion metadata.

## Block 3 ? Provider + Data Audit

Connect the first real football provider for one league, persist raw + normalized data, establish idempotent upserts, rate-limit awareness, and measure real field coverage.

## Block 4 ? Core League Sync

Expand the verified ingestion path to Argentina + Premier League + LaLiga + Serie A + Bundesliga + Ligue 1 with scheduled incremental synchronization and freshness reporting.

## Block 5 ? Player Analytics V1

Implement roles, per-90 features, shrinkage, percentiles, confidence, skill scores, Performance, and Form.

## Block 6 ? First Usable Web

Expose real rankings, player detail, trends, score explanations, filters, and an internal diagnostics lab.

## Block 7 ? Team Intelligence

Implement team features, ELO, Attack, Chance Generation, Finishing Proxy, Defense, Control, Process, Results, Form, and Results-vs-Process diagnostics.

**PASS:** `team-v1.0` persists competition-and-season-relative features, scores,
confidence, diagnostics, and match-level Elo history; `/teams`, `/team/[id]`, and
team `/lab` diagnostics pass real PostgreSQL CI smoke.

## Block 8 ? Expectation & Meta Intelligence

Implement historical baselines, Expectation, Surprise, Disappointment, Watchlist, trend detection, and a stable long-term player score distinct from recent Form.

**PASS:** `meta-v1.0` persists same-role historical baselines, Stable,
confidence-gated Surprise/Disappointment, recent-window Trend, and Watchlist
signals; `/meta` and player detail pass real PostgreSQL CI smoke.

## Block 9 ? Perception Intelligence

Create a source registry and structured qualitative pipeline for expert, media, fan, and other supported web evidence with provenance and deduplication.

## Block 10 ? Overrated / Underrated Intelligence

Compare performance with sufficiently supported perception to calculate Underrated, Overrated, Consensus, and Polarization with strong confidence gates.

## Block 11 ? Tactical Intelligence

Add formation profiles and evidence-backed tactical summaries. Never claim spatial precision unsupported by available data.

## Block 12 ? World Radar + Calibration + V1 Hardening

Detect outliers outside core leagues, validate predictive features and model weights, harden costs/security/observability/UX, and complete V1 end-to-end validation.
