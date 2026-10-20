# ADR-001: Backend Framework

## Status

Accepted

## Date

2026-09-10

## Context

Aegis Vuldris requires a backend application capable of:

- exposing a REST API
- managing users and authorization
- managing AI security-test targets
- orchestrating security tests
- communicating with AI model providers
- storing test configurations and results
- processing evaluation results
- generating security findings
- generating reports
- enforcing security controls
- providing health and operational endpoints

The backend must also support:

- strong typing
- automated testing
- asynchronous I/O
- clear separation of application layers
- maintainable architecture
- good developer experience
- production deployment
- containerization

Aegis Vuldris is intended to remain open-source and use technologies that are
practical for contributors to understand and maintain.

## Decision

Aegis Vuldris will use **Python 3.11+ with FastAPI** as its backend framework.

The initial supported Python versions are:

- Python 3.11
- Python 3.12

FastAPI will provide the HTTP/API layer.

The backend architecture will separate:

- API routes
- request/response schemas
- authentication
- authorization
- application services
- domain logic
- model adapters
- security test execution
- evaluation
- persistence
- reporting
- infrastructure integrations

Business and security logic must not be placed directly inside HTTP route
handlers when that would make the logic difficult to test or reuse.

## Why FastAPI

FastAPI provides:

- native asynchronous request handling
- Python type-hint integration
- automatic OpenAPI documentation
- request validation through Pydantic
- straightforward dependency injection
- good testing support
- compatibility with modern Python tooling
- a mature ecosystem
- suitability for containerized deployments

FastAPI also allows the API layer to remain relatively thin while the
application's security and domain logic is implemented independently.

## Security Considerations

FastAPI does not automatically make an application secure.

Aegis Vuldris must independently implement:

- authentication
- authorization
- input validation
- output validation
- rate limiting
- request-size limits
- secure headers
- error handling
- audit logging
- secret protection
- SSRF protection
- resource limits

Frontend validation must never be considered a security boundary.

Authentication and authorization must be enforced on the backend.

AI model behavior must never be treated as an authorization mechanism.

## Testing Strategy

Backend code will be tested using pytest.

The architecture should make it possible to test:

- API endpoints
- authentication
- authorization
- application services
- model adapters
- security controls
- error handling
- persistence behavior
- attack orchestration
- evaluation logic

Security-sensitive functionality should have dedicated automated tests.

## Alternatives Considered

### Flask

Rejected for the initial architecture.

Flask is mature and capable, but FastAPI provides stronger integration with
modern Python type hints, asynchronous APIs, request validation, and
automatic API schemas for this project's requirements.

### Django

Rejected for the initial architecture.

Django provides a comprehensive web framework and could support the project,
but Aegis Vuldris requires a relatively modular API-first backend rather than a
large integrated web framework.

Django may be reconsidered if future requirements justify its broader
feature set.

### Node.js / TypeScript Backend

Rejected for the initial backend.

TypeScript remains a strong choice for the frontend, but Python provides a
better alignment with the AI/ML and security-testing ecosystem required by
Aegis Vuldris.

## Consequences

### Positive

- Strong typing through Python type hints
- Automatic API documentation
- Async support
- Good testing ergonomics
- Good compatibility with AI/ML tooling
- Clear separation between API and domain logic
- Good Docker compatibility
- Large open-source ecosystem

### Negative

- Python runtime performance is lower than some compiled languages
- Async code requires disciplined design
- Dependency management must be controlled
- CPU-heavy workloads should not block API workers

CPU-intensive security-test operations should eventually be moved to
controlled background workers or isolated execution environments.

## Future Considerations

The backend architecture should allow future introduction of:

- background workers
- job queues
- distributed test execution
- WebSocket or streaming endpoints
- OpenTelemetry
- horizontal scaling
- multi-tenancy
- plugin systems
- additional model providers

These capabilities should be introduced only when justified by actual
requirements.

## Related Documents

- `docs/architecture.md`
- `docs/security-baseline.md`
- `docs/security-boundaries.md`
- `docs/threat-model.md`
- `docs/development.md`
