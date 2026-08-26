# RSSSF Argentina 2016 — player-evidence feasibility

Status: **NO-GO as player/appearance backbone; useful fixture/result corroboration**.

## Decision question

Can the RSSSF `Argentina 2016` document fill the early-2016 Argentina player-evidence gap with lineups, appearances or substitution evidence across the Primera División championship?

## Scope and source rights

Source: `https://www.rsssf.org/tablesa/arg2016.html`

The document was prepared and maintained by Osvaldo José Gorgazzi for RSSSF, last updated 11 May 2017. Its own copyright notice explicitly says that the document may be copied in whole or part provided proper acknowledgement is given to the author. This is materially clearer reuse language than most presentation-site candidates audited for this project, although it is not a standard machine-data licence and any later product use should preserve attribution and provenance.

## Primera División structure

The top-tier section identifies 30 teams split into two groups. Each club played 16 group/intergroup matches. This yields 240 regular/group-stage fixtures, followed by:

- one match between the second-placed teams; and
- one championship final.

Total top-tier championship fixtures represented: **242**.

RSSSF provides round/date, teams, score and venue for the regular championship fixture list.

## Player-depth finding

The regular fixture section does **not** provide starting XIs or substitute lists for each match.

The only complete lineup block inside the `Campeonato de Primera División 2016` section is attached to the championship final on 29 May 2016:

`San Lorenzo 0-4 Lanús`

That block includes:

- starters;
- substitutes;
- substitution minutes;
- cards;
- captain/goalkeeper annotations;
- coaches;
- match officials.

No comparable lineup block is present for the preceding regular rounds or the second-place playoff in the top-tier section.

Therefore observed complete-lineup density for the championship is approximately:

`1 / 242 = 0.4%`

This is far below any threshold suitable for reconstructing league-wide rosters, starts, appearances or minutes.

## Decision

RSSSF is **not** a solution to the early-2016 Argentina player backbone.

Current source role for this problem:

`fixture_result_corroboration_only`

It may be useful for:

- independent fixture/result reconciliation;
- exact competition structure and phase scope;
- stadium/date context;
- the final's one detailed lineup as a small corroboration sample;
- attribution-friendly historical reference.

It must not be presented as:

- a complete roster source;
- a player-season source;
- an appearance/minutes source for Primera 2016;
- evidence that regular-season lineups are available simply because the final contains them.

## Consequence

Continue the zero-cost search for a separate static/open source covering at least roster + appearances/minutes for February–May 2016. The official AFA `#NúmerosDePrimera` series remains useful as sparse, phase-scoped derived-performance evidence but does not replace the missing player backbone.
