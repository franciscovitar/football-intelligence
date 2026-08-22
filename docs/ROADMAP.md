# Roadmap

Each block ends with focused verification and a checkpoint. A block is not complete merely because code exists.

## Progress

- [x] **Block 1 — Foundation** — PASS
- [x] **Block 2 — Data Foundation** — PASS
- [x] **Block 3 — Provider + Data Audit** — PASS
- [x] **Block 4 — Core League Sync** — PASS
- [x] **Block 5 — Player Analytics V1** — PASS
- [x] **Block 6 — First Usable Web** — PASS
- [x] **Block 7 — Team Intelligence** — PASS
- [x] **Block 8 — Expectation & Meta Intelligence** — PASS
- [x] **Block 9 — Perception Intelligence** — PASS
- [x] **Block 10 — Overrated / Underrated Intelligence** — PASS
- [x] **Block 11 — Tactical Intelligence** — PASS
- [x] **Block 12 — World Radar + Calibration + V1 Hardening**
- [x] **Blocks 13-20 — Data Mesh, real-data snapshots, multi-source expansion, entity resolution V2, reconciliation V2** — see `docs/BLOCK20_MULTI_SOURCE.md`'s exit contract (Block 20 = CLOSED / CERTIFIED / MERGED)
- [ ] **V1 Product Closure / Production Readiness** (current phase) — see `docs/PRODUCTION_BOOTSTRAP.md`; the Global Product Closure Review verdict is `CONDITIONAL` pending production data population authorization

## Block 1 — Foundation

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

## Block 2 — Data Foundation

Create PostgreSQL/Supabase persistence using explicit migrations, internal entity IDs, provider mappings, match/player/team stats, constraints, and ingestion metadata.

## Block 3 — Provider + Data Audit

Connect the first real football provider for one league, persist raw + normalized data, establish idempotent upserts, rate-limit awareness, and measure real field coverage.

## Block 4 — Core League Sync

Expand the verified ingestion path to Argentina + Premier League + LaLiga + Serie A + Bundesliga + Ligue 1 with scheduled incremental synchronization and freshness reporting.

## Block 5 — Player Analytics V1

Implement roles, per-90 features, shrinkage, percentiles, confidence, skill scores, Performance, and Form.

## Block 6 — First Usable Web

Expose real rankings, player detail, trends, score explanations, filters, and an internal diagnostics lab.

## Block 7 — Team Intelligence

Implement team features, ELO, Attack, Chance Generation, Finishing Proxy, Defense, Control, Process, Results, Form, and Results-vs-Process diagnostics.

**PASS:** `team-v1.0` persists competition-and-season-relative features, scores,
confidence, diagnostics, and match-level Elo history; `/teams`, `/team/[id]`, and
team `/lab` diagnostics pass real PostgreSQL CI smoke.

## Block 8 — Expectation & Meta Intelligence

Implement historical baselines, Expectation, Surprise, Disappointment, Watchlist, trend detection, and a stable long-term player score distinct from recent Form.

**PASS:** `meta-v1.0` persists same-role historical baselines, Stable,
confidence-gated Surprise/Disappointment, recent-window Trend, and Watchlist
signals; `/meta` and player detail pass real PostgreSQL CI smoke.

## Block 9 — Perception Intelligence

Create a source registry and structured qualitative pipeline for expert, media, fan, and other supported web evidence with provenance and deduplication.

**PASS:** `perception-v1.0` persists auditable source/evidence provenance,
cross-source deduplication, and conservative player mentions; `/perception` and
player detail pass real PostgreSQL CI smoke. Perception scoring remains Block 10 work.

## Block 10 — Overrated / Underrated Intelligence

Compare performance with sufficiently supported perception to calculate Underrated, Overrated, Consensus, and Polarization with strong confidence gates.

**PASS:** `rating-v1.0` source-balances deterministic perception evidence,
applies strong breadth/confidence/polarization gates, persists Rating Gap,
Consensus and Polarization, and exposes `/ratings` plus player-detail context;
PR and merged-main PostgreSQL CI passed.

## Block 11 — Tactical Intelligence

Add formation profiles and evidence-backed tactical summaries. Never claim spatial precision unsupported by available data.

**PASS:** `tactical-v1.0` reuses existing fixture-detail ingestion for nominal
formations, derives Control/Attacking-Volume/Defensive-Resistance proxies and
formation stability from Team Intelligence, and exposes `/tactics` plus
team-detail tactical context; PR and merged-main PostgreSQL CI passed.

## Block 12 — World Radar + Calibration + V1 Hardening

Detect outliers outside core leagues, validate predictive features and model weights, harden costs/security/observability/UX, and complete V1 end-to-end validation.

## Blocks 13-20 and current phase

Work continued past Block 12 into the Data Mesh / real-data-snapshot /
multi-source-expansion track (Blocks 13-20): real ENG_PL 2025/26 evidence
(`docs/REAL_DATA_SNAPSHOT_V2.md`), Product Experience V2
(`docs/PRODUCT_EXPERIENCE_V2.md`), and Wyscout Open + StatsBomb Open
historical/deep adapters with entity resolution V2 and granularity-safe
reconciliation V2 (`docs/BLOCK20_MULTI_SOURCE.md`). Block 20 is the last of
that track and is **CLOSED / CERTIFIED / MERGED** -- see its exit contract
for the full supported/fail-closed/deferred/externally-blocked breakdown
rather than a per-block PASS entry here.

The current phase is **V1 Product Closure / Production Readiness**, not a
new numbered block. The Global Product Closure Review verdict is
`CONDITIONAL`: the application itself (code, security, CI, deployment) is
ready, but real production data has not yet been populated -- see
`docs/PRODUCTION_BOOTSTRAP.md` for the prepared (not yet executed) sequence
and its required explicit authorization. Known V1 limitation: the real
snapshot is ENG_PL 2025/26, the latest **completed** season, with no
approved rich domestic player dataset -- never presented as live/current
coverage.
