# Wikidata ARG_LPF 2016 roster feasibility — 2026-08-26

Status: **C_insufficient** for roster construction; useful only as profile/enrichment evidence.

## Scope

Bounded lab over the 30 clubs in Argentina Primera División 2016.

Season window used for temporal proof:

- start: `2016-02-05`
- end: `2016-05-29`

A `P54` membership counted as compatible only when its non-deprecated `P580`/`P582` qualifiers, with supported Gregorian precision, **guaranteed** overlap with that window. Year-only or otherwise imprecise boundaries that merely made overlap possible remained ambiguous and were not counted as roster evidence.

No PlayerCrosswalk, PostgreSQL write, or product promotion occurred.

## Runtime evidence

GitHub Actions run: `32998029703`

Artifact: `wikidata-arg-lpf-2016-roster-feasibility`

Artifact digest: `sha256:5b550ee11beab7a6dae3a631d097e0d6ead7a411a097e4423eab08c3ec48c531`

## Aggregate result

- clubs: **30**
- unique historical players discovered across those clubs: **6,681**
- total non-deprecated P54 membership statements: **12,459**
- temporally bounded statements: **8,953**
- statements with guaranteed overlap with Primera 2016: **56**
- temporally ambiguous statements: **202**
- statements with insufficient temporal evidence: **3,506**
- unique players with guaranteed Primera-2016 overlap: **56**
- compatible players per club: **min 0 / median 1 / max 5**
- clubs with at least 18 compatible players: **0/30**
- clubs with at least 5 compatible players: **3/30**

The fixed decision heuristic therefore returned **`C_insufficient`**.

## Compatible-profile richness

The small compatible subset is high quality for enrichment:

- DOB: **56/56**
- citizenship: **56/56**
- position: **55/56**
- height: **51/56**

Source-local qualifiers on compatible P54 statements:

- players with `P1350` matches evidence: **44**
- players with `P1351` goals evidence: **44**

`P1350` / `P1351` remain statement-scoped evidence. They are **not** automatically interpreted as Primera-2016 regular-phase totals unless statement scope proves that semantic.

## Per-club breadth highlights

Highest compatible-player counts:

- Independiente: 5
- Racing Club: 5
- River Plate: 5
- Boca Juniors: 4
- Tigre: 4
- Vélez Sarsfield: 4

Zero compatible players under the strict temporal rule:

- Defensa y Justicia
- Patronato
- Quilmes
- San Martín de San Juan
- Temperley

## Decision

Wikidata must **not** be used as a roster backbone for `ARG_LPF` historical seasons based on P54 temporal membership alone.

The 2016 test improved over the earlier 2024 lab, but not remotely enough for league-wide roster reconstruction. Treat Wikidata in Argentina as:

- identity/profile enrichment;
- temporal corroboration where qualifiers are strong;
- source-local historical matches/goals evidence when present;
- never `membership without sufficient dates => season roster`.

This closes the roster-backbone hypothesis for Argentina. Future zero-cost work should prioritize a static/open **player-season / appearances / minutes** source, while AFA/DataFactory-derived official historical rankings can be retained as scoped refined-performance evidence.
