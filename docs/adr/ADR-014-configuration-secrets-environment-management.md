# ADR-014: Configuration, Secrets & Environment Management Architecture

**Status:** Accepted
**Date:** 2026-09-10
**Decision Owners:** Aegis Vuldris Maintainers

---

## 1. Decision Summary

Aegis Vuldris will use an explicit, validated, environment-aware configuration architecture with strict separation between ordinary configuration and secrets.

Configuration will be loaded through a centralized configuration layer rather than being read directly throughout the application.

Secrets will never be committed to source control, embedded in frontend bundles, written to logs, exposed through API responses, included in reports, or placed into telemetry by default.

Development, testing, staging, and production environments will use the same configuration model while supplying environment-specific values through appropriate mechanisms.

Secure defaults will be mandatory.

Required configuration will be validated at startup or before the dependent capability is activated.

Aegis Vuldris will prefer environment variables and deployment-provided secret injection for runtime configuration and will support local `.env` files for developer convenience without treating them as production secret stores.

The frontend will never receive server-side secrets.

Configuration access will follow least privilege.

Sensitive configuration changes will be auditable where appropriate.

Configuration values crossing trust boundaries will be treated according to the security boundaries defined by the threat model and security baseline.

The central principle is:

> Configuration must be explicit, validated, environment-aware, and secure by default; secrets must never be committed to source control or exposed through logs, reports, telemetry, errors, or client-side code.

---

# 2. Context

Aegis Vuldris requires configuration for many subsystems.

Examples include:

- application identity;
- runtime environment;
- database connectivity;
- authentication;
- authorization;
- session handling;
- cryptographic keys;
- model providers;
- model API credentials;
- target endpoints;
- network policies;
- rate limits;
- worker configuration;
- job execution;
- observability;
- report generation;
- evidence storage;
- retention;
- feature flags;
- external integrations;
- testing behavior;
- development tooling;
- production deployment.

Some values are ordinary configuration.

Examples:

- application name;
- log level;
- API bind address;
- port;
- worker count;
- timeout values;
- feature enablement;
- maximum request size.

Other values are secrets.

Examples:

- database passwords;
- API keys;
- access tokens;
- signing keys;
- encryption keys;
- session secrets;
- webhook credentials;
- provider credentials;
- administrative credentials.

Treating both classes identically creates unnecessary risk.

Hard-coded configuration can create operational rigidity.

Hard-coded secrets create serious security risk.

Scattered environment-variable reads create inconsistent behavior.

Unvalidated configuration can cause unsafe runtime states.

Configuration accidentally returned by an API can expose credentials.

Configuration included in logs can create credential leakage.

Configuration embedded into frontend JavaScript becomes client-visible.

Configuration copied into reports or evidence can create secondary disclosure.

Aegis Vuldris therefore requires a dedicated architecture decision.

---

# 3. Problem Statement

Aegis Vuldris must answer the following questions consistently:

1. Where does configuration come from?
2. How is configuration validated?
3. How are secrets distinguished from non-secret values?
4. How are development values supplied?
5. How are tests supplied with safe configuration?
6. How are production secrets injected?
7. How are secrets prevented from entering logs?
8. How are secrets prevented from entering telemetry?
9. How are secrets prevented from entering reports?
10. How are configuration changes audited?
11. How are secrets rotated?
12. What happens when required configuration is missing?
13. How are configuration values exposed to the frontend?
14. How are tenant/project-specific settings isolated?
15. How are model-provider credentials protected?
16. How are Docker and CI/CD environments configured?
17. How are configuration precedence rules defined?
18. How are insecure configurations rejected?
19. How are configuration schemas versioned?
20. How are configuration-related failures tested?

Without explicit answers, different components could implement configuration differently.

That would increase security and operational risk.

---

# 4. Goals

This architecture has the following goals:

1. Centralize configuration loading.
2. Validate configuration consistently.
3. Separate secrets from ordinary configuration.
4. Provide secure defaults.
5. Support development environments.
6. Support automated testing.
7. Support Docker-based development.
8. Support production deployment.
9. Prevent accidental secret exposure.
10. Prevent frontend secret exposure.
11. Support secret rotation.
12. Support configuration versioning.
13. Support operational observability without leaking secrets.
14. Support tenant/project isolation.
15. Support least-privilege configuration access.
16. Make configuration behavior predictable.
17. Make configuration failures explicit.
18. Make security assumptions testable.
19. Keep the architecture open-source compatible.
20. Avoid requiring proprietary secret-management infrastructure for the MVP.

---

# 5. Non-Goals

This ADR does not define:

- application authentication implementation;
- authorization policy implementation;
- model adapter protocol implementation;
- evidence storage implementation;
- risk scoring;
- observability architecture;
- deployment-specific infrastructure implementation.

Those concerns are covered by other ADRs.

This ADR defines how configuration and secrets interact with those systems.

---

# 6. Related Architecture Decisions

This ADR depends on and complements:

- ADR-001: Backend Framework
- ADR-002: Frontend Framework
- ADR-003: Database Architecture
- ADR-004: API Communication Architecture
- ADR-005: Test Execution and Job Architecture
- ADR-006: Authentication and Authorization Architecture
- ADR-007: Model Adapter and Target Integration Architecture
- ADR-008: Evidence, Findings and Reporting Architecture
- ADR-009: Risk Scoring and Severity Assessment Architecture
- ADR-010: Security Test Suite and Evaluation Architecture
- ADR-011: Attack Orchestration and Multi-Turn Execution
- ADR-012: Privacy, Data Leakage and Sensitive Data Handling
- ADR-013: Observability, Audit Logging and Telemetry

Configuration architecture must not contradict the security invariants established by those decisions.

---

# 7. Core Principles

## 7.1 Secure by Default

Default configuration must prefer the safer behavior.

Examples:

- authentication enabled where required;
- debug disabled outside development;
- verbose error output disabled in production;
- unrestricted outbound networking disabled;
- dangerous tools disabled;
- insecure transport disabled;
- arbitrary filesystem access disabled;
- command execution disabled;
- external telemetry disabled unless explicitly configured.

---

## 7.2 Explicit Configuration

Important security-sensitive behavior must not depend on hidden defaults.

A security-sensitive setting should be:

- explicitly defined;
- validated;
- documented;
- testable.

---

## 7.3 Centralized Configuration

Application components must not independently parse arbitrary environment variables.

Configuration access should flow through a centralized configuration module.

Conceptually:

```text
Environment / Secret Source
          |
          v
Configuration Loader
          |
          v
Validation
          |
          v
Immutable Runtime Configuration
          |
          +--> Application
          +--> Database
          +--> Authentication
          +--> Model Adapters
          +--> Jobs
          +--> Security Controls
          +--> Observability
8. Configuration Classes

Aegis Vuldris will classify configuration into several categories.

8.1 Public Configuration

Values that are safe to expose publicly.

Examples:

product name;
public documentation URL;
public frontend configuration;
non-sensitive feature descriptions.
8.2 Internal Configuration

Values that are not secrets but should generally remain server-side.

Examples:

internal service names;
worker settings;
queue settings;
internal hostnames.
8.3 Sensitive Configuration

Values that could expose internal security or operational information.

Examples:

internal network policies;
detailed infrastructure configuration;
security thresholds;
internal service endpoints.
8.4 Secrets

Secrets provide authentication, authorization, signing, encryption, or privileged access.

Examples:

passwords;
API keys;
bearer tokens;
signing keys;
encryption keys;
session secrets;
private credentials.

Secrets receive the strongest handling requirements.

9. Configuration Source Hierarchy

Aegis Vuldris will use an explicit configuration precedence model.

The exact implementation may evolve, but the conceptual precedence is:

Built-in Safe Defaults
        |
        v
Configuration File / Deployment Defaults
        |
        v
Environment Variables
        |
        v
Secret Injection
        |
        v
Explicit Runtime Overrides

Higher-precedence configuration must never silently bypass security validation.

A value supplied through a higher-precedence source is still subject to validation.

10. Environment Variables

Environment variables are the primary deployment-friendly configuration mechanism.

Examples:

APP_NAME
APP_ENV
LOG_LEVEL
DATABASE_URL
SECRET_KEY
MODEL_PROVIDER
MODEL_BASE_URL
MODEL_API_KEY

Environment variable names must be documented.

Unknown environment variables should not silently modify security behavior.

11. Environment Separation

Aegis Vuldris will explicitly distinguish at least:

development
test
staging
production

Each environment may use different values.

Security-sensitive defaults must become stricter as the environment becomes more production-like.

12. Development Environment

Development should be convenient without teaching unsafe habits.

Developers may use:

.env

for local configuration.

The .env file must remain ignored by Git.

Only:

.env.example

may be committed.

13. .env.example

The example file must contain placeholders rather than real secrets.

Example:

APP_NAME=Aegis Vuldris
APP_ENV=development

DATABASE_URL=
SECRET_KEY=

MODEL_PROVIDER=
MODEL_BASE_URL=
MODEL_API_KEY=

The example file must never contain:

production passwords;
personal API keys;
real tokens;
private certificates;
private SSH keys;
real database credentials.
14. .env Security

Local .env files may contain development secrets.

They must:

remain untracked;
be excluded from build artifacts;
be excluded from frontend bundles;
not be copied into container images;
not be included in reports;
not be uploaded to GitHub;
not be attached to issue reports.
15. Production Secret Injection

Production secrets should be injected by the deployment environment.

Examples include:

environment variables;
mounted secret files;
container secret mechanisms;
operating-system secret stores;
dedicated open-source secret managers.

Aegis Vuldris must not require secrets to be committed into application source code.

16. No Hard-Coded Secrets

The following are prohibited:

API_KEY = "real-secret"
SECRET_KEY = "production-password"
DATABASE_URL=postgres://admin:realpassword@...

inside tracked source files.

Security-sensitive tests must actively detect accidental hard-coded credentials where practical.

17. Secret Naming

Secret variables should communicate their sensitivity.

Examples:

DATABASE_PASSWORD
SECRET_KEY
MODEL_API_KEY
JWT_SIGNING_KEY
ENCRYPTION_KEY
WEBHOOK_SECRET

Naming must remain consistent throughout the project.

18. Secret Objects

The application should avoid treating secrets as ordinary strings throughout the entire codebase where practical.

A conceptual secret abstraction may provide:

controlled access;
redaction;
non-printable representation;
explicit serialization restrictions.

Example conceptual type:

SecretValue

The implementation may use an established validation library rather than creating unnecessary custom cryptographic primitives.

19. Configuration Validation

Configuration must be validated before use.

Validation should include:

required values;
data types;
allowed values;
URL formats;
port ranges;
timeout ranges;
size limits;
security constraints;
environment-specific restrictions.

Invalid configuration should fail clearly.

20. Startup Validation

Critical configuration should be validated during application startup.

Examples:

database URL;
required application secret;
cryptographic configuration;
authentication configuration;
production security settings.

The application should fail closed rather than silently running in an unsafe state.

21. Partial Startup

Aegis Vuldris should avoid partially initialized security-sensitive services.

If authentication configuration is invalid, the API should not silently start with authentication disabled.

If database security configuration is invalid, the service should not silently fall back to an insecure database connection.

22. Production Validation

Production startup should apply stricter checks.

Examples:

APP_ENV=production
DEBUG=false

must be compatible.

Production may reject:

development-only authentication bypasses;
unsafe CORS configuration;
wildcard trusted hosts;
unrestricted debug endpoints;
insecure cookie settings;
plaintext secrets in configuration files;
unrestricted network access.
23. Configuration Immutability

Once startup configuration is validated, runtime components should treat core configuration as immutable.

This reduces:

race conditions;
unexpected state changes;
configuration confusion;
security bypasses.

Dynamic configuration changes should occur through explicitly designed mechanisms.

24. Runtime Configuration Changes

Runtime configuration changes must not be implemented through arbitrary mutation.

Security-sensitive changes should use:

authenticated actor;
authorization check;
validation;
audit event;
controlled application;
rollback or recovery mechanism where appropriate.
25. Tenant and Project Configuration

Aegis Vuldris may support configuration scoped to:

installation;
tenant;
project;
target;
test profile;
job.

Scope must be explicit.

A project-scoped setting must never unintentionally affect another project.

26. Configuration Precedence Across Scopes

A conceptual hierarchy is:

System
  |
  v
Tenant
  |
  v
Project
  |
  v
Target
  |
  v
Test/Profile

A narrower scope may override an allowed parent value.

However, child configuration must never weaken a mandatory security boundary.

For example:

project configuration

must not disable a system-wide SSRF protection control.

27. Security Floor

Aegis Vuldris will support the concept of mandatory security floors.

Example:

System Security Policy
        |
        v
Tenant Configuration
        |
        v
Project Configuration
        |
        v
Target Configuration

Lower scopes may configure behavior only within the security limits imposed by higher scopes.

28. Secret Scope

Secrets must also have scope.

Examples:

application secret;
database secret;
model-provider credential;
project integration credential;
target-specific credential.

A secret should only be accessible to the component that requires it.

29. Least Privilege

Components must receive only the configuration they require.

For example:

Frontend
    -> public configuration only

API
    -> API-required configuration

Worker
    -> worker-required configuration

Model Adapter
    -> provider credential only when required
30. Frontend Configuration Boundary

The frontend is untrusted from the perspective of server-side security.

The frontend must never receive:

database credentials;
API provider keys;
signing keys;
encryption keys;
session secrets;
internal service credentials;
privileged administrative secrets.
31. Public Frontend Configuration

If frontend configuration is required, it must be explicitly classified as public.

Examples:

PUBLIC_API_BASE_URL
PUBLIC_BUILD_VERSION
PUBLIC_FEATURE_FLAG

Anything injected into a browser bundle must be assumed public.

32. Build-Time Frontend Configuration

Build systems must distinguish:

public build variables

from:

server secrets

A secret must never be passed as a frontend build argument merely because the build system supports environment variables.

33. Docker Configuration

Docker Compose will support local development configuration.

Conceptually:

docker-compose.yml
.env
.env.example

must be clearly separated.

Production Docker deployment should use deployment-managed secrets rather than committing secret-bearing Compose files.

34. Container Image Security

Container images must not contain:

.env;
private keys;
API keys;
database passwords;
developer credentials;
SSH credentials;
test secrets.

Secret files must not accidentally enter an image through broad build contexts.

35. Docker Build Context

The .dockerignore file should exclude:

.env
.env.*
.git
.venv
node_modules
reports
logs
temporary files

and other sensitive or unnecessary content.

36. CI/CD Secrets

CI/CD systems may provide secrets through their native secure secret mechanisms.

Secrets must not be written directly into workflow source.

Workflows must avoid printing secret-bearing environment variables.

37. CI/CD Log Protection

CI jobs must avoid commands that dump complete environments.

Avoid patterns such as:

Get-ChildItem Env:

or:

env

when secrets may be present.

38. Pull Request Protection

Automated checks should detect likely secrets before merge.

Possible controls include:

secret scanning;
credential pattern detection;
repository scanning;
dependency scanning;
pre-commit checks.

False positives must be handled without weakening secret protection globally.

39. Secret Rotation

Secrets must be replaceable without changing application source code.

Rotation should support:

generate replacement;
deploy replacement;
verify;
revoke old credential;
verify old credential no longer works.
40. Rotation Compatibility

Components should avoid unnecessarily caching secrets indefinitely.

Long-lived processes should have a documented strategy for configuration reload or controlled restart when credentials rotate.

41. Cryptographic Keys

Cryptographic keys require stronger handling than ordinary configuration.

Examples:

session signing keys;
token signing keys;
encryption keys;
key derivation material.

They must not be logged or returned through normal APIs.

42. Cryptographic Key Rotation

Key rotation should account for:

existing sessions;
existing signed objects;
key identifiers;
verification windows;
migration;
emergency revocation.

The exact cryptographic protocol belongs to the subsystem using the key.

43. Secret Generation

Secrets should be generated using cryptographically secure randomness.

Application code must not use predictable values such as:

123456
password
secret
development

for production security controls.

44. Development Secrets

Development may use generated local secrets.

However, development values should not accidentally become production defaults.

45. Test Secrets

Tests should use synthetic credentials.

Examples:

TEST_API_KEY
TEST_DATABASE_PASSWORD
TEST_SIGNING_SECRET

These must not correspond to real external credentials.

46. Canary Secrets

Privacy and leakage testing may use synthetic canaries.

Canaries must be clearly synthetic.

They must never be confused with actual production credentials.

47. Model Provider Credentials

Model provider API keys are highly sensitive.

They must:

remain server-side;
never be returned to the frontend;
never appear in findings;
never appear in model prompts;
never be written into model test inputs;
never be logged by default;
be redacted from exceptions;
be protected from accidental evidence capture.
48. Target Credentials

If Aegis Vuldris tests an authorized target requiring authentication, target credentials must be scoped to that target.

They must not be:

copied into generic project data;
sent to unrelated targets;
included in reports;
included in telemetry;
reused outside their authorization scope.
49. Credential Isolation

Credentials for one target must not automatically become available to another target.

Target identity and credential identity must remain distinct.

50. Configuration and Model Prompts

Configuration must never be automatically injected into model prompts.

In particular, secrets must never become available to a target model merely because they exist in process memory.

51. Prompt Construction Boundary

Any configuration included in prompts must be explicitly selected.

For example:

safe test metadata

may be included.

But:

DATABASE_PASSWORD
MODEL_API_KEY
SECRET_KEY

must never be included.

52. Logging Boundary

Logging is an independent security boundary.

Configuration values crossing into logging must pass through redaction rules.

This aligns with ADR-013.

53. Secret Redaction

Sensitive values should be redacted before logging.

Example:

MODEL_API_KEY=***
DATABASE_PASSWORD=***

Redaction should be centralized.

54. Partial Secret Exposure

Partial masking is preferred over complete omission only when operationally safe.

For example:

sk-************

may be useful for identifying which credential was configured.

However, exposing prefixes must be evaluated for the credential format.

When uncertain, redact completely.

55. Error Handling

Configuration errors must not reveal secret values.

Bad:

Invalid API key: sk-live-actual-secret-value

Good:

Invalid model provider credential configuration.
56. Exception Safety

Exceptions must not contain:

raw secrets;
database URLs with passwords;
Authorization headers;
session cookies;
private keys.

Exception formatting should apply centralized sanitization where appropriate.

57. Database URLs

Database URLs frequently contain credentials.

For example:

postgresql://user:password@host/database

must be treated as sensitive.

Database URLs must never be logged verbatim.

58. Database Configuration

Database configuration should include:

host;
port;
database;
username;
credential;
TLS requirements;
pool settings;
timeout settings.

Production security requirements must be validated.

59. Database TLS

Where production architecture requires encrypted database transport, configuration validation should reject plaintext connections.

The exact database deployment determines the precise TLS settings.

60. Configuration Serialization

Configuration objects should not automatically serialize secrets.

A generic operation such as:

config.model_dump()

must not accidentally produce a report containing credentials.

Sensitive fields should use explicit exclusion or redaction mechanisms.

61. Configuration API

Aegis Vuldris should not expose the complete internal configuration through an administrative endpoint.

An administrative configuration endpoint, if introduced, must return only explicitly approved fields.

62. Configuration Inspection

Operational diagnostics may expose safe metadata such as:

environment=production
database=configured
model_provider=ollama

but should not expose:

database_password
api_key
secret_key
63. Configuration Fingerprints

Where operational comparison is useful, the system may expose non-reversible configuration fingerprints rather than values.

Fingerprints must not be constructed in a way that allows easy recovery of low-entropy secrets.

64. Secrets in URLs

Secrets should not be placed into URLs.

Avoid:

https://example.test/api?token=SECRET

because URLs may enter:

access logs;
proxies;
browser history;
telemetry;
traces.

Prefer authorization headers or another secure mechanism appropriate to the integration.

65. Secrets in Headers

Authorization headers must be redacted from:

application logs;
traces;
metrics;
debug output;
error reports.
66. Secrets in Request Bodies

Sensitive request bodies should not be logged by default.

Model requests and target requests may contain credentials or sensitive data and therefore require explicit logging policy.

67. Secrets in Responses

Model responses, target responses, and tool outputs may accidentally contain secrets.

They must be treated as untrusted sensitive data.

Observability must follow ADR-012 and ADR-013.

68. Configuration in Evidence

Evidence collection must never automatically capture the entire process configuration.

Only the minimum configuration context required to reproduce a security result should be included.

69. Configuration in Reports

Reports should include safe configuration metadata.

Examples:

environment
test profile
model identifier
adapter type
configuration version

Reports should exclude secrets.

70. Configuration in Audit Logs

Audit logs may record:

configuration changed
configuration scope
actor
timestamp
change category

but should not record secret values.

71. Secret Change Auditing

For sensitive configuration changes, audit events should record:

actor;
scope;
timestamp;
configuration key;
operation;
result.

The value itself must not be recorded.

72. Before and After Values

Sensitive configuration should not be stored as:

before=actual-secret
after=new-secret

Instead:

key=MODEL_API_KEY
operation=ROTATE

may be recorded.

73. Audit Integrity

Audit events must use the architecture defined by ADR-013 and the authorization model defined by ADR-006.

Unauthorized users must not modify or delete security audit history.

74. Configuration Access Control

Configuration management must be protected by authentication and authorization.

Permissions should distinguish between:

viewing safe configuration;
modifying configuration;
managing credentials;
rotating credentials;
managing security policies.
75. Administrative Configuration

Administrative configuration changes are security-sensitive.

They require:

authentication;
authorization;
validation;
audit logging;
controlled application.
76. Privileged Operations

The following should generally require elevated permissions:

changing authentication settings;
changing authorization settings;
rotating application signing keys;
changing network security policy;
changing evidence retention;
changing outbound network policy;
changing secret-management settings.
77. Configuration Rollback

Configuration changes should support safe rollback where practical.

Rollback must not reintroduce known-insecure settings.

78. Configuration History

Non-secret configuration history may be retained for operational debugging.

Sensitive values must not be stored in configuration history.

79. Configuration Versioning

Configuration schemas should have versions.

Example:

configuration_schema_version=1

Schema changes should be deliberate and backward-compatible where practical.

80. Configuration Migration

When configuration schemas change, Aegis Vuldris should provide explicit migration behavior.

It should not silently reinterpret old security-sensitive settings.

81. Unknown Configuration

Unknown configuration keys should generally be rejected or clearly reported.

Silent acceptance of misspelled security settings can create unsafe behavior.

For example:

AUTHENTICATON_ENABLED=false

must not silently be ignored if the intended setting was:

AUTHENTICATION_ENABLED=false

without the operator knowing.

82. Type Validation

Configuration values supplied through environment variables are strings.

The configuration layer must convert and validate types explicitly.

Examples:

PORT -> integer
DEBUG -> boolean
TIMEOUT -> duration
MAX_REQUEST_SIZE -> integer
83. Boolean Validation

Boolean configuration should use explicit accepted representations.

Ambiguous values should be rejected.

For example:

true
false

is safer than silently accepting arbitrary strings.

84. URL Validation

URLs must be parsed and validated.

Security-sensitive URL configuration must additionally validate:

scheme;
host;
port;
allowed destinations;
credential embedding;
redirect behavior.
85. Network Configuration

Configuration must not accidentally create unrestricted outbound access.

Network policy should remain deny-by-default where appropriate.

This aligns with ADR-011 and ADR-012.

86. SSRF Protection Configuration

SSRF-related configuration must define:

allowed schemes;
allowed hosts;
private-address policy;
redirect policy;
DNS resolution policy;
maximum response size;
timeout;
request count.

Changing these controls should require appropriate authorization.

87. Filesystem Configuration

Filesystem paths supplied through configuration must be validated.

Security-sensitive path configuration should use:

absolute/normalized path rules;
allowed roots;
permission checks;
non-following of unexpected links where appropriate.
88. Command Execution Configuration

Command execution must be disabled by default.

If an explicitly authorized subsystem requires command execution, configuration must define:

allowed commands;
allowed arguments;
execution environment;
timeout;
resource limits;
filesystem access;
network access.
89. Tool Configuration

Agent tools must be explicitly enabled.

A configuration value such as:

ENABLE_SHELL_TOOL=true

must not be sufficient by itself to bypass authorization.

Tool capability must also pass the runtime security policy.

90. Dangerous Feature Flags

High-risk features should require explicit opt-in.

Examples:

shell execution;
arbitrary HTTP requests;
unrestricted filesystem access;
dynamic plugin loading;
unsafe deserialization.
91. Feature Flags

Feature flags should be classified as:

public;
internal;
security-sensitive;
experimental.

Security-sensitive feature flags require stronger controls.

92. Feature Flag Scope

Feature flags may be scoped to:

installation;
tenant;
project;
target;
test profile.

However, lower scopes must not weaken mandatory security boundaries.

93. Experimental Features

Experimental features should not silently become enabled in production.

They should require explicit configuration.

94. Debug Mode

Debug mode must be treated as sensitive.

Production should reject unsafe debug behavior.

Debug output must not expose:

secrets;
tokens;
full database URLs;
internal credentials;
unrestricted request bodies.
95. Development Debugging

Development may use more verbose logging.

However, development configuration should still practice redaction.

Unsafe logging practices in development can easily become production vulnerabilities.

96. Test Environment Isolation

Test configuration must not point at production resources unless an explicit, authorized integration test requires it.

Default tests should use isolated resources.

97. Production Credential Protection

Production credentials must never be used in ordinary unit tests.

Integration tests should use dedicated test credentials with minimum privileges.

98. Test Database

The default test database should be isolated from development and production.

Destructive test operations must not have access to production data.

99. Test Model Credentials

Tests involving external model providers should use dedicated credentials with:

minimum permissions;
spending limits where available;
restricted models;
controlled endpoints.

Local models should be preferred when practical for automated tests.

100. Mock Credentials

Unit tests should prefer fake values.

Example:

test-api-key
fake-secret
synthetic-token

These values must be unmistakably non-production credentials.

101. Secret Detection Tests

Aegis Vuldris should include tests that verify sensitive configuration does not appear in:

logs;
error responses;
API responses;
reports;
telemetry;
frontend bundles.
102. Configuration Unit Tests

Configuration tests should cover:

valid configuration;
missing required values;
invalid types;
invalid URLs;
invalid environments;
unsafe production combinations;
unknown settings;
secret redaction.
103. Configuration Property Tests

Property-based tests may verify that arbitrary malformed configuration does not result in unsafe startup behavior.

104. Configuration Fuzzing

Configuration parsers should be tested with malformed input.

Targets include:

environment variable values;
configuration files;
URLs;
durations;
sizes;
lists;
structured values.
105. Configuration Regression Tests

Security-sensitive configuration bugs should result in regression tests.

Each fixed bug should become a permanent test where practical.

106. Secret Scanning Regression

Known accidental-secret patterns should be covered by repository scanning.

The goal is prevention, not reliance on manual review.

107. Configuration Documentation

Every security-sensitive configuration option must document:

purpose;
type;
default;
allowed values;
security impact;
environment applicability;
secret status;
restart requirements.
108. Configuration Reference

A machine-readable configuration reference should be considered as the project matures.

It may include:

name
type
required
default
secret
scope
description
validation
environment
109. Configuration Schema

The application configuration should have an explicit schema.

Conceptually:

class Settings:
    app_name: str
    app_env: str
    database_url: SecretValue
    secret_key: SecretValue
    log_level: str

The actual implementation should use a mature validation/configuration library.

110. Dependency Choice

Aegis Vuldris should prefer established Python configuration tooling rather than building a custom parser.

The implementation should integrate naturally with FastAPI and the Python type system.

111. Configuration Loader

A centralized module should own:

source loading;
precedence;
parsing;
validation;
secret classification;
redaction;
immutable settings creation.
112. Dependency Injection

FastAPI dependencies may provide validated settings to request handlers.

The handler should not independently call:

os.getenv(...)

for security-sensitive configuration.

113. Direct Environment Access

Direct environment access may be allowed only in the configuration bootstrap layer.

Application services should receive configuration through explicit dependencies.

114. Configuration and Background Jobs

Workers must receive validated configuration.

Workers must not assume that API-process configuration is automatically available in every deployment model.

115. Configuration and Job Isolation

Jobs should receive only the configuration required for their execution.

A job processing a target should not automatically receive unrelated administrative credentials.

116. Configuration and Model Adapters

Model adapters should receive provider-specific configuration through explicit adapter configuration objects.

Example conceptual structure:

ModelAdapterConfig
    provider
    base_url
    model
    api_key
    timeout
    retry_policy
117. Adapter Secret Isolation

The adapter must not expose its credentials to:

test cases;
evaluators;
reports;
frontend code;
unrelated adapters.
118. Configuration and Evaluators

Evaluators should not receive secrets unless an explicit, justified integration requires them.

A security evaluator should generally receive:

model input
model output
test metadata
evaluation policy

rather than:

database credentials
provider API keys
application signing keys
119. Configuration and Attack Orchestration

Attack orchestration may require:

target configuration;
test configuration;
request budgets;
network policy.

It must not automatically inherit all application secrets.

120. Configuration and Privacy Testing

Privacy testing must be able to use synthetic sensitive data.

Configuration must define whether real sensitive data is permitted.

Secure default:

real sensitive data = disabled
121. Configuration and Evidence

Evidence settings may define:

retention;
redaction;
evidence level;
storage;
export.

Sensitive evidence controls must remain independent from general logging configuration.

122. Configuration and Reporting

Report generation may need:

report format;
evidence inclusion;
retention;
export destination.

It must never require access to unrelated secrets.

123. Configuration and Telemetry

Telemetry configuration may include:

metrics enabled;
tracing enabled;
endpoint;
sampling;
log level.

External telemetry endpoints must be treated as separate trust boundaries.

124. External Telemetry Secrets

Telemetry exporter credentials must be protected like other secrets.

They must not appear in:

traces;
logs;
metrics labels;
reports.
125. Telemetry Endpoint Validation

External telemetry destinations should be explicitly configured.

Untrusted or unexpected destinations must not be accepted merely because they are syntactically valid URLs.

126. Configuration and Audit Logging

Security-sensitive configuration changes must produce audit events.

However, the values of secrets must not be captured.

127. Configuration and Metrics

Metrics must not include secret values as labels.

Avoid:

api_request{api_key="secret"}

Metrics should use bounded, non-sensitive labels.

128. Configuration and Traces

Trace attributes must not contain secrets.

Sensitive headers and query parameters must be redacted.

129. Configuration and Logs

Structured logs should record safe metadata rather than full configuration dumps.

130. Configuration Dump Endpoint

A production configuration dump endpoint is prohibited unless every field is explicitly allowlisted and redacted.

131. Environment Dump

The application must never expose its complete environment through:

diagnostics;
API endpoints;
debug pages;
reports;
error pages.
132. Health Checks

Health endpoints should return minimal information.

They may indicate:

healthy
ready
degraded

without revealing credentials or internal configuration.

133. Readiness Failures

Readiness failures should identify the failing subsystem without exposing secret values.

Example:

database configuration invalid

rather than:

database password XYZ failed authentication
134. Liveness Checks

Liveness checks should avoid requiring privileged credentials where possible.

Liveness should not expose configuration.

135. Secret Files

If production uses mounted secret files, file permissions must be restrictive.

The application should read only the required secret.

136. Secret File Paths

Secret file paths themselves may be sensitive.

They should not be unnecessarily logged.

137. File Permissions

Secret files should be readable only by the process identity that requires them.

138. Secret File Cleanup

Temporary secret files must be removed after use where appropriate.

Applications should prefer direct secret injection when practical.

139. Temporary Files

Secrets must not be written to temporary files unnecessarily.

If temporary storage is unavoidable, access permissions and cleanup must be controlled.

140. Memory Exposure

Aegis Vuldris cannot guarantee that secrets never exist in process memory.

Therefore the architecture focuses on preventing unnecessary propagation and exposure.

141. Secret Lifetime

Secrets should remain in memory only as long as required by the component.

Long-term global copies should be avoided where practical.

142. Secret Copying

Unnecessary copying of secret values should be avoided.

Libraries and frameworks should be used carefully so secret-bearing objects are not duplicated into logs or caches.

143. Secret Caching

Caching secrets should be avoided unless necessary.

If caching is required, the cache must have:

explicit TTL;
access control;
secure storage;
invalidation strategy.
144. Secret Revocation

Aegis Vuldris should support controlled revocation of credentials.

Revocation may be external to Aegis Vuldris but must be operationally documented.

145. Emergency Secret Rotation

The architecture must support emergency rotation after:

accidental exposure;
suspected compromise;
credential theft;
unauthorized access.

The application must not require source changes to perform emergency rotation.

146. Compromise Response

If a secret is exposed:

revoke or rotate it;
assess affected systems;
remove exposed copies where practical;
inspect logs and artifacts;
investigate access;
record the incident;
add regression controls.
147. Repository History

Deleting a secret from the latest commit does not remove it from Git history.

If a real credential is committed, it must be considered compromised.

The credential must be rotated or revoked.

148. Git Protection

Repository controls should prevent accidental secret commits.

Recommended controls include:

.gitignore;
secret scanning;
pre-commit scanning;
CI scanning;
code review.
149. Example Credentials

Documentation may contain examples such as:

YOUR_API_KEY_HERE

rather than realistic credential formats that could be confused with active secrets.

150. Documentation Safety

Documentation must not encourage unsafe practices such as:

export API_KEY=real-production-key

in tracked scripts.

Examples should clearly use placeholders.

151. Shell History

Developers should avoid passing secrets directly on command lines where shell history may retain them.

Prefer environment variables or secure input mechanisms.

152. PowerShell History

Windows development workflows must consider PowerShell command history.

Commands containing real credentials should not be pasted into reusable scripts or shared terminal history.

153. Process Arguments

Secrets should not be passed as command-line arguments where practical because process arguments may be observable by other users or monitoring systems.

154. Environment Exposure

Environment variables are safer than command-line arguments for many deployment scenarios, but they are not automatically secret in every operating environment.

Host and process permissions remain important.

155. Production Host Security

Secret protection depends partly on operating-system isolation.

Aegis Vuldris should not assume that process-local secrecy protects against a fully compromised host.

156. Container Isolation

Containerization reduces deployment complexity but does not make secrets automatically safe.

Container permissions must remain restricted.

157. Privileged Containers

Production Aegis Vuldris containers should not require privileged mode unless explicitly justified.

158. Host Mounts

Sensitive host directories should not be mounted into Aegis Vuldris containers unnecessarily.

159. Secret Mounts

Secret mounts should be read-only where supported.

160. Network Configuration Secrets

Network credentials must follow the same secret-handling rules.

Examples:

proxy passwords;
private registry credentials;
service tokens.
161. Registry Credentials

Container registry credentials must not be baked into Dockerfiles.

162. Dependency Credentials

Private package registry credentials must be supplied through CI/deployment secret mechanisms.

They must not be stored in:

requirements.txt
pyproject.toml
Dockerfile
source code
163. Git Credentials

Git credentials must not be stored in project configuration.

CI/CD should use platform-managed credentials.

164. SSH Keys

Private SSH keys must never be committed.

Development automation should use secure host configuration.

165. Certificates

Private TLS keys must be treated as secrets.

Public certificates may be public, but private keys must not be exposed.

166. Signing Credentials

Code-signing credentials must be managed outside source code.

167. Release Credentials

Release credentials must be provided by CI/CD secret management.

168. Configuration and Supply Chain

Third-party libraries must not receive application secrets merely because they are dependencies.

Only the components requiring credentials should receive them.

169. Plugin Configuration

Plugins are untrusted extensions unless explicitly trusted.

A plugin should not automatically receive all configuration.

170. Plugin Capability Model

Plugins should receive capability-scoped configuration.

For example:

plugin -> specific API credential

rather than:

plugin -> entire application environment
171. Dynamic Imports

Configuration must not directly enable arbitrary Python imports from untrusted input.

172. Unsafe Deserialization

Configuration parsing must avoid unsafe deserialization formats where possible.

Untrusted configuration must not be loaded through mechanisms capable of arbitrary code execution.

173. YAML Configuration

If YAML configuration is supported, safe parsing must be mandatory.

Unsafe YAML loaders must not be used on untrusted input.

174. Pickle

Pickle must not be used as a configuration transport for untrusted data.

175. JSON Configuration

JSON is preferred for interoperable structured configuration where structured files are required.

Schema validation remains mandatory.

176. TOML Configuration

TOML may be used for developer-friendly static configuration.

Secret handling rules still apply.

177. Configuration Files

Configuration files must have:

clear ownership;
clear precedence;
explicit schema;
controlled permissions;
documented security classification.
178. Production Configuration Files

Production configuration files containing secrets should be avoided when environment or secret injection is practical.

179. Configuration Encryption

Aegis Vuldris does not require encrypted configuration files for the MVP.

Encrypted configuration may be supported later when a justified deployment requirement exists.

Encryption does not remove the need for access control and key management.

180. Secret Manager Integration

Aegis Vuldris should keep the configuration abstraction flexible enough to integrate with open-source secret managers later.

Potential implementations may include:

Vault-compatible systems;
container secrets;
Kubernetes secrets;
operating-system secret stores.

The core application must not depend on a proprietary provider.

181. Secret Manager Boundary

External secret managers are separate trust boundaries.

Credentials used to access a secret manager must themselves be protected.

182. Secret Manager Failure

If required secrets cannot be retrieved, security-sensitive services should fail closed.

They must not silently substitute insecure defaults.

183. Optional Secret Sources

Optional integrations may remain disabled when credentials are unavailable.

The application should distinguish:

optional capability unavailable

from:

required security configuration missing
184. Required vs Optional Configuration

Every configuration field should be classified as:

required;
optional;
conditional.

Conditional configuration becomes required when a feature is enabled.

185. Conditional Validation

Example:

TELEMETRY_ENABLED=true

may require:

TELEMETRY_ENDPOINT

If the dependency is missing, startup or feature activation must fail clearly.

186. Feature Dependency Graph

Configuration dependencies should be explicit.

Conceptually:

Feature A
  |
  +--> requires B
  |
  +--> requires secret C

This prevents partial feature activation.

187. Configuration Errors

Configuration errors should have stable categories.

Examples:

CONFIG_MISSING
CONFIG_INVALID
CONFIG_UNSUPPORTED
CONFIG_CONFLICT
CONFIG_SECRET_UNAVAILABLE
CONFIG_SECURITY_VIOLATION
188. Error Messages

Errors should be useful without exposing sensitive values.

They should identify:

configuration key;
error category;
remediation guidance.

Sensitive values must remain redacted.

189. Configuration Metrics

Metrics may count:

configuration_validation_failures

but should not contain configuration values.

190. Configuration Audit Events

Recommended events include:

configuration.created
configuration.updated
configuration.deleted
configuration.validation_failed
secret.rotated
secret.revoked
191. Audit Event Fields

Safe fields include:

event_id
timestamp
actor_id
scope
configuration_key
operation
result
request_id

Secret values must be excluded.

192. Configuration Security Events

Suspicious configuration activity may produce security events.

Examples:

repeated invalid configuration changes;
unauthorized secret access;
attempts to weaken security floors;
attempts to expose protected configuration.
193. Rate Limiting Configuration Changes

Administrative configuration endpoints should be protected against abuse.

Rate limiting may be applied where appropriate.

194. Reauthentication

Highly sensitive operations may require reauthentication.

Examples:

signing key rotation;
authentication policy changes;
administrator credential changes.
195. Approval Workflows

Future deployments may require multi-person approval for highly sensitive configuration changes.

This is outside the MVP but compatible with the architecture.

196. Configuration Export

Exporting configuration must default to safe metadata only.

Full secret export is prohibited through normal application APIs.

197. Configuration Backup

Backups may contain configuration data.

Backup systems must therefore treat configuration backups as potentially sensitive.

198. Backup Encryption

Production backups containing sensitive configuration should use appropriate encryption and access controls.

199. Backup Restoration

Restoration procedures must preserve secret isolation.

Restoring a database must not unexpectedly restore obsolete production credentials into a new environment.

200. Environment Promotion

Configuration promotion from development to staging to production should not copy secrets blindly.

Only configuration structure and approved values should be promoted.

Production secrets must be independently injected.

201. Infrastructure as Code

Infrastructure configuration may be stored in source control when safe.

Secret values must be supplied separately.

202. Terraform and Similar Tools

If infrastructure-as-code tools are introduced, state files must be treated as potentially sensitive.

Aegis Vuldris deployment documentation must warn operators accordingly.

203. Kubernetes

If Kubernetes deployment is introduced, Kubernetes Secret objects may be used, but RBAC and cluster security remain mandatory.

Secrets should not be placed into ConfigMaps.

204. Helm

Helm values files must not contain production secrets in tracked repositories.

205. Docker Compose Development

Local Compose configuration should support:

.env

for developer values while keeping secrets outside version control.

206. Compose Production

Production Compose deployment should use externally supplied secrets or environment injection rather than repository-managed plaintext credentials.

207. Environment Naming

Environment identifiers must be explicit.

Recommended values:

development
test
staging
production

Unknown values should be rejected.

208. Development Security Exceptions

Development-only security exceptions must be explicit.

Example:

ALLOW_INSECURE_DEV_MODE=true

should never silently apply in production.

209. Production Security Enforcement

Production mode should reject development-only bypass settings.

210. Test Security Enforcement

Tests should verify that:

development-only bypass

cannot activate under:

production
211. Configuration Drift

Operational environments may drift from documented configuration.

Aegis Vuldris should expose safe configuration fingerprints or schema versions to assist detection.

212. Configuration Fingerprint Design

Fingerprints must be:

non-secret;
deterministic where useful;
resistant to trivial secret recovery;
safe to expose to authorized operators.
213. Configuration Compatibility

Application upgrades should verify configuration compatibility before migration.

214. Deployment Gate

Production deployment should fail if required configuration validation fails.

215. Health Gate

Deployment automation should verify readiness after configuration injection.

216. Secret Availability Check

A deployment should verify that required secrets are available without printing their values.

217. Secret Presence vs Value

Safe diagnostic output may say:

MODEL_API_KEY configured: yes

but not:

MODEL_API_KEY: sk-actual-secret
218. Configuration Logging

Startup logs may report safe configuration metadata.

Example:

environment=production
log_level=INFO
model_provider=ollama

They must not dump the configuration object.

219. Startup Secret Redaction

Startup validation errors must use redacted representations.

220. Configuration Snapshot

If configuration snapshots are required for debugging, they must be explicitly redacted and access-controlled.

221. Snapshot Storage

Configuration snapshots must not be stored in:

public object storage;
Git repositories;
frontend assets;
ordinary logs.
222. Configuration Snapshot Retention

Snapshots should have explicit retention and deletion policies.

223. Configuration in Crash Reports

Crash reporting must redact configuration before transmission.

224. Configuration in Support Bundles

Support bundles must contain only safe diagnostic information.

They must not automatically include .env.

225. Configuration in Bug Reports

Automated bug-report tooling must avoid attaching environment dumps.

226. Configuration in Screenshots

Documentation and issue reports should avoid screenshots containing credentials.

227. Security Review

Changes to configuration handling should receive security review when they affect:

secrets;
authentication;
authorization;
network policy;
code execution;
filesystem access;
data retention;
telemetry.
228. Code Review Requirements

Reviewers should ask:

Is this configuration sensitive?
Can it contain secrets?
Is it validated?
Is the default secure?
Can it reach the frontend?
Can it reach logs?
Can it reach telemetry?
Can it reach evidence?
Can lower scopes weaken it?
Is authorization required?
229. Threat Model Alignment

Configuration threats identified in the threat model include:

credential exposure;
configuration tampering;
privilege escalation;
unsafe defaults;
secret leakage;
SSRF policy bypass;
command execution enablement;
plugin abuse;
insecure deployment.

The implementation must maintain controls against these threats.

230. Configuration Threat: Secret Exposure

Threat:

Secret -> log -> external system

Control:

centralized redaction
231. Configuration Threat: Frontend Exposure

Threat:

server secret -> frontend build

Control:

strict public/server configuration boundary
232. Configuration Threat: Scope Escalation

Threat:

project configuration -> system security override

Control:

security floor
233. Configuration Threat: Unsafe Default

Threat:

missing configuration -> insecure behavior

Control:

secure default or fail closed
234. Configuration Threat: Configuration Injection

Threat:

untrusted input -> configuration parser

Control:

strict schema validation
235. Configuration Threat: Secret Persistence

Threat:

secret -> database/log/report/cache

Control:

explicit secret handling and minimization
236. Configuration Threat: Credential Reuse

Threat:

target A credential -> target B

Control:

credential scope isolation
237. Configuration Threat: Production Debugging

Threat:

debug=true -> secret disclosure

Control:

production validation rejects unsafe debug settings
238. Configuration Threat: CI Leakage

Threat:

secret -> CI output

Control:

secret masking and no environment dumps
239. Configuration Threat: Container Leakage

Threat:

secret -> Docker image layer

Control:

secret injection at runtime
240. Configuration Threat: Configuration Tampering

Threat:

unauthorized actor -> security setting

Control:

authentication + authorization + audit logging
241. Configuration Threat: Secret Rotation Failure

Threat:

compromised credential remains active

Control:

rotation and revocation procedures
242. Configuration Threat: Stale Secrets

Threat:

obsolete credential -> active deployment

Control:

credential lifecycle management
243. Configuration Threat: Environment Confusion

Threat:

production secret -> test environment

Control:

environment isolation and dedicated credentials
244. Configuration Threat: Configuration Drift

Threat:

runtime state != documented state

Control:

safe configuration metadata and validation
245. Configuration Threat: Unknown Setting

Threat:

misspelled security setting -> silent fallback

Control:

strict configuration validation
246. Configuration Threat: Secret in URL

Threat:

credential -> URL -> logs

Control:

authorization headers and redaction
247. Configuration Threat: Secret in Trace

Threat:

credential -> span attribute

Control:

telemetry redaction
248. Configuration Threat: Secret in Evidence

Threat:

credential -> evidence artifact

Control:

evidence minimization and redaction
249. Configuration Threat: Secret in Report

Threat:

credential -> generated report

Control:

report sanitization
250. Configuration Threat: Secret in Backup

Threat:

configuration backup -> unauthorized access

Control:

backup encryption and access control
251. Configuration Threat: Secret in Error

Threat:

exception -> API response

Control:

safe error handling
252. Configuration Threat: Plugin Access

Threat:

plugin -> entire environment

Control:

capability-scoped configuration
253. Configuration Threat: Tool Access

Threat:

tool -> application secrets

Control:

explicit tool configuration and capability isolation
254. Configuration Threat: Model Exposure

Threat:

model prompt -> application secret

Control:

configuration never automatically enters prompts
255. Configuration Threat: SSRF Policy Override

Threat:

project config -> unrestricted network

Control:

system security floor
256. Configuration Threat: Command Execution

Threat:

config -> shell enabled

Control:

dangerous capabilities disabled by default and separately authorized
257. Configuration Threat: Filesystem Access

Threat:

config -> arbitrary filesystem root

Control:

allowed-root validation
258. Configuration Threat: Dynamic Code

Threat:

configuration -> arbitrary import/evaluation

Control:

configuration is data, not executable code
259. Configuration Threat: Unsafe Deserialization

Threat:

untrusted config -> code execution

Control:

safe serialization formats and parsers
260. Configuration Threat: External Secret Store

Threat:

secret manager credential compromise

Control:

least privilege and separate trust boundary
261. Configuration Threat: Supply Chain

Threat:

dependency -> environment secret access

Control:

minimal configuration exposure
262. Configuration Threat: Memory Scraping

Threat:

host compromise -> process memory

Control:

host security and secret minimization
263. Configuration Threat: Temporary File

Threat:

secret -> temp file

Control:

avoid unnecessary temporary secret storage
264. Configuration Threat: Shell History

Threat:

secret -> command history

Control:

secure developer procedures
265. Configuration Threat: Configuration Export

Threat:

admin -> full config export

Control:

allowlisted safe export
266. Configuration Threat: Configuration Backup

Threat:

backup -> secret recovery

Control:

backup access control and encryption
267. Configuration Threat: Misconfigured CORS

Threat:

production -> wildcard browser access

Control:

production validation
268. Configuration Threat: Weak Cookies

Threat:

production -> insecure cookie configuration

Control:

security validation
269. Configuration Threat: Weak Cryptography

Threat:

invalid signing configuration

Control:

startup validation
270. Configuration Threat: Disabled Authentication

Threat:

production -> authentication bypass

Control:

production configuration enforcement
271. Configuration Threat: Overly Broad Permissions

Threat:

component -> unrelated secret

Control:

least privilege
272. Configuration Threat: Stale Environment Variables

Threat:

obsolete variable -> unexpected behavior

Control:

strict unknown-variable handling and documentation
273. Configuration Threat: Environment Variable Injection

Threat:

untrusted deployment input -> security setting

Control:

trusted deployment boundary + schema validation
274. Configuration Threat: Configuration Override Abuse

Threat:

runtime override -> security bypass

Control:

authorization + immutable security floor
275. Configuration Threat: Feature Flag Abuse

Threat:

flag -> dangerous capability

Control:

security-sensitive flag classification
276. Configuration Threat: Experimental Feature Leakage

Threat:

experimental -> production enabled

Control:

explicit production opt-in
277. Configuration Threat: Logging Configuration

Threat:

LOG_LEVEL=DEBUG -> sensitive data

Control:

redaction remains mandatory regardless of log level
278. Configuration Threat: Telemetry Sampling

Threat:

high sampling -> excessive sensitive data

Control:

privacy-aware telemetry design
279. Configuration Threat: External Export

Threat:

configuration metadata -> external service

Control:

explicit outbound policy
280. Configuration Threat: Configuration API

Threat:

API -> secret disclosure

Control:

allowlisted safe configuration representation
281. Configuration Threat: Admin Privilege

Threat:

low-privilege user -> configuration modification

Control:

resource and action authorization
282. Configuration Threat: Tenant Escape

Threat:

tenant A config -> tenant B

Control:

tenant-scoped authorization and storage
283. Configuration Threat: Project Escape

Threat:

project A secret -> project B

Control:

resource-level isolation
284. Configuration Threat: Target Escape

Threat:

target A credential -> target B

Control:

target-scoped credential binding
285. Configuration Threat: Job Escape

Threat:

job -> unrelated secrets

Control:

job-scoped configuration
286. Configuration Threat: Worker Escape

Threat:

worker -> full application secrets

Control:

worker capability configuration
287. Configuration Threat: Report Worker

Threat:

report worker -> provider credentials

Control:

minimum required configuration
288. Configuration Threat: Evaluator Worker

Threat:

evaluator -> database credentials

Control:

isolated evaluator configuration
289. Configuration Threat: Attack Worker

Threat:

attack worker -> admin secrets

Control:

attack-scoped configuration
290. Configuration Threat: External Target

Threat:

credential -> unauthorized target

Control:

target authorization and allowlisting
291. Configuration Threat: Redirect Credential Leakage

Threat:

Authorization header -> redirected host

Control:

safe redirect policy and credential scoping
292. Configuration Threat: DNS Rebinding

Threat:

allowed hostname -> private address

Control:

DNS-aware network policy
293. Configuration Threat: Proxy Abuse

Threat:

proxy configuration -> unrestricted network

Control:

explicit proxy allowlist and security validation
294. Configuration Threat: Certificate Validation

Threat:

verify_tls=false -> MITM

Control:

production configuration rejects unsafe TLS settings
295. TLS Configuration

TLS configuration should explicitly define:

certificate verification;
trusted authorities;
minimum protocol requirements;
hostname verification.
296. Insecure TLS

Disabling certificate verification should be considered a development-only exception.

Production must reject insecure TLS configuration unless an explicitly documented security exception exists.

297. HTTP Configuration

Plain HTTP should not be used for sensitive production communication unless the deployment architecture explicitly provides equivalent protected transport.

298. Proxy Credentials

Proxy credentials are secrets and must follow the same redaction and rotation rules.

299. External API Configuration

External APIs should have:

explicit endpoint;
authentication method;
timeout;
retry policy;
rate limit;
data-sharing policy.
300. Data-Sharing Configuration

Aegis Vuldris should make external data transfer explicit.

A configuration option should not silently permit sensitive assessment data to leave the deployment.

301. External Evaluator Configuration

External evaluators must be treated as separate trust boundaries.

Configuration should explicitly identify:

external evaluation enabled

and the destination.

302. Local-First Evaluation

Where practical, Aegis Vuldris should prefer local/open-source evaluators for privacy-sensitive workflows.

303. External Model Credentials

Credentials for external evaluators must be isolated from target model credentials.

304. Data Minimization

Only necessary data should be sent to external services.

Configuration must not disable privacy minimization globally without explicit authorization.

305. Configuration and Compliance

Configuration metadata may support compliance evidence.

However, configuration state must not automatically be interpreted as proof of compliance.

306. Legal Classification

Aegis Vuldris configuration does not automatically determine legal or regulatory compliance.

Compliance mappings should remain explicit.

307. Configuration and Risk

Configuration changes may affect risk scoring.

For example:

external telemetry enabled

may change privacy exposure.

Risk engines should consume validated security signals rather than raw secrets.

308. Configuration and Findings

Configuration-related security weaknesses may generate findings.

Examples:

insecure TLS;
debug enabled in production;
unrestricted network;
missing authentication configuration.
309. Configuration Finding Evidence

Findings should contain safe evidence.

Secret values must be redacted.

310. Configuration Finding Reproduction

Reproduction instructions must use placeholders rather than actual credentials.

311. Configuration Finding Remediation

Recommendations should identify the configuration control without exposing secret values.

312. Configuration Regression

Fixed configuration vulnerabilities should become regression tests.

313. Secure Configuration Baseline

Aegis Vuldris should maintain a secure baseline configuration for supported deployment modes.

314. Baseline Validation

Baseline validation should verify:

authentication;
authorization;
TLS;
network restrictions;
logging redaction;
secret handling;
debug state;
resource limits.
315. Configuration Profiles

Aegis Vuldris may define profiles such as:

development
secure-development
test
staging
production

Profiles must be explicit.

316. Production Profile

The production profile should enable the strongest practical security defaults.

317. Test Profile

The test profile should maximize determinism while preserving security boundaries.

318. Development Profile

The development profile may optimize usability but must not teach production-incompatible security patterns.

319. Staging Profile

Staging should approximate production security behavior.

320. Configuration Profiles and Secrets

Profiles should not contain real secret values.

They define behavior and validation requirements.

321. Configuration Templates

Templates should contain placeholders only.

322. Template Validation

CI should validate that templates do not contain obvious real credentials.

323. Example Secret Detection

A documented example should use values such as:

CHANGE_ME
YOUR_SECRET_HERE
example-only
324. Secret Entropy

High-entropy strings in tracked files should be considered potential credentials during secret scanning.

325. False Positive Handling

Secret scanning exceptions should be:

narrow;
documented;
reviewed;
non-global.
326. Secret Scanning Scope

Scanning should cover:

source;
documentation;
configuration;
Docker files;
CI workflows;
test fixtures;
scripts.
327. Generated Files

Generated artifacts must also be considered for secret leakage.

328. Build Artifacts

Release artifacts must not contain secrets.

329. Frontend Build Verification

CI should inspect frontend bundles where practical to ensure known server-secret names are not included.

330. Container Verification

Container scanning should verify that common secret files and credentials are not present in images.

331. SBOM

Software bills of materials should not include secret values.

332. Dependency Configuration

Dependency installation should not expose private credentials in generated logs.

333. Package Manager Credentials

Private package manager tokens must be supplied securely and removed from generated configuration where possible.

334. Build Cache

Build caches must not persist secrets unnecessarily.

335. CI Workspace Cleanup

CI systems should clean secret-bearing temporary files.

336. Release Verification

Before release, Aegis Vuldris should verify:

no known secrets;
no .env;
no private keys;
no credential-bearing logs;
no secret-bearing frontend bundles;
no secret-bearing container layers.
337. Configuration Security Tests

The security test suite should include:

secret leakage tests;
production validation tests;
environment isolation tests;
frontend exposure tests;
configuration injection tests;
redaction tests.
338. Secret Redaction Test

A test should confirm that a known synthetic secret does not appear in logs.

Conceptual test:

secret = SYNTHETIC_SECRET
execute operation
inspect logs
assert secret not present
339. Error Redaction Test

A test should confirm that configuration errors do not expose secret values.

340. Report Redaction Test

A test should confirm that generated reports exclude secret configuration.

341. Telemetry Redaction Test

A test should confirm that telemetry excludes credentials.

342. Frontend Exposure Test

A test should confirm that server-only configuration names are absent from frontend output.

343. Environment Isolation Test

A test should confirm that test configuration cannot accidentally connect to production.

344. Production Debug Test

A test should confirm that production configuration rejects unsafe debug behavior.

345. Production Auth Test

A test should confirm that production configuration cannot silently disable authentication.

346. TLS Test

A test should confirm that insecure TLS configuration is rejected where production policy requires TLS validation.

347. Network Policy Test

A test should confirm that configuration cannot bypass mandatory outbound network restrictions.

348. Security Floor Test

A test should confirm that project-level configuration cannot weaken mandatory system-level security controls.

349. Secret Scope Test

A test should confirm that target A credentials cannot be accessed by target B operations.

350. Tenant Isolation Test

A test should confirm that tenant A cannot read tenant B configuration.

351. Project Isolation Test

A test should confirm that project A cannot read project B secrets.

352. Worker Isolation Test

A test should confirm that a worker receives only authorized configuration.

353. Adapter Isolation Test

A test should confirm that one model adapter cannot access another adapter's credential.

354. Configuration Parser Fuzz Test

Malformed configuration input should never produce arbitrary code execution.

355. Configuration Schema Test

Unknown and invalid values should be rejected consistently.

356. Configuration Precedence Test

Precedence rules should be deterministic and documented.

357. Secret Rotation Test

A test or controlled integration procedure should verify secret rotation behavior.

358. Secret Revocation Test

A test should verify that revoked credentials are not reused after rotation.

359. Backup Safety Test

Backups should be tested for correct access controls where practical.

360. Configuration Security Gate

CI should fail when:

known secrets are detected;
configuration schema validation fails;
production security checks fail;
secret redaction tests fail.
361. Local Development Workflow

Recommended workflow:

copy .env.example -> .env
fill local values
run validation
start application
run tests
362. Development Validation Command

The project should eventually provide a command similar to:

aegis config validate

to validate local configuration without starting the full application.

363. Production Validation Command

Deployment systems should support a non-secret diagnostic such as:

aegis config validate --environment production

without printing secret values.

364. Configuration Health Command

A future command may report:

configuration valid
database configured
model provider configured
authentication configured
telemetry configured

without revealing values.

365. Configuration Documentation Generation

A future tool may generate configuration documentation from the schema.

366. Configuration Schema as Source of Truth

Where practical, the schema should become the source of truth for:

validation;
documentation;
examples;
diagnostics.
367. Documentation Drift

Configuration documentation should be tested or generated to reduce drift.

368. Configuration Review

New configuration keys should be reviewed before introduction.

369. New Secret Review

Any new secret should document:

why it is required;
who accesses it;
where it is stored;
how it is rotated;
how it is redacted;
what happens if unavailable.
370. New Security Setting Review

Security-sensitive configuration should document:

threat addressed;
secure default;
allowed override;
authorization requirements;
audit event.
371. Configuration Naming Convention

Names should be:

descriptive;
stable;
consistent;
unambiguous.

Avoid unclear names such as:

KEY
MODE
TOKEN
SECRET

when a more precise name is available.

Prefer:

MODEL_API_KEY
AUTH_SESSION_SECRET
DATABASE_PASSWORD
372. Prefixing

Subsystem prefixes may be used:

AUTH_
DATABASE_
MODEL_
TELEMETRY_
SECURITY_
REPORT_
JOB_

This improves discoverability.

373. Nested Configuration

Internally, configuration may be represented as structured objects.

Example:

DatabaseSettings
AuthSettings
ModelSettings
TelemetrySettings
SecuritySettings
374. Configuration Dependency Injection

Services should receive the narrow configuration object they need.

Avoid passing the entire application settings object everywhere.

375. Configuration Coupling

Reducing configuration coupling improves:

security;
testing;
maintainability;
portability.
376. Secret Dependency Injection

Secrets should be injected only into the component that needs them.

377. Secret Access Audit

Sensitive secret access may be auditable at the application level when justified.

The system should avoid creating noisy logs containing secret metadata.

378. Secret Usage Metadata

Safe metadata may include:

credential_id
scope
adapter_id
target_id

but not the secret itself.

379. Credential Identifiers

Credentials should have non-secret identifiers where multiple credentials exist.

380. Credential Lifecycle

Credential states may include:

active
rotating
revoked
expired
disabled
381. Expiration

Where providers support expiration, Aegis Vuldris should record safe expiration metadata.

382. Expired Credentials

Expired credentials should fail clearly without exposing their value.

383. Disabled Credentials

Disabled credentials should not be selected for new operations.

384. Credential Selection

Credential selection must respect:

scope;
authorization;
target;
provider;
environment;
status.
385. Credential Fallback

Automatic fallback from one credential to another must be controlled.

It must not accidentally cross tenant/project boundaries.

386. Credential Failover

Failover should not expose credentials or send them to unauthorized destinations.

387. Provider Configuration

Provider configuration should separate:

provider identity
endpoint
model
credential
policy
388. Endpoint Allowlisting

External provider endpoints may require allowlisting.

389. Custom Model Endpoints

Custom endpoints are untrusted integration points.

They require:

explicit authorization;
network policy;
TLS validation;
credential scoping.
390. Model Endpoint Credentials

Credentials must only be sent to the configured authorized endpoint.

391. Redirect Handling

Credentials must not automatically follow redirects to unrelated hosts.

392. DNS Resolution

Security-sensitive outbound connections should resolve and validate destinations according to the network security architecture.

393. Configuration and DNS

Hostname configuration must not be assumed safe solely because it is syntactically valid.

394. Configuration and Ports

Port values should be validated against safe ranges.

395. Configuration and Timeouts

Timeouts should have bounded ranges.

Zero or extremely large timeouts should be rejected where unsafe.

396. Configuration and Retries

Retries should be bounded.

Unbounded retries can cause:

resource exhaustion;
credential reuse;
external service abuse.
397. Configuration and Concurrency

Concurrency limits should have secure upper bounds.

398. Configuration and Resource Budgets

Configuration may define:

maximum requests;
maximum response bytes;
maximum tokens;
maximum execution duration;
maximum tool calls.

These limits must remain bounded.

399. Configuration and Rate Limits

Rate-limit configuration must not be arbitrarily disabled by lower scopes.

400. Configuration and Cancellation

Long-running jobs should remain cancellable regardless of configuration.

401. Configuration and Job Timeouts

Jobs must enforce bounded execution time.

402. Configuration and Queue Settings

Queue configuration should not allow unlimited backlog growth.

403. Configuration and Worker Count

Worker count should have sane operational bounds.

404. Configuration and Database Pool

Database pool configuration should be bounded to prevent resource exhaustion.

405. Configuration and Request Size

Maximum request size should be explicitly configured and bounded.

406. Configuration and Upload Size

Maximum upload size must be enforced independently of client claims.

407. Configuration and Evidence Size

Evidence limits should prevent unbounded storage.

408. Configuration and Report Size

Report generation must have bounded resource use.

409. Configuration and Model Response Size

Model responses should have configured limits.

410. Configuration and Prompt Size

Test prompts should have bounded size.

411. Configuration and Attack Budgets

Attack orchestration budgets must remain bounded.

412. Configuration and Multi-Turn Tests

Maximum turn count must be enforced independently of user-supplied plans.

413. Configuration and Recursive Plans

Recursion depth must be bounded.

414. Configuration and Loops

Attack/test loops must have maximum iterations.

415. Configuration and Branching

Branch fan-out must be bounded.

416. Configuration and External Calls

Maximum external network requests must be bounded.

417. Configuration and Tool Calls

Maximum tool calls must be bounded.

418. Configuration and Memory

Memory retrieval limits must be bounded.

419. Configuration and RAG

RAG configuration must enforce:

collection scope;
retrieval limits;
document size;
source permissions.
420. Configuration and Vector Stores

Vector store credentials must be scoped.

421. Configuration and Search

Search credentials must not be exposed to model outputs.

422. Configuration and Agent Memory

Agent memory configuration must respect tenant/project isolation.

423. Configuration and Session Memory

Session memory must not cross authorization boundaries.

424. Configuration and Retention

Retention settings must have minimum and maximum allowed values.

425. Configuration and Deletion

Deletion policies must not be disabled by unauthorized project configuration.

426. Configuration and Privacy

Privacy-protective settings should be security floors where appropriate.

427. Configuration and Data Classification

Data classification configuration must be explicit.

428. Configuration and Redaction Policy

Redaction settings should not permit lower scopes to disable mandatory secret redaction.

429. Configuration and Evidence Tiers

Evidence levels may be configurable but secret exclusion remains mandatory.

430. Configuration and Report Export

Export destinations must be explicitly configured and authorized.

431. Configuration and External Storage

Object storage credentials must be isolated from database credentials.

432. Configuration and Object Storage

Storage endpoints must have network and authorization controls.

433. Configuration and Encryption at Rest

Where storage encryption is configurable, disabling required encryption must be rejected in production.

434. Configuration and Backups

Backup destination credentials must be separate from application credentials where practical.

435. Configuration and Recovery

Recovery configuration should be tested periodically.

436. Configuration and Disaster Recovery

Disaster recovery documentation must define secret restoration procedures.

437. Configuration and Key Recovery

Cryptographic key recovery must use controlled procedures.

438. Configuration and Emergency Mode

Emergency operational modes must not silently disable security controls.

439. Break-Glass Configuration

Future break-glass mechanisms should require:

explicit authorization;
strong audit;
limited duration;
automatic expiration.
440. Configuration and Maintenance Mode

Maintenance mode must not become an authentication bypass.

441. Configuration and Read-Only Mode

Read-only mode should preserve authentication and authorization.

442. Configuration and Database Migrations

Migration tools must receive only required database credentials.

443. Migration Configuration

Database migration configuration should be separated from application runtime configuration where practical.

444. Migration Secrets

Migration credentials must not appear in migration output.

445. Configuration and CLI Tools

CLI tools should use the same configuration validation rules.

446. CLI Secret Input

CLI tools should prefer secure input methods over command-line plaintext.

447. CLI Output

CLI output must redact secrets.

448. Configuration and Scripts

Scripts must not hard-code credentials.

449. PowerShell Scripts

PowerShell scripts should accept configuration through environment or secure parameters rather than embedded secrets.

450. Bash Scripts

Shell scripts should avoid writing secrets into temporary files.

451. Configuration and Makefiles

Makefiles and task runners must not contain production credentials.

452. Configuration and Documentation Examples

Examples should use fake credentials.

453. Configuration and Issue Templates

Issue templates should warn users not to paste secrets.

454. Configuration and Support

Support procedures must instruct operators to redact credentials before sharing diagnostics.

455. Configuration and Incident Response

Incident response procedures must include credential rotation.

456. Configuration and Security Disclosure

Security reports must never request users to submit live credentials.

457. Configuration and Bug Reproduction

Bug reports should use synthetic credentials and sanitized configuration.

458. Configuration and Test Fixtures

Fixtures must not contain real credentials.

459. Configuration and Seed Data

Database seed data must use synthetic secrets.

460. Configuration and Demo Data

Demo deployments must use disposable credentials.

461. Configuration and Example Deployments

Example deployments must not contain credentials that work against real systems.

462. Configuration and Open Source

Aegis Vuldris source code must remain safe to publish publicly.

No private deployment credential should be required in the repository.

463. Public Repository Principle

Anyone cloning the repository must be able to inspect configuration structure without receiving secrets.

464. Reproducible Development

A developer should be able to reproduce the development environment using:

documented configuration
safe examples
local services
synthetic credentials
465. Zero-Cost Development Principle

The architecture should not require a paid secret manager for local development.

466. Open-Source Compatibility

Secret management integrations should prefer open standards and open-source-compatible mechanisms.

467. Production Independence

Production deployments may use infrastructure-specific secret management without changing application security semantics.

468. Configuration Adapter

A future abstraction may support multiple secret sources:

EnvironmentSecretSource
FileSecretSource
DockerSecretSource
VaultSecretSource
KubernetesSecretSource
469. Secret Source Interface

Conceptually:

class SecretSource:
    def get(self, name: str) -> SecretValue:
        ...

The actual interface may differ.

470. Secret Source Failure

A missing required secret must produce a controlled configuration failure.

471. Secret Source Authorization

Secret-source credentials must have minimum permissions.

472. Secret Source Auditing

Secret manager access should be auditable at the infrastructure layer where supported.

473. Secret Source Caching

Caching policy must be explicit.

474. Secret Source Rotation

Rotation must be compatible with application reload/restart behavior.

475. Configuration Reload

Dynamic reload is optional.

The MVP should prefer controlled process restart for security-sensitive changes if live reload introduces complexity.

476. Safe Restart

Production restart procedures must maintain availability where possible.

477. Configuration Reload Race Conditions

If live reload is introduced, configuration updates must be atomic.

478. Configuration Transactionality

A configuration update should not leave the application in a partially updated state.

479. Configuration Validation Before Apply

New configuration must be fully validated before becoming active.

480. Configuration Rollback

If applying a configuration fails, the previous known-good configuration should remain active where safe.

481. Configuration Audit

Every dynamic security-sensitive configuration change should have an audit record.

482. Configuration Concurrency

Concurrent configuration updates require conflict handling.

483. Optimistic Concurrency

Configuration APIs may use version numbers to prevent lost updates.

484. Configuration Version

A configuration record may contain:

version
updated_at
updated_by

without storing secret values.

485. Secret Version

Secrets may have independent version identifiers.

486. Secret Rotation Event

Rotation should generate a security audit event.

487. Secret Revocation Event

Revocation should generate a security audit event.

488. Secret Deletion

Deleting a credential should remove access without exposing the old value.

489. Secret Recovery

Recovery should be restricted to authorized operational procedures.

490. Secret Export

Normal application users must not be able to export secret values.

491. Administrative Secret Visibility

Even administrators should receive secrets only when explicitly required and authorized.

492. Secret Reveal

A future controlled reveal operation, if needed, must require:

strong authentication;
authorization;
audit;
limited scope;
no automatic logging.
493. Secret Reveal Risk

Secret reveal should be treated as a high-risk operation.

494. Secret Reveal Expiration

Temporary access should expire automatically where practical.

495. Configuration API Authorization

Configuration endpoints must enforce both action-level and resource-level authorization.

496. Object-Level Authorization

A user authorized to edit project A must not edit project B configuration.

497. Tenant-Level Authorization

Tenant administrators must not access other tenants.

498. System-Level Authorization

System administrators may have broader privileges but actions remain auditable.

499. Configuration and Sessions

Configuration changes affecting sessions may invalidate sessions where required.

500. Authentication Configuration Changes

Changing authentication settings may require reauthentication and controlled rollout.

501. Authorization Configuration Changes

Authorization changes should be treated as security-sensitive.

502. Token Configuration

Token lifetime and signing settings must have secure bounds.

503. Cookie Configuration

Cookie security settings must be validated for production.

504. CORS Configuration

CORS origins must be explicit in production.

505. Trusted Host Configuration

Trusted hosts must not default to unrestricted values in production.

506. Proxy Header Configuration

Trusted proxy configuration must be explicit.

507. Forwarded Headers

Incorrect proxy configuration can enable security bypasses.

Configuration must define trusted proxy behavior.

508. Rate Limiting Configuration

Rate limiting must have secure defaults.

509. Brute Force Controls

Authentication-related limits must not be disabled accidentally by generic configuration.

510. Password Policy Configuration

Password security settings should have secure minimums.

511. Session Configuration

Session lifetime must have bounded values.

512. CSRF Configuration

If CSRF protection is required by the authentication architecture, configuration must not silently disable it in production.

513. Security Headers

Security headers should have production-safe defaults.

514. Content Security Policy

CSP configuration must be explicit where deployed.

515. HSTS

HSTS should be enabled in appropriate production HTTPS deployments.

516. Error Detail Configuration

Production error responses should minimize internal details.

517. OpenAPI Configuration

API documentation endpoints may be controlled by environment and authorization.

518. Documentation Exposure

Production documentation exposure should be an explicit deployment decision.

519. Admin Endpoints

Administrative configuration endpoints must not be publicly exposed without authentication.

520. Internal Endpoints

Internal diagnostics must still enforce network and authorization boundaries.

521. Configuration and Reverse Proxies

Reverse proxy configuration must preserve security headers and trusted client identity semantics.

522. Configuration and TLS Termination

TLS termination must be explicitly understood.

The application must not incorrectly assume transport security if a proxy terminates TLS.

523. Configuration and Hostnames

Hostnames used for callbacks or integrations must be validated.

524. Configuration and Webhooks

Webhook secrets must be scoped to the webhook integration.

525. Webhook Verification

Webhook signature verification must be enabled where supported.

526. Webhook Secret Logging

Webhook credentials must never be logged.

527. Configuration and Email

If email integration is added, SMTP credentials must be treated as secrets.

528. Configuration and Storage

Object-storage credentials must be treated as secrets.

529. Configuration and Search

Search-provider credentials must be treated as secrets.

530. Configuration and Notifications

Notification integration credentials must be treated as secrets.

531. Configuration and GitHub Integration

Repository integration tokens must be scoped and secret.

532. Configuration and Issue Tracker Integration

Issue-tracker credentials must be scoped and secret.

533. Configuration and Slack Integration

Webhook URLs and bot tokens must be treated as secrets.

534. Configuration and Future Plugins

Third-party integrations must not automatically inherit global credentials.

535. Integration Credential Store

Future integrations should use a dedicated credential abstraction.

536. Credential Metadata

Safe metadata may include:

integration
credential_id
status
created_at
expires_at
537. Credential Secret Value

Actual secret material must remain protected.

538. Credential Encryption

If credentials are persisted in the database, they should be encrypted using a carefully designed key-management strategy.

Plaintext persistence should be avoided.

539. Database Credential Storage

Database persistence of provider secrets is optional and must not be assumed for the MVP.

540. Application Secret

The application signing/encryption secret must be externally supplied in production.

541. Default Secret Prohibition

The production application must not generate an insecure predictable default signing secret.

542. Secret Length

Cryptographic secret requirements should enforce appropriate minimum entropy and length.

543. Weak Secret Detection

Known weak development secrets must be rejected in production.

544. Secret Equality

Secret comparison should use appropriate constant-time mechanisms where relevant.

545. Secret Hashing

Secrets that only need verification may be stored using appropriate password/credential hashing rather than plaintext.

546. Passwords

User passwords must be handled according to ADR-006.

They are not ordinary application configuration.

547. Password Reset

Password-reset secrets are sensitive and must not be logged.

548. Session Tokens

Session tokens must be treated as secrets.

549. API Keys

Aegis Vuldris-issued API keys must be treated as secrets and shown only according to the authentication architecture.

550. Token Prefixes

If API keys use identifiable prefixes, safe prefixes may be stored for identification, but the full token must not be retained in logs.

551. Token Storage

Authentication token storage belongs to ADR-006.

This ADR governs configuration-level handling.

552. Secret Redaction Library

Aegis Vuldris should centralize secret redaction rather than relying on every logging call to remember individual fields.

553. Redaction Sources

Redaction should consider:

known secret values;
sensitive field names;
authorization headers;
cookies;
credential-bearing URLs;
private keys.
554. Redaction Limits

Redaction systems must avoid accidentally logging raw data before the sanitizer executes.

555. Structured Logging

Structured logs should use fields so sensitive fields can be systematically filtered.

556. String Interpolation

Security-sensitive values should not be directly interpolated into log messages.

Avoid:

logger.info(f"API key: {api_key}")
557. Safe Logging

Prefer:

logger.info("model provider configured", extra={"provider": provider})
558. Logging Tests

Logging tests should assert that synthetic secret values are absent.

559. Trace Tests

Tracing tests should assert that synthetic secrets are absent.

560. Metrics Tests

Metrics tests should assert that secrets are absent from labels.

561. Report Tests

Report tests should assert that secret values are absent.

562. API Tests

API tests should assert that configuration endpoints do not expose secrets.

563. Frontend Tests

Frontend tests should assert that server-only environment variables are not bundled.

564. Container Tests

Container tests should inspect images for accidental secret files.

565. CI Tests

CI should test secret scanning itself.

566. Configuration Security Gate

The release gate should block publication when secret exposure tests fail.

567. Dependency Updates

Configuration-related dependency updates must be reviewed for secret-handling behavior.

568. Security Advisories

Known vulnerabilities in configuration/secret libraries should be tracked.

569. Dependency Pinning

Production dependencies should be managed reproducibly.

570. Lock Files

Dependency lock files must not contain credentials.

571. Package URLs

Private package credentials must not appear in lock files.

572. Git URLs

Authenticated Git URLs must not be committed.

573. Build Reproducibility

Builds should be reproducible without requiring secrets in source control.

574. Configuration Determinism

Given the same valid configuration and environment, behavior should be deterministic except for explicitly dynamic systems.

575. Configuration Testing Matrix

Testing should cover:

development
test
staging
production

where practical.

576. Configuration Matrix

Tests should include:

valid
missing
invalid
unsafe
conflicting
unknown
secret-bearing

inputs.

577. Production Configuration Fixture

A sanitized production-like fixture should exist for automated tests.

It must contain no real secrets.

578. Configuration Contract

The configuration schema forms a contract between:

deployment;
application;
workers;
adapters;
security controls;
observability.
579. Contract Validation

Breaking configuration changes should be detectable before deployment.

580. Backward Compatibility

Non-security-sensitive configuration may support compatibility aliases temporarily.

Security-sensitive aliases should be handled carefully to avoid ambiguity.

581. Deprecated Configuration

Deprecated settings should produce warnings.

Warnings must not expose secret values.

582. Configuration Removal

Removed settings should fail clearly rather than silently changing behavior.

583. Migration Documentation

Configuration migrations must document security implications.

584. Configuration Changelog

Significant configuration changes should be recorded in release notes.

585. Security Changelog

Security-sensitive configuration changes should be highlighted in security release notes where appropriate.

586. Configuration Governance

Configuration changes should follow repository review practices.

587. Ownership

Every security-sensitive configuration group should have an owner.

Examples:

AuthSettings -> authentication maintainers
DatabaseSettings -> backend maintainers
ModelSettings -> model integration maintainers
SecuritySettings -> security maintainers
588. Configuration Reviewers

Changes to secret handling should require review by maintainers familiar with security boundaries.

589. Configuration Documentation Ownership

Documentation must remain synchronized with implementation.

590. Configuration Inventory

The project should maintain an inventory of configuration keys.

591. Secret Inventory

Secrets should be inventoried by purpose and scope without storing their values.

592. Secret Classification

Each secret should have:

name
purpose
owner
scope
source
rotation policy
593. Secret Rotation Schedule

Where practical, credentials should have defined rotation intervals.

594. Expiration Monitoring

Expiring credentials may produce safe alerts.

595. Secret Expiration Alert

Alerts must not contain the secret value.

596. Configuration Monitoring

Operational monitoring should detect invalid or unexpected configuration states.

597. Configuration Drift Alert

Safe configuration drift indicators may produce alerts.

598. Security Policy Drift

Changes weakening security controls should produce high-priority audit/security events.

599. Audit Correlation

Configuration changes should be correlated with:

request ID;
actor;
job ID;
deployment version.
600. Deployment Correlation

A configuration change should be distinguishable from a deployment change.

601. Configuration Provenance

Where practical, Aegis Vuldris should record safe provenance:

source=environment
source=secret-manager
source=default
source=database
602. Secret Provenance

Secret provenance may identify the source type without revealing the value.

603. Configuration Source Trust

Configuration sources have different trust levels.

Deployment-provided secrets should be treated as trusted inputs only after validation.

604. Untrusted Configuration

User-provided configuration must never be treated as trusted application configuration.

605. Project Configuration

Project users may configure allowed application behavior but cannot redefine server trust boundaries.

606. Target Configuration

Target users may define target metadata and authorized integration parameters within policy limits.

607. Test Configuration

Test definitions are data and must not directly mutate process-level security configuration.

608. Attack Configuration

Attack plans are untrusted input and must not override security configuration.

609. Report Configuration

Report settings must not allow arbitrary filesystem or network writes.

610. Export Configuration

Export settings must enforce allowlisted destinations.

611. Plugin Configuration

Plugin configuration must be isolated from system configuration.

612. Dynamic Configuration

Dynamic configuration is a privilege, not a default capability.

613. Configuration API Input Validation

All configuration API inputs must pass schema validation before authorization-sensitive operations.

614. Authorization Before Mutation

Authorization must be evaluated before changing persistent configuration.

615. Validation Before Commit

Configuration should be validated before the database transaction commits.

616. Transaction Boundary

Persistent configuration changes should use explicit transaction boundaries.

617. Configuration Consistency

Related configuration updates should be atomic when required.

618. Configuration Database Model

If configuration is stored in PostgreSQL, it should use typed fields or structured validated data rather than arbitrary unvalidated blobs for security-sensitive settings.

619. JSON Configuration in Database

JSON may be used for flexible non-security-sensitive metadata.

Security-sensitive values still require schema and access controls.

620. Database Secret Encryption

If persistent secret storage is implemented, encryption keys must be stored separately from the database.

621. Key Separation

The database containing encrypted credentials must not be sufficient by itself to decrypt those credentials.

622. Encryption Key Rotation

Persistent secret encryption should support key rotation where implemented.

623. Encrypted Secret Backup

Encrypted secrets remain sensitive even when encrypted.

Backup access controls remain mandatory.

624. Secret Decryption Boundary

Only the component requiring the secret should decrypt it.

625. Secret Decryption Audit

High-risk secret decryption operations may be audited using metadata only.

626. Secret Decryption Failure

Failures must not reveal plaintext secret material.

627. Configuration Caching

Configuration caches must be scoped and invalidated appropriately.

628. Distributed Configuration

If Aegis Vuldris runs multiple workers, configuration consistency must be maintained.

629. Worker Configuration Refresh

Workers should not continue using revoked security configuration indefinitely.

630. Credential Revocation Propagation

Revoked credentials must stop being selected across workers within an acceptable operational window.

631. Configuration Synchronization

Future distributed configuration systems must preserve transactionality and authorization.

632. Configuration Race

Concurrent secret rotation and job execution must have defined semantics.

633. Job Credential Binding

Jobs should bind credentials to the target and authorization context at execution time.

634. Authorization Recheck

Long-running jobs should recheck authorization where the architecture requires it.

635. Configuration Revocation

Revoking a project credential should prevent future jobs from using it.

636. Running Jobs

Already-running jobs should follow explicit cancellation or credential-revocation semantics.

637. Configuration and Scheduling

Scheduled jobs must use current authorized configuration rather than stale user-provided secrets.

638. Scheduled Job Secrets

Schedules must store references to credentials rather than embedding secret values where possible.

639. Job Payloads

Job payloads must not contain plaintext secrets unless strictly required and protected.

640. Queue Security

Queue systems must be treated as sensitive infrastructure.

641. Queue Encryption

Sensitive job data should use protected transport/storage.

642. Queue Logging

Queue debugging must not expose secret-bearing payloads.

643. Worker Error Reporting

Worker failures must redact configuration values.

644. Worker Metrics

Worker metrics must use safe labels.

645. Worker Traces

Worker traces must redact secret-bearing attributes.

646. Configuration and Cancellation

Cancellation must not leak secret-bearing job payloads.

647. Configuration and Retry

Retries must not accidentally send credentials to a different target after configuration changes.

648. Target Binding

Credentials should remain bound to the authorized target identity.

649. Endpoint Binding

Credential use should validate endpoint identity.

650. Provider Binding

Model credentials should be bound to the intended provider.

651. Credential Misrouting

The system should detect configuration mismatches such as:

provider=A
credential=provider-B

where detectable.

652. Configuration Compatibility

Provider-specific credentials should not be assumed compatible across providers.

653. Configuration Metadata

Safe metadata may record:

provider
model
adapter
environment
654. Model Secret Metadata

Secret metadata should not reveal the secret itself.

655. API Response Metadata

APIs may return:

configured=true

instead of credential values.

656. Configuration UI

A future frontend configuration UI should use masked secret inputs.

657. Secret Input UI

Secret fields should:

never display existing values by default;
avoid browser autofill where inappropriate;
avoid client-side logging;
submit over protected transport.
658. Secret Rotation UI

Rotation interfaces should not reveal old secret values.

659. Configuration UI Authorization

Configuration screens must respect backend authorization.

The frontend is not the security boundary.

660. Configuration UI Validation

Frontend validation improves usability but backend validation remains authoritative.

661. Configuration API Security

The backend must enforce all security-sensitive configuration rules independently of the frontend.

662. Configuration API Transport

Configuration containing secrets must use protected transport.

663. Browser Storage

Secrets must not be stored in browser local storage unless explicitly required by a security-reviewed architecture.

664. Browser Memory

Sensitive values should remain in browser memory only as long as necessary.

665. Clipboard

Secret-management interfaces should avoid automatically copying credentials to the clipboard.

666. Secret Reveal UI

If secret reveal is supported, it must be explicit and audited.

667. Configuration UI Errors

UI errors must not display secret values returned accidentally by the server.

668. API Schema

OpenAPI schemas should mark sensitive fields appropriately where supported.

669. Secret Serialization

API serializers must explicitly exclude secret fields.

670. Configuration DTOs

Internal settings models should not be directly reused as API response models.

671. Separation of Models

Use separate structures for:

runtime configuration
API configuration view
audit event
secret metadata
672. Configuration Mapping

Explicit mapping reduces accidental secret exposure.

673. Configuration and Serialization Tests

Tests should verify that serialization cannot leak secrets.

674. Configuration and Pydantic

If Pydantic-style models are used, sensitive fields should use secret-aware types where appropriate.

675. Secret Stringification

Secret objects should avoid exposing plaintext through str() and repr().

676. Secret Debugging

Debugging tools must not automatically expand secret objects.

677. Interactive Shells

Production debugging shells should be restricted.

678. Python REPL

Operational procedures should avoid copying production secrets into interactive sessions.

679. Crash Dumps

Crash dumps may contain process memory and therefore secrets.

Production crash-dump policies must account for this risk.

680. Core Dumps

Core dumps should be disabled or controlled where appropriate for secret-bearing production processes.

681. Memory Diagnostics

Memory diagnostics should be treated as privileged.

682. Container Debugging

Debugging containers must not automatically expose production secret mounts.

683. Kubernetes Exec

Production shell access should be tightly controlled.

684. Host Access

Host-level access is outside application secret guarantees and must be protected operationally.

685. Configuration and Security Boundary

Configuration itself is a trust-boundary input.

Every source must be classified.

686. Source Validation

Even trusted deployment systems can be misconfigured.

Schema validation remains mandatory.

687. Configuration Provenance

Where possible, the system should know whether a value came from:

default
environment
file
secret store
database
runtime override
688. Provenance Security

Provenance metadata must not expose secret values.

689. Configuration Change Reason

Security-sensitive changes may require a reason field.

690. Change Reason Privacy

Change reasons must not contain secrets.

691. Configuration Approval

Future approval workflows may require explicit approval metadata.

692. Configuration Review History

Review history should contain metadata, not secret values.

693. Configuration Rollout

High-risk configuration changes may be rolled out gradually where supported.

694. Feature Rollback

Security feature rollback must not disable mandatory security floors.

695. Canary Configuration

Staging/canary environments should use dedicated credentials.

696. Production Credential Separation

Production credentials must not be shared with staging.

697. Development Credential Separation

Development credentials must not grant production access.

698. Environment Access Control

Access to production secret sources should be restricted to authorized operators and services.

699. Credential Ownership

Every credential should have an owner.

700. Credential Inventory

The system should maintain non-secret credential metadata where practical.

701. Credential Expiry

Expiration should be monitored where supported.

702. Credential Rotation Automation

Future automation may rotate credentials automatically.

Any automation must preserve auditability.

703. Rotation Failure

Failed rotation must not leave the system believing that the new credential is active when it is not.

704. Rotation Transaction

Where possible, rotation should be treated as a controlled state transition.

705. Dual-Key Rotation

Cryptographic systems may temporarily support old and new keys for verification during rotation.

706. Key Identifier

Keys may use non-secret key IDs.

707. Secret Identifier

Secret IDs must not be confused with secret values.

708. Credential Metadata API

Credential APIs should return metadata only.

709. Credential Listing

Listing credentials should never reveal full secret values.

710. Credential Deletion

Deletion should require authorization and audit logging.

711. Credential Revocation

Revocation should be immediate or within a documented propagation window.

712. Credential Testing

Credential validity checks should not log credentials.

713. Credential Health

Health checks should report:

configured
valid
invalid
expired

without exposing the credential.

714. External Provider Failure

Provider authentication failures should not echo the credential.

715. Provider Error Sanitization

Third-party provider errors should be sanitized before logging or returning to users.

716. HTTP Client Logging

HTTP client debug logging must redact:

Authorization;
cookies;
API keys;
sensitive query parameters;
credential-bearing URLs.
717. HTTP Retry Logs

Retry logs must not expose request credentials.

718. HTTP Trace

HTTP tracing must use sanitized headers and bodies.

719. Database Driver Logs

Database driver logging must not expose passwords.

720. ORM Debug Logging

SQL debug output must not reveal sensitive bound parameters.

721. SQL Configuration

Database configuration must not be interpolated into SQL.

722. SQL Injection Boundary

Configuration values must never be used to construct SQL unsafely.

723. Configuration and Search Queries

Search configuration must not bypass query validation.

724. Configuration and File Paths

File paths must not be constructed from untrusted configuration without validation.

725. Configuration and Command Arguments

Command arguments must not be constructed from untrusted configuration without validation.

726. Configuration and Shell

Shell invocation must be avoided where structured APIs exist.

727. Configuration and Serialization

Configuration must not be interpreted as executable code.

728. Configuration and Templates

Template configuration must not permit arbitrary code execution.

729. Configuration and Regex

User-configurable regex values must have resource limits where necessary.

730. Configuration and ReDoS

Regex configuration must not enable catastrophic backtracking attacks.

731. Configuration and Parsing

Parsers must have size and complexity limits.

732. Configuration and Compression

Compressed configuration must have decompression limits if supported.

733. Configuration and Archives

Archive-based configuration must protect against path traversal.

734. Configuration and Symlinks

Filesystem configuration must account for symbolic-link traversal.

735. Configuration and Permissions

Configuration files must use restrictive permissions when they contain secrets.

736. Configuration and Ownership

Secret-bearing files must have appropriate ownership.

737. Configuration and Umask

Deployment documentation should recommend secure file creation permissions.

738. Configuration and Windows

Windows deployments must account for ACLs when protecting secret files.

739. Configuration and Linux

Linux deployments must account for file ownership and permissions.

740. Configuration and macOS

Local developer configuration should follow platform-appropriate secret protection.

741. Cross-Platform Configuration

The logical configuration model must remain consistent across supported operating systems.

742. Path Handling

Configuration paths must use platform-safe path handling rather than string concatenation.

743. Environment Encoding

Configuration parsing should define encoding expectations.

744. Unicode Configuration

Unexpected Unicode characters must not bypass validation.

745. Homograph Risks

Security-sensitive hostnames and identifiers should be normalized and validated.

746. Case Sensitivity

Configuration key matching must be deterministic.

747. Duplicate Keys

Duplicate configuration keys should be rejected where the format permits ambiguity.

748. Precedence Ambiguity

Multiple sources defining the same key must follow documented precedence.

749. Secret Source Conflicts

Conflicting secret sources should not silently select an unexpected credential.

750. Configuration Conflict

Conflicts involving security-sensitive settings should fail closed.

751. Configuration Audit Trail

Configuration changes should be traceable to an actor or deployment.

752. Automated Deployment Identity

Automated deployments should use identifiable service identities.

753. Service Account Scope

Deployment service accounts should have minimum required permissions.

754. CI Service Identity

CI should not receive production secrets unless required for an authorized deployment.

755. Build vs Deploy Separation

Build jobs should generally not need production runtime secrets.

756. Runtime Secret Injection

Production runtime secrets should be injected during deployment/runtime rather than build.

757. Build Artifact Reuse

The same artifact may be promoted across environments without embedding environment secrets.

758. Immutable Artifact Principle

Release artifacts should be environment-neutral with respect to secrets.

759. Environment Injection

Environment-specific values should be supplied at runtime.

760. Configuration and Version Control

Source control contains configuration schema and safe defaults, not secrets.

761. Configuration and Git Branches

Secrets must not be moved between branches through tracked files.

762. Pull Request Secrets

Reviewers must never request production credentials in pull requests.

763. Commit History Scanning

Secret scanning should consider historical commits where feasible.

764. Credential Exposure Response

Historical exposure requires credential rotation, not merely file deletion.

765. Repository Forks

Public forks must not inherit production credentials.

766. Open-Source Releases

Source archives must not contain local .env files.

767. Release Attachments

Release assets must be scanned for secrets.

768. Documentation Site

Documentation builds must not receive production secrets.

769. Static Site Builds

Documentation and frontend builds should use public configuration only.

770. Package Publishing

Published Python packages and frontend packages must not contain secrets.

771. Source Distribution

Source distributions should be scanned before publication.

772. Wheel Inspection

Python wheels should be inspected for accidental secret files.

773. NPM Bundle Inspection

Frontend bundles should be inspected for accidental server configuration.

774. Container Registry

Container images should be scanned before publication.

775. Registry Metadata

Registry credentials must remain outside image layers.

776. Image Build Secrets

Build-time secret mechanisms should be used when unavoidable and must not persist secrets into layers.

777. Dockerfile Review

Dockerfiles should be reviewed for:

ENV secrets;
ARG secrets;
copied .env;
credential-bearing URLs.
778. Docker ARG

Secrets passed as build arguments may be exposed through build metadata or layers.

They should not be used for runtime secrets.

779. Docker ENV

Production secrets should not be baked into image environment definitions.

780. Secret Mounts During Build

If build-time credentials are unavoidable, use ephemeral secret mounts where supported.

781. Configuration and Build Cache

Build caches must not persist secret-bearing intermediate files.

782. CI Artifact Upload

CI artifacts must be scanned before upload.

783. CI Logs

CI logs must be treated as potentially public to authorized repository viewers.

784. CI Debug Mode

CI debug tracing must not be enabled when it could expose secrets.

785. Deployment Logs

Deployment logs must not expose credentials.

786. Infrastructure Logs

Infrastructure systems may log configuration metadata; operators must configure secret redaction there too.

787. Cross-System Redaction

Aegis Vuldris cannot control every external log system, so it must minimize secret exposure at the source.

788. Data Minimization

The safest secret is the secret never copied into an unrelated subsystem.

789. Configuration Minimization

Components should receive only necessary settings.

790. Default Deny

Unknown configuration access should be denied.

791. Explicit Capability

Secret access should be an explicit capability.

792. Capability Audit

Security-sensitive capabilities should be auditable.

793. Configuration Context

A component may receive a context containing:

actor
tenant
project
target
environment
permissions

where relevant.

794. Context Isolation

Configuration resolution must respect that context.

795. Context Confusion

A user-controlled identifier must not be trusted to select credentials without authorization.

796. Credential Lookup

Credential lookup must authorize:

actor -> scope -> credential

before returning a secret.

797. Secret Reference

Application workflows should prefer secret references over embedding values.

798. Secret Handle

A future secret handle may represent:

credential_id

without exposing the value.

799. Late Binding

Secrets should be resolved as late as practical.

This reduces unnecessary propagation.

800. Early Validation

Required secret existence should be validated before starting dependent operations.

801. Late Secret Retrieval

Actual secret material may be retrieved immediately before use.

802. Secret Release

After use, the system should avoid unnecessary retention.

803. Error Path

Secret handling must be safe on both success and failure paths.

804. Retry Path

Retry handling must preserve credential scope.

805. Cancellation Path

Cancellation must not dump secret-bearing state.

806. Timeout Path

Timeout errors must not include secret values.

807. Exception Path

Exceptions must use sanitized messages.

808. Cleanup Path

Cleanup must not write secrets into logs.

809. Shutdown Path

Shutdown logs must not dump configuration.

810. Startup Path

Startup logs must not dump configuration.

811. Migration Path

Migration output must not expose credentials.

812. Health Path

Health endpoints must not expose credentials.

813. Metrics Path

Metrics must not expose credentials.

814. Trace Path

Traces must not expose credentials.

815. Audit Path

Audit logs must not expose credentials.

816. Evidence Path

Evidence must not expose credentials.

817. Report Path

Reports must not expose credentials.

818. Frontend Path

Frontend assets must not expose credentials.

819. CI Path

CI artifacts must not expose credentials.

820. Container Path

Images must not expose credentials.

821. Backup Path

Backups must be protected against credential exposure.

822. Support Path

Support bundles must not expose credentials.

823. Incident Path

Incident reports must avoid storing live credentials.

824. Security Boundary Invariant

No subsystem may weaken a mandatory security boundary through ordinary configuration.

825. Secret Boundary Invariant

Secrets must never cross into a subsystem that does not require them.

826. Frontend Invariant

Server-side secrets must never be delivered to the frontend.

827. Logging Invariant

Secrets must never appear in normal application logs.

828. Telemetry Invariant

Secrets must never appear in telemetry.

829. Evidence Invariant

Secrets must never be captured as default evidence.

830. Reporting Invariant

Secrets must never appear in generated reports.

831. CI Invariant

Production secrets must not be exposed to ordinary build jobs.

832. Repository Invariant

Production secrets must never be committed to source control.

833. Container Invariant

Production secrets must never be baked into container images.

834. Configuration Validation Invariant

Invalid security-sensitive configuration must fail closed.

835. Environment Invariant

Production and non-production credentials must remain isolated.

836. Scope Invariant

Project and tenant configuration must respect resource authorization.

837. Credential Invariant

Credentials must remain bound to their authorized provider/target/scope.

838. Rotation Invariant

Credential rotation must not require source-code changes.

839. Revocation Invariant

Revoked credentials must not continue to be selected for new operations.

840. Default Invariant

Security-sensitive defaults must be safe.

841. Override Invariant

Runtime overrides must not bypass mandatory security floors.

842. Parsing Invariant

Configuration parsing must never execute arbitrary code.

843. Serialization Invariant

Secret-bearing configuration must not serialize accidentally.

844. Authorization Invariant

Configuration mutation requires appropriate authorization.

845. Audit Invariant

Security-sensitive configuration changes must be auditable.

846. Error Invariant

Configuration errors must not expose secret values.

847. Network Invariant

Configuration must not silently disable mandatory network restrictions.

848. Tool Invariant

Configuration must not silently grant dangerous tool capabilities.

849. Model Invariant

Configuration secrets must never automatically become model input.

850. Privacy Invariant

Configuration handling must not create unnecessary privacy exposure.

851. Operational Invariant

Configuration failures must be observable without secret disclosure.

852. Recovery Invariant

Emergency credential rotation must be operationally possible.

853. Deployment Invariant

Production deployment must validate required security configuration before becoming ready.

854. Release Invariant

Release artifacts must be scanned for accidental secret exposure.

855. Security Review Invariant

Changes to secret handling require security-aware review.

856. Implementation Architecture

The initial implementation should contain a centralized configuration package.

Conceptual structure:

backend/
  app/
    config/
      __init__.py
      settings.py
      validation.py
      redaction.py
      sources.py

The exact module names may evolve.

857. Settings Module

The settings module should define validated application settings.

858. Source Module

The source module should define how configuration is loaded.

859. Validation Module

The validation module should enforce cross-field security rules.

860. Redaction Module

The redaction module should provide safe representations of sensitive settings.

861. Secret Module

A dedicated secret abstraction may be introduced for secret-bearing values.

862. Public Configuration Module

A separate safe representation should exist for values that may be returned to authorized clients.

863. Configuration Dependency

FastAPI endpoints should receive validated settings through dependency injection.

864. Service Configuration

Services should receive narrow configuration structures.

865. Adapter Configuration

Model adapters should receive only their provider-specific settings.

866. Worker Configuration

Workers should receive only required worker settings.

867. Security Configuration

Security controls should receive explicit security settings.

868. Observability Configuration

Telemetry should receive only telemetry settings.

869. Report Configuration

Report generation should receive only report-related settings.

870. Configuration Test Package

Tests should live alongside the application test architecture.

871. Unit Tests

Unit tests should validate individual fields and secret behavior.

872. Integration Tests

Integration tests should validate configuration interaction between subsystems.

873. Security Tests

Security tests should verify invariants.

874. End-to-End Tests

End-to-end tests should verify configuration behavior across API, worker, model adapter, and reporting flows.

875. Test Fixtures

Fixtures must use synthetic secrets.

876. Test Cleanup

Tests must clean temporary secret-bearing resources.

877. Test Isolation

Tests must not share production configuration.

878. CI Pipeline

CI should execute:

format
lint
type-check
unit tests
integration tests
security tests
secret scanning

where available.

879. Pre-Commit

Pre-commit should continue enforcing formatting and basic repository hygiene.

880. Secret Scanner Integration

A secret scanner should eventually be added to pre-commit and/or CI.

881. Dependency Scanner

Dependency scanning should identify vulnerable configuration/secret libraries.

882. Container Scanner

Container scanning should verify secret absence and known vulnerabilities.

883. SAST

Static analysis should identify suspicious secret handling patterns where practical.

884. Release Gate

Release should fail when critical configuration security tests fail.

885. Documentation Gate

Configuration documentation should be updated when public configuration contracts change.

886. Migration Gate

Breaking configuration changes require migration documentation.

887. Security Gate

Security-sensitive configuration changes require security review.

888. Operational Gate

Production configuration should pass validation before deployment.

889. Observability Gate

Configuration failures should produce safe observability signals.

890. Privacy Gate

Configuration handling must pass privacy/security tests.

891. Acceptance Criteria

This ADR is considered implemented when:

configuration is centralized;
configuration is schema-validated;
environment separation exists;
.env remains ignored;
.env.example contains placeholders only;
production secrets are externally injected;
no production secrets are hard-coded;
frontend receives only public configuration;
secrets are redacted from logs;
secrets are redacted from telemetry;
secrets are excluded from reports;
secrets are excluded from evidence by default;
production debug behavior is validated;
production authentication configuration is enforced;
security floors prevent unsafe lower-scope overrides;
model-provider credentials are isolated;
target credentials are isolated;
tenant/project configuration is authorized;
configuration changes are auditable;
configuration errors do not reveal secrets;
configuration tests exist;
secret leakage tests exist;
secret scanning is integrated;
Docker images do not contain secrets;
CI artifacts do not contain secrets;
secret rotation procedures exist;
credential revocation procedures exist;
configuration documentation exists;
production deployment validation exists;
security invariants are continuously tested.
892. MVP Implementation Order

Implementation should proceed in this order:

define settings schema;
define environment names;
implement centralized loader;
implement validation;
implement secret-aware values;
integrate .env for development;
integrate environment variables;
integrate FastAPI dependency injection;
add production validation;
add redaction;
add configuration-safe diagnostics;
add configuration tests;
add secret leakage tests;
add CI secret scanning;
add Docker secret protections;
integrate model adapter configuration;
integrate worker configuration;
integrate observability;
integrate authorization;
document deployment configuration.
893. Future Enhancements

Future versions may add:

Vault integration;
Kubernetes Secret integration;
cloud secret manager adapters;
encrypted credential storage;
automatic credential rotation;
configuration UI;
configuration approval workflows;
dynamic configuration reload;
configuration drift detection;
credential health monitoring;
configuration policy engine;
secret access analytics;
break-glass workflows.

These are compatible with this ADR.

894. Alternatives Considered
Alternative A: Hard-coded configuration

Rejected.

Reasons:

insecure;
inflexible;
impossible to operate safely across environments.
Alternative B: .env as production secret store

Rejected.

Reasons:

weak operational controls;
easy accidental disclosure;
poor rotation model.
Alternative C: Store all configuration in PostgreSQL

Rejected as the primary source.

Reasons:

bootstrap dependency;
secret exposure risk;
difficult early startup;
unnecessary coupling.

Database-backed configuration may be added selectively.

Alternative D: Proprietary cloud secret manager only

Rejected for the core architecture.

Reasons:

violates open-source/portable goals;
creates unnecessary provider lock-in;
harms local development.

Integrations remain possible.

Alternative E: Custom cryptographic secret system

Rejected.

Reasons:

unnecessary complexity;
high risk of implementation mistakes;
mature libraries already exist.
Alternative F: Arbitrary runtime environment access

Rejected.

Reasons:

configuration sprawl;
inconsistent validation;
poor testability;
increased secret exposure.
895. Consequences
Positive

This architecture provides:

predictable configuration;
stronger secret isolation;
secure defaults;
environment portability;
easier testing;
better operational debugging;
safer open-source development;
better CI/CD integration;
reduced accidental credential leakage;
clearer security boundaries.
Negative

It introduces:

configuration schema complexity;
additional validation code;
secret-management procedures;
deployment documentation requirements;
more testing;
operational discipline.

These costs are intentional.

896. Security Philosophy

Aegis Vuldris must assume that configuration is a powerful control plane.

Configuration can enable or disable major capabilities.

Therefore configuration must not be treated as harmless metadata.

The application must distinguish:

configuration as data

from:

configuration as authority

and protect the latter accordingly.

897. Final Security Principle

Aegis Vuldris must never create a security vulnerability merely because configuration is convenient.

In particular:

Aegis Vuldris must never require secrets to live in source code, and no component may receive more configuration authority or secret material than it requires.

898. Final Decision

The Aegis Vuldris configuration architecture is therefore:

                ┌───────────────────────────┐
                │ Safe Defaults / Schema    │
                └─────────────┬─────────────┘
                              │
                              v
                ┌───────────────────────────┐
                │ Environment / Config      │
                │ Sources                   │
                └─────────────┬─────────────┘
                              │
                              v
                ┌───────────────────────────┐
                │ Secret Sources             │
                │ env / files / managers    │
                └─────────────┬─────────────┘
                              │
                              v
                ┌───────────────────────────┐
                │ Central Validation        │
                └─────────────┬─────────────┘
                              │
                              v
                ┌───────────────────────────┐
                │ Immutable Runtime Config  │
                └───────┬───────┬───────────┘
                        │       │
             ┌──────────┘       └───────────┐
             v                              v
      ┌───────────────┐              ┌───────────────┐
      │ Scoped Config │              │ Scoped Secrets│
      └───────┬───────┘              └───────┬───────┘
              │                              │
              v                              v
      ┌────────────────────────────────────────────┐
      │ Application / API / Workers / Adapters     │
      └────────────────────────────────────────────┘

Security boundaries remain authoritative regardless of configuration.

Configuration cannot override authentication, authorization, tenant isolation, privacy controls, network restrictions, evidence protection, or other mandatory security controls.

899. Implementation Gate

No production implementation should begin from this ADR until:

the configuration schema is reviewed;
secret classifications are defined;
environment precedence is documented;
production validation requirements are identified;
redaction requirements are identified;
test requirements are identified;
deployment secret-injection strategy is documented.
900. Status

Accepted

This ADR establishes the architectural direction for Aegis Vuldris configuration, secrets, credentials, environment management, secure defaults, configuration validation, and secret isolation.

The implementation may evolve while preserving the security invariants defined above.
