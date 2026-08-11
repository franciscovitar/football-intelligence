# WORKFLOW.md

# AI Engineering Workflow

This file defines HOW work is performed in this project.

`AGENTS.md` defines HOW the software itself must be engineered.

The objective is:

- maximum useful autonomy;
- minimum unnecessary user intervention;
- high engineering quality;
- low token and tool waste;
- minimal duplicated work;
- intelligent delegation;
- reusable checkpoints;
- evidence-based verification;
- controlled and reversible changes.

---

# 1. Core Rule

Do directly everything that can be completed reliably with the currently available tools.

Delegate only when another tool, agent or environment has a concrete advantage.

Every handoff has a cost.

Do not create bureaucratic chains such as:

Primary assistant
→ agent analyzes again
→ another agent audits the same thing
→ user intervenes
→ everything is reviewed again.

Prefer:

Primary assistant
→ solves what it can
→ delegates one precise task when useful
→ receives result
→ verifies what matters
→ continues.

---

# 2. Default Responsibility Order

Use this order unless the task clearly requires otherwise:

1. Primary assistant
2. Specialized implementation agent
3. Alternative specialized agent
4. External/authenticated operator
5. User

The user is the last operational resource, not the first.

---

# 3. Primary Assistant

The primary assistant owns orchestration and final integration.

It should directly handle when possible:

- reasoning;
- architecture;
- product/technical analysis;
- planning;
- research;
- official documentation lookup;
- file inspection;
- comparison of alternatives;
- technical decisions;
- test strategy;
- prompt preparation;
- result review;
- documentation;
- remote verification through available tools.

Do not delegate something merely because another agent exists.

---

# 4. Codex

Prefer Codex when direct repository access provides a meaningful advantage.

Typical tasks:

- implementation;
- repository investigation;
- debugging;
- refactoring;
- writing or repairing tests;
- scripts;
- local build failures;
- focused multi-file changes;
- code-level migrations;
- commits when requested.

Do not ask Codex to redo conceptual analysis already completed and trusted unless implementation reveals contradictory evidence.

---

# 5. Claude / Claude Code

Use Claude or Claude Code only when there is a concrete reason.

Examples:

- unusually large context where it provides an advantage;
- a specific complex refactor;
- specialized document/code reasoning;
- a justified independent review for a high-risk change.

Do not use:

Codex review
+
Claude review
+
primary assistant review

merely "to be safe".

Redundancy must be proportional to risk.

---

# 6. Work / External Operators

Use an external or authenticated environment when the task requires capabilities not available locally or directly.

Examples:

- authenticated browser sessions;
- SaaS administration;
- deployments;
- cloud infrastructure;
- production dashboards;
- external accounts;
- real browser QA;
- device-specific verification;
- private services;
- operations requiring credentials or an installed application.

Do not use an external operator for information already obtainable reliably through an API, connector or local tool.

---

# 7. User Intervention

Default target:

0 manual actions.

Do not ask the user to perform mechanical work an agent can safely perform.

Examples:

- running routine commands;
- copying files;
- manually editing configuration;
- reading logs;
- checking obvious output;
- repeating known information;
- performing QA an agent can perform.

Request user intervention only when genuinely necessary, such as:

- CAPTCHA;
- 2FA;
- physical presence;
- new account authorization;
- legal consent;
- spending money;
- irreversible publication;
- production-sensitive approval;
- destructive operations;
- important product decisions;
- major architecture decisions with materially different consequences.

When intervention is unavoidable:

1. group all necessary actions;
2. ask once;
3. provide exact short steps;
4. avoid unnecessary explanation;
5. continue automatically after the required input is provided.

---

# 8. Effort Classification

For meaningful work, classify effort instead of pretending to know an exact completion time.

Use:

S — small, localized work with low uncertainty.

M — multiple related changes, moderate investigation or verification.

L — broad work, architectural impact, external dependencies or significant uncertainty.

Also state when useful:

- scope;
- main stages;
- important unknowns;
- expected user intervention;
- stop conditions.

Do not fabricate precise elapsed-time estimates.

---

# 9. Token and Tool Economy

Tokens, tool calls, context and execution are finite resources.

Save them without lowering engineering quality.

Avoid:

- repeatedly reading the entire repository;
- re-analyzing already validated documents;
- copying large logs when a relevant excerpt is enough;
- narrating every command;
- sending raw conversation transcripts between agents;
- asking multiple models the same question;
- running full suites after every tiny change;
- redundant web searches;
- rebuilding healthy resources;
- repeating already-passed QA.

Prefer:

- focused searches;
- relevant files;
- diffs;
- metadata;
- targeted tests;
- structured summaries;
- existing checkpoints;
- incremental verification;
- one full validation at the end of a stable stage.

Use the cheapest reliable method, not merely the cheapest method.

---

# 10. Diagnose Before Changing

When something fails, do not immediately modify code.

First classify the likely failure domain:

- application code;
- configuration;
- data;
- database;
- infrastructure;
- environment;
- dependency;
- authentication;
- authorization;
- external service;
- deployment;
- browser/runtime behavior;
- UX;
- misunderstanding of an API or contract.

Then use the appropriate tool.

Examples:

Code failure
→ implementation agent.

Vercel/cloud/SaaS failure
→ external operator.

Architecture problem
→ primary assistant.

Business/product ambiguity
→ user only if the decision materially matters.

Do not fix code when the actual problem is configuration.

---

# 11. Checkpoints

A verified result becomes a checkpoint.

Examples:

- tests PASS;
- build PASS;
- QA PASS;
- migration validated;
- deployment verified;
- configuration verified;
- architecture decision approved;
- credential confirmed;
- integration verified.

A checkpoint should preserve, when relevant:

- objective;
- state;
- validated results;
- pending work;
- changed files;
- commit/version;
- external resources;
- important decisions;
- constraints;
- risks;
- next action.

---

# 12. Do Not Repeat Certified Work

Do not repeat a validated checkpoint unless:

- later changes could affect it;
- a regression is observed;
- new contradictory evidence appears;
- a relevant dependency/version changed;
- the user explicitly requests revalidation.

Always start from the latest trustworthy checkpoint.

Do not restart investigation from zero without reason.

---

# 13. Testing Strategy During Work

Use progressive verification.

Preferred flow:

change
→ focused test/check
→ correction if necessary
→ focused test PASS
→ complete relevant validation
→ checkpoint.

Do not run an expensive full suite after every small edit unless the suite is extremely cheap or the risk requires it.

Final validation should cover relevant cases such as:

- happy path;
- errors;
- permissions;
- boundaries;
- negative behavior;
- idempotency where relevant;
- regression risk;
- partial states;
- rollback behavior when relevant.

---

# 14. Retry Discipline

Do not repeat a failing approach indefinitely.

After approximately two meaningful attempts using essentially the same hypothesis:

STOP repeating it.

Instead:

1. reconsider the diagnosis;
2. inspect new evidence;
3. change strategy;
4. use another tool if it has a real advantage;
5. report the blocker if no safe path remains.

A retry with a new hypothesis is not the same as blindly repeating an old approach.

---

# 15. Fail Fast Only for Real Risk

Stop immediately when continuing could reasonably:

- corrupt data;
- compromise security;
- affect production unexpectedly;
- create unintended cost;
- execute an irreversible action;
- widen permissions unexpectedly;
- produce knowingly invalid results.

Do not confuse internal operational events with incidents.

Examples:

A secret transiently processed inside an authorized secure tool
is not automatically a leak.

A secret persisted in source code or exposed publicly
is a leak.

An internal identifier seen during debugging
is not automatically an incident.

Sensitive data written unnecessarily to persistent logs
is a real problem.

Security must reduce real risk without making normal operation impossible.

---

# 16. Rollback Proportionally

When something fails, preserve everything that remains correct and safe.

Do not destroy a healthy environment because one component failed.

Prefer:

previous state
→ isolated change
→ verification
→ retain or revert that change.

If eight independent items PASS and one FAILS, preserve the eight valid results when safe.

---

# 17. Reversibility

Prefer changes that are:

- incremental;
- reversible;
- isolated;
- observable;
- auditable;
- testable.

For sensitive changes, know when practical:

- previous state;
- intended change;
- validation method;
- rollback method.

Avoid large irreversible operations when smaller reversible steps can achieve the same objective.

---

# 18. Delegation Prompt

When delegating meaningful work, provide only the context needed to succeed.

Include:

## Goal
Exact desired outcome.

## Starting checkpoint
What is already known or verified.

## Do not repeat
Work that has already been completed.

## Scope
What may be changed.

## Relevant context
Files, components, resources or constraints.

## Requirements
Important technical or product constraints.

## Verification
Tests or checks that should be executed.

## PASS
What constitutes success.

## FAIL / STOP
Conditions requiring the agent to stop instead of improvising indefinitely.

## Rollback
How to preserve or revert safely when relevant.

## Return format
Compact summary of results.

Avoid prompts like:

"Review this and fix it."

Prefer a precise bounded assignment.

---

# 19. Agent Result Format

Prefer compact handoffs.

Use approximately:

STATUS: PASS / PARTIAL / FAIL

CHANGES:
- ...

VERIFIED:
- ...

NOT VERIFIED:
- ...

RISKS:
- ...

NEXT:
- ...

Include detailed logs only when required to diagnose a remaining problem.

---

# 20. Research

When current or external information matters:

1. research directly;
2. prefer primary/official sources;
3. compare realistic alternatives;
4. apply the result to the project.

Do not send the user away to perform research that can be done by the available tools.

Do not return a list of options when one option is clearly superior.

Recommend one and briefly explain why.

---

# 21. Autonomous Decisions

An agent may make a decision automatically when it is:

- reversible;
- local;
- low-risk;
- no-cost;
- inside the approved architecture;
- without significant external consequences.

Do not ask permission for trivial engineering choices.

Escalate when involving:

- cost;
- production;
- publication;
- real sensitive data;
- destructive operations;
- irreversible changes;
- major architectural shifts;
- broader permissions;
- new accounts;
- materially different product outcomes.

---

# 22. Large Work

Break large work into coherent stages.

Each stage should ideally have:

input checkpoint
→ focused implementation
→ focused verification
→ final validation
→ new checkpoint.

Do not unnecessarily alternate among agents.

Prefer one agent to own a coherent unit of work.

---

# 23. Cross-Session Handoff

When work moves to another chat, agent or environment, preserve a compact master context.

Include only what is necessary:

- purpose;
- relevant architecture;
- workflow constraints;
- key decisions;
- current state;
- checkpoints;
- versions when important;
- verified results;
- known problems;
- pending work;
- next action.

The next session should be able to answer:

"What should happen next?"

without re-investigating the project.

---

# 24. Communication With the User

Communicate:

- directly;
- concretely;
- without unnecessary technical jargon;
- with enough explanation to understand important decisions.

Do not present ten options when one is clearly preferable.

For meaningful alternatives:

recommend one
+
briefly explain the trade-off.

When the user must act, state exactly what they must do.

---

# 25. Completion Rule

Before finishing a stage, ask internally:

1. Did we solve the requested problem?
2. Did we reuse existing checkpoints?
3. Did we avoid unnecessary duplication?
4. Was the right tool used?
5. Was user intervention minimized?
6. Was the change verified?
7. Is the resulting state safe?
8. Is anything important still unknown?
9. Is the next step obvious?

The objective is not maximum automation.

The objective is maximum useful autonomy with minimum friction, without sacrificing quality, security or control.