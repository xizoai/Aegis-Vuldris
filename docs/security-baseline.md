# Aegis Vuldris Security Baseline

## 1. Purpose

This document defines the minimum security requirements for the Aegis Vuldris
platform.

Aegis Vuldris is itself a security-sensitive application. Security controls must
therefore be applied to Aegis Vuldris independently of the security behavior of
any AI model being tested.

These requirements apply to the backend, frontend, database, model
adapters, testing engine, reporting system, integrations, containers,
CI/CD pipelines, and supporting infrastructure.

---

## 2. Security Principles

Aegis Vuldris follows these core security principles:

- Defense in depth
- Least privilege
- Secure by default
- Fail closed where practical
- Explicit validation
- Strong isolation
- Minimal data collection
- Reproducibility and auditability
- No secrets in source code
- No unnecessary exposure of sensitive data
- Independent application-level security controls

AI model behavior must never be treated as a security boundary.

---

## 3. Authorized Testing

Aegis Vuldris must only be used to assess AI systems that the operator owns or
has explicit authorization to test.

The platform must not intentionally provide mechanisms designed to bypass
authorization, access controls, or security boundaries of systems without
permission.

Testing functionality should support controlled security research,
validation, and defensive assessment.

---

## 4. Secrets and Credentials

Secrets must never be committed to source control.

Examples include:

- API keys
- access tokens
- passwords
- database credentials
- encryption keys
- signing keys
- session secrets
- OAuth credentials

Secrets should be supplied through secure configuration mechanisms such as
environment variables or dedicated secret-management systems.

The application must avoid logging secrets.

Secrets should not appear in:

- source code
- Git history
- test fixtures
- example configuration files
- error messages
- reports
- telemetry

`.env.example` may contain variable names and safe placeholder values, but
must never contain real credentials.

---

## 5. Authentication

Production deployments must require authentication for protected
application functionality.

Authentication mechanisms must:

- use secure credential handling
- protect sessions/tokens
- reject invalid credentials
- avoid exposing authentication secrets
- support secure logout/session invalidation where applicable
- use secure transport in production

Anonymous access must not provide access to privileged functionality.

---

## 6. Authorization

Authentication alone is not sufficient.

Every protected operation must perform server-side authorization.

Authorization must be enforced independently of frontend controls and AI
model behavior.

The backend must verify that the authenticated user has permission to:

- access targets
- execute security tests
- view test results
- access evidence
- generate reports
- modify configurations
- manage credentials
- access administrative functionality

Client-side authorization checks must never be considered sufficient.

### Project Authorization Matrix

The current project API uses authenticated ownership with administrative scope:

| Role | Create | List | Read | Update | Delete |
| --- | --- | --- | --- | --- | --- |
| `super_admin` | Any project | All projects | All projects | All projects | All projects |
| `admin` | Any project | All projects | All projects | All projects | All projects |
| `user` | Own project | Own projects | Own projects | Own projects | Own projects |
| `viewer` | No | Own projects | Own projects | No | No |

Administrative scope is explicit in this implementation because project membership has not yet been modeled. Future membership-based authorization must narrow administrative access to assigned projects.

---

## 7. Network Security

Aegis Vuldris will eventually make outbound requests to model APIs and other
target systems.

User-controlled target addresses must therefore be treated as untrusted
input.

The platform must protect against:

- SSRF
- access to localhost
- access to private networks
- access to cloud metadata services
- DNS rebinding
- unexpected redirects
- unauthorized protocols
- uncontrolled outbound connections

Production deployments should use explicit outbound network policies and
allowlists where appropriate.

Target adapters must not automatically trust arbitrary URLs supplied by
users.

---

## 8. Input Validation

All externally supplied data must be treated as untrusted.

Validation must be applied to:

- API requests
- URLs
- identifiers
- model parameters
- prompts
- uploaded files
- configuration values
- report parameters
- tool arguments
- database query parameters

Validation must occur on the server.

Application code must prefer safe structured APIs over dynamically
constructed commands, queries, or executable code.

---

## 9. Database Security

Database access must use parameterized queries or a trusted ORM/database
abstraction.

The application must protect against:

- SQL injection
- unauthorized data access
- cross-user data access
- accidental data deletion
- insecure database credentials

Production database credentials must never be stored in source control.

Database access should use least-privilege accounts.

---

## 10. Data Protection

Aegis Vuldris may process sensitive security-testing data including prompts,
model responses, findings, evidence, credentials metadata, and reports.

The platform should therefore:

- minimize collected data
- retain only required information
- protect sensitive records
- avoid unnecessary duplication
- support controlled deletion
- prevent unauthorized access
- avoid exposing sensitive data through logs or errors

Sensitive data should be protected in transit and, where appropriate, at
rest.

---

## 11. Logging and Auditability

Security-relevant operations should be auditable.

Audit events may include:

- authentication events
- authorization failures
- target creation/modification
- test execution
- configuration changes
- report generation
- administrative actions
- security-sensitive errors

Logs must not contain secrets or unnecessary sensitive model content.

Logs should be structured where practical.

Security logs should be protected from unauthorized modification or
deletion in production environments.

---

## 12. AI-Specific Security

Aegis Vuldris must treat AI model output as untrusted data.

Model output must not automatically be trusted as:

- executable code
- shell commands
- database queries
- authorization decisions
- security policy decisions
- trusted instructions

AI-generated content must be validated before being passed into sensitive
application components.

Prompt injection and malicious model output must be considered expected
security conditions during testing.

---

## 13. Prompt and Model Isolation

Security tests may intentionally contain adversarial prompts.

The testing system must maintain clear boundaries between:

- test definitions
- attack payloads
- target model input
- target model output
- Aegis Vuldris system instructions
- Aegis Vuldris internal configuration

Target model output must not be allowed to modify Aegis Vuldris's own trusted
configuration or instructions.

---

## 14. Tool and Agent Security

Future Aegis Vuldris functionality may test AI agents capable of using tools.

Tool execution must therefore be treated as a high-risk capability.

Aegis Vuldris must:

- explicitly define permitted tools
- validate tool arguments
- enforce authorization
- limit privileges
- isolate dangerous operations
- record security-relevant tool activity
- prevent uncontrolled command execution

Arbitrary code execution must never be enabled merely because a model
requested it.

---

## 15. File Upload Security

If Aegis Vuldris supports file uploads for RAG or security testing, uploaded
content must be considered untrusted.

The platform must protect against:

- malicious files
- path traversal
- unsafe file types
- oversized uploads
- decompression bombs
- malicious document content
- unauthorized file access

Uploaded files must not automatically become executable.

---

## 16. Container and Host Security

Aegis Vuldris components running in containers should use least privilege.

Containers should avoid unnecessary:

- root privileges
- host filesystem mounts
- host networking
- Linux capabilities
- device access

Production containers should use minimal images and pinned dependencies
where practical.

The host system must not be considered trusted merely because Aegis Vuldris is
running inside a container.

---

## 17. Error Handling

Errors must fail safely.

Production error responses should not expose:

- stack traces
- secrets
- internal filesystem paths
- database credentials
- internal network information
- unnecessary implementation details

Detailed diagnostic information should remain available to authorized
operators through protected logs.

---

## 18. Rate Limiting and Resource Controls

Security testing can intentionally generate large numbers of requests.

The platform must eventually provide controls for:

- request rate
- concurrent tests
- token usage
- execution time
- file size
- response size
- number of attack iterations

Resource limits should prevent accidental or malicious denial-of-service
conditions.

---

## 19. Dependency Security

Third-party dependencies must be treated as part of the application's
attack surface.

Aegis Vuldris should use:

- dependency locking
- dependency vulnerability scanning
- regular updates
- minimal dependencies
- trusted package sources
- automated security checks

Dependencies should not be added without a clear reason.

---

## 20. Testing Security Controls

Security controls must themselves be tested.

Security-related tests should cover:

- authentication
- authorization
- input validation
- SSRF protections
- secret handling
- data isolation
- file handling
- rate limiting
- error handling
- audit logging

Security tests must be automated where practical.

---

## 21. Secure Defaults

When a security-sensitive configuration is unspecified, Aegis Vuldris should
prefer the safer behavior.

Examples:

- deny unauthorized access
- reject invalid input
- disable dangerous functionality
- limit outbound network access
- limit resource consumption
- avoid exposing sensitive information

Security-sensitive features should require explicit enablement where
appropriate.

---

## 22. Defense in Depth

No single security mechanism should be considered sufficient.

For example:

Authentication should be combined with authorization.

URL validation should be combined with network-level egress controls.

Input validation should be combined with safe APIs.

Container isolation should be combined with host-level restrictions.

AI safety evaluation should not replace application security controls.

---

## 23. Security Review Requirement

Security-sensitive changes should be reviewed before merging.

Examples include changes involving:

- authentication
- authorization
- credentials
- network access
- file processing
- code execution
- tool execution
- database access
- sandboxing
- cryptography
- sensitive data handling

---

## 24. Security Baseline Status

This document defines the initial security requirements for Aegis Vuldris.

Implementation will be performed incrementally throughout the project.

A requirement must not be considered implemented merely because it is
documented here.

Implementation and automated verification must be added in the relevant
development phases.
