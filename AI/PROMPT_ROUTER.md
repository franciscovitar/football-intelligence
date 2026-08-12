# AI Prompt Router

This file is the lightweight routing layer for the specialized engineering prompt library in `AI/prompts/`.

It tells the active AI which procedure to load for the current task.

It is NOT a checklist that must be executed from top to bottom.

`AGENTS.md` and `WORKFLOW.md` remain canonical. Specialized prompts supplement them and never override them.

---

# 1. Core Rule

The user describes the outcome they want.

The orchestrator decides which specialized procedure, if any, is useful.

Do not require the user to remember prompt numbers or names.

Do not load all 25 prompt files.

Use the smallest prompt or prompt chain that materially improves the result.

If the task can be completed reliably without a specialized prompt, complete it directly.

---

# 2. Routing Algorithm

For each task:

1. Understand the requested outcome.
2. Recover the latest trustworthy checkpoint.
3. Identify what is already decided, implemented and verified.
4. Identify the single next uncertainty or unit of work.
5. Choose the most specific prompt that addresses it.
6. Load that prompt file only.
7. Execute it using the relevant project context.
8. If its result creates a real need for another procedure, load the next prompt.
9. Stop when the user's outcome is solved and sufficiently verified.

Never execute prompts merely because they appear earlier in the numeric sequence.

---

# 3. Prompt Library

The expected library location is:

`AI/prompts/`

Available procedures:

## FOUNDATION / PRODUCT

`00_Project_Initialization.txt`
Use when establishing the professional foundation of a new or insufficiently prepared project.

`01_Product_Discovery.txt`
Use when the underlying product problem, users, value, scope or MVP are still materially unclear.

`02_Feature_Specification.txt`
Use when a requested feature needs explicit behavior, rules, permissions, states, edge cases or acceptance criteria before implementation.

`03_Technical_Spike.txt`
Use when a meaningful technical uncertainty requires current research, a focused experiment, benchmark or proof before a decision.

## ARCHITECTURE

`04_Architecture_Design.txt`
Use when the architecture of a new system, major subsystem or substantial evolution genuinely needs to be designed.

`05_Architecture_Decision.txt`
Use for one important architectural choice with meaningful trade-offs or reversal cost.

## DESIGN

`06_UX_Design.txt`
Use when the user journey, information architecture, tasks or interaction model need design before visual styling.

`07_UI_Art_Direction.txt`
Use when the product needs a coherent visual direction, personality or visual language.

`08_Design_System.txt`
Use when repeated UI patterns justify reusable tokens, components, states and design rules.

`09_Screen_Design.txt`
Use to design one screen or tightly related flow in implementation-ready detail.

`10_Responsive_States.txt`
Use when responsive transformations and important UI states need explicit behavior.

`11_Visual_QA.txt`
Use to compare the real rendered implementation against the approved design and correct meaningful visual/runtime deviations.

`12_Design_to_Code.txt`
Use when translating an approved design, Figma screen or reference into production-quality code.

## ENGINEERING

`13_Feature_Implementation.txt`
Use when the feature is sufficiently defined and ready to be implemented.

`14_Data_API_Design.txt`
Use when persistent data semantics or an API/application contract need explicit design before implementation.

`15_External_Integration.txt`
Use for non-trivial external APIs, SaaS providers, authentication providers, payments, AI services, storage, webhooks or similar boundaries.

`16_Safe_Refactor.txt`
Use when improving internal structure while preserving intended observable behavior.

## DEBUG

`17_Bug_Diagnosis.txt`
Use when a failure exists and root cause has not yet been established. Diagnose before changing code.

`18_Bug_Fix.txt`
Use after root cause is sufficiently established and the smallest correct fix plus regression protection should be implemented.

## QUALITY

`19_Test_Strategy.txt`
Use when the appropriate testing boundaries, risks, CI tiers or coverage gaps require explicit strategy.

`20_Code_Review.txt`
Use to review a diff, PR or completed change for correctness, risk, maintainability and verification.

`21_Security_Review.txt`
Use when the scope or risk justifies an explicit security review.

`22_Performance_Diagnosis.txt`
Use when performance is actually failing or uncertain and needs measurement before optimization.

## DELIVERY

`23_Production_Readiness.txt`
Use before an important release to determine whether it is responsibly ready for real users.

`24_Deploy_Real_QA.txt`
Use to deploy/promote the approved release and verify actual behavior through the real target environment.

---

# 4. Typical Minimal Chains

These are examples, not mandatory pipelines.

## New project with unclear product

`01 → 00`

Add `03`, `04` or `05` only if their specific uncertainty/decision exists.

## New project already well defined

`00 → 02 → 13`

Add design/data/integration procedures only where they provide value.

## Normal backend feature

`02 → 14 if needed → 13 → 20 if review is warranted`

## Visual feature / screen

`02 → 06 if UX is unresolved → 09 → 10 if needed → 12 → 11`

Use existing `07` and `08` checkpoints instead of recreating art direction or the Design System for every screen.

## External integration

`02 → 15 → 13`

Insert `03` only if a technical assumption is genuinely uncertain.

## Architectural choice

`03 if evidence is missing → 05`

Do not run a full `04` Architecture Design for every local decision.

## Bug

`17 → 18`

Add `20` when an independent code review materially reduces risk.

Do not restart diagnosis inside `18` unless new evidence contradicts the checkpoint.

## Refactor

`16`

If it enables a feature:

`16 → checkpoint → 13`

Keep structural change and behavior change separable when practical.

## Performance problem

`22 → focused implementation/fix → verification`

Do not optimize before the bottleneck is supported by evidence.

## Important release

`21 if security risk warrants it → 22 if performance risk warrants it → 23 → 24`

Do not execute security or performance reviews ceremonially when risk does not justify them.

---

# 5. Skip Rules

Skip a procedure when its required output already exists as a trustworthy checkpoint.

Examples:

- approved Product Discovery exists → do not rerun `01`;
- architecture already supports the feature → do not run `04`;
- Design System is already certified → do not rerun `08`;
- root cause is confirmed → start from `18`, not `17`;
- Visual QA already passed and later changes cannot affect visuals → do not repeat `11`.

Revalidate only when:

- later changes may have invalidated the checkpoint;
- a regression appears;
- contradictory evidence appears;
- a relevant dependency/version/environment changes;
- the user explicitly asks for revalidation.

---

# 6. Loading Rules

The router may be kept in persistent context because it is intentionally compact.

The full prompt library must remain on-demand.

When a prompt is selected:

1. read the complete selected prompt file;
2. combine it with only relevant project context and checkpoint information;
3. do not paste/reload unrelated prompts;
4. do not restate all of `AGENTS.md` or `WORKFLOW.md`;
5. do not treat each selected prompt as requiring a different agent.

A prompt is a procedure, not necessarily a delegation.

The primary assistant may execute it directly when it has the required tools and context.

---

# 7. Delegation Rules

When another agent has a concrete advantage, delegate only the bounded task.

Provide:

- goal;
- starting checkpoint;
- selected specialized procedure when useful;
- relevant files/context;
- scope;
- requirements;
- verification;
- PASS / FAIL conditions;
- rollback when relevant.

Do not send:

- all 25 prompt files;
- full conversation transcripts;
- unrelated repository context;
- already certified analysis.

Follow the responsibility and delegation rules in `WORKFLOW.md`.

---

# 8. Research Rules

When the selected procedure depends on information that can change, verify it using current authoritative sources.

Examples:

- framework/library versions;
- provider APIs;
- standards;
- security guidance;
- platform behavior;
- pricing/limits;
- deployment capabilities.

Prefer official or primary sources.

Do not rely only on model memory for version-sensitive decisions.

---

# 9. Verification Rules

Do not collapse these into one concept:

CODE WRITTEN

TESTS / BUILD

RUNTIME VERIFIED

DEPLOYED

REAL QA VERIFIED

Never declare a layer PASS unless it was actually checked or inherited from a still-valid checkpoint.

Use the smallest verification sufficient for the current stage, then broader relevant validation at stable boundaries.

---

# 10. User Interaction

The user should normally communicate in plain language.

Examples:

"Add favorites to players."

"This save flow is broken."

"Make this Figma screen real."

"The table is too slow."

"Release this to production."

The orchestrator performs prompt selection automatically.

Do not ask the user which prompt to use unless they explicitly want to control the workflow.

Ask the user only for decisions or access that cannot be resolved safely through available context/tools and that materially affect the outcome.

---

# 11. Conflict and Missing-File Rules

Priority inside this repository:

1. higher-priority system/platform instructions;
2. explicit current task requirements;
3. `AGENTS.md` and `WORKFLOW.md`;
4. this router;
5. selected specialized prompt.

A specialized prompt must never weaken security, data integrity, scope control or verification rules from the canonical files.

If a selected prompt file is missing:

- do not load unrelated prompts as a substitute;
- continue using the canonical rules and the router guidance when the task is still clear;
- report the missing library file only if it materially limits the result.

---

# 12. Completion Rule

Prompt routing is successful when:

- the minimum useful procedure set was used;
- existing checkpoints were reused;
- unnecessary context was not loaded;
- no ceremony was added;
- the user's requested outcome was solved;
- relevant behavior was actually verified.

The library exists to reduce cognitive load and improve consistency.

It must not become bureaucracy.
