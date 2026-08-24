# Wikidata × Wyscout Player Profile Lab

Status: empirical lab result, read-only, no product promotion.

## Scope

The lab measured Wikidata identity/profile evidence against the certified Wyscout Open `ENG_PL` 2017/18 roster.

Sources:

- Wyscout Open official Figshare collection `4415000`, CC BY 4.0.
- Wikidata official MediaWiki API + Wikidata Query Service, structured data under CC0.

The lab used no fuzzy matching, edit-distance thresholds, LLM resolution, PostgreSQL writes, PlayerCrosswalk writes, score changes, or product promotion.

## Real-source result

Observed against the official source bytes:

| Measure | Count | Share of 603-player roster |
| --- | ---: | ---: |
| Wyscout roster players | 603 | 100% |
| Wyscout profiles available | 599 | 99.3% |
| Wikidata club mappings resolved | 19 / 20 | 95.0% of clubs |
| Players with one exact normalized-name candidate | 359 | 59.5% |
| Players with exact Wikidata DOB | 354 | 58.7% |
| Players with Wikidata citizenship | 359 | 59.5% |
| Players with Wikidata position | 358 | 59.4% |
| Players with bounded season-relevant P54 team context | 186 | 30.8% |
| `review_required` identity candidates | 354 | 58.7% |
| `insufficient_evidence` candidates | 5 | 0.8% |
| No exact-name candidate | 240 | 39.8% |

Relative to the 599 Wyscout players with a usable profile, exact-name coverage was 59.9% and exact-DOB coverage was 59.1%.

The query discovered 14,541 distinct Wikidata entities associated through P54 with the resolved clubs. The large discovery universe is expected because raw P54 membership is historical and not season-bounded at discovery time; temporal qualifiers are evaluated later by the profile parser.

## Club-resolution finding

Wikidata labels frequently use punctuated corporate abbreviations such as `Liverpool F.C.` and `Huddersfield Town A.F.C.`. The lab therefore normalizes punctuation only at the Wikidata search boundary before applying the existing deterministic team-name normalizer.

One club remained deliberately unresolved: Wyscout `Everton`. Wikidata search returned both `Everton F.C.` and an unrelated footballer labelled `Everton`. The lab fails closed on this homonym rather than silently selecting the club. Consequently the player coverage above is a conservative lower bound.

This is a feature, not a failure of the identity contract: ambiguous external search results must not be converted into canonical links without additional explicit evidence.

## Identity decision

Wikidata is useful enough to keep as a selected profile/identity enrichment source.

However, Wikidata alone must not create a canonical PlayerCrosswalk entry. Even candidates with exact normalized name, exact DOB, same competition/season and bounded shared club context remain `review_required`, because Wikidata does not provide shared canonical match IDs required by the current deterministic player-resolution contract.

No fuzzy/LLM fallback should be added to raise coverage.

## Product role

Approved role from this lab:

- player name/profile corroboration;
- exact date-of-birth corroboration where present;
- citizenship evidence;
- position evidence;
- club-career evidence when P54 temporal qualifiers overlap the target season;
- candidate generation for manual or stronger deterministic cross-source resolution.

Not approved from this lab:

- performance metrics;
- Player V2 dimension inputs;
- Overall/ranking inputs;
- automatic player identity merges;
- treating an unqualified P54 membership as evidence that the player belonged to the club in a target season.

## Next step

The next source-fusion step should preserve this profile evidence as a separate source role and combine it with another source that can provide stronger player identity overlap and/or additional objective football metrics. Profile enrichment must remain separate from performance scoring until each metric has an explicit Metric Catalog identity and reconciliation policy.
