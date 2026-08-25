# Wyscout v0.4 recertification

Status: **PASS — ESP_LL 2017/18 observational equivalence certified**

On 2026-08-25 Football Intelligence re-ran the complete Wyscout Open ESP_LL
2017/18 adapter output under the previously certified `wyscout-open-v0.3` and
the candidate `wyscout-open-v0.4`. The official Wyscout Figshare source was
re-acquired and its five core European league files passed the repository's
source audit before comparison.

## Result

- baseline: `wyscout-open-v0.3`;
- candidate: `wyscout-open-v0.4`;
- scope: `ESP_LL` 2017/18;
- observations per version: **416,407**;
- comparison rule: every `NormalizedObservation` field must be identical except
  `semantic_version`;
- result: **all 416,407 canonical rows identical**;
- candidate `long_passes_accurate` observations in ESP_LL: **0**;
- candidate `passes_into_final_third` observations in ESP_LL: **0**;
- canonical payload SHA-256:
  `29b23d96326fb82b94e6529ad951e4c1b3812d0617fff79a5d34d23bc2763eb5`.

This is evidence that v0.4's new final-third emission is correctly scope-gated
to the separately audited ENG_PL 2017/18 path. It does **not** infer that the
metric is valid for Spain, Italy, Germany or France.

## Comparability consequence

The existing Wyscout Open x StatsBomb Open ESP_LL provider-pair policies were
reviewed against v0.3. Because v0.4 is now proven observationally equivalent in
that exact comparability scope, the Wyscout certified policy pin may move from
`wyscout-open-v0.3` to `wyscout-open-v0.4` without silently inheriting an
untested semantic version. Any future Wyscout semantic bump must fail closed
again until separately re-certified.
