# ADR-002: Frontend Framework

## Status

Accepted

## Date

2026-09-10

## Context

Aegis Vuldris requires a web-based frontend for interacting with the platform.

The frontend will eventually provide interfaces for:

- authentication
- target management
- security-test configuration
- test execution
- live test progress
- findings
- vulnerability details
- evidence inspection
- risk scoring
- reports
- dashboards
- configuration
- system health
- audit information

The frontend must support a growing application without becoming tightly
coupled to backend implementation details.

The project also requires:

- strong typing
- component reuse
- maintainable state management
- accessible interfaces
- automated testing
- secure API communication
- production builds
- good developer tooling
- open-source maintainability

## Decision

Aegis Vuldris will use **React with TypeScript** for the frontend application.

The frontend will be a separate application from the Python backend.

The initial frontend architecture will use:

- React
- TypeScript
- modern React component architecture
- API-driven communication with the FastAPI backend

The frontend will not contain security-critical authorization logic.

All security decisions must be enforced by the backend.

## Why React

React provides:

- mature component architecture
- large open-source ecosystem
- strong TypeScript support
- reusable UI components
- good developer tooling
- broad community adoption
- extensive testing ecosystem
- suitability for complex dashboard applications

Aegis Vuldris will eventually contain many interactive interfaces and reusable
security-analysis components, making a component-based architecture
appropriate.

## Why TypeScript

TypeScript will provide compile-time type checking for frontend code.

This is particularly useful for:

- API request types
- API response types
- security findings
- test configurations
- target configurations
- report data
- dashboard state
- application configuration

Types should reduce accidental mismatches between frontend expectations and
backend API contracts.

Where practical, API schemas should eventually be generated or derived
from the backend OpenAPI specification to reduce duplicated definitions.

## Security Considerations

The frontend is considered an untrusted client.

Client-side controls must never be treated as a security boundary.

The backend must independently enforce:

- authentication
- authorization
- resource ownership
- tenant isolation
- input validation
- rate limiting
- security policies

The frontend must avoid storing sensitive credentials unnecessarily.

Particular care must be taken with:

- authentication tokens
- API keys
- target credentials
- sensitive model responses
- security-test evidence
- reports

Sensitive data should not be unnecessarily exposed to browser storage,
client-side logs, URLs, or telemetry.

## API Communication

The frontend will communicate with the backend through explicit API
contracts.

The frontend must not directly access:

- the database
- server filesystem
- internal services
- model-provider credentials

All privileged operations must go through the backend security boundary.

## State Management

State management will initially remain as simple as practical.

Local component state and lightweight shared state should be preferred
before introducing a large state-management framework.

A dedicated state-management solution may be introduced later if application
complexity justifies it.

## Testing Strategy

The frontend will eventually include automated tests for:

- components
- user interactions
- API integration
- authentication flows
- authorization-related UI behavior
- error states
- loading states
- security-sensitive interfaces

UI tests must not be considered a replacement for backend security tests.

## Accessibility

The frontend should target accessible interfaces from the beginning.

Important requirements include:

- semantic HTML
- keyboard navigation
- accessible form controls
- meaningful labels
- appropriate focus management
- sufficient contrast
- accessible error messages

Accessibility should be considered part of the frontend engineering
standard rather than a late-stage enhancement.

## Performance

The frontend should avoid unnecessary complexity and excessive client-side
processing.

Potential future optimizations include:

- code splitting
- lazy loading
- pagination
- virtualized large datasets
- cached API data
- incremental rendering

Performance optimizations should be introduced based on measured needs.

## Alternatives Considered

### Vue

Vue is a capable and mature frontend framework.

It was not selected because React provides a broader ecosystem and a strong
fit for the expected dashboard and component architecture of Aegis Vuldris.

### Angular

Angular provides a comprehensive application framework with strong
TypeScript support.

It was not selected because its larger framework structure introduces more
opinionated architecture than initially required.

### Svelte

Svelte provides an attractive developer experience and strong performance.

It was not selected because React currently provides a larger ecosystem and
broader availability of reusable components and tooling relevant to this
project.

### Server-Side Rendered HTML

A server-rendered frontend was not selected for the primary application.

Aegis Vuldris is expected to contain highly interactive dashboards, test
execution views, live progress, evidence exploration, and security-analysis
interfaces that benefit from a client application architecture.

## Consequences

### Positive

- Strong TypeScript integration
- Reusable components
- Large ecosystem
- Suitable for complex dashboards
- Good developer tooling
- Clear separation from backend
- Easy integration with REST APIs

### Negative

- Additional frontend build tooling
- JavaScript ecosystem dependency management
- Potential client-side state complexity
- Browser security considerations
- Requires careful handling of sensitive data

## Architectural Boundaries

The frontend is responsible for:

- presentation
- user interaction
- client-side form validation
- API communication
- displaying test results
- displaying findings
- displaying reports

The backend is responsible for:

- authentication
- authorization
- security policies
- target credentials
- model-provider credentials
- database access
- security-test execution
- evaluation
- privileged operations

The frontend must never be trusted to enforce backend security policies.

## Future Considerations

The frontend architecture should allow future integration of:

- real-time test progress
- WebSocket or server-sent event communication
- advanced dashboards
- interactive evidence inspection
- report visualization
- role-based UI capabilities
- multi-tenant interfaces
- accessibility improvements
- internationalization

These features should be introduced incrementally as requirements become
clear.

## Related Documents

- `docs/architecture.md`
- `docs/development.md`
- `docs/security-baseline.md`
- `docs/security-boundaries.md`
- `docs/threat-model.md`
- `docs/adr/ADR-001-backend-framework.md`
