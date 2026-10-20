# ADR-013: Observability, Audit Logging & Telemetry Architecture

**Status:** Accepted
**Date:** 2026-09-10
**Decision Owners:** Aegis Vuldris Maintainers
**Scope:** Backend services, frontend telemetry, API requests, model adapters, test execution, attack orchestration, evaluation, evidence, findings, authentication, authorization, administration, jobs, workers, database operations, security events, and production operations

---

## 1. Decision Summary

Aegis Vuldris will implement a structured, security-aware observability architecture covering application logging, security audit logging, metrics, distributed tracing, health telemetry, test execution telemetry, model interaction telemetry, job/worker telemetry, and operational diagnostics.

Observability is treated as a security control rather than merely a debugging convenience.

The architecture will:

1. Use structured logs instead of uncontrolled free-form logging.
2. Separate operational/application logs from security audit events.
3. Provide request, execution, job, target, test, evaluation, and finding correlation identifiers.
4. Use UTC timestamps consistently.
5. Support metrics suitable for Prometheus-compatible monitoring.
6. Support OpenTelemetry-compatible traces and instrumentation.
7. Prevent secrets and sensitive assessment content from being emitted accidentally.
8. Apply explicit redaction and data-minimization policies.
9. Preserve sufficient audit evidence for security-sensitive actions.
10. Maintain project, tenant, target, job, and user isolation in telemetry.
11. Prevent log injection and structured-log corruption.
12. Treat model-generated output as untrusted telemetry input.
13. Prevent attackers from disabling or manipulating required security audit events through model output.
14. Make observability failures fail safely without becoming an authorization bypass.
15. Support local development without requiring a paid external monitoring service.
16. Support production deployments using open-source observability components.
17. Keep observability implementation independent from the security boundary of the application.
18. Avoid making a model, evaluator, or external telemetry service the sole source of truth for security decisions.
19. Support controlled retention and deletion of telemetry.
20. Make security-sensitive administrative actions auditable.

The primary architectural principle is:

> Aegis Vuldris must be observable without exposing the information it is responsible for protecting.

---

## 2. Context

Aegis Vuldris executes security assessments against AI systems.

The platform can process:

- user accounts;
- projects;
- targets;
- target configurations;
- API credentials;
- prompts;
- generated attack inputs;
- target model responses;
- tool outputs;
- retrieved documents;
- evaluation results;
- evidence;
- findings;
- risk scores;
- reports;
- job state;
- security events;
- administrative actions;
- configuration changes;
- authentication events;
- authorization failures;
- network activity;
- model adapter failures;
- worker failures;
- database operations.

These data types have different security and privacy characteristics.

Traditional application logging is insufficient because blindly logging request and response bodies can create a secondary data-leakage system.

For example, a target response may contain:

- API keys;
- passwords;
- personal information;
- proprietary documents;
- credentials;
- hidden prompts;
- system instructions;
- customer information;
- database records;
- synthetic canaries;
- secrets deliberately planted for security testing.

Therefore logging must not simply capture everything.

At the same time, insufficient logging can make it impossible to investigate:

- unauthorized access;
- privilege escalation;
- test execution;
- evidence manipulation;
- target configuration changes;
- secret access;
- failed authentication;
- repeated authorization failures;
- suspicious job activity;
- destructive test attempts;
- security control bypasses;
- data leakage;
- model adapter failures;
- administrative changes.

Aegis Vuldris therefore requires an explicit observability architecture.

---

## 3. Relationship to Other ADRs

This ADR depends on and complements:

- ADR-005 — Test Execution and Job Architecture
- ADR-006 — Authentication and Authorization Architecture
- ADR-007 — Model Adapter and Target Integration Architecture
- ADR-008 — Evidence, Findings and Reporting Architecture
- ADR-009 — Risk Scoring and Severity Assessment Architecture
- ADR-010 — Security Test Suite and Evaluation Architecture
- ADR-011 — Attack Orchestration and Multi-Turn Execution
- ADR-012 — Privacy, Data Leakage and Sensitive Data Handling

This ADR does not replace those decisions.

It defines how operational, security, and diagnostic telemetry is generated, protected, correlated, stored, transported, queried, retained, and exposed.

---

## 4. Goals

The observability architecture must provide:

- operational visibility;
- security auditability;
- debugging capability;
- performance visibility;
- test execution visibility;
- worker visibility;
- model adapter visibility;
- failure diagnosis;
- request correlation;
- job correlation;
- security-event detection;
- production diagnostics;
- privacy-aware telemetry;
- reliable audit records;
- metrics;
- traces;
- health checks;
- controlled retention;
- secure access.

---

## 5. Non-Goals

This ADR does not define:

- the complete SIEM architecture;
- a commercial monitoring provider;
- a complete incident-response program;
- legal compliance certification;
- a specific production hosting provider;
- a specific cloud vendor;
- a replacement for database auditing;
- a replacement for application authorization;
- a replacement for evidence storage;
- a replacement for security testing.

Observability provides supporting security evidence and operational visibility.

It is not the application security boundary.

---

## 6. Core Principles

### 6.1 Security First

Telemetry must not weaken application security.

### 6.2 Data Minimization

Only information required for the intended observability purpose should be recorded.

### 6.3 Structured Data

Machine-readable structured events are preferred over arbitrary strings.

### 6.4 Correlation

Related activity must be traceable through stable identifiers.

### 6.5 Untrusted Inputs

User input and model-generated content must be treated as untrusted telemetry data.

### 6.6 Explicit Classification

Sensitive fields must have explicit logging policies.

### 6.7 Defense in Depth

Multiple observability layers should exist where appropriate.

### 6.8 Fail Safely

Telemetry failures must not automatically disable authorization or security controls.

### 6.9 Least Privilege

Access to audit and diagnostic telemetry must itself be authorized.

### 6.10 Reproducibility

Security-relevant execution telemetry should support reconstruction of what happened without unnecessarily storing sensitive payloads.

---

## 7. Observability Domains

Aegis Vuldris will distinguish at least these telemetry domains:

1. Application logs
2. Security audit events
3. Authentication events
4. Authorization events
5. API request telemetry
6. Model adapter telemetry
7. Test execution telemetry
8. Attack orchestration telemetry
9. Evaluation telemetry
10. Evidence telemetry
11. Finding telemetry
12. Job/worker telemetry
13. Database telemetry
14. Network telemetry
15. Performance metrics
16. Health telemetry
17. Configuration-change telemetry
18. Administrative telemetry
19. Deployment telemetry
20. Error telemetry

---

## 8. Telemetry Classes

Telemetry will be categorized as:

- DEBUG
- INFO
- NOTICE
- WARNING
- ERROR
- CRITICAL
- SECURITY

The severity of a log record must describe the event, not merely the HTTP status code.

A failed user request is not automatically a security event.

A successful unauthorized operation attempt must be treated as a security-critical condition even if the application subsequently blocks it.

---

## 9. Structured Logging

Application logs will use structured records.

Preferred format:

```json
{
  "timestamp": "2026-09-10T12:00:00Z",
  "level": "INFO",
  "event": "test_execution_started",
  "service": "aegis-backend",
  "environment": "development",
  "request_id": "req_...",
  "job_id": "job_...",
  "project_id": "project_...",
  "target_id": "target_..."
}

The exact production serialization format may evolve, but semantic fields must remain stable.

10. Required Common Log Fields

Where applicable, structured application logs should support:

timestamp;
level;
event name;
service;
environment;
request ID;
trace ID;
span ID;
user ID;
project ID;
tenant ID;
target ID;
job ID;
test execution ID;
attack execution ID;
evaluation ID;
finding ID;
component;
operation;
duration;
outcome;
error type;
status code;
source;
version.

Not every event should contain every field.

Unused identifiers must not be fabricated.

11. Timestamp Requirements

All server-generated timestamps will use UTC.

Timestamps should be machine-readable and timezone-aware.

Naive local timestamps must not be used for security audit events.

The canonical representation should be ISO 8601-compatible.

Example:

2026-09-10T12:00:00.123Z

Clock synchronization is an operational concern for distributed deployments.

12. Event Naming

Event names should:

be stable;
be machine-readable;
use a consistent naming convention;
describe what happened;
avoid embedding arbitrary user input.

Examples:

auth.login.succeeded
auth.login.failed
auth.logout
auth.authorization.denied
project.created
project.updated
target.created
target.connection.failed
job.created
job.started
job.completed
job.failed
test.started
test.completed
attack.started
attack.turn.completed
evaluation.completed
finding.created
report.generated
configuration.changed
secret.access.denied

The implementation may use another consistent naming convention, but event semantics must remain stable.

13. Log Levels
DEBUG

Developer diagnostics that are normally disabled in production.

INFO

Normal application lifecycle information.

NOTICE

Significant but non-error operational events.

WARNING

Unexpected conditions that did not necessarily cause failure.

ERROR

Operation failures requiring attention.

CRITICAL

Severe failures affecting service integrity or availability.

SECURITY

Security-relevant events requiring audit or investigation.

Security events must not rely exclusively on a configurable verbosity level.

Required security audit events must remain enabled.

14. Security Audit Logging

Security audit logging is distinct from normal application logging.

Audit events include:

authentication attempts;
authentication failures;
logout;
credential changes;
password-reset actions;
API-key creation;
API-key revocation;
authorization failures;
role changes;
permission changes;
project membership changes;
target ownership changes;
secret access;
secret configuration changes;
destructive operations;
administrative actions;
evidence access;
evidence deletion;
report access;
security configuration changes;
policy changes;
retention changes;
job cancellation;
privileged test execution.
15. Audit Event Requirements

An audit event should capture:

who performed the action;
what action occurred;
what resource was affected;
when it occurred;
whether it succeeded;
relevant request/trace correlation;
authorization context where appropriate;
source context where appropriate;
failure reason category where safe.

Audit logs must not contain plaintext passwords, API keys, access tokens, session tokens, or other secrets.

16. Authentication Telemetry

Authentication events include:

login success;
login failure;
logout;
session creation;
session expiration;
token issuance;
token revocation;
password change;
password-reset request;
password-reset completion;
API-key authentication;
authentication lockout or throttling.

Sensitive authentication material must never be logged.

17. Authorization Telemetry

Authorization failures must be observable.

Examples:

insufficient role;
missing permission;
cross-project access;
cross-tenant access;
object-level authorization failure;
unauthorized evidence access;
unauthorized target access;
unauthorized job control.

Authorization events should identify the resource type and resource identifier where safe.

They must not expose protected resource contents.

18. Object-Level Authorization Logging

When access to a resource is denied because the resource belongs to another project or tenant, the telemetry must not reveal sensitive information about the protected resource.

The event may record:

resource_type=target
authorization_result=denied
reason=resource_scope_violation

It must not expose the hidden target's secret configuration or sensitive metadata.

19. Request Correlation

Every externally initiated backend request should receive a request correlation ID.

If a trusted upstream request ID is accepted, the application must validate and safely normalize it before use.

Otherwise Aegis Vuldris generates a new identifier.

Correlation identifiers must not contain secrets.

20. Trace Correlation

Where distributed tracing is enabled, request IDs should correlate with:

trace IDs;
span IDs;
job IDs;
test execution IDs;
attack execution IDs.

Correlation must not require putting sensitive data into trace attributes.

21. Trace Attributes

Trace attributes should describe:

service;
operation;
component;
route;
status;
duration;
identifiers;
bounded technical metadata.

Trace attributes must not contain:

passwords;
API keys;
access tokens;
raw prompts;
raw model responses;
private documents;
full headers;
cookies;
authorization credentials.

Unless an explicit controlled security-testing workflow requires otherwise.

22. OpenTelemetry

Aegis Vuldris will design instrumentation to be compatible with OpenTelemetry.

OpenTelemetry may provide:

traces;
metrics;
logs;
context propagation.

The implementation should prefer open standards over proprietary telemetry APIs.

Local development should not require a paid telemetry provider.

23. Metrics

Metrics provide aggregated operational information without requiring storage of full request content.

Metrics should cover:

request count;
request latency;
request failures;
authentication failures;
authorization failures;
active jobs;
job duration;
job failures;
test execution count;
test execution duration;
evaluation count;
evaluation errors;
model adapter request count;
model adapter latency;
model adapter failures;
target timeout count;
retry count;
cancellation count;
queue depth;
worker utilization;
database latency;
database errors;
network failures;
report generation duration.
24. Metric Cardinality

Metric labels must be bounded.

Unbounded values must not become metric labels.

Examples of unsafe labels include:

arbitrary prompts;
model responses;
user-provided URLs;
raw error messages;
arbitrary target names;
request IDs;
finding titles;
arbitrary file paths.

High-cardinality identifiers belong in logs or traces when appropriate, not uncontrolled metric labels.

25. Security Metrics

Security metrics may include:

authentication failures;
authorization denials;
privilege-change events;
secret access attempts;
suspicious request rates;
blocked SSRF attempts;
blocked private-network requests;
blocked command-execution attempts;
blocked filesystem operations;
blocked unsafe plugin operations;
security-test failures;
evaluator errors;
suspicious job cancellation;
repeated failed privileged operations.

Metrics should aggregate rather than expose sensitive payloads.

26. Health Checks

Aegis Vuldris will provide health information appropriate for deployment and operations.

At minimum, conceptual health states include:

process health;
application readiness;
database availability;
worker availability where applicable;
dependency readiness where required.

Health endpoints must not expose:

secrets;
database credentials;
environment variables;
detailed internal topology;
protected target configurations.
27. Liveness and Readiness

Liveness indicates whether a process is alive.

Readiness indicates whether the service can accept work.

These concepts must remain separate.

A database outage should not necessarily cause a liveness failure.

A service unable to safely process authenticated application requests may report readiness failure.

28. Dependency Health

External dependency health checks must be designed carefully.

A health check must not:

send sensitive data;
trigger expensive model calls unnecessarily;
execute arbitrary tools;
access protected customer resources;
bypass authorization.

Health checks should use controlled endpoints or lightweight synthetic checks.

29. Model Adapter Telemetry

Model adapter operations are observable at the metadata level.

Useful telemetry includes:

adapter type;
provider category;
target ID;
request duration;
response duration;
timeout;
retry count;
HTTP status category;
error category;
token usage where safely available;
model identifier where appropriate;
connection status.

Raw prompt and response bodies should not be logged by default.

30. Model Request Logging

Raw model requests are considered potentially sensitive.

Default behavior:

raw_prompt_logging = disabled
raw_response_logging = disabled

Controlled security-test workflows may preserve prompt/response content as evidence through ADR-008 mechanisms.

That evidence must not automatically leak into ordinary application logs.

31. Model-Generated Content Is Untrusted

Model outputs may contain:

fake log records;
terminal escape sequences;
JSON fragments;
misleading event names;
injected URLs;
fabricated identifiers;
fake severity values;
newline characters;
control characters.

Model output must never be interpreted as trusted logging metadata.

32. Log Injection Protection

User and model-controlled values must be safely encoded before being emitted.

Structured logging libraries should be preferred.

The application must avoid constructing log lines by direct string concatenation with untrusted content.

Newline and control-character injection must be handled safely.

33. Terminal Escape Protection

Logs displayed in terminals must not allow attacker-controlled values to manipulate the terminal.

Control sequences must be escaped or removed according to the output context.

This is especially important for:

prompts;
model responses;
URLs;
tool output;
file names;
exception messages.
34. Exception Logging

Exceptions should log:

exception category;
safe message;
operation;
correlation identifiers;
stack trace where appropriate.

Exceptions must not automatically serialize arbitrary request objects.

35. Sensitive Exception Data

Exception messages can contain secrets.

Examples:

database connection strings;
authorization headers;
filesystem paths;
request bodies;
API credentials;
SQL statements containing parameters.

Sensitive exceptions must be sanitized before emission.

36. Secret Redaction

The observability layer must support centralized secret redaction.

Potential sensitive values include:

passwords;
API keys;
bearer tokens;
cookies;
session tokens;
private keys;
database credentials;
cloud credentials;
webhook secrets;
signing keys.

The exact redaction implementation may evolve.

The policy must remain centralized.

37. Redaction Before Logging

Sensitive values should be removed or masked before reaching the logger.

Redaction at the final storage layer alone is insufficient because the secret may already have passed through:

process memory;
log buffers;
collectors;
agents;
network transport;
telemetry exporters.
38. Partial Secret Display

Where debugging requires identification of a credential, a controlled fingerprint or bounded prefix/suffix may be used only when justified.

Full secrets must never be logged.

Example:

api_key=REDACTED

is preferred.

39. Request Header Logging

HTTP request headers must not be logged wholesale.

Particularly sensitive headers include:

Authorization;
Cookie;
Set-Cookie;
Proxy-Authorization;
API-key headers;
custom credential headers.

Only explicitly allowlisted non-sensitive headers may be logged.

40. Request Body Logging

Request bodies are disabled by default for ordinary application logs.

If a request body is required for security evidence, it must use the evidence architecture.

Logging and evidence are separate storage purposes.

41. Response Body Logging

Response bodies are disabled by default for ordinary application logs.

Target responses may contain sensitive information.

Security-test evidence may preserve selected response content according to ADR-008 and ADR-012.

42. Prompt Logging

Prompts may contain:

secrets;
proprietary instructions;
personal information;
customer content;
synthetic canaries.

Therefore prompt logging requires explicit policy.

43. Response Logging

Model responses must be treated as sensitive by default.

Logging only the response length, status, evaluator result, or safe fingerprint is preferred for operational telemetry.

44. Evidence Versus Logs

Evidence is a security-testing artifact.

Logs are operational/audit telemetry.

Aegis Vuldris must not use logs as a substitute for evidence storage.

Evidence may contain data that must never appear in normal logs.

45. Evidence References

Operational logs may contain:

evidence_id
finding_id
test_execution_id

rather than duplicating full evidence payloads.

This provides correlation while preserving data minimization.

46. Finding Telemetry

Finding events may include:

finding ID;
project ID;
target ID;
category;
severity;
risk score;
status;
lifecycle transition.

They should not automatically include complete evidence.

47. Risk Telemetry

Risk telemetry may include:

risk score;
severity;
confidence;
risk calculation version;
risk state;
scoring outcome.

Raw sensitive observations should remain in controlled evidence storage.

48. Test Execution Telemetry

Test execution events should include:

test execution ID;
test ID;
test version;
project;
target;
job;
start time;
completion time;
duration;
outcome;
evaluation state;
error category.
49. Attack Execution Telemetry

Attack orchestration events should include:

attack execution ID;
attack plan ID;
target ID;
job ID;
turn number;
branch identifier where applicable;
execution state;
budget state;
termination reason.

Raw attack content must not be emitted automatically.

50. Multi-Turn Telemetry

For multi-turn attacks, telemetry should permit reconstruction of:

turn order;
turn count;
state transitions;
branch selection;
termination;
evaluator outcomes;
resource consumption.

The telemetry must not expose protected content unnecessarily.

51. Job Telemetry

Jobs should emit lifecycle events:

job.created
job.queued
job.started
job.progress
job.cancel_requested
job.cancelled
job.completed
job.failed
job.expired

Progress telemetry should be bounded and non-sensitive.

52. Worker Telemetry

Workers should expose:

worker startup;
worker shutdown;
job acquisition;
job completion;
job failure;
heartbeat;
capacity;
concurrency;
retry;
cancellation.

Worker logs must not expose secrets from job payloads.

53. Job Ownership

Telemetry must preserve job ownership context.

Where applicable:

project ID;
tenant ID;
initiating user ID;
target ID.

This supports investigation and authorization-aware auditing.

54. Job Isolation

A job belonging to one project or tenant must not cause telemetry from another project or tenant to become visible through normal application interfaces.

Telemetry queries must enforce the same resource isolation principles as application data.

55. Audit Access

Audit logs themselves are sensitive.

Access must require authorization.

Users must not automatically receive access to global security telemetry simply because they can create tests.

56. Administrative Telemetry Access

Administrative access to audit and operational telemetry must itself be auditable.

Examples:

audit_log.accessed
audit_log.exported
audit_log.search_performed
audit_log.retention_changed
57. Telemetry Export

Telemetry exported to external systems must be explicitly configured.

The default development architecture should favor local/open-source destinations.

External telemetry must not silently receive:

model prompts;
model responses;
secrets;
private evidence;
personal data.
58. External Telemetry Providers

If an external telemetry backend is used, Aegis Vuldris must treat it as a separate trust boundary.

The deployment must explicitly define:

data transmitted;
purpose;
retention;
access control;
encryption;
geographic considerations where applicable;
deletion behavior;
failure behavior.
59. Local-First Observability

Development must support local observability without requiring:

paid SaaS;
proprietary monitoring systems;
externally hosted log ingestion.

Suitable open-source components may be introduced later.

60. Prometheus-Compatible Metrics

Metrics should be designed to be compatible with Prometheus-style collection.

The application should expose metrics through a controlled endpoint or exporter architecture.

Metrics endpoints must not expose sensitive application state.

61. OpenTelemetry Tracing

Tracing should support:

inbound API requests;
database interactions;
model adapter calls;
test execution;
evaluation;
attack orchestration;
report generation;
background jobs.

Tracing should be sampled appropriately in production.

62. Trace Sampling

Tracing can generate substantial telemetry.

Production deployments may use:

head sampling;
tail sampling;
error-biased sampling;
security-event sampling.

Security audit events must not disappear merely because tracing is sampled.

Audit logging and tracing are separate mechanisms.

63. Audit Reliability

Required security audit events should be emitted through a mechanism designed for durable handling.

A temporary telemetry collector outage must not silently erase critical security events where durable auditing is required.

64. Audit Delivery Failure

If audit storage becomes unavailable, the application must follow an explicit policy.

For critical security-sensitive operations, possible safe behavior includes:

reject the operation;
queue the audit event locally;
enter a degraded mode;
allow only non-sensitive operations.

The policy must be explicit.

65. Fail-Open Versus Fail-Closed

Observability failure must not automatically create an authorization bypass.

For security-sensitive actions, failure to create mandatory audit records may require blocking the action.

For ordinary diagnostic logging, failure should generally not crash the entire application.

66. Logging Backpressure

Logging systems must be protected against resource exhaustion.

Potential controls:

bounded queues;
asynchronous logging;
sampling;
rate limiting;
batch export;
size limits;
drop policies for low-priority telemetry.

Critical audit events require stronger durability guarantees than DEBUG logs.

67. Log Volume Limits

Untrusted input must never allow unlimited log generation.

Examples:

maximum field length;
maximum exception size;
maximum model-output diagnostic size;
maximum request metadata size;
maximum audit metadata size.
68. Oversized Payloads

If a telemetry field exceeds its permitted size, it should be:

truncated safely;
hashed;
summarized;
replaced with metadata.

The behavior must be deterministic and documented.

69. Hashing for Correlation

When content must be correlated without storing the content itself, a cryptographic hash may be used.

Example:

response_fingerprint=<hash>

The hash must not be treated as proof that the content is safe.

70. Hash Security

Hashing does not anonymize low-entropy secrets reliably.

A password or short API key may remain guessable.

Therefore hashing is not a replacement for redaction.

71. Pseudonymous Identifiers

Where full identifiers are unnecessary, telemetry may use pseudonymous identifiers.

The mapping must not be exposed through unauthorized interfaces.

72. User Privacy

User-identifying telemetry should be minimized.

The system should record only the identity needed for:

authentication audit;
authorization investigation;
accountability;
support;
security operations.
73. Personal Data

Personal data must not be logged merely because it was present in a request.

Telemetry should prefer:

user_id

over copying:

email
name
phone
address

where identity correlation is sufficient.

74. Prompt Privacy

Prompt content may include personal or proprietary data.

Therefore:

prompt_body -> evidence-controlled storage

rather than:

prompt_body -> application log

by default.

75. Model Response Privacy

The same principle applies to model responses.

Operational telemetry should use metadata rather than full content whenever possible.

76. RAG Telemetry

RAG operations may involve:

document identifiers;
chunk identifiers;
retrieval scores;
source references;
retrieved text.

Operational telemetry should prefer identifiers and counts.

Full retrieved content belongs in controlled evidence or assessment artifacts where required.

77. Agent Telemetry

Agent execution may involve:

tools;
APIs;
filesystem operations;
network requests;
commands;
retrieved data.

Telemetry must record safe metadata about tool execution without automatically recording sensitive tool output.

78. Tool Invocation Logging

Tool events may include:

tool name;
execution ID;
start/end;
outcome;
duration;
authorization result;
safety policy result.

Arguments should be redacted or excluded unless explicitly permitted.

79. Command Execution Telemetry

If a supported testing workflow executes commands, logs should contain:

command category;
execution ID;
exit status;
duration;
safety policy decision.

Raw command output may contain secrets and must not be logged by default.

80. Filesystem Telemetry

Filesystem events may record:

operation;
bounded path metadata;
result;
execution ID.

Sensitive file contents must never be automatically logged.

81. Network Telemetry

Network events may include:

destination category;
hostname where safe;
port;
protocol;
result;
duration;
policy decision.

Raw request bodies must not be logged by default.

82. SSRF Telemetry

Blocked SSRF attempts should be observable.

Example:

security.network.request_blocked
reason=private_address

The system should record enough information for investigation without exposing internal infrastructure details unnecessarily.

83. DNS Rebinding Telemetry

Blocked DNS rebinding or unsafe address-resolution behavior should generate security telemetry.

Telemetry should distinguish:

resolution;
validation;
connection;
policy decision.
84. Redirect Telemetry

Unsafe redirects should be observable without logging sensitive query parameters or credentials.

85. URL Sanitization

URLs in telemetry should be sanitized.

Sensitive query parameters such as:

token=
key=
secret=
password=
access_token=

must be removed or redacted.

86. Database Telemetry

Database telemetry should record:

query duration;
transaction outcome;
connection errors;
pool utilization;
deadlocks;
timeout;
migration status.

Raw SQL parameter values must not be logged by default.

87. SQL Injection Protection

Database logs must not become a second path for storing attacker-controlled SQL payloads without sanitization.

Structured fields and bounded values are preferred.

88. Database Error Handling

Database exceptions may contain:

SQL;
schema information;
connection strings;
table names;
parameter values.

Only sanitized database errors should reach user-facing logs.

89. Configuration Telemetry

Configuration changes must be auditable.

Examples:

security policy changed;
target configuration changed;
rate limit changed;
retention policy changed;
logging policy changed;
authentication configuration changed;
adapter configuration changed.

Secret values must never appear in configuration audit records.

90. Secret Configuration Changes

For secret changes, audit:

secret.updated

rather than:

secret.updated value=<secret>

The event should identify the logical secret without revealing its value.

91. Environment Variables

Environment variable names may be logged only when useful and safe.

Environment variable values must never be dumped into application logs.

A generic startup diagnostic such as:

configuration_loaded=true

is preferred.

92. Startup Logging

Startup logs may include:

application version;
environment;
component version;
migration status;
configuration validation result.

They must not include:

secrets;
credentials;
complete environment dumps.
93. Shutdown Logging

Shutdown events should include:

shutdown reason;
graceful/forced status;
active job handling;
duration where useful.

Sensitive job content must not be emitted.

94. Configuration Validation

Invalid configuration should generate useful diagnostics.

Errors should identify the logical setting and failure category without revealing secret values.

95. Audit Event Immutability

Audit records should be protected from unauthorized modification.

The storage architecture should support append-oriented semantics where practical.

Administrative deletion must be restricted and auditable.

96. Tamper Detection

Production deployments may use:

append-only storage;
hash chaining;
immutable object storage;
database controls;
external archival;
integrity verification.

The chosen mechanism must match operational requirements.

97. Audit Log Deletion

Deletion of audit records must be treated as a privileged operation.

Where deletion is legally or operationally required, the deletion itself must generate an audit event where feasible.

98. Retention

Telemetry retention must be configurable.

Retention categories should distinguish:

application logs;
security audit logs;
metrics;
traces;
evidence references.

Retention must follow data-minimization principles.

99. Short-Lived Debug Logs

DEBUG telemetry should have a shorter retention period than security audit records.

DEBUG logging should not become a permanent storage mechanism for sensitive data.

100. Security Audit Retention

Security audit retention should be longer than ordinary debug telemetry where operationally justified.

Exact duration is a deployment policy rather than a universal architecture constant.

101. Evidence Retention

Evidence retention is governed primarily by ADR-008 and ADR-012.

Observability telemetry must not independently retain duplicate copies of evidence.

102. Trace Retention

Trace retention should be bounded according to:

operational value;
security value;
storage cost;
privacy requirements.
103. Metric Retention

Metrics may generally have longer retention because they are aggregated.

However, labels must remain privacy-safe.

104. Log Rotation

Self-hosted log storage should support controlled rotation or retention.

Log files must not grow without bounds.

105. Disk Exhaustion

Aegis Vuldris must protect against disk exhaustion caused by telemetry.

Controls may include:

maximum log size;
rotation;
quotas;
retention;
compression;
backpressure.
106. Log Storage Permissions

Local log files must have restrictive permissions appropriate to the deployment.

Sensitive audit logs must not be world-readable.

107. Container Logging

Containerized deployments should avoid storing unbounded logs inside writable container layers.

Logs should use an explicit collection strategy.

108. Docker Considerations

Docker logging configuration should account for:

rotation;
size;
retention;
permissions;
centralized collection where applicable.
109. Kubernetes Considerations

If Aegis Vuldris is later deployed on Kubernetes, telemetry should integrate with cluster-native collection while preserving application-level redaction and authorization boundaries.

110. Frontend Logging

Frontend logs must not contain:

access tokens;
cookies;
API keys;
private prompts;
model responses;
sensitive project data.

Browser console logging should be minimized in production builds.

111. Frontend Error Telemetry

Frontend errors may include:

route;
component;
application version;
correlation ID;
safe error category.

Stack traces must be reviewed for accidental secret exposure.

112. Browser Network Errors

Client-side telemetry must not capture complete request/response bodies by default.

Authorization headers must never be transmitted to an external error-reporting system merely for debugging.

113. Source Maps

Production source maps must be handled according to deployment security requirements.

They must not expose sensitive source code through public locations unintentionally.

114. Correlation Across Frontend and Backend

Where appropriate, the frontend may propagate a request correlation identifier.

The backend remains responsible for validating and normalizing it.

115. Authentication Session Telemetry

Session identifiers must not be logged.

Instead use:

session fingerprint;
user ID;
event ID;
safe session lifecycle metadata.
116. API Key Telemetry

API keys must never be logged in plaintext.

Key events should use:

key ID;
key fingerprint;
creation/revocation event;
owner context.
117. Target Credentials

Target credentials are particularly sensitive.

Logs must not contain target credential values.

Target operations may be correlated through:

target_id
credential_reference_id

where appropriate.

118. Provider Credentials

Provider API credentials must be treated as secrets.

Provider names and adapter types may be logged.

Credential values must not.

119. Token Usage Metrics

Token usage may be recorded as numeric metadata when supported.

Prompt and response text should not be required to calculate ordinary token-usage metrics.

120. Cost Metrics

If a provider exposes usage or cost estimates, telemetry may record:

token counts;
request counts;
bounded cost estimates.

These values must not expose credentials.

121. Performance Telemetry

Performance metrics should cover:

API latency;
database latency;
model latency;
test execution latency;
evaluation latency;
report generation latency;
queue wait time;
worker execution time.
122. Percentile Metrics

Where useful, latency monitoring should support:

p50;
p90;
p95;
p99.

Average latency alone is insufficient for identifying tail latency.

123. Timeout Telemetry

Timeouts should record:

operation type;
timeout category;
duration;
target/job/test context.

They should not record sensitive payloads automatically.

124. Retry Telemetry

Retries should record:

operation;
retry number;
reason category;
final outcome.

Retry payloads should not be duplicated into logs.

125. Cancellation Telemetry

Cancellation should distinguish:

user requested;
system timeout;
budget exhausted;
worker shutdown;
dependency failure;
policy termination.
126. Resource Budget Telemetry

ADR-011 defines execution budgets.

Observability should expose safe consumption metadata such as:

turns used;
requests used;
tokens used;
duration;
tool calls;
network calls.
127. Resource Exhaustion Events

Budget exhaustion should produce structured telemetry.

Example:

attack.execution.terminated
reason=budget_exhausted
budget=turns
128. Concurrency Telemetry

Track:

active jobs;
active model calls;
worker utilization;
queue depth;
concurrency-limit rejections.

Unbounded concurrency must never be hidden by missing telemetry.

129. Rate-Limit Telemetry

Rate limiting should emit aggregate events for:

rejected requests;
throttled requests;
identity/category;
endpoint category.

Raw credentials or user input must not be recorded.

130. Abuse Detection

Observability may provide signals for abuse detection, such as:

repeated authentication failures;
repeated authorization failures;
excessive target requests;
repeated blocked network access;
repeated unsafe tool calls;
abnormal job creation.

Observability signals alone must not determine authorization.

131. Security Alerts

Alerting may be built on security metrics and audit events.

Potential alerts:

repeated privileged authorization failures;
unexpected administrative changes;
audit storage failure;
excessive blocked SSRF attempts;
abnormal worker failures;
repeated authentication failures;
unusual destructive test attempts.
132. Alert Fatigue

Alerts should be:

actionable;
bounded;
deduplicated;
severity-aware.

Not every warning should generate an operational alert.

133. Alerting Independence

A failed alert delivery must not change application authorization behavior.

Alerting is downstream of security enforcement.

134. Security Event Pipeline

Conceptually:

Application Action
       |
       v
Security Decision
       |
       +------> Audit Event
       |
       +------> Metrics
       |
       +------> Trace
       |
       +------> Application Log
       |
       v
Operational / Security Analysis

The security decision does not depend on the monitoring system.

135. Audit Versus Monitoring

Audit records answer:

Who did what, when, and to which resource?

Metrics answer:

How often and how much?

Traces answer:

How did an operation flow through the system?

Application logs answer:

What operationally happened?

These purposes must remain conceptually separate.

136. Event Correlation

A single operation may have:

request_id
trace_id
job_id
test_execution_id
attack_execution_id
evaluation_id
finding_id

Only applicable identifiers should be emitted.

137. Correlation ID Integrity

Correlation IDs must be treated as metadata, not authorization credentials.

An attacker controlling a request ID must not gain access to another request's telemetry.

138. Telemetry Query Authorization

Search APIs for logs, traces, audit events, or metrics must enforce authorization.

A user cannot bypass project isolation by manipulating:

project_id
target_id
job_id
request_id
finding_id
139. Cross-Tenant Telemetry Isolation

If multi-tenancy is introduced, telemetry storage and query paths must preserve tenant isolation.

Tenant identifiers must be enforced server-side.

140. Telemetry Injection

Attackers must not be able to create misleading telemetry that appears to originate from trusted system components.

User-controlled fields must never become trusted fields such as:

level
service
actor
authorization_result
system_event
141. Actor Identity

The authenticated actor identity must come from trusted application context.

It must not be derived from user-controlled request fields.

142. Service Identity

Service names must be application-controlled.

Model output cannot set:

service=aegis-auth

and have that become trusted telemetry.

143. Severity Integrity

User and model input must not control event severity.

For example, an attacker cannot submit:

severity=CRITICAL

and create a trusted critical security event.

144. Event Name Integrity

Event names must come from controlled application code.

User-provided strings should be values, not event identifiers.

145. Structured Field Integrity

Security-sensitive structured fields must come from trusted application state.

Example:

authorization_result=denied

must be generated by the authorization system.

It must not be copied from request input.

146. Model Evaluator Telemetry

LLM evaluators may produce:

scores;
labels;
explanations;
confidence;
structured findings.

Only validated evaluator results should become trusted telemetry.

147. Evaluator Prompt Injection

A target model may attempt to manipulate an evaluator.

Observability must record:

evaluator execution;
evaluator version;
evaluator status;
safe outcome metadata.

Evaluator-generated claims must not automatically become trusted audit events.

148. External Evaluator Telemetry

If evaluation occurs through an external model provider, telemetry must record that an external boundary was crossed.

Sensitive evidence must not be transmitted unless explicitly permitted.

149. Privacy-Preserving Evaluation Telemetry

Where possible, evaluator telemetry should contain:

evaluator ID;
version;
result;
confidence;
duration;
error category.

rather than full sensitive evidence.

150. Security Test Telemetry Integrity

Test telemetry must distinguish:

test defined;
test selected;
test started;
test executed;
test evaluated;
test failed;
test errored;
test skipped.

A test failure is not automatically an application security failure.

151. Finding Lifecycle Telemetry

Finding lifecycle events should include:

finding.created
finding.updated
finding.triaged
finding.confirmed
finding.rejected
finding.resolved
finding.reopened
152. Finding Modification Audit

Changes to security findings should be auditable where they affect:

severity;
risk;
status;
evidence;
ownership;
disposition.
153. Report Telemetry

Report generation may emit:

report created;
generation started;
generation completed;
generation failed;
report downloaded;
report deleted.

Sensitive report contents should not be copied into logs.

154. Export Telemetry

Exports should be auditable.

Examples:

report.exported
evidence.exported
audit.exported

The event should include the actor and resource context without embedding the exported data.

155. Bulk Export

Bulk exports are higher-risk operations.

Telemetry should record:

actor;
project;
export type;
item count;
completion;
failure.

Authorization must occur before export.

156. Administrative Actions

Administrators may have broader telemetry access.

Administrative actions must remain auditable.

No administrator should be exempt from audit logging merely because of role.

157. Audit-of-Audit Access

Access to security audit telemetry should itself be auditable.

This provides accountability for highly privileged observability access.

158. Telemetry Configuration Changes

Changes to:

logging level;
audit policy;
retention;
exporters;
tracing;
metric endpoints;
redaction rules

should be auditable.

159. Dangerous Debug Mode

Production debug mode must not enable unrestricted sensitive logging.

A configuration mistake must not turn on plaintext prompt, response, credential, or environment logging globally.

160. Safe Debugging

Debugging sensitive execution should use:

controlled reproduction;
evidence references;
secure local environments;
bounded diagnostic captures.

Not unrestricted production logging.

161. Sampling

Low-value repetitive logs may be sampled.

Security audit events must not be sampled away.

162. Duplicate Event Suppression

Telemetry pipelines may deduplicate repetitive events.

Security events should preserve enough information to establish occurrence and frequency.

163. Event Ordering

Distributed telemetry may arrive out of order.

Event timestamps and sequence metadata should be used where ordering matters.

164. Monotonic Duration

Duration calculations should use monotonic clocks internally where possible.

Wall-clock timestamps remain necessary for event correlation.

165. Clock Drift

Production systems should use time synchronization.

Large clock discrepancies can undermine incident reconstruction.

166. Trace Context Security

Incoming trace context must not be treated as authorization context.

Trace IDs are correlation data, not identity proof.

167. Trace Context Propagation

Trace context may propagate across:

frontend;
backend;
workers;
model adapters;
evaluators.

Sensitive headers must not be propagated accidentally.

168. Queue Telemetry

Job queues should expose:

queue depth;
wait duration;
worker count;
failure rate;
retry count.

Queue payloads should not appear in metrics.

169. Dead-Letter Telemetry

If dead-letter handling exists, telemetry should record:

job ID;
failure category;
retry count;
dead-letter transition.

Sensitive payloads remain protected.

170. Worker Crash Telemetry

Worker crashes should generate telemetry where infrastructure permits.

Crash reporting must be reviewed for secrets in memory-derived output.

171. Database Connection Pool Metrics

Useful metrics include:

active connections;
idle connections;
acquisition wait;
pool exhaustion;
connection failures.

Connection strings must never appear in metrics or logs.

172. Migration Telemetry

Database migrations should record:

migration start;
migration completion;
migration failure;
application version;
migration version.

Migration SQL containing secrets must not be logged.

173. Deployment Telemetry

Deployments should expose:

version;
commit identifier;
startup status;
migration status;
health status.

Deployment telemetry should not contain secrets.

174. Release Correlation

Security findings and telemetry may record the Aegis Vuldris application version.

This supports determining whether an issue existed before or after a release.

175. Build Metadata

Safe build metadata may include:

application version;
commit hash;
build timestamp;
dependency lock identifier.

Sensitive build secrets must not be included.

176. Dependency Telemetry

Dependency failures may identify:

dependency category;
library name;
version;
error class.

Secrets in dependency configuration must be excluded.

177. Security Scanner Telemetry

Future SAST, dependency, container, or SBOM systems may produce telemetry.

Their output must be validated before becoming trusted security records.

178. CI/CD Audit

Security-sensitive CI/CD actions may be recorded outside the application.

Examples:

release;
deployment;
configuration change;
signing;
artifact publication.

This ADR defines application observability compatibility, not the entire CI/CD audit system.

179. Container Security Telemetry

Containerized deployments should expose safe signals for:

restart loops;
health failures;
resource exhaustion;
image/version;
worker failures.

Container logs must not expose mounted secrets.

180. Resource Metrics

Production monitoring should cover:

CPU;
memory;
disk;
network;
process count;
worker count.

Application metrics remain necessary because infrastructure metrics cannot explain security-test behavior.

181. Memory Safety

Telemetry systems must avoid retaining sensitive payloads unnecessarily in in-memory queues.

Buffers should be bounded.

182. Telemetry Queue Limits

Telemetry queues must have:

maximum size;
bounded record size;
controlled retry behavior.
183. Telemetry Transport Security

Telemetry sent over networks must use appropriate transport protection.

Plaintext transmission of sensitive audit telemetry is prohibited in production unless the transport itself is explicitly protected by another mechanism.

184. Collector Authentication

If a telemetry collector requires authentication, credentials must be managed through the secret-management architecture.

Collector credentials must never be logged.

185. Collector Authorization

Telemetry exporters should have only the permissions required to write telemetry.

They should not receive broad application database permissions.

186. Separate Telemetry Credentials

Telemetry systems should use dedicated credentials.

Application credentials must not be reused unnecessarily.

187. Telemetry Network Isolation

Where practical, telemetry collectors should be placed in a controlled network path.

Telemetry infrastructure must not become a path to internal application resources.

188. SSRF Through Telemetry

User-controlled telemetry destinations must not be supported without explicit security controls.

A malicious user must not configure Aegis Vuldris to send telemetry to arbitrary internal addresses.

189. Exporter Configuration

Exporter endpoints must be controlled by trusted configuration.

They must not be supplied directly by model output or untrusted test input.

190. Dynamic Telemetry Plugins

Dynamic telemetry plugins are a potential code-execution boundary.

Plugins must be trusted, versioned, and controlled.

Arbitrary plugin installation from user input is prohibited.

191. Unsafe Deserialization

Telemetry ingestion must not use unsafe deserialization such as unrestricted pickle loading.

Structured formats should use safe parsers.

192. YAML Safety

If YAML is used for observability configuration, safe parsing must be used.

Arbitrary object construction is prohibited.

193. Regular Expressions

Redaction rules may use regular expressions.

Regex processing must be protected against pathological expressions and excessive input sizes.

194. Redaction Rule Testing

Redaction rules must have automated tests covering:

API keys;
bearer tokens;
passwords;
cookies;
database URLs;
private keys;
custom secret headers.
195. Redaction Failure

If a required redaction operation fails, sensitive data must not silently fall through to unrestricted logging.

The system should use a safe fallback such as:

REDACTION_FAILED

or omit the field.

196. Secret Detection

Automated secret scanners may inspect telemetry output.

This is a defense-in-depth measure.

It must not replace preventive redaction.

197. Canary Secrets

Security testing may use synthetic canary secrets.

If a canary appears in a target response, telemetry should preserve only what is required for the relevant evidence and finding.

198. Sensitive Data Classification

Telemetry fields should conceptually support:

PUBLIC
INTERNAL
CONFIDENTIAL
SENSITIVE
SECRET
RESTRICTED

Logging policy must become stricter as sensitivity increases.

199. Default Classification

Unknown fields should default to a conservative classification.

The system must not assume that unknown model output is public.

200. Logging Policy Matrix

Conceptually:

Data Class    Normal Logs    Audit Logs    Evidence
PUBLIC    Allowed    Conditional    Allowed
INTERNAL    Controlled    Conditional    Allowed
CONFIDENTIAL    Minimized    Metadata    Controlled
SENSITIVE    Redacted    Metadata    Controlled
SECRET    Never    Never plaintext    Controlled if explicitly required
RESTRICTED    Never    Minimal metadata    Strictly controlled
201. Sensitive Identifiers

Identifiers such as project IDs and target IDs may be logged when required for correlation, but they do not automatically grant access to the underlying resource.

202. Authorization Before Telemetry Retrieval

Telemetry retrieval APIs must enforce authorization independently of the identifiers provided by the requester.

203. Search Security

Search fields must be validated.

Search functionality must not allow:

SQL injection;
arbitrary filesystem access;
arbitrary backend queries;
regex denial of service;
cross-tenant enumeration.
204. Telemetry Pagination

Telemetry APIs must use bounded pagination.

Requests for unbounded telemetry datasets must be rejected or constrained.

205. Export Limits

Telemetry export must be bounded by:

time range;
record count;
response size;
authorization scope.
206. Audit Query Rate Limits

Audit search endpoints may require rate limits because audit datasets can be large and sensitive.

207. Metrics Endpoint Protection

Metrics endpoints must not accidentally expose sensitive application metrics.

Where deployment architecture requires it, metrics should be network-restricted or authenticated.

208. Health Endpoint Protection

Health endpoints should reveal only operationally necessary information.

Detailed dependency failures should not be exposed publicly.

209. Error Response Versus Logs

A detailed internal error may be recorded securely in logs while the user receives a generic safe response.

Example:

Internal log:
database_timeout

User response:
Request could not be completed.
210. Correlation in Error Responses

A safe request ID may be returned to the user for support.

Example:

request_id=req_123

The ID must not reveal internal secrets.

211. Error Enumeration

Error messages should not allow attackers to enumerate:

users;
projects;
targets;
secrets;
database records.

Logs may contain more diagnostic detail, but access remains controlled.

212. Logging User Input

User input may be logged only when necessary.

Examples of safer logging:

input_length=128
input_type=prompt

rather than copying the full prompt.

213. Logging URLs

URLs should be normalized and sensitive parameters removed.

214. Logging File Paths

File paths may reveal sensitive filesystem layout.

Paths should be:

minimized;
normalized;
restricted;
redacted where necessary.
215. Logging Tool Arguments

Tool arguments are untrusted and potentially sensitive.

They must not be logged automatically.

216. Logging Retrieved Documents

Retrieved document text must not be emitted into ordinary logs.

Document IDs and retrieval metadata are preferred.

217. Logging Memory Operations

AI memory operations may expose sensitive conversation data.

Telemetry should use:

memory ID;
operation;
count;
outcome.

not raw memory content.

218. Logging Session Operations

Session lifecycle events should use session identifiers only in safe/pseudonymous form.

219. Logging Cross-Context Access

Potential cross-project, cross-user, or cross-tenant access attempts should create security telemetry.

220. Privacy Finding Telemetry

Privacy findings should include:

finding ID;
category;
severity;
detection result;
confidence;
project/target context.

Sensitive leaked content belongs in controlled evidence.

221. Data Leakage Detection Telemetry

Telemetry should record that a leakage detector matched a pattern or semantic condition.

It should not necessarily record the entire leaked value.

222. Detection Fingerprints

A sensitive match may be represented by:

detector ID;
match type;
safe fingerprint;
count;
evidence reference.
223. DLP Telemetry

Data-loss-prevention style detectors may generate events.

These events must not themselves leak the protected data.

224. Log Review

Production logs should be periodically reviewed for:

accidental secrets;
sensitive prompts;
personal data;
unsafe stack traces;
excessive payload logging;
attacker-controlled formatting.
225. Automated Log Testing

CI should test that known synthetic secrets do not appear in ordinary telemetry.

226. Negative Logging Tests

Security tests should verify that:

passwords are not logged;
API keys are not logged;
tokens are not logged;
cookies are not logged;
prompts are not logged by default;
responses are not logged by default.
227. Log Injection Tests

Tests should submit inputs containing:

newline
carriage return
ANSI escape
JSON delimiters
structured-log fields

and verify telemetry remains structurally valid.

228. Model Output Log Injection Tests

The same tests must be applied to model-generated output.

229. Audit Integrity Tests

Tests should verify:

audit event creation;
authorization;
tenant isolation;
immutable behavior where applicable;
deletion controls;
export controls.
230. Correlation Tests

Tests should verify that related operations share the expected correlation context.

231. Missing Correlation Tests

The application should generate a safe request ID when one is missing.

232. Malicious Correlation Tests

Tests should verify that malicious correlation values cannot become:

authorization context;
trusted actor identity;
privileged telemetry scope.
233. Metrics Cardinality Tests

Tests should verify that user-controlled fields do not become unbounded metric labels.

234. Trace Attribute Tests

Tests should verify that sensitive fields are not exported into tracing attributes.

235. Redaction Regression Tests

Every discovered secret-leak pattern should be converted into a regression test where practical.

236. Evidence Separation Tests

Tests should verify that sensitive evidence is not automatically copied into ordinary logs.

237. Audit Failure Tests

Tests should simulate audit-storage failure and verify the documented fail-open/fail-closed behavior.

238. Telemetry Storage Failure

Tests should verify that normal application functionality degrades safely if low-priority telemetry storage fails.

239. Telemetry Resource Exhaustion Tests

Tests should verify that telemetry cannot consume unlimited memory, disk, CPU, or network bandwidth.

240. Worker Telemetry Tests

Tests should verify:

job start;
job completion;
failure;
retry;
cancellation;
worker restart.
241. Security Event Taxonomy

Security events should use stable categories.

Examples:

AUTHENTICATION
AUTHORIZATION
SECRET
CONFIGURATION
NETWORK
FILESYSTEM
COMMAND_EXECUTION
TOOL
MODEL
PRIVACY
EVIDENCE
ADMINISTRATION
JOB
242. Security Event Severity

Security severity should be assigned based on impact and confidence.

A high-volume low-risk event should not automatically become critical.

243. Security Event Deduplication

Repeated identical events may be aggregated for alerting while preserving enough information for investigation.

244. Security Event Suppression

Security event suppression must be explicit and auditable.

Users must not be able to suppress mandatory security auditing through untrusted input.

245. Audit Policy

Audit policy may define mandatory events.

Mandatory events must not be disabled by ordinary debug configuration.

246. Audit Policy Versioning

Changes to audit policy should be versioned.

This allows investigators to understand which policy was active at the time.

247. Redaction Policy Versioning

Redaction behavior should be versioned where practical.

This helps determine whether an old telemetry record was produced under different redaction rules.

248. Telemetry Schema Versioning

Structured telemetry schemas should be versioned.

Example:

schema_version=1

Breaking changes require explicit migration strategy.

249. Backward Compatibility

Telemetry consumers should tolerate additive fields.

Removal or semantic changes to important fields require review.

250. Audit Schema Stability

Security audit event semantics should remain stable across application releases.

251. Event Documentation

Important events should have documented:

event name;
purpose;
producer;
required fields;
sensitivity;
retention;
access scope.
252. Event Registry

A centralized event registry is recommended.

It reduces accidental inconsistent event naming.

253. Event Producers

Each event should have a controlled producer.

Examples:

authentication service
authorization layer
job manager
test executor
attack orchestrator
evaluation engine
evidence service
reporting service
configuration service
254. Logging Library

The backend should use a structured logging implementation rather than manually formatting strings throughout the application.

255. Logging Abstraction

Application components should depend on a small internal logging abstraction where practical.

This allows:

redaction;
context propagation;
testing;
exporter changes.
256. Context Propagation

Logging context should be attached using request/job execution context rather than passing dozens of arguments through every function.

257. Async Context

Async execution must preserve appropriate correlation context.

Context must not leak between concurrent requests or jobs.

258. Context Isolation

A request's:

request_id
user_id
project_id
tenant_id

must not accidentally persist into another request.

259. Worker Context Isolation

Workers must reset context between jobs.

A previous job's project or user context must never appear in another job's telemetry.

260. Thread Safety

Logging context storage must be safe for concurrent execution.

261. Process Isolation

Separate worker processes should have distinct process metadata.

262. Service Boundaries

Cross-service requests should propagate only necessary correlation context.

263. Trust Boundary

Telemetry propagation across service boundaries must not create trust in user-controlled fields.

264. External Target Boundary

Target model output crosses a trust boundary.

Its content must remain untrusted in logs, metrics, traces, and audit events.

265. Tool Boundary

Tool output crosses a trust boundary.

Tool output must be sanitized before telemetry processing.

266. File Boundary

File names and file content may be attacker-controlled.

Telemetry must not treat them as trusted metadata.

267. Network Boundary

Network responses may be malicious.

Telemetry parsing must use safe parsers and bounded sizes.

268. Parser Safety

Telemetry pipelines should safely parse:

JSON;
HTTP metadata;
structured tool results;
model output;
YAML configuration where required.
269. Malformed Telemetry

Malformed untrusted telemetry data should result in safe error handling.

It must not crash the logging subsystem globally.

270. Telemetry Isolation

A malicious model response must not be able to:

disable logging;
change log destination;
modify audit severity;
alter audit identity;
inject trusted fields;
access previous telemetry;
retrieve telemetry contents.
271. Prompt Injection Defense

Prompt injection defenses remain application/test concerns.

Telemetry must observe the event without trusting the injected instructions.

272. Audit Log Prompt Injection

An attacker may attempt to insert text such as:

IGNORE PREVIOUS INSTRUCTIONS

into a log field.

The telemetry system must store it as data.

It must never interpret it as an instruction.

273. LLM-Assisted Operations

If an LLM is later used to summarize logs, the summarizer must treat logs as untrusted content.

274. LLM Log Analysis

An LLM analyzing logs must not automatically execute:

commands;
network requests;
administrative actions.

without explicit application-level authorization.

275. Security Analyst Assistants

If Aegis Vuldris later includes an AI assistant for security analysis, its access to telemetry must be scoped by project and role.

276. Telemetry Export to AI

Sensitive telemetry must not be sent to an external LLM merely to summarize it unless explicitly authorized.

277. Summary Integrity

AI-generated telemetry summaries are derived information.

They are not replacements for original audit records.

278. Audit Record Authority

The authoritative audit record remains the structured application event or durable audit store.

279. Operational Dashboards

Dashboards should display:

system health;
job health;
execution rates;
failure rates;
latency;
security event trends;
resource utilization.
280. Dashboard Authorization

Dashboard data must obey authorization boundaries.

281. Project Dashboards

Project users should see only telemetry permitted for their project.

282. Global Dashboards

Global operational dashboards require elevated access.

283. Security Dashboards

Security dashboards may aggregate cross-project information for authorized administrators.

Raw sensitive content should remain inaccessible unless specifically authorized.

284. Dashboard Data Minimization

Dashboards should prefer aggregates.

Example:

347 authorization failures

rather than displaying 347 request bodies.

285. Telemetry APIs

Telemetry APIs should support:

bounded filters;
authorization;
pagination;
safe sorting;
time ranges;
resource scope.
286. Sorting Security

Sorting should use allowlisted fields.

User-controlled SQL fragments must never be accepted.

287. Filter Security

Filters should use typed values.

Raw SQL, raw query languages, or executable expressions must not be accepted unless explicitly sandboxed and authorized.

288. Regex Search

Regex search should be disabled by default or heavily constrained.

289. Search Resource Limits

Telemetry searches should enforce:

maximum time range;
maximum result count;
query timeout;
response size.
290. Audit Export Format

Audit exports may support structured formats such as:

JSON;
CSV.

Export formats must preserve safe schema semantics.

291. CSV Injection

CSV exports must protect against spreadsheet formula injection when values begin with formula-like characters.

292. HTML Log Views

HTML views must HTML-escape untrusted log values.

293. Markdown Log Views

Markdown rendering must treat log content as untrusted.

Raw HTML and executable constructs must be controlled.

294. PDF Reports

PDF reports generated from telemetry must preserve the same redaction and data-minimization rules.

295. Report Security

Telemetry must not become an indirect mechanism for placing secrets into generated reports.

296. Download Authorization

Telemetry and audit downloads require authorization.

297. Signed Exports

Future deployments may support signed audit exports.

Signatures should protect integrity, not confidentiality.

298. Encryption at Rest

Sensitive audit and telemetry storage should use appropriate encryption at rest where supported by deployment infrastructure.

299. Encryption in Transit

Sensitive telemetry transport should use appropriate encryption in transit.

300. Key Management

Encryption keys must be managed separately from application logs.

Keys must never appear in telemetry.

301. Backup Security

Telemetry backups may contain sensitive information.

Backups require:

access control;
encryption;
retention;
deletion;
restore testing.
302. Audit Backup

Critical audit records should have appropriate backup or durable storage strategy in production.

303. Restore Testing

Telemetry restore procedures should be tested.

A backup that cannot be restored is not sufficient operational protection.

304. Telemetry Disaster Recovery

Production architecture should define how observability behaves during:

database outage;
telemetry backend outage;
worker outage;
network outage;
disk exhaustion;
deployment rollback.
305. Graceful Degradation

Low-priority telemetry may be dropped during severe resource pressure.

Mandatory security auditing requires stronger guarantees.

306. Log Loss Classification

Telemetry loss should be distinguishable between:

expected sampling;
temporary exporter failure;
permanent storage failure;
intentional retention deletion.
307. Monitoring the Monitoring System

The observability system itself must be observable.

Monitor:

collector health;
export failures;
queue depth;
dropped records;
storage utilization;
exporter latency.
308. Telemetry Drop Metrics

Telemetry pipelines should expose metrics such as:

telemetry_records_dropped_total
telemetry_export_failures_total
telemetry_queue_depth
309. Audit Drop Detection

Critical audit events should have mechanisms to detect delivery failures.

310. Startup Telemetry Validation

Application startup should validate required telemetry configuration without exposing secrets.

311. Configuration Defaults

Secure defaults include:

raw_prompt_logging=false
raw_response_logging=false
credential_logging=false
environment_dump=false
unbounded_debug_logging=false
312. Development Overrides

Development may enable additional diagnostics, but sensitive logging should still require explicit opt-in.

313. Production Overrides

Production should not permit a simple configuration toggle to expose all sensitive payloads.

314. Test Environment

Security tests should be able to capture detailed evidence without changing global production logging policy.

315. Synthetic Test Data

Automated tests should prefer synthetic data for verifying telemetry behavior.

316. Sensitive Test Fixtures

If real sensitive data is unavoidable, fixtures must be controlled and excluded from ordinary telemetry.

317. Secret Fixture Scanning

Repository tests should scan fixtures for accidental real secrets.

318. CI Log Safety

CI output must not expose:

secrets;
tokens;
credentials;
private test data.
319. CI Secret Masking

CI platforms should use their supported secret masking features where available.

Aegis Vuldris code must still avoid printing secrets directly.

320. Test Failure Output

Pytest failure output can include sensitive fixture values.

Tests should avoid using real secrets in assertions that print full values.

321. Debugger Safety

Developer debugging tools may expose sensitive memory.

Production debugger access must be restricted.

322. Crash Dumps

Crash dumps can contain secrets.

Production crash-dump collection must be explicitly controlled.

323. Core Dumps

Core dumps should be disabled or securely controlled in environments handling sensitive assessment data.

324. Memory Dumps

Memory dumps must never be uploaded automatically to external telemetry services without explicit authorization.

325. Exception Telemetry

Exception tracking systems must apply the same privacy and secret-redaction policy as application logs.

326. Third-Party Error Reporting

If a third-party error reporting service is introduced, it becomes a new trust boundary.

Its payload must be explicitly reviewed.

327. Open-Source Error Reporting

Open-source/self-hosted error reporting may be preferred for zero-cost and privacy goals.

328. Dependency Selection

Observability dependencies should be:

open source;
maintained;
auditable;
compatible with the project license;
security-reviewed.
329. Dependency Pinning

Telemetry dependencies should be pinned through the project's dependency management strategy.

330. Supply Chain

Observability packages are part of the application supply chain.

They require the same dependency security controls as other packages.

331. Telemetry Dependency Failure

An observability dependency failure must not automatically disable core authorization.

332. Logging API Abuse

Application code must not allow arbitrary callers to bypass centralized redaction by directly writing untrusted sensitive payloads to raw sinks.

333. Raw Logger Access

Raw logger access should be limited by coding conventions and review.

334. Code Review

Changes to:

audit events;
redaction;
telemetry destinations;
security metrics;
trace attributes;
logging policies

require security-aware review.

335. Telemetry Threat Model

The observability subsystem itself is included in the threat model.

Threats include:

log injection;
secret leakage;
log deletion;
log tampering;
telemetry denial of service;
cross-tenant telemetry access;
exporter compromise;
collector compromise;
metric cardinality explosion;
trace data leakage;
audit suppression;
malicious model output;
malicious tool output.
336. Threat: Secret Leakage

Threat: application logs expose credentials.

Mitigations:

centralized redaction;
no raw body logging;
secret-aware tests;
restricted telemetry access;
secure defaults.
337. Threat: Log Injection

Threat: attacker-controlled input changes log structure.

Mitigations:

structured logging;
escaping;
bounded fields;
control-character handling;
regression tests.
338. Threat: Cross-Tenant Telemetry

Threat: user accesses another tenant's logs.

Mitigations:

server-side authorization;
tenant filtering;
object-level checks;
scoped queries;
audit of telemetry access.
339. Threat: Telemetry DoS

Threat: attacker generates huge logs.

Mitigations:

input limits;
bounded log fields;
rate limits;
sampling;
queues;
quotas.
340. Threat: Audit Suppression

Threat: attacker prevents security events from being recorded.

Mitigations:

mandatory audit events;
durable audit path;
configuration protection;
monitoring audit failures.
341. Threat: Malicious Model Output

Threat: model output injects fake telemetry.

Mitigations:

untrusted output handling;
structured fields;
controlled event names;
controlled severity;
controlled actor identity.
342. Threat: External Export Leakage

Threat: sensitive telemetry is sent to an external service.

Mitigations:

explicit exporter configuration;
redaction;
data classification;
allowlisted destinations;
privacy review.
343. Threat: Metric Cardinality Explosion

Threat: attacker creates unique metric labels.

Mitigations:

bounded labels;
allowlisted label values;
tests;
monitoring.
344. Threat: Audit Tampering

Threat: privileged user modifies audit history.

Mitigations:

restricted access;
append-oriented storage;
integrity controls;
audit-of-audit access.
345. Threat: Log Storage Exhaustion

Threat: logs fill disk.

Mitigations:

rotation;
quotas;
retention;
alerts;
bounded events.
346. Threat: Trace Data Leakage

Threat: sensitive prompt/response data enters trace attributes.

Mitigations:

explicit attribute allowlist;
redaction;
tracing tests;
no automatic body capture.
347. Threat: Collector Compromise

Threat: telemetry collector is compromised.

Mitigations:

least privilege;
encryption;
network isolation;
minimized payloads;
retention limits.
348. Threat: Telemetry Query Injection

Threat: telemetry search endpoint becomes an injection vector.

Mitigations:

typed filters;
parameterized queries;
allowlisted sorting;
query limits.
349. Threat: HTML Injection

Threat: malicious log values execute in a web dashboard.

Mitigations:

output encoding;
safe templating;
CSP where appropriate;
XSS testing.
350. Threat: CSV Injection

Threat: malicious log value becomes spreadsheet formula.

Mitigations:

CSV cell sanitization;
export tests.
351. Threat: SSRF Through Exporters

Threat: attacker controls telemetry destination.

Mitigations:

trusted configuration;
destination allowlisting;
network restrictions.
352. Threat: Plugin Code Execution

Threat: malicious observability plugin executes code.

Mitigations:

trusted plugins;
package review;
no arbitrary runtime installation.
353. Threat: Unsafe Parser

Threat: malicious telemetry crashes or compromises parser.

Mitigations:

safe parsers;
bounded input;
dependency scanning.
354. Threat: Regex Denial of Service

Threat: redaction regex causes excessive CPU.

Mitigations:

controlled regexes;
bounded inputs;
regex testing.
355. Threat: Telemetry Credential Theft

Threat: exporter credentials are exposed.

Mitigations:

secret manager/environment secret;
no logging;
least privilege;
rotation.
356. Threat: Debug Configuration Abuse

Threat: attacker enables sensitive debug mode.

Mitigations:

authenticated configuration;
privileged access;
audit;
secure production defaults.
357. Threat: Information Disclosure

Threat: health or metrics endpoint reveals internal details.

Mitigations:

minimal output;
network controls;
authentication where appropriate.
358. Threat: Insider Abuse

Threat: privileged user accesses sensitive telemetry unnecessarily.

Mitigations:

least privilege;
access auditing;
retention;
data minimization.
359. Threat: Correlation Context Leakage

Threat: request context leaks between concurrent operations.

Mitigations:

scoped context;
async-safe context;
worker reset;
concurrency tests.
360. Threat: Audit Replay Ambiguity

Threat: timestamps alone cannot reconstruct event ordering.

Mitigations:

request IDs;
trace IDs;
sequence metadata;
synchronized clocks.
361. Threat: Telemetry Spoofing

Threat: attacker generates telemetry appearing to come from trusted service.

Mitigations:

service-controlled metadata;
trusted producer identity;
separate user fields.
362. Threat: Data Retention Excess

Threat: telemetry stores sensitive information indefinitely.

Mitigations:

retention policies;
automated deletion;
minimized payloads;
evidence separation.
363. Threat: Backup Leakage

Threat: telemetry backup exposes sensitive records.

Mitigations:

encryption;
access control;
retention;
restore security.
364. Threat: Alert Manipulation

Threat: attacker floods or suppresses alerts.

Mitigations:

deduplication;
independent security events;
rate limits;
alert integrity.
365. Security Invariant 1

User-controlled input must never become trusted audit metadata.

366. Security Invariant 2

Model-generated content must never become trusted audit metadata.

367. Security Invariant 3

Tool output must never become trusted audit metadata.

368. Security Invariant 4

Secrets must never be emitted in plaintext telemetry.

369. Security Invariant 5

Raw prompts are not logged by default.

370. Security Invariant 6

Raw model responses are not logged by default.

371. Security Invariant 7

Audit logging cannot be disabled by untrusted input.

372. Security Invariant 8

Telemetry access is subject to authorization.

373. Security Invariant 9

Telemetry queries cannot bypass project or tenant isolation.

374. Security Invariant 10

Correlation IDs are not authorization credentials.

375. Security Invariant 11

Trace context is not identity proof.

376. Security Invariant 12

Metric labels must remain bounded.

377. Security Invariant 13

Telemetry queues must be bounded.

378. Security Invariant 14

Telemetry storage cannot become an uncontrolled data store.

379. Security Invariant 15

Audit records and security-test evidence remain separate concepts.

380. Security Invariant 16

Audit access is itself auditable.

381. Security Invariant 17

Telemetry failure must not create an authorization bypass.

382. Security Invariant 18

External telemetry export requires explicit configuration.

383. Security Invariant 19

Telemetry cannot execute instructions contained within logged data.

384. Security Invariant 20

Observability must never become the sole security boundary.

385. Security Invariant 21

Security-sensitive operations must remain protected even when monitoring systems fail.

386. Security Invariant 22

Sensitive evidence must not be copied into ordinary logs merely for convenience.

387. Security Invariant 23

A malicious log value cannot change the meaning of surrounding structured fields.

388. Security Invariant 24

Telemetry configuration is itself security-sensitive configuration.

389. Security Invariant 25

Production debug settings cannot silently expose protected assessment content.

390. Implementation Boundary

The observability subsystem will be implemented as a cross-cutting infrastructure layer.

Conceptually:

                    +--------------------+
                    |   Aegis Vuldris App      |
                    +---------+----------+
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
        Application       Security Audit    Metrics/Trace
          Logging             Events          Telemetry
             |                |                |
             +----------------+----------------+
                              |
                              v
                    Observability Pipeline
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
           Logs            Metrics            Traces
391. Logging Abstraction Boundary

Application components should not directly know the details of the final telemetry backend.

They emit structured semantic events.

392. Audit Abstraction Boundary

Security-sensitive code should call an explicit audit mechanism.

This prevents important audit semantics from being hidden inside arbitrary debug statements.

393. Metrics Abstraction Boundary

Metrics should be emitted through centralized instruments.

394. Tracing Abstraction Boundary

Tracing should use standardized context propagation rather than custom identifiers where possible.

395. Telemetry Configuration Boundary

Telemetry destinations are configuration, not application data.

They must be loaded from trusted configuration sources.

396. Dependency Injection

Telemetry components should be injectable where practical.

This enables tests to use:

in-memory sinks;
fake audit stores;
test exporters;
capture handlers.
397. Testability

Every security-sensitive telemetry behavior must be testable without requiring a production telemetry backend.

398. In-Memory Test Sink

Tests should be able to capture structured events in memory.

This allows assertions such as:

assert event.name == "auth.authorization.denied"
assert "secret" not in event.payload
399. Audit Test Store

Tests should be able to simulate:

successful audit persistence;
audit persistence failure;
duplicate events;
unauthorized access.
400. Metrics Testability

Metrics should be testable without requiring Prometheus infrastructure.

401. Trace Testability

Trace propagation should be testable with in-memory exporters or equivalent mechanisms.

402. Redaction Testability

Redaction must be independently unit-testable.

403. Context Testability

Concurrent requests and jobs must be tested to ensure context isolation.

404. Integration Tests

Integration tests should cover:

API request → log;
API request → trace;
authenticated action → audit;
job → worker telemetry;
test → evaluation telemetry;
attack → multi-turn telemetry;
finding → audit/lifecycle telemetry.
405. Security Integration Tests

Security integration tests should cover:

unauthorized telemetry access;
cross-project query;
cross-tenant query;
audit export;
audit deletion;
secret redaction;
malicious model output;
log injection.
406. Property-Based Tests

Property-based testing may verify that arbitrary untrusted strings cannot break structured telemetry.

407. Fuzz Testing

Fuzzing should cover:

log values;
model responses;
tool output;
URLs;
headers;
exception messages;
telemetry search filters.
408. Metamorphic Tests

Metamorphic tests can verify that adding harmless text to a prompt does not change trusted telemetry metadata.

409. Golden Tests

Golden telemetry fixtures may verify stable schemas and redaction behavior.

410. Regression Tests

Every telemetry security bug should produce a regression test where practical.

411. CI Gates

CI should fail if:

telemetry code introduces lint errors;
schema tests fail;
secret-redaction tests fail;
security invariants fail;
structured output becomes invalid.
412. Static Analysis

Telemetry code is subject to the project's standard static analysis.

413. Dependency Scanning

Telemetry dependencies are included in dependency scanning.

414. Secret Scanning

Repository and CI secret scanning should include telemetry fixtures and configuration examples.

415. Container Scanning

Telemetry containers and images must be included in container scanning where applicable.

416. SBOM

Observability dependencies must appear in the project's SBOM.

417. Audit Schema Migration

Changes to audit schemas require migration or compatibility planning.

418. Telemetry Version Compatibility

Collector and application versions should be compatible through documented schema expectations.

419. Backward-Compatible Fields

Adding optional fields should normally be backward compatible.

420. Breaking Changes

Breaking telemetry schema changes require:

ADR review;
migration strategy;
consumer impact analysis;
rollback plan.
421. Operational Runbooks

Production deployment should document:

telemetry outage;
audit storage outage;
log disk exhaustion;
collector failure;
metrics failure;
trace failure;
audit query incident;
secret-leak investigation.
422. Incident Investigation

Telemetry should support investigators in answering:

who acted;
what happened;
when;
which project;
which target;
which job;
which test;
which attack;
which finding;
which application version.
423. Incident Evidence

Logs and audit records may help locate evidence.

They do not automatically replace evidence artifacts.

424. Incident Correlation

Investigators should be able to correlate:

request
    ->
job
    ->
test
    ->
attack
    ->
target request
    ->
evaluation
    ->
finding
    ->
report

where the execution path contains those stages.

425. Security Timeline

Aegis Vuldris should be capable of constructing a security timeline from structured events.

426. Timeline Ordering

Timeline reconstruction should use:

timestamps;
correlation IDs;
sequence values where available;
job/test/attack state.
427. Timeline Integrity

Derived timelines must not modify the underlying audit records.

428. Audit Search UI

Future dashboards may provide audit search.

Search UI must preserve:

authorization;
filtering;
pagination;
data minimization.
429. Audit Search Filters

Useful filters include:

time range;
actor;
event type;
project;
target;
severity;
outcome;
resource type.
430. Audit Search Security

Search filters must not reveal existence of unauthorized resources.

431. Telemetry Pagination Security

Pagination cursors must not permit cross-project access.

432. Cursor Integrity

If opaque cursors are used, they should be protected against tampering.

433. Audit Event IDs

Audit events should have unique identifiers.

They may use UUIDs or another secure identifier scheme consistent with project architecture.

434. Event Deduplication IDs

Events that may be retried should support idempotency/deduplication where required.

435. Duplicate Audit Prevention

Retrying a request must not unintentionally create misleading duplicate audit events when the underlying action occurred only once.

436. Exactly-Once Semantics

The architecture should not assume universal exactly-once delivery.

Instead it should define idempotency and reconciliation where needed.

437. At-Least-Once Telemetry

Operational telemetry may use at-least-once delivery where practical.

Consumers should tolerate duplicates.

438. Audit Reconciliation

Critical audit systems may periodically verify expected events against persisted records.

439. Missing Audit Event Detection

Where feasible, security-sensitive operations should make missing audit events detectable.

440. Transactional Audit

For operations requiring strong audit guarantees, audit persistence may be coupled to the same transaction or durable transaction boundary.

The implementation must balance database coupling and availability.

441. Audit Transaction Boundaries

The transaction strategy must be documented for each critical operation.

442. Authentication Transaction

Successful security-sensitive authentication state changes should have appropriate audit semantics.

443. Authorization Transaction

Authorization decisions should be generated from trusted security context.

444. Permission Changes

Permission changes require durable audit events.

445. Role Changes

Role changes require durable audit events.

446. Project Membership Changes

Membership changes require durable audit events.

447. Target Changes

Changes to security-test targets should be auditable.

448. Security Policy Changes

Changes to:

allowed networks;
tool permissions;
test policies;
data-retention policies;
evaluation policies

should be auditable.

449. Destructive Test Authorization

Destructive testing actions require explicit authorization and should generate audit telemetry.

450. Test Cancellation

Privileged cancellation of tests should be auditable.

451. Evidence Deletion

Evidence deletion must generate audit telemetry.

452. Finding Disposition

Changing a finding to:

false_positive
accepted_risk
resolved

should be auditable where applicable.

453. Report Deletion

Report deletion should be auditable.

454. Account Administration

Account administration events should be auditable.

455. Security Configuration

Security configuration changes should be auditable.

456. Telemetry Configuration

Telemetry configuration changes should be auditable.

457. Audit Configuration

Audit-policy changes should themselves be auditable.

458. Retention Configuration

Retention changes should be auditable.

459. Export Configuration

Telemetry exporter changes should be auditable.

460. Production Access

Production administrative access should be auditable.

461. Break-Glass Access

Future emergency access mechanisms must generate explicit audit events.

462. Emergency Disablement

Emergency security-control disablement must be auditable and time-bounded where possible.

463. Maintenance Mode

Maintenance mode changes should be auditable.

464. Observability Maintenance

Changes to telemetry infrastructure should be treated as operationally sensitive.

465. Security Monitoring

Observability can support security monitoring but does not replace dedicated detection systems.

466. Detection Rules

Future detection rules may operate on audit events and metrics.

467. Detection Rule Security

Detection rules must not execute arbitrary commands from event content.

468. Alert Rule Validation

Alert rules should be validated and versioned.

469. Alert Rule Injection

User-provided strings must not become executable alert expressions without sandboxing.

470. Notification Security

Notifications must not include sensitive evidence by default.

471. Email Notifications

Security alerts sent by email should contain:

event category;
severity;
safe identifiers;
link to authorized dashboard.

Not raw sensitive evidence.

472. Webhook Notifications

Webhook destinations must be trusted configuration.

Webhook payloads must be minimized.

473. Webhook Secret Handling

Webhook signing secrets must not appear in logs.

474. Notification Failure

Notification delivery failure must not disable underlying security controls.

475. Notification Retry

Retries must be bounded to prevent notification storms.

476. Alert Deduplication

Repeated security events should be deduplicated when appropriate.

477. Alert Correlation

Related events may be correlated into incidents.

478. Incident Records

Future incident-management features may reference audit event IDs rather than copying all event payloads.

479. Incident Privacy

Incident records may contain sensitive information and require authorization.

480. Audit Data Classification

Audit data itself is classified as sensitive operational/security information.

481. Operational Log Classification

Ordinary logs should be treated as internal unless explicitly classified otherwise.

482. Public Telemetry

No internal telemetry should be considered public by default.

483. Open Metrics

Public metrics, if ever exposed, must be separately designed and reviewed.

484. Version Endpoint

A public version endpoint may expose:

version

but not:

environment variables
commit secrets
database configuration
provider credentials
485. Security Headers

Telemetry dashboards and APIs remain subject to application security headers and browser protections.

486. XSS Protection

Telemetry values rendered in a web UI must be safely encoded.

487. Content Security Policy

Future telemetry dashboards should use an appropriate CSP.

488. Clickjacking Protection

Administrative telemetry interfaces should prevent unauthorized framing where applicable.

489. CSRF Protection

State-changing telemetry administration operations require appropriate CSRF protection in browser-based sessions.

490. Audit Export CSRF

Audit export endpoints must remain protected by normal authentication and browser security controls.

491. API Authentication

Telemetry APIs follow ADR-006 authentication architecture.

492. API Authorization

Telemetry APIs follow ADR-006 authorization architecture.

493. Service-to-Service Authentication

Internal telemetry endpoints should use authenticated service communication where required.

494. Worker Authentication

Workers accessing telemetry services must use controlled service identity.

495. Least Privilege Worker

Workers should not automatically receive access to global audit logs.

496. Model Adapter Isolation

Model adapters should emit metadata through the application telemetry abstraction rather than writing directly to privileged audit storage.

497. Test Engine Isolation

Test engines should not have unrestricted access to audit storage.

498. Attack Orchestrator Isolation

Attack orchestration may create execution telemetry but must not control trusted audit metadata.

499. Evaluation Isolation

Evaluators can report evaluation results but cannot impersonate users or administrators in audit records.

500. Evidence Service Isolation

Evidence services may store sensitive artifacts but should not automatically expose them to telemetry collectors.

501. Reporting Isolation

Reporting services may reference evidence and findings without copying their sensitive contents into operational logs.

502. Database Isolation

Telemetry storage permissions should be separate from general application data permissions where practical.

503. Telemetry Database

A separate telemetry database may be introduced in larger deployments.

The architectural requirement is isolation, not necessarily a separate database in the MVP.

504. PostgreSQL Initial Strategy

The initial implementation may use PostgreSQL for application/audit metadata while maintaining strict table and permission boundaries.

505. Separate Storage Later

Large deployments may separate:

application database;
audit database;
log storage;
metrics storage;
trace storage.
506. Migration Path

The observability abstraction must permit moving telemetry storage without changing security semantics.

507. Open-Source Production Stack

A production deployment may use open-source components such as:

OpenTelemetry;
Prometheus;
Grafana;
Loki;
Tempo;
compatible collectors.

Exact component selection remains an implementation/deployment decision.

508. No Mandatory SaaS

Aegis Vuldris must remain usable without requiring a proprietary hosted observability service.

509. Docker Compose Observability

Local Docker Compose may later include optional observability services.

They should not be required for the basic application to run.

510. Optional Components

Telemetry backends should be optional infrastructure where practical.

Core application logic must not become tightly coupled to one monitoring product.

511. Development Simplicity

The initial MVP should use a simple structured logger and local metrics/tracing support.

Complex telemetry infrastructure should be introduced incrementally.

512. Production Readiness

Before production, telemetry must support:

security audit;
health;
metrics;
traces;
redaction;
retention;
access control;
alerting;
failure handling.
513. MVP Observability

The MVP implementation should include:

structured backend logging;
request IDs;
security audit events;
centralized redaction;
basic metrics;
health/readiness endpoints;
job/test correlation;
authentication/authorization audit events;
sensitive-data logging tests.
514. Phase 1 Implementation

Initial implementation should create:

logging module;
audit-event model/interface;
request-context middleware;
redaction utilities;
basic metrics abstraction;
health endpoints;
tests.
515. Phase 2 Implementation

Then integrate:

job telemetry;
test execution telemetry;
model adapter telemetry;
evaluation telemetry;
finding lifecycle telemetry.
516. Phase 3 Implementation

Then add:

OpenTelemetry;
Prometheus metrics;
tracing;
production collectors;
dashboards.
517. Phase 4 Implementation

Then add:

advanced retention;
immutable audit storage;
alerting;
security analytics;
operational runbooks.
518. Logging Module

Conceptual module:

backend/
  observability/
    logging.py
    audit.py
    metrics.py
    tracing.py
    context.py
    redaction.py
    health.py

Exact package organization may evolve.

519. Audit Interface

Conceptual interface:

audit.record(
    event="target.updated",
    actor=actor,
    resource=resource,
    outcome="success",
)

The implementation must enforce trusted metadata and redaction.

520. Logging Interface

Conceptual interface:

logger.info(
    "target.connection.completed",
    target_id=target_id,
    duration_ms=duration_ms,
)
521. Security Event Interface

Conceptual interface:

audit.security(
    category="AUTHORIZATION",
    event="authorization.denied",
    resource_type="target",
    resource_id=target_id,
)
522. Context Interface

Conceptual context:

request_id
trace_id
user_id
project_id
tenant_id
job_id
test_execution_id
attack_execution_id
523. Redaction Interface

Conceptual behavior:

safe_value = redact(value, classification="SECRET")
524. Metrics Interface

Conceptual behavior:

metrics.counter(
    "test_executions_total",
    labels={"outcome": "completed"},
)

Labels must remain bounded.

525. Trace Interface

Conceptual behavior:

with tracer.span("model.adapter.request"):
    ...
526. Health Interface

Conceptual health response:

{
  "status": "ready"
}

Detailed diagnostics remain protected.

527. Audit Storage Interface

Conceptual:

audit_store.append(event)

Storage implementation must preserve authorization and integrity requirements.

528. Event Builder

A centralized event builder can enforce:

schema;
timestamp;
context;
redaction;
size limits.
529. Field Allowlisting

For highly sensitive events, fields should be explicitly allowlisted.

530. Field Denylists

Denylisting sensitive field names may supplement but must not replace allowlisting for critical events.

531. Secret Field Names

Known sensitive names include:

password
secret
token
api_key
authorization
cookie
private_key
client_secret
database_url
credential
532. Nested Secret Redaction

Redaction must work for nested structures.

Example:

{
  "config": {
    "credentials": {
      "api_key": "REDACTED"
    }
  }
}
533. List Redaction

Redaction must work for arrays and nested collections.

534. Circular Structures

Logging serializers must safely handle circular or unsupported structures without dumping sensitive object representations.

535. Object Serialization

Application objects should not automatically expose all attributes through generic serialization.

536. ORM Safety

Database model objects must not be dumped wholesale into logs.

537. Pydantic Safety

Structured application models should define explicit telemetry representations rather than logging entire request models.

538. HTTP Client Safety

HTTP clients must not log complete requests automatically.

539. HTTP Response Safety

HTTP clients must not log complete responses automatically.

540. Retry Debugging

Retry debugging should use:

request category;
attempt;
status;
timing.

rather than complete payloads.

541. Database Query Safety

Database debugging should avoid parameter values.

542. Stack Trace Safety

Stack traces should be accessible only to appropriate operational users.

User-facing errors remain sanitized.

543. File Upload Telemetry

File uploads should record:

file ID;
size;
type;
scan result;
outcome.

Not file contents.

544. Malware Scan Telemetry

Malware/security scanning may emit:

scanner;
version;
result;
duration.

Scanner output must be sanitized.

545. File Type Telemetry

File type values must be normalized and bounded.

546. Upload Error Telemetry

Upload failures should not expose file contents.

547. Archive Extraction Telemetry

Archive extraction may generate security events for:

path traversal;
decompression bombs;
unsafe file types.

Telemetry must not extract or log unbounded archive contents.

548. Path Traversal Event

Blocked traversal should generate security telemetry.

549. Command Injection Event

Blocked command injection should generate security telemetry.

550. SQL Injection Event

Blocked SQL injection attempts may generate security telemetry.

551. XSS Event

Blocked or detected XSS payloads may generate security telemetry.

552. SSRF Event

Blocked SSRF attempts should generate security telemetry.

553. Authentication Abuse Event

Repeated authentication failures may generate aggregated security telemetry.

554. Authorization Abuse Event

Repeated authorization failures may generate security telemetry.

555. Rate Limit Abuse Event

Repeated rate-limit violations may generate security telemetry.

556. Tool Policy Violation

Blocked unsafe tool invocation should generate security telemetry.

557. Agent Policy Violation

Blocked unsafe agent behavior should generate security telemetry.

558. Model Policy Violation

Model safety-test results may generate test/evaluation telemetry.

They are not automatically application security incidents.

559. Security Test Finding

A confirmed security-test finding may generate security telemetry and finding lifecycle events.

560. False Positive

A finding rejected as false positive should remain auditable where appropriate.

561. Accepted Risk

Accepted-risk decisions should be auditable.

562. Regression Detection

A regression detection should include:

test ID;
baseline;
current result;
application version;
target version where available.
563. Baseline Telemetry

Baseline creation and modification should be auditable.

564. Compliance Mapping

Compliance mappings may reference telemetry events.

This ADR does not define legal compliance semantics.

565. Audit Evidence

Security audit records can support compliance evidence but do not automatically establish compliance.

566. Time-Series Security Data

Security metrics should remain queryable over a defined retention window.

567. Aggregation

High-volume security events may be aggregated while preserving raw audit events where required.

568. Aggregation Integrity

Aggregates must not be treated as replacements for authoritative audit records.

569. Telemetry Labels

Labels must use controlled values.

570. Example Safe Labels

Safe labels include:

outcome=success
outcome=failure
component=worker
operation=model_request
571. Example Unsafe Labels

Unsafe labels include:

prompt=<arbitrary text>
response=<arbitrary text>
url=<unbounded URL>
error=<unbounded exception>
request_id=<millions of unique values>
572. Metric Name Integrity

Metric names are application-controlled.

573. Trace Name Integrity

Trace/span names should be application-controlled.

574. Log Event Integrity

Event names and severity must be application-controlled.

575. Audit Actor Integrity

Actor identity must come from trusted authentication context.

576. Audit Resource Integrity

Resource identity must come from trusted application state after authorization.

577. Audit Outcome Integrity

Outcome must be determined by the application.

578. Audit Reason Integrity

Security reasons should use controlled categories.

579. Free-Text Audit Fields

Free-text audit fields should be minimized.

580. Audit Metadata Size

Audit metadata must be bounded.

581. Audit Event Serialization

Audit events must use safe structured serialization.

582. Audit Event Validation

Events should be validated against a schema before persistence where practical.

583. Invalid Audit Event

Invalid events should not silently become arbitrary log strings.

584. Audit Event Failure

Failure to construct a mandatory audit event should be treated according to the critical operation's audit policy.

585. Audit Queue

An audit queue may buffer events.

It must be bounded and durable enough for the required guarantee.

586. Audit Queue Security

Queue payloads contain sensitive metadata and require appropriate protection.

587. Queue Encryption

Sensitive queues should use encrypted transport/storage where appropriate.

588. Queue Authorization

Only required services should access audit queues.

589. Queue Poisoning

Malformed or malicious events must not crash the entire audit consumer.

590. Dead-Letter Security

Dead-letter records may contain sensitive metadata and require protection.

591. Audit Replay

Replay mechanisms must not accidentally duplicate security actions.

592. Telemetry Replay

Telemetry replay should reproduce observation, not execute application actions.

593. Audit Replay Safety

Reprocessing an audit event must not grant authorization or trigger destructive actions.

594. Security Event Consumers

Consumers may:

aggregate;
alert;
index;
visualize.

They must not automatically perform privileged actions without explicit policy.

595. Automated Response

Future automated security response systems require a separate security architecture decision.

596. No Implicit Remediation

An alert must not automatically delete data, disable users, or modify targets unless explicitly authorized.

597. Telemetry as Evidence

Telemetry may become investigative evidence.

Its integrity and provenance must therefore be preserved.

598. Evidence Provenance

When telemetry is attached to a finding, preserve:

source;
timestamp;
event ID;
schema version;
relevant correlation IDs.
599. Provenance Integrity

Derived summaries must not overwrite original telemetry.

600. Audit Event Provenance

Audit events should identify their producer component.

601. Service Version

Security events should record service version where useful for incident investigation.

602. Configuration Version

Security-sensitive events may reference the active configuration/policy version.

603. Test Version

Test events should include test version where applicable.

604. Evaluator Version

Evaluation events should include evaluator version.

605. Attack Plan Version

Attack execution telemetry should include attack plan version.

606. Risk Model Version

Risk-related telemetry may include the risk model/version used.

607. Evidence Schema Version

Evidence references should remain compatible with ADR-008 schema versioning.

608. Cross-ADR Correlation

The observability layer should use stable identifiers from:

targets;
jobs;
tests;
attacks;
evaluations;
findings;
evidence.
609. No Identifier Guessing

Telemetry consumers must not infer resource ownership from IDs.

Authorization must query trusted state.

610. UUID Security

UUIDs provide identification but do not replace authorization.

611. Enumeration Resistance

Telemetry APIs should avoid allowing unauthorized enumeration of resource IDs.

612. Audit Event Pagination

Pagination must not leak whether unauthorized events exist.

613. Time Range Authorization

Time ranges do not override resource authorization.

614. Audit Filtering

Filtering by actor/project/target must remain authorization-scoped.

615. Telemetry Aggregation Authorization

Aggregated metrics must not reveal protected cross-project information to unauthorized users.

616. Differential Disclosure

Even aggregate counts can reveal sensitive information.

For example:

project X has 1 finding

may itself be sensitive.

617. Small-Group Aggregates

Where necessary, telemetry APIs should avoid exposing sensitive aggregate results for unauthorized populations.

618. Tenant-Level Aggregation

Tenant administrators may receive tenant-level aggregates subject to authorization.

619. Global Security Aggregation

Global security operators may receive system-wide metrics.

620. Access Logging

Access to telemetry dashboards and APIs should be logged.

621. Dashboard Export Logging

Dashboard exports should be auditable.

622. Saved Queries

Saved telemetry queries may contain sensitive filters.

Access to saved queries must be scoped.

623. Query Sharing

Shared telemetry queries must not bypass data authorization.

624. Telemetry Links

Links to telemetry records should use authorized references rather than embedding sensitive content.

625. Deep Links

Deep links must enforce authorization when opened.

626. Incident Links

Incident links should point to protected dashboards/resources.

627. URL Tokens

Telemetry URLs must not place sensitive tokens in query strings.

628. Browser History

Sensitive telemetry identifiers should be minimized in URLs because browser history may retain them.

629. Referrer Leakage

Telemetry pages should prevent sensitive identifiers from leaking through referrer headers where appropriate.

630. Caching

Sensitive telemetry responses must use appropriate cache controls.

631. Browser Cache

Security audit pages should not be cached publicly.

632. Proxy Cache

Sensitive telemetry must not be accidentally cached by shared proxies.

633. API Response Headers

Telemetry responses should include appropriate cache-control directives.

634. Content-Type

Telemetry APIs should return explicit safe content types.

635. JSON Encoding

Structured telemetry APIs should use safe JSON serialization.

636. Unicode Safety

Logs must safely handle Unicode content.

637. Normalization

Where security decisions depend on text normalization, the same normalization policy should be used consistently.

638. Homoglyphs

Telemetry should not rely solely on visual interpretation of identifiers.

639. Log Review Interfaces

UI should clearly distinguish:

trusted metadata;
untrusted payload;
generated summaries.
640. Untrusted Content Labels

Model outputs and user content displayed in telemetry should be visibly treated as data.

641. Safe Rendering

HTML escaping and safe text rendering are mandatory for untrusted telemetry.

642. Markdown Rendering

Raw model output should not be rendered as trusted Markdown in an audit UI.

643. Link Handling

URLs appearing in logs should not automatically become trusted executable links.

644. External Links

Opening external URLs from telemetry may create phishing/SSRF risks and should use safe browser behavior.

645. Security Dashboard Authentication

Security dashboards require authentication.

646. Security Dashboard Authorization

Security dashboards require explicit permissions.

647. Session Expiration

Telemetry dashboards follow normal session expiration policy.

648. Admin Reauthentication

Highly sensitive telemetry exports may require reauthentication depending on deployment policy.

649. MFA

MFA for privileged telemetry access is governed by the authentication architecture.

650. Audit Access Revocation

Revoking a user's telemetry permissions must take effect according to authorization cache/session policy.

651. Cached Telemetry Authorization

Telemetry results must not remain accessible after authorization changes through stale caches.

652. Cache Invalidation

Authorization-sensitive telemetry caches require appropriate invalidation.

653. Retention Deletion

Deletion jobs must themselves be observable.

654. Deletion Telemetry

Retention deletion may emit aggregate metadata:

records_deleted=1000
retention_category=debug

without logging deleted contents.

655. Deletion Failure

Failed retention jobs must be visible operationally.

656. Legal Hold

Future legal-hold features require separate policy.

657. Privacy Deletion

Privacy-driven deletion must consider:

logs;
traces;
metrics where identifiers exist;
audit records;
evidence;
backups.
658. Identifier-Based Deletion

Where feasible, telemetry should support locating records associated with a resource/user for authorized deletion workflows.

659. Deletion Boundaries

Security/audit retention requirements may constrain deletion.

This ADR does not define legal requirements.

660. Compliance

The architecture is designed to support auditable systems but does not claim compliance with any specific regulation.

661. Auditability

The architecture provides evidence for:

authentication;
authorization;
configuration;
test execution;
administrative actions;
security findings.
662. Accountability

Security-sensitive actions should be attributable to authenticated actors or trusted service identities.

663. Anonymous Actions

Anonymous actions should not be represented as authenticated users.

664. Service Actions

Automated jobs should use explicit service identity metadata.

665. Worker Identity

Workers should have stable identifiers where useful for operational investigation.

666. Job Actor

The initiating actor should remain distinguishable from the worker executing the job.

667. Delegation

If one service acts on behalf of another actor, telemetry should distinguish:

initiator
executor
668. Impersonation

Any future impersonation feature must generate explicit audit telemetry.

669. Privileged Automation

Privileged automated operations require service identity and auditability.

670. Scheduled Jobs

Scheduled jobs should record:

scheduler identity;
job ID;
execution time;
target/project scope;
outcome.
671. Automation Security

Scheduled execution must not bypass authorization.

672. Cancelled Schedules

Cancellation or modification of scheduled security testing should be auditable.

673. Recurring Tests

Recurring tests should correlate each run to:

schedule ID;
job ID;
test ID.
674. Regression Runs

Regression runs should be observable independently from manual runs.

675. Baseline Changes

Baseline modifications should be auditable.

676. Test Suite Changes

Security-test suite changes may affect findings and should be versioned/auditable.

677. Evaluator Changes

Evaluator changes can alter security conclusions and should be versioned.

678. Risk Model Changes

Risk model changes can alter severity and should be versioned.

679. Reporting Changes

Report schema changes should be versioned.

680. Observability Changes

Telemetry schema/policy changes should be versioned.

681. Release Correlation

A finding may need correlation with the Aegis Vuldris version that generated it.

682. Reproducibility

Telemetry should support reproducing the execution path without requiring unsafe replay of production actions.

683. Replay Safety

Replay should occur in isolated environments.

684. Replay Telemetry

Replayed tests should be clearly marked as replayed.

685. Synthetic Replay

Replay should prefer synthetic data where possible.

686. Production Replay

Production replay of sensitive requests is prohibited by default.

687. Evidence Replay

Evidence replay should not automatically send sensitive content to external services.

688. Network Replay

Network replay requires explicit target authorization.

689. Tool Replay

Tool replay requires explicit tool permissions.

690. Command Replay

Command replay requires isolated execution.

691. Audit Replay

Audit events must never be replayed as executable application commands.

692. Security Testing of Observability

Aegis Vuldris must security-test its own observability subsystem.

693. Observability Test Suite

The observability security suite should cover:

logging;
redaction;
audit;
metrics;
tracing;
telemetry APIs;
dashboards;
exports.
694. Secret Leak Test

Inject a synthetic secret into:

request;
model response;
tool output;
exception;
configuration;

and verify normal telemetry does not contain it.

695. Log Injection Test

Inject:

\n
\r
\t
ANSI escape sequences
JSON delimiters

and verify event structure remains safe.

696. Cross-Project Test

Create telemetry for project A and verify project B cannot retrieve it.

697. Cross-Tenant Test

Where tenants exist, verify telemetry cannot cross tenant boundaries.

698. Audit Access Test

Verify users without audit permission cannot retrieve audit records.

699. Audit Export Test

Verify export authorization and audit logging.

700. Audit Deletion Test

Verify deletion requires explicit privilege and is auditable.

701. Metric Cardinality Test

Use arbitrary attacker values and verify they do not create uncontrolled metric labels.

702. Trace Privacy Test

Verify prompts, responses, credentials, and cookies do not enter trace attributes.

703. Health Endpoint Test

Verify health endpoints do not disclose secrets or protected topology.

704. Dashboard XSS Test

Inject HTML/script-like values and verify safe rendering.

705. CSV Injection Test

Inject spreadsheet formula-like values and verify safe export.

706. URL Sanitization Test

Inject sensitive query parameters and verify redaction.

707. Error Leakage Test

Trigger database/network/auth errors and verify user-facing responses remain safe.

708. Collector Failure Test

Simulate collector failure and verify expected degraded behavior.

709. Disk Exhaustion Test

Test bounded logging behavior under storage pressure.

710. Queue Exhaustion Test

Test telemetry queue backpressure.

711. Concurrent Context Test

Run concurrent requests with different users/projects and verify no context crossover.

712. Worker Context Test

Run consecutive jobs from different projects and verify telemetry isolation.

713. Model Output Test

Provide malicious model output containing fake event metadata and verify trusted fields remain unchanged.

714. Tool Output Test

Provide malicious tool output containing fake audit records and verify it remains untrusted.

715. Evaluator Output Test

Provide malicious evaluator output and verify it cannot impersonate trusted security metadata.

716. Search Injection Test

Attempt SQL-like and expression-like telemetry filters.

717. Regex Abuse Test

Provide pathological regex input where supported and verify bounded execution.

718. Pagination Abuse Test

Request excessive telemetry pages or result sizes and verify limits.

719. Export Abuse Test

Attempt oversized telemetry export.

720. Authorization Race Test

Change permissions while telemetry queries are active and verify no unauthorized results are returned.

721. Retention Test

Verify telemetry is deleted according to retention policy.

722. Backup Test

Verify protected telemetry backups retain appropriate access controls.

723. Recovery Test

Verify observability recovers after telemetry backend failure.

724. Audit Recovery Test

Verify mandatory audit events are not silently lost after recovery.

725. Schema Compatibility Test

Verify telemetry consumers tolerate compatible schema changes.

726. Event Registry Test

Verify important events use registered names.

727. Unknown Event Test

Unknown/unregistered events should be rejected or safely classified rather than becoming trusted audit records.

728. Severity Test

User input attempting to set critical severity must not change trusted severity.

729. Actor Test

User input attempting to impersonate another actor must not change audit identity.

730. Resource Test

User input attempting to reference another project's target must not change authorized resource scope.

731. Service Identity Test

Model output must not become service identity.

732. Trace Context Test

Forged trace IDs must not change authorization.

733. Request ID Test

Forged request IDs must not grant access to telemetry.

734. Audit Ordering Test

Concurrent events should remain reconstructable using timestamps/correlation/sequence data.

735. Duplicate Event Test

Retries should not create misleading audit duplicates where idempotency is required.

736. Observability Documentation

Developer documentation should explain:

how to emit logs;
how to emit audit events;
how to add metrics;
how to create traces;
how to classify sensitive fields;
how to write redaction tests;
how to add new event types.
737. Contributor Rule

Contributors must not add raw payload logging simply because it helps debugging.

They must use approved observability/evidence mechanisms.

738. Code Review Rule

A pull request introducing a new sensitive log field should explain:

why it is needed;
its classification;
retention;
access;
redaction;
tests.
739. Security Review Rule

Changes affecting security audit events require security-aware review.

740. Privacy Review Rule

Changes that increase telemetry data collection require privacy-aware review.

741. Performance Review Rule

High-volume telemetry changes require performance review.

742. Operational Review Rule

Changes introducing new telemetry infrastructure require operational review.

743. Dependency Review Rule

New telemetry dependencies require supply-chain review.

744. Documentation Review Rule

Telemetry behavior that affects operators must be documented.

745. Rollback

Telemetry changes should be independently rollbackable where practical.

746. Safe Deployment

A telemetry deployment must not expose sensitive data merely because the collector/backend version changed.

747. Canary Deployment

Production telemetry changes may be introduced through staged deployment.

748. Monitoring Changes

Changes to monitoring should themselves be monitored.

749. Alert Validation

New security alerts should be tested before production rollout.

750. False Positive Management

Alert false positives should be reviewed without weakening underlying security event generation.

751. Security Event Retention

Security events required for incident investigation must have retention sufficient for operational needs.

752. Audit Storage Availability

Production deployments must monitor audit storage availability.

753. Audit Storage Capacity

Production deployments must monitor audit storage capacity.

754. Audit Export Availability

If audit exports are supported, export functionality should be monitored.

755. Telemetry Health Dashboard

Operators should have a dashboard showing:

collector status;
event ingestion;
dropped events;
storage;
exporter failures.
756. Security Telemetry Dashboard

Authorized security operators should have:

authentication trends;
authorization failures;
security event counts;
blocked network operations;
job anomalies;
audit failures.
757. Application Dashboard

Application operators should have:

API latency;
errors;
database health;
worker health;
model adapter health.
758. Test Dashboard

Security-test operators should have:

executions;
outcomes;
duration;
errors;
target failures;
evaluator failures.
759. Privacy Dashboard

Privacy/security operators may have:

leakage detections;
sensitive-data matches;
evidence counts;
privacy finding trends.
760. Dashboard Isolation

Each dashboard must expose only data appropriate to its intended role.

761. Dashboard Data Freshness

Dashboards should display freshness indicators where delayed telemetry could cause confusion.

762. Stale Metrics

Operators must be able to distinguish zero activity from missing telemetry.

763. Telemetry Silence

Missing telemetry may itself be an operational signal.

764. Heartbeats

Workers and collectors may emit heartbeats.

Heartbeat data should remain lightweight.

765. Heartbeat Security

Heartbeat endpoints must not expose secrets or permit arbitrary worker registration.

766. Worker Registration

Future dynamic worker registration requires authentication and authorization.

767. Worker Spoofing

Worker identity must be authenticated.

768. Service Discovery

Telemetry service discovery must not be controlled by model output or user input.

769. Collector Discovery

Collector endpoints come from trusted deployment configuration.

770. Network Policy

Telemetry network paths should follow deployment network policy.

771. Firewall Rules

Production telemetry endpoints should be restricted to necessary sources.

772. Ingress Security

Telemetry ingestion endpoints must be protected from arbitrary public access unless explicitly designed for it.

773. Egress Security

Telemetry exporters should only reach approved destinations.

774. Proxy Security

Proxy configuration must be trusted.

775. DNS Security

Telemetry destinations should be resolved and connected according to secure network policy.

776. Certificate Validation

TLS certificate validation must not be disabled merely to simplify telemetry setup.

777. Telemetry Credentials Rotation

Exporter credentials should support rotation.

778. Credential Revocation

Revoked telemetry credentials should no longer be accepted.

779. Secret Storage

Telemetry secrets follow ADR-014 when that ADR is implemented.

780. Environment Separation

Development, test, staging, and production telemetry destinations must remain distinct.

781. Production Data Isolation

Production telemetry must not be sent to development telemetry systems.

782. Test Data Isolation

Test telemetry should not pollute production audit stores.

783. Staging Isolation

Staging telemetry should remain separate unless explicitly aggregated.

784. Local Developer Privacy

Local development telemetry should avoid unnecessary persistence of real sensitive data.

785. Demo Environment

Demo environments should use synthetic data.

786. Example Configuration

Documentation must use placeholders, never real credentials.

787. Sample Logs

Sample logs must contain synthetic identifiers and values.

788. Sample Secrets

Example secrets must be clearly synthetic and nonfunctional.

789. Documentation Safety

Documentation must not teach contributors to print credentials for debugging.

790. Debugging Guide

The debugging guide should recommend safe metadata capture.

791. Sensitive Debugging

Sensitive debugging should point developers toward evidence capture where appropriate.

792. Evidence Reference Debugging

Developers should use evidence IDs to inspect protected artifacts rather than copying them into logs.

793. Operational Runbook Example

A model adapter failure should be diagnosed through:

request_id
job_id
target_id
adapter_type
duration
status
error_category

not by dumping the API key or full prompt.

794. Security Incident Example

A suspected unauthorized target access should be investigated through:

actor
request_id
target_id
project_id
authorization_result
timestamp

plus controlled application records.

795. Privacy Incident Example

A suspected leakage should correlate:

test_execution_id
target_id
evaluation_id
finding_id
evidence_id

without copying the leaked value into logs.

796. Production Incident Example

A worker failure should correlate:

job_id
worker_id
test_execution_id
error_category
retry_count
797. Audit Example

A privileged target configuration change should create:

event=target.updated
actor=<trusted actor>
target_id=<target>
project_id=<authorized project>
outcome=success

without secret configuration values.

798. Security Boundary Principle

Observability records what the security boundary decided.

It does not define the security boundary.

799. Authorization Principle

Authorization must be enforced before telemetry access.

800. Evidence Principle

Sensitive evidence must remain in evidence storage.

801. Privacy Principle

Telemetry must collect the minimum information required.

802. Integrity Principle

Trusted telemetry metadata must come from trusted application state.

803. Availability Principle

Observability must remain resource-bounded.

804. Reliability Principle

Critical security audit events require stronger delivery guarantees than low-priority diagnostics.

805. Open-Source Principle

The core observability architecture must remain compatible with open-source infrastructure.

806. Zero-Cost Development Principle

Local development must not require paid monitoring services.

807. Vendor-Neutral Principle

Application instrumentation should remain portable across telemetry backends.

808. Portability

OpenTelemetry-compatible instrumentation should minimize backend lock-in.

809. Maintainability

Telemetry APIs should be small and consistent.

810. Developer Experience

Adding safe telemetry should be easier than writing ad hoc logging.

811. Centralized Policy

Security-sensitive logging policy should be centralized.

812. Decentralized Event Production

Business/security components may produce semantic events through the centralized observability abstraction.

813. Separation of Concerns

Business logic should not contain telemetry-backend implementation details.

814. Testing Boundary

Observability should be independently testable.

815. Failure Boundary

Telemetry failures should be isolated from unrelated application failures.

816. Security Boundary

Telemetry infrastructure must not grant application privileges.

817. Data Boundary

Telemetry data must not automatically gain access to evidence storage.

818. Network Boundary

Telemetry exporters must not gain arbitrary network access.

819. Filesystem Boundary

Telemetry must not read arbitrary files merely to improve diagnostics.

820. Command Boundary

Telemetry must never execute commands based on logged content.

821. Parser Boundary

Telemetry parsers must treat incoming data as untrusted.

822. Plugin Boundary

Telemetry plugins must be treated as executable code and trusted accordingly.

823. AI Boundary

AI-generated telemetry summaries are untrusted derived content.

824. Administrative Boundary

Observability administration is privileged functionality.

825. Audit Boundary

Audit records require stronger integrity than ordinary debug logs.

826. Retention Boundary

Retention policy must distinguish operational logs from security records and evidence.

827. Backup Boundary

Telemetry backups are sensitive assets.

828. Export Boundary

Telemetry exports create new copies of sensitive information and therefore require authorization.

829. Incident Boundary

Incident-management systems must not automatically receive raw sensitive telemetry.

830. Monitoring Boundary

Monitoring services are external trust boundaries when separately deployed.

831. Security Testing Boundary

Aegis Vuldris's own observability system must be included in security testing.

832. Regression Boundary

Observability security bugs must become regression tests.

833. Release Boundary

Telemetry schema and policy changes require release review.

834. Governance Boundary

Audit-policy changes require appropriate governance.

835. Acceptance Criterion 1

All backend requests have safe request correlation.

836. Acceptance Criterion 2

Authentication and authorization security events are auditable.

837. Acceptance Criterion 3

Secrets do not appear in ordinary telemetry.

838. Acceptance Criterion 4

Raw prompts and responses are disabled by default.

839. Acceptance Criterion 5

Telemetry APIs enforce project/tenant authorization.

840. Acceptance Criterion 6

Metrics have bounded cardinality.

841. Acceptance Criterion 7

Telemetry payloads are size-bounded.

842. Acceptance Criterion 8

Model output cannot manipulate trusted telemetry metadata.

843. Acceptance Criterion 9

Tool output cannot manipulate trusted telemetry metadata.

844. Acceptance Criterion 10

Audit access is itself auditable.

845. Acceptance Criterion 11

Health endpoints do not disclose secrets.

846. Acceptance Criterion 12

Telemetry failure cannot bypass authorization.

847. Acceptance Criterion 13

Critical audit events have defined delivery behavior.

848. Acceptance Criterion 14

Redaction has automated tests.

849. Acceptance Criterion 15

Log injection has automated tests.

850. Acceptance Criterion 16

Cross-project telemetry isolation has automated tests.

851. Acceptance Criterion 17

Worker context isolation has automated tests.

852. Acceptance Criterion 18

Evidence remains separate from normal logs.

853. Acceptance Criterion 19

External telemetry export is explicit.

854. Acceptance Criterion 20

Observability is documented for contributors.

855. Acceptance Criterion 21

Production deployment can use open-source telemetry components.

856. Acceptance Criterion 22

Telemetry can operate without a paid SaaS dependency.

857. Acceptance Criterion 23

Telemetry schema is versioned.

858. Acceptance Criterion 24

Security event semantics are stable and documented.

859. Acceptance Criterion 25

Telemetry retention is configurable.

860. Acceptance Criterion 26

Telemetry storage is access-controlled.

861. Acceptance Criterion 27

Telemetry backups are protected.

862. Acceptance Criterion 28

Telemetry resource consumption is bounded.

863. Acceptance Criterion 29

Security events remain distinguishable from ordinary test failures.

864. Acceptance Criterion 30

A production incident can be correlated across request, job, test, attack, evaluation, finding, and evidence identifiers where applicable.

865. Implementation Checklist

Initial implementation checklist:

 structured logger;
 request context;
 request ID middleware;
 redaction utility;
 audit event interface;
 audit event schema;
 authentication audit events;
 authorization audit events;
 configuration audit events;
 job telemetry;
 test telemetry;
 model adapter telemetry;
 evaluation telemetry;
 finding lifecycle telemetry;
 metrics;
 health checks;
 trace instrumentation;
 telemetry API authorization;
 retention;
 security tests.
866. Initial Package Strategy

The first implementation should remain intentionally small.

Recommended initial modules:

observability/
    __init__.py
    context.py
    logging.py
    redaction.py
    audit.py
    metrics.py
    health.py

Tracing can be added once the foundational interfaces are stable.

867. Logging Implementation Order

Implement:

structured logger;
context;
redaction;
size limits;
test sink;
application integration.
868. Audit Implementation Order

Implement:

event schema;
audit interface;
persistence;
authorization;
audit tests;
access auditing.
869. Metrics Implementation Order

Implement:

metric abstraction;
request counters;
latency;
job metrics;
test metrics;
model adapter metrics.
870. Health Implementation Order

Implement:

liveness;
readiness;
database readiness;
worker readiness if applicable.
871. Tracing Implementation Order

Implement:

request traces;
database spans;
model adapter spans;
job spans;
test spans;
evaluation spans.
872. Dashboard Implementation Order

Later dashboard work should begin with:

application health;
job health;
test execution;
security events;
performance.
873. Production Hardening

Before production:

validate retention;
validate redaction;
validate access control;
validate audit durability;
validate storage;
validate backup;
validate alerting;
validate failure modes.
874. Security Review

A security review is required before enabling raw sensitive telemetry in any deployment.

The default architecture does not permit raw sensitive telemetry.

875. Privacy Review

A privacy review is required before increasing telemetry collection of personal or confidential data.

876. Operational Review

A production telemetry deployment must have:

storage sizing;
retention;
rotation;
backup;
monitoring;
alerting;
recovery.
877. Performance Review

High-volume telemetry must be benchmarked.

878. Load Testing

Load testing should verify:

logging overhead;
metrics overhead;
tracing overhead;
audit overhead;
queue behavior.
879. Telemetry Overhead

Observability must not impose unacceptable latency or resource usage.

880. Sampling Under Load

Low-priority logs/traces may be sampled under high load.

Mandatory audit events remain protected.

881. Backpressure Under Load

Telemetry backpressure must not cause unbounded application memory growth.

882. Security Under Load

Security enforcement must remain functional during telemetry overload.

883. Audit Under Load

Critical audit events must retain their documented guarantees under expected production load.

884. Failure Injection

Chaos/failure tests may simulate:

collector outage;
database outage;
exporter outage;
disk full;
queue full;
worker crash.
885. Recovery

Recovery should preserve event correlation and avoid context contamination.

886. Operational Documentation

Operators must know:

where logs go;
where audit records go;
where metrics go;
where traces go;
how to investigate failures;
how to rotate credentials;
how to handle telemetry outages.
887. Security Documentation

Developers must know:

what must never be logged;
how to redact;
how to create audit events;
how to preserve evidence.
888. Contributor Education

The repository documentation should contain safe logging examples.

889. Unsafe Example

This pattern is prohibited:

logger.info(f"request={request.json()}")

when the request may contain secrets or sensitive data.

890. Safer Example

Prefer:

logger.info(
    "request.received",
    request_id=request_id,
    route=route_name,
)
891. Unsafe Model Example

This is prohibited by default:

logger.debug("model_response=%s", response.text)
892. Safer Model Example

Prefer:

logger.info(
    "model.request.completed",
    target_id=target_id,
    duration_ms=duration_ms,
    outcome="success",
)
893. Unsafe Credential Example

This is prohibited:

logger.info("api_key=%s", api_key)
894. Safer Credential Example

Prefer:

logger.info(
    "credential.configured",
    credential_id=credential_id,
)
895. Unsafe Exception Example

Avoid:

logger.exception("request failed: %s", request)

if request serialization may expose sensitive fields.

896. Safer Exception Example

Prefer:

logger.exception(
    "request.failed",
    request_id=request_id,
    error_type=type(exc).__name__,
)

with centralized safe exception handling.

897. Audit Example

A privileged configuration change should record:

event=configuration.changed
actor_id=<trusted>
resource_type=target
resource_id=<trusted>
outcome=success

not the secret configuration value.

898. Decision

Aegis Vuldris adopts a centralized, structured, privacy-aware, security-aware observability architecture with separate application logging, audit logging, metrics, and tracing concerns.

OpenTelemetry-compatible instrumentation will be preferred for portable tracing/metrics/logging integration.

Open-source telemetry infrastructure will be preferred for production deployments.

Raw prompts, model responses, credentials, and sensitive evidence will not be logged by default.

Security-sensitive actions will produce controlled audit events.

Telemetry access will follow the same authentication, authorization, project isolation, and tenant isolation principles as the rest of Aegis Vuldris.

899. Consequences
Positive
Better production debugging.
Stronger security auditability.
Better incident investigation.
Safer AI-specific telemetry.
Better test execution visibility.
Better worker/job visibility.
Better performance analysis.
Reduced accidental secret leakage.
Portable observability architecture.
Open-source production options.
Stronger regression testing.
Better operational readiness.
Negative
Additional implementation complexity.
Additional storage requirements.
Additional testing requirements.
Redaction maintenance.
Telemetry schema governance.
Operational monitoring requirements.
Some debugging becomes less convenient because raw payloads are intentionally unavailable.
Critical audit paths may increase coupling for security-sensitive operations.
900. Alternatives Considered
Alternative 1: Plain Text Logging Everywhere

Rejected.

It is difficult to query, easy to inject into, and unsafe for sensitive AI workloads.

Alternative 2: Log Every Request and Response

Rejected.

This creates a significant privacy and secret-leakage risk.

Alternative 3: Application Logs Only

Rejected.

Application logs do not provide sufficient audit, metric, and distributed execution visibility.

Alternative 4: Commercial Monitoring SaaS as a Requirement

Rejected.

It conflicts with the open-source and zero-cost development goals and creates an unnecessary external trust boundary.

Alternative 5: Custom Proprietary Telemetry Protocol

Rejected.

Open standards such as OpenTelemetry provide better interoperability.

Alternative 6: Separate Telemetry Database Immediately

Deferred.

A separate database may be appropriate at scale, but the MVP should avoid unnecessary operational complexity.

Alternative 7: No Audit Logging

Rejected.

Security-sensitive administrative, authentication, authorization, and testing actions require accountability.

901. Relationship to Future ADRs

ADR-014 will define:

configuration;
secrets;
environment management;
credential handling.

ADR-015 will define:

production deployment;
operational architecture;
infrastructure;
deployment topology.

This ADR provides the observability requirements those future decisions must satisfy.

902. Implementation Gate

Implementation of observability functionality may begin after this ADR is accepted.

However, production enablement requires verification of:

redaction;
authorization;
retention;
audit durability;
resource limits;
security testing;
telemetry isolation;
external exporter controls.
903. Final Security Principle

Aegis Vuldris must never create a privacy, confidentiality, integrity, or authorization vulnerability merely to make the system easier to observe.

904. Final Decision Statement

Accepted.

Aegis Vuldris will use structured, correlated, privacy-aware observability with distinct application logging, security auditing, metrics, and tracing.

Observability will remain subordinate to the application's security boundaries, authorization model, evidence architecture, and privacy controls.

The system must be observable enough to explain what happened while collecting no more sensitive information than necessary.
