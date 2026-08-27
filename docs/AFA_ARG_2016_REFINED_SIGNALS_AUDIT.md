# AFA Argentina 2016 Refined Signals Audit

Status: **bounded lab closed — official narrative evidence GO; archived Stats Center recovery NO-GO for V1**.

This audit records the durable outcome of `lab/afa-arg-2016-refined-signals` for the short 2016 Argentine Primera División tournament.

## Question

Can AFA's 2016 `#NúmerosDePrimera` material provide legally and semantically defensible player-performance evidence for Football Intelligence, and can the extinct interactive Stats Center embedded by those articles be recovered from a public archive with enough density to act as a broader player-stat source?

The spike follows the zero-cost-first sourcing strategy in `docs/V1_ZERO_COST_HISTORICAL_DATA_STRATEGY.md` and does not write PostgreSQL or create production identity crosswalks.

## Source role

AFA's surviving article text is treated as **official refined partial evidence**.

It is not a player-season backbone and must not be represented as complete coverage. Values copied from the prose remain source-scoped and metric-scoped, with article URL/date, competition context and phase/scope retained.

The extinct embedded tables are a separate acquisition route. Their historical URLs preserve useful semantics, but the table contents are not available at the live URLs today.

## Surviving AFA articles

The audited series includes:

- goals: `https://www.afa.com.ar/Sitio/posts/numerosdeprimera-sand-el-artillero`
- recoveries: `https://www.afa.com.ar/Sitio/posts/numerosdeprimera-recuperaciones`
- fouls received: `https://www.afa.com.ar/Sitio/posts/numerosdeprimera-faltas-recibidas`
- assists: `https://www.afa.com.ar/es/posts/numerosdeprimera-malcorra-el-asistidor`
- shots / finishing: `https://www.afa.com.ar/a/posts/numerosdeprimera-tiros-al-arco`
- passes: `https://www.afa.com.ar/es/posts/numerosdeprimera-pases`

Representative values explicitly present in the surviving prose include:

- passes: Gerónimo Poblete `642` attempted / `583` correct; Pablo Ledesma `632` attempted / `574` correct; Iván Marcone `94%` on `416` passes;
- recoveries: Santiago Ascacíbar `62`, Gerónimo Poblete `61`, Jonathan Bottinelli `59`; the article also publishes per-match examples with appearances such as Juan Mercier `47 / 9 = 5.2` and Poblete `61 / 14 = 4.4`;
- assists: Ignacio Malcorra `8`, Emiliano Rigoni `6`;
- fouls received: Fernando Zuqui `55`, Ezequiel Cerutti `54`; the article also contains player appearance denominators for some per-match examples;
- finishing: Ramón Ábila `11` goals from `39` shots as published by the article; Maximiliano Romero `3` goals from `6` shots on target (`50%`);
- goals: José Sand `14`, with published breakdowns by half, time window and goal type.

These examples are evidence anchors, not an exhaustive extracted dataset.

## Competition phase / scope

Scope must be preserved at article level and must not be silently promoted to a full-season claim.

The passes article explicitly describes the `16 fechas` of the tournament. The shots article explicitly says `16 fechas de la fase regular`. Therefore values whose source text establishes that scope should be stored with the corresponding regular-phase context rather than labelled as an undifferentiated full season.

If a particular article does not explicitly establish the same scope for a value, preserve the article wording/context and do not infer a broader scope merely because it belongs to the same editorial series.

## Legacy Stats Center semantics

Several AFA articles still contain the historical iframe URLs of the old per-player Stats Center:

```text
channel=deportes.futbol.primeraa.statsCenterPerPlayer
module=statsCenterPerPlayer
```

Observed `tableType` values:

- `passes`
- `correctPasses`
- `passesAccuracy`
- `stealing`
- `stealingsPM`
- `foulsReceived`
- `foulsReceivedPJ`
- `goalAssistances`

These URLs are useful provenance because they preserve the original table semantics. They do **not** prove that the historical table rows remain retrievable.

## Live-url result

The legacy iframe requests currently return HTTP 200 only after redirecting away from the historical module to:

```text
https://www.afa.com.ar/es/
```

The returned page is the modern AFA site/homepage, not the historical player table. No player rows are recoverable from the live module URL.

Original embed probe:

- workflow run: `33004699134`
- artifact: `afa-arg-2016-refined-signal-embed-probe`
- artifact id: `9620032316`
- digest: `sha256:57326b8518125344db7e7c6075b9aa3dde8d1c26e1822b306ab89056c73ff39f`

## Bounded archive test

The archive hypothesis was intentionally bounded: first attempt to recover real player rows for the old Stats Center / passing data, and only broaden if an actual archived table or player-stat payload appears.

Public Wayback/CDX probes tested the legacy module/data family and candidate player-stat JSON paths. Results included:

- `.../htmlCenter/data/deportes/futbol/primeraa/statsCenter/*`: HTTP 200 from CDX with `0` archived records returned for the bounded 2016 query;
- candidate `playersStats.json` / `playersStatsFull.json` paths: successful CDX responses returned `0` snapshots for the tested variants; one query timed out;
- broader legacy-prefix searches produced no useful archived record and several timeouts.

Player-stat JSON archive probe:

- workflow run: `33006904944`
- artifact: `afa-arg-2016-wayback-player-stats`
- artifact id: `9620958570`
- digest: `sha256:c14640def27c37fe589a3145e4d409442a52fd282b38f01df322e09c3858628a`
- `unique_2016_snapshots = 0`

Final bounded prefix probe:

- workflow run: `33007189285`
- artifact: `afa-arg-2016-wayback-prefix-search`
- artifact id: `9621139153`
- digest: `sha256:aec9e0f6f1a7df0c2f1bae37fb7959470ef1d119cfac1d455a8a614a8d7db59d`
- useful archived records: `0`

Timeouts are not proof that no snapshot can exist anywhere. They are sufficient to fail this spike's GO criterion because no archived payload containing actual player rows was observed after the bounded direct and prefix probes.

## Decision

### GO — official narrative refined evidence

Retain only values explicitly published in the surviving AFA article text as official, source-scoped refined evidence.

For every retained value preserve at least:

- AFA as source;
- article URL and publication date;
- player literal / resolved identity provenance;
- metric name and published value;
- competition and known phase/scope;
- whether the value is direct prose evidence or a ratio reproduced by AFA;
- acquisition timestamp / evidence reference;
- missingness as unknown rather than zero for players not mentioned.

### NO-GO — archived Stats Center as V1 backbone

Do not spend more V1 engineering time trying to reconstruct the extinct AFA Stats Center through increasingly broad Wayback searches, alternate headers, proxies or bypass techniques.

Re-open only if a concrete public snapshot/static asset is independently discovered that contains real player rows with recoverable provenance and scope.

## Important limitations

- The prose articles publish leaders/examples, not a complete player population.
- `tableType` names establish semantics of extinct embeds, not recovered values.
- A player absent from an article is **missing/unknown**, never zero.
- Do not call regular-phase values a complete season without explicit evidence.
- Do not infer appearances/minutes for the broader roster from ratios or leader articles.
- DataFactory may have powered the historical statistics, but this audit does not establish a reusable DataFactory dataset or licence for Football Intelligence.

## Next action

The largest remaining Argentina 2016 gap is still **player appearances and minutes**. The next bounded spike should target a source that can provide match/player context or season appearance denominators without weakening identity, provenance or rights guarantees.

AFA `#NúmerosDePrimera` may contribute isolated appearance counts where they are explicitly printed in prose, but those isolated counts are not sufficient as the Argentina 2016 appearance/minutes backbone.
