# Aegis Vuldris Architecture

This document describes the **implemented** architecture. It replaces the
earlier stub, which described components in the future tense. Decisions and
their rationale live in [`docs/adr/`](adr/); the honest capability boundaries
live in [`OVERVIEW.md`](OVERVIEW.md) sections 8–9. Every statement here is
checkable against the code.

## 1. System overview

One backend, one single-page app, one database. The default (community)
deployment has no message broker, no cache, and no external services:

```
┌──────────────┐         ┌─────────────────────────────┐
│  Operator    │         │  React SPA (frontend/)      │
│  (browser)   │<───────>│  holds no security decisions│
└──────────────┘  HTTPS  └─────────────────────────────┘
                  JSON over /api/v1
┌───────────────────────────────────────────────────────┐
│  FastAPI backend (backend/app/)                       │
│  api/routes  →  services  →  db/models                │
│    ├── execution engine   (in-process asyncio, default)│
│    ├── adapters + SSRF network policy → target endpoints│
│    ├── grading / finding classifier / scoring         │
│    └── evidence / findings / reports / verification   │
└───────────────────────────────────────────────────────┘
            │  SQLAlchemy (psycopg)
            v
       ┌──────────────┐
       │ PostgreSQL 16│   the only infrastructure dependency
       └──────────────┘
```

## 2. Components

### Frontend — `frontend/`

React + TypeScript, built by Vite. `src/App.tsx` defines the routes:
`/login`, `/register`, then protected routes `/projects`, `/projects/:projectId`,
`/targets`, `/targets/:targetId` under a shared layout. `src/auth/` holds the
JWT context; `src/api/client.ts` is the single fetch wrapper and
`src/api/types.ts` mirrors the API schemas. The UI enforces nothing — every
authorization, validation, and grading decision is made by the backend.

### API — `backend/app/api/`

FastAPI, versioned under `/api/v1/`, one router per domain: `auth`, `projects`,
`memberships`, `targets`, `credentials`, `assessments` (executions, findings,
evidence, reports, verifications), `patches`, `system` (health, readiness,
system info). Requests validate through Pydantic schemas and use standardized
error codes (for example `TARGET_NOT_FOUND`, `EMAIL_ALREADY_REGISTERED`).
Database access is a synchronous SQLAlchemy `Session` per request
(`app/db/session.py`). Rate limiting is an in-process sliding window
(per-IP for login and registration).

### Services — `backend/app/services/`

The domain layer; route handlers stay thin. The load-bearing pieces:

| Area | Services |
|---|---|
| Identity & access | `auth`, `memberships`, `projects` |
| Targets | `targets` (validation), `credentials` (Fernet-encrypted, write-only, rotate/revoke) |
| Library | `test_cases`, `seed_tests`, attack plugin loading |
| Execution | `execution_engine` (async, in-process), `bulk_execution` (suite runs) |
| Grading | `grading` (deterministic keyword/regex), `finding_classifier` (refusal/property suppression), `confirmation` (two-stage resolution: judge verdicts, human triage, derived results), judge-target path |
| Scoring & output | `risk_scoring`, `severity_scorer`, `evidence`, `report_generation` (+ discovered exporters) |
| Remediation | `remediation`, `patch_generation`, `verification` (rerun-only `verified`), `regression` |
| Platform | `audit`, `redaction`, `retention`, `demo`, `extensions` (plugin loader) |

The execution engine runs as an `asyncio` task inside the API process — the
community default. A durable DB-backed worker is a recorded, unimplemented
decision (see ADR-018); its consequences today are documented in
[`OVERVIEW.md`](OVERVIEW.md) section 8.

### Adapters — `backend/app/adapters/`

One normalized contract (`ModelRequest` / `ModelResponse` in
`app/models/model.py`) over three providers: `openai_compatible`, `ollama`,
`custom_rest`. The registry resolves the adapter for a target's provider; the
base adapter applies the SSRF network policy (`app/security/network.py`)
before any outbound call. Third parties can substitute an adapter for an
existing provider through the extension contract
([`extension-points.md`](extension-points.md)).

### Data — `backend/app/db/`, `backend/app/models/`, `alembic/`

PostgreSQL 16 via SQLAlchemy (synchronous sessions, `expire_on_commit=False`)
with Alembic migrations. `alembic check` runs in CI: a model change without a
migration fails the build. Entities:

| Entity | Represents |
|---|---|
| `User`, `ProjectMembership` | Accounts and project-scoped roles (`super_admin`/`admin`/`user`/`viewer`) |
| `Project` | The container for one assessed system |
| `Target`, `TargetCredential` | Model endpoints and their encrypted credentials |
| `SecurityTest` | A library case (schema in [`test-cases.md`](test-cases.md)) |
| `Execution`, `ExecutionStep` | A run of one case against one target; multi-turn steps |
| `Finding`, `Evidence` | Graded results and the exact request/response behind them |
| `Report` | Generated artifacts (JSON, Markdown, exporters) |
| `PatchProposal` | Candidate remediation diffs — drafts that change no fix state |
| `AuditLog` | Structured, action-coded audit events |

### CLI — `backend/app/cli/`

The `aegis` console script (`doctor`, `run`, `verify`, `export`, `seed-tests`,
`clear-history`, `retention prune`, `demo`) drives the same services as the
API. Its exit-code contract — 0 success, 2 a configured gate fired, 4
operational error, 1 usage — is documented in
[`ci-integration.md`](ci-integration.md) and shared with the GitHub Action.

## 3. The execution pipeline

1. **Create.** A test and target are chosen (UI, CLI, or API); an `Execution`
   row is created as pending.
2. **Resolve.** The engine resolves the target's adapter through the registry,
   resolves credentials in-process only, and builds the normalized request —
   multi-turn cases replay their conversation.
3. **Call.** The outbound request passes the SSRF policy, then the provider
   adapter. Errors map to normalized provider errors; the execution fails —
   which is *not* a security verdict.
4. **Grade.** Deterministic keyword/regex grading runs with refusal and
   property suppression; every match is a **candidate** finding. Confirmation
   (`services/confirmation.py`) then resolves candidates: `judge_model` cases
   are graded by the project's judge target through the same adapter path (a
   model never judges its own answers), deterministic cases with a judge
   configured get a per-turn strict-JSON verdict, human triage writes the same
   fields, and `grading.confirm: false` lets a decisive test confirm its own
   match. Only confirmed findings make the execution `fail`; all-dismissed is
   `pass`; any candidate left is `needs_review`; grading that cannot run is
   `inconclusive` — never `pass`.
5. **Record.** Findings carry severity, confirmation state and source,
   evidence: the exact exchange (or the external reference) that produced
   them, and each turn's request/response as `ExecutionStep` rows (served
   back redacted on read).
6. **Verify.** Fix state is human-only (`fixed`); `verified` is reachable only
   through a passed rerun in `services/verification.py`. Patch proposals,
   report generation, and model output can never move a finding's state.

## 4. Security boundaries

- **Authentication** — Argon2id password hashing; JWT bearer sessions
  (30-minute expiry); registration/login rate limits.
- **Authorization** — project-scoped RBAC with membership guardrails; the
  backend is the authoritative boundary on every request, and denied attempts
  are recorded as audit events. (The future cross-tenant rule for the hosted
  path — 404 instead of 403, to avoid existence leaks — is recorded in
  ADR-017.)
- **Credentials** — encrypted at rest (Fernet, key derived via PBKDF2 from
  `SECRET_KEY`), write-only through the API, decrypted only in-process on the
  execution path, and covered by the redaction service for logs.
- **Egress** — every outbound call passes `app/security/network.py`: scheme
  allowlist, private/link-local/metadata address blocking, DNS-rebinding
  defense, and redirect handling. `ALLOW_LOCAL_TARGETS=true` is a documented
  local-development override only.
- **Honesty invariants** — see the P2/P3 rules: `INCONCLUSIVE` and
  `NEEDS_REVIEW` are not passes, demo data is marked `[DEMO]`, no phone-home
  telemetry exists in the codebase, and unsupported claims are treated as bugs.

Detail: [`security-boundaries.md`](security-boundaries.md),
[`threat-model.md`](threat-model.md), [`ssrf-protection.md`](ssrf-protection.md).

## 5. Deployment topologies

- **Community** — Docker Compose: PostgreSQL, a one-shot `migrate` service,
  backend, frontend. Single host; the database is not published.
- **Production** — the hardened Compose stack: non-root, read-only
  filesystems, dropped capabilities, internal networks, TLS at a reverse
  proxy. See [`deployment.md`](deployment.md).
- **Cloud (planned, not implemented)** — same image, different environment:
  durable jobs, organizations/tenancy, quotas and edition defaults. Recorded
  as ADR-016, ADR-017, and ADR-018.

## 6. Quality gates

Backend: `ruff check` + format check, `pyright` (0 errors), the full pytest
suite against a real PostgreSQL, `alembic check`, and a wheel-packaging test
that installs the built wheel into a throwaway venv and runs the console
script. Frontend: `oxlint`, `tsc`, vitest, production build. Docs:
`docs/configuration.md` is generated from `Settings` and `.env.example` and a
test fails on drift. CI runs all of these plus the compose smoke walkthrough;
the release workflow publishes images and a GitHub Release from tags (see
[`release-process.md`](release-process.md)).

## 7. Extension points

Four versioned contracts load through one entry-point loader
(`app/services/extensions.py`): `aegis.graders`, `aegis.report_exporters`,
`aegis.attack_plugins` (attacks stay YAML data), and `aegis.adapters`.
Third-party plugins are enabled in community installs and disabled in the
hosted pilot by policy (`ALLOW_THIRD_PARTY_PLUGINS`). The operating reference
is [`extension-points.md`](extension-points.md); the policy is ADR-019.

## 8. Where decisions are recorded

- [`docs/adr/`](adr/) — the 20 architecture decision records, from framework
  choices through the open-core edition boundary.
- [`OVERVIEW.md`](OVERVIEW.md) section 6 — the load-bearing decisions at a
  glance.
