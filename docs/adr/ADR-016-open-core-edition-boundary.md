# ADR-016: Open-Core Edition Boundary

**Status:** Accepted
**Date:** 2026-10-17
**Decision Owners:** Aegis Vuldris Maintainers

---

## 1. Decision Summary

Aegis Vuldris remains a single open-source engine: one repository, one `aegis-vuldris`
distribution, one shared codebase. Two deployment paths run that code:

- **Community** — self-hosted, default configuration, no limits imposed by the
  software itself.
- **Cloud** — a hosted pilot configured from the same image with different
  environment settings, a worker process, and organization-level defaults.

The boundary between them is **configuration only**:

- `AEGIS_EDITION=community|cloud` is a defaults switch. It may select default
  dispatcher behavior, default plugin policy, and default quota values. It must
  never branch engine logic, grading, or verdict semantics.
- Billing and entitlement code lives outside the core, in a new top-level
  package `app/billing/`, exposing only an `Entitlements` protocol. Core modules
  never import it — enforced by an automated import test, not by convention.
- For identical inputs, both editions produce identical verdicts. Any graded
  divergence between editions is a bug, not a feature.
- There is no license split, no second package, and no closed-source fork in
  this window.

## 2. Context

Aegis Vuldris's next stage is twofold: grow open-source adoption, and prepare a
hosted pilot for organizations that want the tool operated for them. Both goals
are real, and they pull in opposite directions if handled carelessly:

- **Forking the engine** (a private cloud repository) duplicates grading,
  adapters, evidence handling, and verification semantics. From that moment the
  open-source engine and the hosted engine drift, and every fix has to be
  applied twice or silently diverges.
- **Feature-gating the engine** (paid checks inside core code paths) corrupts
  the community tool's predictability and makes operational behavior depend on
  a license state — exactly the kind of hidden behavior the project's honesty
  rules exist to prevent.
- **Restructuring into `core/`-style packages** would be the "clean" answer to
  boundaries, but it is a large mechanical change with real regression risk and
  no user-visible benefit at this stage.

The existing codebase is a single coherent backend (`backend/app/`) with
well-established seams: the adapter registry, the execution engine, service
modules, and the security policy layer. The planned package boundary
(`core / assessment / execution / …`) is mapped onto those existing
packages and enforced by tests, not by moving files.

The P2 safety semantics are permanent and constrain this decision as well:
nothing outside the deterministic verification loop may change fix state, and
no edition may behave differently in ways users cannot observe.

## 3. Decision Drivers

1. **Adoption and trust.** Community users must be able to read the exact code
   that runs for them, including everything that touches their targets and
   evidence.
2. **Single source of truth.** One engine means one set of verdicts, one bug
   tracker, one verification semantics.
3. **Contributor trust.** Contributions to the open engine must not be
   silently "moved" behind a hosted boundary.
4. **Pilot safety.** The hosted path needs tenancy, quotas, and retention
   without modifying engine behavior under operational pressure.
5. **Reviewability.** The boundary must be small enough to review in a pull
   request and mechanical enough to test in CI.
6. **Reversibility.** Choosing "configuration switch" over "architecture
   change" keeps both directions open.

## 4. Decision

### 4.1 One repository, one package

The `aegis-vuldris` wheel remains a single distribution. Community is the default
configuration. The cloud path adds modules (`app/billing/`, worker, dispatch),
settings, and a Compose profile — not a fork, not a second package.

### 4.2 The edition switch is a defaults switch

`AEGIS_EDITION=community|cloud` sets defaults only:

| Setting | Community default | Cloud default |
|---|---|---|
| `JOB_DISPATCHER` | `inline` (in-process, ADR-005 behavior) | `db` (durable jobs, ADR-018) |
| `ALLOW_THIRD_PARTY_PLUGINS` | `true` (self-hosted responsibility) | `false` (first-party code only, ADR-019) |
| Quota defaults | unlimited | organization plan limits (ADR-017) |

It must not branch engine logic. Review rule: no `if edition == cloud` in
service or engine code. The cloud image is the same image with different
environment and Compose profile; the switch matrix is documented in the
deployment guide.

### 4.3 Billing never enters the core

The only new top-level package the cloud path adds is `app/billing/`. It
contains an `Entitlements` protocol and a `CommunityEntitlements` no-op
(unlimited); the pilot reads plan limits from the organization row. There is no
external billing-provider integration in this window.

Core modules — adapters, grading, classifier, scoring, execution engine,
verification, security — must never import `app.billing` or `app.api`. A test
(`tests/test_module_boundaries.py`, an AST scan) enforces this. Convention is
not considered enforcement.

### 4.4 Verdict parity

For the same inputs, the community and cloud engines must produce identical
verdicts. Cloud adds tenancy, limits, scheduling, and retention — never
different grading. The parity rule is a review checklist item: any graded
verdict differing between editions is treated as a bug.

### 4.5 What this boundary is not

- It is **not** a physical package move. No `core/`-style restructuring happens
  in this window; boundaries are documented and import-tested instead.
- It is **not** an entitlement system in community. A community install never
  checks a license.
- It is **not** a license split. Everything in the repository is Apache-2.0
  (ADR-020).

## 5. Implementation Status

**Shipped:**

- Single-distribution packaging (`pyproject.toml`), single-sourced version,
  releases published from tags.
- The plugin policy switch `ALLOW_THIRD_PARTY_PLUGINS` with versioned
  extension contracts (ADR-019).
- Contribution and licensing infrastructure (ADR-020).

**Pending (Workstream 3):**

- `app/billing/` with the `Entitlements` protocol and `CommunityEntitlements`.
- The `AEGIS_EDITION` switch and its documented matrix.
- `tests/test_module_boundaries.py` (AST scan).
- Quota defaults derived from the organization plan.

## 6. Consequences

**Positive:**

- One engine to secure, test, and document.
- Community users can audit everything that runs; contributors know the code
  they touch ships to everyone.
- The hosted pilot cannot silently diverge in grading behavior.

**Negative:**

- Discipline cost: the boundary must be maintained through review, and the
  parity rule rules out "cloud-only improvements" to grading.
- Two configurations to test where settings differ (dispatcher, plugin
  policy); the parity rule makes the expected outcome of both explicit.
- There is no closed-source moat beyond hosted operations. This is accepted:
  the strategy is adoption first, operations as the paid layer.

## 7. Alternatives Considered

| Alternative | Outcome |
|---|---|
| Private cloud repository forked from community | Rejected — drift, duplicated verification semantics, double maintenance. |
| Paid feature flags inside the engine | Rejected — would make verdicts license-dependent and break parity/trust. |
| Two distributions built from one repo (community wheel, cloud wheel) | Deferred — packaging complexity with no benefit while billing stays entitlements-only. |
| Physical `core/` package restructuring | Deferred — violates the no-rewrite fence; import tests give the enforceable boundary at a fraction of the risk. |

## 8. References

- [ADR-017](ADR-017-organizations-tenancy-model.md) — organizations and tenancy.
- [ADR-018](ADR-018-durable-jobs-postgres-dispatcher.md) — durable jobs and the dispatcher interface.
- [ADR-019](ADR-019-third-party-plugin-execution-policy.md) — plugin execution policy.
- [ADR-020](ADR-020-contribution-licensing-policy.md) — contribution and licensing policy.
- [`docs/extension-points.md`](../extension-points.md) — the versioned extension contracts.
