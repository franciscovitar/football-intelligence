# AGENTS.md

# Engineering Rules

These rules define the default engineering standards for this repository.

Also follow `WORKFLOW.md` for orchestration, delegation, checkpoints and resource efficiency.

The goal is not maximum architecture, abstraction, patterns, tests, files or documentation.

The goal is the simplest solution that correctly satisfies the requirements while remaining secure, maintainable, testable and evolvable.

---

# 1. Engineering Priorities

When trade-offs are necessary, prioritize approximately:

1. Correct behavior and data integrity
2. Security and privacy
3. Simplicity
4. Maintainability and understandability
5. Reliability
6. Testability
7. User experience and accessibility
8. Performance based on evidence
9. Scalability based on realistic requirements
10. Developer convenience

Do not sacrifice a higher-priority concern for a lower-priority concern without a concrete reason.

---

# 2. Understand Before Implementing

Before a non-trivial change:

- understand the desired outcome;
- inspect the relevant existing implementation;
- identify constraints and acceptance criteria;
- identify affected modules and boundaries;
- understand relevant data flows;
- inspect existing conventions;
- reuse existing working mechanisms where appropriate;
- check existing checkpoints;
- avoid unrelated redesign.

Do not modify code merely because a different design appears aesthetically cleaner.

Prefer the smallest safe change that solves the actual problem.

---

# 3. Requirements and Assumptions

Distinguish:

- explicit requirements;
- inferred requirements;
- engineering decisions;
- assumptions.

If missing information can be handled through a safe and reversible assumption, proceed and document it when relevant.

Escalate only when the missing information materially affects product behavior, security, cost, irreversible actions or architecture.

---

# 4. Architecture

Architecture follows requirements and quality attributes, not fashion.

Prefer the simplest architecture that satisfies realistic current requirements.

For most small and medium new applications, prefer a well-structured modular application unless distributed architecture provides a concrete benefit.

Do not introduce microservices merely for:

- perceived professionalism;
- generic scalability;
- separation of concerns;
- future-proofing.

Distributed services require explicit justification such as:

- independent scaling;
- independent deployment;
- organizational ownership boundaries;
- strong isolation requirements;
- genuinely distinct domains;
- operational reasons that outweigh added complexity.

Maintain:

- high cohesion;
- low coupling;
- clear responsibilities;
- explicit boundaries;
- controlled dependency direction.

---

# 5. Modules and Responsibilities

Organize modules around coherent responsibilities.

A module should ideally know as little as necessary about unrelated modules.

Keep important contracts explicit.

Business logic should not unnecessarily depend on:

- UI;
- database details;
- framework internals;
- transport mechanisms;
- external vendors.

However, do not create layers merely to claim architectural independence.

A direct dependency is acceptable when abstraction provides no practical value.

---

# 6. Design Principles

Treat principles as heuristics, not laws.

Useful heuristics include:

- SOLID;
- GRASP;
- KISS;
- YAGNI;
- DRY;
- Tell Don't Ask;
- composition over inheritance.

Use them when they improve the design.

Do not optimize for compliance with acronyms.

Examples:

Single Responsibility does not mean one class per tiny action.

Dependency Inversion does not mean every dependency requires an interface.

DRY does not mean every similar line must immediately become an abstraction.

Sometimes duplication is safer than the wrong abstraction.

---

# 7. Patterns

Use design patterns to solve observed problems.

Never introduce a pattern simply because it is recognized as a best practice.

Before introducing a meaningful pattern, consider:

- problem;
- context;
- simpler alternatives;
- benefits;
- costs;
- new complexity.

Avoid speculative flexibility.

Build only the complexity the problem has earned.

---

# 8. Important Architectural Decisions

Document significant hard-to-reverse decisions using lightweight ADRs under:

`docs/adr/`

Use an ADR when a decision is:

- architecture-defining;
- expensive to reverse;
- security-sensitive;
- operationally important;
- likely to be questioned later.

Suggested structure:

Context  
Decision  
Alternatives  
Trade-offs  
Consequences

Do not create ADRs for trivial implementation choices.

---

# 9. Quality Attributes

Identify which quality attributes actually matter to the product.

Consider when relevant:

- functional suitability;
- security;
- reliability;
- maintainability;
- performance efficiency;
- scalability;
- usability;
- accessibility;
- compatibility;
- interoperability;
- portability;
- deployability;
- observability;
- recoverability.

Do not maximize every attribute.

Prioritize them.

Where important, turn vague goals into verifiable criteria.

Bad:

"The system should be fast."

Better:

Define the relevant operation, expected load and measurable latency objective.

Architecture is a trade-off process.

---

# 10. Security

Security is part of design.

Never commit:

- passwords;
- API keys;
- access tokens;
- private keys;
- production credentials;
- real secret environment values.

Use environment variables or the platform's secure secret mechanism.

Apply least privilege.

Authentication and authorization are separate concerns.

Authorization must be enforced server-side.

Validate untrusted input at system boundaries.

Do not implement custom cryptography.

Use established security mechanisms.

Do not weaken security controls simply to make development easier.

Do not log secrets or unnecessary sensitive data.

For security-sensitive features, consider:

- assets;
- actors;
- trust boundaries;
- entry points;
- abuse cases;
- mitigations.

Use current authoritative security guidance relevant to the stack when needed.

---

# 11. Data Integrity

Treat data integrity as a first-class requirement.

Use database constraints where the database can reliably enforce an invariant.

Use transactions when multiple changes must succeed or fail together.

Maintain referential integrity where appropriate.

Validate input at boundaries and enforce critical invariants at the correct deeper layer.

Never silently destroy production data.

---

# 12. Database Changes

Use explicit migrations.

Prefer backward-compatible migrations when multiple application versions may coexist during deployment.

For destructive operations:

- understand impact;
- preserve recoverability;
- provide a rollback or recovery strategy when practical.

Indexes must respond to actual access patterns.

Avoid speculative indexing.

Watch for:

- N+1 queries;
- excessive round trips;
- unbounded queries;
- missing pagination;
- race conditions;
- lost updates;
- inconsistent writes.

---

# 13. Persistence Abstractions

Do not automatically create:

- Repository;
- Unit of Work;
- DAO wrappers;
- service layers around every ORM call.

Use them only when they provide concrete value such as:

- a meaningful domain boundary;
- complex persistence logic;
- multiple implementations;
- substantially improved testing;
- portability that is actually required.

Do not wrap a framework API merely to create another indirection layer.

---

# 14. APIs and External Boundaries

Keep contracts explicit and predictable.

Validate external input.

Use consistent error semantics.

Never expose unnecessary:

- stack traces;
- internal infrastructure details;
- secrets;
- sensitive data.

For potentially unbounded collections, use pagination or safe limits.

Consider idempotency for operations that may be retried.

Consider backward compatibility before modifying a public contract.

---

# 15. External Integrations

External services fail.

Handle when relevant:

- timeout;
- unavailable service;
- rate limits;
- invalid responses;
- partial responses;
- authentication failures;
- safe retries.

Retries require bounded behavior.

Avoid aggressive or infinite retry loops.

Do not assume a third-party API behaves as remembered.

For version-sensitive behavior, verify current official documentation.

---

# 16. Dependencies

Prefer existing platform/framework capabilities when they adequately solve the problem.

Before adding a production dependency, evaluate:

- necessity;
- maintenance status;
- trust;
- complexity;
- transitive dependencies;
- security implications;
- runtime/bundle cost;
- lock-in.

Use lockfiles.

Do not perform unrelated major dependency upgrades while implementing a feature.

Do not add a dependency for trivial functionality that can be implemented clearly and safely with existing capabilities.

---

# 17. Testing Philosophy

Optimize for confidence, not test count or coverage percentage.

Use the smallest test level that reliably detects the relevant failure.

Use:

Unit tests
for isolated logic and domain behavior.

Integration tests
for database, service and module boundaries.

End-to-end tests
for critical user journeys.

Test meaningful behavior rather than implementation details.

Do not mock everything.

Prefer real integrations when their cost and reliability are acceptable.

Tests must be deterministic.

Do not hide flaky tests through blind retries.

---

# 18. Bug Fixes

Before fixing a bug when practical:

1. reproduce it;
2. understand the cause;
3. create or identify a failing verification;
4. implement the smallest correct fix;
5. verify the original failure is gone;
6. add a regression test when valuable.

Do not "fix" symptoms while leaving the root cause untouched unless scope explicitly requires a temporary mitigation.

---

# 19. Code Quality

Prefer readable code over clever code.

Use clear names.

Keep responsibilities coherent.

Avoid:

- giant functions;
- giant modules;
- hidden side effects;
- unexplained global mutable state;
- dead code;
- commented-out implementations;
- unnecessary indirection.

Do not split code merely to satisfy arbitrary line counts.

Comments should primarily explain:

- why;
- important constraints;
- non-obvious trade-offs;
- unusual behavior.

Do not comment what the code already says clearly.

---

# 20. Error Handling

Do not silently swallow unexpected errors.

Handle expected failures explicitly.

Preserve useful context when propagating errors.

Keep the original cause where supported.

User-facing errors should be understandable without revealing sensitive implementation details.

Logs should contain enough context to diagnose failures without exposing secrets or unnecessary personal information.

---

# 21. Frontend

For user-facing interfaces, account intentionally for:

- responsive behavior;
- loading states;
- empty states;
- error states;
- success states;
- disabled states;
- duplicate submission prevention;
- navigation;
- visual hierarchy.

Avoid unnecessary layout shifts and excessive client-side work.

Do not sacrifice usability for visual novelty.

---

# 22. Accessibility

Accessibility is part of correctness.

When applicable:

- use semantic HTML;
- support keyboard navigation;
- preserve visible focus;
- provide meaningful labels;
- maintain usable contrast;
- associate errors with inputs;
- provide text alternatives;
- avoid interaction requiring a pointer only.

Use appropriate current accessibility guidance for user-facing applications.

---

# 23. Performance

Do not optimize blindly.

First determine whether performance matters for the requested operation.

Measure where practical.

Prioritize improvements involving:

- algorithms;
- database access;
- network round trips;
- rendering waterfalls;
- payload size;
- unnecessary serialization;
- client bundle size;
- unbounded work;
- blocking operations.

Avoid micro-optimization without evidence.

---

# 24. Caching

Do not add caching merely because it may improve performance.

Caching requires:

- a demonstrated need;
- clear ownership;
- invalidation strategy;
- acceptable staleness;
- failure behavior.

A cache without an invalidation strategy is unfinished architecture.

---

# 25. Reliability and Observability

Critical operations should fail predictably.

When appropriate provide:

- structured logging;
- error reporting;
- metrics;
- tracing;
- health checks.

Observability should help answer:

What failed?  
Where?  
For which operation/request?  
Why?  
How often?

Do not collect telemetry without a concrete operational purpose.

Do not expose sensitive data through observability systems.

---

# 26. Configuration

Keep environment-specific configuration outside application source code.

When environment variables are required, provide an `.env.example` or equivalent.

Never place real secrets in example files.

Prefer reproducible configuration and setup.

Avoid undocumented environment-specific magic.

---

# 27. Environments

Keep development, test, staging and production behavior as consistent as reasonably possible.

Differences must be intentional.

Production must not be the default target for development operations.

Destructive commands should make their target environment clear.

---

# 28. CI and Quality Gates

Automate repeatable quality checks where appropriate.

Possible gates:

- formatting;
- linting;
- type checking;
- tests;
- build;
- security/dependency checks.

Do not disable a valid quality gate merely to obtain a passing pipeline.

Do not declare work complete while required checks are failing.

---

# 29. Git and Scope

Keep changes focused on the requested objective.

Do not:

- rewrite unrelated files;
- reformat the entire repository;
- mix unrelated refactors;
- overwrite user work;
- delete unrelated local modifications.

Preserve existing public behavior unless changing it is part of the task.

Use descriptive commits when commits are part of the workflow.

---

# 30. Documentation

Documentation should be proportional to complexity.

Keep setup and execution instructions accurate.

Document:

- non-obvious architecture;
- important constraints;
- external integrations;
- operational requirements;
- decisions difficult to infer from code.

Do not create documentation that simply restates the directory tree.

Do not create empty documentation files for ceremonial completeness.

---

# 31. Project Initialization

For a new project, establish only what is immediately useful.

Evaluate creating:

- README.md;
- AGENTS.md;
- WORKFLOW.md;
- CLAUDE.md;
- `.env.example`;
- `docs/ARCHITECTURE.md`;
- `docs/QUALITY_ATTRIBUTES.md`;
- `docs/adr/`.

Do not create an artifact if it would currently contain no useful information.

Configure when appropriate:

- formatter;
- linter;
- type checking;
- tests;
- build;
- lockfile;
- CI.

The initial project should compile, build or run successfully before significant feature development continues.

---

# 32. Completion Gate

Writing code is not completion.

Before declaring a task complete:

1. re-read the requested objective;
2. inspect the resulting diff;
3. execute the smallest relevant checks;
4. execute broader validation when risk justifies it;
5. verify actual behavior when possible;
6. consider regression risk;
7. check obvious security and data-integrity impact;
8. remove debugging artifacts;
9. update documentation only when necessary.

For UI changes, perform real browser/visual verification when tools permit it.

Never state that a test, build, deployment or workflow passed unless it was actually executed.

---

# 33. Forbidden Shortcuts

Do not:

- invent library APIs;
- invent configuration options;
- assume current version-specific behavior when it can be verified;
- add architecture because it is fashionable;
- introduce abstractions without demonstrated value;
- introduce microservices without justification;
- weaken tests to make them pass;
- disable security controls for convenience;
- silently ignore failing checks;
- commit secrets;
- perform destructive operations without understanding impact;
- hide unresolved issues behind optimistic wording.

---

# 34. Final Engineering Rule

Prefer evidence over assumptions.

Prefer explicit trade-offs over dogma.

Prefer simple designs over speculative flexibility.

Prefer verified behavior over plausible-looking code.

Prefer maintainability over cleverness.

Build only the complexity the problem has earned.