# API-Football free coverage probe gate

Status: implementation and simulated-response validation PASS; no live API request executed yet.

## Why this exists

Football Intelligence needs to know whether API-Football can cheaply provide a broad player-season layer across the six core competitions before any paid historical experiment is justified.

The cheapest useful first question is not "download all players". It is:

> What league-season coverage does one free authenticated `/leagues` catalogue response expose for the six targets, and which provider coverage flags are present for each season?

The provider itself recommends checking `/leagues` coverage before building data features. The free dashboard plan currently provides 100 requests/day and is limited in available data/seasons, so this first gate is deliberately designed to consume exactly **one request**.

## Implemented probe

CLI:

`football-intelligence-probe-api-football-free-coverage`

Implementation:

`analytics/src/football_intelligence/jobs/probe_api_football_free_coverage.py`

The probe:

1. reads the API key only from environment variable `API_FOOTBALL_KEY`;
2. performs exactly one `GET https://v3.football.api-sports.io/leagues` request;
3. never accepts a key on the command line;
4. resolves the six targets by exact country + league name rather than trusting copied provider IDs;
5. preserves each provider league ID returned by the API;
6. records every returned season plus `players`, fixture-player-statistics, fixture-statistics, lineups and events coverage flags;
7. preserves missing coverage fields as `null` rather than converting them to `false` or zero;
8. freezes both the exact raw `leagues.json` bytes and a deterministic `coverage.json` summary;
9. records SHA-256 and byte size for both files through the generic static-snapshot manifest;
10. refuses to overwrite an existing snapshot directory's files;
11. does not call `/players`, fixtures or any other endpoint;
12. does not write PostgreSQL or create canonical IDs.

Target resolution:

- `ARG_LPF` -> Argentina / Liga Profesional Argentina
- `ENG_PL` -> England / Premier League
- `ESP_LL` -> Spain / La Liga
- `ITA_SA` -> Italy / Serie A
- `GER_BL1` -> Germany / Bundesliga
- `FRA_L1` -> France / Ligue 1

## Validation

Quality run `32958672173` (#696), commit `9f565350398a3d1bcca6471e3ce8359b57376839`:

- Analytics: PASS
  - Ruff lint: PASS
  - Ruff format: PASS
  - mypy strict: PASS
  - pytest: PASS
- Database: PASS
- Web: PASS

Tests use provider-shaped simulated responses and verify, among other cases:

- exact six-competition resolution;
- country disambiguation for duplicate league names;
- provider API errors fail closed;
- missing target competition fails closed;
- missing coverage fields remain `None`;
- one `collect_probe()` execution invokes the network fetch exactly once;
- the frozen raw bytes match their recorded SHA-256;
- the generic static-snapshot validator accepts the generated artifact;
- existing files are never overwritten.

No real API-Football quota was consumed by these tests.

## What a future live PASS would mean

A live PASS would prove only:

- the free account can call `/leagues`;
- the six target competitions resolve uniquely in the authenticated catalogue;
- the exact provider league IDs returned at that acquisition time;
- the set of season objects returned for each target;
- the provider's coverage flags attached to those seasons;
- frozen provenance/integrity for that one catalogue response.

It would **not** prove:

- that `/players` is actually accessible for every catalogue season on the free account;
- that every player-season is complete;
- that player statistics have useful non-null depth;
- that player IDs/team context are sufficient for canonical identity;
- that `false` or `null` fields should be interpreted as zero;
- that API-Football grants publication rights for the underlying competition data;
- that API-Football is approved as a Football Intelligence product source.

The provider's current terms explicitly state that it does not itself grant the licence/permission required to publish supplied data, so rights/compliance remains a separate gate even if technical coverage is excellent.

## Stage 2 only after the one-call live gate

If and only if the live catalogue evidence is useful, Stage 2 should spend a small bounded number of the remaining free daily requests:

1. select one recent ARG_LPF season and one European season actually returned by the free catalogue;
2. call only page 1 of `/players?league=<id>&season=<year>` for each;
3. inspect real schema, pagination, team blocks, player IDs, null/zero semantics and statistic depth;
4. do not paginate a complete league until those two page-1 probes pass;
5. compare a complete test season against an independent official lower bound before treating it as roster/performance evidence.

A future full 6 x 10 import is not authorized by this probe and must remain blocked until historical access and rights are separately proven.

## Budget conclusion

Current cost of this next gate: **USD 0**, one request from a 100-request/day free quota.

No paid API-Football plan is justified before this evidence exists.
