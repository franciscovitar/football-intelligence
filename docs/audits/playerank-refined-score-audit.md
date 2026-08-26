# PlayeRank refined-score audit

Status: bounded source/model audit on `lab/playerank-refined-score-audit`. No database write, product promotion, canonical-player creation, deploy or merge to `main` is implied by this document.

## Decision

PlayeRank is a strong example of the V1 zero-cost strategy recorded in `docs/V1_ZERO_COST_HISTORICAL_DATA_STRATEGY.md`: where a defensible historical model output already exists, Football Intelligence can ingest that external result as provider/model-scoped evidence instead of requiring every underlying raw input to be reconstructed first.

For the five European Football Intelligence core leagues in 2017/18, the public PlayeRank artifact provides a role-aware player-match performance score with complete match-schedule coverage and deterministic linkage to the existing Wyscout Open identities/matches.

It is therefore a useful **external model evidence candidate** for:

- `ENG_PL` 2017/18;
- `ESP_LL` 2017/18;
- `ITA_SA` 2017/18;
- `GER_BL1` 2017/18;
- `FRA_L1` 2017/18.

It does **not** cover `ARG_LPF`, and this audit does not generalize the result to other seasons.

PlayeRank is not treated as objective ground truth, a canonical Football Intelligence rating, or an automatically comparable score against ratings from other providers/models.

## Primary sources

- PlayeRank Figshare dataset: <https://figshare.com/articles/dataset/PlayeRanks/9361148>
- DOI: <https://doi.org/10.6084/m9.figshare.9361148.v1>
- original PlayeRank paper: <https://arxiv.org/abs/1802.04987>
- official PlayeRank implementation: <https://github.com/mesosbrodleto/playerank>
- Wyscout Open / Scientific Data paper: <https://www.nature.com/articles/s41597-019-0247-7>
- later methodological critique, `Revisiting PlayeRank`: <https://arxiv.org/abs/2407.13439>

The frozen Figshare metadata reports **CC BY 4.0** for the PlayeRank dataset. Wyscout Open is also published under CC BY 4.0 through the existing open-data path already used by Football Intelligence.

## Frozen audit evidence

Workflow run: `32970661139`

Artifact:

- name: `playerank-refined-score-audit-32970661139`;
- artifact id: `9607452705`;
- uploaded ZIP digest: `sha256:6098ff72b19564f9088355249991d5b02bfcbede35ee5062a6a47040cfffcc5c`.

The audit froze:

- Figshare article metadata;
- the exact `playerank.json` file;
- deterministic audit summary;
- checksum manifest.

Actual PlayeRank file metadata:

- Figshare file id: `16972010`;
- file name: `playerank.json`;
- byte size: `6,241,757`;
- MD5 reported by Figshare: `dbb3671e04eb37f30ef4006986748812`;
- SHA-256 observed by Football Intelligence: `8f3ef4a2b2ffba2c88a041ae90a07c74080f7ae1bcf555b5d05c4992d5834acb`.

Figshare metadata observed:

- title: `PlayeRanks`;
- DOI: `10.6084/m9.figshare.9361148.v1`;
- licence: `CC BY 4.0`;
- published: `2019-08-08T08:53:20Z`;
- modified: `2023-05-30T11:36:37Z`.

## Empirical dataset shape

The real downloaded artifact contains:

- **46,897** player-match rows;
- **1,941** unique Wyscout match ids;
- **2,719** unique Wyscout player ids;
- **0** missing required fields among `goalScored`, `playerankScore`, `matchId`, `playerId`, `roleCluster`, `minutesPlayed`;
- **0** null `playerankScore` values;
- **0** duplicate `(matchId, playerId)` pairs;
- **0** PlayeRank match ids unmatched against the Wyscout Open match snapshot used in the audit;
- **0** PlayeRank player ids unmatched against the Wyscout Open player snapshot used in the audit.

The exact ID alignment is particularly valuable: PlayeRank and Wyscout Open can be joined deterministically inside the same Wyscout provider identity space. This does **not** make Wyscout ids canonical Football Intelligence ids; normal FI canonical identity rules still apply when crossing provider boundaries.

## Five-league 2017/18 coverage

| FI competition | PlayeRank rows | Unique matches | Wyscout league matches | Unique scored players |
| --- | ---: | ---: | ---: | ---: |
| `ENG_PL` | 9,059 | 380 | 380 | 463 |
| `ESP_LL` | 9,218 | 380 | 380 | 493 |
| `ITA_SA` | 9,292 | 380 | 380 | 485 |
| `GER_BL1` | 7,391 | 306 | 306 | 427 |
| `FRA_L1` | 9,173 | 380 | 380 | 488 |

Thus PlayeRank covers the full Wyscout Open league match schedule for all five European core competitions in 2017/18.

The same artifact also contains Euro and World Cup observations, but those are outside this audit's six-core-league decision question.

## What the model output represents

The public artifact exposes, per player-match row:

- `playerId`;
- `matchId`;
- `roleCluster`;
- `minutesPlayed`;
- `goalScored`;
- `playerankScore`.

Role clusters are model/provider outputs such as `central MF`, `central FW`, `left CB`, `right CB`, `left FW`, `right FW`, `left MF`, `right MF`, plus smaller hybrid labels. They must remain PlayeRank-scoped role evidence rather than silently becoming canonical Football Intelligence positions.

The original PlayeRank methodology is data-driven and role-aware. The score is therefore a **model output**, not a direct observed football fact.

## Important scale discrepancy

The Figshare page describes the score as being in a `0-1` range. The actual frozen `playerank.json` does not satisfy that description.

Observed real artifact values:

- minimum `playerankScore`: **-0.1192**;
- maximum `playerankScore`: **0.1731**;
- mean: approximately **0.006796**;
- null scores: **0**.

Football Intelligence must therefore preserve the exact artifact value and must **not** silently rescale it to 0-1 or describe it as a probability/percentage.

The official implementation contains multiple rating-processing stages, including normalization logic, which may explain why different PlayeRank representations exist. This audit does not claim that the Figshare field is definitely a specific pre- or post-normalization internal representation. The empirical artifact governs ingestion semantics until direct documentation establishes otherwise.

A safe metric name should make this explicit, for example `playerank_score_raw`, with source/model version attached.

## Minutes quality anomaly

Observed `minutesPlayed` range is `-3` through `120`.

Exact anomaly counts:

- **2** rows have negative minutes (`-3` and `-2`);
- **4** rows have exactly zero minutes;
- **0** rows exceed 120 minutes.

The two negative-minute rows are retained in raw evidence and must not be silently changed to zero. They should receive a source-quality diagnostic and be excluded/quarantined from any calculation whose methodology requires valid non-negative minutes unless a source-specific explanation is later proven.

This is a concrete example of why refined historical outputs are useful but still require empirical quality auditing.

## Model limitation / later critique

A later paper, `Revisiting PlayeRank`, reports methodological inconsistencies in the original PlayeRank training/evaluation process and proposes corrected feature weights. This does not make the public original score useless, but it prevents Football Intelligence from presenting the score as an objective or definitive measure of player quality.

Required provenance should therefore retain at least:

- model family: PlayeRank;
- model/artifact version: original public 2019 artifact / Figshare v1;
- underlying Wyscout Open match/player ids;
- role cluster;
- raw score scale;
- original methodology reference;
- known later methodological critique.

If a corrected/recomputed PlayeRank variant is used later, it must be a distinct model/version rather than overwriting original observations.

## Proposed Football Intelligence evidence role

If implemented after a separate adapter/metric review, the safe initial role is:

- source/provider: PlayeRank public artifact, linked to Wyscout Open ids;
- grain: `player_match`;
- evidence class: external/provider model output;
- candidate metric: `playerank_score_raw`;
- companion model field: `playerank_role_cluster`;
- source fields `minutesPlayed` and `goalScored` retained for provenance/diagnostics but not automatically promoted over existing direct Wyscout-derived observations without reconciliation.

The external score may help answer historical performance questions directly without rebuilding all input event features for every use case.

However:

- do not normalize it against API-Football, SofaScore, WhoScored, FIFA/EA or any other rating merely because they all measure 'performance';
- do not infer a defensive/offensive subdimension that PlayeRank itself does not explicitly publish;
- do not convert the player-match score to a player-season score until an aggregation methodology is separately reviewed/versioned;
- do not treat a high-level score as proof that every raw component metric exists;
- do not extend coverage beyond the observed competitions/seasons.

## V1 implication

This audit validates the user's zero-cost refined-output strategy in a concrete production-relevant case:

**For 2017/18 across the five European core leagues, Football Intelligence can recover a large body of already-computed role-aware player performance evidence for free and with clear provenance/licensing, rather than requiring every performance conclusion to be rebuilt from raw events first.**

The remaining historical problem is now narrower:

- `ARG_LPF` still needs separate free historical performance evidence;
- 2016/17 and 2018/19 through 2021/22 still need additional open/static/academic sources;
- later recent seasons can also use API-Football Free only within its observed 2022–2024 access window, subject to separate rights/product-promotion gates.

PlayeRank should therefore be retained as a high-value 2017/18 European historical model source candidate while Football Intelligence continues assembling the zero-cost multi-source V1.
