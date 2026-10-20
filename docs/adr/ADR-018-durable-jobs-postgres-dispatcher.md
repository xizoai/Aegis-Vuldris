# ADR-018: Durable Jobs on Postgres with a Dispatcher Interface

**Status:** Accepted — implementation pending (Workstream 3)
**Date:** 2026-10-17
**Decision Owners:** Aegis Vuldris Maintainers

---

## 1. Decision Summary

The cloud path runs executions as **durable jobs stored in PostgreSQL**,
claimed with `SELECT … FOR UPDATE SKIP LOCKED`, and served by a worker process
(`python -m app.worker`). No Redis, no Celery, no external broker for the
pilot.

The community path keeps today's in-process execution as the default, behind a
new dispatcher interface:

- `JOB_DISPATCHER=inline` — the community default; wraps today's
  `start_execution` exactly.
- `JOB_DISPATCHER=db` — enqueues into the `jobs` table for the worker.

Routes call `dispatch.enqueue_execution(...)` instead of `start_execution`
directly. `JOB_DISPATCHER=inline` must reproduce current behavior exactly — the
existing suite passes without changes to engine tests.

Scheduling (`schedules` table, 5-field UTC cron) rides on the same worker.
Missed ticks run once and advance to the next future occurrence — no backfill
storms.

## 2. Context

Execution today is in-process `asyncio.create_task` inside the API process
(ADR-005). The project documents the consequences honestly in the overview: a
restart loses running executions, and only one worker can execute at a time.
That is an acceptable posture for a single-user community install and not
acceptable for a hosted pilot with multiple customers.

The pilot needs: durability across restarts, concurrent workers, bounded
retries for poison jobs, dead-worker reclaim, cancellation, and recurring
schedules. It does not need: a queue that scales past a handful of workers,
sub-second latency, or a new operational dependency the team would have to
run, secure, and back up.

PostgreSQL is already the system of record. Its transactional guarantees,
`FOR UPDATE SKIP LOCKED` claim semantics, and index-driven due-job scans are
sufficient for the pilot's concurrency target — and enqueueing a job in the
same transaction as the row it describes removes an entire class of
"row exists, job lost" failures.

## 3. Decision Drivers

1. **Durability without new infrastructure.** One less service to operate,
   secure, and restore.
2. **Transactional enqueue.** Job creation and the state it describes commit
   together.
3. **Bounded failure semantics.** Retries, backoff, poison-job handling, and
   dead-worker reclaim must be explicit and testable.
4. **Community parity.** The default path must remain the current in-process
   behavior, untouched.
5. **Scheduling without storms.** Recurring runs must never backfill; the
   system runs a missed tick once and moves on.
6. **A swap door.** If the Postgres backlog model ever stops fitting, the
   dispatcher interface is the single place a queue swap touches.

## 4. Decision

### 4.1 Schema (migration M2)

`jobs`:

- `id`, `kind`, `payload` (JSONB), `organization_id`
- `idempotency_key` (unique — e.g. `execution:{id}`)
- `status` — `queued` / `running` / `succeeded` / `failed` / `cancelled`
- `attempts`, `max_attempts`
- `run_after`, `locked_by`, `locked_at`, `heartbeat_at`, `last_error`
- index on `(status, run_after)`

`schedules`:

- `id`, `project_id`, `organization_id`, `target_id`, `test_ids` (JSONB),
  `cron` (5-field, UTC), `enabled`, `next_run_at`, `created_by`
- index on `(enabled, next_run_at)`

### 4.2 Claim and failure semantics (`services/jobs.py`)

- `enqueue` — idempotent on `idempotency_key`.
- `claim` — `SELECT … FOR UPDATE SKIP LOCKED`; a job is owned by exactly one
  worker while locked.
- `heartbeat` — updates the claim's liveness.
- `complete` / `fail` — `fail` applies bounded retries with exponential
  backoff `min(2**attempt, 300)` seconds; a poison job lands in `failed` with
  an audit entry.
- `requeue_expired` — reclaims jobs whose heartbeat is older than 3× the
  interval (simulated dead worker).

### 4.3 Dispatcher (`services/dispatch.py`)

- `enqueue_execution(...)` with two implementations selected by
  `JOB_DISPATCHER`:
  - `inline` — community default; wraps today's `start_execution`.
  - `db` — writes a `jobs` row for the worker.
- Routes replace direct `start_execution` calls with `enqueue_execution`;
  tests that monkeypatch `app.api.routes.assessments.start_execution` are
  updated **deliberately** as part of the change.

### 4.4 Worker (`app/worker.py`)

- Entry point: `python -m app.worker`; polling loop configured by
  `WORKER_CONCURRENCY` and `WORKER_POLL_SECONDS`.
- Compose gains a `worker` service behind a `cloud` profile, so the community
  Compose stack is unchanged.

### 4.5 Scheduling (`services/scheduling.py`)

- `next_run_at` is computed by an owner-written 5-field parser (no new
  dependency).
- The worker claims due schedules and creates executions through the same
  service path as manual runs.
- Missed ticks run once and advance to the next future occurrence — no
  backfill storms.
- Audit actions: `schedule.created`, `schedule.ran`, `schedule.failed`.

### 4.6 Cancellation

Cancellation reuses the engine's existing cancel path; job status and
execution status transition together. There is no second cancellation
mechanism.

## 5. Why Postgres, Not Redis/Celery

| Criterion | Postgres jobs | Redis/Celery |
|---|---|---|
| New infrastructure | none | broker + result backend to operate, secure, back up |
| Transactional enqueue with the described row | yes (same transaction) | no (dual-write risk) |
| Claim exclusivity | `FOR UPDATE SKIP LOCKED` | provider-specific semantics |
| Scheduling | same tables, same worker | additional beat process |
| Pilot concurrency | sufficient | more than needed |

The risk register is explicit about the failure mode: sustained backlog or more
than a handful of workers is the trigger to revisit this decision with a new
ADR. The dispatcher interface is the single touch point for a swap.

## 6. Implementation Status

**Not started** (Workstream 3). Acceptance criteria to satisfy:

- [ ] Killing a worker mid-execution results in the job being reclaimed and
  completed by another worker (simulated in
  `tests/services/test_jobs.py`; the recovery drill is documented in
  `docs/deployment.md`).
- [ ] `JOB_DISPATCHER=inline` reproduces current behavior exactly — the full
  existing suite passes without changes to engine tests.
- [ ] Claim exclusivity under concurrency, idempotent replay, bounded
  retries/backoff, heartbeat-expiry requeue, cancellation, and schedule
  due/disabled/skip-not-backfill are all covered by tests.
- [ ] One end-to-end test runs an execution through the `db` dispatcher and
  the worker loop in-process.

## 7. Consequences

**Positive:**

- Executions survive API restarts; multiple workers can drain a backlog.
- Enqueue and its describing row commit atomically — no lost-job window.
- One fewer service for the operator; backups already cover job state.
- Community behavior is untouched (inline default).

**Negative:**

- Job state lives in the primary database; heavy scheduling load contends
  with transactional traffic (accepted at pilot scale).
- Postgres-specific locking semantics (`SKIP LOCKED`) are now load-bearing;
  tests must simulate concurrency, not only sequence.
- Scheduling correctness (cron parsing, DST-free UTC arithmetic) is our own
  code, so its edge cases are our tests to write.

## 8. Alternatives Considered

| Alternative | Outcome |
|---|---|
| Redis + Celery | Rejected — new operational dependency; dual-write enqueue; oversized for pilot concurrency. |
| APScheduler / arq / RQ | Rejected — still an extra process/dependency or weaker durability guarantees than the jobs table. |
| Managed cloud queue (SQS etc.) | Rejected — contradicts the self-hostable, zero-cost-infrastructure preference; cloud-only divergence for a core execution concern. |
| Keep in-process only (no jobs) | Rejected — loses runs on restart and cannot schedule; the pilot requires durability. |
| External scheduler (cron) invoking the CLI | Rejected — no claim exclusivity, no idempotency, no audit coupling to executions. |

## 9. References

- [ADR-005](ADR-005-test-execution-job-architecture.md) — in-process execution; remains the community default. This ADR extends it with a dispatcher seam rather than replacing it.
- [ADR-016](ADR-016-open-core-edition-boundary.md) — `AEGIS_EDITION` selects the dispatcher default.
- [ADR-017](ADR-017-organizations-tenancy-model.md) — jobs carry `organization_id` for quota checks without joins.
