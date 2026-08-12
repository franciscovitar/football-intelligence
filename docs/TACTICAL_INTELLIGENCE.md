# Tactical Intelligence V1

Block 11 adds formation profiles and evidence-backed tactical summaries without
pretending that aggregate box-score data is tracking data.

Model version: `tactical-v1.0`.

Source quantitative model: `team-v1.0`.

## What V1 can support

The singular API-Football fixture response already used by the core sync can
include lineups. Block 11 normalizes the provider's nominal formation and coach
into `football.team_match_lineups`; it does not add another API request per fixture.

The tactical analytics layer then combines:

- Team V1 `Control`;
- Team V1 `Chance Generation` as an attacking-volume proxy;
- Team V1 `Defense` as a shot-resistance proxy;
- observed nominal formation frequency.

This gives a compact description of how a team is producing without claiming
spatial detail the source data cannot prove.

## Formation profile

For each team/season:

- count observed nominal formations;
- identify the most frequent formation;
- calculate its share of observed lineups;
- calculate formation coverage against the team's Team V1 match sample;
- label formation use as stable, variable, mixed, limited-evidence, or unavailable.

A formation such as `4-3-3` is the provider's nominal lineup shape. It is not
treated as proof that the team defended, pressed, or attacked in that exact shape
for the full match.

Formation confidence increases with both coverage and repeated use of the primary
formation.

## Observable style signals

V1 intentionally uses a small deterministic vocabulary.

### Control + volume

High Team V1 Control and high Chance Generation.

### Possession control

High Control with more moderate Chance Generation.

### Volume with lower control

High Chance Generation with lower Control.

This **does not prove counterattacking football**.

### Low control + low volume

Both dimensions are low relative to the competition.

### Balanced

No strong V1 extreme between those dimensions.

## Defensive signal

Team V1 Defense already combines opponent shot volume, shots on target, and shots
inside the box, with lower conceded volume treated as better.

Tactical V1 maps that dimension to:

- restrictive shot profile;
- balanced;
- permissive shot profile;
- insufficient evidence.

It does not infer defensive block height or pressing intensity.

## Claims V1 deliberately does not make

Without event locations, tracking, pressure events, possession sequences, or
verified transition events, V1 does not claim:

- high press / low block / mid block;
- pressing triggers;
- exact defensive shape;
- man-oriented or zonal pressing;
- counterattack frequency;
- build-up lanes;
- player movement paths;
- which player marks which opponent;
- formation changes minute by minute.

Those can be added only when the data source actually supports them.

## Persistence

`football.team_match_lineups` stores nominal formation and coach observed for a
team in a match.

`analytics.team_tactical_snapshots` stores:

- Team V1 source confidence;
- Control;
- attacking-volume proxy;
- defensive-resistance proxy;
- deterministic style/defensive signals;
- primary formation and observed share;
- formation coverage/confidence;
- alternative formations;
- overall tactical confidence;
- deterministic summary;
- explicit evidence and unsupported-claim boundaries;
- model versions and timestamp.

## Web

`/tactics` exposes the latest tactical profiles per competition.

`/team/[id]` adds the latest Tactical Intelligence panel beside Team Intelligence.

## Scheduling

The core sync already retrieves each selected completed fixture by singular ID.
Those responses can contain lineups, so formation persistence piggybacks onto the
existing request. After Team Analytics completes, the workflow runs Tactical
Intelligence.

No new service, queue, scraper, or recurring provider call is introduced.

## Historical coverage

Matches synchronized before Block 11 may not have normalized formation rows even
if their raw provider payload originally contained lineups.

V1 does not spend additional API quota on a broad historical formation backfill.
Formation coverage grows as fixtures are synchronized/re-synchronized. Missing
formation data remains visible as missing.

## Calibration

Block 12 should review thresholds and labels against real tactical examples.
These labels are useful summaries, not ground truth.
