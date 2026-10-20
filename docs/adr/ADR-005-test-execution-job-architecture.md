# ADR-005: Test Execution and Job Architecture

- **Status:** Accepted
- **Date:** 2026-09-10
- **Decision Owners:** Aegis Vuldris Contributors
- **Scope:** Security test execution, assessment runs, asynchronous jobs, concurrency, cancellation, retries, timeouts, persistence, and future worker architecture

---

## 1. Context

Aegis Vuldris is an AI model security testing and evaluation platform.

A single security assessment may execute a small number of tests during development or a very large number of test cases in production.

A test case may involve:

1. Generating or selecting an attack input.
2. Sending a request to a target model.
3. Waiting for the model response.
4. Evaluating the response.
5. Recording evidence.
6. Calculating or updating findings.
7. Applying risk classification.
8. Persisting execution state and results.

A realistic assessment may therefore produce many independent or partially dependent operations.

For example:

```text
Assessment
    |
    +-- Test Case 1
    |      +-- Attack generation
    |      +-- Model request
    |      +-- Evaluation
    |      +-- Evidence
    |
    +-- Test Case 2
    |      +-- Attack generation
    |      +-- Model request
    |      +-- Evaluation
    |      +-- Evidence
    |
    +-- Test Case N
           +-- Attack generation
           +-- Model request
           +-- Evaluation
           +-- Evidence

Executing all of this directly inside an HTTP request would create several problems:

Long-running requests.
HTTP connection timeouts.
Poor cancellation semantics.
Unbounded resource consumption.
Difficult retry behavior.
Difficult progress tracking.
Poor isolation between assessments.
Increased risk that one assessment affects the availability of the entire application.
Difficulty scaling execution independently from the API.
Difficulty recovering incomplete work after process failure.

Aegis Vuldris therefore needs a defined execution architecture before the test engine is implemented.

2. Problem Statement

Aegis Vuldris needs an execution model that:

Supports short and long-running security assessments.
Does not require the frontend to keep an HTTP request open for the entire assessment.
Provides explicit test-run lifecycle states.
Supports cancellation.
Supports bounded concurrency.
Supports timeouts.
Supports controlled retries.
Persists execution state.
Prevents uncontrolled resource consumption.
Preserves evidence and failure information.
Allows individual test cases to fail without necessarily terminating the entire assessment.
Provides a stable API contract.
Can evolve from a simple local execution model into a distributed worker architecture.
Remains suitable for Docker and VPS deployment.
Does not introduce unnecessary infrastructure before it is needed.
3. Decision

Aegis Vuldris will use an asynchronous assessment execution architecture.

The API will create and manage assessment runs, while test execution will occur independently of the initial HTTP request.

The initial implementation will use an in-process asynchronous execution mechanism with an explicit service boundary, while keeping the architecture compatible with a future external worker/job queue.

The execution architecture will therefore have the following conceptual layers:

React Frontend
      |
      | HTTP REST API
      v
FastAPI
      |
      v
Assessment Service
      |
      v
Execution Service
      |
      +----------------------+
      |                      |
      v                      v
Test Engine            Persistence Layer
      |
      +-- Model Adapter
      |
      +-- Evaluator
      |
      +-- Evidence
      |
      +-- Findings

A future production deployment may replace or extend the execution service with dedicated workers:

React
  |
FastAPI API
  |
  +---- PostgreSQL
  |
  +---- Job Queue
           |
           +---- Worker 1
           |
           +---- Worker 2
           |
           +---- Worker N

The API contract will remain stable across this evolution.

4. Execution Boundary

The HTTP API is responsible for:

Authentication.
Authorization.
Request validation.
Creating an assessment run.
Returning the run identifier.
Returning current run state.
Requesting cancellation.
Exposing persisted results.
Exposing execution status.

The execution layer is responsible for:

Selecting test cases.
Scheduling test cases.
Executing model requests.
Evaluating responses.
Recording evidence.
Recording failures.
Applying retries according to policy.
Enforcing timeouts.
Updating run state.
Respecting concurrency limits.
Performing cleanup.

The frontend must never directly control the execution process.

The frontend communicates only through the API.

5. Assessment Run as a First-Class Resource

Every execution will be represented by a persistent assessment run.

A run will have a unique identifier.

Conceptually:

POST /api/v1/assessments/{assessment_id}/runs

returns:

run_id
status
created_at

The frontend can then retrieve the run:

GET /api/v1/runs/{run_id}

and request cancellation:

POST /api/v1/runs/{run_id}/cancel

The exact endpoint structure remains governed by ADR-004.

The important architectural decision is that an assessment execution is a persistent resource rather than a temporary HTTP request.

6. Run Lifecycle

Assessment runs will use explicit lifecycle states.

The initial state model will be:

QUEUED
   |
   v
RUNNING
   |
   +------> COMPLETED
   |
   +------> FAILED
   |
   +------> CANCELLING
              |
              v
          CANCELLED

Additional terminal or operational states may be introduced later if required.

6.1 QUEUED

The run has been accepted but execution has not started.

6.2 RUNNING

At least one test execution is actively being processed.

6.3 CANCELLING

Cancellation has been requested and the execution layer is stopping eligible work.

6.4 COMPLETED

The assessment completed according to its execution policy.

Individual test failures do not automatically make the entire run failed.

6.5 FAILED

The run could not complete because of an unrecoverable execution-level failure.

Examples include:

Internal execution failure.
Persistent infrastructure failure.
Corrupted execution state.
Unrecoverable initialization failure.
6.6 CANCELLED

The user or authorized system actor requested cancellation and the execution layer stopped the run.

7. Test Case State

Individual test cases will also maintain execution state.

The initial conceptual state model is:

PENDING
   |
   v
RUNNING
   |
   +------> PASSED
   |
   +------> FAILED
   |
   +------> TIMED_OUT
   |
   +------> CANCELLED
   |
   +------> SKIPPED

The final persistence model may normalize or extend these states.

A failed test case is an execution result and should not automatically terminate unrelated test cases.

This provides fault isolation within an assessment.

8. Asynchronous Execution

A request that starts an assessment must return without waiting for the complete assessment to finish.

Conceptually:

Client
  |
  | POST start assessment
  v
API
  |
  | create run
  | enqueue/start execution
  |
  +----> return run_id

The client subsequently retrieves state through the API.

This prevents long-running security tests from being coupled to HTTP request lifetime.

9. Progress Reporting

The initial implementation will expose progress through persisted run information.

A run may expose fields such as:

total_tests
pending_tests
running_tests
completed_tests
failed_tests
skipped_tests
progress_percentage

The frontend can poll the run endpoint.

The initial architecture will not require WebSockets or Server-Sent Events.

Future real-time streaming may be added without changing the fundamental execution model.

Possible future mechanisms include:

Server-Sent Events.
WebSockets.
Event streaming.
Push notifications.
10. Concurrency Control

Aegis Vuldris will use explicit concurrency limits.

The system must never assume that unlimited parallel model requests are safe.

Concurrency may be bounded at multiple levels:

Global execution concurrency
        |
        +-- Per assessment
        |
        +-- Per target
        |
        +-- Per provider

The exact limits will be configurable.

Defaults must be conservative.

Concurrency controls exist to protect:

Aegis Vuldris resources.
Target model resources.
External model-provider limits.
Database capacity.
Network capacity.
Assessment isolation.
11. Resource Limits

Every execution path must operate within explicit resource boundaries.

Potential limits include:

Maximum tests per run.
Maximum concurrent tests.
Maximum request size.
Maximum response size.
Maximum execution duration.
Maximum retries.
Maximum evidence size.
Maximum generated attack size.
Maximum assessment duration.
Maximum provider requests.

Limits must be enforced server-side.

Client-provided values must never be trusted merely because they originate from the frontend.

12. Timeouts

Timeouts will be applied at appropriate execution boundaries.

Potential timeout boundaries include:

Assessment timeout
      |
      +-- Test timeout
              |
              +-- Model request timeout
              |
              +-- Evaluation timeout

A timeout must produce an explicit execution result rather than silently hanging.

Timeout behavior must preserve enough information to determine:

Which operation timed out.
Which test was affected.
Whether a retry occurred.
Whether the retry succeeded.
Whether the final result was timed out.

Timeout values must be bounded and configurable.

13. Retry Policy

Retries will be explicit and limited.

Aegis Vuldris must not blindly retry every failure.

Retry decisions will consider whether the failure is potentially transient.

Potentially retryable conditions may include:

Temporary network failure.
Provider rate limiting.
Temporary upstream service failure.

Non-retryable conditions may include:

Invalid request.
Authentication failure.
Authorization failure.
Malformed configuration.
Deterministic validation failure.

The execution layer will record retry attempts.

Conceptually:

Attempt 1
   |
   +-- transient failure
          |
          v
       Attempt 2
          |
          +-- success

Retries must have an upper bound.

Exponential backoff and jitter may be used where appropriate.

14. Idempotency

Execution operations must be designed to avoid unintended duplicate work.

Aegis Vuldris will distinguish between:

API request idempotency.
Execution job identity.
Individual test execution identity.

A retry of an API request must not accidentally create multiple assessment runs when the caller intended to create one.

An execution job must have a stable identity.

Persisted execution state will be used to prevent unsafe duplicate completion or result recording.

15. Cancellation

Authorized users must be able to request cancellation of an active run.

Cancellation is cooperative.

A cancellation request will transition an eligible run to:

CANCELLING

The execution layer will then:

Stop scheduling new work.
Cancel pending asynchronous tasks where possible.
Allow currently executing operations to terminate according to their cancellation and timeout rules.
Persist cancellation-related state.
Transition the run to CANCELLED.

Cancellation must not bypass cleanup or persistence guarantees.

A forced process termination is not considered normal cancellation.

16. Failure Isolation

A single test failure must not automatically terminate the entire assessment.

For example:

Test 1 -> PASS
Test 2 -> FAIL
Test 3 -> PASS
Test 4 -> TIMEOUT
Test 5 -> PASS

The assessment may still complete.

The run-level result will be calculated separately from individual test outcomes.

This distinction is important because security testing intentionally executes adversarial and potentially failure-producing inputs.

17. Persistence

Execution state and results will be persisted in PostgreSQL according to ADR-003.

Persistence will include enough information to reconstruct the state of an assessment.

Conceptual entities include:

Assessment
   |
   +-- AssessmentRun
          |
          +-- TestExecution
                 |
                 +-- ModelInteraction
                 |
                 +-- Evaluation
                 |
                 +-- Evidence
                 |
                 +-- Finding

The final relational schema will be defined during implementation.

Execution state must not depend solely on process memory.

This is important for recovery after:

Application restart.
Container restart.
Worker failure.
Network failure.
Deployment.
18. Transaction Boundaries

Database transactions will be kept reasonably short.

Long-running model requests must not hold database transactions open.

The preferred pattern is:

Create/update state
      |
commit
      |
perform external operation
      |
persist result
      |
commit

External model calls must not occur while holding an unnecessary database transaction.

This reduces:

Lock duration.
Connection consumption.
Deadlock risk.
Database contention.
19. External Model Calls

Model providers are external execution boundaries.

A test execution must therefore treat model calls as untrusted and failure-prone external operations.

Model adapters must provide bounded behavior for:

Connection failures.
Timeouts.
Rate limits.
Invalid responses.
Unexpected response formats.
Authentication failures.
Provider outages.

The execution engine must not contain provider-specific logic.

Provider-specific behavior belongs behind the model adapter boundary established by the overall architecture.

20. Evaluation Execution

Evaluation is considered a separate execution stage.

Conceptually:

Attack
  |
  v
Target Model
  |
  v
Response
  |
  v
Evaluator
  |
  v
Evaluation Result

Evaluation may itself require model calls in the future.

Therefore evaluation must also respect:

Timeouts.
Resource limits.
Retry policy.
Concurrency limits.
Evidence handling.

The evaluator must not be treated as inherently trustworthy merely because it is part of Aegis Vuldris.

21. AI Judge Isolation

When an LLM is used as an evaluator or judge, the judge must remain logically separate from the target model.

Target-model output is untrusted input to the evaluator.

The evaluator must not be allowed to redefine:

Security policy.
Evaluation criteria.
Authorization.
Execution permissions.
Application configuration.

The evaluator produces an assessment signal.

It is not itself the security authority.

22. Evidence Handling

Test execution may produce evidence such as:

Prompt/input.
Target response.
Evaluation result.
Metadata.
Error information.
Timing information.
Model/provider information.

Evidence must be bounded.

Large or sensitive evidence must not be allowed to exhaust:

Memory.
Database storage.
Logs.
API response size.

Evidence persistence must follow the security and privacy requirements defined in the security baseline.

23. Logging and Auditability

Execution events must produce structured logs where useful.

Important execution events may include:

Run created.
Run started.
Test started.
Test completed.
Test failed.
Retry performed.
Timeout occurred.
Cancellation requested.
Run cancelled.
Run completed.
Run failed.

Logs must not unnecessarily contain:

API keys.
Authentication credentials.
Secrets.
Sensitive personal information.
Full sensitive model responses when not required.

Security-sensitive actions must also remain auditable.

24. Background Worker Evolution

The initial implementation will avoid requiring a distributed queue solely for architectural appearance.

Instead, the execution service will expose a clean boundary that can later be moved to workers.

Initial:

FastAPI
  |
  +-- Async Execution Service
          |
          +-- Test Engine

Future:

FastAPI
  |
  +-- Job Queue
          |
          +-- Worker
                 |
                 +-- Test Engine

This allows Aegis Vuldris to start with a simple development environment while retaining a path toward production scaling.

25. Future Queue and Worker Infrastructure

A distributed queue may be introduced when workload requirements justify it.

Candidate open-source technologies may include:

Redis-backed job systems.
Celery.
Other open-source task queues.
PostgreSQL-backed job mechanisms for smaller deployments.

The final technology choice will be documented in a separate architecture decision when required.

This ADR therefore establishes the worker boundary, not a mandatory selection of a particular queue technology.

26. Worker Safety

Future workers must assume that jobs can be malformed, duplicated, delayed, cancelled, or retried.

Workers must therefore enforce:

Authentication where applicable.
Authorization boundaries.
Job validation.
Resource limits.
Timeouts.
Safe retries.
Idempotent result handling.
Controlled concurrency.
Graceful shutdown.
Failure reporting.

Workers must not execute arbitrary commands derived from model output.

27. Graceful Shutdown

The execution layer must support graceful shutdown.

During shutdown:

No new work should be accepted unnecessarily.
Existing work should be given an opportunity to finish or cancel safely.
Execution state must be persisted.
External resources must be released.
Database connections must be closed cleanly.

For future workers, shutdown behavior must distinguish between:

Work completed.
Work safely cancelled.
Work interrupted and requiring recovery.
28. Recovery

The architecture must account for process or worker failure.

A run must not remain permanently marked as RUNNING merely because the process that was executing it disappeared.

Future implementations must provide a recovery mechanism based on persisted state, leases, heartbeats, timestamps, or equivalent mechanisms.

Recovery logic must avoid accidentally executing the same destructive operation multiple times.

29. API Semantics

The API communication architecture defined by ADR-004 remains authoritative.

The execution architecture therefore follows an asynchronous resource-oriented pattern.

Conceptually:

POST /api/v1/assessments/{assessment_id}/runs

        |
        v

202 Accepted

{
    "run_id": "...",
    "status": "QUEUED"
}

The exact response schema will be defined during API implementation.

Clients may then retrieve:

GET /api/v1/runs/{run_id}

and eventually obtain:

status: COMPLETED

along with references to results.

The exact HTTP status codes and schemas remain governed by ADR-004 and the eventual API contract.

30. Security Requirements

The execution architecture must enforce the following security properties:

Only authorized users can start assessments.
Only authorized users can view assessment results.
Only authorized users can cancel assessments.
One user's assessment cannot access another user's data.
Target configuration must be validated.
Execution limits must be enforced server-side.
External requests must obey network security controls.
Secrets must not be exposed to test cases unnecessarily.
Model output must never directly gain application privileges.
Test execution must not permit arbitrary host command execution.
Evidence must be treated as potentially sensitive.
Logs must avoid unnecessary sensitive data.
Resource exhaustion must be actively controlled.

Security boundaries defined in docs/security-boundaries.md remain authoritative.

31. Observability

Execution should expose sufficient operational information to diagnose problems without leaking sensitive data.

Future observability may include:

Structured logs.
Metrics.
Traces.
Run duration.
Test duration.
Provider latency.
Retry counts.
Timeout counts.
Failure rates.
Queue depth.
Worker utilization.

OpenTelemetry-compatible instrumentation may be introduced during the production hardening phase.

32. Testing Strategy

The execution architecture will require tests for:

Unit tests
State transitions.
Retry decisions.
Timeout behavior.
Cancellation behavior.
Concurrency limits.
Progress calculations.
Failure classification.
Integration tests
PostgreSQL persistence.
Assessment lifecycle.
Model adapter execution.
API-to-execution interaction.
Failure tests
Model timeout.
Provider failure.
Database failure.
Worker interruption.
Cancellation during execution.
Duplicate execution attempts.
Security tests
Unauthorized run creation.
Unauthorized run access.
Unauthorized cancellation.
Cross-user result access.
Resource-limit bypass attempts.
Malformed execution requests.
33. Alternatives Considered
33.1 Fully synchronous HTTP execution

Rejected.

Long-running security assessments should not be coupled to HTTP request lifetime.

33.2 Celery/Redis from the first implementation

Not selected as the initial architecture.

A distributed queue adds operational complexity that is not required for the first working implementation.

The architecture instead establishes a worker boundary so that a queue can be introduced later without redesigning the API.

33.3 WebSockets as the primary execution mechanism

Rejected.

WebSockets are unnecessary for starting or managing execution.

REST remains the primary control plane according to ADR-004.

Real-time streaming can be added later.

33.4 Browser-controlled execution

Rejected.

Security test execution must remain server-side.

The browser must not be trusted with execution authority, provider credentials, or sensitive target configuration.

33.5 Database-only job execution

Not selected as the primary initial abstraction.

Although PostgreSQL can support queue-like patterns, execution behavior should remain behind a dedicated execution service so the persistence mechanism can evolve independently.

34. Consequences
Positive consequences
Long-running tests are decoupled from HTTP request lifetime.
Assessment progress can be persisted.
Cancellation can be modeled explicitly.
Test failures can be isolated.
Concurrency can be controlled.
Resource limits can be enforced.
Retries and timeouts become explicit.
Execution can later move to dedicated workers.
API contracts remain stable during scaling.
Docker/VPS deployment remains practical.
PostgreSQL remains the source of durable execution state.
Negative consequences
Execution state becomes more complex than a simple synchronous function call.
Additional lifecycle and persistence logic is required.
Cancellation and recovery require careful implementation.
Testing asynchronous behavior is more difficult.
A future distributed worker architecture introduces operational complexity.

These costs are accepted because reliable asynchronous execution is fundamental to a serious AI security assessment platform.

35. Implementation Constraints

The first implementation must not introduce distributed infrastructure merely for appearance.

The implementation should prioritize:

Correctness.
Security.
Deterministic state management.
Bounded resources.
Testability.
Observability.
Clean abstraction boundaries.
Future scalability.

Infrastructure should be introduced only when the corresponding operational requirement exists.

36. Future Considerations

Future architecture decisions may define:

Distributed job queue technology.
Worker deployment model.
Queue persistence strategy.
Multi-worker coordination.
Distributed locks or leases.
Job priorities.
Scheduled assessments.
Recurring assessments.
Multi-tenant quotas.
Provider-specific rate limits.
Advanced progress streaming.
Distributed tracing.
Horizontal worker scaling.
Worker autoscaling.
Dead-letter queues.
Job replay.
Advanced execution graphs.

These concerns are intentionally not fully decided by this ADR.

37. Related Decisions

This ADR should be read together with:

docs/adr/ADR-001-backend-framework.md
docs/adr/ADR-002-frontend-framework.md
docs/adr/ADR-003-database-architecture.md
docs/adr/ADR-004-api-communication-architecture.md
docs/security-baseline.md
docs/security-boundaries.md
docs/threat-model.md
38. Decision Summary

Aegis Vuldris will execute security assessments asynchronously through a dedicated execution service with persistent assessment-run state, explicit lifecycle states, bounded concurrency, timeouts, controlled retries, cancellation, failure isolation, and durable PostgreSQL state.

The initial implementation will use in-process asynchronous execution to minimize operational complexity while preserving a clean worker boundary. A future distributed queue and worker architecture may be introduced when scale or reliability requirements justify it.

The REST API defined by ADR-004 remains the primary control plane, while execution remains server-side and independently managed from the frontend.
