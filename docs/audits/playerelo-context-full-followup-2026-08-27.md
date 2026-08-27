# PlayerElo context-full follow-up — 2026-08-27

Status: **provider clarification verified in runtime; match context GO where covered; Argentina February–May 2016 NO-GO; product rights still unresolved**.

This document supersedes the earlier conclusion that PlayerElo history can only be used as a context-free global rating timeline. That conclusion remains true for the previously tested default history response, but PlayerElo support disclosed an enriched `context=full` route on 2026-08-27 and Football Intelligence verified it with the existing Free-tier credential.

No production database writes, canonical identity crosswalks, paid plan changes or public-product integration were performed.

## Provider clarification

Direct PlayerElo support confirmed on 2026-08-27 that enriched player history is available by adding `context=full` to the player-history request.

The provider said the enriched form can include match context such as:

- fixture ID;
- league ID;
- team;
- opponent;
- home/away context;
- minutes played;
- match outcome;
- Elo and Elo change.

Support also stated:

- historical coverage begins approximately around 2015 for major leagues, explicitly including Argentina Liga Profesional, Premier League, La Liga, Serie A, Bundesliga and Ligue 1;
- player and fixture IDs are stable and compatible with API-Football IDs;
- there is no public bulk export at present;
- custom dumps/partnerships can be discussed, while ordinary access is through the API subject to plan limits;
- the standard API is designed for live querying;
- long-term storage, reuse, cancellation/retention and commercial terms are not yet fully standardized and should be clarified for the intended product use.

Therefore the support response removes the earlier **technical schema blocker**, but it does **not** remove the rights/retention blocker.

## Runtime verification: enriched schema

Football Intelligence then called the existing authenticated endpoint in the form:

```text
GET /v1/players/{player_id}/history?context=full
```

The actual retained runtime rows contained:

- `date`;
- `fixture_id`;
- `league_id`;
- `team`;
- `opponent`;
- `is_home`;
- `minutes`;
- `elo`;
- `elo_change`;
- `ear`.

This proves that the enriched history is materially more useful than the previously tested default response.

Important schema note: the provider's support example described fields such as `minutes_played` and richer nested team/opponent objects, while the real responses observed in these probes used `minutes`, `is_home`, and string team/opponent values. Football Intelligence must map the **runtime schema actually observed**, not silently assume the example shape.

## Bounded Argentina 2016 test

The immediate question was whether enriched history could fill Football Intelligence's largest remaining Argentina 2016 gap: player appearances/minutes for the short tournament approximately `2016-02-05` through `2016-05-29`.

Two players independently anchored by AFA `#NúmerosDePrimera` material were used. Provider candidates were used only for the spike; no canonical `PlayerCrosswalk` was created.

### Iván Marcone

Provider search for `Marcone` returned one surname candidate:

- provider player ID: `2474`;
- provider display name: `I. Marcone`;
- provider position: midfielder.

The enriched history returned:

- `328` career rows;
- full match-context keys listed above;
- real Argentina `league_id = 128` rows in other periods;
- **0 rows** of any league between `2016-02-05` and `2016-05-29`;
- nearest retained row before the tournament window: `2015-11-07`;
- nearest retained row after the tournament window: `2016-08-28`.

This is not a league-ID filtering mistake: there are zero PlayerElo history rows of any competition inside the target window for this provider player.

First probe:

- workflow run: `33075449586`;
- artifact: `playerelo-arg-2016-context-full-33075449586`;
- artifact ID: `9647636693`;
- digest: `sha256:061f7b6ec87c92ec64393508eb9ce3cd34dd5e92bb89bfd279e2bd8f4d9d3b29`;
- counted Free-tier calls during the run: `3` (two bounded searches plus one history request; `/v1/usage` remained uncounted as previously observed).

### Gerónimo Poblete

The first surname search intentionally refused to auto-select because PlayerElo returned two provider candidates:

- `I. Poblete` — ID `11801`;
- `G. Poblete` — ID `6623`.

AFA independently names **Gerónimo Poblete**, so a second bounded probe inspected provider ID `6623` and proceeded only after the provider detail still identified it as `G. Poblete`. This remains a temporary provider-candidate selection, not a canonical Football Intelligence identity link.

The enriched history for provider ID `6623` returned:

- `239` career rows;
- the same match-context schema;
- **0 rows** of any league between `2016-02-05` and `2016-05-29`;
- nearest retained row before the tournament window: `2015-12-05`;
- nearest retained row after the tournament window: `2016-08-29`.

AFA's narrative evidence says Poblete had `61` recoveries in `14` appearances in its 2016 tournament analysis. PlayerElo cannot reproduce or validate that denominator because its timeline contains no rows in the relevant tournament window.

Second probe:

- workflow run: `33075609788`;
- artifact: `playerelo-poblete-2016-context-full-33075609788`;
- artifact ID: `9647705822`;
- digest: `sha256:33d8cea4618791ea918ac9d5520715f1e94d062d1b5aed15c542fe672970eaee`;
- counted Free-tier calls during the run: `2` (player detail plus enriched history).

### Club-history fallback: Lanús

A final bounded fallback tested whether club history might preserve the missing fixtures even though the player timelines do not.

PlayerElo club search returned one exact normalized candidate:

- provider club ID: `446`;
- provider club name: `Lanus`.

`GET /v1/clubs/446/history?context=full` returned:

- `299` rows;
- row keys only `date` and `team_elo`;
- **0 rows** between `2016-02-05` and `2016-05-29`;
- no row before the tournament window;
- first row after the window: `2019-08-30`.

So the club-history route cannot supply hidden fixture IDs for the short 2016 tournament and does not provide a path to reconstruct player minutes from PlayerElo fixture context.

Club probe:

- workflow run: `33075905849`;
- artifact: `playerelo-lanus-2016-club-history-33075905849`;
- artifact ID: `9647827505`;
- digest: `sha256:9d9b5fb98889195797d3064514ed16fdcbee82dff06e46983a6fc6979a9fd72f`;
- counted Free-tier calls during the run: `2` (club search plus club history).

## Decision

### Enriched PlayerElo history as match-context evidence

**TECHNICAL GO where rows exist.**

`context=full` can supply fixture-scoped model evidence plus observed match context and minutes. This materially upgrades PlayerElo's technical usefulness because league/team/opponent/minutes can be preserved alongside provider-scoped Elo/EAR.

The context fields are not themselves permission to treat Elo/EAR as direct objective facts. Elo/EAR remain external model-scoped outputs.

### Argentina short tournament 2016 appearances/minutes

**NO-GO.**

The two independently anchored player probes both show a clear gap across the February–May 2016 tournament despite PlayerElo history existing both before and after the window. The Lanús club-history fallback also contains no target-window rows and only begins in 2019. The result is strong enough to stop spending Free-tier quota on more PlayerElo routes for this tournament unless new provider evidence contradicts it.

Do not use PlayerElo to infer zero appearances or zero minutes for Argentina short 2016. The evidence is **missing because the provider timeline is absent**, not a sporting zero.

### Six-league historical use outside this gap

**PROMISING / season-by-season audit required.**

The enriched endpoint removes the old schema limitation, but provider coverage must still be measured by competition-season before treating it as a historical layer. The provider's statement that coverage starts around 2015 does not imply every competition phase or season is complete.

### Public product / retained backfill

**BLOCKED on explicit rights and retention terms.**

The provider explicitly said long-term storage/reuse terms are not fully standardized. Football Intelligence must obtain a clear answer for its intended use before retaining a large backfill or publishing PlayerElo-derived evidence. No paid plan should be purchased for this purpose without explicit user approval.

## Next action

For **Argentina February–May 2016**, continue searching for a different free appearance/minutes source. PlayerElo should not receive more quota for that specific tournament unless a new source/provider statement shows that the missing interval can be recovered.

For PlayerElo more generally, a later bounded coverage-density audit can test selected competition-seasons where `context=full` is likely to add value, but only after the rights/storage question is clarified enough to justify acquisition effort.
