# Wikipedia historical ARG_LPF 2024 undercount cadence

Status: **completed; Wikipedia rejected as a complete roster-season backbone**.

The four-cut historical Wikipedia union was below the official LPF players-used
lower bound for Banfield, Newell's Old Boys, Godoy Cruz, and Barracas Central.
This bounded follow-up added six intermediate historical cuts for only those
four clubs: 2024-05-31, 2024-06-30, 2024-08-15, 2024-09-30, 2024-10-31, and
2024-11-30.

## Runtime evidence

Workflow run: `32921774722`.

- 24/24 requested historical revisions collected successfully;
- 24/24 contained accepted active-squad evidence;
- generic static-snapshot checksum verification: `PASS`;
- maximum revision lag among the extra cuts: 3,722,936 seconds (~43.09 days);
- artifact ID: `9590074485`;
- artifact name: `wikipedia-arg-lpf-2024-undercount-cadence-32921774722`;
- artifact SHA-256: `bde175e5f3fd8a36a5e03595a3cb752d99b580969339c1d9eca4f52b584e0637`.

The new revisions were not merely duplicates of one old article state. Across
the ten combined cuts, the tested clubs exposed multiple distinct revision ids:

- Banfield: 9 distinct revisions;
- Newell's Old Boys: 10 distinct revisions;
- Godoy Cruz: 8 distinct revisions;
- Barracas Central: 6 distinct revisions.

## Ten-cut union result

The extra six cuts added **zero new deterministic provider-local player
identities** to the four-cut union for every tested club.

| Club | Four-cut union | Ten-cut union | Official LPF players used | Remaining gap |
| --- | ---: | ---: | ---: | ---: |
| Club Atlético Banfield | 37 | 37 | 43 | -6 |
| Newell's Old Boys | 38 | 38 | 43 | -5 |
| Godoy Cruz Antonio Tomba | 37 | 37 | 40 | -3 |
| Barracas Central | 33 | 33 | 34 | -1 |

The official LPF value is only a lower-bound validation target; reaching it
would not prove completeness because an active squad also contains non-used
players. Remaining below it after ten sampled cuts is stronger: the Wikipedia
membership route demonstrably cannot represent all players that the official
competition says were actually used.

## Decision

Stop increasing Wikipedia snapshot cadence for the purpose of building a
complete ARG_LPF 2024 roster-season backbone. The denser experiment produced no
coverage gain despite multiple distinct article revisions, so more sampling has
no demonstrated return.

Retain historical Wikipedia only for the roles it has actually passed:

- source-local dated `player_membership` evidence;
- deterministic player-article identity hints;
- bridge input to Wikidata after the explicit `P31 = human` gate;
- profile/identity enrichment and cross-source corroboration.

Do not describe this source as AFA registration, complete season participation,
or canonical Football Intelligence identity. Independiente Rivadavia remains an
explicit free-source roster gap, while Vélez remains handled by separate primary
club evidence.
