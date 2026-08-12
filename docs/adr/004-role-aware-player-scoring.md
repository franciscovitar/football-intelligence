# ADR 004 — Role-aware, versioned player scoring

## Context

Football Intelligence needs a useful player ranking before richer event and
tracking data are available. Raw totals favor minutes played, while one universal
score would compare fundamentally different roles on inappropriate metrics.

The current provider reliably supplies broad positions and a limited set of
player event counts, but not verified detailed roles, xG/xA, progressive actions,
or tracking data.

## Decision

Player Analytics V1 will:

- compare players within broad goalkeeper/defender/midfielder/forward roles;
- normalize count output per 90 minutes;
- use exponentially weighted recent windows for Form;
- context-adjust defensive actions for possession opportunity;
- shrink small samples toward role baselines;
- convert stabilized metrics to role percentiles;
- calculate transparent, versioned role-weighted Performance scores;
- persist score and confidence separately;
- preserve raw per-90 features alongside adjusted values.

The initial model version is `player-v1.0`.

## Alternatives

### One universal weighted sum

Rejected because it systematically favors roles whose event counts dominate the
selected metrics and hides role context.

### Provider player rating

Rejected as the core model because its methodology is opaque and would make
Football Intelligence dependent on an unexplained vendor score.

### Machine-learned black-box rating immediately

Deferred. The current verified dataset is not yet rich enough, and there is no
validated target label that justifies added complexity.

## Trade-offs

The V1 model is interpretable and testable but its weights remain hypotheses.
Broad role groups also lose tactical nuance.

Those limitations are preferable to false precision. Later model versions can
add league/opponent adjustment, richer data, detailed roles, or learned weights
without changing the snapshot contract.
