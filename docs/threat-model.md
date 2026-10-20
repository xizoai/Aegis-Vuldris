# Aegis Vuldris Threat Model

## 1. Purpose

This document defines the security threat model for Aegis Vuldris.

Aegis Vuldris is an AI security testing and evaluation platform that intentionally
interacts with potentially untrusted AI systems, prompts, documents, APIs,
URLs, files, tools, and generated content.

The threat model identifies:

- assets that require protection
- trust boundaries
- attack surfaces
- potential threats
- security impacts
- mitigations
- detection requirements
- security testing requirements

The threat model is intended to guide implementation and future security
reviews.

---

## 2. Security Objectives

Aegis Vuldris must protect:

1. User accounts and identities
2. Authentication credentials
3. API keys and target-system credentials
4. Security-test configurations
5. Target-system information
6. Test prompts and payloads
7. Target model responses
8. Evaluation evidence
9. Security findings
10. Reports
11. Database records
12. Uploaded files
13. Application configuration
14. Internal system instructions
15. Tool execution capabilities
16. Host and container resources
17. Other users' data
18. Tenant data, where multi-tenancy is supported
19. System availability
20. Audit information

---

## 3. Threat Actors

### 3.1 Unauthenticated Internet Attacker

An external attacker attempts to compromise publicly exposed Aegis Vuldris
interfaces.

Potential goals include:

- account compromise
- unauthorized access
- data theft
- service disruption
- SSRF
- remote code execution
- credential theft

---

### 3.2 Malicious Authenticated User

A legitimate user intentionally abuses Aegis Vuldris.

Potential goals include:

- accessing another user's data
- bypassing authorization
- extracting secrets
- abusing target integrations
- consuming excessive resources
- executing unauthorized tools

---

### 3.3 Compromised Target AI

A target AI system may behave maliciously or may be manipulated by an
attacker.

The target model must therefore be treated as untrusted.

Potential behaviors include:

- prompt injection
- malicious instructions
- fake system messages
- malicious structured output
- data exfiltration attempts
- resource exhaustion attempts
- attempts to manipulate the evaluator

---

### 3.4 Malicious Document or Dataset

A document, dataset, web page, or other artifact supplied to Aegis Vuldris may
contain malicious content.

Potential attacks include:

- indirect prompt injection
- malicious markup
- oversized content
- parser exploitation
- path traversal through filenames
- malicious instructions intended for AI evaluators

---

### 3.5 Compromised External Service

An external API, model provider, integration, or dependency may be
compromised or return unexpected content.

Aegis Vuldris must not automatically trust external responses.

---

### 3.6 Supply-Chain Attacker

An attacker compromises:

- Python dependencies
- JavaScript dependencies
- container images
- build tools
- GitHub Actions
- development tooling
- third-party integrations

The attacker attempts to introduce malicious code into Aegis Vuldris.

---

## 4. Trust Boundaries

Aegis Vuldris contains multiple trust boundaries.

### Boundary A — User → Aegis Vuldris

User-controlled requests enter the application.

All user input is untrusted.

---

### Boundary B — Aegis Vuldris → Target AI

Aegis Vuldris sends security-testing content to an external AI system.

The target system is outside Aegis Vuldris's trust boundary.

---

### Boundary C — Target AI → Aegis Vuldris

Target model output enters Aegis Vuldris.

The output is untrusted and may contain adversarial instructions.

---

### Boundary D — Aegis Vuldris → External Network

Aegis Vuldris may access externally specified URLs or APIs.

Outbound network access must be controlled.

---

### Boundary E — Aegis Vuldris → Database

Application code accesses persistent application data.

Authorization and query safety must be enforced.

---

### Boundary F — Aegis Vuldris → Filesystem

Uploaded files, reports, temporary files, and application files cross a
privileged boundary.

Filesystem operations require strict validation.

---

### Boundary G — Aegis Vuldris → Tool Execution

Tools may provide capabilities beyond normal application processing.

Tool access must be explicitly authorized and constrained.

---

### Boundary H — Aegis Vuldris → Container/Host

Application processes operate within infrastructure that must be isolated
from the host.

---

### Boundary I — AI Judge → Aegis Vuldris

AI-generated evaluations enter the trusted application workflow.

AI judges must not be treated as security authorities.

---

## 5. Asset Classification

| Asset | Confidentiality | Integrity | Availability |
|---|---|---|---|
| User credentials | Critical | Critical | High |
| API keys | Critical | Critical | High |
| Target credentials | Critical | Critical | High |
| User data | High | High | High |
| Test configurations | High | High | Medium |
| Test prompts | Medium | High | Medium |
| Model responses | Medium/High | High | Medium |
| Evaluation evidence | High | Critical | Medium |
| Security findings | High | Critical | High |
| Reports | High | Critical | Medium |
| Database | Critical | Critical | Critical |
| Uploaded files | Medium/High | High | Medium |
| Application configuration | High | Critical | High |
| Audit logs | High | Critical | High |
| Tool permissions | Critical | Critical | Critical |
| Container/host resources | Critical | Critical | Critical |

---

# 6. STRIDE Threat Analysis

## 6.1 Spoofing

### Threat S-01 — Account Impersonation

An attacker obtains or guesses authentication credentials and impersonates
another user.

**Impact:**

- unauthorized access
- data exposure
- unauthorized testing
- account takeover

**Controls:**

- secure authentication
- strong password handling where passwords are supported
- secure session management
- token expiration
- rate limiting
- authentication event logging

**Detection:**

- repeated authentication failures
- suspicious login behavior
- abnormal session activity

---

### Threat S-02 — API Credential Impersonation

An attacker obtains a target-system API key and uses it outside the intended
Aegis Vuldris workflow.

**Impact:**

- target-system compromise
- financial loss
- unauthorized API access
- data exposure

**Controls:**

- encrypted secret storage
- secret isolation
- least privilege
- secret redaction
- never expose secrets to frontend clients unnecessarily

---

## 6.2 Tampering

### Threat T-01 — Test Configuration Tampering

An attacker modifies another user's security-test configuration.

**Impact:**

- unauthorized testing
- incorrect results
- data integrity loss

**Controls:**

- authorization checks
- ownership validation
- immutable audit records where appropriate

---

### Threat T-02 — Evidence Tampering

An attacker modifies security-test evidence or findings.

**Impact:**

- false security conclusions
- unreliable reports
- loss of forensic value

**Controls:**

- access control
- immutable or append-only audit records where appropriate
- evidence integrity metadata
- controlled update workflows

---

### Threat T-03 — Report Tampering

Generated reports are modified without authorization.

**Impact:**

- false security reporting
- reputational damage
- incorrect remediation decisions

**Controls:**

- authorization
- controlled report generation
- integrity metadata
- audit logging

---

## 6.3 Repudiation

### Threat R-01 — Untraceable Security Actions

A user performs sensitive operations without sufficient audit information.

**Impact:**

- inability to investigate incidents
- inability to determine responsibility
- weak forensic capability

**Controls:**

Log security-relevant events such as:

- authentication events
- authorization failures
- target creation
- test execution
- credential changes
- report generation
- privileged operations

Logs must avoid exposing secrets or unnecessary sensitive content.

---

## 6.4 Information Disclosure

### Threat I-01 — Cross-User Data Access

A user accesses another user's resources by manipulating an identifier.

Example:

```text
GET /tests/123
