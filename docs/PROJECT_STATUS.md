# Football Intelligence — Project Status

**Status:** PAUSED  
**Pause requested:** 2026-08-27  
**Owner intent:** preserve the current verified state and stop active development/research until the project is explicitly resumed.

This document is the durable cross-session checkpoint for the pause. It should be read before restarting substantial Football Intelligence work.

## 1. Canonical state at pause

Repository: `franciscovitar/football-intelligence`

The pause was requested immediately after `main` integrated the RSSSF Argentina 2016 match backbone at:

`1bd8fd459b1478d4555aa7970f9f7e1447d29015`

Quality on that `main` commit:

- workflow run `33102507222`: **SUCCESS**;
- Analytics: Ruff check, Ruff format, mypy and full pytest: **PASS**;
- Web: lint, typecheck and build: **PASS**;
- Database: migrations, schema contracts, PostgreSQL integrations, deterministic smoke checks and Next.js PostgreSQL read path: **PASS**.

When the project is resumed, always re-read the then-current `main`; do not assume this pause commit is still the latest repository state.

## 2. Product goal preserved during the pause

Football Intelligence remains a historical football intelligence product, not merely a live-score product.

The intended target is a multi-season database across the six target leagues:

- Premier League;
- La Liga;
- Serie A;
- Bundesliga;
- Ligue 1;
- Argentina LPF.

Fresh post-match updates are not the current priority. Historical depth and reliable player/team/competition context are more important.

The working direction at the pause is to prefer **several complete historical seasons** over forcing ten years immediately. A practical first target when work resumes is approximately **five seasons**, especially for the Big Five, and then extend backward when the data model and source strategy are proven.

## 3. Data strategy learned so far

The original hope of obtaining a uniform, deep, five-to-ten-season dataset for all six leagues using only free sources is not supported by the evidence gathered so far.

A realistic architecture is layered:

### Layer A — broad historical structure

Usually feasible with free/open sources:

- competitions and seasons;
- teams;
- fixtures;
- dates;
- results;
- standings where available;
- identity/context fields;
- historical rosters where defensible evidence exists.

### Layer B — basic player-season statistics

Highest-priority unresolved layer:

- appearances;
- starts;
- minutes;
- goals;
- assists;
- cards;
- team/season membership;
- position.

Free sources can cover parts of this, but a single reusable zero-cost source with uniform multi-season coverage across all six target leagues has not been found.

### Layer C — deep performance/event data

Examples:

- shots;
- passing detail;
- progressive actions;
- recoveries;
- tackles/interceptions;
- duels;
- xG/xA;
- event-level data.

Do not require uniform coverage for every season unless a licensed provider makes it economically and legally practical.

## 4. Important source conclusions

### Wyscout public dataset

Strong open historical performance/event backbone where its public release has coverage, especially the major European leagues around 2017/18. It is valuable evidence, but it is not a five-to-ten-season universal source.

### Wikidata

Useful profile/identity enrichment source. Existing repository audits already cover real fusion work. Preserve provenance and never treat Wikidata as performance truth.

### RSSSF — Argentina 2016

**Integrated into `main`.**

Production provider/adapter support now exists for the bounded Argentina Primera División 2016 document.

Verified runtime evidence persisted in:

- `docs/audits/rsssf-arg-lpf-2016-match-backbone.md`;
- `docs/audits/rsssf-arg-lpf-2016-match-backbone-runtime.json`.

Observed production-path result:

- 242 matches;
- 1,694 normalized observations;
- 242 logical matches resolved;
- 0 player observations;
- 0 fabricated `kickoff_at` values.

The integration also added generic explicit calendar-year season semantics so genuine `2016` competitions are not silently converted into `2016-2017`.

RSSSF is therefore a match/result backbone for this bounded document, **not** a player-statistics backbone.

### Historical Wikipedia — Argentina 2016

Validated research remains on branch:

`lab/wikipedia-arg-2016-roster-revisions`

Current recorded branch head at pause:

`ed71004a08696e83ea76f8a72ac5ca5befa8e6f1`

Key conclusions:

- historical roster extraction produced 903 player-club slots across 30/30 clubs;
- individual player tables are not reliable enough to become the automatic appearance backbone;
- exact-competition machine-extractable appearance candidates covered only about 30% of roster slots;
- revision drift and direct conflicts with stronger official evidence were observed;
- missing evidence must remain missing, never zero.

Use Wikipedia only as provenance-preserving roster/corroborative evidence unless new evidence changes this decision.

### AFA — Argentina 2016

Validated research remains on branch:

`lab/afa-arg-2016-refined-signals`

Recorded branch head at pause:

`5af1f75e967f48e142aa4d3e123d2571fcb12648`

AFA surviving official articles provide useful partial official signals such as passes, recoveries, assists, fouls, shots and goals, but they do not provide a complete player population/statistical backbone.

The archived Stats Center recovery attempts did not produce a usable full player dataset.

### PlayerElo

Provider research established that `context=full` can expose contextual history rows where data exists, but the target short Argentina 2016 tournament window was absent in tested players.

Do not spend more PlayerElo quota on February–May 2016 Argentina unless new provider evidence appears.

### API-Football

Technically one of the strongest candidates tested for the missing player/stat layer. Existing repository audits show useful player-match/player-appearance data.

However, historical persistence/reuse rights remain the gating issue. A rights/storage inquiry was sent to API-Football and **no reply had been received as of 2026-08-27**.

When work resumes, check the provider reply/status again before making any source decision. Do not infer permission from technical accessibility.

### Proprietary/statistical websites audited

Several sources were technically promising but unsuitable as an automatic free product backbone because of terms, licensing, redistribution or cost constraints. Examples investigated include FBref/Sports Reference, FootyStats, BDFutbol and Football-Lineups.

Preserve the distinction between:

- useful validation/reference source;
- legally reusable ingestion source.

Do not scrape a site merely because the numbers are visible in a browser.

## 5. The key unresolved problem

The main unresolved data problem is no longer fixtures/results. It is **uniform player coverage over multiple historical seasons**, especially:

- appearances;
- starts;
- minutes;
- basic player-season statistics;
- eventually deep performance metrics.

Argentina is materially harder than the Big Five and should not block progress on the European historical dataset.

## 6. Recommended plan when the project resumes

Do not restart source research from zero.

Recommended sequence:

1. Read current `main`, this checkpoint, `AGENTS.md`, `WORKFLOW.md` and only the minimal relevant audits.
2. Re-check any time-sensitive provider/licensing facts, especially API-Football.
3. Define the exact minimum player-season schema required for a useful V1 historical profile.
4. Target roughly five seasons first rather than ten.
5. Prioritize the Big Five for consistent multi-season player coverage.
6. Keep Argentina progressive: best available coverage without letting it block the rest of the product.
7. Use free/open data for structural/historical layers wherever possible.
8. If free-only evidence cannot satisfy the required player fields, evaluate **one licensed paid historical source** rather than continuing indefinitely with brittle source stitching.
9. Only consider a paid source if its contract/terms explicitly permit the required storage, retention, derived use and product display after acquisition/cancellation.
10. Preserve source provenance, confidence, model/source roles and `missing != zero` throughout.

## 7. Paid-data decision is not yet made

The project is **not committed to paying for a provider**.

The pause-state conclusion is only that a paid/licensed source is likely to be necessary if the product requires a uniform deep player database across five or more seasons and all target leagues.

No paid plan should be activated without explicit owner approval and a verified rights/storage review.

## 8. What not to repeat on resume

Unless new evidence contradicts the existing checkpoints, do not repeat:

- broad Wikipedia player-table parser experiments for Argentina 2016;
- PlayerElo probing of the known February–May 2016 Argentina gap;
- attempts to treat RSSSF as a player-minute source;
- generic scraping of proprietary sites whose terms already make them unsuitable;
- analysis that assumes missing data is zero;
- source fusion that silently resolves identity/stat conflicts.

## 9. Pause boundary

From 2026-08-27 onward, Football Intelligence is intentionally **paused**.

No further product development, source acquisition, provider spending, production ingestion or expansion work is implied by this checkpoint.

When the owner explicitly asks to resume Football Intelligence, this document should be treated as the starting handoff, then reconciled against the current `main` and current external provider evidence.