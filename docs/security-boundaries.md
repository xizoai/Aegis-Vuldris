# Aegis Vuldris Security Boundaries

## Purpose

This document defines the trust boundaries of Aegis Vuldris.

A trust boundary exists wherever data, instructions, credentials, or
execution capability crosses from one security context into another.

Aegis Vuldris must treat data crossing a trust boundary as untrusted unless it
has been explicitly validated and authorized.

---

## 1. Core Trust Boundary

The Aegis Vuldris application itself is a trusted execution environment.

However, all external inputs entering the application are untrusted.

This includes:

- user input
- target model input
- target model output
- uploaded files
- remote API responses
- third-party service responses
- tool output
- generated attack payloads
- generated reports
- network metadata

Untrusted data must never directly control privileged Aegis Vuldris operations.

---

## 2. User → Aegis Vuldris

Users interact with Aegis Vuldris through the frontend and API.

### Untrusted

- usernames
- prompts
- target configuration
- URLs
- test parameters
- uploaded files
- report parameters
- API request bodies

### Required controls

- authentication
- authorization
- input validation
- rate limiting
- safe error handling
- audit logging where appropriate

Frontend validation must never replace backend validation.

---

## 3. Aegis Vuldris → Target Model

Aegis Vuldris intentionally sends security-testing inputs to target AI systems.

The target model must be treated as an external system.

Target responses are untrusted.

Aegis Vuldris must not assume that target model output is:

- truthful
- safe
- correctly formatted
- non-malicious
- policy compliant
- free of instructions intended to manipulate Aegis Vuldris

---

## 4. Target Model → Aegis Vuldris

This is a high-risk trust boundary.

A target model may return content designed to:

- manipulate the evaluator
- inject instructions
- imitate system messages
- produce malicious structured data
- request dangerous operations
- expose sensitive information
- consume excessive resources

Target model output must therefore be treated as untrusted data.

It must not directly modify:

- Aegis Vuldris configuration
- application permissions
- system instructions
- credentials
- filesystem contents
- database structure
- executable code
- security policies

---

## 5. Aegis Vuldris → External Network

Aegis Vuldris may eventually communicate with:

- AI model APIs
- target applications
- databases
- external integrations

Outbound network access is security-sensitive.

User-controlled destinations must not automatically receive unrestricted
network access.

Controls must address:

- SSRF
- private IP ranges
- localhost
- loopback interfaces
- cloud metadata endpoints
- unsafe protocols
- redirects
- DNS rebinding
- excessive outbound traffic

---

## 6. Aegis Vuldris → Database

The database is a separate security boundary.

Application code must use controlled database access.

Database queries must not be constructed from untrusted input using unsafe
string concatenation.

The application must enforce authorization before returning database
records.

Users must not be able to access another user's or tenant's data merely by
changing an identifier.

---

## 7. Aegis Vuldris → Filesystem

Filesystem access is privileged.

User-controlled filenames and paths must never be trusted directly.

The application must protect against:

- path traversal
- arbitrary file access
- unauthorized file modification
- symlink-based escapes
- accidental overwrites

Uploaded files must remain isolated from executable application code.

---

## 8. Aegis Vuldris → Tool Execution

Tool execution represents a high-risk boundary.

A model or user must not automatically receive arbitrary operating-system
capabilities.

Every tool must have:

- an explicit identity
- defined inputs
- authorization requirements
- controlled permissions
- resource limits
- auditability where appropriate

Dangerous operations should be isolated or sandboxed.

---

## 9. Aegis Vuldris → Container/Host

The host operating system is outside the application's normal trust
boundary.

A container must not receive unnecessary access to:

- host filesystem
- host network
- host devices
- privileged kernel capabilities
- host process namespace

Container isolation must be treated as an additional security layer, not
as the only security control.

---

## 10. AI Judge → Aegis Vuldris

Aegis Vuldris may eventually use AI models to evaluate security-test results.

The evaluator model must also be treated as untrusted.

An AI judge must not independently determine:

- application authorization
- user permissions
- credential access
- filesystem permissions
- network permissions

AI-generated evaluations should be combined with deterministic controls
and retained evidence.

---

## 11. Secrets Boundary

Credentials used to access target systems are highly sensitive.

Secrets must remain separated from:

- prompts
- model responses
- logs
- test evidence
- reports
- frontend responses
- source control

Only the component that requires a credential should receive access to it.

---

## 12. Reporting Boundary

Security reports may contain sensitive evidence.

Reports must therefore be treated as protected data.

Report generation must prevent untrusted content from becoming executable
content or unsafe markup.

Generated reports must not expose credentials or unrelated sensitive data.

---

## 13. Logging Boundary

Logs are operational data, not a dumping ground for application state.

The following should not normally be logged:

- API keys
- passwords
- session tokens
- database credentials
- complete sensitive model conversations
- private user data

Security-relevant events should be logged with the minimum information
necessary for investigation.

---

## 14. Trust Rule

The following rule applies throughout Aegis Vuldris:

> Data is not trusted merely because it came from an AI model, an internal
> component, a database, a container, or a previously validated request.

Every security-sensitive operation must enforce its own authorization and
validation requirements.

---

## 15. Security Boundary Review

Any new feature that introduces a new:

- external integration
- network connection
- file operation
- code execution capability
- tool
- model
- credential
- data store
- privileged operation

must identify its trust boundary and security controls before production
use.
