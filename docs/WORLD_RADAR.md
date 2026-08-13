# World Radar V1

Block 12 adds an explicit offensive/creative radar for standout production
outside the six core leagues, without synchronizing entire leagues and
without spending uncontrolled provider quota.

Model version: `world-radar-v1.0`.

## What World Radar is

World Radar V1 is a **radar ofensivo/creativo**. It detects players with
standout goal-scoring or creative production inside a small set of external
competitions, using `GET /players/topscorers` and `GET /players/topassists`.

## What World Radar is not

It does **not** claim to cover:

- central/purely-defensive defenders;
- goalkeepers;
- full scouting;
- league quality or strength;
- market value;
- transfer potential.

Scores are **competition-relative percentiles**. A 90 in one competition is
never presented as equivalent to a 90 in another; V1 has no cross-league
strength coefficient.

## Competitions

Competitions are configured by **name + country**, not by provider id, in
[`config/world_radar_competitions.json`](../config/world_radar_competitions.json).
V1 ships with:

- Eredivisie — Netherlands (`NED_ED`);
- Primeira Liga — Portugal (`POR_PL`);
- Serie A — Brazil (`BRA_A`);
- Major League Soccer — USA (`USA_MLS`).

The config schema is validated strictly: only `code`/`name`/`country` keys are
allowed, codes must be unique and uppercase, and no URLs or endpoints are
configurable. These codes are namespaced separately from the six core league
codes and are never merged with them.

Each competition's provider league id is resolved live via `GET /leagues`
using `name` + `country` + `season`. A run only proceeds for a competition
when exactly one candidate matches; zero or multiple candidates is reported as
an unresolved competition for that run, not guessed.

## Request economics

Per competition: 1 `/leagues` request + 1 `/players/topscorers` request +
1 `/players/topassists` request = 3 logical requests.

With the four shipped competitions: **12 logical requests** per run.

The CLI (`football-intelligence-world-radar`) takes `--request-budget`
(default 12, hard-capped at 60) and computes
`planned_requests = competitions * 3` **before any network call**. If
`planned_requests > request_budget`, the run fails immediately with no
provider request made.

World Radar deliberately avoids:

- pagination (each feed already returns a top-20 list);
- full squad fetches;
- fixture backfill;
- aggressive/unbounded retries (the shared provider client's existing
  bounded retry policy applies, nothing more).

The report records planned vs actual requests, per-competition status, and
the provider's remaining-quota header when available.

## Normalization

`topscorers` and `topassists` responses are merged by `provider_player_id`
so a player present in both feeds is processed once. Missing fields (a stat
the provider omitted) stay missing — they are never coerced to zero.

Per-90 metrics (`goals_per90`, `assists_per90`, `shots_on_target_per90`,
`key_passes_per90`, `successful_dribbles_per90`) are only computed when
minutes played is greater than zero.

## Score

Two deterministic, versioned weight profiles, each summing to 1:

- **Attacker**: goals-weighted, with shots on target, assists, key passes,
  dribbles;
- **Midfielder**: assists/key-passes-weighted, with goals, dribbles, shots on
  target.

A player's raw position text selects the profile (any position containing
"mid" is scored as a midfielder; everything else uses the attacker profile —
V1 does not build separate defender/goalkeeper profiles, since this radar is
offensive/creative by design).

Each metric contributes its **percentile rank within that competition's
eligible candidate pool** (minutes > 0), weighted and renormalized over
whichever metrics are actually available for that player.

Confidence combines minutes played (capped at 1200), appearances (capped at
15), and presence in one vs both feeds — 90 minutes never produces the same
confidence as 1200.

Reasons are a small deterministic vocabulary (`top_scorer_feed`,
`top_assist_feed`, `elite_goals_per90`, `elite_creation_per90`), never
LLM-generated text.

## Persistence

`analytics.world_radar_snapshots` stores provider identity, competition,
season, raw counts, per-90 metrics, score, confidence, reasons, and source
feeds.

The primary key is `(provider_code, provider_player_id, competition_code,
season_label, model_version)`.

World Radar candidates are **external to the core league graph**: this table
never creates or fuzzy-links `football.players`/`football.teams` rows. There
is no automatic identity matching against core players.

Raw provider payloads are stored through the existing `LocalRawStore`
mechanism, consistent with the rest of the architecture.

## Web

`/radar` lists the latest candidates with filters for competition, position,
minimum confidence, and player/team search. Copy is explicit that scores are
competition-relative, not a cross-league comparison.

## Scheduling

World Radar runs only via the manual `world-radar.yml` GitHub Actions
workflow (`workflow_dispatch`, `season` + `request_budget` inputs). There is
**no automatic schedule**: production/current-season provider access is not
yet certified, and this keeps quota spend fully operator-controlled.

## Calibration

Block 12's V1 Validation module measures Elo and player-stability signals; it
does not calibrate World Radar's weights. World Radar's own weight/threshold
tuning against real external-competition data remains future work once a
live run has been executed and reviewed.
