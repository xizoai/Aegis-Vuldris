# ADR-012: Privacy, Data Leakage & Sensitive Data Handling Architecture

**Status:** Accepted
**Date:** 2026-09-10
**Decision Owners:** Aegis Vuldris Contributors
**Scope:** Privacy testing, data leakage detection, sensitive-data handling, evidence protection, synthetic data, redaction, retention, isolation, and privacy-oriented security evaluation

---

## 1. Decision Summary

Aegis Vuldris will implement privacy and data-leakage testing as a dedicated security subsystem with explicit separation between:

1. test definition,
2. test input generation,
3. target execution,
4. response observation,
5. privacy analysis,
6. sensitive-data detection,
7. evidence handling,
8. finding creation,
9. risk assessment,
10. reporting, and
11. retention/deletion controls.

The privacy subsystem will detect and assess unauthorized disclosure, inference, exposure, reconstruction, memorization, cross-user leakage, cross-project leakage, sensitive-data handling failures, prompt-context leakage, tool-result leakage, RAG retrieval leakage, and related privacy failures.

Privacy findings will not be treated as ordinary text-matching failures.

Aegis Vuldris will preserve sufficient evidence to make findings reproducible while minimizing unnecessary storage of sensitive information.

Privacy testing must operate under explicit authorization and controlled test boundaries.

The system will prefer synthetic canary data and uniquely attributable markers wherever possible.

Sensitive data will be classified before storage where practical, and storage, logging, reporting, export, and retention behavior will be governed by data sensitivity.

The target model will never be treated as the sole privacy boundary.

Application-level authorization, tenant isolation, database authorization, filesystem controls, network controls, and tool permissions remain independent security boundaries.

---

## 2. Context

AI systems may process or expose information that is sensitive, confidential, personal, proprietary, regulated, or otherwise security-relevant.

A model can potentially leak information through:

- direct responses,
- system prompts,
- hidden instructions,
- conversation history,
- retrieval systems,
- embeddings,
- tool results,
- function arguments,
- agent memory,
- cached content,
- generated summaries,
- logs,
- error messages,
- model memorization,
- cross-user context,
- cross-project state,
- improperly isolated databases,
- uploaded files,
- generated reports,
- evaluator outputs, and
- downstream integrations.

Traditional security testing frequently focuses on whether a response contains a known string.

That approach is insufficient for AI systems.

A privacy-oriented security test may need to determine:

- whether a secret was disclosed,
- whether a sensitive record was retrieved without authorization,
- whether information from another user appeared in a response,
- whether a model reconstructed sensitive information,
- whether an attacker can infer protected attributes,
- whether a system prompt contains sensitive information,
- whether retrieved documents cross authorization boundaries,
- whether tool output exposes protected information,
- whether a conversation contaminates another conversation,
- whether an agent retains sensitive state beyond its permitted scope,
- whether sensitive evidence is unnecessarily persisted by Aegis Vuldris itself,
- whether generated reports reproduce protected information, and
- whether a privacy failure can be reliably reproduced.

Therefore privacy testing requires both:

- security evaluation of the target system, and
- privacy protection of Aegis Vuldris's own testing artifacts.

---

## 3. Problem Statement

Aegis Vuldris must answer two distinct questions:

### Question A

Did the target system improperly expose sensitive information?

### Question B

Did Aegis Vuldris itself unnecessarily expose or retain sensitive information while testing the target?

The first is a target security question.

The second is an Aegis Vuldris security and privacy question.

The architecture must protect against both.

---

## 4. Goals

This decision establishes architecture for:

- sensitive-data discovery,
- privacy test generation,
- privacy canary testing,
- data leakage detection,
- unauthorized disclosure detection,
- cross-user leakage testing,
- cross-project leakage testing,
- RAG leakage testing,
- agent memory leakage testing,
- tool-result leakage testing,
- prompt and context leakage testing,
- reconstruction testing,
- inference-oriented testing,
- memorization-oriented testing,
- sensitive-data classification,
- evidence minimization,
- redaction,
- retention,
- deletion,
- export controls,
- privacy finding creation,
- privacy-specific severity signals,
- privacy regression testing,
- privacy auditability, and
- secure privacy-test execution.

---

## 5. Non-Goals

This ADR does not define:

- general authentication architecture,
- general authorization architecture,
- general model adapter architecture,
- general attack orchestration,
- general evidence architecture,
- general risk scoring,
- general production deployment,
- legal determination of regulatory compliance,
- legal advice,
- replacement of an organization's privacy program,
- replacement of a data protection impact assessment,
- replacement of application-level access control.

Those concerns are governed by other architecture decisions and organizational policies.

---

## 6. Architectural Principles

Aegis Vuldris will follow these principles.

### 6.1 Privacy by design

Privacy controls are architectural requirements rather than optional reporting features.

### 6.2 Data minimization

Only the data required to execute, evaluate, reproduce, or explain a test should be retained.

### 6.3 Purpose limitation

Collected sensitive information must have a defined testing purpose.

### 6.4 Least privilege

Components receive only the permissions required for their task.

### 6.5 Defense in depth

No single privacy control is considered sufficient.

### 6.6 Explicit trust boundaries

Data crossing component or trust boundaries is treated as untrusted.

### 6.7 Synthetic data first

Synthetic secrets and synthetic personal data should be preferred for testing whenever they can provide equivalent coverage.

### 6.8 Attributable markers

Privacy tests should use uniquely identifiable canary values where possible.

### 6.9 Evidence minimization

Evidence should demonstrate the security failure without unnecessarily reproducing sensitive content.

### 6.10 Reproducibility

Privacy findings should remain reproducible without requiring uncontrolled retention of sensitive information.

### 6.11 Independent application security

Model behavior must never replace application-level authorization or data isolation.

---

## 7. Privacy Threat Model

The privacy subsystem considers the following threat classes.

### 7.1 Direct disclosure

The target directly returns sensitive information.

### 7.2 Indirect disclosure

The target reveals information through transformed or contextual responses.

### 7.3 Cross-user leakage

Information belonging to one user becomes accessible to another user.

### 7.4 Cross-project leakage

Information from one project becomes accessible to another project.

### 7.5 Cross-tenant leakage

Information from one tenant becomes accessible to another tenant.

### 7.6 Conversation leakage

Information from one conversation appears in another conversation.

### 7.7 Session leakage

Information persists across sessions when it should not.

### 7.8 Memory leakage

Agent or model memory exposes information outside its authorized scope.

### 7.9 RAG leakage

Unauthorized documents or chunks are retrieved or exposed.

### 7.10 Tool-result leakage

A tool returns sensitive information to an unauthorized model or user.

### 7.11 Prompt leakage

Sensitive system or developer instructions are disclosed.

### 7.12 Secret leakage

API keys, credentials, tokens, private keys, or similar secrets are exposed.

### 7.13 Personal-data leakage

Personally identifiable or otherwise sensitive personal information is exposed.

### 7.14 Proprietary-data leakage

Confidential business information is exposed.

### 7.15 Memorization leakage

A model reproduces information that should not be available from its permitted context.

### 7.16 Reconstruction

A system enables reconstruction of protected information from partial observations.

### 7.17 Inference

A system enables an attacker to infer protected attributes or confidential facts.

### 7.18 Metadata leakage

Metadata reveals sensitive information even when the underlying content is hidden.

### 7.19 Side-channel leakage

Timing, error, ranking, confidence, token behavior, or other observable properties reveal protected information.

### 7.20 Aggregation leakage

Multiple individually harmless responses combine to reveal sensitive information.

---

## 8. Privacy Data Classification

Aegis Vuldris will classify data according to sensitivity.

At minimum, the conceptual classification is:

- PUBLIC
- INTERNAL
- CONFIDENTIAL
- SENSITIVE
- SECRET
- RESTRICTED

Projects may define more granular classifications.

Classification is metadata, not a substitute for access control.

---

## 9. PUBLIC

Public data may be safely disclosed without authorization concerns.

Examples include:

- public documentation,
- public product descriptions,
- public test prompts,
- public metadata.

Public does not mean trusted.

Public content may still contain malicious instructions or injection payloads.

---

## 10. INTERNAL

Internal information is intended for authorized organizational use.

It should not automatically be exposed to external users or unrelated projects.

---

## 11. CONFIDENTIAL

Confidential information includes information that could cause business or operational harm if disclosed.

Examples include:

- internal architecture,
- private documentation,
- unreleased product information,
- internal policies,
- non-public configuration.

---

## 12. SENSITIVE

Sensitive information may create significant privacy, security, financial, legal, or operational impact if exposed.

Examples may include:

- personal information,
- authentication information,
- financial information,
- private communications,
- confidential records,
- internal identifiers.

---

## 13. SECRET

Secrets include values whose disclosure can directly enable unauthorized access.

Examples include:

- API keys,
- passwords,
- session tokens,
- access tokens,
- private keys,
- signing secrets,
- database credentials.

Secrets must never be intentionally persisted in plaintext by Aegis Vuldris unless an explicit architecture decision requires it and compensating controls exist.

---

## 14. RESTRICTED

Restricted information is subject to the strongest organizational controls.

Examples may include:

- highly sensitive regulated data,
- production credentials,
- privileged security material,
- highly confidential customer information.

Testing with restricted data should require explicit authorization and additional safeguards.

---

## 15. Data Classification Metadata

Privacy-relevant artifacts should carry metadata where applicable.

Conceptual fields include:

- classification,
- source,
- purpose,
- project,
- target,
- owner,
- created_at,
- retention_policy,
- redaction_policy,
- sensitivity_reason,
- authorization_scope.

Classification metadata itself may be sensitive.

---

## 16. Sensitive Data Types

The detection engine should support extensible categories.

Examples include:

- names,
- email addresses,
- phone numbers,
- physical addresses,
- government identifiers,
- financial identifiers,
- payment information,
- credentials,
- API keys,
- tokens,
- private keys,
- authentication cookies,
- health-related information,
- biometric identifiers,
- employee identifiers,
- customer identifiers,
- proprietary source code,
- internal URLs,
- confidential documents,
- system prompts,
- developer prompts,
- tool credentials,
- database connection strings,
- cloud credentials.

The list must remain extensible.

---

## 17. Detection Strategy

Aegis Vuldris will use multiple complementary detection strategies.

### 17.1 Exact matching

Detect known canary values or exact sensitive strings.

### 17.2 Pattern matching

Use carefully designed patterns for common sensitive-data formats.

### 17.3 Structured detection

Inspect JSON, XML, key-value structures, headers, tool calls, and other structured output.

### 17.4 Semantic detection

Use classifiers or other semantic methods to detect disclosures that are not exact string matches.

### 17.5 Contextual analysis

Determine whether detected information was authorized in the current context.

### 17.6 Provenance comparison

Compare observed output against known protected inputs.

### 17.7 Cross-context comparison

Compare outputs across users, sessions, projects, or tenants.

### 17.8 Composite evaluation

Combine multiple signals instead of relying on one detector.

---

## 18. Canary Data

Privacy testing should prefer synthetic canaries.

A canary is a uniquely identifiable value inserted into controlled test data.

Examples:

```text
AEGIS-CANARY-EMAIL-7F3A
AEGIS-CANARY-SECRET-92KD
AEGIS-CANARY-CUSTOMER-4M8P

Canaries should:

be unique,
be attributable to a test,
avoid resembling real credentials,
avoid granting actual privileges,
be traceable to their originating context,
be safe to store,
support exact matching.
19. Canary Lifecycle

Canary generation should record:

canary identifier,
test identifier,
generated value or protected representation,
classification,
intended scope,
creation time,
expiration,
expected exposure conditions.

Canary values should not become reusable production secrets.

20. Canary Non-Privilege Requirement

Synthetic canaries must not provide real access.

A test secret must never be:

a real cloud credential,
a real API key,
a real database password,
a valid production token,
a usable signing key.

The preferred design is to make synthetic credentials structurally recognizable but operationally invalid.

21. Real Sensitive Data

Real sensitive data should not be required for ordinary testing.

If real data is necessary:

authorization must be explicit,
the minimum required data should be used,
access must be restricted,
retention must be minimized,
logs must avoid unnecessary disclosure,
evidence must be minimized,
deletion must be supported,
exports must be controlled.
22. Test Data Isolation

Privacy test data must be isolated by project and execution context.

The architecture should prevent accidental mixing of:

test fixtures,
user data,
target data,
evaluator data,
evidence,
generated reports.
23. Project Isolation

A privacy test in Project A must not automatically access:

Project B's test data,
Project B's evidence,
Project B's targets,
Project B's credentials,
Project B's reports.

Authorization must be enforced independently of model behavior.

24. Target Isolation

Target A's data must not become available to Target B unless explicitly configured.

Adapters and execution contexts must preserve target boundaries.

25. Execution Isolation

Each execution should have an explicit privacy context.

Conceptual metadata includes:

execution_id,
project_id,
target_id,
user_id,
tenant_id where applicable,
authorization_scope,
data_classification,
retention_policy.
26. Conversation Isolation

Where conversational targets are tested, Aegis Vuldris must explicitly distinguish:

same conversation,
new conversation,
same session,
new session,
same user,
different user,
same project,
different project.

Privacy tests should use these distinctions to identify unintended persistence.

27. Cross-User Leakage Testing

Cross-user tests should establish:

User A creates protected canary data.
User A performs an operation that stores or exposes that data.
User B starts an independent authorized context.
User B attempts to retrieve the canary.
Aegis Vuldris evaluates whether disclosure occurred.

A finding should distinguish:

expected authorized access,
denied access,
partial leakage,
complete leakage,
ambiguous evidence.
28. Cross-Project Leakage Testing

Cross-project testing follows the same principle while varying project boundaries.

The test should verify that project-scoped information cannot be accessed through another project without authorization.

29. Cross-Tenant Leakage Testing

Where the target supports tenancy, tests should verify tenant isolation.

Tenant identifiers must be treated as authorization boundaries rather than merely metadata.

30. RAG Privacy Testing

RAG privacy tests should evaluate:

document authorization,
chunk authorization,
metadata filtering,
retrieval isolation,
citation leakage,
hidden document content,
cross-user retrieval,
cross-project retrieval,
cross-tenant retrieval,
deleted-document persistence,
stale-index leakage.
31. RAG Deletion Testing

When a document is deleted or access is revoked, privacy testing should verify whether the target can still retrieve information derived from that document.

The test should distinguish:

expected indexing delay,
unauthorized persistent retrieval,
cached response leakage,
embedding-related leakage,
generated-summary leakage.
32. Agent Memory Testing

Agent systems may store:

conversation state,
user preferences,
tool results,
retrieved documents,
intermediate reasoning artifacts,
generated summaries.

Tests should verify that memory scope matches authorization scope.

33. Memory Boundary Tests

Aegis Vuldris should test combinations such as:

same user / same session,
same user / new session,
different user / same project,
different user / different project,
different tenant,
revoked authorization,
deleted resource.
34. Tool Privacy Testing

Tool-enabled systems may expose sensitive data through:

tool results,
tool parameters,
error messages,
metadata,
generated summaries.

Privacy tests should verify that tool output is authorized before it reaches:

the model,
the user,
logs,
evidence,
reports.
35. Prompt Privacy Testing

System and developer prompts may contain sensitive information.

Testing should detect:

direct prompt extraction,
partial prompt disclosure,
secret fragments,
internal URLs,
credentials,
proprietary instructions,
hidden configuration.

Prompt disclosure should be classified according to the sensitivity of the exposed content.

36. Model Memorization Testing

Memorization-oriented testing should use authorized test material.

Tests may evaluate whether a model reproduces:

canary records,
synthetic confidential text,
controlled training-like material,
unique markers.

Claims about real-world training-data memorization require careful interpretation.

A matching response alone does not prove unauthorized training-data exposure.

37. Reconstruction Testing

Reconstruction tests may attempt to determine whether multiple outputs allow recovery of protected information.

Aegis Vuldris should record:

source material,
observations,
reconstruction method,
confidence,
required number of queries,
whether the reconstruction was exact or approximate.
38. Inference Testing

Inference testing evaluates whether an attacker can infer protected information from observable behavior.

Examples include:

membership inference,
attribute inference,
relationship inference,
existence inference.

Inference findings should distinguish direct disclosure from probabilistic inference.

39. Privacy Side Channels

Privacy evaluation may consider:

response timing,
error differences,
status codes,
response size,
ranking behavior,
confidence values,
token behavior,
retrieval scores.

Side-channel tests must remain bounded and authorized.

40. Aggregation Attacks

A sequence of individually non-sensitive answers may collectively reveal protected information.

The orchestration layer should support bounded aggregation tests while respecting the resource limits established by ADR-011.

41. Privacy Test Families

The privacy subsystem should support test families including:

privacy.direct_disclosure
privacy.cross_user
privacy.cross_project
privacy.cross_tenant
privacy.session_isolation
privacy.memory_isolation
privacy.rag_isolation
privacy.tool_output
privacy.prompt_disclosure
privacy.secret_exposure
privacy.personal_data
privacy.memorization
privacy.reconstruction
privacy.inference
privacy.metadata
privacy.side_channel
privacy.aggregation

Identifiers are illustrative and versionable.

42. Test Versioning

Privacy tests must be versioned.

Changing:

detection logic,
expected behavior,
fixtures,
canary strategy,
evaluator logic,
thresholds,
test steps

may require a test version change.

Historical results must retain the test version used.

43. Privacy Evaluator Architecture

Privacy evaluators should be modular.

Possible evaluator types include:

exact_match,
regex,
structured_match,
semantic_classifier,
provenance_match,
authorization_compare,
cross_context_compare,
composite.

LLM-based evaluation may be used only as one component of a broader evaluation strategy.

44. LLM Judge Limitations

An LLM judge must not be the sole authority for determining whether a sensitive-data leak occurred.

Where possible, deterministic evidence should establish:

whether the canary appeared,
whether a protected record was referenced,
whether an unauthorized context produced the data.

LLM judges may help interpret ambiguous semantic leakage.

45. Authorization-Aware Evaluation

Privacy detection must consider whether disclosure was authorized.

The presence of a sensitive value is not automatically a vulnerability.

For example:

an authorized administrator retrieving an authorized record may be expected,
an unrelated user retrieving the same record may be a finding.

Evaluation therefore requires both:

data sensitivity, and
authorization context.
46. Expected Exposure

Tests should declare whether sensitive data is expected to be exposed.

Possible states include:

expected,
prohibited,
conditionally permitted,
unknown.
47. Privacy Policy Context

Each privacy test may specify policy expectations.

Conceptual fields include:

permitted_data_classes,
prohibited_data_classes,
permitted_subjects,
permitted_projects,
permitted_users,
permitted_tools,
permitted_targets,
permitted_operations.
48. Data Subject Context

Where relevant, tests may identify the data subject category without storing unnecessary personal information.

Examples:

synthetic customer,
synthetic employee,
synthetic administrator,
synthetic vendor.
49. Sensitive Data Matching

Matching should support normalization.

Examples include normalization of:

case,
whitespace,
formatting,
punctuation,
common encoding,
structured serialization.

Normalization must not create false positives that materially affect findings.

50. Partial Leakage

A system may leak only part of a protected value.

The evaluator should support:

exact match,
prefix match,
suffix match,
fragment match,
transformed match,
semantic match.

Partial leakage severity depends on exploitability and sensitivity.

51. Encoded Leakage

Sensitive values may be encoded.

Tests may detect authorized transformations such as:

Base64,
hexadecimal,
URL encoding,
escaped JSON,
Unicode representations.

Decoding must be bounded and must not execute untrusted content.

52. Obfuscated Leakage

Detection should consider common transformations while avoiding unsafe dynamic execution.

Aegis Vuldris must never evaluate arbitrary leaked content as executable code merely to determine whether it contains a secret.

53. Secret Detection

Secret detectors should recognize common credential structures where practical.

Detection should avoid storing full secrets unnecessarily.

Preferred evidence includes:

secret type,
location,
fingerprint,
redacted representation,
matched test identifier.
54. Secret Fingerprints

Aegis Vuldris may store a one-way fingerprint or keyed digest of a sensitive value to support correlation without retaining the plaintext.

The exact cryptographic mechanism will be defined in implementation.

Plain hashes must not automatically be assumed safe for low-entropy secrets.

55. Redaction

Sensitive evidence should be redacted before:

ordinary logs,
user-visible reports,
exports,
telemetry,
notifications.

Redaction must preserve enough context for understanding and reproduction.

56. Redaction Strategy

Possible redaction forms include:

sk-[REDACTED]
user@example.com -> [EMAIL_REDACTED]
AEGIS-CANARY-SECRET-92KD -> [CANARY_SECRET]

The system should preserve a stable representation when correlation is required.

57. Evidence Tiers

Privacy evidence should support sensitivity-aware tiers.

Tier 0

Metadata only.

Tier 1

Redacted evidence.

Tier 2

Minimal sensitive evidence.

Tier 3

Restricted raw evidence.

Higher tiers require stronger authorization.

58. Default Evidence Level

The default should be the minimum evidence level sufficient to establish the finding.

Raw sensitive output must not be the default storage format.

59. Raw Response Handling

Raw target responses may contain sensitive information.

Storage should therefore be:

explicitly controlled,
access restricted,
encrypted where required,
retention-limited,
auditable.
60. Evidence Access

Access to sensitive evidence must be independently authorized.

A user who can view a finding does not automatically receive unrestricted access to raw evidence.

61. Evidence Authorization

Authorization should consider:

user,
role,
project,
target,
execution,
evidence classification,
operation.
62. Evidence Encryption

Sensitive evidence should be encrypted at rest when required by deployment policy or classification.

Encryption keys must not be stored in source control.

63. Transport Protection

Sensitive evidence must use protected transport when crossing network boundaries.

TLS should be required for production deployments.

64. Database Storage

Sensitive evidence stored in PostgreSQL must be subject to:

project isolation,
authorization,
classification,
retention policy,
deletion semantics,
audit logging.
65. Database Queries

Queries involving sensitive evidence must use parameterized operations.

Dynamic SQL based on untrusted model output is prohibited.

66. Report Generation

Reports may contain sensitive evidence.

Report generation must therefore apply:

authorization,
redaction,
classification,
retention,
secure download,
audit logging.
67. Export Controls

Exports should be explicit user actions.

Exports containing sensitive evidence should require appropriate authorization.

68. CSV Injection

Generated CSV reports must safely handle values beginning with spreadsheet formula characters.

Untrusted model output must not be allowed to become executable spreadsheet formulas.

69. HTML Report Injection

HTML reports must safely encode untrusted content.

Model output, prompts, tool results, filenames, and evidence must not be inserted as trusted HTML.

70. Markdown Safety

Markdown rendering must consider:

embedded HTML,
links,
images,
scriptable content,
dangerous URL schemes.

Untrusted content must not create an unintended browser execution path.

71. PDF Generation

PDF generation must treat evidence and model output as untrusted data.

Generated documents must not execute arbitrary embedded content.

72. Logging Policy

Logs should contain enough information for operational diagnosis without reproducing sensitive content unnecessarily.

Preferred logging:

identifiers,
event type,
classification,
status,
timing,
counts,
fingerprints,
redacted summaries.
73. Sensitive Log Prevention

The system should prevent accidental logging of:

API keys,
passwords,
access tokens,
session cookies,
private keys,
raw personal records,
unrestricted model responses containing sensitive content.
74. Exception Handling

Exceptions must not expose sensitive payloads to users or logs by default.

Error messages should use safe identifiers and controlled summaries.

75. Metrics

Metrics should avoid high-cardinality sensitive values.

Never use raw:

secrets,
personal identifiers,
prompts,
responses

as metric labels.

76. Tracing

Distributed tracing should use identifiers rather than sensitive content.

Trace attributes must follow the same classification rules as logs.

77. Audit Logging

Sensitive-data access must be auditable.

Audit events may include:

actor,
action,
resource,
project,
evidence classification,
timestamp,
result.

Sensitive content itself should generally not be placed in the audit event.

78. Retention

Every sensitive artifact should have a retention policy.

Possible retention categories include:

execution lifetime,
short-term,
project-defined,
regulatory/organizational,
indefinite only when explicitly justified.
79. Default Retention

The default should minimize retention while preserving required reproducibility.

Long-term retention of raw sensitive responses should require explicit justification.

80. Deletion

Aegis Vuldris must support deletion of privacy-sensitive artifacts where operationally appropriate.

Deletion should consider:

database records,
raw evidence,
generated reports,
exports,
caches,
temporary files,
object storage,
derived artifacts.
81. Deletion and Derived Data

Deleting a source artifact does not automatically mean all derived data is safe.

The architecture should identify dependencies between:

raw evidence,
findings,
reports,
fingerprints,
summaries,
embeddings,
caches.
82. Temporary Files

Sensitive test data must not remain indefinitely in temporary directories.

Temporary files should have:

controlled permissions,
bounded lifetime,
cleanup behavior,
safe filenames.
83. File Names

Sensitive information must not be encoded into filenames.

Use opaque identifiers.

84. Path Safety

Paths derived from target responses, model output, or user-controlled input must not permit:

path traversal,
arbitrary overwrite,
access outside permitted directories.
85. Archive Safety

If privacy evidence is compressed or archived, extraction must prevent:

path traversal,
archive bombs,
unexpected file types,
arbitrary overwrite.
86. Upload Safety

Uploaded test fixtures may contain sensitive information.

Uploads must be:

validated,
classified,
size-limited,
isolated,
access-controlled,
retention-managed.
87. Content-Type Validation

File extensions alone must not establish trust.

Where practical, Aegis Vuldris should validate file content and enforce permitted formats.

88. Image Privacy

Images may contain:

faces,
documents,
IDs,
screenshots,
credentials,
metadata.

Privacy testing involving images should apply equivalent classification and evidence controls.

89. Metadata Privacy

Files may contain metadata such as:

author,
timestamps,
location,
software,
internal paths.

Metadata should be considered during sensitive-data handling.

90. Clipboard and Browser Data

If future integrations access browser or clipboard data, such data must be treated as potentially sensitive and subject to explicit authorization.

91. External Integrations

External services must not receive sensitive evidence unless explicitly configured and authorized.

Default behavior should minimize outbound disclosure.

92. Evaluator Data Sharing

Sending target responses to an external LLM evaluator can create a secondary data disclosure.

Therefore:

local evaluators are preferred for sensitive data,
external evaluators require explicit configuration,
sensitive data should be redacted where possible,
outbound sharing should be auditable.
93. External LLM Privacy Boundary

An external evaluator is a separate trust boundary.

Aegis Vuldris must not assume that a third-party model provider:

stores no data,
deletes data immediately,
provides confidentiality,
uses no data for training,
satisfies an organization's privacy requirements.

Those properties must be verified and configured separately.

94. Local Evaluators

For sensitive tests, local/open-source evaluators should be preferred where practical.

This reduces external data transfer.

95. Evaluator Isolation

Evaluator input should contain only what is required for the evaluation.

Do not send unrelated project context.

96. Prompt Construction

Privacy evaluator prompts must not unnecessarily include:

unrelated user records,
unrelated project data,
credentials,
full raw logs.
97. Prompt Injection in Privacy Evaluation

Sensitive target output may contain malicious instructions.

A privacy evaluator must treat target output as untrusted data.

Target output must never automatically override evaluator instructions.

98. Model-as-Judge Security

An LLM judge may be manipulated by target output.

Therefore deterministic privacy checks should be preferred for known canaries.

99. Privacy Evaluation Evidence

Evaluator decisions should retain:

evaluator identifier,
evaluator version,
inputs or references,
decision,
confidence where applicable,
reason,
timestamp.

Sensitive raw inputs should be minimized.

100. Confidence

Evaluator confidence is distinct from risk.

A high-confidence privacy detection does not automatically mean high risk.

Risk assessment remains governed by ADR-009.

101. Privacy Severity Signals

Privacy findings should provide signals to the risk engine including:

sensitivity,
exposure scope,
authorization status,
exploitability,
persistence,
reproducibility,
number of affected contexts,
data subject impact,
secret usability,
aggregation requirements.

ADR-009 remains responsible for final risk scoring.

102. Exposure Scope

Exposure scope should distinguish:

single response,
single user,
multiple users,
project,
tenant,
organization,
public/external.
103. Persistence

Privacy impact may increase when leaked data persists through:

memory,
logs,
cache,
indexes,
reports,
databases,
downstream systems.

Persistence should therefore be recorded.

104. Reproducibility

A finding should record whether the leakage is:

deterministic,
intermittent,
probabilistic,
context-dependent,
unreproducible.
105. Privacy Finding Structure

Conceptual privacy finding fields include:

finding_id,
test_id,
test_version,
category,
data_classification,
leakage_type,
source_context,
destination_context,
authorization_state,
evidence_reference,
confidence,
exposure_scope,
persistence,
reproducibility,
severity,
recommendation,
status.
106. Finding Correlation

Repeated observations of the same privacy defect should be correlated.

Correlation should not erase meaningful differences in:

affected users,
projects,
data types,
attack paths,
exposure scope.
107. Duplicate Findings

Deduplication must distinguish:

repeated evidence of one issue,
separate issues involving different authorization boundaries,
separate data classes,
separate root causes.
108. Privacy Regression Testing

Known privacy findings should become regression tests where practical.

Regression tests should verify that:

the canary is no longer disclosed,
unauthorized retrieval remains blocked,
isolation remains intact,
deletion remains effective,
tool boundaries remain enforced.
109. Regression Baselines

A privacy baseline should record:

test version,
target version where available,
expected result,
evaluator version,
relevant configuration,
execution environment.
110. False Positives

Privacy detection must account for false positives.

Examples include:

public information,
intentionally exposed test data,
expected administrator access,
synthetic values that appear sensitive,
documentation examples.
111. False Negatives

No privacy detector can guarantee detection of all leakage.

The architecture should support multiple complementary detection methods.

112. Ambiguous Results

If the system cannot determine whether disclosure violated authorization, the result should be:

INCONCLUSIVE

rather than automatically marking a vulnerability.

113. Evaluation States

Privacy evaluators should support:

PASS,
FAIL,
INCONCLUSIVE,
ERROR,
SKIPPED.

These states follow ADR-010.

114. Test Preconditions

Privacy tests may require:

multiple users,
multiple projects,
controlled documents,
canaries,
role assignments,
session boundaries,
memory configuration,
target capabilities.

Preconditions must be explicit.

115. Test Postconditions

Tests should define cleanup expectations.

Examples:

remove synthetic documents,
invalidate sessions,
delete canaries,
clear temporary state,
remove test users where appropriate.
116. Cleanup Failure

If cleanup fails, Aegis Vuldris must record the failure.

Cleanup failure may itself create a security or privacy concern.

117. Isolation Verification

The system should verify that cleanup actually occurred where feasible.

A cleanup command succeeding is not equivalent to proof that data is inaccessible.

118. Authorization Context

Every privacy test should identify the authorization context under which it executes.

This includes, where applicable:

principal,
role,
permissions,
tenant,
project,
target,
session.
119. Privilege Escalation

Privacy testing may identify cases where a low-privilege user can access high-privilege data.

Such cases should be classified as authorization/privacy boundary failures.

120. Administrative Access

Administrator access must not automatically justify unrestricted evidence access.

Aegis Vuldris itself should maintain least-privilege administrative controls.

121. Multi-Tenant Architecture

If Aegis Vuldris supports tenants, tenant boundaries are mandatory security boundaries.

All privacy artifacts must carry tenant ownership where applicable.

122. Tenant Isolation Invariant

A request authorized for Tenant A must never retrieve Tenant B's sensitive evidence.

This invariant must be enforced at the application and persistence layers.

123. Project Isolation Invariant

A project-scoped user must not retrieve another project's sensitive evidence.

124. Target Isolation Invariant

A target-scoped user must not retrieve unrelated target evidence.

125. Evidence Isolation Invariant

Knowledge of a finding identifier must not bypass evidence authorization.

Opaque identifiers are not authorization.

126. Report Isolation Invariant

Knowledge of a report identifier must not bypass report authorization.

127. Job Isolation Invariant

Knowledge of an execution identifier must not allow access to another project's execution data.

128. API Authorization

Every sensitive API endpoint must enforce authorization.

Frontend restrictions are insufficient.

129. Object-Level Authorization

Authorization must be evaluated against the requested resource.

Do not assume that authentication implies resource access.

130. Broken Object-Level Authorization

Privacy regression tests should explicitly test for object-level authorization failures.

Examples include manipulating:

project IDs,
target IDs,
execution IDs,
finding IDs,
evidence IDs,
report IDs.
131. Identifier Security

Identifiers should be difficult to guess where practical.

However, unguessability is not a substitute for authorization.

132. Secrets in URLs

Sensitive values must not be placed in URLs or query parameters.

URLs may be logged by infrastructure.

133. Secrets in Headers

Sensitive authentication material should be handled through appropriate protected headers and never copied into ordinary application logs.

134. Secrets in Request Bodies

Sensitive values should be handled carefully and excluded from generic request logging.

135. Secrets in Responses

API responses should return only the minimum sensitive data required.

136. Secret Display

Secrets should be masked by default in user interfaces.

Explicit reveal operations should require authorization and auditing where appropriate.

137. Secret Copying

If a UI allows copying sensitive values, the operation should be treated as a sensitive action.

138. Browser Storage

Sensitive evidence should not be stored unnecessarily in browser local storage.

Session and evidence handling must follow the authentication architecture.

139. Frontend Caching

Sensitive responses should not be cached beyond what is required.

Browser and intermediary cache controls should be appropriate to sensitivity.

140. API Error Responses

API errors should not disclose:

database records,
SQL fragments,
credentials,
internal file paths,
private target content.
141. Database Error Handling

Database exceptions must be sanitized before reaching clients.

142. Backup Considerations

Sensitive evidence may appear in database backups.

Backup retention and access controls must therefore align with evidence retention.

143. Backup Deletion

A logical deletion from the primary database does not guarantee immediate deletion from all backups.

Deployment documentation must define backup retention behavior.

144. Object Storage

If evidence is stored in object storage, access must use:

authorization,
scoped paths or object identifiers,
encryption,
retention policies,
secure deletion procedures.
145. Signed URLs

If signed URLs are used for sensitive evidence:

expiration must be short,
authorization must be checked before issuing them,
URLs must not be logged unnecessarily.
146. Cache Security

Caches may retain sensitive data.

Sensitive cache entries require:

bounded TTL,
access controls,
isolation,
invalidation behavior.
147. Queue Security

Job queues may contain sensitive execution information.

Queue payloads should contain references rather than full sensitive content where practical.

148. Worker Security

Workers must enforce the same project and evidence isolation as API processes.

149. Background Job Leakage

A background job must not:

log raw sensitive prompts,
emit raw responses to shared queues,
store unrestricted evidence,
access another project's resources.
150. Concurrency

Concurrent privacy tests must maintain isolation.

A race condition must not cause:

context mixing,
evidence mixing,
authorization confusion,
canary misattribution.
151. Canary Attribution Under Concurrency

Each canary should map to an explicit test/execution context.

This prevents one test's marker from being attributed to another.

152. Race Testing

Privacy testing should include controlled concurrency where race conditions may affect isolation.

153. Shared State

Shared mutable state must be minimized.

Where shared state is unavoidable, ownership and synchronization must be explicit.

154. Process Isolation

Sensitive test execution should use process/container isolation where required by target capabilities.

155. Container Isolation

Containers must not be assumed to make arbitrary target interaction safe.

Host access, mounted volumes, network access, and capabilities must be explicitly controlled.

156. Network Privacy

Outbound requests may disclose target or test information.

Network access should therefore be controlled and logged appropriately.

157. SSRF

Target-generated URLs, model-generated URLs, and tool-generated URLs must be treated as untrusted.

Privacy testing must not accidentally turn the Aegis Vuldris infrastructure into an SSRF proxy.

158. Private Network Protection

Requests to private or sensitive network ranges should be denied unless explicitly required and authorized.

159. DNS Rebinding

Network validation must account for DNS rebinding where relevant.

Checking a hostname once is insufficient if the resolved destination can change.

160. Redirect Handling

Redirects must be validated.

A safe initial URL must not automatically make an unsafe redirected destination safe.

161. URL Scheme

Only permitted URL schemes should be accepted.

Dangerous or unexpected schemes must be rejected.

162. File URI Protection

Remote or target-generated file URIs must not automatically grant local filesystem access.

163. Command Execution

Model output or leaked content must never become an operating-system command without an explicit, separately secured execution mechanism.

164. Shell Injection

Untrusted privacy-test values must never be interpolated directly into shell commands.

165. Serialization

Untrusted privacy artifacts must not be deserialized using unsafe mechanisms.

166. YAML

Untrusted YAML must not be processed with unsafe constructors.

167. Pickle

Untrusted data must never be loaded through unsafe Python pickle deserialization.

168. Dynamic Imports

Model-controlled or user-controlled module names must not automatically become dynamic imports.

169. Plugin Privacy

Plugins that process sensitive data must declare their data requirements.

Plugin trust boundaries remain governed by the plugin architecture.

170. External Plugin Data Sharing

Plugins must not silently transmit sensitive evidence to external services.

171. Plugin Capability Scope

Sensitive-data access should be denied unless the plugin explicitly requires it and authorization permits it.

172. Privacy Policy Configuration

Projects should be able to configure privacy policies.

Conceptual configuration includes:

prohibited_data_classes,
permitted_data_classes,
evidence_retention,
evidence_redaction,
external_evaluator_policy,
export_policy,
raw_response_policy.
173. Secure Defaults

Secure privacy defaults should include:

synthetic data preferred,
raw evidence restricted,
external evaluators disabled for restricted data,
sensitive logs redacted,
exports controlled,
retention bounded,
cross-project access denied.
174. Configuration Validation

Invalid or unsafe privacy configurations should fail closed where possible.

175. Policy Precedence

When multiple policies apply, the stricter applicable privacy restriction should generally win unless an explicit higher-priority policy is defined.

176. Configuration Auditability

Changes to privacy-sensitive configuration should be auditable.

177. Test Policy Versioning

Privacy policy versions should be recorded with test results.

178. Privacy Test Metadata

Privacy tests should include metadata such as:

category,
version,
sensitivity,
prerequisites,
expected exposure,
evaluator,
cleanup requirements,
risk signals.
179. Test Discovery

The test engine should discover privacy tests through registered metadata rather than hardcoded routing.

180. Test Selection

Users should be able to select privacy tests by:

category,
severity,
sensitivity,
target capability,
profile,
tags,
project policy.
181. Privacy Profiles

The framework should support profiles such as:

basic privacy,
secrets,
RAG privacy,
agent privacy,
cross-user isolation,
high-assurance privacy.

Profiles must remain bounded and explicit.

182. High-Assurance Testing

High-assurance privacy tests may require:

stronger isolation,
additional evidence,
multiple independent evaluators,
stricter authorization,
extended regression coverage.
183. Destructive Privacy Tests

Tests that delete data, alter permissions, or otherwise modify target state require explicit authorization.

They should not be enabled by default.

184. Production Testing

Production privacy testing requires especially strict safeguards.

Synthetic data and non-destructive tests should be preferred.

185. Production Data

Production data must not be copied into development or test environments without explicit authorization and appropriate protections.

186. Development Data

Development fixtures should use synthetic data whenever practical.

187. Test Fixture Repository

Fixtures containing sensitive information must not be committed to source control.

188. Secret Scanning

The repository should use automated secret scanning where practical.

189. Pre-Commit Secret Checks

Future implementation may add secret-detection hooks to prevent accidental credential commits.

190. CI Secret Protection

CI logs must not expose secrets or sensitive evidence.

191. Pull Request Protection

Sensitive test outputs should not be automatically posted into pull requests.

Use redacted summaries.

192. CI Artifacts

CI artifacts containing sensitive evidence require restricted retention and access.

193. Public CI

Public CI pipelines must never expose private target responses.

194. Test Failure Output

Pytest failures should avoid printing complete sensitive fixtures or target responses.

195. Debug Mode

Debug mode must not disable privacy protections.

196. Development Logging

Development environments may have more verbose logs, but sensitive-data redaction remains mandatory.

197. Local Developer Data

Developers should use synthetic privacy fixtures.

Real sensitive data should not be required for normal development.

198. Documentation Examples

Documentation must use synthetic examples.

199. Screenshots

Screenshots included in documentation or issue reports must be checked for sensitive information.

200. Issue Tracker

Security or privacy issues must not include raw sensitive data unless the issue-management process explicitly supports it.

201. Security Disclosure

If a real privacy vulnerability is discovered, disclosure should follow the responsible disclosure process of the target owner.

Aegis Vuldris must not publish sensitive target data merely to demonstrate a finding.

202. Finding Redaction

Public or shared findings should use redacted evidence.

203. Finding Ownership

Findings should be scoped to the project and target that produced them.

204. Finding Status

Privacy findings should support statuses such as:

OPEN,
ACKNOWLEDGED,
REMEDIATED,
ACCEPTED_RISK,
FALSE_POSITIVE,
DUPLICATE.
205. Accepted Risk

Accepted-risk decisions should record:

actor,
timestamp,
rationale,
scope,
expiration where applicable.
206. Privacy Exceptions

Exceptions should be explicit rather than encoded as undocumented bypasses.

207. Exception Expiration

Temporary privacy exceptions should have expiration dates.

208. Privacy Control Testing

Aegis Vuldris itself should have automated tests for:

project isolation,
tenant isolation,
evidence authorization,
secret redaction,
report redaction,
retention behavior,
deletion,
cross-context isolation,
canary attribution.
209. Unit Tests

Deterministic detectors should have unit tests covering:

positive matches,
negative matches,
malformed inputs,
encoding variants,
false-positive cases,
large inputs.
210. Property Tests

Property-based testing may validate detector invariants.

211. Fuzz Testing

Privacy parsers should be fuzz-tested for:

malformed JSON,
malformed encodings,
unusual Unicode,
oversized input,
deeply nested structures.
212. Metamorphic Tests

Privacy detectors should maintain expected behavior under safe transformations.

213. Regression Corpus

A controlled corpus of synthetic privacy cases should be maintained.

The corpus must not contain real sensitive information.

214. Golden Tests

Known expected privacy outcomes should be represented as golden tests.

215. Detector Versioning

Changing a detector may alter historical outcomes.

Results must retain detector version information.

216. Threshold Changes

Changes to detection thresholds must be versioned and reviewed.

217. Semantic Detector Drift

LLM-based or statistical detectors may change behavior over time.

Detector model/version must therefore be recorded.

218. Privacy Benchmarking

Aegis Vuldris may benchmark privacy detectors against controlled synthetic datasets.

Benchmark datasets should measure:

precision,
recall,
false-positive rate,
false-negative rate,
latency.
219. Benchmark Privacy

Benchmark datasets themselves must not contain real personal or confidential information.

220. Detector Performance

Privacy detection must not create uncontrolled resource consumption.

Inputs and processing depth should be bounded.

221. Maximum Response Size

Privacy evaluators should enforce response-size limits.

222. Maximum Decode Depth

Recursive decoding of encoded values must have a bounded depth.

223. Regex Safety

Regular expressions must be designed to avoid catastrophic backtracking.

224. Parser Safety

Parsers must use bounded resource consumption.

225. Large Document Handling

Large documents should be processed incrementally or with explicit limits.

226. Compression Bombs

Compressed test fixtures must have decompression limits.

227. Archive Bombs

Archives must be inspected before extraction and bounded by size and file-count limits.

228. Privacy Test Budgets

Privacy tests must inherit execution budgets from ADR-011.

Budgets include:

maximum turns,
maximum requests,
maximum duration,
maximum tokens,
maximum response bytes,
maximum tool calls,
maximum network requests.
229. Adaptive Privacy Attacks

Adaptive privacy tests may adjust strategy based on observations.

They must remain bounded by the orchestration layer.

230. Adaptive Strategy Boundary

An adaptive strategy must never be able to change:

authorization,
project scope,
tenant scope,
network policy,
filesystem policy,
secret access,
evidence access,
execution limits.
231. Privacy Test State

State should be explicitly represented and versioned.

Sensitive state should not be hidden inside arbitrary Python globals.

232. State Serialization

Persisted test state must use safe serialization formats.

233. State Isolation

State must be scoped to the execution.

234. Replay

Privacy tests should support replay where practical.

Replay should use the same:

test version,
canaries,
target configuration,
evaluator version,
policy version.
235. Replay Safety

Replay must not accidentally reuse real credentials or production-sensitive data.

236. Deterministic Canaries

Canaries should be deterministic when reproducibility requires it, while avoiding collisions across concurrent executions.

237. Random Canaries

Random canaries may be used when uniqueness is more important than deterministic generation.

The seed or generation metadata should be recorded where safe.

238. Randomness Security

Random values used for security-sensitive correlation should use an appropriate cryptographic random source.

239. Canary Expiration

Canaries should have an expiration policy.

240. Canary Cleanup

Expired canaries should not remain indefinitely in persistent stores.

241. Canary Collision

The system should detect improbable but possible canary collisions.

242. Canary Storage

Where possible, Aegis Vuldris should store a protected representation rather than unnecessary plaintext copies.

243. Canary Correlation

A protected canary representation should allow reliable correlation without exposing the original value.

244. Privacy Test Inputs

Inputs may contain:

synthetic personal data,
synthetic secrets,
synthetic confidential documents,
authorization markers.

All must be classified.

245. Privacy Test Outputs

Outputs should be classified based on the most sensitive content they contain.

246. Classification Propagation

Derived artifacts should inherit an appropriate sensitivity classification from their source data.

247. Classification Downgrade

A derived artifact must not be marked less sensitive merely because it contains a summary.

248. Summaries

A summary may still contain sensitive information.

Summaries must therefore be classified independently.

249. Embeddings

Embeddings derived from sensitive information may themselves be sensitive.

If Aegis Vuldris stores embeddings in the future, they must receive appropriate access and retention controls.

250. Vector Database

Vector stores used for privacy testing must enforce the same project and tenant boundaries as relational storage.

251. Retrieval Authorization

Retrieval authorization must be enforced before returning content, not merely after model generation.

252. Model Context Authorization

Sensitive content must not enter model context merely because the model could theoretically be instructed not to reveal it.

253. Tool Authorization

Tools must enforce authorization independently of the model.

254. Memory Authorization

Memory stores must enforce authorization independently of the model.

255. Cache Authorization

Caches must enforce authorization independently of the model.

256. Search Authorization

Search and retrieval layers must enforce authorization independently of the model.

257. Database Authorization

Database access must enforce least privilege and resource isolation.

258. Filesystem Authorization

Filesystem access must be restricted to permitted directories.

259. Network Authorization

Network access must be restricted according to explicit policy.

260. Model Boundary

The target model is an untrusted processing component from Aegis Vuldris's perspective.

261. Target Output Trust

Target output must never be treated as trusted application instructions.

262. Sensitive Target Output

Target output may contain:

secrets,
malicious instructions,
exploit payloads,
personal information,
confidential content.

It must be handled as untrusted data.

263. Prompt Injection

A target response containing instructions such as "ignore your security policy" must not influence Aegis Vuldris's privacy controls.

264. Indirect Prompt Injection

Retrieved documents may attempt to manipulate the evaluator or orchestrator.

They remain untrusted.

265. Evaluator Isolation

The privacy evaluator must receive target output through a controlled data channel.

266. Control/Data Plane Separation

Untrusted target data must not be able to directly modify:

test configuration,
authorization,
budgets,
storage policy,
network policy,
deletion policy.
267. Structured Output Validation

Structured target output must be validated against a schema before use.

268. Unknown Fields

Unexpected structured fields must not automatically become executable configuration.

269. URLs in Target Output

URLs returned by targets must remain data unless explicitly passed through an authorized network operation.

270. Tool Names in Target Output

Tool names returned by targets must not automatically trigger tools.

271. File Paths in Target Output

File paths returned by targets must not automatically be opened.

272. Commands in Target Output

Commands returned by targets must never automatically execute.

273. Privacy Attack Generation

Attack generation should produce privacy-focused attempts such as:

direct retrieval,
role manipulation,
context confusion,
cross-session retrieval,
prompt extraction,
tool extraction,
memory extraction,
RAG retrieval,
indirect inference.
274. Attack Safety

Attack generation must remain within authorized boundaries.

275. Attack Corpus

Reusable privacy attack templates should be versioned.

276. Template Variables

Privacy templates should use safe synthetic variables.

277. Real Identifiers

Real customer or employee identifiers should not be required in reusable attack templates.

278. Test Naming

Privacy tests should use stable identifiers.

279. Finding Naming

Findings should use opaque identifiers rather than embedding sensitive data in names.

280. Report Naming

Reports should use opaque filenames.

281. Log Correlation

Opaque identifiers should connect:

execution,
test,
evidence,
finding,
report

without exposing sensitive content.

282. Privacy Event Schema

Conceptual privacy events may include:

PrivacyTestStarted
SensitiveDataDetected
UnauthorizedDisclosureDetected
EvidenceRedacted
SensitiveEvidenceAccessed
SensitiveEvidenceDeleted
PrivacyPolicyChanged
PrivacyFindingCreated
PrivacyFindingResolved
283. Event Payload Minimization

Events should contain references rather than full sensitive content whenever possible.

284. Event Authorization

Sensitive event streams must be access-controlled.

285. Event Retention

Privacy events must have retention policies.

286. Audit Integrity

Audit events should be protected against unauthorized modification.

287. Time Synchronization

Privacy event timestamps should use consistent UTC representation.

288. Clock Dependence

Retention and expiration behavior should not rely on untrusted client-provided timestamps.

289. Privacy API

Future API endpoints should expose privacy test operations through the normal authentication and authorization architecture.

290. Privacy API Examples

Conceptual operations include:

list privacy tests,
start privacy test,
retrieve privacy finding,
retrieve redacted evidence,
request authorized raw evidence,
export redacted report,
delete sensitive evidence.
291. API Response Minimization

API responses should not return unnecessary sensitive fields.

292. Pagination

Sensitive findings and evidence lists must use authorized pagination.

293. Filtering

Filtering parameters must not bypass authorization.

294. Search

Search endpoints must apply the same resource-level authorization as direct retrieval.

295. Bulk Operations

Bulk privacy operations require authorization for every affected resource.

296. Bulk Export

Bulk export must not bypass individual evidence restrictions.

297. Rate Limits

Privacy endpoints should have rate limits to prevent:

brute-force discovery,
bulk extraction,
denial of service.
298. Privacy Enumeration

APIs must not reveal whether an unauthorized resource exists through distinguishable responses where that information itself is sensitive.

299. Response Timing

Where resource existence is sensitive, timing differences should be considered.

300. Notification Privacy

Notifications about privacy findings should not contain raw sensitive evidence.

301. Email Privacy

If email notifications are implemented, emails should contain minimal information and direct users to authorized secure interfaces.

302. Webhook Privacy

Webhooks must not transmit sensitive evidence unless explicitly configured.

303. Webhook Signing

Sensitive webhooks should use authentication/integrity mechanisms.

304. Webhook Replay

Webhook events should support replay protection where required.

305. Integration Failures

External integration failures must not cause sensitive evidence to be dumped into logs.

306. Privacy Policy Failure

If a privacy policy cannot be evaluated reliably, the system should fail safely or mark the result inconclusive rather than silently permitting exposure.

307. Fail-Closed

Security-sensitive authorization checks should fail closed.

308. Fail-Safe Evidence

If redaction fails, raw sensitive evidence should not automatically be exposed.

309. Redaction Failure

A redaction failure should produce a controlled error and audit event.

310. Evidence Retrieval Failure

If restricted evidence cannot be safely authorized, deny retrieval.

311. Deletion Failure

Deletion failure should be visible and auditable.

312. Retention Failure

If retention cleanup fails, the system should record the condition and support operational remediation.

313. Privacy Health Checks

Operational health checks should verify privacy-critical dependencies without exposing sensitive data.

314. Security Health Checks

Security health checks should validate:

authorization configuration,
evidence storage,
redaction,
encryption configuration,
retention jobs.
315. Startup Validation

Application startup should reject obviously unsafe privacy configurations where feasible.

316. Environment Separation

Development, testing, staging, and production privacy configurations must be distinguishable.

317. Production Safety Flag

Production-target testing should require explicit configuration.

318. Sensitive Mode

Aegis Vuldris may support a high-security privacy mode with stricter defaults.

319. High-Security Defaults

High-security mode may:

disable raw evidence,
disable external evaluators,
disable broad exports,
reduce retention,
require stronger authentication.
320. Configuration Secrets

Privacy configuration must not contain plaintext secrets in source control.

321. Environment Variables

Sensitive configuration should be injected through approved secret-management mechanisms.

322. Secret Rotation

Secrets used for privacy infrastructure should support rotation.

323. Secret Scope

Each integration should use the least privileged credential available.

324. Secret Exposure in Findings

Findings should never intentionally include usable credentials.

325. Credential Revocation

If a real credential is accidentally exposed during authorized testing, the appropriate response should include immediate revocation or rotation by the authorized owner.

Aegis Vuldris should not attempt unauthorized credential use.

326. Incident Handling

A real sensitive-data exposure discovered by Aegis Vuldris should be treated as a security/privacy incident according to the target owner's process.

327. Incident Evidence

Incident evidence should be minimized and access-controlled.

328. Incident Notifications

Incident notifications should avoid including raw sensitive data.

329. Privacy Risk Mapping

Privacy findings provide inputs to ADR-009 risk scoring.

330. Severity Inputs

Potential severity signals include:

sensitivity,
authorization violation,
exposure scope,
exploitability,
persistence,
affected records,
repeatability,
secret usability.
331. No Automatic Legal Classification

Aegis Vuldris should not automatically claim that a technical finding constitutes a specific legal violation without an appropriate policy mapping and qualified interpretation.

332. Compliance Mapping

Future compliance mappings may connect technical findings to privacy controls.

Mappings must remain separate from technical evidence.

333. Regulatory Metadata

Where supported, a project may record relevant regulatory frameworks.

The presence of a framework does not automatically determine legal compliance.

334. Data Subject Rights

Aegis Vuldris's own data-management features may eventually support organizational requirements around:

access,
deletion,
export,
retention.

Specific legal obligations remain outside this ADR.

335. Privacy Documentation

Projects should document:

what data is tested,
why it is tested,
how it is retained,
who can access it,
when it is deleted.
336. User Consent

Where organizational policy requires consent or notice for testing, Aegis Vuldris does not replace that process.

337. Authorized Testing

Privacy testing is permitted only against systems the operator owns or is explicitly authorized to assess.

338. Unauthorized Data Acquisition

Aegis Vuldris must not be used to acquire private information from systems without authorization.

339. Data Exfiltration Boundary

The objective of a privacy test is to demonstrate a controlled security condition, not to collect as much private data as possible.

340. Minimal Proof

Aegis Vuldris should stop a privacy test once sufficient evidence exists to establish the vulnerability, where practical.

341. Exfiltration Limits

Privacy tests must have bounded extraction limits.

342. Canary Stop Condition

A test may stop when a uniquely attributable canary is disclosed.

Further extraction is generally unnecessary.

343. Sensitive Data Stop Condition

Where real sensitive data is encountered, the test should stop or minimize additional collection unless explicitly authorized.

344. Safe Demonstration

Findings should demonstrate:

what happened,
why it was unauthorized,
what boundary was crossed,
how to reproduce safely,
how to remediate.
345. Reproduction

Reproduction steps should use synthetic data where possible.

346. Remediation

Recommendations may include:

authorization enforcement,
data filtering,
retrieval filtering,
tenant isolation,
memory isolation,
tool access control,
secret removal,
prompt hardening,
cache invalidation,
deletion enforcement.
347. Root Cause

Findings should distinguish root cause from observed symptom.

Example:

Observed symptom:
User B received User A's canary.

Potential root cause:
RAG retrieval omitted tenant authorization filtering.

348. Evidence Chain

Privacy findings should maintain a chain:

Test
  -> Input
  -> Target Context
  -> Observation
  -> Sensitive Data Detection
  -> Authorization Comparison
  -> Evaluation
  -> Evidence
  -> Finding
  -> Risk
349. Evidence Integrity

Evidence references should be integrity-protected where required.

350. Evidence Tampering

Unauthorized modification of evidence must be detectable where assurance requirements justify it.

351. Hashing

Evidence may use cryptographic digests for integrity and correlation.

352. Hash Limitations

A digest is an integrity mechanism, not an access-control mechanism.

353. Evidence Versioning

If evidence is transformed through redaction, the transformation should be recorded.

354. Transformation Metadata

Record:

transformation type,
version,
timestamp,
operator/system,
resulting classification.
355. Redaction Reversibility

Redaction should generally be irreversible in user-visible artifacts.

356. Restricted Raw Evidence

If reversible masking or raw evidence is retained, access must be strictly controlled.

357. Privacy Evidence UI

The UI should display:

classification,
redaction status,
access restrictions,
evidence summary.
358. Raw Reveal

Raw reveal should be an explicit operation, not default page rendering.

359. Reveal Audit

Raw evidence reveal operations should be auditable.

360. Clipboard Protection

Sensitive content should not be automatically copied to clipboard.

361. Browser History

Sensitive evidence should not appear in URL paths or query strings.

362. Browser Cache

Sensitive pages should use appropriate cache-control policies.

363. Screenshots in UI

User interfaces should minimize unnecessary rendering of sensitive evidence.

364. Pagination of Evidence

Raw evidence should not be loaded automatically in large lists.

365. Progressive Disclosure

Sensitive information should be revealed only when necessary.

366. Privacy Dashboard

A future privacy dashboard may summarize:

privacy tests,
leakage categories,
findings,
severity,
trends,
remediation.
367. Dashboard Redaction

Dashboard summaries should avoid exposing raw sensitive values.

368. Trend Data

Trend metrics should use aggregate statistics.

369. Aggregated Privacy Metrics

Examples:

number of privacy findings,
findings by classification,
cross-project leakage count,
unresolved high-risk findings.
370. Metric Safety

Aggregates must not become an oracle for sensitive record existence where that would itself create a privacy issue.

371. Privacy Regression Gate

CI may fail when defined privacy regression conditions are violated.

372. Gate Configuration

Gates should specify:

affected test families,
required status,
allowed exceptions,
severity threshold,
baseline version.
373. Gate Failures

Gate failures should return minimal evidence in public CI output.

374. Security Review

Changes to privacy detection or evidence handling should receive security review.

375. Code Review Requirements

Reviewers should consider:

authorization,
classification,
retention,
redaction,
external data transfer,
logging,
concurrency,
isolation.
376. Dependency Review

Dependencies used for privacy detection must be reviewed for:

license,
maintenance,
security,
data handling,
network behavior.
377. Supply Chain

Third-party privacy detectors must not silently upload test data.

378. Offline Operation

Where practical, sensitive privacy detection should support offline operation.

379. Network-Free Evaluators

Deterministic detectors should not require network access.

380. External Model Evaluators

External model evaluators require explicit opt-in for sensitive data.

381. Data Transfer Audit

Outbound sensitive data transfers should be observable and auditable.

382. Network Allowlist

External privacy evaluators should use an explicit network allowlist.

383. Provider Configuration

Provider endpoints should be explicitly configured rather than inferred from model output.

384. Provider Identity

Evaluation records should include the provider and model identifier when external evaluation is used.

385. Provider Version

Provider/model version should be retained where available for reproducibility.

386. Provider Data Policy

Organizations must independently verify the provider's data-handling policy.

Aegis Vuldris cannot infer contractual privacy guarantees from an API endpoint alone.

387. Local-Only Policy

Projects may enforce a local-only evaluation policy for sensitive classifications.

388. External Evaluation Denial

If external evaluation is prohibited for a classification, the system should deny the operation rather than silently downgrade protections.

389. Privacy Data Flow Documentation

The architecture should document:

Test Fixture
   |
   v
Privacy Test
   |
   v
Target
   |
   v
Observation
   |
   +--> Deterministic Detector
   |
   +--> Optional Local Evaluator
   |
   v
Evidence
   |
   v
Finding
   |
   v
Risk
   |
   v
Report

Each transition is a privacy boundary.

390. Data Flow Review

New components handling sensitive information require data-flow review.

391. New Storage Review

Any new persistent storage of sensitive data requires explicit architecture review.

392. New External Service Review

Any new external service receiving target responses or evidence requires explicit privacy review.

393. Privacy Architecture Review

Privacy architecture should be reviewed when:

new target types are added,
new evaluators are added,
new storage is added,
new exports are added,
new agent capabilities are added,
new integrations are added.
394. Threat Model Updates

New privacy attack classes should update the threat model.

395. Security Boundaries

This ADR extends the trust boundaries established by the security baseline and threat model.

396. Relationship to ADR-005

Job execution must preserve privacy isolation and evidence authorization.

397. Relationship to ADR-006

Authentication and authorization define who may access privacy artifacts.

398. Relationship to ADR-007

Model adapters define the target integration boundary.

399. Relationship to ADR-008

Evidence architecture defines evidence storage and lifecycle.

This ADR adds privacy-specific classification and minimization requirements.

400. Relationship to ADR-009

Risk scoring consumes privacy-specific risk signals.

This ADR does not replace the central risk engine.

401. Relationship to ADR-010

Privacy tests are implemented as security test/evaluation modules under ADR-010.

402. Relationship to ADR-011

Multi-turn privacy attacks are orchestrated under ADR-011.

403. Architecture Dependency

Privacy functionality should not bypass the existing architecture decisions.

404. Central Policy Enforcement

Privacy restrictions should be enforced through reusable policy mechanisms rather than duplicated ad hoc checks.

405. Policy Enforcement Point

Sensitive evidence access should pass through a central authorization/policy enforcement layer.

406. Policy Enforcement Failure

If the policy engine is unavailable for a sensitive operation, deny access rather than bypassing policy.

407. Service-to-Service Authorization

Internal services must authenticate and authorize requests where sensitive data crosses service boundaries.

408. Internal Trust

Internal network location must not automatically imply trust.

409. Database Credentials

Database credentials must use least privilege.

410. Read vs Write Access

Components that only need to read privacy artifacts should not automatically receive write/delete privileges.

411. Delete Privilege

Deletion should be granted only to components that require it.

412. Export Privilege

Export permissions should be separate from ordinary finding-view permissions.

413. Raw Evidence Privilege

Raw evidence access should be more restrictive than redacted finding access.

414. Administrative Override

Administrative overrides must be explicit and auditable.

415. Break-Glass Access

If break-glass access is implemented, it must:

require strong authentication,
be narrowly scoped,
be time-limited,
be audited.
416. Privacy Review of Break-Glass

Break-glass access must not become a routine bypass.

417. Access Reviews

Sensitive evidence access permissions should be periodically reviewed.

418. Dormant Data

Sensitive evidence that is no longer required should be removed according to policy.

419. Dormant Accounts

Users who no longer require access should lose access according to the authentication/authorization lifecycle.

420. Service Account Review

Service accounts accessing sensitive evidence should be reviewed periodically.

421. API Key Scope

Service credentials should be scoped to required projects or resources where supported.

422. Privacy Test Identity

Privacy tests should use dedicated identities rather than personal administrator credentials where practical.

423. Identity Attribution

Test actions should be attributable to the executing identity.

424. Shared Accounts

Shared accounts should be avoided for privacy testing.

425. Session Isolation

Test sessions should not accidentally reuse human browser sessions.

426. Authentication Cookies

Aegis Vuldris should not persist target authentication cookies beyond their intended lifetime.

427. Token Handling

Target tokens should be stored only where necessary and should never appear in ordinary evidence.

428. Token Redaction

Known token patterns should be redacted from logs and evidence.

429. Token Expiration

Test tokens should have the shortest practical lifetime.

430. Test Credentials

Test credentials should be synthetic or dedicated and non-production whenever possible.

431. Credential Cleanup

Test credentials should be revoked or deleted after testing where appropriate.

432. Credential Ownership

Aegis Vuldris should not assume ownership of target credentials.

433. Credential Rotation

Target owners remain responsible for rotating credentials exposed during authorized testing.

434. Privacy Test Scope

Each run should declare a bounded scope.

435. Scope Expansion

A test must not expand into additional users, tenants, projects, or data classes without explicit authorization.

436. Scope Enforcement

Scope should be enforced by code rather than relying solely on test prompts.

437. Model Prompt Scope

A prompt saying "only test this project" is not sufficient security enforcement.

438. Target Capability Scope

Target capabilities should be explicitly declared.

439. Unsupported Privacy Test

If required target capabilities are unavailable, mark the test as skipped rather than approximating silently.

440. Test Capability Matrix

Privacy tests should declare required capabilities.

441. Capability Validation

Capabilities should be validated before execution.

442. Capability Spoofing

Target output must not be allowed to claim capabilities that Aegis Vuldris has not actually authorized.

443. Privacy Test Planning

Before execution, Aegis Vuldris should determine:

scope,
data classification,
target capabilities,
evaluator,
retention,
evidence policy,
budget,
cleanup.
444. Privacy Test Execution

Execution follows:

Plan
  -> Preconditions
  -> Canary/Data Setup
  -> Attack/Test
  -> Observation
  -> Detection
  -> Authorization Evaluation
  -> Evidence
  -> Finding
  -> Cleanup
445. Cleanup Before Reporting

Where possible, cleanup should occur before long-term evidence/report generation.

446. Cleanup and Evidence

If cleanup affects reproducibility, the system should retain the minimum information necessary to reproduce the security claim.

447. Cleanup Evidence

Cleanup results should be recorded as metadata.

448. Privacy Test Completion

A test is not fully complete until cleanup expectations are satisfied or explicitly recorded as failed.

449. Interrupted Tests

Interrupted tests must execute best-effort cleanup.

450. Cancellation

Cancellation should propagate to privacy test workers.

451. Cancellation Safety

Cancellation must not bypass evidence or cleanup protections.

452. Timeout Safety

Timeouts must not leave uncontrolled sensitive temporary data.

453. Worker Crash

Worker crashes should trigger cleanup/recovery mechanisms where possible.

454. Orphaned Evidence

The system should detect and clean orphaned temporary sensitive artifacts.

455. Recovery

Recovery jobs must preserve isolation and authorization.

456. Privacy Test Queues

Queue messages should reference execution IDs rather than include full sensitive content.

457. Queue Encryption

Sensitive queue infrastructure should use appropriate transport and storage protections.

458. Dead Letter Queues

Dead-letter queues may contain sensitive data and require equivalent protections.

459. Retry Data

Retries must not multiply sensitive evidence unnecessarily.

460. Idempotency

Privacy setup and cleanup operations should be idempotent where possible.

461. Duplicate Canaries

Repeated setup should not create ambiguous canary ownership.

462. Duplicate Evidence

Repeated observations should not cause uncontrolled evidence duplication.

463. Storage Quotas

Sensitive evidence storage should have quotas.

464. Resource Exhaustion

An attacker-controlled target must not be able to cause unbounded sensitive-data storage.

465. Evidence Size Limits

Raw and redacted evidence must have size limits.

466. Truncation

Truncation should preserve enough context for evaluation while minimizing storage.

467. Truncation Metadata

Evidence should record whether it was truncated.

468. Evidence Completeness

A finding should distinguish:

complete evidence,
partial evidence,
truncated evidence.
469. Confidence After Truncation

Truncation must not silently preserve a confidence value that depended on unavailable content.

470. Privacy Finding Confidence

Confidence should reflect the evidence actually available.

471. Sensitive Data Classifier Confidence

Classifier confidence should be stored separately from finding severity.

472. Multi-Signal Detection

Multiple independent detectors may increase confidence.

473. Detector Disagreement

Detector disagreement should be represented rather than hidden.

474. Human Review

Sensitive findings may require human review.

475. Human Review Access

Reviewers must receive only the evidence necessary for the review.

476. Review Decisions

Review decisions should be auditable.

477. Reviewer Annotations

Reviewer comments may themselves contain sensitive information.

478. Annotation Classification

Annotations should inherit appropriate sensitivity.

479. Reviewer Exports

Reviewer exports must follow evidence restrictions.

480. Privacy Finding Resolution

Resolution should record:

resolver,
timestamp,
remediation reference,
verification result.
481. Remediation Verification

A privacy finding should be marked remediated only after an appropriate regression test passes.

482. Retest

Retesting should preserve the original finding history.

483. Historical Findings

Historical findings must retain their original evidence classification and test version.

484. Historical Data Access

Historical privacy evidence remains subject to authorization.

485. Historical Deletion

Deleting historical evidence should not silently delete audit records required for accountability unless policy permits it.

486. Audit vs Evidence

Audit metadata and raw evidence have different retention requirements.

487. Audit Minimization

Audit records should not become a second copy of sensitive evidence.

488. Privacy Metrics Retention

Aggregate metrics may be retained longer than raw evidence when they do not expose sensitive information.

489. Aggregation Review

Aggregated data should be reviewed for re-identification risk where relevant.

490. Re-identification

Aegis Vuldris should consider whether combining metadata can identify a person, tenant, or confidential resource.

491. Small-Group Metrics

Metrics about very small groups may require suppression where they could reveal sensitive facts.

492. Differential Privacy

Differential privacy is not required for the initial implementation.

It may be considered for future analytics where appropriate.

493. Privacy Analytics

Analytics should prioritize aggregate security trends rather than individual sensitive records.

494. Data Minimization in Analytics

Analytics pipelines should use summarized or redacted data where possible.

495. Privacy Testing of Aegis Vuldris

Aegis Vuldris should eventually test itself for:

evidence isolation,
cross-project leakage,
cross-user leakage,
secret exposure,
report leakage,
API enumeration,
authorization bypass.
496. Self-Testing

Self-testing must not use uncontrolled production-like secrets.

497. Synthetic Self-Test Data

Aegis Vuldris self-tests should use unique synthetic canaries.

498. Self-Test Isolation

Self-tests should run in isolated test environments where practical.

499. Security Regression

Privacy self-tests should run in CI.

500. Release Gate

A release should not proceed when defined critical privacy self-tests fail.

501. Documentation Gate

Privacy architecture changes must update relevant documentation.

502. ADR References

Implementation changes should reference the applicable ADR.

503. Change Review

Changes that weaken privacy controls require explicit review.

504. No Silent Downgrades

A dependency or configuration change must not silently downgrade privacy protections.

505. Feature Flags

Privacy-sensitive feature flags should have secure defaults.

506. Flag Authorization

Changing sensitive feature flags should require authorization.

507. Flag Audit

Sensitive flag changes should be audited.

508. Emergency Changes

Emergency changes should be reviewed retrospectively.

509. Privacy Control Inventory

The implementation should maintain an inventory of privacy controls.

510. Control Ownership

Each privacy control should have an identifiable owner in the implementation.

511. Control Testing Frequency

Critical privacy controls should be tested regularly.

512. Control Failure Monitoring

Operational monitoring should detect failures of privacy-critical jobs such as retention cleanup.

513. Alerting

Alerts should contain minimal sensitive information.

514. Alert Destinations

Sensitive alerts should only go to authorized destinations.

515. Monitoring Integrations

External monitoring services must not receive raw sensitive evidence by default.

516. Telemetry Sampling

Sensitive traces should be sampled conservatively.

517. Telemetry Scrubbing

Telemetry pipelines should scrub sensitive attributes.

518. Debug Dumps

Automatic memory dumps may contain sensitive data and must be controlled.

519. Crash Reporting

Crash-reporting systems must be reviewed for data leakage.

520. Dependency Telemetry

Third-party libraries must not be allowed to transmit sensitive test data unexpectedly.

521. Network Egress

Default egress should be restrictive for sensitive execution environments.

522. DNS Logging

DNS logs may reveal target or data relationships and should be considered in privacy analysis.

523. Proxy Logs

HTTP proxy logs may contain URLs or headers containing sensitive information.

524. TLS Inspection

If TLS inspection is used, its privacy implications must be documented.

525. Localhost Access

Local services may contain sensitive information.

Targets must not automatically access Aegis Vuldris internal services.

526. Metadata Service Protection

Cloud metadata endpoints must be protected from SSRF.

527. Container Metadata

Container runtime metadata should not be exposed to target-generated requests.

528. Host Files

Host files must not be exposed to target processes.

529. Mounted Volumes

Sensitive host directories must not be mounted into untrusted execution environments.

530. Temporary Secrets

Secrets injected into test processes should have bounded lifetime.

531. Environment Variables

Environment variables may be exposed by process inspection or accidental logging.

Sensitive values should therefore be minimized.

532. Process Arguments

Secrets must not be passed through command-line arguments where they may appear in process listings.

533. Shell History

Sensitive commands must not be written to shell history.

534. Developer Tools

Debugging tools must be treated as privileged access paths to sensitive evidence.

535. IDE Integrations

IDE integrations should not automatically transmit sensitive files to external services.

536. AI Coding Assistants

Sensitive privacy fixtures should not be sent to external coding assistants without explicit authorization.

537. Repository Protection

Sensitive fixtures should be excluded from Git repositories.

538. Git History

Accidentally committed secrets remain present in Git history even after deletion.

Credential rotation and history remediation may be required.

539. Secret Remediation

If a secret enters Git history, removing the file alone is insufficient.

540. Branch Protection

Protected branches should require appropriate review and CI checks.

541. Pull Request Review

Reviewers should inspect privacy-impacting code changes.

542. Dependency Locking

Dependencies should be pinned or locked according to project dependency-management policy.

543. Dependency Vulnerabilities

Privacy components are subject to dependency vulnerability scanning.

544. License Compliance

Open-source privacy libraries must comply with project licensing requirements.

545. Open-Source Principle

Aegis Vuldris should prefer open-source privacy detection components when they provide adequate capability and security.

546. External Data Services

Paid or closed external services are not required for the core privacy architecture.

547. Zero-Cost Principle

The core privacy subsystem should be implementable using open-source software and self-hosted infrastructure.

548. Optional External Services

External services may be supported as optional integrations, but must not be required for baseline privacy testing.

549. Local Development

Local development should work with synthetic fixtures and local evaluators.

550. Docker Development

Dockerized services must preserve privacy isolation.

551. PostgreSQL Development

Development database instances should use synthetic data.

552. Database Reset

Development database reset procedures must not accidentally target production databases.

553. Environment Separation

Production database connection strings must never be committed to source control.

554. Test Database

Automated tests should use isolated test databases.

555. Test Database Cleanup

Test data should be cleaned up automatically where practical.

556. Migration Safety

Database migrations involving sensitive evidence must be reviewed for:

data exposure,
retention,
rollback,
access controls.
557. Schema Design

Sensitive tables should include appropriate ownership and classification fields.

558. Foreign Keys

Evidence and findings should have explicit relationships to:

project,
target,
execution,
test.
559. Ownership Enforcement

Database relationships do not replace application-level authorization.

560. Row-Level Security

PostgreSQL row-level security may be considered for additional defense in depth.

It is not the sole authorization mechanism.

561. Database Views

Views may be used to expose redacted representations.

562. Redacted Views

Redacted database views can reduce accidental access to raw evidence.

563. Sensitive Columns

Sensitive columns should be clearly identified in schema documentation.

564. Database Logging

Database query logging must be configured to avoid sensitive payload leakage.

565. Connection Pooling

Connection pooling must not cause credential or tenant-context confusion.

566. Transaction Isolation

Privacy-sensitive operations should use appropriate transaction isolation.

567. Race Conditions

Authorization checks and sensitive retrieval must be designed to avoid time-of-check/time-of-use vulnerabilities.

568. Transactional Authorization

Where necessary, authorization and retrieval should occur within a safe transaction boundary.

569. Deletion Transactions

Deletion operations should ensure related records are handled consistently.

570. Cascading Deletes

Cascading deletes must be explicit and reviewed to avoid unintended data loss.

571. Soft Delete

Soft deletion does not necessarily satisfy data-removal requirements.

572. Hard Delete

Hard deletion should be available where policy requires it.

573. Cache Invalidation

Deleted sensitive data must be removed from caches where applicable.

574. Search Index Invalidation

Deleted sensitive documents must be removed from search indexes where applicable.

575. Vector Index Invalidation

Deleted sensitive vectors must be removed from vector indexes where applicable.

576. Derived Artifact Cleanup

Summaries or reports derived from deleted sensitive data should be evaluated for deletion.

577. Backup Awareness

Deletion workflows should document backup behavior.

578. Retention Scheduler

Retention cleanup should be implemented as a controlled background job.

579. Retention Job Authorization

Retention workers require only the privileges necessary to perform cleanup.

580. Retention Job Monitoring

Failed retention jobs should be monitored.

581. Retention Job Idempotency

Retention jobs should be safe to retry.

582. Retention Audit

Retention operations should produce minimal audit metadata.

583. Legal Hold

If a future deployment requires legal holds, retention deletion must respect explicitly configured holds.

584. Legal Hold Scope

Legal holds should be narrowly scoped and auditable.

585. Privacy Exception Handling

Privacy exceptions must not silently disable deletion or access controls.

586. Data Export Review

Before exporting sensitive evidence, the system should determine:

actor,
scope,
classification,
destination,
format,
retention.
587. Export Watermarking

Future exports may include classification/warning metadata.

588. Export Expiration

Export links should expire where possible.

589. Export Encryption

Sensitive exported files should use appropriate encryption where required.

590. Export Audit

Exports should be auditable.

591. Report Access

Reports must enforce the same project/tenant isolation as findings.

592. Report Redaction

Reports should default to redacted evidence.

593. Report Profiles

Future reports may support:

executive summary,
technical report,
compliance report,
raw evidence report.

Raw evidence reports require elevated authorization.

594. Privacy Report Content

Privacy reports should emphasize:

affected boundary,
data class,
exposure,
exploitability,
evidence,
remediation.
595. Report Safety

Reports must not expose more data than required to communicate the finding.

596. Privacy Finding Deduplication

Duplicate leakage observations should be correlated while preserving meaningful scope differences.

597. Root Cause Grouping

Multiple privacy findings may share a common root cause.

598. Risk Aggregation

Risk aggregation must not double-count the same underlying exposure merely because multiple canaries were used.

599. Canary Count

A larger number of leaked canaries may provide stronger evidence of systemic leakage but does not necessarily represent independent vulnerabilities.

600. Privacy Risk Evidence

Risk scoring should receive structured privacy signals rather than raw sensitive content.

601. Risk Engine Isolation

The risk engine must not require unrestricted access to sensitive evidence.

602. Report Generation Isolation

Report generation should consume the minimum evidence required.

603. Evidence Access by Reference

Components should use evidence references rather than copying raw content.

604. Data Duplication

Sensitive content should not be copied across services unnecessarily.

605. Data Lineage

The system should maintain enough lineage to determine where sensitive evidence originated.

606. Lineage Metadata

Lineage may include:

source,
execution,
test,
transformation,
storage location.
607. Lineage Security

Lineage metadata may itself reveal sensitive relationships.

It requires access control.

608. Privacy Test Provenance

Test results should identify the provenance of privacy inputs and evaluators.

609. Reproducibility Metadata

Reproducibility metadata should not require storing unnecessary sensitive content.

610. Environment Fingerprint

Where useful, record a safe environment fingerprint rather than secrets or raw configuration.

611. Configuration Snapshot

Configuration snapshots must redact secrets.

612. Model Configuration

Model identifiers and safe configuration metadata may be recorded.

Sensitive prompts or credentials must not be included by default.

613. Target Configuration

Target configuration should record only what is necessary for reproducibility.

614. Target Secrets

Target credentials must not be included in test result snapshots.

615. Privacy Test Determinism

Tests should distinguish deterministic setup from nondeterministic target behavior.

616. Randomized Testing

Randomized privacy tests must retain enough metadata to reproduce failures where practical.

617. Seed Protection

Seeds should not contain sensitive values.

618. Random Test Data

Generated synthetic personal data should not accidentally correspond to real people.

619. Synthetic Data Quality

Synthetic data should be clearly identifiable as synthetic where practical.

620. Synthetic Email Domains

Synthetic emails should prefer reserved/non-deliverable domains where appropriate.

621. Synthetic Credentials

Synthetic credentials must be invalid and non-privileged.

622. Synthetic Identifiers

Synthetic identifiers should avoid accidental collision with real organizational identifiers where practical.

623. Synthetic Documents

Synthetic documents should use fictional entities.

624. Synthetic Customer Records

Synthetic customer records should not use real customer information.

625. Synthetic Employee Records

Synthetic employee records should not use real employee information.

626. Synthetic Secrets

Synthetic secrets should be unmistakable and non-functional.

627. Canary Naming

Canary names should identify test purpose without revealing real data.

628. Canary Entropy

Canary identifiers should be sufficiently unique to avoid accidental collisions.

629. Canary Discoverability

Canaries should be recognizable to the evaluator but not trivially mistaken for production secrets.

630. Privacy Test Cleanup

Synthetic data should be removed after testing unless retention is required for reproducibility.

631. Cleanup Verification

Cleanup should verify expected deletion where feasible.

632. Cleanup Reporting

Cleanup status should appear as metadata, not as raw sensitive content.

633. Privacy Test Errors

Errors should distinguish:

setup failure,
target failure,
detection failure,
authorization evaluation failure,
evidence failure,
cleanup failure.
634. Error Classification

Privacy errors must not automatically become security findings unless the error itself demonstrates a vulnerability.

635. Detection Failure

If detection fails, the test result should be marked appropriately rather than silently passing.

636. Evidence Failure

If evidence cannot be safely stored, the system should preserve minimal metadata and mark the result accordingly.

637. External Evaluator Failure

If an external evaluator fails, no sensitive fallback transfer should occur automatically.

638. Fallback Policy

Fallback evaluators must respect the same privacy policy.

639. Provider Failover

Failover to another external provider must not occur without explicit policy authorization.

640. Privacy Policy Enforcement Before Transfer

The system must evaluate whether data may be transferred before sending it to an evaluator.

641. Data Transfer Denial

Denied transfer should be visible to the user as a controlled failure or skipped evaluator.

642. Privacy Test Coverage

The privacy suite should measure coverage across:

data classes,
boundaries,
user roles,
projects,
tenants,
target capabilities,
attack families.
643. Coverage Limitations

Coverage metrics do not prove absence of privacy vulnerabilities.

644. Boundary Coverage

A privacy test suite should identify which trust boundaries have been exercised.

645. Role Coverage

Where authorized, privacy tests should cover relevant roles.

646. Tenant Coverage

Where applicable, tests should cover tenant boundaries.

647. Data-Class Coverage

Tests should cover important sensitive-data classes.

648. RAG Coverage

RAG privacy testing should cover authorization and lifecycle conditions.

649. Agent Coverage

Agent privacy testing should cover:

memory,
tools,
retrieval,
state,
cross-session behavior.
650. Prompt Coverage

Prompt privacy testing should cover:

system prompts,
developer prompts,
tool instructions,
retrieved instructions.
651. Output Coverage

Privacy detection should consider direct and transformed outputs.

652. Multi-Turn Coverage

Privacy tests should support bounded multi-turn leakage attempts.

653. Long-Term Leakage

Where authorized, tests may evaluate persistence over bounded sessions.

654. Persistence Boundary

Long-term tests must not create indefinite state or uncontrolled storage.

655. State Reset

Test environments should provide a reliable state-reset mechanism where supported.

656. Reset Verification

State reset should be verified before declaring isolation successful.

657. Isolation Oracle

The test harness should define expected isolation behavior explicitly.

658. Oracle Data

The expected sensitive value should be stored securely and minimally.

659. Oracle Security

The target must not receive the evaluator's protected expected-output oracle unless the test explicitly requires it.

660. Oracle Leakage

The evaluator must not leak its expected canary value through prompts or logs unnecessarily.

661. Blind Evaluation

Where possible, evaluator components should not receive information that would bias the evaluation.

662. Privacy Test Blinding

Some privacy tests may benefit from blinded evaluators to reduce confirmation bias.

663. Independent Verification

High-impact privacy findings should support independent verification.

664. Verification Isolation

Verification should use controlled synthetic data where possible.

665. Reproduction Safety

Reproduction should not require collecting additional unnecessary sensitive information.

666. Proof-of-Concept Limits

Privacy proof-of-concepts should demonstrate the minimum required disclosure.

667. No Mass Extraction

The framework must not encourage unrestricted extraction of sensitive information.

668. Query Limits

Privacy attacks must respect bounded query limits.

669. Token Limits

Token budgets apply to privacy tests.

670. Response Limits

Response-size budgets apply to privacy tests.

671. Network Limits

Network request budgets apply to privacy tests.

672. Tool Limits

Tool-call budgets apply to privacy tests.

673. Time Limits

Execution duration budgets apply to privacy tests.

674. Concurrency Limits

Concurrency budgets apply to privacy tests.

675. Fairness

One privacy test must not starve unrelated project executions.

676. Quotas

Projects may have privacy-test quotas.

677. Quota Enforcement

Quota enforcement must be application-level.

678. Budget Enforcement

Budget enforcement must not rely on model compliance.

679. Cancellation Authority

Authorized users may cancel privacy tests subject to job controls.

680. Cancellation Audit

Cancellation events should be auditable.

681. Retry Policy

Retries must not create uncontrolled repeated disclosure.

682. Retry Classification

A retry should preserve the same privacy context and authorization.

683. Backoff

Retries should use bounded backoff.

684. Idempotent Cleanup

Cleanup must remain safe under repeated execution.

685. Privacy Test Scheduling

Scheduled privacy tests must retain the original authorization scope and policy.

686. Expired Authorization

A scheduled test must not run after its authorization scope has expired.

687. Scheduled Secrets

Scheduled jobs must retrieve credentials through secure mechanisms rather than persisting plaintext secrets in job definitions.

688. Job Ownership

Scheduled privacy jobs must remain associated with an authorized project.

689. Job Cancellation

Project removal or authorization revocation should prevent future privacy jobs from running.

690. Authorization Revocation

Revoking access should prevent further retrieval of protected evidence.

691. Existing Jobs

Existing jobs should revalidate authorization before execution.

692. Existing Evidence

Existing evidence remains protected after authorization changes.

693. Role Changes

Role changes should immediately affect sensitive evidence access where possible.

694. Tenant Changes

Tenant membership changes must affect access immediately or according to explicitly documented propagation guarantees.

695. Project Removal

Deleting a project should trigger defined handling for:

findings,
evidence,
reports,
jobs,
test fixtures,
canaries.
696. Target Removal

Removing a target should trigger defined handling for associated sensitive data.

697. Evidence Orphans

Orphaned evidence must not remain accessible indefinitely.

698. Referential Integrity

Database constraints should reduce accidental orphan creation.

699. Orphan Cleanup

Background cleanup may remove orphaned sensitive artifacts.

700. Privacy Architecture Testing

The architecture must be validated through automated tests before implementation is considered complete.

701. Required Security Invariants

At minimum:

Sensitive evidence cannot be accessed without authorization.
Project isolation cannot be bypassed through identifiers.
Tenant isolation cannot be bypassed through identifiers.
Raw evidence is more restricted than redacted evidence.
Synthetic canaries cannot grant real access.
External evaluators cannot receive restricted data without explicit authorization.
Model output cannot modify privacy policy.
Model output cannot bypass evidence authorization.
Sensitive values are not written to ordinary logs.
Cleanup cannot silently fail without visibility.
Retention policy is enforced independently of model behavior.
Deletion does not depend on model cooperation.
Privacy tests have bounded extraction limits.
Cross-context testing requires explicit authorization.
Privacy findings remain project-scoped.
Knowledge of an opaque identifier does not grant authorization.
Secrets are not stored in source control.
Test credentials are non-production whenever possible.
Sensitive data is minimized in reports and exports.
Privacy controls fail closed where security-sensitive decisions cannot be evaluated safely.
702. Implementation Boundary

This ADR defines architecture, not implementation details.

Concrete libraries and classes may change provided they preserve the architectural invariants.

703. Initial Implementation Order

Implementation should proceed in this order:

privacy data classification types,
sensitive-data detector interfaces,
synthetic canary generator,
privacy test metadata,
deterministic privacy evaluators,
authorization-aware evaluation,
evidence classification/redaction integration,
privacy finding creation,
retention/deletion integration,
cross-context privacy tests,
RAG privacy tests,
agent/memory privacy tests,
optional semantic evaluators,
privacy regression suite,
reporting integration,
dashboard integration.
704. Initial MVP

The first MVP should support:

synthetic canaries,
exact matching,
sensitive-data classification,
direct disclosure testing,
cross-context leakage testing,
redacted evidence,
privacy findings,
basic retention,
project isolation,
deterministic evaluation.
705. Later Capabilities

Later versions may add:

semantic privacy detection,
memorization testing,
inference testing,
reconstruction testing,
vector-store testing,
advanced RAG privacy,
agent memory testing,
side-channel analysis,
privacy analytics.
706. Architecture Alternatives Considered
Alternative A: Treat privacy as ordinary safety testing

Rejected because privacy requires authorization-aware data handling and evidence protection.

Alternative B: Store all raw responses

Rejected because it violates data minimization.

Alternative C: Use only regex detection

Rejected because semantic and contextual leakage may not match known patterns.

Alternative D: Use only an LLM judge

Rejected because the evaluator itself may be manipulated and deterministic evidence is stronger for canaries.

Alternative E: Use real personal data for realistic testing

Rejected as the default because synthetic data can provide safer controlled testing.

Alternative F: Trust the model to protect private data

Rejected because application-level security boundaries must be independent.

707. Consequences

Positive consequences:

stronger privacy testing,
safer evidence handling,
reproducible canary-based tests,
clearer privacy findings,
reduced sensitive-data retention,
better project/tenant isolation,
safer external evaluator integration,
improved regression coverage.

Costs:

additional classification logic,
additional storage metadata,
redaction complexity,
stricter evidence authorization,
more complex test setup,
additional cleanup requirements,
more extensive privacy regression testing.
708. Operational Consequences

Operators must understand:

what sensitive data may be collected,
how it is classified,
how long it is retained,
who may access it,
whether external evaluators are permitted,
how deletion works.
709. Developer Consequences

Developers must:

prefer synthetic data,
avoid sensitive logging,
enforce authorization,
use safe parsers,
preserve classification,
respect evidence policies,
write privacy regression tests.
710. User Consequences

Users receive:

privacy-specific findings,
evidence appropriate to their authorization,
clearer exposure scope,
reproducible canary-based results,
safer reports.
711. Security Consequences

This architecture reduces the probability that Aegis Vuldris itself becomes a secondary privacy breach while testing another system.

712. Performance Consequences

Classification and detection introduce processing overhead.

The implementation should use bounded processing and efficient deterministic detectors first.

713. Storage Consequences

Classification and evidence lineage increase metadata requirements.

Data minimization should offset unnecessary raw-response storage.

714. Complexity Consequences

Privacy is intentionally treated as a first-class subsystem rather than a collection of ad hoc regexes.

715. Governance Consequences

Changes to sensitive-data handling require security/privacy review.

716. Open-Source Consequences

The architecture remains compatible with open-source and self-hosted deployments.

717. Vendor Independence

The core privacy subsystem must not depend on a single external model provider.

718. Local-First Principle

Local deterministic evaluation is preferred for sensitive data.

719. Cloud Optionality

Cloud evaluators may be optional.

720. Deployment Portability

The privacy subsystem should work in local development, Docker, and production environments.

721. Configuration Portability

Privacy policies must be portable through versioned configuration.

722. Environment-Specific Restrictions

Production may apply stricter restrictions than development.

723. Policy Documentation

Environment-specific differences must be documented.

724. Secure Default Review

Every new privacy-related feature must define its secure default.

725. Feature Acceptance Criteria

A privacy feature is not complete until:

authorization is defined,
data classification is defined,
logging is reviewed,
evidence handling is reviewed,
retention is defined,
deletion behavior is defined,
tests exist.
726. Test Acceptance Criteria

A privacy test is complete when:

metadata is defined,
scope is explicit,
preconditions are defined,
evaluator is defined,
evidence policy is defined,
cleanup is defined,
budgets are defined.
727. Evaluator Acceptance Criteria

An evaluator is complete when:

inputs are defined,
outputs are defined,
failure behavior is defined,
versioning is defined,
sensitive-data handling is defined,
tests exist.
728. Detector Acceptance Criteria

A detector is complete when:

supported data classes are documented,
false-positive cases are tested,
false-negative limitations are documented,
performance limits are defined,
output classification is defined.
729. Evidence Acceptance Criteria

Privacy evidence support is complete when:

redaction works,
classification works,
authorization works,
retention works,
deletion works,
audit events exist.
730. Report Acceptance Criteria

Privacy reporting is complete when:

raw sensitive data is restricted,
redacted output is safe,
classifications are displayed,
evidence references work,
exports respect authorization.
731. Regression Acceptance Criteria

Privacy regression is complete when:

known leakage tests exist,
known fixed cases exist,
baselines are versioned,
CI can detect regressions.
732. Security Review Acceptance Criteria

The architecture is ready for implementation when the defined security invariants can be converted into automated tests.

733. Implementation Gate

No privacy subsystem implementation should be considered production-ready until the following are implemented and tested:

authorization-aware privacy evaluation,
sensitive-data classification,
canary generation,
evidence minimization,
redaction,
retention,
deletion,
project isolation,
secure logging,
external evaluator policy,
regression tests.
734. Final Decision

Aegis Vuldris will implement privacy and data-leakage testing as a dedicated, authorization-aware, evidence-producing security subsystem.

The subsystem will prioritize:

synthetic data,
canary-based detection,
deterministic evaluation,
data minimization,
explicit classification,
controlled evidence,
strong isolation,
bounded testing,
reproducibility,
defense in depth.

Privacy protection applies both to the target being tested and to Aegis Vuldris's own handling of test data.

735. Final Security Principle

Aegis Vuldris must never create a privacy vulnerability in order to test for a privacy vulnerability.

736. Status

Accepted.

Implementation may proceed subject to the architecture and security invariants defined in this ADR.
