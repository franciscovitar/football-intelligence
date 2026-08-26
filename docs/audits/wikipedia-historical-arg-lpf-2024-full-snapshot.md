# Wikipedia historical ARG_LPF 2024 full snapshot

Status: **bounded real collection completed and inspected on the isolated lab branch**.

This checkpoint freezes exact historical English-Wikipedia article revisions for
the 26 ARG_LPF clubs whose active-squad sections passed the earlier source audit.
Vélez Sarsfield and Independiente Rivadavia are deliberately outside this
Wikipedia snapshot: Vélez has separate primary club convocatoria evidence and
Independiente Rivadavia remains an explicit free-source coverage gap.

This is source-local `player_membership` evidence only. It must not be
interpreted as AFA/COMET registration, Torneo LPF appearance, season statistics,
or Football Intelligence canonical identity.

## Runtime and integrity evidence

Full collection workflow:

- run: `32921437933`;
- branch head used by the run: `82e11e4a685a6a693b53be6b2adefea6cff77338`;
- four explicit snapshot targets;
- 26 clubs per target;
- 104 historical revision requests total;
- all four matrix jobs: `success`;
- every cut passed the generic static-snapshot checksum validator;
- every returned revision had a positive revision id and
  `revision_timestamp <= snapshot_target`;
- every one of the 104 requests contained accepted active-squad evidence.

The repository Quality workflow for the same branch head also passed all three
jobs in run `32921437940`: Analytics, Database, and Web.

| Cut | Target | Active-squad evidence | Observations | Min/club | Max/club | Max revision lag | Artifact ID | Artifact SHA-256 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| opening | 2024-05-10T23:59:59Z | 26/26 | 752 | 24 | 43 | 99.61 days | 9589975259 | `ccf2efca9ef7a047a54a1908a98345b3ec78d026ab2e91f47d0f34a04a4c30bc` |
| midyear | 2024-07-15T23:59:59Z | 26/26 | 751 | 23 | 44 | 87.26 days | 9589959278 | `621c28c6f94ec4c2a4fb8712c9bf33d7f7845eae382d694327cf61ca6617f2fd` |
| window-close | 2024-09-06T23:59:59Z | 26/26 | 750 | 24 | 43 | 99.08 days | 9589974274 | `8e64680993d820b8010698743a9dea218ca74361012e23027b1b0c9602d73de9` |
| final | 2024-12-16T23:59:59Z | 26/26 | 782 | 25 | 43 | 51.06 days | 9589975270 | `803742dcac7943eb139dff9d4ad979867fd8c74afc845c7f2ec2064bacee6dfe` |

Across all 104 requests, revision freshness relative to the lookup target was:

- 49/104 (47.1%) within 7 days;
- 61/104 (58.7%) within 14 days;
- 85/104 (81.7%) within 30 days;
- 96/104 (92.3%) within 60 days;
- 100/104 (96.2%) within 90 days.

The four requests older than 90 days were:

- Unión de Santa Fe at the opening cut;
- Defensa y Justicia at the opening cut;
- Barracas Central at the opening cut;
- Atlético Tucumán at the window-close cut.

This does **not** turn those rows into invalid or zero evidence. It changes their
temporal interpretation: the direct observation time is the historical
`revision_timestamp`; `snapshot_target` is only the upper bound used to select
the latest available revision at or before that target. A downstream transform
must preserve both values and must not silently describe an old revision as an
exact observation at the target date.

## Four-cut season-union audit

The retained parser was reapplied to the immutable raw bytes and the four cuts
were unioned per club using the same deterministic provider-local identity key
(`player_article_title` when present, otherwise normalized display name).

The 26-club union contains **1,087 provider-local player membership rows**. This
is not a count of AFA registrations and is not directly equivalent to the LPF
`JUGADORES UTILIZADOS` statistic.

The official LPF players-used counts nevertheless provide a useful lower-bound
validation. For four clubs, the four-cut Wikipedia union is below the official
number of players actually used:

| Club | Four-cut Wikipedia union | Official LPF players used | Gap |
| --- | ---: | ---: | ---: |
| Club Atlético Banfield | 37 | 43 | -6 |
| Newell's Old Boys | 38 | 43 | -5 |
| Godoy Cruz Antonio Tomba | 37 | 40 | -3 |
| Barracas Central | 33 | 34 | -1 |

Therefore four dated active-squad snapshots are **not sufficient to certify a
complete season-player backbone**, even though all 104 source requests contain
valid membership evidence. A player can be used during a short interval that is
not represented by one of the four selected revisions, and Wikipedia revision
freshness itself is uneven.

For clubs whose union is equal to or above the LPF used count, completeness is
still not proven: an active squad contains non-used players and can still omit a
used player while having a larger total count.

## Decision

Retain the historical Wikipedia route as a reproducible, attribution-preserving
`player_membership` source and as an identity/profile bridge input. Do **not**
promote the four-cut union as a complete ARG_LPF 2024 roster source.

Next bounded experiment: add denser historical cuts only for the four proven
undercount clubs and measure whether the deterministic union reaches or exceeds
the official used-player lower bound. If denser cadence still undercounts, stop
trying to make Wikipedia the complete roster backbone and keep it only as
membership/identity enrichment.
