# ADR-017: Organizations and Tenancy Model

**Status:** Accepted — implementation pending (Workstream 3)
**Date:** 2026-10-17
**Decision Owners:** Aegis Vuldris Maintainers

---

## 1. Decision Summary

Aegis Vuldris adds a tenancy layer that is invisible to community installs:

- New `organizations` and `organization_memberships` tables with roles
  `owner`, `admin`, `member`.
- `projects.organization_id` ships **nullable** (migration M1) with a
  documented backfill; a separate migration (M1b) sets `NOT NULL` only once a
  database has zero orphan projects. The pilot gate requires that state.
- `executions.organization_id` is denormalized so workers and quota checks
  never need joins.
- Existing personal use keeps working unchanged: every user has a personal
  organization, and community API behavior is byte-for-byte the same.
- Cross-organization requests return **404, never 403** — a 403 would leak the
  existence of another tenant's resources.
- Isolation is proven by a route-enumerated sweep test: a new route without
  isolation logic fails the suite.

## 2. Context

Today identity is project-scoped: `User` plus `ProjectMembership` with roles
`super_admin`, `admin`, `user`, `viewer`. Projects have a nullable `owner_id`
and an explicit membership list. There is no organization anywhere in the schema
or APIs.

A hosted pilot needs tenant isolation: multiple customers in one deployment,
with asset separation strong enough to be a contractual claim. In the P3 risk
register, a tenancy bug class is rated the highest severity item — "any
cross-org leak: pilot halts, incident process runs."

At the same time, the community install must not notice the change. A
self-hoster with one user and personal projects should see no new concepts, no
new required fields, and no behavior difference in any existing test.

## 3. Decision Drivers

1. **Isolation above all.** Cross-tenant reads/writes are the highest-risk bug
   class in the hosted path.
2. **Zero behavior change for community.** Existing tests are the contract.
3. **Incremental migration.** A big-bang `NOT NULL` migration on existing
   databases would fail on rows with unresolved ownership; the nullable-org
   path makes each step verifiable.
4. **Auditability of the backfill.** Operators must be able to see and resolve
   what did not attach automatically.
5. **Testability.** Isolation must be provable by a suite that fails when a
   route is missed, not by manual review.
6. **Cheap checks at scale.** Denormalized `organization_id` on executions
   lets workers and quotas enforce org boundaries without joining through
   projects.

## 4. Decision

### 4.1 Schema (migration M1)

- `organizations` — id, name, timestamps.
- `organization_memberships` — user id, organization id, `OrganizationRole`
  (`owner` | `admin` | `member`), timestamps.
- `projects.organization_id` — nullable, indexed.
- `executions.organization_id` — nullable, indexed, denormalized
  (copied from the project at creation).

Nullable in M1 is deliberate: it mirrors the existing nullable `owner_id` and
keeps the migration safe on real data.

### 4.2 Backfill rules

1. One organization per **distinct `projects.owner_id`**; the organization name
   derives from the owner's email. The owner joins as `OrganizationRole.owner`;
   all their projects attach.
2. Projects with `owner_id IS NULL` fall back to the owner implied by their
   **earliest `admin`-role membership**.
3. Anything still unresolvable stays `organization_id NULL` under the current
   membership rules until the operator runs `aegis org adopt-orphans` (new CLI
   command), which reports and resolves orphans.

### 4.3 M1b: the NOT NULL step is separate on purpose

Once a database has zero NULL-org projects (checked by command + test), the
follow-up migration M1b sets `projects.organization_id NOT NULL`. The migration
pre-checks for NULLs and **fails loudly** otherwise. This gives the pilot gate
(§6.7) a single, unambiguous condition: `aegis org adopt-orphans` reports zero
orphans.

### 4.4 Access semantics

- `backend/app/services/organizations.py` (new): `create_organization`,
  `ensure_organization_access(session, user, organization_id, minimum_role)`,
  `list_organizations_for_user`.
- `ensure_project_access` gains an organization short-circuit: an org
  `owner`/`admin` implies project admin; a member's project role still governs.
- Personal-organization behavior is identical to today's behavior, so the
  community API does not change and existing authorization tests pass
  unchanged.

### 4.5 API surface

- `backend/app/api/routes/organizations.py` (new, registered in
  `api/router.py`): create / list / get.
- Project creation accepts an optional `organization_id`, defaulting to the
  caller's personal organization.
- Frontend: pilot scope is API-first for org administration. An org
  switcher/settings page is added only when a concrete deployment requires it.

### 4.6 Isolation contract (proven, not promised)

- Cross-org resource ids return **404** (never 403), to avoid existence leaks.
- List endpoints filter by the caller's organizations.
- Report downloads and exports are included in the sweep.
- `tests/api/test_tenant_isolation.py` enumerates every id-taking route in
  `api/routes/`; a new route without isolation handling fails the suite.
- Membership changes follow existing guardrail patterns, including a
  last-owner guardrail mirroring project memberships.

## 5. Migration Register

| ID | Contents | Backfill | Downgrade |
|---|---|---|---|
| M1 | `organizations`, `organization_memberships` (+enum), `projects.organization_id` (nullable, indexed), `executions.organization_id` (nullable, indexed) | one org per distinct `projects.owner_id`; fallback to earliest `admin` membership; unresolved rows stay NULL until `aegis org adopt-orphans` | drops columns/tables; backfilled data is disposable |
| M1b | `projects.organization_id NOT NULL` | pre-check: zero NULLs (fails loudly otherwise) | drop NOT NULL |

## 6. Implementation Status

**Not started.** This ADR records the accepted decision so implementation can
follow the migration order above. Acceptance for the pilot gate:

- [ ] Route-enumerated cross-org sweep green (`tests/api/test_tenant_isolation.py`).
- [ ] `ensure_project_access` semantics unchanged for every existing test.
- [ ] `aegis org adopt-orphans` reports zero orphans; M1b applied.

## 7. Consequences

**Positive:**

- Tenant isolation that is testable by construction (route sweep) rather than
  by spot checks.
- Community installs see no new required concepts; personal organizations are
  automatic.
- Denormalized `executions.organization_id` keeps worker and quota checks O(1).

**Negative:**

- Two ownership notions coexist during the transition (`owner_id` and
  `organization_id`); documentation and commands must be explicit about which
  one is authoritative at each step.
- The nullable window is a real state: between M1 and M1b, code paths must be
  correct for both NULL and non-NULL rows.

## 8. Alternatives Considered

| Alternative | Outcome |
|---|---|
| `projects.organization_id NOT NULL` in M1 | Rejected — would fail on unresolved ownership rows; the pilot gate wants one explicit condition (M1b), not a fragile big-bang. |
| Replace `owner_id` with `organization_id` outright | Rejected — breaks community semantics and existing tests; the plan's zero-behavior-change rule forbids it. |
| Organization per project | Rejected — does not match the pilot's per-customer org model; makes membership meaningless. |
| Database row-level security as the enforcement mechanism | Not adopted in this window. Isolation is enforced in the service layer and proven by the route sweep. If RLS is pursued later, it requires its own decision. |

## 9. References

- [ADR-006](ADR-006-authentication-authorization-architecture.md) — authentication and authorization.
- [ADR-016](ADR-016-open-core-edition-boundary.md) — edition boundary and quota defaults.
- [ADR-018](ADR-018-durable-jobs-postgres-dispatcher.md) — jobs carry `organization_id` for the same reasons.
