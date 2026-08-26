# StatsBomb Open historical coverage audit

Status: completed technical spike.

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

Primary gap window: domestic seasons beginning 2016 through 2021. Adjacent 2015/16 and 2022/23 entries were measured only to understand source shape.

This was an audit only. No canonical identity creation, database write, product promotion or deployment occurred.

## Source checkpoint

Observed against the current public `hudl/open-data` repository at commit:

`b0bc9f22dd77c206ddedc1d742893b3bbe64baec`

Runtime audit run:

- GitHub Actions run `32972823047`
- artifact `statsbomb-open-historical-coverage-audit-32972823047`
- artifact ID `9608263135`
- artifact digest `sha256:f920a7d50adae93d20b3644df097d365667b1aee32a6a92f85768512f5a8b1ef`
- frozen catalogue SHA256 `e6cd42f5d8956d6aa30fb917ce8d4c3b3df1879a93f02f8feba820930a6971fa`

## Observed coverage

### Primary 2016-2021 gap

| Competition | Season | Open matches | Domestic total | Coverage | Classification | Observed concentration |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `ESP_LL` | 2016/17 | 34 | 380 | 8.95% | partial | Barcelona appears in all 34 matches |
| `ESP_LL` | 2017/18 | 36 | 380 | 9.47% | partial | Barcelona appears in all 36 matches |
| `ESP_LL` | 2018/19 | 34 | 380 | 8.95% | partial | Barcelona appears in all 34 matches |
| `ESP_LL` | 2019/20 | 33 | 380 | 8.68% | partial | Barcelona appears in all 33 matches |
| `ESP_LL` | 2020/21 | 35 | 380 | 9.21% | partial | Barcelona appears in all 35 matches |
| `FRA_L1` | 2021/22 | 26 | 380 | 6.84% | partial | Paris Saint-Germain appears in all 26 matches |

No StatsBomb Open domestic competition-season was present in this primary gap for:

- `ARG_LPF`;
- `ENG_PL`;
- `GER_BL1`;
- `ITA_SA`.

Therefore the open catalogue does **not** provide a multi-league complete historical backbone for 2016-2021.

### Adjacent evidence

The adjacent 2015/16 season is much stronger in some leagues:

| Competition | Season | Open matches | Domestic total | Classification |
| --- | ---: | ---: | ---: | --- |
| `ENG_PL` | 2015/16 | 380 | 380 | full by match count |
| `ESP_LL` | 2015/16 | 380 | 380 | full by match count |
| `ITA_SA` | 2015/16 | 380 | 380 | full by match count |
| `FRA_L1` | 2015/16 | 377 | 380 | near-complete, 3 matches missing |
| `GER_BL1` | 2015/16 | 34 | 306 | partial; Bayer Leverkusen appears in all 34 matches |

The adjacent Ligue 1 2022/23 entry contains 32 of 380 league matches and Paris Saint-Germain appears in all 32.

This asymmetry is important: StatsBomb Open can expose a complete domestic season in one period and a club-concentrated subset in another. Catalogue presence must never be interpreted as season completeness without counting the underlying match records.

## Event / lineup depth

For every audited competition-season, the sampled match resolved both:

- an event JSON file;
- a lineup JSON file.

Observed event types include direct actions useful to Football Intelligence such as:

- passes;
- carries;
- shots;
- pressures;
- duels;
- interceptions;
- blocks;
- clearances;
- dribbles;
- ball recoveries;
- fouls;
- goalkeeper actions;
- substitutions;
- tactical shifts.

Sample shot events contained `statsbomb_xg`, and sampled lineup player records contained provider player IDs, names, jersey numbers, country and position information.

This is strong `ADVANCED` / event-level evidence where coverage exists, but does not expand the number of covered matches beyond the observed subset.

## Licence / attribution state

The current open-data README says the data is freely available for public use for research projects and genuine interest in football analytics. It requires attribution to StatsBomb and use of the StatsBomb logo when publishing, sharing or distributing research, analysis or insights based on the data.

This audit does **not** certify Football Intelligence product/commercial publication rights. Exact use still requires review against the current StatsBomb Public Data User Agreement before promotion into public product output.

## Conclusion

**CONDITIONAL GO as partial/high-depth evidence.**

**NO-GO as the 2016-2021 historical backbone.**

StatsBomb Open is worth retaining because its event data is rich and its sampled schema is highly useful. However, inside the target gap its domestic coverage is sparse and club-concentrated rather than league-complete. It cannot solve the broad six-league player-history problem by itself.

## Recommended use

- retain StatsBomb Open as source-scoped event/lineup/xG evidence where an exact match is covered;
- consider full 2015/16 Premier League, La Liga and Serie A as especially strong optional historical blocks if V1 expands one season earlier;
- never treat the Barcelona- or PSG-concentrated seasons as complete league evidence;
- preserve missing matches as missing, not zero;
- continue searching for complete player-season or refined-score sources for 2016/17 through 2021/22.

## Nonclaims

This spike does not prove:

- that all event files exist for every observed match; one representative match per competition-season was resolved;
- that StatsBomb player IDs map canonically to Football Intelligence identities;
- that all event semantics are already mapped to Football Intelligence metrics;
- that public/commercial display rights are certified;
- that a club-concentrated sample is representative of the entire league.
