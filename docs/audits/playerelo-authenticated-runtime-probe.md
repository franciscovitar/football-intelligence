# PlayerElo authenticated runtime probe

Status: authenticated Free-tier technical spike complete; product approval still blocked on rights and historical scoping.

## Decision question

Can PlayerElo provide real zero-cost historical player-rating depth back through Football Intelligence's 2016-2021 gap, with stable provider IDs and predictable quota behaviour?

## Environment

- Provider: PlayerElo
- Base URL: `https://data-api.playerelo.football`
- Authentication: `Authorization: Bearer` using GitHub Actions secret `PLAYERELO_API_KEY`
- Tier observed: `free`
- Monthly cap observed: `500`
- Per-minute limit observed: `10`
- No API key bytes were written to the retained artifact directories.

## Primary six-player runtime probe

GitHub Actions run: `32981798275`

Artifact:

- ID: `9611735065`
- name: `playerelo-six-history-probe-32981798275`
- ZIP digest reported by GitHub Actions: `sha256:9ac63f2eb1a1f64c43f8dca84ec01503143ec4c5ed852cb32c916e56228ac8fa`

The run made exactly:

- one `GET /v1/usage` call;
- six `GET /v1/players/{id}/history` calls.

All six history requests returned HTTP success and non-empty JSON arrays.

| Provider player ID | Representative | History rows | Earliest observed date | Latest observed date |
| ---: | --- | ---: | --- | --- |
| `9933` | Miguel Borja | 352 | 2016-01-30 | 2026-03-18 |
| `5` | Manuel Akanji | 443 | 2015-11-05 | 2026-08-22 |
| `278` | Kylian Mbappe | 536 | 2015-12-02 | 2026-08-22 |
| `217` | Lautaro Martinez | 467 | 2016-08-27 | 2026-08-22 |
| `184` | Harry Kane | 628 | 2013-09-24 | 2026-08-22 |
| `153` | Ousmane Dembele | 424 | 2015-11-06 | 2026-08-23 |

This proves that the history endpoint is not restricted to recent seasons and that real career timelines reach well into the 2016-2021 target window.

The original current-league labels used to choose the six representatives must not be interpreted as historical league scope. A better historical reading of the same evidence is:

- Harry Kane supplies real target-window history while he was playing in the Premier League;
- Ousmane Dembele supplies target-window history while he was playing in La Liga from 2017 onward;
- Lautaro Martinez supplies target-window history while he was playing in Serie A from 2018 onward;
- Manuel Akanji supplies target-window history while he was playing in the Bundesliga from 2018 onward;
- Kylian Mbappe supplies target-window history while he was playing in Ligue 1;
- a separate Argentina player probe was required because Miguel Borja did not play Liga Profesional Argentina during 2016-2021.

## Observed history schema

The most important negative finding is that every retained `GET /v1/players/{id}/history` row had only:

- `date`;
- `elo`;
- `ear`.

No observed row contained:

- fixture ID;
- club/team ID;
- competition/league ID;
- opponent;
- minutes;
- match result;
- position;
- season label.

Therefore the public description `match-by-match Elo & EAR history` is technically consistent with a rating point after matches, but the current response does **not** expose enough match context to scope a row independently to one Football Intelligence competition-season.

This is a material product/data limitation. PlayerElo can currently support a provider-scoped **global player-strength time series**, but it cannot by itself prove `player X had rating Y in league L / season S` without an additional historical match/team/competition join.

`EAR` is nullable. Real retained rows include both numeric and `null` EAR values. Missing EAR must remain missing; it must not be converted to zero.

## Argentina target-window probe

The first exact-name search for `Franco Armani` returned no exact full-name match and was rejected rather than linked fuzzily.

A second bounded surname search returned one provider record:

- provider ID: `2463`;
- provider display name: `F. Armani`;
- position: `Goalkeeper`.

Search run: `32982313182`

Artifact:

- ID: `9611933159`
- ZIP digest: `sha256:691f2e5f02ce8c6e09dfba4cf7ad80727d3bbd1beef04986192c2e36cce614ec`

The same provider ID was then queried directly; no name-only canonical identity was created.

Argentina history run: `32982443084`

Artifact:

- ID: `9611984926`
- name: `playerelo-arg-history-quota-32982443084`
- ZIP digest: `sha256:f1ef6fdbaca399930882f87fbd1c9288844c14eb5a56d2e8af46a66ddac4b105`

Observed result for provider player ID `2463`:

- 386 history rows;
- earliest date `2016-02-07`;
- latest date `2026-08-23`;
- history row keys again limited to `date`, `elo`, `ear`.

This supplies real historical depth for an Argentina-based representative in the target era, but it still does not independently label which rows are Liga Profesional vs cups/international matches.

## Quota behaviour

The Free-tier `/v1/usage` response observed:

- `tier = free`;
- `monthly_cap = 500`;
- `per_minute_limit = 10`;
- `/v1/usage` itself did not increment usage in the bounded checks.

The surname search increased `used_this_month` by exactly 1.

The direct Armani history request increased `used_this_month` by exactly 1.

This matches the documented request-counting model for the calls observed.

## What this proves

Observed / supported:

- Free-tier authentication works with Bearer tokens.
- Known API-Football-aligned player IDs resolve directly for the six initial representatives.
- Player history has genuine depth back to at least 2016 for all relevant sampled careers, and earlier for several.
- Argentina target-era depth also exists for provider player ID `2463`.
- Elo is numeric in real history rows.
- EAR has explicit nullable semantics.
- Free-tier quota accounting behaved predictably in the calls measured.
- The API key was masked in Actions logs and absent from retained artifact directories.

## What this does not prove

Not validated:

- league-wide completeness for any historical season;
- exact six-league player counts by season;
- that every historical rostered player has a rating timeline;
- a direct competition-season label on each history row;
- historical club or fixture identity from the history endpoint itself;
- a league-wide bulk backfill route;
- public/commercial display rights after cancellation;
- whether Pro vs Business is the correct licence for Football Intelligence;
- post-cancellation retention rights;
- attribution requirements.

## Decision

### Global historical model signal

**GO for further evaluation.**

PlayerElo is genuinely useful as a low-cost provider-scoped historical `Elo` / `EAR` time series. It is substantially more than a current-only API.

### Six-league historical backbone

**NO-GO in the current response shape.**

The history endpoint's lack of fixture/team/league context prevents Football Intelligence from responsibly treating each row as league-season evidence without another source/join.

### Public product source

**INCONCLUSIVE / blocked on rights.**

No PlayerElo data should be promoted into the public product until storage, retention, commercial-use tier and attribution questions are answered explicitly.

## Next

Ask PlayerElo whether an enriched history response or another endpoint can return historical fixture ID, team/club ID and league/competition ID for each rating update, and resolve the prepared storage/licensing questions before considering any paid plan.
