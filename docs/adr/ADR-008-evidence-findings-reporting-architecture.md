# ADR-008: Evidence, Findings, and Reporting Architecture

- **Status:** Accepted
- **Date:** 2026-09-10
- **Decision Owners:** Aegis Vuldris Maintainers
- **Scope:** Evidence collection, evidence normalization, finding creation, finding lifecycle, risk metadata, report generation, report export, report integrity, evidence retention, and security controls surrounding assessment results

---

## 1. Context

Aegis Vuldris is a security testing and evaluation platform for AI systems.

Security tests executed by Aegis Vuldris do not produce a single boolean result. A test may generate prompts, model responses, intermediate evaluation results, metadata, tool interactions, policy classifications, reproduction information, and evaluator decisions.

The platform therefore requires a dedicated architecture for transforming raw test execution data into trustworthy, structured, reviewable, and exportable security results.

The architecture must preserve the distinction between:

1. Raw execution data
2. Collected evidence
3. Normalized evidence
4. Evaluation results
5. Findings
6. Risk metadata
7. Reports
8. Audit records

These objects have different security properties, retention requirements, authorization requirements, and intended consumers.

Aegis Vuldris must not treat a model response, evaluator output, or generated report as inherently trustworthy merely because it was produced by an AI system.

Evidence may contain attacker-controlled content.

Model output may contain malicious instructions, fabricated claims, sensitive information, structured-output attacks, prompt-injection payloads, or content designed to manipulate the evaluator.

Evaluator output may also be influenced by malicious model responses.

Reports may contain sensitive security findings and therefore must be protected as security-sensitive artifacts.

The architecture must support reproducibility while avoiding unnecessary retention of secrets and sensitive personal information.

---

## 2. Problem Statement

Without a dedicated evidence and reporting architecture, Aegis Vuldris could encounter:

- Loss of security-test evidence
- Inability to reproduce findings
- Confusion between test failures and vulnerabilities
- Inconsistent severity classification
- Duplicate findings
- Evidence tampering
- Sensitive data exposure
- Unsafe report rendering
- Cross-project data leakage
- Unauthorized report downloads
- Untrusted evaluator output being treated as authoritative
- Report injection
- Log injection
- Excessive evidence retention
- Unbounded evidence storage
- Inconsistent report formats
- Loss of provider/model/version metadata
- Inability to audit finding lifecycle changes
- Inconsistent findings between executions
- Accidental exposure of raw model responses
- Failure to distinguish observed behavior from inferred risk

Aegis Vuldris therefore requires a first-class architecture for evidence, findings, and reports.

---

## 3. Decision

Aegis Vuldris will implement a layered evidence-to-report architecture in which each stage has a clearly defined responsibility.

The canonical flow will be:

```text
Target
  |
  v
Test Definition
  |
  v
Test Execution
  |
  v
Execution Events
  |
  v
Raw Evidence
  |
  v
Normalized Evidence
  |
  v
Evaluation
  |
  v
Finding Candidate
  |
  v
Validated Finding
  |
  v
Risk Metadata
  |
  v
Report Artifact

The system will maintain explicit separation between execution evidence, evaluator conclusions, findings, and generated reports.

No generated report will become the authoritative source of truth.

The authoritative security state will remain the structured finding and evidence records stored by Aegis Vuldris.

Reports will be derived artifacts.

4. Architectural Principles

The following principles govern this decision.

4.1 Evidence First

Security findings must be backed by evidence whenever technically possible.

4.2 Findings Are Conclusions

A finding is an evaluated security conclusion, not merely a raw model response.

4.3 Reports Are Derived Artifacts

Reports are generated from stored assessment data and must not become the canonical security record.

4.4 Untrusted-by-Default

Model responses, prompts, tool outputs, evaluator outputs, uploaded artifacts, and external provider responses are untrusted data.

4.5 Reproducibility

A finding should contain enough metadata to understand how it was produced and, when safe and possible, reproduce the behavior.

4.6 Minimize Sensitive Data

Aegis Vuldris will retain only the evidence necessary to support security testing, debugging, reproduction, auditing, and reporting.

4.7 Authorization Before Disclosure

Evidence and findings must be subject to the same project/resource authorization boundaries as the assessment that produced them.

4.8 Integrity

Evidence and findings must be protected against unauthorized modification and accidental corruption.

4.9 Immutable Historical Meaning

Changes to a finding must preserve its historical lifecycle through audit records rather than silently overwriting security history.

4.10 Defense in Depth

The reporting layer must not be treated as a security boundary by itself.

5. Evidence Model

Evidence represents observable information collected during an assessment.

Evidence may include:

Input prompt
Model response
System metadata
Model metadata
Target metadata
Provider metadata
Request metadata
Response metadata
Tool invocation metadata
Tool result metadata
Evaluation result
Attack sequence
Multi-turn conversation
HTTP metadata
Error information
Timing information
Token usage
Reproduction instructions
Relevant configuration
Test definition
Test case identifier
Execution identifier

Evidence must have a stable relationship to the execution that produced it.

6. Evidence Identity

Every evidence record must have a unique identifier.

The evidence identifier must not depend solely on user-provided values.

A preferred model is:

evidence_id = UUID

Evidence should additionally retain:

assessment_id
execution_id
test_case_id
target_id
created_at

Where applicable, evidence may also contain:

parent_evidence_id
sequence_number
turn_number
event_type

This permits evidence to represent both single-turn and multi-turn executions.

7. Evidence Types

Aegis Vuldris will use explicit evidence types rather than storing all information as an unstructured blob.

Examples include:

prompt
response
conversation
tool_call
tool_result
http_request
http_response
evaluation
metadata
error
reproduction
configuration
trace

The set may expand as the testing engine evolves.

Evidence type values must be controlled by the application.

Arbitrary user-supplied type names must not silently create new security semantics.

8. Raw Evidence

Raw evidence represents the closest available representation of what occurred during an execution.

Raw evidence may be required for:

Debugging
Reproduction
Security investigation
Dispute resolution
Evaluator verification
Provider troubleshooting

Raw evidence must be treated as untrusted data.

Raw evidence must never be rendered as executable content.

9. Normalized Evidence

Normalized evidence is a structured representation used by downstream evaluation and reporting systems.

Normalization may include:

Canonical field names
Normalized timestamps
Provider-independent metadata
Structured request/response relationships
Explicit turn numbering
Explicit tool interaction relationships
Normalized error categories

Normalization must not silently modify the semantic content of security evidence.

If normalization changes, removes, truncates, or redacts content, the transformation should be represented in metadata.

10. Evidence Chain

Aegis Vuldris should maintain relationships between evidence records.

Example:

Test Case
   |
   +-- Prompt
   |
   +-- Model Response
   |
   +-- Evaluation
   |
   +-- Finding

For multi-turn testing:

Execution
 |
 +-- Turn 1
 |    +-- Prompt
 |    +-- Response
 |
 +-- Turn 2
 |    +-- Prompt
 |    +-- Response
 |
 +-- Turn 3
      +-- Prompt
      +-- Response

This structure allows investigators to understand how a finding developed.

11. Evidence Ordering

Evidence generated during an execution must preserve ordering where ordering affects interpretation.

Aegis Vuldris should use an explicit sequence field when required.

For example:

sequence_number = 1
sequence_number = 2
sequence_number = 3

Timestamps alone must not be relied upon for ordering because multiple events may occur within the same timestamp resolution.

12. Evidence Content Security

Evidence can contain attacker-controlled strings.

Therefore:

Evidence must be stored as data.
Evidence must not be interpreted as executable code.
Evidence must not be used directly as SQL.
Evidence must not be inserted into shell commands.
Evidence must not be trusted as HTML.
Evidence must not be interpreted as templates.
Evidence must not be trusted as configuration.
Evidence must not be used to construct file paths without validation.
Evidence must not be used as authorization input.
13. Evidence and Secrets

Aegis Vuldris must avoid storing provider secrets inside evidence.

Examples of secrets that must not appear in persisted evidence include:

API keys
Access tokens
Session tokens
Passwords
Private keys
Credential headers
Authorization cookies
Database credentials

If provider responses accidentally contain secrets, the system should support redaction or controlled handling before persistence or report generation.

14. Evidence Redaction

Evidence redaction must be explicit.

Aegis Vuldris should support redaction of known sensitive fields such as:

authorization
cookie
set-cookie
api_key
access_token
refresh_token
password
secret
private_key

Redaction should not silently destroy the original evidence when preservation is required for authorized forensic purposes.

Where appropriate, the architecture should retain:

original evidence
redacted representation
redaction metadata

with strict access controls around the original representation.

15. Evidence Classification

Evidence should have a data sensitivity classification.

Suggested classifications:

public
internal
sensitive
restricted

Security assessment evidence will normally be treated as at least sensitive.

Evidence containing credentials, personal data, confidential customer data, or high-impact security information may require restricted handling.

16. Evidence Access

Evidence access must be authorization-controlled.

A user who can access a project should not automatically receive unrestricted access to every internal evidence representation.

The authorization system defined by ADR-006 remains authoritative.

Evidence access must enforce:

authentication
+
authorization
+
resource ownership/isolation
17. Project Isolation

Evidence must remain associated with the project/tenant/resource boundary from which it originated.

Queries must not allow a user to retrieve evidence belonging to another project.

Resource identifiers supplied by clients must never be treated as proof of authorization.

The backend must independently determine whether the authenticated principal can access the referenced evidence.

18. Finding Model

A finding represents a validated security observation or conclusion.

A finding should contain at least:

finding_id
assessment_id
execution_id
test_case_id
target_id
title
category
severity
status
summary
description
impact
evidence_references
reproduction
recommendation
created_at
updated_at

Additional fields may include:

confidence
risk_score
first_seen_at
last_seen_at
fingerprint
owner
resolution
tags
compliance_mappings
19. Finding Is Not Equivalent to Test Failure

A failed test does not automatically mean a vulnerability exists.

Examples:

Test failure
!=
Security finding

A test may fail because:

The provider was unavailable
A timeout occurred
The evaluator failed
The test was incorrectly configured
The target lacked a required capability
A rate limit was reached

Therefore Aegis Vuldris must distinguish:

execution outcome
evaluation outcome
finding outcome
20. Execution Outcome

Execution outcome describes whether the test execution itself completed successfully.

Example states:

queued
running
completed
failed
cancelled
timed_out

These states are independent from finding severity.

21. Evaluation Outcome

Evaluation outcome describes how the observed behavior was interpreted.

Example states:

not_evaluated
pass
fail
inconclusive
error

Evaluation errors must not automatically become security findings.

22. Finding Status

Finding lifecycle should use explicit states.

Suggested states:

open
acknowledged
in_progress
resolved
accepted_risk
false_positive
duplicate
reopened

The exact lifecycle may evolve.

Status changes must be auditable.

23. Finding Severity

Aegis Vuldris will use a controlled severity scale.

Initial levels:

informational
low
medium
high
critical

Severity represents security impact rather than confidence.

Confidence must therefore be represented independently.

24. Severity and Confidence

The architecture must distinguish:

severity

from:

confidence

Example:

severity = critical
confidence = low

This can represent a potentially severe issue for which the available evidence is incomplete.

Likewise:

severity = low
confidence = high

may represent a clearly verified but low-impact issue.

25. Risk Score

Aegis Vuldris may calculate a risk score using multiple dimensions.

The score must not be represented as a simplistic:

security_percentage

Instead, risk may incorporate:

severity
confidence
exploitability
impact
exposure
reproducibility
scope
affected assets

The exact scoring algorithm will be defined separately from this ADR when sufficient empirical requirements exist.

26. Evidence References in Findings

Findings must reference evidence rather than duplicating large evidence payloads whenever practical.

For example:

finding
  |
  +-- evidence_id: ...
  +-- evidence_id: ...
  +-- evidence_id: ...

This reduces duplication and preserves a canonical evidence record.

Reports may include selected evidence excerpts derived from these references.

27. Finding Fingerprints

Aegis Vuldris should support finding fingerprints for deduplication and regression analysis.

A fingerprint may incorporate normalized properties such as:

target identity
test category
test case
vulnerability class
normalized finding signature

Raw model output should not be the only fingerprint input because minor response changes should not necessarily create entirely new findings.

Fingerprints must not expose secrets.

28. Finding Deduplication

Duplicate findings should be identified where technically possible.

However, deduplication must not merge unrelated findings merely because they share a category.

Aegis Vuldris should prefer conservative deduplication.

If confidence in duplication is insufficient, the system should retain separate findings.

29. Finding Relationships

Findings may have relationships such as:

duplicate_of
related_to
regression_of
supersedes
derived_from

These relationships must not overwrite historical records.

30. Regression Findings

Aegis Vuldris should support tracking findings across assessments.

A regression may be represented as:

previously_resolved
        |
        v
new_execution
        |
        v
same_fingerprint_detected
        |
        v
reopened/regression

Regression detection must remain independent from report formatting.

31. Finding Reproduction

A finding should contain reproducibility information where safe and practical.

Reproduction data may include:

Test case identifier
Prompt or prompt reference
Required target configuration
Model/provider information
Relevant parameters
Number of turns
Tool configuration
Evaluation conditions
Execution metadata

Secrets must never be included in reproduction instructions.

32. Reproducibility Metadata

Reproducibility should capture relevant versions such as:

Aegis Vuldris version
test suite version
test case version
adapter version
target/provider identifier
model identifier
model version
evaluation engine version
configuration version

Where exact provider/model version information is unavailable, the system should record that it was unavailable rather than inventing it.

33. Finding Description

Finding descriptions must distinguish observed facts from interpretation.

A recommended structure is:

Observed Behavior
Security Interpretation
Impact
Evidence
Recommendation

This reduces the risk of presenting evaluator assumptions as directly observed facts.

34. Evaluator Output

Evaluator output is untrusted.

This includes:

Rule-engine output
Classifier output
LLM judge output
Provider-provided evaluation output
External evaluator output

Evaluator output must be validated before being persisted into security-sensitive fields.

35. LLM Judge Security

An LLM judge must not be considered an authoritative security boundary.

The target model may attempt to manipulate the judge through its response.

Therefore:

target output
        |
        v
evaluation boundary
        |
        v
validated evaluator result

The evaluator must be isolated from target instructions where practical.

Evaluator prompts must not automatically inherit arbitrary target-provided instructions.

36. Structured Evaluator Output

Where LLM evaluators are used, Aegis Vuldris should prefer structured output.

For example:

{
  "decision": "fail",
  "confidence": 0.92,
  "rationale": "...",
  "categories": ["prompt_injection"]
}

The backend must validate:

Required fields
Types
Enumerated values
Numeric ranges
Maximum lengths
Allowed categories

Malformed evaluator output must not crash the reporting pipeline.

37. Evaluator Rationale

Evaluator rationale is evidence about the evaluation process, not necessarily proof of the vulnerability.

Therefore rationale should be retained separately from observed target behavior.

Reports should distinguish:

Observed Evidence

from:

Evaluator Interpretation
38. Report Architecture

Reports are derived artifacts generated from:

assessment
+
executions
+
evidence
+
findings
+
risk metadata

The report generator must not independently query unauthorized data.

The report generation request must execute within the authenticated user's authorization context or an explicitly authorized service context.

39. Report Types

Aegis Vuldris should support:

JSON
CSV
HTML
PDF

Additional formats may be added later.

JSON will be treated as the primary machine-readable representation.

HTML and PDF will be optimized for human review.

CSV will support tabular export and downstream analysis.

40. Canonical Report Data

The canonical report data model should be independent from presentation formats.

For example:

AssessmentReport
    metadata
    summary
    findings
    evidence_references
    risk_summary
    recommendations
    compliance

Each renderer consumes this canonical representation.

41. JSON Reporting

JSON reports should contain structured fields rather than flattened prose wherever practical.

JSON output should be deterministic where possible.

Example:

{
  "report_version": "1",
  "assessment": {},
  "summary": {},
  "findings": [],
  "recommendations": []
}

The schema should be versioned.

42. CSV Reporting

CSV exports should be intended for tabular analysis.

Potential columns include:

finding_id
title
category
severity
confidence
status
target_id
assessment_id
test_case_id
created_at
updated_at

Large evidence blobs should not automatically be duplicated into every CSV row.

43. HTML Reporting

HTML reports must treat all model-generated and user-generated content as untrusted.

The renderer must escape dynamic content.

The system must not directly interpolate model output into raw HTML.

The renderer must protect against:

Cross-site scripting
HTML injection
Attribute injection
Script injection
Malicious URLs
Template injection
44. HTML Escaping

Dynamic content must be contextually escaped.

For example:

HTML text context
HTML attribute context
URL context

must not be treated as interchangeable.

Aegis Vuldris should use established safe templating/rendering libraries rather than constructing HTML through unsafe string concatenation.

45. Report PDF Security

PDF reports may contain attacker-controlled text.

The PDF generation process must:

Treat content as data
Escape or safely encode dynamic content
Avoid arbitrary code execution
Limit resource consumption
Avoid unsafe external resource loading
Avoid embedding unnecessary secrets

PDF generation must be isolated from the main API process where practical.

46. External Resources in Reports

Reports should not automatically load remote content.

Examples of risky resources include:

remote images
remote CSS
remote scripts
external URLs
tracking pixels

The preferred default is self-contained report generation.

47. Report Injection

User-controlled or model-controlled strings must never become:

HTML markup
JavaScript
template syntax
shell commands
SQL
filesystem paths

without explicit validation and safe encoding.

This includes:

Finding titles
Finding descriptions
Model responses
Prompt text
Tool output
Tags
Assessment names
Target names
48. Report File Names

Generated report filenames must not be directly controlled by arbitrary user input.

A safe naming strategy should use:

aegis-report-<report_id>.<extension>

or a sanitized bounded name.

Path traversal sequences must be rejected or neutralized.

49. Report Storage

Generated reports may be stored temporarily or persistently depending on requirements.

Persistent report records should contain:

report_id
assessment_id
format
status
created_at
created_by
storage_reference
content_hash

Reports must remain subject to authorization.

50. Report Content Hash

Generated report artifacts should support integrity verification.

A cryptographic hash such as SHA-256 may be stored:

content_hash

This allows the system to detect unexpected modification.

The hash is an integrity mechanism, not an authorization mechanism.

51. Report Versioning

Reports should contain:

report_version
generator_version
schema_version

This allows consumers to understand which report structure and rendering implementation produced the artifact.

52. Report Determinism

Where possible, identical canonical input should produce equivalent report output.

Non-deterministic metadata such as generation timestamps may be isolated from content hashing if exact byte-level determinism is required.

53. Report Generation Status

Report generation should have explicit lifecycle states:

queued
running
completed
failed
cancelled

The report generator must not leave indefinitely running jobs without resource controls.

54. Large Reports

Large assessments may generate substantial reports.

The system must avoid loading arbitrarily large evidence collections into memory.

Preferred strategies include:

Pagination
Streaming
Chunked processing
Bounded queries
Incremental rendering
Temporary files
Explicit maximum report sizes
55. Resource Exhaustion

Report generation is a potential denial-of-service vector.

Controls should include:

Maximum evidence count per report
Maximum report size
Maximum execution duration
Maximum concurrent report jobs
Request rate limiting
Pagination
Memory limits
Disk quotas
Cancellation
56. Evidence Retention

Evidence retention must be intentional.

Retention may depend on:

assessment lifecycle
project policy
data sensitivity
storage capacity
legal requirements
security requirements

The architecture should support future configurable retention policies.

57. Evidence Deletion

Deletion must respect authorization and lifecycle requirements.

Deleting an assessment should not accidentally leave publicly accessible evidence artifacts.

Conversely, deleting evidence required for audit or compliance must be prevented or explicitly controlled where policy requires retention.

58. Cascading Deletion

Database relationships must define deletion behavior explicitly.

The system must not rely on accidental database behavior.

Before deletion, the application must consider:

assessment
execution
evidence
finding
report
audit record

and their dependencies.

59. Evidence and Finding Integrity

Security-sensitive evidence and findings must not be silently modified.

Mutable fields such as status and ownership should be updated through controlled application operations.

Important historical events should be captured through audit logging.

60. Finding Audit History

Changes to findings should record:

actor
timestamp
finding_id
old_value
new_value
reason

At minimum, audit history should cover:

Severity changes
Status changes
Assignment changes
Resolution changes
Risk acceptance
False-positive classification
Reopening
Deletion/retention actions where applicable
61. Audit Log Separation

Audit logs are not the same as evidence.

Evidence answers:

What happened during the assessment?

Audit records answer:

Who changed or accessed security-sensitive state?

These must remain conceptually separate.

62. Evidence Access Auditing

Access to highly sensitive evidence may require audit logging.

Examples:

Raw evidence retrieval
Restricted evidence access
Report download
Evidence export
Finding export
Administrative deletion

The exact audit policy will be refined with the observability architecture.

63. Report Authorization

Before generating or downloading a report, Aegis Vuldris must verify authorization against the underlying assessment/project.

The existence of a report identifier must never grant access.

The backend must enforce authorization independently of the frontend.

64. Object-Level Authorization

Aegis Vuldris must prevent insecure direct object references.

Unsafe pattern:

GET /reports/{report_id}

where the existence of report_id is treated as sufficient authorization.

Required pattern:

authenticated principal
        |
        v
authorization check
        |
        v
report
        |
        v
underlying assessment/project authorization
65. Export Authorization

Exports are security-sensitive because they create copies of data.

Export operations must therefore enforce:

Authentication
Resource authorization
Format validation
Size limits
Rate limits
Audit logging where required
66. Evidence Pagination

Evidence retrieval APIs must be paginated when collections can grow large.

Clients must not be able to request unlimited evidence in a single response.

Pagination parameters must have bounded maximum values.

67. Finding Pagination

Finding lists should also be paginated.

Example:

page
page_size
cursor

The exact API mechanism will be defined by the API architecture and implementation.

68. Filtering and Sorting

Finding queries may support:

severity
category
status
target
assessment
date
confidence

Filter values must be validated against controlled fields.

Sort fields must be allowlisted.

Client-provided arbitrary SQL fragments must never be accepted.

69. Search

Full-text search may eventually be supported across findings and evidence.

Search must be implemented using safe parameterized mechanisms.

Search input must not become executable SQL, template code, shell commands, or report markup.

70. Sensitive Search Results

Search results may themselves reveal sensitive information.

Authorization must apply before search results are returned.

The system must avoid leaking the existence of inaccessible findings through:

Counts
Error messages
Timing
Search suggestions
Autocomplete
Aggregations

where practical.

71. Risk Aggregation

Assessment-level risk summaries may aggregate findings.

Example dimensions:

critical_count
high_count
medium_count
low_count
informational_count

Additional metrics may include:

open_findings
resolved_findings
regressions
high_confidence_findings
affected_targets

These are summaries and must not replace the underlying findings.

72. Risk Score Transparency

If Aegis Vuldris exposes a calculated risk score, the report should provide enough metadata to understand its meaning.

The system should avoid presenting an opaque numerical score as an absolute truth.

Risk scoring methodology must be versioned.

73. Compliance Mapping

Findings may later map to compliance or security frameworks.

A finding may contain references such as:

framework
control_id
mapping_version

Compliance mapping must not alter the underlying security observation.

74. Recommendation Model

Recommendations should be associated with findings where possible.

Recommendations may contain:

title
description
priority
affected_component
reference

Model-generated recommendations must be clearly distinguishable from verified remediation requirements where necessary.

75. Recommendation Safety

Recommendations must not automatically execute remediation.

Aegis Vuldris is a testing and evaluation platform.

Generating a recommendation is separate from applying a configuration or code change.

Any future remediation automation must have its own authorization and security architecture.

76. Evidence and Model Privacy

Aegis Vuldris may test models that process confidential information.

Therefore evidence storage must support privacy-preserving controls.

Potential controls include:

Redaction
Encryption at rest
Encryption in transit
Access control
Retention limits
Restricted exports
Secret detection
PII detection
Configurable evidence capture
77. Evidence Capture Configuration

Tests may need configurable evidence capture.

Possible modes:

minimal
standard
debug
forensic

The exact modes will be defined during implementation.

A minimal mode may capture only information necessary for reporting.

A debug mode may capture additional provider metadata.

A forensic mode may capture more detailed execution information subject to explicit authorization.

78. Capture Defaults

Secure defaults should minimize unnecessary sensitive data collection.

The default configuration should not capture credentials or secrets.

Debug/forensic capture should require deliberate configuration.

79. Evidence Encryption

Sensitive evidence should be protected using encryption at rest where supported by the deployment environment.

Application-level encryption may be considered for particularly sensitive fields.

Encryption keys must never be stored alongside encrypted data without appropriate protection.

80. Database Storage

Structured evidence metadata and findings should be stored in PostgreSQL as defined by ADR-003.

Large evidence payloads may require separate storage depending on size and operational requirements.

The architecture must preserve a stable reference between metadata and payload storage.

81. Large Evidence Storage

Very large artifacts should not necessarily be stored directly in database rows.

Potential future storage options include:

filesystem
object storage
encrypted blob storage

The storage implementation must preserve:

authorization
integrity
retention
deletion
auditability
82. Evidence Object References

External evidence storage references must not be treated as public URLs.

Access should be mediated by authorization.

If signed URLs are introduced, they must be:

Short-lived
Scoped
Non-guessable
Revocable where possible
Bound to authorized resources
83. Evidence Integrity Hashing

Evidence payloads may be associated with cryptographic hashes.

For example:

sha256(payload)

Hashes provide integrity evidence.

They do not prove that the original evidence itself was truthful.

84. Evidence Provenance

Where practical, evidence should identify its source.

Example:

source_type
source_provider
source_adapter
source_execution

This enables investigators to distinguish:

target-generated content
provider metadata
Aegis-generated evaluation
Aegis-generated normalization
85. Provenance Must Not Imply Trust

A source label does not make content trustworthy.

For example:

source = target_model

means the target produced the content.

It does not mean the content is accurate or safe.

86. Timestamps

Aegis Vuldris should store timestamps in UTC.

Important timestamps include:

created_at
started_at
completed_at
updated_at
first_seen_at
last_seen_at

Client-provided timestamps must not overwrite authoritative server timestamps without explicit justification.

87. Clock Skew

Provider timestamps and client timestamps may differ from server time.

When external timestamps are retained, they should be clearly distinguished from Aegis server timestamps.

88. Time-Based Evidence

Evidence involving expiration, authentication, rate limits, or time-sensitive behavior should retain relevant timing metadata where practical.

This can improve reproducibility.

89. Correlation Identifiers

Evidence should be traceable across execution layers.

Relevant identifiers may include:

assessment_id
execution_id
test_case_id
evidence_id
finding_id
report_id
trace_id

These identifiers must not themselves grant authorization.

90. Report Correlation

A report should be traceable back to:

report
  |
  +-- assessment
       |
       +-- executions
            |
            +-- evidence
                 |
                 +-- findings

This relationship should remain navigable for authorized investigators.

91. Report Snapshots

A generated report should represent a snapshot of the underlying assessment data at generation time.

If findings change later, an existing report should not silently change.

A new report should be generated when a current snapshot is required.

92. Report Snapshot Metadata

Reports should retain:

generated_at
source_assessment_version
finding_set_version
report_schema_version
generator_version

This makes historical reports interpretable.

93. Report Reproducibility

Where possible, a report should be regenerable from the same canonical source data and versions.

The system should record the report generator version.

94. Report Storage Lifecycle

Generated reports may be:

temporary
persistent
archived
deleted

The lifecycle must be explicit.

Temporary reports should not remain indefinitely.

95. Download Streaming

Large report downloads should use streaming or bounded file transfer where practical.

The API must avoid unnecessarily loading entire large files into memory.

96. Content-Disposition Safety

Download filenames must be sanitized.

User-controlled values must not be allowed to inject:

CRLF
path separators
control characters
unexpected extensions

into response headers.

97. MIME Types

Report responses must use explicit expected MIME types.

Examples:

application/json
text/csv
text/html
application/pdf

The application must not trust a user-provided MIME type to determine the response behavior.

98. Report Content-Type Protection

Generated HTML reports must not accidentally be served as executable application content in unrelated contexts.

Download behavior and inline viewing should be deliberate.

Security headers should be applied consistently with the broader API/security architecture.

99. Browser Security

HTML reports should use browser security controls where appropriate.

Potential controls include:

Content Security Policy
X-Content-Type-Options
Referrer Policy
Frame restrictions
Safe link handling

The exact header policy will be finalized under production security architecture.

100. Untrusted Links

Model-generated evidence may contain URLs.

Reports must treat these as untrusted.

The renderer should consider:

Dangerous schemes
javascript: URLs
Data URLs
Unexpected redirects
Tracking links

Only safe URL schemes should be allowed.

101. Report Rendering Isolation

If report rendering uses complex libraries, rendering should be isolated from sensitive application processes where practical.

A compromised rendering dependency should not automatically compromise the primary API process.

102. Template Security

Templates must be application-controlled.

Users, target models, evaluators, and test cases must not be able to create arbitrary templates.

Dynamic content must be inserted only through safe templating mechanisms.

103. Report Internationalization

Reports may eventually support multiple languages.

Localized strings must come from trusted application resources.

User/model content must remain dynamic data and must not become localization templates.

104. Unicode and Encoding

Reports must correctly handle Unicode.

The system should explicitly define encoding expectations.

CSV generation should account for spreadsheet compatibility without sacrificing security.

105. CSV Injection

CSV output may be opened in spreadsheet applications.

Cells beginning with characters interpreted as formulas may create security risks.

Aegis Vuldris should consider safe CSV escaping/neutralization for untrusted values beginning with characters such as:

=
+
-
@

The implementation must balance compatibility with preserving evidence.

106. JSON Injection

JSON must be generated through a proper serializer.

The system must not construct JSON by string concatenation.

This protects against malformed output and escaping issues.

107. PDF Resource Controls

PDF generation must enforce resource limits.

Potential controls include:

maximum pages
maximum text length
maximum image count
maximum image size
maximum generation time
108. Image Evidence

If screenshots or images become evidence, the same trust model applies.

Images may contain:

Sensitive information
Embedded metadata
Malicious payloads
Unexpected formats

Image processing should therefore be isolated and resource-limited.

109. File Evidence

Uploaded or captured files must be treated as untrusted.

The evidence pipeline must not execute uploaded content.

File type detection should not rely solely on user-provided extensions.

110. Archive Evidence

If archive files are supported, extraction must protect against:

Path traversal
Zip bombs
Excessive nesting
Excessive file counts
Oversized extracted content
111. Evidence Normalization Failures

If evidence cannot be normalized safely, the system should preserve the raw failure information where possible and mark normalization as failed.

It must not silently invent normalized values.

112. Partial Evidence

An execution may produce partial evidence.

Examples:

request succeeded
response missing
evaluation failed

Partial evidence should remain representable.

The system should not fabricate missing response data.

113. Incomplete Findings

A finding may be marked inconclusive if evidence is insufficient.

Possible state:

evaluation = inconclusive
finding = not_created

or, where investigation requires it:

finding.status = open
finding.confidence = low

The exact policy belongs to the evaluation engine.

114. Error Evidence

Errors may be retained as evidence when they are relevant to the security assessment.

Errors must be normalized so that sensitive internals are not exposed unnecessarily.

Examples of data that may require redaction:

stack traces
filesystem paths
credentials
internal hostnames
database URLs
tokens
115. Report Error Handling

Report generation failures should return safe errors.

Internal stack traces must not be returned to untrusted clients.

Detailed diagnostics should remain in protected logs.

116. Report Retry Behavior

Report generation may be retried for transient failures.

Retries must be bounded.

Repeated failures must not create unlimited report jobs or duplicate persistent artifacts.

117. Idempotency

Where report generation requests can be retried, the system should support idempotency where practical.

Duplicate requests should not unexpectedly create an unbounded number of identical persistent reports.

118. Evidence Processing Idempotency

Evidence normalization and finding derivation should be designed so that retrying processing does not create uncontrolled duplicates.

Stable identifiers and fingerprints should be used where appropriate.

119. Transaction Boundaries

Database state changes involving findings and related metadata should use explicit transaction boundaries.

A partially committed finding must not reference nonexistent required records.

ADR-003 remains authoritative for transaction and database architecture.

120. Finding Creation Transaction

Where practical, creation of a finding and its required evidence references should occur atomically.

If the operation fails, the system should avoid leaving a misleading partial finding.

121. Report Record and Artifact Consistency

If a persistent report record points to an artifact, the system must ensure that the reference is valid.

Orphaned report records should be detected and handled.

122. Orphaned Evidence

The system should detect evidence that is no longer referenced by an active execution or retained finding where appropriate.

Cleanup must respect retention policies.

123. Orphan Cleanup

Cleanup processes must be:

Authorized
Auditable
Bounded
Safe against deleting referenced data
Safe against path traversal
Resistant to race conditions
124. Concurrency

Multiple workers may process evidence concurrently.

The architecture must prevent:

Duplicate finding creation
Conflicting status updates
Corrupt report artifacts
Lost updates

Database constraints and transactional mechanisms should be used where appropriate.

125. Finding Update Conflicts

Concurrent finding updates must not silently overwrite important changes.

Optimistic concurrency or equivalent mechanisms may be introduced where necessary.

126. Evidence Ordering Under Concurrency

Parallel execution must preserve logical relationships between evidence records.

Sequence identifiers and execution identifiers should be used rather than relying solely on insertion order.

127. Report Generation Concurrency

Concurrent report generation must be bounded.

A user must not be able to exhaust worker resources by requesting unlimited reports.

128. Report Cache

Report caching may be introduced for expensive reports.

Caches must be scoped by:

authorized resource
report parameters
source data version
report version

A cache hit must never bypass authorization.

129. Cache Invalidation

If underlying findings change, stale reports must not be presented as current without explicit indication.

The system should use source-data versioning or equivalent invalidation mechanisms.

130. Sensitive Cache Data

Report caches may contain sensitive assessment data.

Cache storage therefore requires appropriate access controls and retention.

131. Evidence Compression

Large textual evidence may be compressed where appropriate.

Compression must not weaken integrity or authorization.

132. Evidence Encryption in Transit

Evidence must be protected during transport using the application's secure communication architecture.

Provider communication must follow ADR-007 and the broader security baseline.

133. Evidence Across Trust Boundaries

Evidence crossing trust boundaries must be treated as untrusted.

This includes:

target -> Aegis
provider -> Aegis
worker -> API
database -> API
storage -> API
API -> report renderer

Validation must occur at the receiving boundary.

134. Evidence From External Providers

External provider responses may be malformed or malicious.

The adapter layer must normalize provider responses before the evidence layer consumes them.

ADR-007 remains authoritative for provider integration.

135. Tool Interaction Evidence

Agent/tool testing may generate evidence such as:

tool name
arguments
result
authorization context
timestamp
sequence

Tool arguments and results remain untrusted.

Sensitive tool credentials must never be persisted as evidence.

136. Tool Evidence Redaction

Tool interaction evidence should support redaction of:

Authentication tokens
Cookies
Credentials
Secrets
Sensitive request headers
Sensitive response headers
137. Prompt Injection Evidence

Prompt injection payloads are expected security-test data.

They must be preserved when required for reproduction.

However, their presence must not cause the evidence renderer to execute them.

138. Jailbreak Evidence

Jailbreak prompts and model responses must be treated as untrusted evidence.

Reports may display them as quoted test content.

They must never become report instructions.

139. Privacy Leakage Evidence

Privacy/data-leakage findings may contain sensitive information by definition.

Such findings may require stronger access controls and redaction than ordinary findings.

140. PII Detection

Aegis Vuldris may eventually detect personally identifiable information in evidence.

PII detection should be considered an assistive classification mechanism, not a guarantee of complete detection.

141. Secret Detection

Aegis Vuldris may scan evidence for probable secrets.

Secret detection must not itself leak discovered secrets through logs, findings, metrics, or error messages.

142. Secret Detection Results

Secret findings should indicate that a secret was detected without unnecessarily reproducing the secret.

For example:

secret_type = api_key
exposure = detected
value = redacted
143. Evidence Truncation

Evidence may require bounded storage.

If content is truncated, metadata should indicate:

truncated = true
original_size
stored_size

Truncation must not silently make evidence appear complete.

144. Maximum Evidence Size

The implementation must define maximum sizes for:

Prompt
Response
Tool result
Error
Evidence record
Report
Uploaded artifact

These limits protect against resource exhaustion.

145. Oversized Evidence

When evidence exceeds configured limits, the system should fail safely.

Possible behavior:

reject
truncate with explicit metadata
store externally

The behavior must be deterministic and documented.

146. Evidence Sampling

Sampling may be used for very large or repetitive execution data.

Sampling must not silently omit evidence needed to substantiate a security finding.

147. Evidence Retention and Reports

A report may outlive the underlying evidence depending on policy.

If so, the report must clearly represent whether detailed evidence remains available.

The system must not imply that an evidence reference is retrievable if the referenced evidence has been deleted.

148. Report Evidence Excerpts

Reports may include bounded evidence excerpts.

Excerpts should:

Preserve context
Indicate truncation
Escape dynamic content
Avoid secrets
Link to full evidence only when authorized
149. Evidence Diffing

Aegis Vuldris may eventually support comparison between executions.

Diffs may compare:

prompts
responses
findings
severity
evaluation
tool interactions

Diff output must preserve the distinction between actual observations and derived comparison results.

150. Finding Diffing

Finding comparison should use stable identifiers and fingerprints.

It should support identifying:

new findings
resolved findings
persistent findings
regressions
severity changes
confidence changes
151. Historical Findings

Historical findings should not be rewritten merely because a newer evaluation changes its interpretation.

Historical assessment results should remain reproducible.

A new assessment or finding revision should represent the new state.

152. Finding Re-evaluation

A finding may be re-evaluated using a newer evaluator.

The system should record:

previous evaluator version
new evaluator version
previous decision
new decision

This prevents silent historical reinterpretation.

153. Report Regeneration

Regenerating a report with a newer renderer should create a distinguishable artifact/version.

Historical reports should not silently mutate.

154. Report Metadata

Every report should contain enough metadata to identify:

Aegis Vuldris version
report schema
assessment
target(s)
generation timestamp
generator version
155. Report Summary

A report summary should provide high-level information such as:

assessment status
targets tested
test count
execution count
finding count
severity distribution
risk summary

The summary must be derived from canonical data.

156. Report Findings

The report finding section should include, as appropriate:

title
category
severity
confidence
description
impact
evidence
reproduction
recommendation
status
157. Report Recommendations

Recommendations should be organized so that users can understand:

what is wrong
why it matters
what should be changed
how to verify remediation
158. Report Executive Summary

A human-readable report may include an executive summary.

The executive summary must be generated from structured assessment data.

If AI-generated prose is used, it must not invent findings that are absent from canonical records.

159. AI-Generated Report Narratives

If Aegis Vuldris eventually uses an LLM to summarize findings, the generated narrative must be considered untrusted derived content.

The report pipeline must ensure:

canonical findings
        |
        v
bounded summary input
        |
        v
AI-generated narrative
        |
        v
validation
        |
        v
report

The AI summary must not become the authoritative finding source.

160. Summary Hallucination Protection

AI-generated summaries must not introduce unsupported:

Findings
Severity levels
CVEs
Compliance claims
Affected assets
Remediation actions

unless those values are explicitly supported by canonical assessment data.

161. Report Validation

Before a report becomes downloadable, the system should validate:

Required metadata
Finding references
Schema validity
Format validity
Artifact existence
Size limits
Integrity metadata
162. JSON Schema Validation

JSON reports should be validated against a versioned schema.

Schema validation should occur before the artifact is marked complete.

163. CSV Validation

CSV output should be validated for:

Correct column count
Correct encoding
Correct escaping
Formula-injection protections
Expected newline behavior
164. HTML Validation

HTML output should be validated for:

Safe escaping
Expected document structure
Absence of executable untrusted content
Safe links
Size limits
165. PDF Validation

PDF output should be validated for:

Successful generation
Expected file type
Size limits
Page limits
Artifact integrity
166. Report Artifact Integrity

The report artifact should be hashed after successful generation.

The stored hash must correspond to the artifact that users receive.

167. Artifact Replacement

Replacing a generated report artifact must be controlled.

An unexpected file overwrite must not silently change historical security reports.

168. Temporary Files

Temporary report and evidence files must be stored in controlled directories.

Temporary paths must not be constructed directly from untrusted input.

169. Temporary File Cleanup

Cleanup must be bounded and safe.

Failures to clean temporary artifacts should be observable without exposing sensitive contents.

170. Filesystem Permissions

Where filesystem storage is used, application processes should have the minimum permissions required.

Evidence directories should not be unnecessarily executable.

171. Path Traversal Protection

All evidence/report filesystem paths must be generated by the application.

User input must never directly determine an unrestricted filesystem path.

172. Symlink Safety

Filesystem operations should consider symbolic links and other filesystem redirection mechanisms.

The application must not unintentionally read or overwrite arbitrary files through malicious links.

173. Report Archive Handling

If reports are packaged into archives, archive creation must use safe filenames and bounded content.

Archive extraction, if ever supported, must follow the same protections described for file evidence.

174. Evidence Export Packaging

Multi-file evidence exports should have deterministic structure where possible.

For example:

assessment/
  metadata.json
  findings.json
  evidence/
  report/

Archive names must not be controlled directly by untrusted content.

175. Export Manifest

Large evidence exports may include a manifest containing:

artifact_id
type
size
hash
created_at

This supports integrity and inventory tracking.

176. Export Limits

Evidence export must enforce:

Maximum number of records
Maximum total size
Maximum processing time
Authorization
Rate limits
177. Export Cancellation

Long-running exports should support cancellation where practical.

Cancellation should safely release resources and clean temporary artifacts.

178. Background Processing

Large report generation and exports should use the execution/job architecture defined by ADR-005.

The API should not perform arbitrarily expensive generation synchronously.

179. Job Authorization

A report job must retain sufficient authorization context to ensure the worker cannot access resources outside the originally authorized scope.

Workers must not trust arbitrary resource identifiers stored in job payloads.

180. Job Payload Security

Job payloads should contain identifiers and bounded configuration rather than large sensitive evidence blobs.

Workers should retrieve authorized data through controlled mechanisms.

181. Job Result Security

Generated artifacts must remain associated with the correct project/assessment.

A job must not be able to publish a report under another resource.

182. Worker Isolation

Report workers should have restricted permissions.

They should not require:

Database superuser privileges
Host administrator privileges
Unrestricted filesystem access
Unrestricted outbound network access
183. Report Renderer Network Access

Report rendering should not require unrestricted outbound network access.

Where possible, outbound network access should be disabled.

This reduces SSRF and data-exfiltration risk.

184. External URL Fetching

If report rendering ever supports fetching external resources, it must use the same SSRF protections defined for model target integration and security boundaries.

185. Dependency Security

Report-generation dependencies must be treated as security-sensitive.

They must be:

Version controlled
Scanned
Updated
Tested
Pinned/locked according to project dependency policy
186. Supply Chain Risk

PDF, HTML, CSV, serialization, templating, and document-processing dependencies may process attacker-controlled content.

Dependency vulnerabilities may therefore directly affect Aegis Vuldris security.

187. Safe Serialization

Aegis Vuldris should use safe serialization formats and libraries.

Unsafe deserialization of attacker-controlled objects must not be permitted.

188. Pickle and Similar Formats

Untrusted evidence must never be deserialized using unsafe object serialization mechanisms such as unrestricted Python pickle loading.

189. Schema Evolution

Evidence, finding, and report schemas will evolve.

Schemas should use explicit versions where compatibility matters.

Migration logic must be deliberate.

190. Backward Compatibility

Existing findings and reports should remain readable when practical.

Breaking changes must be versioned and documented.

191. Finding Schema Version

Where schema evolution is expected, findings may include a schema version.

This prevents newer application versions from incorrectly interpreting older data.

192. Report Schema Version

Machine-readable reports must include a schema version.

Consumers should be able to determine how to parse the report.

193. API Compatibility

Evidence/finding/report API contracts must follow ADR-004.

Breaking changes should be versioned or otherwise explicitly managed.

194. Database Migrations

Changes to evidence/finding/report persistence models must use Alembic migrations as defined by ADR-003.

Schema changes must not be performed through ad hoc production SQL.

195. Database Constraints

Where appropriate, PostgreSQL constraints should enforce:

Required fields
Valid relationships
Uniqueness
Foreign keys
Valid lifecycle values

Application validation remains necessary.

196. Application Validation

Client input must be validated before persistence.

Validation must include:

Types
Lengths
Enumerations
Required fields
Relationships
Resource ownership
197. Trust in Database Data

Database records are authoritative application state, but data must still be handled defensively.

Corrupt or inconsistent data must not cause unsafe report generation.

198. Defensive Report Generation

Report generation should fail safely if required records are inconsistent.

It should not:

Execute arbitrary data
Follow arbitrary filesystem paths
Fetch arbitrary URLs
Expose secrets
Bypass authorization
199. Error Classification

Evidence/report errors should be categorized.

Examples:

validation_error
authorization_error
not_found
storage_error
render_error
serialization_error
resource_limit
internal_error
200. Error Disclosure

External clients should receive safe error messages.

Internal diagnostics should remain protected.

201. Logging

The reporting subsystem should log operational events such as:

report generation started
report generation completed
report generation failed
export requested
export completed
evidence processing failed

Logs must not contain raw sensitive evidence by default.

202. Log Injection

Untrusted evidence values must not be written into logs without safe handling.

Newline/control-character injection must be considered.

203. Metrics

The reporting system may expose metrics such as:

report_jobs_total
report_jobs_failed
report_generation_duration
evidence_processing_duration
report_size_bytes
finding_creation_total

Metrics must not contain sensitive evidence content.

204. Observability Separation

Detailed audit and observability architecture will be defined in ADR-009.

This ADR defines only the requirements relevant to evidence, findings, and reports.

205. Security Event Handling

Security-relevant failures in the evidence/report pipeline should be observable.

Examples:

Unauthorized evidence access
Repeated export failures
Report artifact integrity mismatch
Unexpected path errors
Suspicious report generation activity
206. Access to Raw Evidence

Raw evidence should require the same or stronger authorization than normalized summaries where necessary.

A report may expose a redacted excerpt while raw evidence remains restricted.

207. Least Privilege

Components should receive only the permissions required to perform their tasks.

For example:

API
Worker
Database
Evidence storage
Report renderer

should not all share unrestricted permissions.

208. Separation of Duties

Where practical, sensitive administrative operations such as:

bulk deletion
retention override
restricted evidence access
risk acceptance

should be auditable and potentially require elevated permissions.

209. Risk Acceptance

Risk acceptance should never delete the underlying evidence.

Instead:

finding.status = accepted_risk

while the original evidence remains available according to retention policy.

210. False Positive Classification

A false-positive finding should retain its evidence and evaluation history.

Changing the status must not erase the historical observation.

211. Finding Resolution

Resolved findings should preserve:

resolution
resolved_at
resolved_by

and relevant historical state.

212. Finding Reopening

If a resolved finding reappears, the system should be able to represent the regression rather than silently changing the old assessment.

213. Assessment Completion

An assessment may be considered complete only after relevant test executions and processing jobs have reached terminal states according to the execution architecture.

214. Report Readiness

A report should not be marked complete while required finding/evaluation processing is still pending unless the report is explicitly identified as partial.

215. Partial Reports

Aegis Vuldris may support partial/interim reports.

Such reports must clearly indicate:

partial = true

and identify incomplete components.

216. Final Reports

Final reports should be generated only when the assessment has reached the required completion state.

The exact completion policy will be defined by the assessment/test orchestration architecture.

217. Report Status and Assessment Status

Report status and assessment status are independent.

For example:

assessment = completed
report = failed

is valid.

Likewise:

assessment = running
report = partial

may be valid if explicitly supported.

218. Evidence Processing Status

Evidence processing may also have its own state.

Examples:

pending
processing
processed
failed

This prevents execution state from being overloaded.

219. Finding Derivation

Finding creation should be traceable to the evaluation that produced the finding candidate.

This enables investigation into why a finding exists.

220. Finding Provenance

A finding should be able to identify:

derived_from_execution
derived_from_evaluation
derived_from_evidence

This improves traceability.

221. Manual Findings

Aegis Vuldris may eventually support manually created findings.

Manual findings should still use the same structured model.

They should indicate:

source = manual

rather than pretending to be automated findings.

222. Automated Findings

Automated findings should identify their source.

For example:

source = automated_test
source = evaluator
source = regression
223. Finding Source Integrity

Clients must not be able to claim privileged finding sources through arbitrary request fields.

Source classification must be controlled by the backend.

224. Finding Severity Overrides

If authorized users can manually override severity, the original automated severity should remain auditable.

Example:

automated_severity = high
current_severity = critical

with an audit event explaining the change.

225. Finding Confidence Overrides

The same principle applies to confidence changes.

Historical evaluator confidence should not be silently destroyed.

226. Evidence Mutation

Raw evidence should generally be immutable after creation.

If correction is required, the architecture should prefer:

new corrected representation
+
audit history

rather than silent modification.

227. Evidence Corrections

Corrections may be necessary for:

Redaction
Provider metadata correction
Parsing correction
Normalization bug fixes

Corrections must preserve provenance.

228. Redaction Audit

Sensitive evidence redaction should be auditable where appropriate.

Audit information may include:

actor
timestamp
reason
fields affected

The audit record must not reproduce the redacted secret.

229. Data Minimization

Aegis Vuldris should not store:

unnecessary full network captures
unnecessary provider headers
unnecessary credentials
unnecessary personal data

merely because they are technically available.

230. Configurable Evidence Policies

Projects may eventually define policies such as:

retain raw responses = true
retain tool results = false
redact secrets = true
redact PII = true
retention_days = 30

Policy enforcement must occur server-side.

231. Policy Changes

Changing evidence retention or capture policies must not retroactively imply that historical evidence was captured differently.

Policy versioning may be used.

232. Evidence Policy Metadata

Executions may record the effective evidence policy identifier/version.

This improves reproducibility.

233. Evidence and Compliance

If assessment evidence is used for compliance purposes, the report should identify relevant evidence and finding relationships.

Compliance claims must remain bounded by actual assessment evidence.

234. Compliance Evidence Integrity

Evidence used to substantiate compliance results should receive appropriate integrity and retention controls.

235. Compliance Mapping Versioning

Compliance mappings must be versioned.

A report generated under one mapping version must remain interpretable later.

236. Report References

Reports may contain references to:

Finding identifiers
Evidence identifiers
Test identifiers
Target identifiers
Compliance controls

References should be stable within the application's versioning model.

237. External References

External URLs included in findings or recommendations must be treated as untrusted data.

The report renderer must safely encode them.

238. CVE/CWE-like Identifiers

Future finding classifications may use standardized vulnerability identifiers.

Identifiers must be validated.

The platform must not invent authoritative external identifiers.

239. Taxonomy

Aegis Vuldris should maintain controlled categories such as:

safety
jailbreak
prompt_injection
privacy
data_leakage
rag_security
agent_security
tool_security
robustness
compliance

The taxonomy may evolve independently from the report format.

240. Category Versioning

If taxonomy changes materially, findings should retain enough metadata to interpret historical categories.

241. Finding Tags

Tags may be supported for organization.

Tags are untrusted input and must have:

Maximum length
Allowed character policy
Maximum count
Authorization controls
242. Finding Ownership

Findings may eventually be assigned to users or teams.

Assignment must be authorized.

An arbitrary user identifier must not be accepted as proof of permission.

243. Finding Comments

If comments are supported, they are untrusted user-generated content.

Comments must be escaped in reports and protected from injection.

244. Comment Auditability

Changes to security-relevant comments may be audited depending on implementation requirements.

245. Finding Attachments

If finding attachments are supported, they must follow the same untrusted-file controls as evidence.

246. Report Attachments

Reports should include only authorized attachments.

External file references must not become arbitrary filesystem paths.

247. API Pagination Limits

The API must enforce server-side maximum page sizes.

Clients cannot bypass limits by requesting extremely large values.

248. API Rate Limits

Evidence and report endpoints may require stronger rate limits than ordinary metadata endpoints because they can expose large amounts of sensitive data.

249. Abuse Prevention

The system should detect or limit suspicious repeated export/download behavior where operationally appropriate.

This is complementary to authentication and authorization, not a replacement.

250. Tenant Isolation

For multi-tenant deployments, evidence and findings must include tenant/project boundaries where applicable.

Cross-tenant queries must be impossible through normal application operations.

251. Tenant-Scoped Reports

Report generation must inherit tenant scope from the authorized assessment.

A client must not be able to request a report containing multiple tenants unless explicitly authorized.

252. Administrative Access

Administrative access to evidence must remain auditable.

Administrators should not automatically bypass all data-protection controls without explicit policy.

253. Break-Glass Access

If emergency access is supported, it should require:

Explicit authorization
Strong audit trail
Limited duration
Reason
Scope restriction
254. Database Backups

Evidence and findings stored in PostgreSQL become part of database backup requirements.

Backups must receive security protections appropriate to the sensitivity of the stored data.

255. Object Storage Backups

If evidence artifacts use object storage, backup and retention policies must be aligned with database metadata.

256. Deletion Consistency

Deleting metadata without deleting associated sensitive artifacts can create data-retention violations.

Deleting artifacts without metadata can create broken references.

Deletion workflows must handle both sides.

257. Disaster Recovery

Recovery procedures must preserve relationships among:

assessment
execution
evidence
finding
report

Restored data should remain internally consistent.

258. Backup Encryption

Sensitive evidence backups should use encryption appropriate to the deployment.

259. Backup Access

Backup access must be restricted to authorized operational roles.

260. Report Disaster Recovery

Persistent reports must either be recoverable from canonical assessment data or included in appropriate artifact backup policies.

261. Evidence Recovery

Recovery procedures should allow authorized operators to determine whether evidence is:

available
corrupted
missing
expired
redacted
262. Integrity Verification

Integrity verification jobs may periodically check stored evidence/report hashes where practical.

Unexpected mismatches should be observable and investigated.

263. Finding Integrity Verification

Finding relationships should be validated against database constraints and application consistency checks.

264. Data Corruption Handling

Corrupted evidence must not be silently treated as valid.

The system should mark or quarantine corrupted artifacts.

265. Quarantine

If malicious or corrupted evidence artifacts are detected, they may be isolated from normal rendering.

Quarantine operations must remain authorized and auditable.

266. Malicious Content Rendering

Aegis Vuldris must assume that some evidence intentionally attempts to exploit report viewers.

Examples:

<script>
<img onerror=...>
javascript:
template payloads
CSV formulas
malicious filenames

All must be handled as untrusted data.

267. Security Testing of Reports

Report generation itself must be security tested.

Test cases should include:

XSS payloads
HTML injection
CSV injection
Path traversal
Malicious filenames
Unicode edge cases
Oversized content
Broken encodings
Malicious URLs
Template payloads
PDF resource exhaustion
268. Security Testing of Evidence

Evidence APIs should be tested against:

Unauthorized access
IDOR
Excessive page sizes
Injection
Oversized payloads
Malformed structured data
Cross-project access
Secret leakage
269. Security Testing of Findings

Finding APIs should be tested against:

Unauthorized creation
Unauthorized modification
Severity escalation
Status manipulation
Cross-project access
Duplicate creation
Invalid relationships
Injection
Audit bypass
270. Security Testing of Exports

Export endpoints should be tested against:

Unauthorized exports
Cross-project exports
Oversized exports
Export job abuse
Path traversal
Filename injection
Sensitive data leakage
271. Report Security Regression Suite

Aegis Vuldris should maintain automated regression tests for previously discovered report/evidence vulnerabilities.

272. Evidence Contract Tests

Evidence schemas should have contract tests ensuring:

Required fields remain available
Enumerations remain valid
Relationships remain valid
Serialization remains compatible
273. Finding Contract Tests

Finding models should have tests for:

Creation
Validation
Lifecycle transitions
Authorization
Serialization
Deduplication
Audit history
274. Report Contract Tests

Each report renderer should have tests for:

same canonical data
        |
        v
expected report structure
275. Golden Reports

The project may use version-controlled golden fixtures for deterministic report output.

Golden files must not contain real secrets or private customer data.

276. Test Data

Security tests must use synthetic or authorized test data.

Real secrets should never be committed to test fixtures.

277. Sensitive Test Fixtures

Fixtures containing simulated secrets should be clearly synthetic.

Examples:

TEST_API_KEY_123
TEST_SECRET_VALUE
278. Report Fuzz Testing

Report renderers should eventually be fuzz-tested with:

Random Unicode
Control characters
Long strings
Nested structures
Malformed URLs
Injection payloads
279. Evidence Fuzz Testing

Evidence ingestion should be tested with malformed provider/model responses.

280. Property-Based Testing

Property-based testing may be introduced for serialization, normalization, escaping, and schema validation.

281. Performance Testing

The reporting pipeline should be performance-tested with realistic large assessments.

Metrics should include:

generation time
memory usage
CPU usage
artifact size
database load
282. Load Testing

Load tests should cover concurrent:

Evidence retrieval
Finding queries
Report generation
Export jobs
283. Resource Isolation

A large report must not starve normal API traffic.

Worker pools, concurrency limits, or separate processes should be used as appropriate.

284. Failure Isolation

A report renderer failure must not corrupt the underlying assessment data.

285. Transactional Safety

Report generation should read a consistent view of canonical data where practical.

It must not partially modify findings merely because rendering failed.

286. Report Generation Read Model

A report may use a dedicated read model or canonical aggregation layer to simplify consistent generation.

The implementation should avoid duplicating business logic across every renderer.

287. Single Canonical Representation

All report formats should derive from the same canonical report representation.

For example:

Assessment
   |
   v
Canonical Report Model
   |
   +----> JSON
   +----> CSV
   +----> HTML
   +----> PDF
288. Renderer Independence

Each renderer should be independently testable.

A failure in PDF rendering must not affect JSON generation.

289. Renderer Security Boundary

Renderers should receive only the data required to produce the requested format.

290. Renderer Input Validation

Canonical report data should be validated before entering a renderer.

291. Report Format Selection

Report format must be allowlisted.

Example:

json
csv
html
pdf

Arbitrary format strings must not trigger dynamic code loading.

292. Plugin-Based Reporters

Dynamic report-renderer plugins are deferred.

The initial implementation will use built-in, controlled renderers.

293. Custom Templates

Custom user templates are deferred until a separate security architecture exists.

294. User-Provided Rendering Code

Aegis Vuldris will not execute user-provided report-rendering code in the initial architecture.

295. Report Branding

User/project branding may eventually be supported.

Branding values remain untrusted content and must be safely encoded.

296. Logo/Image Uploads

If branding images are supported, uploads must follow secure file handling requirements.

297. Report Metadata Integrity

Report metadata such as assessment identity and finding counts must come from canonical server-side data.

Clients must not be able to modify them through report-generation parameters.

298. Client-Supplied Summary Data

Clients must not submit arbitrary:

finding_count
severity_count
risk_score
assessment_status

and have those values become report truth.

299. Server-Side Derivation

Security-sensitive report summary fields must be calculated server-side.

300. Report Generation Authorization Context

Workers generating reports must operate within a constrained authorization context.

301. Background Worker Credentials

Workers must not receive unrestricted database credentials.

Least-privilege database roles should be used.

302. Storage Credentials

Evidence/report storage credentials must be separated from unrelated application secrets where practical.

303. Secret Redaction in Reports

Reports should default to redacting probable credentials and secrets.

A deliberate forensic export may have different controls but must be explicitly authorized.

304. Secret Redaction Limitations

Automated secret detection is not guaranteed to detect every secret.

Therefore users must not assume that enabling redaction makes arbitrary evidence safe for public disclosure.

305. Public Reports

Public report sharing is not part of the initial architecture.

If introduced later, it requires a separate security review.

306. Shareable Reports

If report sharing is later supported, share tokens must be:

High entropy
Scoped
Revocable
Expirable
Auditable
307. Report Access Logs

Report downloads may be logged for sensitive deployments.

308. Evidence Access Logs

Restricted evidence access should be observable where required.

309. Audit Retention

Audit records associated with findings and reports may require longer retention than ordinary operational logs.

310. Audit Integrity

Audit records should be protected against unauthorized modification.

The detailed mechanism will be addressed by ADR-009 and the security architecture.

311. Finding History

The user-facing system should be able to distinguish:

current finding state
historical finding state
312. Finding Timeline

A finding timeline may contain:

created
severity changed
status changed
assigned
resolved
reopened
risk accepted
313. Assessment Timeline

Assessment-level reporting may also include execution milestones.

314. Evidence Timeline

Evidence should be sortable by logical execution order.

315. Time Zones

User-facing reports may display localized time zones.

Canonical storage remains UTC.

316. Report Locale

Report locale should be explicitly selected or derived from authorized user settings.

Locale selection must not alter canonical security data.

317. Number Formatting

Risk and count formatting should be presentation-level concerns.

Canonical numeric values must remain machine-readable.

318. Date Formatting

Dates in reports should be rendered consistently according to report locale.

319. Accessibility

Human-readable HTML/PDF reports should consider accessibility.

Examples include:

Semantic headings
Table headers
Readable contrast
Text alternatives for meaningful images
Keyboard navigation where applicable
320. Accessibility and Security

Accessibility features must not introduce unsafe dynamic rendering.

321. Report Navigation

Large reports should provide navigable sections.

Navigation anchors must be generated safely and must not permit arbitrary HTML injection.

322. Table Rendering

Finding tables must safely render untrusted values.

Long values should be bounded or wrapped.

323. Evidence Display

Evidence display should visually distinguish:

prompt
response
tool call
tool result
evaluation

This helps prevent users from confusing attacker-controlled content with trusted application instructions.

324. Instruction Boundary in UI

The UI must not visually imply that model-generated evidence is an instruction from Aegis Vuldris.

Labels such as:

Model Output
Observed Response
Test Input
Evaluator Result

should be used appropriately.

325. Report Viewer Isolation

If reports are displayed in the application, the viewer must not allow report content to execute application JavaScript.

326. Download vs Inline Viewing

Sensitive reports should default to safe download behavior where appropriate.

Inline viewing must be explicitly designed and secured.

327. Browser Storage

Sensitive report/evidence content should not be unnecessarily stored in browser local storage.

328. Frontend Authorization

The frontend may hide controls based on permissions, but the backend remains authoritative.

329. API Response Minimization

Evidence APIs should return only the fields needed by the caller.

Sensitive raw fields should not be included in every response by default.

330. Field-Level Redaction

The backend may apply field-level redaction based on authorization or evidence sensitivity.

331. Administrative Views

Administrative interfaces may expose additional metadata, but must remain subject to explicit authorization.

332. Audit UI

Audit history may be exposed to authorized users without exposing underlying secrets.

333. Evidence Search UI

Search interfaces should avoid leaking sensitive evidence through autocomplete or previews.

334. Finding Search UI

Finding search should use the same backend authorization model as direct retrieval.

335. Report List UI

Report lists must not reveal reports belonging to inaccessible assessments.

336. Report Download UI

Download controls should reflect permissions, but backend authorization must always be enforced.

337. Evidence Preview

Evidence previews should use bounded excerpts rather than loading arbitrarily large content.

338. Evidence Expansion

Full evidence expansion should require explicit retrieval.

339. Sensitive Evidence Warning

The UI may warn users when viewing restricted evidence.

340. Data Export Warning

The UI may warn users before exporting sensitive assessment data.

341. Finding Bulk Operations

Bulk finding changes must enforce authorization for every affected finding.

A single authorized finding must not imply authorization for all findings in a project.

342. Bulk Export Authorization

Bulk exports must verify access to the complete selected dataset.

343. Bulk Delete

Bulk deletion is deferred as a separate high-risk administrative operation.

344. Report Deletion

Deleting a report artifact must not delete the canonical assessment/finding data.

345. Evidence Deletion

Evidence deletion must respect retention and audit requirements.

346. Finding Deletion

Finding deletion should generally be restricted and audited.

Historical references may need to remain available.

347. Soft Delete

Soft deletion may be used for findings or reports where historical retention requires recoverability.

The exact policy will be decided during implementation.

348. Hard Delete

Hard deletion should be rare and controlled.

349. Deletion Confirmation

High-impact deletion operations should require explicit confirmation and appropriate authorization.

350. Report Naming

Human-readable names may be supported but should remain secondary to stable report identifiers.

351. Evidence Naming

Evidence should use stable IDs rather than arbitrary filenames as primary identity.

352. Stable Identifiers

IDs should be generated server-side and should not expose sensitive information.

353. UUID Choice

UUIDs are preferred for evidence, findings, and reports consistent with ADR-003.

354. Identifier Enumeration

The system should avoid predictable sequential public identifiers for sensitive resources.

355. ID Validation

Incoming identifiers must be syntactically validated before database lookup.

356. Not Found vs Unauthorized

The API should avoid leaking resource existence through inconsistent authorization errors.

The exact response policy will follow ADR-006.

357. Finding Counts

Counts must be computed only over authorized records.

358. Risk Aggregation Authorization

Risk summaries must be calculated only from authorized findings.

359. Report Aggregation Authorization

Reports must never aggregate data outside the authorized assessment/project boundary.

360. Cross-Assessment Reports

Cross-assessment reports may be supported later.

They must explicitly define authorization and tenant boundaries.

361. Multi-Target Assessments

An assessment may contain multiple targets.

Reports must preserve target attribution for each finding.

362. Target Attribution

A finding must identify the target to which it applies.

363. Target Deletion

If a target is deleted, historical findings should retain sufficient historical identity to remain interpretable.

364. Provider Changes

A target may change provider/model configuration.

Historical findings must retain the relevant historical target/model metadata needed for interpretation.

365. Model Version Changes

A new model version should not silently rewrite previous findings.

366. Adapter Version Changes

Adapter behavior may affect evidence.

Reports and findings should retain adapter version metadata where practical.

367. Evaluation Version Changes

Evaluator changes may alter findings.

Evaluator version must therefore be part of reproducibility metadata.

368. Test Version Changes

Test definitions may evolve.

Findings should reference the relevant test case/version.

369. Configuration Version

Security-relevant test configuration should be versioned or captured sufficiently for reproduction.

370. Prompt Template Version

If tests use templates, the relevant template version should be recorded.

371. Attack Sequence Version

Adaptive attack strategies may evolve.

The execution should retain sufficient orchestration metadata to understand how the attack was generated.

372. Randomness

If randomized testing is used, random seeds should be captured where safe and useful.

373. Randomness and Reproduction

A random seed does not guarantee reproducibility if provider/model behavior is nondeterministic.

Reports should not overstate reproducibility.

374. Determinism Metadata

Where provider APIs expose deterministic configuration, relevant parameters may be retained.

375. Token Usage

Token usage may be included in evidence metadata.

It must not be treated as security evidence unless relevant to the finding.

376. Cost Metadata

Cost estimates may be retained for operational analysis.

They must not be confused with security risk.

377. Provider Request IDs

Provider request IDs may be retained to aid troubleshooting.

They must be treated as metadata, not authorization credentials.

378. Correlation With Provider Support

Authorized operators may use provider request IDs for external troubleshooting.

Aegis Vuldris must not automatically expose these IDs to unauthorized users.

379. Network Metadata

Network timing and status codes may be useful evidence.

Sensitive headers and credentials must be redacted.

380. Request/Response Bodies

Request/response bodies may be evidence.

They must follow the same sensitivity and storage policies as model content.

381. HTTP Redirects

Redirect information may be retained where relevant to security testing.

Redirect targets remain untrusted.

382. Evidence of SSRF

If a target integration or test produces SSRF-related evidence, the report must avoid turning malicious URLs into automatically fetched resources.

383. Evidence of Prompt Injection

Prompt injection strings should be displayed safely and quoted as data.

384. Evidence of Tool Abuse

Tool abuse findings should clearly identify:

requested action
observed action
authorization context
result
385. Evidence of Data Leakage

Data leakage findings should indicate what class of information was observed without unnecessarily exposing the complete sensitive value.

386. Evidence of Policy Bypass

Policy-bypass findings should distinguish:

policy expectation
observed behavior
evidence
387. Finding Validation

Before creating a high-severity finding, the system may require stronger validation depending on the test category.

The evaluation architecture will define the exact policy.

388. Confidence Thresholds

Confidence thresholds may be used to control automatic finding creation.

These thresholds must be configurable and versioned.

389. Human Review

Certain findings may require human review.

Possible workflow:

candidate
   |
   v
needs_review
   |
   v
validated
390. Human Review Evidence

Human reviewers must see enough evidence to validate the finding without unnecessary exposure of restricted information.

391. Reviewer Actions

Reviewer actions should be auditable.

392. Finding Approval

If approval workflows are implemented, approval must not erase the automated evaluation.

393. Finding Rejection

Rejected findings should retain the evidence and review rationale.

394. Finding Escalation

High-impact findings may be escalated to authorized users.

395. Notification

Notifications are outside the primary scope of this ADR but may reference findings.

Notifications must not include unnecessary sensitive evidence.

396. Email Reports

Email delivery of reports is deferred.

If introduced, it requires a separate review for data leakage and recipient authorization.

397. Webhook Reports

Webhook delivery is deferred.

If introduced, it requires authentication, authorization, signing, replay protection, and data-minimization controls.

398. API Consumers

External API consumers must receive only authorized report/finding data.

399. Machine-Readable Findings

Aegis Vuldris should expose structured finding APIs for automation.

Consumers should not need to scrape HTML reports.

400. Report API Separation

Report generation APIs should remain separate from canonical finding APIs.

401. Evidence API Separation

Evidence retrieval should remain separately authorized from finding summaries.

402. Summary vs Raw Data

Summary endpoints should avoid returning raw evidence by default.

403. Data Aggregation

Aggregations must use canonical structured data.

404. Finding Metrics

Finding metrics should remain reproducible from stored findings.

405. Report Statistics

Report statistics should be generated server-side.

406. Count Consistency

A report's finding count must match the findings included by its scope.

407. Severity Distribution Consistency

Severity counts must be derived from the report's canonical finding set.

408. Risk Summary Consistency

Risk summaries must be calculated from the same finding snapshot used by the report.

409. Snapshot Consistency

A report must avoid mixing findings from different source versions unless explicitly identified.

410. Snapshot Identifier

A report may include a source snapshot identifier.

411. Assessment Version

Assessment-level changes may increment a version used for report reproducibility.

412. Finding Set Version

The canonical finding set may have a version or equivalent change marker.

413. Report Cache Keys

If report caching is implemented, cache keys should include relevant source versions.

414. Security of Cache Keys

Cache keys must not contain secrets.

415. Report Job Deduplication

Identical report requests may be deduplicated where safe.

Deduplication must preserve authorization boundaries.

416. Evidence Processing Queue

Evidence processing jobs must use the job architecture defined in ADR-005.

417. Retry Safety

Retries must not:

Duplicate findings
Duplicate audit events unnecessarily
Overwrite newer state
Generate uncontrolled artifacts
418. Dead-Letter Handling

Repeated evidence/report processing failures may require a dead-letter mechanism.

The exact mechanism belongs to the job architecture.

419. Failure Visibility

Operators should be able to identify stuck or failed processing jobs without exposing sensitive content.

420. Operational Backpressure

The reporting pipeline must support backpressure under large workloads.

421. Database Load Protection

Large report queries should use bounded queries and indexes.

422. Evidence Indexing

Frequently queried metadata should be indexed.

Large raw payloads should not automatically be indexed in ways that create excessive storage or performance cost.

423. Finding Indexing

Likely finding filters should have appropriate indexes.

Potential fields:

assessment_id
target_id
status
severity
category
created_at
fingerprint
424. Report Indexing

Report metadata should be indexed by relevant ownership/resource fields.

425. Query Safety

Queries must use parameterized database APIs.

426. Sorting Safety

Sort fields must come from an allowlist.

427. Pagination Stability

Pagination should remain stable under concurrent changes where practical.

Cursor-based pagination may be preferred for very large collections.

428. Evidence Ordering Index

Evidence may require indexes supporting:

execution_id
sequence_number
created_at
429. Finding Fingerprint Uniqueness

Fingerprint uniqueness constraints should be used carefully.

The same vulnerability may legitimately appear across separate assessments.

Therefore uniqueness should normally be scoped rather than global.

430. Assessment-Scoped Deduplication

A fingerprint may be unique within an assessment/execution context while allowing recurrence across assessments.

431. Historical Recurrence

Repeated findings across assessments are valuable for regression tracking.

They should not be globally deduplicated away.

432. Finding Lifecycle Automation

Automatic transitions should be conservative.

The system should not automatically mark a finding resolved solely because one later execution passed unless the regression policy explicitly supports that behavior.

433. Remediation Verification

Future remediation workflows may link a finding to verification executions.

434. Verification Evidence

Verification results must be stored as separate evidence and executions.

435. Finding Closure Evidence

Resolved findings should be associated with evidence supporting the resolution where appropriate.

436. Report Remediation Section

Reports may include remediation status.

This must be derived from finding state.

437. Risk Acceptance Expiration

Future risk acceptance workflows may support expiration dates.

Expired risk acceptance should not silently remain accepted indefinitely.

438. Finding Ownership Changes

Ownership changes must be auditable.

439. Finding Comments and Sensitive Data

Users should be warned that comments may become part of reports.

440. Report Inclusion Policy

Future reports may support including/excluding selected finding details.

Authorization must still apply.

441. Report Filters

Filtered reports must clearly indicate their scope.

442. Report Scope Integrity

A client must not manipulate filters to access data outside authorization.

443. Report Scope Metadata

Reports should record:

assessment_scope
target_scope
finding_scope
filters

where relevant.

444. Report Reproducibility and Filters

Filters used to generate a report should be retained as metadata.

445. Report Schema Stability

Machine-readable consumers should receive a stable schema contract.

446. Versioned Export Formats

Breaking report changes should increment report schema versions.

447. Deprecation

Deprecated report fields should remain documented during a compatibility period where practical.

448. Documentation

Evidence, finding, and report schemas must be documented.

449. OpenAPI Integration

API models should appear in OpenAPI documentation where applicable.

450. Example Reports

The project should maintain synthetic example reports for:

Simple finding
Multiple findings
Critical finding
Inconclusive evaluation
Partial assessment
Regression
Redacted evidence
Tool interaction
Multi-turn attack
451. Example Data Safety

Examples must never contain real credentials, personal data, customer information, or private assessment evidence.

452. Developer Experience

Developers should be able to create deterministic local reports using synthetic fixtures.

453. Local Development

Local development should use synthetic evidence by default.

454. Test Environment Isolation

Test evidence must not accidentally enter production storage.

455. Environment Separation

Development, test, and production report storage must be separated.

456. Environment Metadata

Reports should identify the environment where useful:

development
staging
production

Sensitive deployment information should not be unnecessarily exposed.

457. Production Debugging

Production debug evidence capture should be explicitly enabled.

458. Secure Defaults

Initial implementation defaults should prioritize:

authorization
redaction
bounded evidence
bounded reports
safe rendering
auditability
459. Fail-Safe Behavior

When a security decision cannot be safely made, the system should fail closed.

Examples:

unknown authorization -> deny
invalid report format -> reject
invalid evidence schema -> reject/quarantine
unknown lifecycle transition -> reject
missing source authorization -> deny
460. No Security by Obscurity

Security must not depend on:

Hidden report URLs
Unpredictable filenames alone
Obscure evidence identifiers
Frontend-only restrictions
461. Defense Against IDOR

Every evidence, finding, and report lookup must perform authorization.

462. Defense Against Mass Assignment

Clients must not be able to arbitrarily set security-sensitive fields such as:

severity
status
source
created_by
assessment_id
tenant_id
risk_score

unless explicitly authorized.

463. Immutable Server Fields

Server-controlled fields must not be client-editable.

464. Finding Creation Authorization

Creating findings manually should require appropriate permission.

Automated finding creation should use trusted internal execution context.

465. Internal Service Trust

Internal workers are not automatically trusted.

Worker inputs must still be validated.

466. Queue Message Validation

Job payloads should be validated before processing.

467. Worker Authorization

Workers must validate that the requested resource belongs to the permitted execution scope.

468. Report Renderer Input Trust

The renderer must assume all canonical text fields may contain malicious content.

469. HTML Template Trust

Only application-controlled templates may execute.

470. PDF Template Trust

Only application-controlled PDF templates/layout definitions may execute.

471. Export Format Trust

The requested format must be validated before dispatch.

472. Dynamic Import Restriction

User input must not control Python module imports for report generation.

473. Command Execution

Report generation must not invoke arbitrary shell commands based on report content.

474. Shell Safety

If external tools are ever required for PDF/report generation, command arguments must be constructed from validated application-controlled values.

475. Container Isolation

Heavy report rendering may be containerized.

Containers must not be treated as an absolute security boundary.

476. Container Permissions

Report containers should run with least privilege.

477. Container Filesystem

Temporary rendering files should use controlled writable locations.

478. Container Network

Network access should be disabled unless explicitly required.

479. Container Resource Limits

Rendering containers should have CPU, memory, process, and filesystem limits.

480. Report Renderer Timeouts

Renderer operations must have explicit timeouts.

481. Cancellation

Cancelled report jobs must stop processing and clean resources where possible.

482. Zombie Processes

External rendering processes must not remain indefinitely after cancellation.

483. Process Isolation

If external rendering processes are used, they should be isolated from the main application.

484. Evidence Processing Timeouts

Evidence normalization must have bounded execution time.

485. Malformed Evidence

Malformed evidence must not cause unbounded parser behavior.

486. Parser Security

Parsers for structured evidence must use safe, maintained libraries.

487. XML

If XML evidence is ever supported, secure parser configuration must prevent external entity attacks and related resource abuse.

488. YAML

If YAML evidence is ever supported, safe parsing must be used.

Arbitrary object construction must not be enabled.

489. JSON

JSON parsing must use bounded input sizes and schema validation.

490. HTML

HTML evidence should be stored as text and escaped before display.

491. Markdown

Markdown evidence may be supported for readability.

If rendered to HTML, the renderer must sanitize/escape unsafe content.

492. Markdown Links

Markdown links must be treated as untrusted URLs.

493. Markdown Images

Remote image loading should be disabled or tightly controlled.

494. Template Syntax in Evidence

Template-like content must remain inert.

495. Jinja-Like Payloads

Strings such as:

{{ malicious_expression }}

must remain plain data.

496. Expression Evaluation

Aegis Vuldris must never evaluate arbitrary expressions contained in evidence.

497. Serialization Safety

Only explicitly supported serialization formats should be accepted.

498. Deserialization Boundary

All deserialization must occur inside a validation boundary.

499. Type Confusion

Unexpected JSON types must not cause authorization or reporting logic to interpret attacker-controlled structures incorrectly.

500. Numeric Bounds

Risk scores, confidence values, counts, and limits must be bounded.

501. Confidence Bounds

Confidence values should normally be constrained to a defined range such as:

0.0 <= confidence <= 1.0
502. Risk Score Bounds

If a normalized risk score is introduced, its valid range must be explicitly defined.

503. Severity Enumeration

Severity must be selected from the controlled severity set.

504. Status Enumeration

Finding status must be selected from the controlled lifecycle set.

505. Category Enumeration

Security categories must be validated.

506. Evidence Type Enumeration

Evidence types must be validated.

507. Report Format Enumeration

Report formats must be validated.

508. Report Status Enumeration

Report statuses must be validated.

509. Lifecycle Transition Rules

Not every status transition should be valid.

For example:

resolved -> reopened

may be valid.

deleted -> open

may not be valid.

Transition rules should be explicit.

510. Transition Authorization

Some transitions may require elevated permissions.

511. Transition Audit

Security-relevant transitions must be auditable.

512. Finding State Machine

The finding lifecycle should eventually be represented as an explicit state machine.

513. Evidence Lifecycle

Evidence may have a simpler lifecycle:

created
processed
redacted
archived
deleted
514. Report Lifecycle

Reports may use:

queued
running
completed
failed
cancelled
deleted
515. State Consistency

State transitions must not create impossible combinations.

516. Cross-Object State

For example, a report cannot truthfully claim:

assessment = complete

if it was generated from a different assessment.

517. Referential Integrity

Evidence/finding/report references must remain valid or explicitly indicate deleted/expired data.

518. Missing Evidence

If referenced evidence is unavailable, the finding should remain interpretable without falsely implying the evidence is still accessible.

519. Evidence Availability

Reports may include:

evidence_available = true/false

where appropriate.

520. Evidence Expiration

Expired evidence should be clearly distinguished from never-captured evidence.

521. Retention Metadata

Evidence may include:

retention_policy_id
expires_at
522. Automatic Retention

Automatic cleanup must be carefully bounded and auditable.

523. Retention Override

Retention overrides require authorization.

524. Legal Hold

Future legal-hold functionality may prevent deletion of selected evidence.

This is deferred.

525. Report Retention

Reports should follow defined retention policy rather than existing forever by default.

526. Storage Quotas

Projects may eventually have evidence/report storage quotas.

527. Quota Enforcement

Quota enforcement must prevent denial of service through unlimited evidence generation.

528. Quota Errors

Quota failures should produce safe, actionable errors.

529. Quota Metadata

Usage statistics may include:

evidence_bytes
report_bytes
artifact_count
530. Quota Security

Quota calculations must be scoped to authorized resources.

531. Cost Controls

Report generation should not create uncontrolled compute or storage costs.

532. Operational Limits

The application should expose configurable limits for:

max evidence size
max report size
max findings
max report jobs
max concurrent renderers
533. Configuration Security

Operational limits must be server-controlled.

Untrusted users must not bypass them through request parameters.

534. Configuration Versioning

Security-relevant report configuration may be versioned.

535. Secure Configuration Defaults

Defaults must favor bounded processing and data minimization.

536. Testing Configuration

Tests should cover boundary values.

Examples:

0
1
maximum
maximum + 1
negative values
null
unexpected type
537. Fuzzing Boundaries

Input boundaries should be fuzz-tested where practical.

538. Report Security Review

Before production release, report rendering dependencies and code should undergo focused security review.

539. Evidence Security Review

Evidence storage/retrieval should undergo focused security review.

540. Finding Security Review

Finding authorization and lifecycle logic should undergo focused security review.

541. Threat Model Updates

The threat model must be updated when new evidence/report features introduce new trust boundaries.

542. Relationship to ADR-003

ADR-003 defines PostgreSQL as the primary database architecture.

This ADR defines what evidence/finding/report information must conceptually be persisted there.

543. Relationship to ADR-004

ADR-004 defines API communication architecture.

This ADR defines the security and data semantics of evidence, findings, and report APIs.

544. Relationship to ADR-005

ADR-005 defines test execution and job architecture.

This ADR relies on that architecture for asynchronous evidence processing and report generation.

545. Relationship to ADR-006

ADR-006 defines authentication and authorization.

This ADR requires those controls to protect evidence, findings, and reports.

546. Relationship to ADR-007

ADR-007 defines model adapter and target integration architecture.

Adapter outputs become evidence inputs but remain untrusted.

547. Relationship to ADR-009

ADR-009 will define observability and audit logging architecture.

This ADR establishes the audit requirements specific to findings, evidence, and reports.

548. Separation From Test Engine

The test engine determines what to test.

The evidence architecture determines how observations are preserved.

The evaluation engine determines what the observations mean.

The finding layer records security conclusions.

The report layer presents the results.

549. Separation of Responsibilities

The system should follow:

Test Engine
    -> generates executions

Evidence Layer
    -> preserves observations

Evaluation Layer
    -> interprets observations

Finding Layer
    -> records security conclusions

Risk Layer
    -> aggregates/prioritizes

Reporting Layer
    -> presents/export results
550. No Hidden Coupling

A report renderer must not contain security-testing logic.

A test implementation must not directly construct HTML/PDF reports.

An evaluator must not bypass finding validation.

551. Canonical Source of Truth

The canonical source of truth is:

structured assessment data
+
structured findings
+
stored evidence

Not:

HTML report
PDF report
CSV file
LLM-generated summary
552. Report Regeneration From Canonical Data

Any report format should be regenerable from canonical data subject to retention and version availability.

553. Evidence-to-Finding Traceability

Every automated finding should be traceable back to the evidence and evaluation that produced it.

554. Finding-to-Report Traceability

Every report finding should be traceable to the canonical finding identifier.

555. Report-to-Assessment Traceability

Every report should identify its source assessment.

556. Assessment-to-Target Traceability

Every assessment should identify the tested target(s).

557. Full Traceability Chain

The system should support:

Report
  -> Assessment
      -> Execution
          -> Test Case
          -> Evidence
              -> Evaluation
                  -> Finding

The exact internal relationships may evolve, but the conceptual chain must remain.

558. Security Invariant

A user must never gain access to evidence, findings, or reports solely by possessing an identifier.

559. Security Invariant

Untrusted model output must never become executable report content.

560. Security Invariant

A report must never become the authoritative source of security state.

561. Security Invariant

Secrets must not intentionally be persisted as evidence.

562. Security Invariant

Finding severity and status must be server-controlled and authorization-protected.

563. Security Invariant

Report generation must respect project/tenant authorization.

564. Security Invariant

Large evidence/report operations must be resource-bounded.

565. Security Invariant

Historical finding state must not be silently rewritten.

566. Security Invariant

Evaluator output must not be treated as inherently trustworthy.

567. Security Invariant

Report rendering must not require unrestricted outbound network access.

568. Security Invariant

Dynamic report formats must use safe serializers/renderers.

569. Security Invariant

Evidence deletion must respect retention and audit requirements.

570. Security Invariant

Cross-project and cross-tenant evidence access must be denied.

571. Security Invariant

Client-supplied summary values must not become report truth.

572. Security Invariant

A failed report generation must not corrupt assessment or finding state.

573. Security Invariant

A malformed evidence record must not cause arbitrary code execution.

574. Security Invariant

A report filename must never allow path traversal.

575. Security Invariant

CSV exports must defend against spreadsheet formula injection.

576. Security Invariant

HTML reports must defend against cross-site scripting.

577. Security Invariant

Raw evidence access must be explicitly authorized.

578. Security Invariant

Report caches must not bypass authorization.

579. Security Invariant

Worker permissions must follow least privilege.

580. Security Invariant

Generated reports must include sufficient version metadata for interpretation.

581. Alternatives Considered
Alternative A: Store Only Findings

Rejected.

This would lose raw evidence required for reproduction and investigation.

Alternative B: Store Only Raw Evidence

Rejected.

Raw evidence alone does not provide structured security conclusions or lifecycle management.

Alternative C: Treat Reports as the Source of Truth

Rejected.

Reports are presentation artifacts and can become stale.

Alternative D: Store Everything in One JSON Blob

Rejected.

A single unstructured object would make authorization, querying, lifecycle management, indexing, migration, and reporting difficult.

Alternative E: Generate Reports Directly From Provider Responses

Rejected.

Provider responses are untrusted and provider-specific.

Alternative F: Let the LLM Decide the Final Finding

Rejected.

The model/evaluator must not be the sole security authority.

Alternative G: Allow User-Defined Report Templates Immediately

Rejected.

Dynamic templates create significant injection and code-execution risks.

Alternative H: Use Client-Side Report Generation

Rejected for canonical security reporting.

Client-side rendering may be useful for presentation, but server-side authorization and canonical report generation remain required.

Alternative I: Store All Evidence Forever

Rejected.

This violates data minimization and creates unnecessary storage and privacy risk.

Alternative J: Automatically Delete Evidence Immediately After Finding Creation

Rejected.

This harms reproducibility and investigation.

582. Consequences
Positive Consequences
Strong evidence-to-finding traceability
Better reproducibility
Clear separation of concerns
Safer report generation
Multiple report formats from one canonical model
Better lifecycle management
Stronger authorization boundaries
Better auditability
Reduced risk of report injection
Better support for regression testing
Better support for privacy controls
Better operational scalability
Negative Consequences
More data models
More storage requirements
More schema/version management
More complex authorization
More processing stages
More testing requirements
More complicated retention policies
Additional report-generation infrastructure

These costs are accepted because security assessment evidence is inherently more complex than ordinary application output.

583. Implementation Guidance

The initial implementation should proceed incrementally.

Recommended order:

1. Evidence domain model
2. Evidence persistence
3. Evidence relationships
4. Finding domain model
5. Finding persistence
6. Finding lifecycle
7. Evidence/finding authorization
8. Evaluation-to-finding pipeline
9. Canonical report model
10. JSON renderer
11. CSV renderer
12. HTML renderer
13. PDF renderer
14. Report persistence
15. Report jobs
16. Retention
17. Integrity hashing
18. Audit integration
19. Security regression tests
20. Performance/load tests
584. Initial MVP Boundary

The first implementation should not attempt to implement every future feature described in this ADR.

The MVP should prioritize:

structured evidence
structured findings
authorization
safe JSON reporting
safe HTML reporting
bounded storage
basic lifecycle
reproducibility metadata
audit-ready design

CSV/PDF, advanced retention, external artifact storage, and advanced compliance reporting may be introduced incrementally.

585. Database Model Direction

The likely initial entities include:

Assessment
Execution
Evidence
Evaluation
Finding
Report

Additional entities may include:

FindingHistory
ReportArtifact
EvidenceArtifact
ComplianceMapping

Exact SQLAlchemy models and relationships will be defined during implementation.

586. API Model Direction

Potential API resources include:

/assessments/{assessment_id}/evidence
/assessments/{assessment_id}/findings
/assessments/{assessment_id}/reports
/findings/{finding_id}
/evidence/{evidence_id}
/reports/{report_id}

These are conceptual resources only.

Final routes must follow ADR-004 and ADR-006.

587. Testing Strategy

Tests must cover:

Unit Tests
Evidence validation
Evidence normalization
Finding validation
Severity handling
Status transitions
Fingerprints
Report serialization
Escaping
CSV safety
Redaction
Integration Tests
Database persistence
Authorization
Evidence-to-finding relationships
Report generation
Job processing
Artifact storage
Security Tests
IDOR
XSS
CSV injection
Path traversal
SSRF through report rendering
Template injection
Secret leakage
Cross-project access
Resource exhaustion
End-to-End Tests
test
 -> execution
 -> evidence
 -> evaluation
 -> finding
 -> report
588. Acceptance Criteria

This ADR is considered implemented when:

Evidence has a structured domain model.
Evidence has stable identifiers.
Evidence is linked to executions.
Evidence is treated as untrusted.
Sensitive evidence can be redacted.
Findings have structured lifecycle states.
Findings have severity and confidence separately.
Findings reference evidence.
Finding changes are auditable.
Cross-project access is denied.
Reports are derived artifacts.
JSON reporting is schema-versioned.
HTML rendering safely escapes dynamic content.
CSV rendering considers formula injection.
Report generation is resource-bounded.
Report files have safe names.
Report artifacts can be integrity-checked.
Report generation respects authorization.
Large report generation can use background jobs.
Historical reports do not silently change.
Reproducibility metadata is retained.
Security regression tests exist.
Sensitive test fixtures contain no real secrets.
Report renderers are independently testable.
The canonical source of truth remains structured assessment/finding/evidence data.
589. Security Review Checklist

Before production release, verify:

[ ] Authentication enforced
[ ] Authorization enforced
[ ] Project isolation enforced
[ ] Tenant isolation enforced where applicable
[ ] IDOR tests pass
[ ] Evidence is treated as untrusted
[ ] Raw evidence access is protected
[ ] Secrets are redacted
[ ] PII handling is defined
[ ] Evidence size limits exist
[ ] Report size limits exist
[ ] Report generation timeouts exist
[ ] HTML escaping is verified
[ ] CSV injection protection is verified
[ ] PDF generation is isolated
[ ] Report filenames are sanitized
[ ] Path traversal tests pass
[ ] SSRF protection is verified
[ ] External resource loading is disabled by default
[ ] Unsafe deserialization is prohibited
[ ] Temporary files are controlled
[ ] Artifact integrity is verified
[ ] Audit events exist
[ ] Retention policy exists
[ ] Deletion behavior is tested
[ ] Background jobs are authorized
[ ] Worker permissions are restricted
[ ] Report caches respect authorization
[ ] Security regression tests pass
590. Operational Checklist

Before deployment, verify:

[ ] Database migrations applied
[ ] Evidence storage configured
[ ] Report storage configured
[ ] Storage encryption configured
[ ] Backup policy configured
[ ] Retention policy configured
[ ] Worker capacity configured
[ ] Report concurrency limit configured
[ ] Evidence size limits configured
[ ] Report size limits configured
[ ] Logging configured
[ ] Metrics configured
[ ] Alerting configured
[ ] Cleanup jobs configured
[ ] Artifact integrity checks configured
591. Documentation Requirements

Documentation should explain:

Evidence lifecycle
Finding lifecycle
Severity semantics
Confidence semantics
Report formats
Report schema versions
Evidence retention
Redaction
Export controls
Reproducibility
Security limitations
592. Future Extensions

Potential future capabilities include:

Advanced evidence stores
Object storage
Evidence encryption at field level
Configurable retention policies
Legal holds
Public report sharing
Signed reports
Digital signatures
Advanced compliance mapping
Evidence diffing
Assessment comparison
AI-generated summaries
Human review workflows
Finding ownership
Finding comments
Remediation tracking
Verification workflows
Advanced analytics
Risk trend dashboards
Scheduled reports
External report delivery
Webhook delivery
Custom report templates
Report plugins

Each capability must receive appropriate security review before implementation.

593. Digital Signatures

Future versions may support digitally signed reports.

A signature could provide stronger authenticity than a simple hash.

If implemented, key management and signature verification require a dedicated security design.

594. Signed Evidence

Future versions may support signed evidence chains.

This could improve forensic integrity in high-assurance deployments.

595. Merkle-Style Evidence Integrity

Future high-assurance deployments may consider chained hashes or Merkle structures for large evidence sets.

This is explicitly deferred.

596. Forensic Mode

A future forensic mode may capture more detailed execution data.

Forensic mode must have explicit authorization and stronger storage protections.

597. Privacy-Preserving Evidence

Future versions may support:

Differential redaction
PII masking
Tokenization
Selective disclosure
Cryptographic commitments

These are deferred.

598. Data Residency

Future enterprise deployments may require data residency controls.

Evidence/report storage architecture should remain extensible enough to support regional storage.

599. Customer-Controlled Keys

Future deployments may support customer-managed encryption keys.

This requires a separate key-management architecture.

600. Multi-Tenant Encryption

Future multi-tenant deployments may use tenant-scoped encryption keys.

This is deferred.

601. Retention Policy Engine

A future policy engine may determine retention based on:

project
assessment
finding severity
data classification
regulatory requirements
602. Automated Evidence Classification

Future versions may classify evidence automatically.

Automated classification must remain advisory unless explicitly validated.

603. Automated Secret Detection

Secret detection may become part of evidence ingestion.

False positives and false negatives must be expected.

604. Automated PII Detection

PII detection may become part of evidence processing.

It must not be treated as complete privacy protection.

605. Evidence Access Approval

Future deployments may require approval before viewing restricted evidence.

606. Dual-Control Operations

Highly sensitive exports/deletions may eventually require dual authorization.

607. Report Watermarking

Future reports may include:

confidential
assessment identifier
generated timestamp
recipient

Watermarking is presentation-level protection and does not replace access control.

608. Report Expiration

Future reports may include explicit expiration metadata.

609. Secure Report Sharing

Secure sharing may include:

short-lived links
recipient binding
access logging
revocation
download limits
610. Offline Reports

Reports may be used offline.

Offline copies cannot be remotely revoked, so report disclosure must be considered irreversible once downloaded.

611. Report Classification

Reports should eventually support sensitivity classification.

612. Evidence Classification Propagation

A report containing restricted evidence should not automatically become public simply because its report format is HTML or PDF.

613. Classification Downgrade

Any future downgrade of report sensitivity must be explicit and auditable.

614. Security Boundary Summary

The evidence/reporting subsystem crosses multiple trust boundaries:

Target
  |
  v
Adapter
  |
  v
Execution
  |
  v
Evidence
  |
  v
Evaluator
  |
  v
Finding
  |
  v
Report
  |
  v
User

Every boundary must assume the incoming data may be malicious.

615. Core Architecture

The final conceptual architecture is:

                 +-------------------+
                 |      Target       |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 |  Model Adapter    |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | Test Execution    |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 |     Evidence      |
                 |  Raw + Normalized |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 |    Evaluation     |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 |     Findings      |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 |   Risk Metadata   |
                 +---------+---------+
                           |
                           v
                 +-------------------+
                 | Canonical Report  |
                 |      Model        |
                 +----+----+----+----+
                      |    |    |
                      v    v    v
                    JSON CSV HTML
                              |
                              v
                             PDF
616. Final Decision Summary

Aegis Vuldris will implement a structured evidence, findings, and reporting architecture with:

Evidence as the canonical record of observable execution data
Findings as structured security conclusions
Risk metadata as a separate analytical layer
Reports as derived snapshots
Explicit provenance and reproducibility metadata
Strong resource-level authorization
Secure evidence handling
Secret and sensitive-data minimization
Safe HTML/CSV/PDF generation
Versioned machine-readable reports
Integrity metadata
Explicit lifecycle states
Audit-ready changes
Background processing for expensive operations
Resource limits
Strong isolation between rendering and core application logic
Defense in depth
Open-source implementation
No reliance on model output as a security boundary

The architecture deliberately separates:

what happened
    from
what it means
    from
what risk it represents
    from
how it is presented

This separation is a foundational security property of Aegis Vuldris.

617. Status

Accepted.

Implementation will follow the architecture and acceptance criteria defined in this ADR.

Future changes that materially alter evidence trust, finding semantics, report security, authorization boundaries, or canonical data ownership should be recorded as new ADRs or explicit amendments.

618. Related ADRs
ADR-001: Backend Framework
ADR-002: Frontend Framework
ADR-003: Database Architecture
ADR-004: API Communication Architecture
ADR-005: Test Execution and Job Architecture
ADR-006: Authentication and Authorization Architecture
ADR-007: Model Adapter and Target Integration Architecture
ADR-009: Observability and Audit Logging Architecture
