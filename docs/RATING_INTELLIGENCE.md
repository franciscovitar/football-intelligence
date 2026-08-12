# Rating Intelligence V1

Block 10 compares durable player performance with structured external perception.
Its model version is `rating-v1.0`.

The output is intentionally conservative. A player is not labelled Overrated or
Underrated just because one article is positive or negative.

## Inputs

Performance comes from `meta-v1.0`:

- `stable_score`;
- `stable_confidence`.

Perception comes from canonical, player-linked `perception-v1.0` evidence.

`Stable Score` is the anchor because public reputation usually moves more slowly
than short Form. Rating Intelligence therefore compares perception with the
longer-term performance layer rather than with the last few matches.

## Evidence window

V1 uses canonical evidence from the latest 180 days.

Evidence recency follows a 45-day half-life. Older evidence remains usable inside
the window but contributes less than recent evidence.

## Deterministic stance model

V1 does not use an LLM to produce a quantitative perception score.

For each player-linked evidence item:

1. keep title/excerpt sentences containing the player's exact linked display name;
2. normalize Unicode/case/spacing;
3. match a deliberately small football-specific phrase lexicon;
4. produce a stance in `[-1, +1]`;
5. attach stance confidence based on explicit matched phrases.

Examples of supported positive cues include `earns praise`, `outstanding`,
`brilliant`, `superb`, and `impresses`.

Examples of supported negative cues include `struggles`, `poor`, `under fire`,
`costly error`, `blunder`, and `disappointing`.

Evidence with no supported stance phrase is retained for breadth/provenance but
is not silently guessed positive or negative.

The V1 lexicon is intentionally English-first because the checked-in public feeds
are English-language sources. New languages require explicit rules and tests.

## Source balancing

Article volume is not treated as independent consensus.

Within each source, evidence is weighted by recency and stance confidence. The
source's total contribution is then normalized so each scored source receives
equal aggregate influence.

This prevents an outlet publishing many articles from dominating another outlet
solely because it has higher volume.

Block 9 cross-source duplicates remain excluded from Rating Intelligence because
the repository reads only canonical evidence (`duplicate_of_id is null`).

## Perception score

The source-balanced mean stance is mapped to `0–100`:

```text
Perception = 50 + 50 × mean_stance
```

- 50 ≈ neutral/mixed direction;
- above 50 = increasingly positive perception;
- below 50 = increasingly negative perception.

This is a structured evidence score, not factual truth or market value.

## Consensus and Polarization

Polarization is the source-balanced dispersion of evidence stance.

```text
Polarization = 100 × sqrt(weighted stance variance)
```

Strong opposite views approach 100; uniform views approach 0.

Consensus rewards both directional strength and agreement:

```text
Consensus = 100 × mean_absolute_stance × (1 - polarization_fraction)
```

Neutral evidence therefore cannot create strong Consensus merely by agreeing on
nothing directional.

## Confidence

Perception confidence combines:

- 35% evidence breadth, saturating at 8 canonical items;
- 30% scored-source breadth, saturating at 3 sources;
- 20% stance coverage;
- 15% recency quality.

Final rating confidence is capped by the weaker side of the comparison:

```text
min(Stable confidence, Perception confidence)
```

and is reduced as Polarization rises.

## Strong gates

Overrated / Underrated is only allowed when all are true:

- at least 4 canonical evidence items;
- at least 3 scored evidence items;
- at least 2 independently scored sources;
- Perception confidence >= 0.55;
- final Rating confidence >= 0.50;
- Polarization < 60.

If Polarization reaches 60, the signal is `polarized` instead of forcing an
Overrated/Underrated conclusion.

## Rating gap

```text
Rating Gap = Stable Score - Perception Score
```

With sufficient evidence:

- gap >= +12 → `underrated`;
- gap <= -12 → `overrated`;
- otherwise → `aligned`.

A positive gap means measured stable performance is stronger than external
perception. A negative gap means perception is stronger than measured stable
performance.

## Persistence

`analytics.player_rating_snapshots` stores:

- performance and perception scores/confidence;
- Rating Gap and Rating confidence;
- rating/perception signals;
- Consensus and Polarization;
- evidence/source counts;
- the 180-day evidence window;
- auditable evidence breakdown;
- source and model versions;
- calculation timestamp.

## Web

`/ratings` exposes:

- Underrated;
- Overrated;
- Consensus;
- Polarization;
- role/search/confidence filters.

Player detail also shows the latest Rating Intelligence snapshot.

## Scheduling

Rating Intelligence is recalculated:

- after Meta Analytics in the core football sync;
- after Perception ingestion in the perception sync.

That keeps the comparison current when either side changes without introducing
another service or queue.

## Limits

V1 is intentionally conservative and heuristic.

- no LLM sentiment score;
- no market value;
- no transfer recommendation;
- no semantic duplicate detection beyond Block 9's deterministic model;
- no aliases/fuzzy entity resolution;
- no language inference;
- no source-quality prestige weighting;
- no causal claims about why perception differs from performance.

The phrase model, thresholds, source breadth, and calibration should be evaluated
with real collected evidence in Block 12 before treating rankings as stable
product truth.
