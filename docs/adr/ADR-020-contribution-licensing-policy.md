# ADR-020: Contribution and Licensing Policy

**Status:** Accepted — implemented
**Date:** 2026-10-17
**Decision Owners:** Aegis Vuldris Maintainers

---

## 1. Decision Summary

- **License:** Apache-2.0 stays. Everything in the repository, including all
  additions in this window, is inbound = outbound Apache-2.0. No
  source-available licenses, no per-edition license split, no dual licensing.
- **Contributions:** the Developer Certificate of Origin (DCO 1.1) — a
  `Signed-off-by` trailer — instead of a Contributor License Agreement.
- **Process:** a published contribution guide, code of conduct, issue and pull
  request templates, and a private security-reporting path.
- **Supply chain:** Dependabot updates plus a dependency-review workflow on
  pull requests that touch dependencies.
- **Relicensing guard:** any future relicensing requires legal review first.
  Because the project takes DCO (not CLA) sign-offs, relicensing also requires
  contributor consent — an accepted trade-off, see §5.

## 2. Context

Aegis Vuldris is moving from a single-maintainer project to an open-source project
that accepts outside contributions and plans a hosted pilot. That requires
answers to three questions that are cheap to settle now and expensive to
retrofit:

1. **Under what license do inbound contributions arrive?** Without an explicit
   policy, provenance is ambiguous and a later relicensing or legal review
   becomes archaeology.
2. **What friction does a contributor accept?** Two standard instruments
   exist: a CLA (assigns or licenses rights to an entity) and a DCO (a signed
   statement that the contributor has the right to submit the code under the
   project license). CLAs require an entity capable of administering them and
   add a signature step for every contributor; DCOs are lightweight and
   verifiable per commit.
3. **How do security reports and dependencies flow?** A security testing tool
   that mishandles its own vulnerability reports or dependency updates is
   undermining its own subject matter.

The P3 risk register names the constraint directly: license is Apache-2.0 and
contributions go through DCO from day one; a required CLA or a relicensing is
a legal-review trigger, not a routine decision.

## 3. Decision Drivers

1. **Low friction.** Casual contributors should be able to send a fix with
   `git commit -s`, nothing more.
2. **Provenance.** Every contribution must carry an explicit statement that
   its author had the right to submit it.
3. **No legal machinery the project does not have.** There is no entity
   administering CLAs at this stage; pretending otherwise would produce a
   policy that is not actually enforceable.
4. **License stability as an adoption promise.** Downstream users (and
   companies evaluating Aegis Vuldris) need the license to be boring and stable.
5. **Supply-chain hygiene.** Dependency changes are reviewed like code.

## 4. Decision

### 4.1 Licensing

- Apache License 2.0 for the whole repository (`LICENSE`).
- Inbound = outbound: contributions are accepted under Apache-2.0.
- No license split between community and cloud configurations (ADR-016); the
  hosted pilot changes operations, not licensing.

### 4.2 DCO instead of CLA

- Every commit must carry a `Signed-off-by` trailer certifying the Developer
  Certificate of Origin 1.1 (`git commit -s`).
- No CLA is required, now or in this window.
- Enforcement in this window is review-time (the contributing guide states the
  requirement; maintainers check it during review). Adding a DCO status check
  later is a tooling change, not a policy change.

### 4.3 Contribution process

- `CONTRIBUTING.md` — setup, the project's definition of done (lint, format,
  type check, full test suite, migrations check, docs, changelog), DCO
  instructions, and where to ask questions.
- `CODE_OF_CONDUCT.md` — adopted and enforced by the maintainers.
- Templates — bug reports request reproduction steps and the relevant
  environment; feature requests state the problem before the solution.
- `docs/branch-protection.md` describes the merge requirements (CI green,
  review) already configured.

### 4.4 Security reports

- Vulnerability reports go through `SECURITY.md` (GitHub private
  vulnerability reporting), never public issues.
- This ADR does not change the report-handling process; it records that a
  private path is part of the contribution surface from the start.

### 4.5 Supply chain

- `.github/dependabot.yml` — scheduled dependency updates.
- `.github/workflows/dependency-review.yml` — dependency changes in a pull
  request are reviewed for advisories and license compatibility before merge.

### 4.6 Relicensing guard

Any move away from Apache-2.0 requires legal review and, under DCO, the
consent of the contributors whose code is affected. This is accepted
deliberately: the project is not reserving a unilateral path to relicense.

## 5. Consequences

**Positive:**

- Contributors need no signature step beyond `-s`; the barrier to a drive-by
  fix is minimal.
- Provenance is explicit per commit.
- License stability is a documented promise, not an assumption.
- Private security reporting exists from the start.

**Negative:**

- DCO sign-offs (unlike copyright assignment) mean a future relicensing needs
  contributor consent — the intended trade-off for low friction and no legal
  administration.
- Review-time DCO enforcement is weaker than an automated check; a missing
  sign-off can slip through review until a bot is added.
- Two more workflows to keep green (dependency review runs on PRs).

## 6. Implementation Status

**Shipped** (P3 §4.5, commit `7011ec7`):

| Artifact | Purpose |
|---|---|
| `CONTRIBUTING.md` | Setup, quality gates, DCO instructions |
| `CODE_OF_CONDUCT.md` | Conduct expectations and enforcement |
| `SECURITY.md` | Private vulnerability reporting |
| `.github/pull_request_template.md` | PR checklist |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Bug reports with reproduction and environment |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | Feature requests |
| `.github/ISSUE_TEMPLATE/config.yml` | Issue template routing |
| `.github/dependabot.yml` | Dependency updates |
| `.github/workflows/dependency-review.yml` | Dependency review on PRs |

## 7. Alternatives Considered

| Alternative | Outcome |
|---|---|
| Contributor License Agreement (CLA) | Rejected — signature friction on every contributor; requires an entity to administer; no requirement in this window justifies it. |
| No formal contribution policy | Rejected — ambiguous provenance and no conduct or security-reporting path for a security tool accepting external code. |
| Copyright assignment to a foundation or company | Rejected at this stage — no entity, no need; DCO gives adequate provenance. |
| Copyleft (e.g., AGPL) or source-available licensing | Rejected — breaks the adoption promise and, for an early-stage security tool, the trust that comes with a permissive license. |

## 8. References

- [`CONTRIBUTING.md`](../../CONTRIBUTING.md) — the operating guide.
- [`SECURITY.md`](../../SECURITY.md) — vulnerability reporting.
- [`CODE_OF_CONDUCT.md`](../../CODE_OF_CONDUCT.md).
- [ADR-016](ADR-016-open-core-edition-boundary.md) — no license split between editions.
