# ADR-006: Authentication and Authorization Architecture

- **Status:** Accepted
- **Date:** 2026-09-10
- **Decision Owners:** Aegis Vuldris Engineering Team
- **Scope:** Authentication, authorization, identity, session security, API access control, resource isolation, and security-sensitive application operations

---

## 1. Context

Aegis Vuldris is designed as an AI model security testing and evaluation platform.

The platform will eventually manage security-sensitive resources and operations including:

- users and identities
- targets
- model connection configurations
- assessments
- test suites
- test executions
- jobs
- findings
- evidence
- reports
- audit records
- API credentials and other secrets
- project and organizational boundaries

Authentication and authorization therefore represent a core security boundary of the application.

Aegis Vuldris must not assume that a user who can reach an API endpoint is automatically authorized to perform the requested operation.

The system must establish:

1. who the caller is;
2. whether the caller is authenticated;
3. what the caller is allowed to access;
4. whether the requested operation is permitted;
5. which resources belong to the caller or their authorized scope;
6. which security-sensitive actions require additional controls;
7. how authorization decisions are recorded for auditing.

The architecture must also prevent a common class of security failures in AI security platforms: allowing an authenticated user to access another user's target, assessment, evidence, credentials, or reports by manipulating an identifier.

Examples include:

```text
GET /api/v1/targets/{target_id}

where the supplied target_id belongs to another user.

Other examples include:

changing another user's assessment;
viewing another user's findings;
downloading another user's evidence;
accessing credentials associated with another target;
cancelling another user's job;
modifying project membership without permission;
accessing administrative functions through direct API requests;
bypassing frontend restrictions by calling the backend directly.

The backend must therefore remain the authoritative security boundary.

Frontend visibility controls are useful for usability but must never be treated as authorization.

2. Decision

Aegis Vuldris will implement authentication and authorization as explicit backend security layers.

The architecture will use:

authenticated identities;
explicit authorization checks;
resource ownership and/or project-scoped access control;
least-privilege permissions;
backend-enforced authorization;
secure credential and session handling;
audit logging for security-sensitive operations;
deny-by-default behavior for protected resources.

The initial architecture will be designed so that authentication and authorization mechanisms can evolve without coupling business logic directly to a specific identity provider.

The application will separate:

Authentication
        ↓
Identity
        ↓
Authorization
        ↓
Resource Access
        ↓
Business Operation

These concerns must remain conceptually distinct.

3. Authentication
3.1 Authentication Responsibility

Authentication establishes the identity of the caller.

Authentication answers:

"Who is making this request?"

Authorization answers:

"Is this identity allowed to perform this operation?"

The two concerns must not be combined.

A successful authentication event must never imply unrestricted authorization.

3.2 Initial Authentication Architecture

The initial application architecture will support a backend-managed authentication model suitable for a self-hosted open-source deployment.

The design must permit future support for external identity providers without requiring major changes to application business logic.

Potential future identity integrations may include:

OpenID Connect;
OAuth 2.0-compatible identity providers;
enterprise single sign-on;
self-hosted identity systems.

External identity-provider integration is not required for the initial implementation.

3.3 Password Authentication

If local password authentication is implemented, passwords must never be stored in plaintext.

Passwords must be stored only as strong password hashes using a modern password hashing algorithm.

The implementation must:

use a cryptographically appropriate password hashing algorithm;
use unique salts;
use parameters appropriate for the deployment environment;
avoid custom password hashing algorithms;
never log plaintext passwords;
never expose password hashes through API responses;
support password verification without recovering the original password.

The exact password hashing library and parameters will be selected during implementation based on current maintained open-source libraries.

3.4 Credential Handling

Authentication credentials are sensitive security material.

The system must not:

log passwords;
place passwords in URLs;
return passwords from API responses;
store plaintext passwords in ordinary database fields;
expose credentials through frontend state unnecessarily;
include credentials in exception messages;
include credentials in audit records.

Secrets must be handled separately from ordinary application data where practical.

4. Session and Token Architecture
4.1 General Principle

Authentication state must be represented using a secure session or token mechanism.

The implementation must prevent:

session fixation;
session theft;
token leakage;
accidental credential exposure;
indefinite sessions;
reuse of invalidated sessions where revocation is required.

The exact mechanism will be finalized during implementation.

4.2 Browser Authentication

For browser-based authentication, the preferred architecture is a secure server-controlled session mechanism or an appropriately protected token mechanism.

If cookies are used, security-sensitive authentication cookies should use:

HttpOnly;
Secure when HTTPS is enabled;
appropriate SameSite configuration;
controlled expiration;
server-side invalidation where applicable.

Authentication state must not be stored in browser storage merely for convenience when a safer architecture is available.

Sensitive authentication material must not be unnecessarily exposed to JavaScript.

4.3 Token-Based API Access

If bearer tokens are supported, the implementation must:

validate token integrity;
validate expiration;
validate issuer/audience where applicable;
avoid accepting malformed tokens;
avoid accepting expired tokens;
support appropriate revocation or rotation mechanisms;
avoid logging full tokens;
avoid returning tokens unnecessarily.

Bearer tokens must be treated as secrets.

4.4 Session Expiration

Sessions must have explicit expiration policies.

The implementation should distinguish between:

access/session lifetime;
refresh lifetime where applicable;
password-reset lifetime;
email-verification lifetime;
invitation lifetime;
API-key lifetime where applicable.

Short-lived credentials should be preferred for high-risk operations.

5. Authorization
5.1 Authorization Responsibility

Authorization establishes whether an authenticated identity may perform a requested operation.

Authorization answers:

"Is this identity permitted to perform this operation on this resource in this context?"

Every protected backend operation must perform authorization appropriate to the resource and action.

5.2 Deny by Default

Protected resources will use deny-by-default authorization.

If the system cannot establish that an operation is authorized, the operation must be denied.

The implementation must never rely on:

"If the frontend does not show the button, the user cannot perform the action."

Instead:

Frontend restriction
        +
Backend authorization

must be used.

The backend authorization check is authoritative.

6. Authorization Model

Aegis Vuldris will initially use a layered authorization model.

The model will combine:

identity;
role/permission;
resource ownership;
project or organizational scope where applicable;
operation-specific security rules.

Conceptually:

Authenticated User
        |
        v
Role / Permission Check
        |
        v
Resource Scope Check
        |
        v
Operation Policy Check
        |
        v
Allow / Deny

This avoids relying on role-based access control alone.

7. Role-Based Access Control

Aegis Vuldris will support role-based permissions where appropriate.

The initial conceptual roles may include:

User

Can:

manage their own permitted resources;
create assessments;
execute authorized tests;
view authorized findings;
view authorized reports.
Project Administrator

Can additionally:

manage project resources;
manage project membership;
manage project-level configuration;
access project-wide assessment data.
System Administrator

Can additionally perform system-level administrative operations.

The exact production role set may evolve as multi-user and organizational functionality develops.

Roles must not automatically grant access to every resource.

Resource scope must still be enforced.

8. Permission Model

Permissions should represent actions rather than merely screens.

Examples include:

target:read
target:create
target:update
target:delete

assessment:read
assessment:create
assessment:update
assessment:delete
assessment:execute

job:read
job:create
job:cancel

finding:read
finding:update

evidence:read
evidence:delete

report:read
report:create
report:delete

project:read
project:update
project:manage_members

admin:system

The exact permission vocabulary will be refined during implementation.

Permissions should be checked at the backend service or policy boundary rather than duplicated arbitrarily throughout route handlers.

9. Resource-Level Authorization

Role checks alone are insufficient.

Every resource that contains user-specific or project-specific data must be checked against the caller's authorized scope.

For example:

User A
  |
  +-- Target A
  +-- Assessment A
  +-- Findings A

User B
  |
  +-- Target B
  +-- Assessment B
  +-- Findings B

User A must not be able to access User B's resources simply by changing an identifier.

For example:

/api/v1/targets/target-b-id

must not return Target B merely because the request is authenticated.

The backend must verify resource ownership or another valid authorization relationship.

10. Object-Level Authorization

Object-level authorization is mandatory for protected resources.

The implementation must explicitly defend against insecure direct object references and broken object-level authorization.

Examples requiring object-level authorization include:

target IDs;
assessment IDs;
job IDs;
finding IDs;
evidence IDs;
report IDs;
project IDs;
user IDs;
API-key identifiers.

A resource lookup must not be treated as an authorization decision.

Unsafe conceptual pattern:

resource = repository.get(resource_id)
return resource

Safer conceptual pattern:

resource = repository.get(resource_id)

if not authorization.can_read(user, resource):
    raise ForbiddenError()

return resource

The final implementation may use repository-level filtering or policy-aware queries to enforce the same invariant.

11. Database-Level Support

Where appropriate, authorization-aware queries should constrain resource retrieval directly.

For example:

SELECT *
FROM assessments
WHERE id = ?
AND owner_id = ?

or an equivalent project-scope query.

This reduces the chance of accidentally retrieving an unauthorized object before the authorization check.

Application-level authorization remains required.

Database-level isolation mechanisms may be considered for stronger multi-tenant isolation in future deployments.

12. Project and Tenant Isolation

Aegis Vuldris will be designed so that project or tenant boundaries can be introduced without redesigning the entire domain model.

Where a project model exists:

User
  |
  +-- Membership
          |
          +-- Project
                  |
                  +-- Targets
                  +-- Assessments
                  +-- Jobs
                  +-- Findings
                  +-- Evidence
                  +-- Reports

Access to project resources must be derived from project membership and permissions.

A user leaving a project must lose access to resources governed by that membership unless another valid authorization relationship exists.

Cross-project access must be explicitly authorized.

13. Administrative Authorization

Administrative endpoints require explicit administrative authorization.

Examples include:

user management;
role management;
project membership management;
system configuration;
security configuration;
maintenance operations;
sensitive diagnostics;
data deletion;
system-wide job control.

Administrative routes must not rely solely on route naming or frontend access restrictions.

14. Sensitive Operations

Certain operations require stronger controls than ordinary read operations.

Examples include:

changing authentication settings;
changing user roles;
changing project membership;
rotating credentials;
deleting assessments;
deleting evidence;
deleting reports;
changing target credentials;
exporting sensitive data;
disabling security controls;
system-wide administrative operations.

The architecture should support step-up authentication or re-authentication for particularly sensitive operations when appropriate.

15. API Keys

Aegis Vuldris may support API keys for programmatic access.

If implemented:

API keys must be high-entropy random values;
plaintext API keys should not be stored where avoidable;
only secure representations or hashes should be retained where practical;
keys should have scopes;
keys should support revocation;
keys should support expiration where appropriate;
keys must not be logged;
key values must not appear in ordinary API responses after creation;
key usage should be auditable.

API keys must follow least privilege.

A single unrestricted permanent API key should not be the default design.

16. Service-to-Service Authentication

Internal services must not automatically trust any network request merely because it originates from an internal network.

If Aegis Vuldris later becomes multi-service, service-to-service communication must use explicit authentication where appropriate.

Examples may include:

signed credentials;
short-lived service tokens;
mutual TLS;
authenticated message queues.

The exact mechanism will be selected based on the production deployment architecture.

17. Authorization and Background Jobs

Background jobs must preserve authorization context.

A job created by a user must not execute with unrestricted system privileges merely because it is running asynchronously.

Conceptually:

User
  |
  v
Authenticated Request
  |
  v
Authorization
  |
  v
Create Job
  |
  +-- owner/project scope
  +-- authorized target
  +-- permitted operation
  |
  v
Worker

The worker must validate the job's authorization context before accessing protected resources.

Jobs must not accept arbitrary user-controlled resource identifiers without validating that the job is authorized to access them.

18. Authorization and AI Model Testing

AI model testing introduces additional security concerns.

An assessment may cause Aegis Vuldris to:

send requests to external model APIs;
consume API credits;
process sensitive prompts;
store model responses;
execute large test suites;
access configured target credentials;
generate potentially sensitive evidence.

Therefore, authorization must apply to assessment execution itself.

A user who can view a target must not automatically be assumed to have permission to execute tests against it.

Permissions should distinguish where appropriate between:

target:read

and:

assessment:execute

This supports safer separation of discovery, configuration, and potentially expensive or externally impactful operations.

19. Authorization and Secrets

Access to model credentials and other secrets must be more restrictive than access to ordinary target metadata.

For example:

Target metadata
    ↓
May be visible to authorized users

Credential metadata
    ↓
Restricted

Credential plaintext
    ↓
Highly restricted / normally never returned

A user who can view a target should not automatically receive its plaintext API credential.

Secrets should be injected into the execution path only when required.

20. Authentication Error Handling

Authentication and authorization failures must not disclose unnecessary information.

Responses should avoid revealing:

whether a particular username exists;
whether a particular resource belongs to another user;
internal permission structures;
secret values;
internal authorization policies.

The application should use appropriate HTTP semantics while minimizing information leakage.

For example, resource access failures may intentionally return a generic not-found response where that prevents unauthorized resource enumeration.

The exact behavior must be consistent across the API.

21. Brute-Force Protection

Authentication endpoints must include appropriate protections against automated abuse.

Controls may include:

rate limiting;
login attempt throttling;
temporary account protection;
credential stuffing defenses;
monitoring;
audit logging.

Controls must avoid creating an easy denial-of-service mechanism against legitimate users.

22. Password Reset and Account Recovery

Password reset mechanisms must be designed as security-sensitive workflows.

Reset tokens must:

be cryptographically random;
expire;
be single-use;
not be logged;
not disclose whether a target account exists unnecessarily.

Reset URLs and tokens must not be unnecessarily persisted in application logs.

After successful password reset, appropriate existing-session invalidation should be supported.

23. Account Lifecycle

The architecture must support account lifecycle operations including:

account creation;
activation;
suspension;
deactivation;
deletion;
credential reset;
role changes.

Authorization must be reevaluated after privilege changes.

Previously issued sessions or credentials may need invalidation when security-sensitive account changes occur.

24. Audit Logging

Authentication and authorization events must generate appropriate audit records.

Important events include:

successful authentication;
failed authentication;
logout;
password change;
password reset;
API-key creation;
API-key revocation;
role changes;
project membership changes;
authorization failures;
sensitive resource access;
sensitive resource deletion;
administrative operations.

Audit records must not contain plaintext credentials, access tokens, or unnecessary sensitive data.

Audit logging is not a substitute for authorization.

25. Security Event Integrity

Security-sensitive audit events should be difficult for ordinary users to modify or delete.

Where practical:

Application
    |
    v
Audit Event
    |
    v
Protected Audit Storage

must be separated from ordinary user-controlled resource data.

Future production deployments may add:

append-only audit storage;
centralized logging;
integrity verification;
external log sinks.
26. Frontend Responsibilities

The React frontend may:

hide controls the user cannot use;
display authorized resources;
present role-dependent navigation;
handle authentication state;
display authorization errors.

However, the frontend must never be considered the security boundary.

A malicious user can bypass frontend restrictions by directly calling the API.

Therefore:

Frontend authorization UX
        ≠
Backend authorization

Backend authorization is mandatory.

27. Backend Authorization Architecture

Authorization logic should be centralized into reusable policy or service components.

Routes should remain relatively thin.

Conceptually:

HTTP Request
     |
     v
Authentication
     |
     v
Identity Context
     |
     v
Authorization Policy
     |
     v
Application Service
     |
     v
Repository / Database

This reduces duplicated authorization logic and makes security behavior easier to test.

28. Authorization Context

The authenticated request context should contain sufficient information for authorization decisions.

Depending on the final identity model, this may include:

user_id
roles
permissions
project memberships
authentication method
session metadata

Authorization code must not trust user-provided versions of these values.

For example, a request body such as:

{
  "user_id": "admin"
}

must not cause the server to treat the caller as that user.

Identity must come from verified authentication context.

29. Privilege Escalation Prevention

Users must not be able to elevate privileges by modifying client-controlled values.

Security-sensitive fields must be server-controlled.

Examples include:

role
is_admin
permissions
owner_id
project_membership
created_by

The backend must reject or ignore unauthorized attempts to modify such fields.

Mass-assignment vulnerabilities must be prevented through explicit request schemas and server-side authorization.

30. Authorization Testing Requirements

The test suite must include security tests for authorization.

At minimum, tests must cover:

Authentication
unauthenticated request rejection;
invalid credential rejection;
expired session rejection;
invalid token rejection;
revoked credential rejection where supported.
Authorization
authorized access succeeds;
unauthorized access fails;
role restrictions work;
permission restrictions work;
resource ownership is enforced;
project isolation is enforced;
administrative restrictions work.
Object-Level Access

Tests must verify that changing resource identifiers cannot expose another user's resources.

Examples:

User A → Target A → allowed
User A → Target B → denied

User A → Assessment A → allowed
User A → Assessment B → denied
Privilege Escalation

Tests must verify that users cannot modify:

role;
ownership;
project membership;
administrative flags;
protected permissions.
Background Jobs

Tests must verify that workers cannot execute unauthorized jobs or access unauthorized resources.

31. Security Invariants

The following invariants are mandatory.

Invariant 1

Every protected API operation requires authentication.

Invariant 2

Authentication does not imply authorization.

Invariant 3

Authorization is enforced by the backend.

Invariant 4

Resource ownership or project scope must be checked for protected resources.

Invariant 5

Client-controlled identity and privilege fields must never be trusted.

Invariant 6

Sensitive operations require appropriate permissions.

Invariant 7

Secrets are never returned unnecessarily.

Invariant 8

Authentication credentials are never logged.

Invariant 9

Background jobs preserve authorization scope.

Invariant 10

Authorization failures must not disclose unnecessary sensitive information.

32. Alternatives Considered
32.1 No Authentication

Rejected.

Aegis Vuldris will manage security-sensitive resources and cannot safely assume a trusted single user.

32.2 Frontend-Only Authorization

Rejected.

Frontend controls can be bypassed.

The backend must enforce authorization.

32.3 Role-Only Authorization

Rejected.

Roles alone do not solve resource-level authorization.

A user may have a valid role while still being unauthorized to access a particular resource.

32.4 Database-Only Authorization

Rejected as the sole mechanism.

Database isolation can strengthen security but cannot replace application authorization because authorization also depends on:

operation type;
user identity;
project membership;
role;
business rules;
security context.
32.5 Permanent Unrestricted API Tokens

Rejected as the default.

Long-lived unrestricted credentials create excessive blast radius.

32.6 Identity Provider Dependency From the Beginning

Deferred.

External identity providers are useful for enterprise deployments but would add complexity to the initial implementation.

The architecture will remain extensible so they can be introduced later.

33. Consequences
Positive Consequences

This architecture provides:

explicit authentication boundaries;
centralized authorization;
resource-level access control;
stronger multi-user isolation;
protection against IDOR/BOLA-style vulnerabilities;
safer administrative operations;
safer background jobs;
clearer security testing requirements;
extensibility toward enterprise identity systems;
better auditability;
reduced reliance on frontend behavior.
Negative Consequences

The architecture introduces additional complexity.

Examples include:

authentication flows;
session management;
authorization policies;
permission management;
resource ownership checks;
project membership checks;
audit events;
additional security testing.

These costs are accepted because authentication and authorization are foundational security requirements.

34. Implementation Boundaries

This ADR defines architectural behavior but does not yet select every implementation dependency.

Implementation decisions will determine:

exact password hashing library;
exact session/token implementation;
database schema details;
authentication endpoints;
middleware/dependencies;
authorization policy APIs;
API-key format;
identity-provider integrations.

These details must remain consistent with the security invariants defined here.

35. Relationship to Other Architecture Decisions

This decision depends on and reinforces:

ADR-001: FastAPI backend provides the authoritative API security boundary.
ADR-002: React frontend is not trusted as the authorization boundary.
ADR-003: PostgreSQL stores identity and resource relationships with appropriate integrity constraints.
ADR-004: API communication must transport authentication and authorization context securely.
ADR-005: Background test execution must preserve authorization scope.

Future decisions must not weaken these boundaries.

36. Security Review Requirements

Before authentication and authorization functionality is considered production-ready, the implementation must undergo security-focused review.

The review must include:

authentication flow review;
session/token review;
authorization policy review;
object-level authorization testing;
privilege escalation testing;
resource enumeration testing;
brute-force protection testing;
secret exposure testing;
background-job authorization testing;
administrative endpoint testing;
audit logging review.

Automated tests must be supplemented by adversarial security testing.

37. Future Extensions

The architecture should support future capabilities including:

OpenID Connect;
OAuth 2.0;
enterprise SSO;
MFA;
passkeys;
organization-level tenancy;
fine-grained permissions;
service identities;
scoped API keys;
short-lived credentials;
step-up authentication;
centralized identity management;
policy engines;
stronger database-level tenant isolation.

These extensions must preserve the core authorization invariants.

38. Decision Summary

Aegis Vuldris will implement authentication and authorization as explicit backend security layers.

The architecture will use:

Authentication
      ↓
Verified Identity
      ↓
Role / Permission Check
      ↓
Resource Scope Check
      ↓
Operation Policy Check
      ↓
Authorized Application Operation

The system will use deny-by-default authorization, resource-level access controls, project/tenant isolation where applicable, least privilege, protected secrets, secure session/token handling, and audit logging.

The frontend will never be considered a security boundary.

The backend will remain the authoritative enforcement point for all protected operations.

The architecture will also preserve sufficient abstraction to support future external identity providers, MFA, enterprise SSO, API keys, and stronger multi-tenant isolation without requiring a fundamental redesign.

Status: Accepted.
