# StatsBomb Open historical coverage audit

Status: technical spike in progress.

## Decision question

Can StatsBomb Open provide defensible zero-cost player/event evidence for the six Football Intelligence core leagues in the historical gap around 2016-2021, and if so at what exact competition-season-match coverage?

## Scope

Targets:

- `ARG_LPF` — Liga Profesional Argentina
- `ENG_PL` — Premier League
- `ESP_LL` — La Liga
- `ITA_SA` — Serie A
- `GER_BL1` — Bundesliga
- `FRA_L1` — Ligue 1

Primary gap window: domestic seasons beginning 2016 through 2021. Adjacent 2015/16 and 2022/23 catalogue entries may be measured only to understand source shape; they are not substitutes for the missing window.

This is an audit only. It does not promote StatsBomb Open into the canonical database, create canonical player identities, or imply complete league-season coverage from catalogue presence alone.

## Source checkpoint

Audit against the current public `hudl/open-data` repository at commit:

`b0bc9f22dd77c206ddedc1d742893b3bbe64baec`

The catalogue is `data/competitions.json`. Match files are provider-scoped by StatsBomb competition and season IDs.

## Current public evidence

The current catalogue is heterogeneous. It lists La Liga for 2016/17 through 2020/21 and Ligue 1 for 2021/22 inside the main gap window, while the other target domestic leagues do not expose corresponding seasons there. Catalogue presence is not enough: a listed competition-season may be a subset rather than a complete domestic season.

The runtime audit must therefore count actual match records and compare them with the expected domestic league match count before any completeness claim.

## Licence / attribution note

The open-data repository states that the data is freely available for public use for research projects and genuine interest in football analytics. Its README requires attribution to StatsBomb and use of the StatsBomb logo when publishing, sharing or distributing research, analysis or insights based on the data. Exact product/commercial suitability remains provider-scoped and must be reviewed against the current StatsBomb Public Data User Agreement before product promotion.

This audit records technical/data coverage only; it does not certify product publication rights.

## Exit criteria

The spike is complete when it records, for each relevant target competition-season:

- StatsBomb competition ID and season ID;
- actual open match count;
- expected domestic match count where structurally known;
- full vs partial coverage classification;
- sample event and lineup availability;
- useful player/event schema evidence;
- explicit limitations and compliance state.

No database write, canonical identity creation, product promotion or deployment is allowed in this spike.
