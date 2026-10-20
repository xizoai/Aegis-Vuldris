# ADR-004: API and Communication Architecture

## Status

Accepted

## Date

2026-09-10

## Context

Aegis Vuldris requires a stable communication architecture between its frontend, backend, model adapters, test execution components, evaluation engine, and future background workers.

The architecture must support:

- clear API boundaries
- versioning
- predictable request and response formats
- authentication and authorization
- validation
- error handling
- asynchronous test execution
- long-running model assessments
- future real-time progress updates
- rate limiting
- auditability
- backward compatibility
- secure communication between components

Because Aegis Vuldris is a security testing platform, the API itself is part of the security boundary and must not trust client-provided data.

## Decision

Aegis Vuldris will use a RESTful HTTP API built with FastAPI as the primary communication interface between the React frontend and backend.

The public API will be versioned under:

/api/v1/

The backend remains the authoritative security boundary.

The frontend must never be trusted to enforce authentication, authorization, validation, or other security controls.

## API Architecture

The communication flow will initially follow:

React Frontend
       |
       | HTTPS / HTTP during local development
       v
FastAPI API
       |
       +--> Application Services
       |
       +--> Domain Logic
       |
       +--> Test Execution
       |
       +--> Evaluation Engine
       |
       +--> Model Adapters
       |
       +--> Persistence Layer

Future background execution may introduce:

FastAPI API
     |
     v
Job / Worker System
     |
     +--> Test Execution
     +--> Model Adapters
     +--> Evaluation

## API Versioning

All externally exposed API endpoints will use an explicit version prefix.

Initial version:

/api/v1/

Breaking API changes will require a new API version.

Non-breaking changes should remain compatible with existing clients whenever practical.

Versioning decisions must be documented when compatibility implications exist.

## Resource-Oriented Design

The API will expose resources rather than tightly coupling endpoints to frontend screens.

Potential resources include:

- users
- projects
- targets
- model configurations
- test suites
- test runs
- findings
- evaluations
- reports
- audit events

Example endpoint structure:

GET    /api/v1/targets
POST   /api/v1/targets
GET    /api/v1/targets/{target_id}
PATCH  /api/v1/targets/{target_id}
DELETE /api/v1/targets/{target_id}

Exact resources and endpoints will be defined as implementation progresses.

## Request Validation

All external API input must be validated before reaching application logic.

FastAPI/Pydantic schemas will be used for request and response validation.

Validation must cover:

- required fields
- field types
- allowed values
- string lengths
- numeric ranges
- collection sizes
- identifiers
- URLs
- structured objects

Validation must not rely on frontend behavior.

Untrusted input must be treated as hostile until validated.

## Response Schemas

API responses should use explicit schemas.

Responses should not expose raw database models.

Response schemas provide:

- stable contracts
- controlled data exposure
- serialization guarantees
- easier API evolution
- protection against accidental sensitive-field disclosure

## Error Handling

Aegis Vuldris will use a consistent structured error format.

Errors should provide enough information for clients to handle failures without exposing internal implementation details.

Conceptually:

{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The requested resource was not found.",
    "request_id": "..."
  }
}

Internal stack traces, database details, secrets, model credentials, and infrastructure information must not be returned to clients.

Error codes should remain stable where client behavior depends on them.

## HTTP Status Codes

The API will use standard HTTP semantics.

Examples:

- 200 successful request
- 201 resource created
- 202 asynchronous operation accepted
- 204 successful request with no response body
- 400 malformed request
- 401 authentication required or failed
- 403 authorization denied
- 404 resource not found
- 409 resource conflict
- 422 validation failure
- 429 rate limit exceeded
- 500 unexpected server error
- 503 temporary service unavailability

Exact status-code behavior will be defined per endpoint.

## Authentication Boundary

Authentication will be enforced by the backend.

The frontend may manage authentication state and credentials according to the selected authentication mechanism, but it must never be considered an authority for identity.

Every protected API request must be authenticated by the backend.

Authentication credentials and tokens must:

- never be logged
- never be returned unnecessarily
- never be embedded in URLs
- be handled according to the security baseline
- be protected against accidental exposure

The final authentication mechanism will be recorded in a separate architecture decision if it requires significant architectural detail.

## Authorization Boundary

Authentication establishes identity.

Authorization determines whether that identity may perform an operation.

Authorization must be enforced server-side for every protected operation.

The backend must verify access to resources such as:

- projects
- targets
- test configurations
- test runs
- findings
- reports
- audit information

The API must not rely on client-supplied ownership identifiers.

Object-level authorization must be checked using trusted server-side context.

## Idempotency

Operations that may be retried or triggered multiple times must be designed carefully to avoid unintended duplicate effects.

Where appropriate, APIs that create long-running operations may support idempotency keys.

Idempotency requirements will be defined per operation based on its side effects.

## Pagination

Collection endpoints will support pagination when result sets can become large.

Pagination should be predictable and bounded.

Clients must not be able to request unlimited result sizes.

The API should define consistent pagination parameters and response metadata.

## Filtering and Sorting

Filtering and sorting will be explicitly allowlisted.

Clients must not be allowed to inject arbitrary database expressions through API query parameters.

Only supported fields and operations should be accepted.

## Asynchronous Test Execution

AI security assessments may take significant time because they can involve:

- multiple model requests
- attack generation
- multi-turn interactions
- evaluation
- evidence collection
- report generation

Long-running operations must not block an HTTP request unnecessarily.

The initial API will support asynchronous execution semantics.

A typical workflow may be:

POST /api/v1/test-runs
        |
        v
202 Accepted
        |
        v
test_run_id
        |
        v
GET /api/v1/test-runs/{test_run_id}

The exact worker implementation will be determined separately.

## Job State

Long-running operations should expose explicit lifecycle states.

Potential states include:

- queued
- running
- completed
- failed
- cancelled

State transitions must be validated by the backend.

Clients must not be able to arbitrarily change internal execution state.

## Real-Time Progress

REST polling will be the initial mechanism for retrieving test-run status.

If real-time progress becomes necessary, Aegis Vuldris may introduce:

- Server-Sent Events
- WebSockets

Such mechanisms will be added only when justified by product requirements.

They must use the same authentication and authorization model as the primary API.

## OpenAPI

FastAPI's OpenAPI support will be used as the authoritative machine-readable API description.

The API specification should be generated from the backend implementation rather than maintained separately whenever practical.

OpenAPI documentation must not accidentally expose:

- secrets
- internal credentials
- private infrastructure details
- sensitive implementation information

Development and production documentation exposure may differ.

## Rate Limiting

The API will enforce rate limits appropriate to the operation.

Higher-cost operations such as AI model testing may require stricter limits than inexpensive read operations.

Rate limiting may be applied by:

- authenticated user
- project
- target
- IP address
- operation type

The exact mechanism will be selected during implementation.

## Request Size Limits

API requests must have reasonable size limits.

Large AI prompts, test payloads, uploaded content, and evidence must not be allowed to consume unlimited memory or processing resources.

Endpoints handling large content will define explicit limits and may use object storage or streaming mechanisms in future versions.

## Request Correlation

Each API request should have a correlation/request identifier.

The identifier should be:

- generated or validated by the backend
- included in relevant logs
- returned in appropriate error responses
- useful for troubleshooting and audit correlation

Client-provided identifiers must not be blindly trusted.

## Auditability

Security-sensitive API operations must produce appropriate audit events.

Examples include:

- authentication events
- authorization failures
- target creation or modification
- credential configuration changes
- test execution
- test cancellation
- finding changes
- report generation
- administrative actions

Audit logs must avoid storing secrets or unnecessary sensitive content.

## Security Headers and Transport

Production API communication will use HTTPS.

The backend should implement appropriate security headers and transport protections.

Local development may use HTTP where TLS termination is not required.

TLS termination may occur at a reverse proxy or ingress layer in production.

## Internal Communication

Internal components should communicate through well-defined application interfaces rather than directly manipulating another component's internal state.

The API layer should not directly invoke database implementation details.

Model adapters should expose a stable internal interface to the test engine.

Future worker systems should communicate through explicit job contracts.

## External Model Providers

Model adapters may communicate with external AI providers.

External provider communication must be isolated behind the model adapter abstraction.

The rest of Aegis Vuldris must not depend on provider-specific request formats.

Provider credentials must remain isolated from API responses, logs, reports, and user-visible data unless explicitly required.

## Model Adapter Boundary

The API must not directly implement provider-specific model communication.

Instead:

API
 |
 v
Application Service
 |
 v
Model Adapter Interface
 |
 +--> Provider Adapter
 +--> Ollama Adapter
 +--> Custom Adapter

This allows new model providers to be added without changing API contracts.

## Cancellation

Long-running test operations should support cancellation where practical.

Cancellation must be handled server-side.

A cancellation request must verify that the requesting identity is authorized to cancel the specific test run.

Cancellation must not leave inconsistent database state.

## Timeouts

External requests and long-running operations must have explicit timeouts.

The API must not wait indefinitely for:

- model providers
- external HTTP services
- database operations
- internal worker operations

Timeout values should be configurable and have safe defaults.

## Retries

Retries must be deliberate.

The system must distinguish between:

- transient failures
- permanent failures
- rate limiting
- authentication failures
- validation failures
- provider-side errors

Retries must not cause duplicate security-sensitive actions.

Operations must only be retried when their semantics permit safe retrying.

## Security Consequences

The API becomes a major trust boundary in Aegis Vuldris.

Therefore:

- all client input is untrusted
- authorization occurs server-side
- sensitive responses are minimized
- errors are sanitized
- expensive operations are bounded
- external calls use timeouts
- credentials remain isolated
- audit events are generated for security-sensitive actions

The model itself is never considered an authorization mechanism.

## Alternatives Considered

### GraphQL

Not selected initially because REST provides simpler operational behavior, straightforward HTTP semantics, mature FastAPI integration, and clear resource-oriented boundaries for the initial platform.

GraphQL may be reconsidered if frontend data-access requirements become sufficiently complex.

### gRPC

Not selected as the primary external API because browser-facing communication is simpler through HTTP/REST.

gRPC may be considered for future high-performance internal service-to-service communication if Aegis Vuldris evolves into a multi-service architecture.

### WebSockets as the Primary API

Rejected as the primary API because most Aegis Vuldris operations are naturally represented as resource-oriented HTTP requests.

WebSockets may be introduced later for real-time progress.

## Consequences

### Positive

- clear frontend/backend boundary
- mature HTTP semantics
- strong FastAPI integration
- automatic OpenAPI documentation
- explicit validation
- straightforward browser compatibility
- easy testing
- future-compatible with background workers
- clear security boundaries

### Negative

- API versioning requires discipline
- asynchronous operations require lifecycle management
- rate limiting and request limits require implementation
- real-time functionality may require an additional communication mechanism
- backward compatibility becomes an ongoing responsibility

These costs are accepted because a stable and secure API contract is essential for a production-grade platform.

## Future Considerations

The architecture can evolve to support:

- Server-Sent Events
- WebSockets
- background workers
- message queues
- internal gRPC
- API gateways
- service-to-service authentication
- distributed tracing
- API usage analytics

These additions should be driven by demonstrated requirements rather than premature complexity.

## Related Decisions

- `docs/adr/ADR-001-backend-framework.md`
- `docs/adr/ADR-002-frontend-framework.md`
- `docs/adr/ADR-003-database-architecture.md`
- `docs/security-baseline.md`
- `docs/security-boundaries.md`
- `docs/threat-model.md`

## Decision Summary

**Aegis Vuldris will use a versioned REST API built with FastAPI as its primary frontend/backend communication mechanism, with strict server-side validation, authentication, authorization, bounded resources, structured errors, asynchronous execution semantics, and a stable abstraction boundary for model providers and future workers.**
