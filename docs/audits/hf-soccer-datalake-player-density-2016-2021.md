# Public soccer data lake — player-density audit, 2016–2021

Status: **technical conditional GO / product BLOCKED**.

This audit evaluates the public `eatpizzanot/soccer-dataset` distribution only as a candidate historical evidence source. It does not promote the source into Football Intelligence, write PostgreSQL, create canonical crosswalks, or treat calendar years as canonical seasons.

## Decision question

Can the public data lake materially fill Football Intelligence's free historical player-data gap for the six core leagues between 2016 and 2021?

## Runtime evidence

Two bounded read-only GitHub Actions laboratories downloaded only the four public Parquet tables required for the question (`leagues`, `fixtures`, `fixture_players`, `fixture_players_stats_flat`). No secret or database write was involved.

- density run: `32993243428`; artifact digest `sha256:0f4bc812df44f9f2cbbd7305879f96fd48b26778ffc064ac1efff27874562570`;
- player-semantics run: `32993975454`; artifact digest `sha256:936577b7b1375c71fc8f1509a16e5f63070b1280c05b2f5cb63dc7865ded1a26`.

The durable machine-readable summary is `docs/audits/hf-soccer-datalake-player-density-2016-2021.json`.

## League identity

The public Parquet data resolved all six intended API-Football league IDs uniquely:

| FI code | API-Football | Dataset league id |
| --- | ---: | ---: |
| `ARG_LPF` | 128 | 28 |
| `ENG_PL` | 39 | 1 |
| `ESP_LL` | 140 | 5 |
| `ITA_SA` | 135 | 7 |
| `GER_BL1` | 78 | 11 |
| `FRA_L1` | 61 | 9 |

## Density result

The predeclared gate classified a league/calendar-year cell as `strong` when at least 85% of played fixtures had player rows and at least 70% had detailed player-stat rows.

Result across 6 leagues × 6 calendar years:

- **32 strong**;
- **3 partial**;
- **1 weak**.

Weighted 2016–2021 fixture coverage:

| League | Fixtures with player evidence | Fixtures with detailed player stats |
| --- | ---: | ---: |
| Argentina | 77.0% | 71.4% |
| Premier League | 100.0% | 100.0% |
| La Liga | 89.1% | 89.0% |
| Serie A | 91.7% | 91.6% |
| Bundesliga | 95.6% | 95.5% |
| Ligue 1 | 100.0% | ~100.0% |

The only non-strong cells were:

- `ARG_LPF` 2016 — weak: 41.2% player fixtures / 20.6% detailed-stat fixtures;
- `ARG_LPF` 2017 — partial: 83.0% / 82.4%;
- `ARG_LPF` 2018 — partial: 83.9% / 83.0%;
- `ESP_LL` 2017 — partial: 83.7% / 83.7%.

These percentages are coverage evidence only. They do not prove that every metric is semantically usable.

## Player-row semantics

The second runtime audit materially clarified the tables:

- `fixture_players` behaves like **matchday-squad evidence** and can include unused substitutes;
- `fixture_players_stats_flat` can also contain unused-substitute rows in later years;
- `games_minutes IS NOT NULL` is strong direct evidence that the player actually appeared;
- `games_minutes IS NULL` must remain missing and must **not** be promoted to a zero-minute appearance;
- rating and pass values were not observed on audited rows whose `games_minutes` was null;
- after conditioning on non-null minutes, covered fixtures contain roughly **27–31 actual player appearances per match**, a football-plausible range.

This explains why raw field non-null percentages drop in 2020–2021: later snapshots include more unused bench players, not simply poorer observation of players who actually played.

## Argentina 2016 is a real gap

The weak 2016 Argentina result is localized, not random:

- February–May: **zero** player/stat coverage;
- first player-covered fixture: `2016-08-26`;
- first detailed-stat fixture: `2016-08-27`;
- August–October: player rows exist broadly but detailed stats are still thin;
- November–December: both player and detailed-stat fixture coverage are about 88%.

Therefore this source cannot be presented as a complete ARG_LPF 2016 player backbone. A separate free source is still required for the early-2016 competition period.

## Metric warnings

Coverage is not metric equivalence. At minimum:

- null goals/assists have not been proven to mean zero;
- `tackles_total` availability changes sharply across league/year cells, while related defensive fields can remain populated;
- xG was not evaluated by this audit;
- metric-specific source semantics must be reviewed before mapping into Football Intelligence's canonical metric catalog.

## Rights/provenance blocker

The dataset declares CC-BY-4.0 but identifies API-Football and football-data.co.uk as upstream sources. Football Intelligence must not assume that a downstream licence automatically grants all publication rights for upstream competition data.

Until rights/redistribution are clarified, the source remains:

`candidate_rights_blocked`

This is a **product blocker**, not a technical-feasibility failure.

## Next work if rights become acceptable

1. map source fixtures into real canonical seasons rather than calendar-year buckets;
2. audit each desired player metric for null/zero and field-version semantics;
3. design a source-local immutable snapshot and provenance contract;
4. reconcile players by stable external IDs where possible;
5. retain a separate workstream for Argentina early 2016.
