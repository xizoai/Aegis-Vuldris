# ADR-015: Production Deployment & Operational Architecture

**Status:** Accepted
**Date:** 2026-09-10
**Decision Owners:** Aegis Vuldris Maintainers

---

## 1. Decision Summary

Aegis Vuldris will use a production architecture designed around secure, reproducible, self-hostable deployment.

The production deployment model will prioritize:

- Docker-based packaging
- Docker Compose for the initial production deployment topology
- VPS-compatible infrastructure
- Linux-based production hosts
- Reverse proxy termination for HTTPS
- TLS for external communication
- PostgreSQL as the primary persistent database
- Separate application, worker, database, and supporting service boundaries
- Explicit network segmentation
- Health and readiness checks
- Resource limits
- Secure configuration and secret injection
- Persistent storage for required state
- Automated and tested backups
- Restore procedures
- Controlled deployment and rollback
- Database migration discipline
- Security scanning
- Operational observability
- Auditability
- Least privilege
- Minimal exposed ports
- Defense in depth
- Production-safe defaults
- No dependency on developer laptops for production operation

The deployment architecture must preserve all security boundaries defined by the preceding ADRs.

Production deployment is an operational concern and must not weaken application-level authentication, authorization, data isolation, model-target isolation, evidence protection, or security testing controls.

---

## 2. Context

Aegis Vuldris is intended to evolve from a local development project into a production-capable AI security testing platform.

The system will execute security tests against authorized AI model targets.

The platform may process:

- prompts
- model responses
- attack plans
- evaluation results
- security findings
- evidence
- sensitive test artifacts
- target configuration
- credentials
- audit events
- reports
- telemetry
- project and tenant metadata

Production deployment therefore introduces security and operational requirements beyond application code.

A secure application deployed insecurely can still become compromised.

Examples include:

- exposing PostgreSQL directly to the Internet
- exposing internal worker services
- storing secrets in images
- running containers with excessive privileges
- mounting sensitive host paths
- allowing arbitrary outbound network access
- failing to configure TLS
- failing to isolate tenants
- failing to back up evidence
- allowing unbounded jobs
- deploying unreviewed database migrations
- failing to monitor resource exhaustion
- exposing debug endpoints
- allowing insecure administrative access
- losing security audit history
- running outdated dependencies
- failing to verify image provenance
- deploying without rollback capability

The deployment architecture must therefore make secure operation the default.

---

## 3. Decision Drivers

The architecture is driven by:

1. Security
2. Reproducibility
3. Self-hostability
4. Zero-cost/open-source infrastructure preference
5. VPS compatibility
6. Operational simplicity
7. Isolation
8. Reliability
9. Recoverability
10. Observability
11. Maintainability
12. Upgrade safety
13. Performance
14. Resource control
15. Data protection
16. Least privilege
17. Disaster recovery
18. Auditability
19. Portability
20. Clear operational boundaries

---

## 4. Architectural Principle

Production infrastructure must not become an implicit security boundary that the application assumes is sufficient.

The application must continue enforcing:

- authentication
- authorization
- object-level access control
- tenant/project isolation
- target authorization
- evidence authorization
- job authorization
- secret protection
- input validation
- output validation
- network policy
- resource limits

Infrastructure controls provide defense in depth.

---

## 5. Production Deployment Target

The initial production target is a Linux VPS.

The architecture must not require:

- a developer laptop
- a local Windows environment
- proprietary cloud services
- managed Kubernetes
- proprietary model infrastructure
- proprietary observability platforms

The application must be deployable to a generic VPS provider capable of running:

- Linux
- Docker Engine
- Docker Compose
- persistent storage
- networking
- firewall rules

The exact VPS provider is not part of this ADR.

---

## 6. Production Topology

The initial production topology will conceptually contain:

```text
                         Internet
                            |
                            v
                    +----------------+
                    | Reverse Proxy  |
                    | HTTPS / TLS    |
                    +-------+--------+
                            |
             +--------------+--------------+
             |                             |
             v                             v
      +-------------+              +--------------+
      | Frontend    |              | Backend API  |
      | Static App  |              | FastAPI      |
      +-------------+              +------+-------+
                                           |
                          +----------------+----------------+
                          |                                 |
                          v                                 v
                   +-------------+                    +-------------+
                   | PostgreSQL  |                    | Job Worker  |
                   | Database    |                    | Execution   |
                   +-------------+                    +------+------+
                                                            |
                                                            v
                                                     Model Targets
                                                     / External APIs

                    Observability / Audit / Metrics
                              |
                              v
                       Operational Stack

The exact container count may evolve.

The trust boundaries must not.

7. Reverse Proxy

A reverse proxy will be the public network entry point.

The reverse proxy will:

terminate HTTPS
route requests
enforce basic connection limits
provide security headers where appropriate
handle TLS certificates
avoid exposing internal services directly
support request size limits
support timeout controls
provide access logging without leaking sensitive data

The backend API will not need to be directly Internet-facing.

8. HTTPS Requirement

Production external application traffic must use HTTPS.

Plain HTTP must not be used for authenticated application traffic.

HTTP may only exist as a controlled mechanism for redirecting clients to HTTPS where operationally necessary.

Sensitive data must never be intentionally transmitted over plaintext external connections.

9. TLS

TLS configuration must:

use currently supported secure protocol versions
disable obsolete protocols
use trusted certificates
renew certificates safely
avoid hard-coded private keys in source control
protect certificate private keys
avoid exposing certificate-management endpoints publicly
be monitored for expiration

TLS configuration should be centrally documented.

10. Certificate Management

Production certificates must be provisioned using an automated or operationally controlled mechanism.

Certificate private keys must be treated as secrets.

Certificate files must not be committed to Git.

Certificate renewal must not require application source changes.

Certificate failures must produce operationally visible alerts.

11. Public Port Exposure

Only ports required for public operation should be exposed.

The preferred public exposure is:

443/tcp HTTPS

An HTTP port may be exposed only when required for certificate issuance or HTTPS redirection.

Internal ports must not be unnecessarily exposed to the public Internet.

12. Database Network Isolation

PostgreSQL must not be directly exposed to the public Internet.

The database should only accept connections from authorized internal application or worker networks.

Firewall rules must reinforce this policy.

The application must still use authentication and authorization at the database and application layers.

13. Worker Network Isolation

Workers must not expose unnecessary public ports.

Worker services should be reachable only through internal infrastructure.

Workers require network access only to:

required internal services
authorized target endpoints
required infrastructure services

Outbound access should be restricted where practical.

14. Container Architecture

Aegis Vuldris production components will be packaged as containers.

Containers should provide:

reproducible runtime environments
dependency isolation
deployment consistency
controlled configuration
resource limits
explicit networking
predictable startup behavior

Containers are not considered a complete security boundary.

Host-level security remains necessary.

15. Container Images

Production images must:

use trusted base images
pin important dependency versions
avoid unnecessary packages
avoid development tools
avoid compilers where unnecessary
avoid shells where practical
run application processes as non-root users
contain no secrets
be scanned before release
be rebuilt regularly
16. Image Provenance

Production deployments should prefer images produced by controlled CI/CD pipelines.

The release process should record:

source revision
image digest
build timestamp
dependency state
build environment
release identifier

Mutable image tags alone must not be treated as sufficient deployment identity.

17. Container Privileges

Production containers must run with the minimum privileges required.

The following should be avoided unless explicitly justified:

privileged containers
host PID namespace
host network namespace
host IPC namespace
arbitrary device access
unrestricted capabilities
writable host filesystem mounts

Security-sensitive exceptions require documented justification.

18. Non-Root Execution

Application and worker containers should run as non-root users.

Container entrypoints must not unnecessarily elevate privileges.

Any initialization requiring root privileges should be isolated and completed before dropping privileges where possible.

19. Filesystem Policy

Containers should use read-only filesystems where practical.

Writable directories should be explicitly identified.

Temporary files must use controlled temporary storage.

The application must never assume that a writable container filesystem is persistent.

20. Host Filesystem Mounts

Host filesystem mounts must be minimized.

The application must never receive unrestricted host filesystem access.

Sensitive host paths must not be mounted into application or worker containers.

Docker socket access must not be granted to application containers.

21. Docker Socket Protection

The Docker daemon socket provides highly privileged host control.

Aegis Vuldris containers must not receive direct Docker socket access unless a future architecture explicitly requires it and introduces a hardened broker.

The default policy is deny.

22. Database Architecture

PostgreSQL remains the primary persistent database as defined by ADR-003.

Production PostgreSQL must use:

strong authentication
least-privilege database roles
encrypted transport where applicable
controlled network access
regular backups
tested restore procedures
transaction integrity
migration management
monitoring
23. Database Credentials

Database credentials must never be:

hard-coded
committed
embedded in Docker images
printed in logs
included in error responses
exposed through health endpoints
included in telemetry

Credentials must be injected through the production secret-management mechanism.

24. Database Roles

Separate database roles should be used where operationally appropriate.

At minimum, application access should avoid superuser privileges.

Migration operations should be separated from ordinary runtime access where practical.

The application runtime must not require PostgreSQL superuser privileges.

25. Database Migrations

Alembic will be used for schema migrations.

Production migration procedures must:

identify the release
validate database connectivity
verify migration state
execute migrations in a controlled manner
verify application compatibility
record migration results
support recovery procedures

Destructive migrations require additional review.

26. Migration Compatibility

Application releases should account for database compatibility.

Where practical, schema changes should follow:

expand
    ->
migrate
    ->
backfill
    ->
switch
    ->
contract

This reduces deployment downtime and rollback risk.

27. Migration Rollback

Not every migration is safely reversible.

The deployment process must distinguish:

application rollback
migration rollback
data restoration

A previous application image must not automatically be assumed compatible with a newer database schema.

28. Database Backups

Production databases must be backed up regularly.

Backup strategy should include:

scheduled backups
retention policy
backup verification
access controls
encrypted storage where appropriate
off-host copies
restore testing

A backup that has never been restored successfully must not be treated as proven recoverability.

29. Evidence Backups

Evidence may contain security-sensitive information.

Evidence backups must preserve:

authorization boundaries
encryption controls
retention policies
deletion policies
project isolation

Evidence backups must not become an uncontrolled secondary data store.

30. Backup Security

Backup credentials must be separate from application runtime credentials where practical.

Backups must not be publicly accessible.

Backup locations must use least-privilege access.

Backup logs must not disclose sensitive content.

31. Restore Testing

Restore procedures must be tested periodically.

Restore testing should verify:

database integrity
application compatibility
evidence accessibility
configuration recovery
secret recovery procedures
tenant/project isolation
report availability

Recovery time and recovery point expectations should be documented.

32. Disaster Recovery

Production operations must define recovery procedures for:

database loss
server loss
container corruption
accidental deletion
credential compromise
certificate failure
application deployment failure
worker failure
storage failure

The recovery process must be documented and testable.

33. Recovery Point Objective

A future production deployment should define an explicit Recovery Point Objective (RPO).

RPO determines the maximum acceptable amount of data that may be lost.

The exact target depends on deployment scale and operational requirements.

The architecture must support configuring this independently from application code.

34. Recovery Time Objective

A future production deployment should define a Recovery Time Objective (RTO).

RTO determines the acceptable recovery duration.

Deployment automation should minimize manual recovery steps.

35. Frontend Deployment

The React/TypeScript frontend should be built into a production static bundle.

The production frontend should:

avoid development servers
avoid exposing source maps unnecessarily
contain no private secrets
contain only intentionally public configuration
use HTTPS API endpoints
implement secure authentication flows
handle API errors safely
36. Frontend Secret Boundary

No frontend configuration can be considered secret.

Anything delivered to a browser can be inspected by the user.

Therefore:

Browser-visible configuration = public
Server-side configuration = potentially sensitive
Secrets = server-side only
37. Backend Deployment

The FastAPI backend will run as a dedicated application service.

The backend must:

run without development reload
use production logging
validate configuration
enforce authentication
enforce authorization
enforce rate limits
enforce resource controls
expose controlled health endpoints
avoid debug mode
use secure error handling
38. Worker Deployment

Workers will execute background jobs and security test workloads.

Workers must be isolated from the public Internet.

Worker execution must inherit:

authorization context
project context
target restrictions
resource limits
network policy
evidence policy

Workers must not bypass application security controls.

39. Worker Isolation

A worker executing a security test must not automatically gain:

administrator permissions
unrestricted database access
unrestricted filesystem access
unrestricted network access
arbitrary command execution
arbitrary Docker control

Worker privileges must be scoped to the operation.

40. Job Persistence

Job state must be persisted using the architecture defined in ADR-005.

The system must support:

queued
running
completed
failed
cancelled
timed out

Job state transitions must remain auditable.

41. Worker Failure

Worker crashes must not corrupt persistent job state.

Jobs must have controlled retry semantics.

Retry behavior must not cause uncontrolled attack amplification.

42. Job Resource Limits

Production jobs must have explicit limits for:

execution duration
number of requests
number of turns
tokens
response bytes
tool calls
network requests
concurrency
storage
memory
CPU

These limits complement ADR-005 and ADR-011.

43. Queue Safety

If a queue is introduced, it must be treated as a security boundary.

Queue messages must:

be validated
contain identifiers rather than unnecessary sensitive payloads
be authorization-aware
have bounded size
avoid arbitrary executable content
be protected from unauthorized producers
be protected from unauthorized consumers
44. Redis

If Redis is introduced for job coordination or caching, it must not be publicly exposed.

Redis credentials must be protected.

Redis must not become the authoritative source for security-sensitive persistent records unless explicitly designed for that purpose.

45. Cache Security

Caches must not bypass authorization.

A cached response must never be served across:

users
projects
tenants
authorization contexts

Sensitive cached content requires explicit retention and deletion controls.

46. Model Target Connectivity

Aegis Vuldris may communicate with external model targets.

Target connections must use the architecture defined in ADR-007.

Production deployment must preserve:

target allowlisting
authorization
credential isolation
TLS
SSRF protection
timeout controls
response-size limits
network policy
47. Outbound Network Policy

Outbound network access must not be unrestricted by default.

The platform should distinguish:

approved model endpoints
approved tool endpoints
approved infrastructure endpoints
disallowed private network ranges
loopback
metadata endpoints
local hostnames
arbitrary Internet destinations
48. SSRF Defense

Production infrastructure must not rely solely on container networking to prevent SSRF.

Application-level SSRF controls remain mandatory.

The system must consider:

DNS resolution
redirects
IPv4
IPv6
private addresses
loopback
link-local addresses
cloud metadata endpoints
DNS rebinding
alternative URL representations
49. DNS Rebinding

Host validation must not be considered complete after checking only the initial DNS result.

Connections should be validated according to the target security policy.

Redirects and subsequent resolutions must also be controlled.

50. Private Network Protection

Unless explicitly authorized, requests from test execution infrastructure must not reach:

loopback services
private network ranges
host services
container management interfaces
cloud metadata endpoints
internal administrative interfaces
51. Tool Execution

Tool-enabled testing must use explicit capabilities.

Tools must be:

allowlisted
authenticated
scoped
rate limited
logged
resource constrained

The model must never be allowed to dynamically expand its own privileges.

52. Command Execution

Arbitrary shell execution is disabled by default.

If a future testing feature requires command execution, it must use:

isolated execution
explicit authorization
allowlisted commands
resource limits
timeout
filesystem isolation
network restrictions
audit logging
53. Code Execution

Untrusted model output must never be directly executed as application code.

Dynamic code execution must not be introduced through:

eval
exec
arbitrary subprocess construction
unsafe template execution
dynamic module loading
untrusted deserialization

Any future execution sandbox requires a separate security architecture decision.

54. Configuration

Production configuration follows ADR-014.

Production configuration must be:

validated
environment-aware
secret-safe
explicit
versioned where required
immutable during normal process execution
55. Environment Separation

The deployment model must distinguish:

development
testing
staging
production

Production credentials must never be reused in development or tests.

Production data must never be copied into development environments without explicit authorization and privacy controls.

56. .env Files

Local .env files may be used for development.

Production deployments should prefer controlled secret injection.

Production secrets must not be committed to Git.

.env.example must contain placeholders only.

57. Secret Injection

Production secrets should be supplied through:

environment injection
secret files with strict permissions
a future secret-management service
another controlled secret provider

The application must never retrieve secrets from arbitrary URLs.

58. Secret Rotation

Production credentials must support rotation.

Rotation procedures should include:

create replacement
deploy replacement
verify operation
revoke old credential
verify old credential no longer works
record audit event
59. Secret Compromise

If a production secret is suspected to be compromised:

revoke or rotate it
identify affected systems
inspect audit logs
assess potential access
restore secure configuration
investigate impact
document the incident

Secrets must not be printed during incident investigation.

60. Administrative Access

Administrative access to the VPS must use secure mechanisms.

Preferred controls include:

SSH keys
restricted users
firewall rules
disabled password authentication where practical
disabled direct root login where practical
regular operating system updates
audit logging
61. Host Hardening

The production host should use:

minimal installed packages
automatic or controlled security updates
host firewall
time synchronization
restricted SSH access
disk monitoring
resource monitoring
intrusion detection where practical
62. SSH Security

SSH should be restricted to administrative access.

The system should prefer key-based authentication.

SSH access should not be exposed broadly if network restrictions can limit it.

63. Firewall

The host firewall should follow default-deny principles for inbound traffic.

Only explicitly required services should be reachable.

The firewall must complement container networking.

64. Operating System Updates

Production hosts must receive security updates.

Updates should be performed through a controlled operational process.

Critical security updates must be prioritized.

65. Container Updates

Application images must be rebuilt regularly.

Dependency and base-image vulnerabilities must be monitored.

An outdated but "working" image must not be treated as indefinitely acceptable.

66. Health Checks

Each production service must provide appropriate health checks.

Health checks should distinguish:

process alive
service ready
dependency available

A process being alive does not necessarily mean the service is ready.

67. Liveness

Liveness checks should answer:

Is the process functioning sufficiently to remain running?

Liveness checks must be lightweight.

They must not expose sensitive system information.

68. Readiness

Readiness checks should answer:

Can this service safely receive production work?

Readiness may consider required dependencies.

A failing dependency should not necessarily reveal internal details to public clients.

69. Health Endpoint Security

Public health endpoints must return minimal information.

They must not expose:

database credentials
environment variables
internal hostnames
filesystem paths
stack traces
secrets
dependency versions unnecessarily
70. Resource Monitoring

Production must monitor:

CPU
memory
disk
disk I/O
network
container restarts
database connections
queue depth
job duration
failed jobs
API latency
error rates
71. Resource Exhaustion

Resource exhaustion must be treated as a security concern.

Controls should include:

request limits
job limits
concurrency limits
storage quotas
worker limits
database connection limits
response-size limits
timeout limits
72. Disk Protection

Disk usage must be monitored.

The system must prevent unbounded growth from:

logs
evidence
reports
temporary files
database growth
container layers
backups
73. Log Rotation

Logs must use controlled retention and rotation.

Logs must not grow without bound.

Log rotation must not cause security audit history to be silently destroyed.

74. Observability

Observability follows ADR-013.

Production should support:

structured logs
metrics
traces
audit events
request correlation
job correlation
test correlation
finding correlation
75. Privacy-Safe Observability

Production telemetry must not automatically include:

passwords
API keys
tokens
database URLs
model credentials
raw sensitive prompts
raw sensitive responses

Sensitive evidence must remain in the evidence subsystem.

76. Audit Logging

Security-sensitive administrative operations must produce audit records.

Examples:

authentication events
authorization failures
target creation
target credential changes
project changes
job cancellation
configuration changes
evidence access
report generation
administrative operations
77. Audit Integrity

Audit records must be protected against unauthorized modification.

Application users must not be able to silently rewrite historical security audit records.

78. Time Synchronization

Production systems must maintain synchronized system time.

UTC should be used for stored timestamps.

Correct time is required for:

audit logs
authentication
TLS
job scheduling
incident investigation
distributed tracing
79. Deployment Strategy

The initial deployment strategy will prioritize simplicity.

A release should generally follow:

Build
  ->
Test
  ->
Scan
  ->
Publish
  ->
Backup
  ->
Deploy
  ->
Migrate
  ->
Health Check
  ->
Verify

Failures must stop progression where appropriate.

80. Pre-Deployment Checks

Before production deployment:

tests must pass
lint checks must pass
type checks must pass
dependency checks should pass
security scans should pass
image scans should pass
configuration validation must pass
migration compatibility must be reviewed
81. Release Identity

Every production deployment must be identifiable by:

Git commit
application version
image digest
database migration state

This allows operators to determine exactly what is running.

82. Git-Based Release Traceability

Production source must correspond to a known Git revision.

Uncommitted local changes must never be deployed as production source.

83. CI/CD

CI/CD should automate:

tests
linting
type checking
security checks
dependency checks
image builds
image scanning
artifact generation
release tagging

Deployment automation may be introduced incrementally.

84. Deployment Secrets

CI/CD secrets must be stored using the CI/CD platform's secret mechanism.

They must never appear in:

source code
workflow definitions
logs
build artifacts
Docker layers
85. Supply Chain Security

The build pipeline should verify:

dependency versions
dependency vulnerabilities
container base image status
lockfiles
source provenance
build artifacts
86. Dependency Locking

Production Python dependencies should be reproducibly locked.

Frontend dependencies should use a committed lockfile.

Dependency changes must be reviewable.

87. Software Bill of Materials

A production release should eventually produce an SBOM.

The SBOM should identify relevant:

application dependencies
operating system packages
container components

SBOM generation is part of the production security roadmap.

88. Vulnerability Scanning

Production release pipelines should support:

SAST
dependency scanning
container scanning
secret scanning
configuration scanning
SBOM generation

No scanner should be treated as a complete security guarantee.

89. Security Gates

Critical security findings should block release where appropriate.

Severity policy must align with the risk architecture in ADR-009.

Exceptions require documented approval.

90. Staging

A staging environment should approximate production architecture.

It should use:

equivalent containers
equivalent networking
equivalent configuration structure
representative health checks
migration procedures

Staging data must remain non-production unless explicitly authorized.

91. Production Configuration Validation

The application must fail safely when required production configuration is missing.

It must not silently fall back to insecure defaults.

Examples include:

missing secret keys
missing database credentials
invalid TLS configuration
invalid allowed origins
invalid target configuration
92. Debug Mode

Debug mode must be disabled in production.

Production errors must not expose:

stack traces
internal paths
SQL statements
credentials
environment variables
sensitive model content
93. CORS

Production CORS configuration must use explicit trusted origins.

Wildcard origins must not be used with credentialed browser authentication.

94. Security Headers

The reverse proxy and/or application should provide appropriate security headers.

The exact set should be validated against the deployed frontend architecture.

Headers must not be treated as substitutes for authentication or authorization.

95. Cookie Security

If browser sessions use cookies, production cookies should use appropriate:

Secure
HttpOnly
SameSite

attributes according to the authentication architecture.

96. CSRF

If cookie-based authentication is used, CSRF protections must be implemented where applicable.

The chosen mechanism must align with ADR-006.

97. Authentication

Authentication follows ADR-006.

Infrastructure deployment must not bypass application authentication.

Internal services may have separate service authentication.

98. Authorization

Authorization remains an application responsibility.

A private Docker network does not mean a user is authorized.

Every sensitive application operation must still enforce authorization.

99. Tenant Isolation

Infrastructure must not create cross-tenant data exposure.

Database queries, caches, workers, evidence, reports, telemetry, and backups must preserve tenant boundaries.

100. Project Isolation

Project boundaries must be preserved across:

API
jobs
workers
database
evidence
reports
telemetry
caches
queues
101. Evidence Isolation

Security evidence must be accessible only to authorized users.

Infrastructure operators may require separate administrative controls.

Evidence access must be auditable.

102. Report Isolation

Generated reports must preserve project and tenant authorization.

Report download endpoints must not rely on obscurity.

103. File Uploads

Production file uploads must be:

size limited
type validated
stored outside executable paths
access controlled
scanned where appropriate
isolated from application code
protected against path traversal
104. Temporary Files

Temporary test artifacts must use controlled directories.

Temporary files must have bounded lifetime.

Sensitive temporary data must be deleted according to retention policy.

105. Object Storage

If object storage is introduced, it must use:

private buckets
least-privilege credentials
signed access where appropriate
encryption
retention controls
deletion controls
tenant/project isolation

Public object storage is not permitted for sensitive evidence.

106. Backup Object Storage

Backup storage must be separated from ordinary application storage.

Backup access must use dedicated credentials.

107. Report Generation Isolation

Report generation must not execute untrusted content.

Report templates must be controlled.

Generated HTML, CSV, Markdown, and PDF outputs must follow ADR-008 security requirements.

108. HTML Reports

HTML report generation must prevent:

script injection
unsafe HTML injection
malicious links where relevant
unsafe embedded resources

Evidence must be escaped or safely rendered.

109. CSV Reports

CSV exports must consider spreadsheet formula injection.

Untrusted strings beginning with spreadsheet formula characters must be handled safely.

110. PDF Reports

PDF generation must not execute untrusted content.

PDF generation must use controlled templates and bounded inputs.

111. Operational Access to Evidence

Operators should not routinely access raw security evidence.

Administrative access must follow least privilege.

Sensitive access should be auditable.

112. Production Data Handling

Production data must be classified according to ADR-012.

Operational systems must preserve:

retention
deletion
minimization
access control
auditability
113. Data Residency

The architecture must allow deployment-specific data residency decisions.

The application should not silently send data to unrelated external services.

114. External Telemetry

External telemetry services are disabled by default unless explicitly configured.

Production deployments should prefer local/open-source observability where practical.

115. External Model Providers

External model providers are separate trust boundaries.

The deployment must make outbound data transfer explicit.

Sensitive test data must not be sent externally without authorization and policy approval.

116. Local-First Operation

Aegis Vuldris should remain capable of operating with local/open-source infrastructure where practical.

Examples include:

PostgreSQL
Docker
OpenTelemetry
Prometheus-compatible metrics
Grafana
Loki
Tempo
Ollama

Optional integrations must not become mandatory for the core platform.

117. Monitoring Stack

A production deployment may use:

Aegis Vuldris
   |
   +--> OpenTelemetry
   |
   +--> Metrics
   |
   +--> Logs
   |
   +--> Traces
            |
            v
   Operational dashboards

The exact stack may evolve.

118. Alerting

Production alerts should cover:

application downtime
high error rates
repeated worker failures
queue backlog
database failures
disk exhaustion
memory exhaustion
certificate expiration
backup failures
security-critical events
119. Alert Security

Alerts must not contain secrets.

Sensitive evidence must not be embedded into alert payloads.

Alerts should contain references or identifiers rather than unnecessary raw content.

120. Operational Dashboards

Dashboards should provide visibility into:

service health
request latency
error rate
job throughput
job failures
queue depth
worker utilization
database health
storage usage
security events
121. Operational Runbooks

Production deployment must maintain runbooks for:

deployment
rollback
backup
restore
certificate renewal
secret rotation
database migration
worker recovery
incident response
disk exhaustion
service restart
emergency shutdown
122. Emergency Shutdown

Aegis Vuldris must support controlled emergency shutdown.

Emergency shutdown should be capable of:

stopping new jobs
cancelling active jobs where safe
preventing new external target requests
preserving existing evidence
maintaining audit records
stopping worker execution
123. Kill Switch

A future operational kill switch may disable:

new test execution
external target calls
tool execution
high-risk attack modes

The kill switch must fail closed for the affected capability.

124. Maintenance Mode

Maintenance mode may prevent new user operations while allowing operators to:

inspect health
complete migrations
perform recovery
review logs
execute controlled administrative tasks
125. Graceful Shutdown

Services should support graceful shutdown.

The system should:

stop accepting new work
finish safe in-flight operations
cancel unsafe or expired work
persist job state
close database connections
flush telemetry
terminate cleanly
126. Deployment Restart

A restart must not automatically duplicate security test execution.

Job state and idempotency controls must prevent accidental repeated execution.

127. Idempotency

Sensitive operations should use idempotency mechanisms where duplicate execution could cause:

duplicate tests
duplicate reports
duplicate notifications
duplicate external requests
inconsistent state
128. Database Connection Management

Production connection pools must be bounded.

Connection exhaustion must be monitored.

Worker concurrency must account for database capacity.

129. API Rate Limiting

Production APIs must enforce appropriate rate limits.

Rate limiting should consider:

authentication state
user
project
tenant
endpoint
operation cost

Expensive security testing operations require stronger controls than cheap metadata operations.

130. Attack Execution Rate Limits

Security testing can generate significant target traffic.

Attack execution must enforce:

request budgets
concurrency budgets
duration limits
target-specific rate limits

The purpose of Aegis Vuldris must not become uncontrolled traffic generation.

131. Target Authorization

Before executing a test against a target, Aegis Vuldris must have sufficient authorization context.

Infrastructure deployment does not grant authorization.

The system must preserve the target authorization model from ADR-007 and ADR-011.

132. Production Testing

Production targets must not be used for uncontrolled development experimentation.

Test profiles should distinguish:

development
staging
authorized production assessment
133. High-Risk Tests

High-risk security tests require stronger safeguards.

Examples include tests involving:

destructive actions
external side effects
tool execution
network access
file operations
command execution

High-risk testing must be explicitly enabled.

134. Safe Defaults

Production defaults must favor:

no arbitrary execution
no unrestricted network
no public database
no debug mode
no wildcard CORS with credentials
no secret logging
no privileged containers
no unrestricted tool access
no uncontrolled job execution
135. Feature Flags

Security-sensitive features should use explicit feature flags.

Examples:

tool execution
experimental attack strategies
external evaluators
high-risk testing
dynamic plugins

Flags must not silently weaken core security controls.

136. Feature Flag Security

Feature flags must be:

authorized
audited where security-sensitive
validated
environment-aware

User-controlled feature flags must not grant administrative privileges.

137. Operational Configuration Changes

Runtime configuration changes should be controlled.

Security-sensitive configuration changes must produce audit events.

Changes should require appropriate authorization.

138. Plugin Deployment

Production plugins must be explicitly trusted.

Plugins must not automatically receive:

filesystem access
network access
database access
shell access
secrets

Plugin capabilities must be explicitly granted.

139. Plugin Isolation

A future plugin sandbox should be considered for untrusted extensions.

The initial production architecture will not treat arbitrary Python plugins as safe by default.

140. Dynamic Imports

Production systems must not dynamically import arbitrary module names derived from user or model input.

141. Unsafe Serialization

Production services must not deserialize untrusted data using unsafe mechanisms.

Examples of prohibited default behavior include unsafe pickle deserialization.

142. YAML

Untrusted YAML must use safe parsing mechanisms.

YAML configuration must not allow arbitrary object construction.

143. Authentication Failure Handling

Production authentication failures must:

avoid account enumeration
avoid sensitive error details
be rate limited
be logged appropriately
not reveal credential values
144. Authorization Failure Handling

Authorization failures must return safe responses.

The system must avoid revealing whether unauthorized resources exist where appropriate.

145. Error Correlation

Errors should include safe correlation identifiers.

Users should be able to report an error identifier without receiving internal implementation details.

146. Internal Error Details

Detailed errors should be available to authorized operators through protected logs and telemetry.

They must not be returned directly to untrusted clients.

147. Production Logging Level

Production logging should default to an operationally useful level.

Debug logging must require explicit configuration and should not expose sensitive content.

148. Sensitive Logging

The following must never be logged directly:

passwords
API keys
session tokens
private keys
database passwords
authentication headers
secret environment variables
149. Prompt and Response Logging

Raw model prompts and responses should not be logged automatically.

Security evidence storage is separate from operational logs.

150. Log Injection

User, model, tool, and target-provided values must be encoded safely before entering structured logs.

Control characters and terminal escape sequences must not allow log manipulation.

151. Metrics Cardinality

Metrics must avoid unbounded labels.

User-provided values must never become arbitrary metric label values.

152. Trace Safety

Distributed traces must not automatically contain raw:

prompts
responses
credentials
sensitive evidence

Trace attributes should be bounded and privacy-aware.

153. Health Data

Health checks should return only information required by the caller.

Detailed operational diagnostics must remain protected.

154. Database Health Monitoring

Database monitoring should include:

connection count
failed connections
query latency
transaction failures
storage growth
replication state if applicable
backup status
155. Worker Monitoring

Worker monitoring should include:

active workers
job throughput
failed jobs
retry count
execution duration
resource utilization
queue depth
156. Model Adapter Monitoring

Model adapter telemetry should include safe metadata such as:

provider identifier
target identifier
request duration
status
retry count
bounded token metrics where available

Raw secrets must not be emitted.

157. Security Test Monitoring

Security test execution should be observable through:

test identifier
execution identifier
project identifier
target identifier
status
duration
evaluator result
finding count

Sensitive evidence remains separately controlled.

158. Attack Monitoring

Attack orchestration should record:

attack plan identifier
execution identifier
turn count
budget consumption
termination reason
target identifier
evaluation outcome

It must not expose sensitive raw attack content in ordinary telemetry.

159. Evaluation Monitoring

Evaluation should expose safe metadata including:

evaluator identifier
evaluation status
duration
confidence
finding identifiers
160. Finding Monitoring

Findings should include:

finding identifier
severity
status
category
project context
timestamps

Sensitive evidence should not be duplicated into metrics.

161. Deployment Verification

After deployment:

verify containers
verify health
verify readiness
verify database
verify migrations
verify authentication
verify authorization
verify frontend
verify worker execution
verify telemetry
verify backups
162. Smoke Tests

Production smoke tests should use safe, non-destructive test cases.

Smoke tests should not accidentally invoke high-risk model targets.

163. Post-Deployment Security Verification

Each release should verify critical security invariants.

Examples:

HTTPS works
database is not publicly reachable
debug mode is disabled
unauthorized access is denied
tenant isolation works
secrets are not exposed
worker services are not publicly exposed
health endpoints are safe
164. Rollback

Deployment rollback must be documented.

Rollback should identify:

previous application version
previous image digest
database compatibility
configuration compatibility
secret compatibility
165. Application Rollback

Application rollback should be possible when the previous image remains compatible with the current database schema.

166. Database Recovery

When application rollback cannot safely reverse a migration, database restoration or forward migration may be required.

The runbook must make this distinction explicit.

167. Blue/Green Deployment

Blue/green deployment is not required for the initial deployment.

It may be introduced later when operational scale justifies it.

168. Canary Deployment

Canary deployment is not required initially.

It may be introduced later for large-scale installations.

169. Kubernetes

Kubernetes is not required for the initial architecture.

Docker Compose is preferred initially because it reduces operational complexity.

A future Kubernetes architecture would require a separate ADR or amendment.

170. Cloud Provider Dependency

Aegis Vuldris must not depend on a single cloud provider.

Cloud-specific services may be optional integrations.

171. Infrastructure as Code

Infrastructure as Code should be introduced as the deployment complexity increases.

Possible open-source tools may include:

Terraform
OpenTofu
Ansible

The exact tool is not selected by this ADR.

172. Docker Compose

Docker Compose is the initial deployment orchestration mechanism.

Compose configuration should explicitly define:

services
networks
volumes
health checks
resource constraints where supported
restart policies
environment configuration
secret handling
173. Compose Security

Compose files must not contain production secrets.

Production overrides must be protected.

Public ports must be explicit.

Internal services should use internal networks.

174. Network Segmentation

At minimum, the deployment should conceptually separate:

public network
internal application network
database network
worker/target network

Exact network topology may evolve.

175. Network Egress

Worker outbound traffic must be controlled.

The platform should support future policy enforcement for:

allowed domains
allowed IP ranges
ports
protocols
target identities
176. Network Timeouts

All external calls must have bounded timeouts.

No security test should wait indefinitely for a target.

177. Response Limits

External model responses must have bounded size.

This protects against memory exhaustion and oversized evidence.

178. Request Limits

Incoming API requests must have appropriate size limits.

Large uploads require explicit limits.

179. Compression Security

Compression must be configured carefully to avoid resource-exhaustion attacks.

Compressed request payloads must still respect effective size limits.

180. Reverse Proxy Timeouts

Reverse proxy timeouts must prevent indefinite connections.

Timeouts should account for normal API behavior without permitting unbounded resource consumption.

181. Long-Running Tests

Long-running tests should be asynchronous jobs.

The API should not hold an HTTP connection open for the full test duration.

182. Job Polling

Job status should be retrieved through authorized APIs.

Users must not be able to query arbitrary job identifiers.

183. WebSockets

If WebSockets or streaming are introduced, they must preserve:

authentication
authorization
origin validation
rate limiting
resource limits
project isolation
184. Server-Sent Events

If SSE is introduced, it must preserve the same security controls as ordinary API communication.

185. Database Encryption

Where feasible, production database storage should use encrypted disks or encrypted volumes.

Application-level encryption may be added for particularly sensitive fields.

186. Evidence Encryption

Sensitive evidence should be protected through encryption at rest where supported.

Keys must be managed separately from data.

187. Key Management

Cryptographic keys must not be stored alongside encrypted data without appropriate protection.

Key rotation procedures must be documented.

188. Backup Encryption

Sensitive backups should be encrypted.

Encryption keys must not be stored inside the same unrestricted backup location.

189. Secret Manager Abstraction

The application should provide a configuration abstraction that allows future integration with secret managers.

The core application must not become tightly coupled to a single vendor.

190. Operational Credentials

Different services should receive only the credentials they require.

For example:

Backend -> database runtime credential
Worker  -> restricted database/job credential
Backup  -> backup credential
CI/CD   -> deployment credential

These credentials should not be interchangeable.

191. Deployment Credential Protection

Deployment credentials must not be available to runtime containers.

192. Database Backup Credential Protection

Backup credentials must not be available to ordinary application users.

193. Worker Credentials

Workers must receive only the credentials required for their assigned jobs.

194. Target Credentials

Model target credentials must remain isolated from:

frontend
ordinary users
logs
metrics
reports
unrelated workers
195. Credential Scope

Credentials should be scoped to the smallest practical:

target
project
tenant
environment
operation
196. Credential Rotation Monitoring

Credential rotation failures must be operationally visible.

197. Certificate Monitoring

Certificate expiration should be monitored before expiry.

198. Backup Monitoring

Backup jobs must produce success/failure status.

Silent backup failure is unacceptable.

199. Restore Monitoring

Restore testing results should be recorded.

200. Security Incident Detection

Production monitoring should identify suspicious events such as:

repeated authentication failures
unusual authorization failures
unexpected administrative operations
excessive test execution
unexpected target destinations
repeated SSRF blocks
tool abuse
unusual resource consumption
201. Incident Response

A production incident should preserve:

relevant audit logs
deployment identity
affected service versions
security findings
evidence where authorized
configuration history

Incident response must avoid destroying useful evidence.

202. Incident Containment

Containment may include:

disable test execution
revoke credentials
isolate worker network
block target access
disable affected feature
rotate secrets
shut down compromised services
203. Incident Recovery

Recovery should:

contain the issue
identify root cause
restore secure state
verify controls
rotate affected secrets
deploy fixes
monitor for recurrence
204. Incident Postmortem

Significant incidents should produce a postmortem containing:

timeline
impact
root cause
contributing factors
detection
response
remediation
prevention
205. Security Testing of Infrastructure

Production infrastructure itself must be security tested.

Testing should include:

port exposure
TLS configuration
authentication
authorization
network isolation
container configuration
image vulnerabilities
secret exposure
SSRF controls
resource exhaustion
backup security
recovery
206. Container Security Testing

Container testing should verify:

non-root execution
minimal capabilities
no privileged mode
no Docker socket
minimal mounts
expected network access
image vulnerabilities
207. Host Security Testing

Host testing should verify:

firewall rules
SSH configuration
exposed services
update state
filesystem permissions
Docker daemon exposure
208. Database Security Testing

Database testing should verify:

public accessibility
credential strength
role privileges
network restrictions
backup access
migration security
209. Reverse Proxy Security Testing

Proxy testing should verify:

TLS
HTTP redirects
security headers
request limits
routing
path normalization
oversized requests
malformed requests
210. Deployment Configuration Testing

CI should validate production Compose/configuration files.

Tests should detect:

public database ports
privileged containers
root containers
secret literals
unsafe volume mounts
missing health checks
debug mode
wildcard CORS
unsafe network exposure
211. Configuration Drift

Production configuration should be monitored for unexpected drift.

Drift detection may compare:

deployed image
Compose configuration
environment configuration
migration state
firewall state
212. Immutable Releases

Where practical, deployments should use immutable image references.

Running containers should correspond to a known release.

213. Restart Policy

Production services should use controlled restart policies.

Automatic restarts must not create restart loops that conceal persistent failures.

214. Crash Loop Monitoring

Repeated container crashes must generate operational alerts.

215. Service Dependencies

Dependencies must be explicit.

A service should not rely on accidental startup ordering.

Health checks and readiness conditions should coordinate startup.

216. Startup Ordering

The deployment should ensure:

Database
   ->
Backend readiness
   ->
Workers

but startup ordering alone must not replace health checks.

217. Database Initialization

Database initialization must not run destructive operations automatically in production.

218. Production Seed Data

Production startup must not automatically insert development test data.

219. Development Data Separation

Development fixtures must never accidentally execute against production databases.

220. Test Database Isolation

Automated tests must use isolated databases.

Production credentials must never be loaded into automated test environments.

221. CI Environment Isolation

CI jobs must use isolated credentials and infrastructure.

222. Build Environment Isolation

Build jobs must not receive production secrets unless explicitly required.

The default is no production secret access.

223. Artifact Storage

Build artifacts should be private unless explicitly intended for public release.

Sensitive reports must never be published accidentally.

224. Release Artifacts

A release may include:

source archive
container image
SBOM
checksums
release notes
deployment metadata
225. Checksums

Release artifacts should have integrity checks such as cryptographic hashes.

226. Release Signing

Release signing may be introduced as the project matures.

Signed artifacts provide stronger provenance guarantees.

227. Public Open-Source Release

Open-source releases must be scanned for:

secrets
private keys
credentials
internal endpoints
accidental production data
228. Git History Security

Removing a secret from the latest commit is insufficient if it exists in Git history.

Secret compromise procedures must include historical exposure assessment.

229. Production Source Protection

Private deployment configuration must not be committed to the public repository.

230. Repository Security

Repository controls should include:

protected main branch
reviewed changes
CI checks
secret scanning
dependency monitoring
231. Branch Protection

Production repositories should require appropriate CI checks before merging.

232. Release Approval

Production releases should require explicit approval when risk warrants it.

233. Emergency Releases

Emergency security releases may use an expedited process but must remain auditable.

234. Versioning

Application versions should follow a consistent versioning strategy.

The exact versioning scheme may evolve.

235. Database Version Compatibility

Release notes must identify database migration requirements.

236. Operational Compatibility

Releases should document:

configuration changes
migration changes
secret changes
infrastructure requirements
rollback limitations
237. Documentation

Production documentation must include:

architecture
deployment
configuration
backup
restore
security
incident response
troubleshooting
238. Deployment Checklist

A production release checklist should include:

[ ] Source revision verified
[ ] Tests passed
[ ] Lint passed
[ ] Type checks passed
[ ] Security checks passed
[ ] Dependency scan passed
[ ] Container scan passed
[ ] Secrets scan passed
[ ] Backup verified
[ ] Migration reviewed
[ ] Configuration validated
[ ] Image verified
[ ] Deployment completed
[ ] Health verified
[ ] Authentication verified
[ ] Authorization verified
[ ] Worker verified
[ ] Telemetry verified
[ ] Rollback path confirmed
239. Rollback Checklist
[ ] Identify failing release
[ ] Identify previous release
[ ] Check schema compatibility
[ ] Stop new jobs if necessary
[ ] Preserve evidence
[ ] Roll back application
[ ] Verify health
[ ] Verify database
[ ] Verify authentication
[ ] Verify authorization
[ ] Verify workers
[ ] Resume controlled traffic
240. Backup Checklist
[ ] Database backup completed
[ ] Backup integrity verified
[ ] Backup encrypted
[ ] Backup access restricted
[ ] Retention applied
[ ] Off-host copy verified
241. Restore Checklist
[ ] Identify incident
[ ] Stop affected services
[ ] Preserve evidence
[ ] Obtain approved backup
[ ] Verify backup integrity
[ ] Restore database
[ ] Verify migrations
[ ] Restore required evidence
[ ] Restore configuration
[ ] Rotate secrets if required
[ ] Start services
[ ] Verify authorization
[ ] Verify data isolation
[ ] Resume traffic
242. Security Baseline

Production deployment must satisfy:

secure transport
secure authentication
secure authorization
network isolation
secret protection
non-root execution
controlled filesystem access
controlled outbound network access
resource limits
logging
monitoring
backups
recovery
vulnerability management
243. Defense in Depth

No single infrastructure control may be considered sufficient.

Examples:

Firewall
+
Container network
+
Application SSRF validation
+
Target allowlist

provide stronger protection than any single layer.

244. Fail Closed

Security-sensitive infrastructure behavior should fail closed.

Examples:

missing target authorization -> deny
missing credential -> fail
invalid configuration -> fail startup
unknown target -> deny
invalid network destination -> deny
unauthorized evidence request -> deny
245. Availability vs Security

Availability must not automatically override security.

When a security control cannot be safely evaluated, the system should prefer:

safe failure
explicit error
audit event

over silently disabling the control.

246. Operational Simplicity

The initial deployment must remain operationally understandable.

Complexity must have a justified security or reliability benefit.

247. Open-Source Infrastructure

The deployment should prefer open-source infrastructure where practical.

This supports:

self-hosting
transparency
portability
cost control
community contribution
248. Zero-Cost Development

The architecture should remain usable without paid infrastructure during development.

Production hosting may require infrastructure costs, but the software stack itself should not require proprietary services.

249. VPS Resource Planning

Production capacity planning must consider:

CPU
RAM
storage
network bandwidth
database workload
worker concurrency
model traffic
evidence retention
250. Scaling Model

Initial deployment may scale vertically.

Future scaling may separate:

frontend
API
workers
database
evidence storage
observability
251. Horizontal Worker Scaling

Workers should eventually be horizontally scalable.

Scaling must preserve:

job ownership
idempotency
authorization
project isolation
resource budgets
252. API Scaling

The backend should be designed to support multiple API instances in the future.

Session state should not depend on local process memory where distributed deployment would require otherwise.

253. Database Scaling

PostgreSQL remains the source of truth.

Read replicas or other scaling mechanisms may be introduced later.

254. Evidence Scaling

Evidence storage may move from local persistent volumes to object storage at larger scale.

The security architecture must remain unchanged.

255. Worker Autoscaling

Autoscaling may be introduced later.

Autoscaling must respect target rate limits and resource budgets.

More workers must not automatically mean unlimited attack traffic.

256. Queue Backpressure

The system must implement backpressure where workloads exceed safe capacity.

257. Fair Scheduling

Job scheduling should prevent a single project or tenant from monopolizing all worker capacity.

258. Tenant Quotas

Production deployments should support configurable quotas for:

concurrent jobs
daily requests
storage
reports
evidence
API usage
259. Administrative Quotas

Administrative operations should also be bounded where expensive.

260. Abuse Prevention

The deployment must account for the possibility that a valid user account becomes abusive.

Authentication alone is insufficient.

Rate limits, quotas, audit logging, and authorization remain necessary.

261. External Target Protection

Aegis Vuldris must not unintentionally overwhelm authorized targets.

Target-specific request budgets and concurrency controls are required.

262. Legal and Authorization Boundary

Deployment infrastructure does not determine whether a target is legally authorized for testing.

Users remain responsible for authorization.

Aegis Vuldris must provide technical controls that support authorized use.

263. Production Security Documentation

The deployment security model must be documented for operators.

Operators must understand:

exposed ports
trust boundaries
secrets
network paths
database access
worker capabilities
evidence storage
backup architecture
264. Change Management

Infrastructure changes must be reviewed.

Security-sensitive changes require additional review.

265. Infrastructure ADR Changes

Material changes to production topology should result in a new ADR or amendment.

Examples:

Kubernetes adoption
new cloud-managed database
new external secret manager
new execution sandbox
new public service
new external telemetry provider
266. Operational Ownership

Production deployments must have clearly assigned operational ownership.

Ownership includes:

releases
backups
security updates
incident response
credential rotation
monitoring
267. On-Call Readiness

A production deployment should have an operational contact or escalation process.

268. Maintenance Windows

Planned maintenance should be communicated where appropriate.

269. Scheduled Maintenance

Scheduled maintenance may include:

OS updates
database maintenance
image updates
certificate rotation
backup verification
restore testing
270. Maintenance Security

Maintenance procedures must use the same authentication and authorization principles as normal operation.

271. Administrative CLI

If an administrative CLI is introduced, it must:

require explicit authorization
avoid printing secrets
use safe defaults
log sensitive operations
validate input
272. Production Shell Access

Direct shell access to application containers should be restricted.

Administrative debugging should prefer controlled observability mechanisms.

273. Debugging

Debugging production systems must not require enabling global debug mode.

Temporary diagnostics must be controlled and removed afterward.

274. Support Access

Support personnel should receive the minimum access necessary.

Sensitive evidence access must be separately controlled.

275. Data Export

Production data exports must be:

authorized
audited
bounded
protected
retention-controlled
276. Data Import

Imports must be validated.

Imported configuration or test data must not automatically grant permissions or execute code.

277. Import Isolation

Imported files must not be executed.

278. Database Import

Database restore/import procedures must be performed only through controlled administrative workflows.

279. Configuration Import

Configuration imports must pass schema validation.

Secrets must not be exposed in validation errors.

280. Disaster Recovery Exercises

Recovery procedures should be exercised periodically.

281. Security Drills

Production teams should periodically test:

credential compromise response
database recovery
application rollback
worker shutdown
target access revocation
282. Backup Retention

Backup retention must balance:

recovery requirements
storage cost
privacy
deletion obligations
283. Evidence Retention

Evidence retention follows ADR-012.

Infrastructure must not keep indefinite copies merely because storage is available.

284. Log Retention

Log retention follows ADR-013.

Security logs require sufficient retention for investigation while respecting privacy.

285. Telemetry Retention

Telemetry should use bounded retention.

High-volume telemetry should not consume unlimited storage.

286. Database Retention

Database cleanup jobs must be controlled and authorization-aware.

287. Cleanup Jobs

Cleanup jobs must never delete data outside their authorized scope.

288. Cleanup Auditability

Sensitive deletion operations should be auditable.

289. Secure Deletion

Deletion procedures should address:

primary records
evidence
backups
caches
temporary files
indexes
derived artifacts

where required by the retention policy.

290. Production Readiness

A feature is not production-ready merely because it works locally.

Production readiness requires:

security
observability
resource control
recoverability
configuration management
documentation
testing
291. Local-to-Production Parity

Development should approximate production architecture where practical.

Differences must be intentional and documented.

292. Docker Compose Development

Local Docker Compose may provide:

PostgreSQL
backend
frontend
worker
observability services where useful
293. Production Compose

Production Compose configuration must not inherit development settings that weaken security.

294. Development Debugging

Development conveniences such as:

hot reload
verbose errors
unrestricted CORS
mock credentials

must not leak into production.

295. Production Environment Name

Production must be explicitly identified.

The application must not infer production solely from the hostname.

296. Secure Environment Defaults

Unknown or invalid environments should not silently use production credentials.

297. Configuration Validation Tests

Configuration validation should have automated tests covering:

missing values
invalid values
secret handling
environment differences
secure production defaults
298. Deployment Tests

Deployment automation should include tests for:

startup
health
database connectivity
migrations
worker connectivity
authentication
authorization
299. Security Regression Tests

Infrastructure security controls must have regression tests.

300. Infrastructure Test Categories

Test categories should include:

container security
network security
authentication
authorization
secret handling
TLS
database security
backup
recovery
resource limits
301. Smoke Test Target

Smoke tests must use an explicitly controlled test target.

302. Production Test Data

Production smoke tests should minimize persistent data.

303. Production Test Isolation

Production smoke-test resources should use dedicated identifiers where possible.

304. Operational Metrics

Metrics should enable detection of degradation before complete failure.

305. SLOs

Future production deployments may define Service Level Objectives for:

API availability
API latency
job completion
worker availability
backup success

Exact SLO values are deployment-specific.

306. Error Budgets

Future operational maturity may use error budgets.

307. Capacity Alerts

Capacity thresholds should be configured before resources are exhausted.

308. Storage Alerts

Storage warnings should occur before critical exhaustion.

309. Memory Alerts

Memory pressure should trigger operational investigation.

310. CPU Alerts

Sustained high CPU should trigger capacity or workload investigation.

311. Queue Alerts

Large queue depth should trigger investigation.

312. Worker Alerts

Repeated worker failure should trigger investigation.

313. Database Alerts

Database connection exhaustion and storage exhaustion must trigger alerts.

314. Certificate Alerts

Certificate expiration warnings should occur well before expiry.

315. Backup Alerts

Backup failure must produce an alert.

316. Restore Alerts

Failed restore tests must produce an operational finding.

317. Security Alerts

Security-critical audit events may produce alerts depending on deployment policy.

318. Alert Fatigue

Alerts should be actionable.

Excessive low-value alerts reduce security effectiveness.

319. Alert Privacy

Alert content must remain privacy-safe.

320. Observability Failure

Failure of optional observability infrastructure must not silently disable core security controls.

321. Audit Failure

If a mandatory security audit operation cannot be recorded, sensitive administrative operations should fail safely where practical.

322. Backup Failure

Backup failure must not be silently ignored.

323. Certificate Failure

Certificate renewal failure must be operationally visible.

324. Database Failure

Database unavailability must fail API operations safely.

325. Worker Failure

Worker failure must not expose internal state to users.

326. Queue Failure

Queue failure must preserve job consistency.

327. Model Target Failure

Target failures must not expose credentials or internal network details.

328. External Network Failure

External network failures must have bounded retries.

329. Retry Storm Prevention

Retries must use:

limits
backoff
jitter where appropriate
cancellation
budgets
330. Circuit Breaking

Circuit breakers may be introduced for unstable external dependencies.

331. Dependency Isolation

Failure of one external model provider should not necessarily make the entire platform unavailable.

332. Provider Credentials

Provider credentials must be isolated by target/provider configuration.

333. Provider Rate Limits

External providers may impose rate limits.

Aegis Vuldris must respect provider policies and configured limits.

334. Target Quotas

Target-specific quotas should prevent accidental excessive testing.

335. Cost Controls

Although the core platform is open source, external model providers may incur costs.

The system should support request/token budgets where available.

336. Budget Enforcement

Budget enforcement should occur before expensive operations where practical.

337. Budget Exhaustion

When a budget is exhausted, the job should stop safely and record the termination reason.

338. Long-Running Resource Leaks

Workers must release:

database connections
network connections
temporary files
locks
memory
telemetry spans

after jobs finish.

339. Process Isolation

One failed test should not corrupt another test's persistent state.

340. Job Isolation

Each job must have explicit:

project
target
authorization
budget
evidence
configuration

context.

341. Worker Identity

Workers should have explicit service identity where required.

342. Service-to-Service Authentication

Internal services may require service authentication where network trust alone is insufficient.

343. Internal API Security

Internal APIs must still validate callers.

Internal network location does not equal authorization.

344. Service Identity Rotation

Service credentials must support rotation.

345. Service Authorization

Backend-to-worker operations must use least privilege.

346. Database Service Identity

Database credentials must identify the service role.

347. Audit Service Identity

Administrative operations must preserve the initiating identity where possible.

348. Job Identity

Jobs must preserve the initiating user/service identity.

349. Attack Identity

Attack executions must preserve the initiating authorization context.

350. Evidence Identity

Evidence access must preserve the requesting identity.

351. Report Identity

Report generation and access must preserve identity.

352. Trace Identity

Trace correlation must not expose sensitive identity attributes unnecessarily.

353. Tenant-Aware Telemetry

Telemetry correlation should preserve tenant isolation.

354. Operational Metrics and Tenants

Tenant identifiers should be used in metrics only when cardinality and privacy are controlled.

355. Security Event Correlation

Security events should support correlation across:

request
  ->
job
  ->
test
  ->
attack
  ->
evaluation
  ->
finding
356. Deployment Correlation

Operational events should identify the deployed release.

357. Incident Correlation

Incidents should be traceable to:

release
configuration
target
job
service
358. Configuration Audit

Security-sensitive configuration changes should record:

actor
timestamp
affected scope
change type
result

Secrets themselves must not be logged.

359. Infrastructure Audit

Infrastructure changes should be traceable through deployment systems or configuration management.

360. Administrative Operations

Administrative operations must not rely on obscurity.

361. Least Privilege

Every production component should receive the minimum:

network
filesystem
database
credential
CPU
memory

required.

362. Default Deny

The default policy is deny unless access is explicitly required.

363. Trust Boundaries

The production architecture preserves trust boundaries between:

Internet
reverse proxy
frontend
backend
workers
database
target models
tools
filesystem
observability
administrators
364. Untrusted Target Output

Model output remains untrusted even inside production infrastructure.

365. Untrusted User Input

User input remains untrusted even after authentication.

366. Untrusted Model Input

Target input/output must not be assumed trustworthy.

367. Untrusted Telemetry

External telemetry systems remain separate trust boundaries.

368. Untrusted Files

Uploaded files remain untrusted.

369. Untrusted Reports

Generated reports must be treated as potentially sensitive artifacts.

370. Production Security Invariants

The following invariants are mandatory.

Invariant 1

The production database must not be publicly accessible.

Invariant 2

Production secrets must not exist in source control.

Invariant 3

Production secrets must not exist in container images.

Invariant 4

Application containers must not require root privileges by default.

Invariant 5

The Docker socket must not be exposed to application containers.

Invariant 6

Debug mode must be disabled in production.

Invariant 7

External application traffic must use HTTPS.

Invariant 8

Unauthorized users must not access protected resources.

Invariant 9

Tenant boundaries must be enforced by the application.

Invariant 10

Project boundaries must be enforced by the application.

Invariant 11

Worker services must not be publicly exposed unless explicitly required.

Invariant 12

Arbitrary shell execution must be disabled by default.

Invariant 13

Arbitrary code execution must be disabled by default.

Invariant 14

Outbound network access must be controlled.

Invariant 15

SSRF protections must exist independently of network segmentation.

Invariant 16

Security-sensitive jobs must have bounded resources.

Invariant 17

External target requests must have bounded timeouts.

Invariant 18

External target requests must have bounded response sizes.

Invariant 19

Sensitive evidence must not be placed into ordinary logs by default.

Invariant 20

Credentials must not appear in telemetry.

Invariant 21

Health endpoints must not expose secrets.

Invariant 22

Production backups must be protected.

Invariant 23

Backups must be periodically tested.

Invariant 24

Database migrations must be controlled.

Invariant 25

Production releases must be traceable to known source revisions.

Invariant 26

Critical security checks must be part of the release process.

Invariant 27

A failed optional observability service must not disable core security controls.

Invariant 28

Audit records must be protected from unauthorized modification.

Invariant 29

Administrative operations must be auditable.

Invariant 30

A deployment must have a documented rollback or recovery strategy.

Invariant 31

A worker must not bypass application authorization.

Invariant 32

A model must never be treated as an infrastructure security boundary.

Invariant 33

The infrastructure must not silently disable security controls for availability.

Invariant 34

Production configuration must fail safely when required security settings are invalid.

Invariant 35

The platform must not generate uncontrolled traffic against targets.

371. Production Architecture Acceptance Criteria

ADR-015 is considered implemented when:

A production Docker Compose topology exists.
HTTPS is configured.
Public ports are minimized.
PostgreSQL is isolated.
Backend deployment is production-safe.
Worker deployment is isolated.
Secrets are injected securely.
Containers run with least privilege.
Resource limits exist.
Health checks exist.
Readiness checks exist.
Database migrations are controlled.
Backups are automated.
Restore procedures are documented.
Observability is configured.
Audit logging is configured.
Debug mode is disabled.
CORS is restricted.
Authentication is enabled.
Authorization is enforced.
Target access is controlled.
SSRF defenses are active.
Outbound network policy exists.
Security scanning exists.
Deployment releases are traceable.
Rollback procedures are documented.
Incident response procedures exist.
Configuration validation exists.
Production smoke tests exist.
Security regression tests exist.
372. Implementation Order

Production implementation should follow a controlled sequence.

Step 1

Create production Dockerfiles.

Step 2

Create development and production Compose configurations.

Step 3

Implement backend production startup.

Step 4

Implement frontend production build.

Step 5

Implement worker production execution.

Step 6

Configure PostgreSQL persistence.

Step 7

Configure internal networks.

Step 8

Configure reverse proxy.

Step 9

Configure HTTPS.

Step 10

Configure production secrets.

Step 11

Configure resource limits.

Step 12

Configure health and readiness.

Step 13

Configure database migrations.

Step 14

Configure backups.

Step 15

Configure observability.

Step 16

Configure security scanning.

Step 17

Configure CI/CD.

Step 18

Perform deployment smoke tests.

Step 19

Perform infrastructure security tests.

Step 20

Perform recovery testing.

Step 21

Document runbooks.

Step 22

Complete production readiness review.

373. Initial Production MVP

The minimum production deployment should contain:

Reverse Proxy
      |
      v
Frontend
      |
      v
Backend API
      |
      +---- PostgreSQL
      |
      +---- Worker
      |
      +---- Authorized Model Targets

with:

HTTPS
authentication
authorization
database isolation
secure secrets
health checks
resource limits
logging
audit events
backups
374. Future Production Enhancements

Future architecture may add:

Kubernetes
OpenTofu/Terraform
Ansible
managed PostgreSQL
object storage
dedicated queue infrastructure
autoscaling
distributed workers
service mesh
dedicated execution sandbox
hardware isolation
advanced WAF
advanced SIEM integration
release signing
workload identity
confidential computing

Each significant addition requires security review.

375. Alternatives Considered
Alternative A: Kubernetes from the beginning

Rejected for initial deployment due to unnecessary operational complexity.

Alternative B: Serverless architecture

Rejected because long-running security tests and worker execution require controlled execution environments.

Alternative C: Managed cloud-only services

Rejected as the primary architecture because they reduce self-hostability and increase vendor dependency.

Alternative D: Bare-metal application installation

Rejected as the primary deployment method because containers improve reproducibility and environment consistency.

Alternative E: Single all-in-one container

Rejected because it weakens service isolation and makes scaling and operational security harder.

376. Consequences
Positive consequences
predictable deployment
VPS compatibility
self-hostability
reproducibility
clear trust boundaries
controlled networking
simpler initial operations
easier development/production parity
better disaster recovery
improved security posture
Negative consequences
operational responsibility remains with the deployment owner
Docker security must be maintained
backups require operational discipline
production deployment is more complex than local development
external model providers may introduce additional cost
scaling beyond one VPS will require additional architecture
377. Relationship to Previous ADRs

ADR-015 depends on:

ADR-001 for backend architecture
ADR-002 for frontend architecture
ADR-003 for database architecture
ADR-004 for API communication
ADR-005 for jobs
ADR-006 for authentication and authorization
ADR-007 for model target integration
ADR-008 for evidence and reporting
ADR-009 for risk scoring
ADR-010 for security tests and evaluation
ADR-011 for attack orchestration
ADR-012 for privacy and sensitive data
ADR-013 for observability
ADR-014 for configuration and secrets

ADR-015 provides the operational environment in which those architectures run.

378. Architecture Boundary

ADR-015 does not define:

individual API endpoints
database schemas
detailed authentication flows
attack algorithms
evaluator algorithms
risk formulas
privacy detection algorithms
UI design

Those remain governed by their respective architectural decisions.

379. Security Boundary

Infrastructure must never become a justification for weakening application controls.

For example:

"PostgreSQL is private"

does not mean:

"Authorization is unnecessary."

Likewise:

"The worker is inside Docker"

does not mean:

"Untrusted code is safe to execute."
380. Operational Boundary

The production environment is responsible for:

secure hosting
networking
container lifecycle
persistence
backups
monitoring
deployment
recovery

The application remains responsible for:

authentication
authorization
data isolation
input validation
target authorization
security testing logic
evidence handling
risk evaluation
381. Core Deployment Principle

The production deployment must be:

Secure by default, reproducible, observable, recoverable, minimally exposed, least-privileged, and independent of developer infrastructure.

382. Final Decision

Aegis Vuldris will use a Docker-based, VPS-compatible production architecture with:

reverse-proxy HTTPS
containerized frontend
containerized FastAPI backend
isolated worker execution
private PostgreSQL
explicit network segmentation
controlled outbound target access
secure secret injection
resource limits
health/readiness checks
structured observability
protected audit logging
automated backups
tested recovery
controlled migrations
CI/CD security gates
vulnerability scanning
traceable releases
documented rollback
documented incident response

The architecture is intentionally simple enough for self-hosting while establishing the security and operational foundations required for future scale.

383. Final Security Principle

Aegis Vuldris must never become insecure merely because it is deployed.

Production infrastructure must preserve every security boundary established by the application architecture.

The deployment must fail safely, expose minimally, recover predictably, and remain observable.

Status: Accepted.

384. Implementation Gate

ADR-015 authorizes implementation of the production deployment architecture.

Implementation must not proceed directly to production without completing:

configuration validation
secret protection
container hardening
network isolation
HTTPS
database protection
backup verification
health checks
observability
authentication
authorization
security regression testing
deployment smoke testing
rollback preparation

Only after these controls are verified should Aegis Vuldris be considered ready for production deployment.
