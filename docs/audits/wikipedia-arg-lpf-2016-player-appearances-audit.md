# Wikipedia ARG_LPF 2016 individual-player appearance audit

Status: **bounded lab closed — partial corroborative evidence only; NO-GO as automatic appearance/minutes backbone**.

## Decision question

Can individual Spanish Wikipedia player pages, linked from the already-audited historical `ARG_LPF 2016` roster snapshot, provide a free, sufficiently dense and semantically stable player-appearance layer for Football Intelligence without fuzzy identity matching?

This audit is intentionally limited to the short Argentine Primera División 2016 tournament. It does not create production identities, `PlayerCrosswalk` rows or PostgreSQL records.

## Starting population and identity rule

The prior historical-roster audit established:

- `30` Primera División clubs;
- `903` player-club roster slots;
- `891` literal unique names;
- historical club-page revisions at or before `2016-02-09T00:00:00Z`;
- roster membership as a snapshot only, not an appearance claim.

For this follow-up, identity was deliberately stricter than name matching:

1. re-run the validated historical roster parser;
2. preserve the player hyperlink target embedded in the historical roster row;
3. follow only that Wikipedia target;
4. never search or fuzzy-link an unlinked player name automatically.

The validated link reconstruction returned:

- `903` roster slots;
- `878` linked slots;
- `871` unique player targets;
- `799` roster slots whose linked player page resolved with current wikitext;
- `79` linked slots whose target is currently missing;
- `25` unlinked roster slots.

The validated roster-link/current-page probe was:

- workflow run: `33078390845`;
- artifact: `wikipedia-arg-2016-player-appearance-coverage-v2-33078390845`;
- artifact id: `9648889723`;
- digest: `sha256:81e9e5adf9cfa1a20006c953ce71960f6f034e9d9e351d8fe36e6e805b2e93a1`.

## Why a simple `2016` parser is unsafe

Current player pages use several incompatible career-stat table shapes. Some rows explicitly link the competition:

```text
[[Campeonato de Primera División 2016 (Argentina)|2016]]
```

Others contain only a plain calendar/season cell such as:

```text
|2016
```

A plain `2016` cell is not sufficient to establish the exact Football Intelligence competition-phase semantics. Depending on the page, a calendar-year row can coexist with other league/cup blocks, club changes, finals or differently scoped season conventions.

Therefore the final population metric counts only rows with an **exact link to `Campeonato de Primera División 2016`**, a nearby matching roster-club context, and one extractable first league-stat value. Plain-year rows remain a separate ambiguous class and are not promoted into the final coverage figure.

## Final current-page population measurement

Final exact-competition probe:

- workflow run: `33079793609`;
- artifact: `wikipedia-arg-2016-strict-exact-final-33079793609`;
- artifact id: `9649501428`;
- digest: `sha256:8c4c4e508a9e3786a43057ac3b9ca8c5a49f92764431a3c3ef810947b0d9d60f`.

Across the `903` historical roster slots:

| Classification | Slots | Share of all roster slots |
| --- | ---: | ---: |
| exact-competition row with one machine-extractable value | `272` | `30.12%` |
| exact-competition row with multiple candidate values | `2` | `0.22%` |
| no accepted exact-competition row | `629` | `69.66%` |

Among the `799` slots whose linked current player page resolved, the exact single-value candidate rate is `34.04%`.

This is **parseable candidate coverage**, not a claim that all `272` values are authoritative or correct.

Coverage is also uneven by club. Representative exact-single-value counts include:

- Unión de Santa Fe: `29`;
- River Plate: `14`;
- Boca Juniors: `13`;
- Racing Club: `13`;
- Quilmes: `13`;
- San Lorenzo: `12`;
- Colón: `11`;
- Tigre: `11` plus one ambiguous row;
- Defensa y Justicia: `5`;
- Independiente: `5`;
- San Martín de San Juan: `5`;
- Temperley: `5`.

A source with roughly `30%` machine-extractable population coverage cannot act as the Argentina 2016 appearance backbone by itself.

## Parser regression anchors

The final parser reproduced three known current-page structures:

- Gerónimo Poblete / Colón: current Wikipedia exact-linked value `15`;
- Adrián Cubas / Boca Juniors: exact-linked value `6`;
- Agustín Orión / Boca Juniors: exact-linked value `12`.

These are parser regression checks, not Football Intelligence truth labels.

Two current pages returned more than one candidate under the bounded positional context rule and therefore stayed ambiguous rather than being silently resolved:

- Gino Peruzzi / Boca Juniors;
- José Erik Correa / Tigre.

## Historical-revision test

Because current Wikipedia pages can change, a second bounded test asked whether end-of-tournament historical revisions would improve stability or density.

The sample contained `63` players:

- two deterministic linked players per club from the earlier unresolved/strict-missing pool;
- plus Iván Marcone, Gerónimo Poblete and José Sand as anchors.

Historical cutoff:

`2016-08-15T23:59:59Z`

Run / artifact:

- workflow run: `33078907914`;
- artifact: `wikipedia-arg-2016-player-revision-sample-33078907914`;
- artifact id: `9649123352`;
- digest: `sha256:eb91a586fc906970afba360206c10ae74767e0c2f2815cb25c102347db5178c2`.

Observed sample result:

- historical player pages resolved: `55 / 63`;
- historical explicit competition rows: `8`;
- current explicit competition rows in the same sample: `19`;
- historical plain-2016 rows: `2`;
- current plain-2016 rows: `23`;
- explicit historical/current conflicts observed: `2`.

Historical revisions therefore did **not** improve coverage in this bounded sample and introduced an additional revision-selection/stability problem.

## Authoritative conflict: Gerónimo Poblete

This is the decisive semantic warning.

For Gerónimo Poblete / Colón:

- current Spanish Wikipedia revision `175021574` (`2026-08-25T10:43:42Z`) produces an exact-linked 2016 league value of `15`;
- sampled historical Spanish Wikipedia revision `92771812` (`2016-08-06`) produced `12`;
- AFA's surviving official `#NúmerosDePrimera` recoveries article explicitly publishes `61 / 14 = 4.4`, establishing an appearance denominator of **14** in that article's tournament context.

Therefore the same player can yield:

```text
Wikipedia historical revision: 12
Wikipedia current revision:    15
AFA official prose:             14
```

Football Intelligence must not choose one of these merely because it is easier to parse.

This conflict also demonstrates why a Wikipedia career-stat row must remain source/revision scoped and why `current page` is not equivalent to `historically correct tournament truth`.

## Other observed representation drift

The historical-revision sample also showed representation/value drift such as:

- César Pereyra / Belgrano: historical exact value `6`, current exact value `12`;
- Alan Ruiz: historical exact row `9`, while the current page expresses the relevant value through a plain `2016` row;
- Alejandro Romero Gamarra: historical exact `16`, current representation as a plain `2016` row;
- Augusto Batalla: historical exact `4`, no equivalent current accepted row in the bounded parser;
- Bautista Merlini: historical exact `0`, current plain `2016` value `1`.

These examples are not automatically adjudicated here because the purpose of the spike is source viability, not player-by-player correction.

## Decision

### Automatic Argentina 2016 appearance backbone

**NO-GO.**

Reasons:

1. exact, single-value machine-extractable coverage is only `272 / 903 = 30.12%` of the historical roster slots;
2. coverage is highly uneven across clubs;
3. many pages represent 2016 only through semantically weaker plain-year rows;
4. current and historical Wikipedia revisions can disagree;
5. a direct conflict exists with stronger official AFA evidence for Gerónimo Poblete;
6. no complete minutes layer was found;
7. missing Wikipedia evidence must remain missing, not zero.

Do not invest V1 engineering effort in turning heterogeneous Wikipedia career tables into a universal Argentina 2016 appearance parser.

### Partial supporting evidence

**CONDITIONAL GO as source-scoped corroboration / fallback evidence.**

An exact competition-linked row may still be useful for an individual player when:

- identity comes from a provenance-preserving link or another accepted identity bridge;
- the exact page revision ID and timestamp are recorded;
- the competition/phase semantics are explicit;
- the value is kept attributed to Wikipedia rather than silently converted into an objective canonical truth;
- stronger official/provider evidence is checked first;
- conflicts remain explicit and unresolved until adjudicated.

Wikipedia should not override official AFA evidence merely because the Wikipedia row is structurally easier to parse.

## Provenance and licensing

The existing roster audit treats Spanish Wikipedia historical revisions as CC BY-SA material and requires page/revision attribution. Any retained player-page evidence must preserve at least:

- source language/project;
- requested and resolved page title;
- page ID;
- revision ID;
- revision timestamp;
- acquisition timestamp;
- exact competition label/link;
- roster-club context;
- extracted value;
- parser/model version if automated;
- conflict state and stronger-source references when applicable.

Do not copy whole Wikipedia pages into the canonical repository. Retain only the minimum audit metadata/distillation required by the project storage policy.

## Non-claims

- `272` means parseable exact-row candidates, **not 272 independently verified appearance totals**.
- A missing row is unknown, never zero appearances.
- A plain calendar-year `2016` row is not automatically the short 2016 Primera competition.
- No minutes coverage was established.
- No `PlayerCrosswalk`, PostgreSQL record or production entity was created.
- This audit does not generalize automatically to other leagues or seasons.

## Next action

The Argentina February–May 2016 appearance/minutes gap remains open.

Do not spend more V1 time broadening Wikipedia parsers for this tournament. Continue with an independent source whose native data model is match/player or competition-season scoped and whose usage rights can be defended. Wikipedia exact-linked rows can remain available as partial corroboration when a stronger source is missing, but they are not the backbone.