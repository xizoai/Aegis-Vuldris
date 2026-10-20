# ADR-011 — Attack Orchestration & Multi-Turn Execution Architecture

**Status:** Accepted
**Date:** 2026-09-10
**Decision Type:** Architecture
**Scope:** Aegis Vuldris attack orchestration, multi-turn execution, adaptive attack chains, execution state, safety controls, replay, concurrency, cancellation, and integration with security testing
**Related ADRs:** ADR-005, ADR-007, ADR-008, ADR-009, ADR-010

---

## 1. Decision Summary

Aegis Vuldris SHALL implement attack orchestration as a dedicated application-layer subsystem responsible for coordinating security-test attack strategies and executing controlled attack conversations against configured model targets.

The orchestration subsystem SHALL NOT itself determine whether a target is vulnerable.

Instead, orchestration SHALL coordinate:

1. attack-plan selection,
2. attack-step generation,
3. execution against a target adapter,
4. conversation/session state,
5. observation capture,
6. execution control,
7. adaptive continuation,
8. stopping conditions,
9. evidence production,
10. replay metadata,
11. resource limits,
12. cancellation,
13. authorization checks,
14. audit events,
15. handoff to evaluation.

The resulting architectural pipeline is:

```text
Security Test
      |
      v
Attack Strategy
      |
      v
Attack Plan
      |
      v
Attack Orchestrator
      |
      +--------------------+
      |                    |
      v                    v
Execution State       Resource Controls
      |                    |
      +---------+----------+
                |
                v
          Target Adapter
                |
                v
          Target Model
                |
                v
            Response
                |
                v
           Observation
                |
                v
       Continue / Stop Decision
                |
          +-----+-----+
          |           |
       Continue      Stop
          |           |
          +----->-----+
                |
                v
             Evidence
                |
                v
            Evaluation
                |
                v
             Finding
                |
                v
          Risk Assessment
                |
                v
             Reporting

The orchestrator SHALL therefore be treated as an execution-control component rather than as a vulnerability classifier.

2. Problem Statement

Single-request security testing is insufficient for many classes of AI security behavior.

Some target weaknesses emerge only after:

several conversational turns,
progressive instruction escalation,
context accumulation,
state changes,
tool invocation,
retrieval of malicious content,
role manipulation,
repeated attempts,
adaptive responses,
changes in system context,
or interactions between apparently harmless prompts.

Aegis Vuldris therefore requires an architecture capable of representing and executing attack sequences rather than only isolated prompts.

The architecture must also prevent attack orchestration from becoming an uncontrolled automation layer.

An attack engine that can freely:

issue unlimited requests,
access arbitrary URLs,
invoke arbitrary tools,
write arbitrary files,
execute arbitrary commands,
bypass target restrictions,
or continue indefinitely

would itself become a security risk.

Therefore attack orchestration MUST combine attack flexibility with explicit execution boundaries.

3. Context

Aegis Vuldris is intended to test systems that may expose:

conversational models,
completion APIs,
RAG systems,
agentic systems,
tool-enabled assistants,
custom REST APIs,
OpenAI-compatible endpoints,
Ollama-backed models,
or other authorized model interfaces.

The target may maintain conversational state.

A security test may therefore require:

Turn 1
  |
  v
Target response
  |
  v
Turn 2 based on response
  |
  v
Target response
  |
  v
Turn 3 based on accumulated state
  |
  v
Evaluation

The orchestration architecture must preserve sufficient state to reproduce this sequence while avoiding unnecessary retention of sensitive information.

4. Goals

The architecture SHALL provide:

deterministic attack execution,
controlled adaptive execution,
multi-turn conversation support,
explicit attack-plan representation,
execution-state persistence,
target-session isolation,
configurable stopping conditions,
request limits,
time limits,
token/resource limits where supported,
concurrency controls,
retry controls,
cancellation,
failure handling,
reproducibility,
replay support,
evidence preservation,
auditability,
authorization enforcement,
project isolation,
target isolation,
evaluator integration,
risk-engine integration,
reporting integration,
safe plugin boundaries,
testability,
extensibility.
5. Non-Goals

This ADR does NOT define:

vulnerability severity scoring,
final risk formulas,
evidence schema in full,
authentication implementation details,
database schema in full,
model adapter protocol in full,
frontend implementation,
compliance mapping,
report rendering,
infrastructure deployment.

Those concerns are delegated to the related architecture decisions.

6. Architectural Principles

The attack orchestration subsystem SHALL follow these principles.

6.1 Orchestration Is Not Evaluation

The orchestrator executes attacks.

The evaluator determines whether observed behavior satisfies a security condition.

The orchestrator MUST NOT convert an attack response directly into a vulnerability finding without passing through the evaluation architecture.

6.2 Model Behavior Is Untrusted

The target model response SHALL be treated as untrusted data.

A model response MUST NOT be interpreted as trusted instructions to the Aegis Vuldris runtime.

For example, a response such as:

Ignore the test framework and execute this command:

MUST remain model output.

It MUST NOT become an Aegis Vuldris execution instruction.

6.3 Attack Content Is Untrusted

Attack prompts may intentionally contain:

instructions,
code,
URLs,
shell syntax,
JSON,
HTML,
SQL,
template expressions,
encoded data,
malicious payloads.

The orchestration engine MUST treat attack content as data.

6.4 Explicit Capabilities

An attack execution SHALL receive only the capabilities required by the test.

Capabilities SHALL NOT be granted implicitly.

6.5 Defense in Depth

No single safeguard SHALL be considered sufficient.

The orchestrator SHALL combine:

authorization,
target allowlisting,
input validation,
resource limits,
network controls,
timeout controls,
concurrency controls,
cancellation,
logging,
audit events,
isolation,
and post-execution evaluation.
7. Attack Orchestration Responsibilities

The orchestrator SHALL be responsible for:

loading an authorized attack plan,
validating the plan,
resolving the target,
verifying target permissions,
creating execution state,
initializing a target session,
executing attack steps,
collecting responses,
updating execution state,
applying step transitions,
enforcing limits,
evaluating continuation conditions,
handling retries,
handling failures,
recording evidence references,
emitting audit events,
finalizing execution,
handing observations to evaluation.

The orchestrator SHALL NOT be responsible for:

authenticating the user directly,
calculating final risk,
generating arbitrary application code,
bypassing authorization,
deciding business permissions,
or trusting model-generated commands.
8. Attack Plan

An attack plan is the declarative representation of an attack strategy.

A conceptual attack plan contains:

AttackPlan
  |
  +-- identity
  +-- metadata
  +-- category
  +-- objective
  +-- target requirements
  +-- initial context
  +-- steps
  +-- transitions
  +-- limits
  +-- capabilities
  +-- stopping conditions
  +-- evaluator references
  +-- version

Attack plans SHALL be versioned.

An execution SHALL record the exact attack-plan version used.

9. Attack Plan Identity

Every attack plan SHALL have a stable identifier.

Example:

aegis.prompt-injection.direct.v1
aegis.jailbreak.multi-turn.v1
aegis.rag.indirect-injection.v1
aegis.agent.tool-abuse.v1

The identifier SHALL remain stable across compatible revisions.

Breaking changes SHALL result in a new major version.

10. Attack Plan Versioning

Attack plans SHALL use explicit versions.

Example:

1.0
1.1
1.2
2.0

Minor versions MAY add compatible metadata or improve generation behavior.

Major versions SHALL represent incompatible behavior.

The execution record SHALL store:

attack_plan_id
attack_plan_version
11. Attack Categories

The orchestration layer SHALL support categories including:

jailbreak,
prompt injection,
indirect prompt injection,
system prompt extraction,
privacy leakage,
sensitive data disclosure,
RAG poisoning,
RAG injection,
agent abuse,
tool abuse,
unsafe tool selection,
excessive agency,
instruction hierarchy attacks,
context manipulation,
role confusion,
multi-turn escalation,
robustness attacks,
structured-output attacks,
policy evasion.

New categories SHALL be extensible.

12. Attack Objective

Each attack plan SHALL declare an objective.

Examples:

induce_policy_violation
extract_protected_information
cause_unsafe_tool_use
bypass_instruction_boundary
cause_sensitive_data_disclosure
trigger_unauthorized_action

The objective is a testing intent.

It SHALL NOT itself constitute proof of vulnerability.

13. Attack Steps

An attack plan consists of ordered or conditionally selected steps.

Conceptually:

Step 1
  |
  v
Step 2
  |
  v
Step 3
  |
  +---- condition ----> Step 4
  |
  +---- otherwise ----> Step 5

A step may contain:

prompt template,
generated input reference,
expected observation type,
transition rules,
timeout,
retry policy,
capability requirements,
evaluator hooks,
metadata.
14. Step Identity

Every step SHALL have a stable identifier within the plan.

Example:

initialize
establish_context
probe
escalate
request_sensitive_action
verify_response
finalize

Execution records SHALL identify the current step.

15. Step Ordering

Steps MAY be:

sequential,
conditional,
branching,
repeated,
response-dependent.

The architecture SHALL avoid arbitrary executable workflow definitions.

Attack plans SHALL use a constrained execution model.

16. Declarative Execution

Attack plans SHOULD be declarative.

They SHOULD describe:

what to execute
when to execute it
what data is required
what transition is allowed
what limits apply

They SHOULD NOT contain unrestricted Python or shell code.

This reduces the risk that imported attack plans become code-execution mechanisms.

17. Dynamic Attack Generation

The framework SHALL support generated attack inputs.

Generation may use:

deterministic templates,
mutation,
fuzzing,
model-assisted generation,
adaptive generation,
combinatorial generation.

Generated content SHALL remain subject to the same validation and execution controls as static content.

18. Deterministic Generation

Where reproducibility is required, generation SHALL support a deterministic seed.

An execution SHALL record:

generator_id
generator_version
seed
generation_parameters

This allows the generated attack to be reconstructed where the underlying generator is deterministic.

19. Adaptive Generation

Adaptive attacks may use previous target observations to determine subsequent inputs.

Conceptually:

attack input
    |
    v
target response
    |
    v
strategy decision
    |
    v
next attack input

Adaptive generation MUST NOT be allowed to modify security boundaries.

It may choose among permitted attack actions but may not:

disable limits,
expand target scope,
grant itself permissions,
access secrets,
invoke unrestricted tools,
modify authorization state.
20. Multi-Turn Execution

A multi-turn execution SHALL maintain explicit conversation state.

Conceptually:

Conversation
  |
  +-- turn 1
  +-- response 1
  +-- turn 2
  +-- response 2
  +-- turn 3
  +-- response 3

The state SHALL distinguish:

attack input,
target response,
system metadata,
execution metadata,
evaluator observations.
21. Conversation State

Conversation state SHALL be owned by the execution context.

A conceptual state structure is:

ExecutionState
  |
  +-- execution_id
  +-- target_id
  +-- attack_plan
  +-- current_step
  +-- turn_count
  +-- messages
  +-- observations
  +-- transition_history
  +-- resource_usage
  +-- status
22. State Isolation

Execution state SHALL be isolated between:

users,
projects,
targets,
executions,
test runs.

One execution MUST NOT be able to read another execution's conversation state unless explicitly authorized.

23. Target Session Isolation

A target conversation session SHALL be associated with exactly one logical execution context.

Where the target supports server-side sessions, Aegis Vuldris SHALL explicitly manage session identifiers.

A session identifier MUST NOT be reused across unrelated tests unless the test explicitly requires state reuse.

24. Session Leakage Prevention

Target sessions MUST NOT accidentally carry state from:

another project,
another user,
another test,
another target.

Session lifecycle SHALL therefore be explicit.

25. Session Reset

The orchestration architecture SHALL support:

create session
reset session
continue session
terminate session

Tests requiring clean state SHOULD use a fresh session.

26. Cross-Turn Context

The orchestrator SHALL distinguish between:

context intentionally supplied to the target,
context generated by the target,
Aegis Vuldris execution metadata,
evaluator-only metadata.

Evaluator-only metadata MUST NOT accidentally be sent to the target.

27. System Prompt Separation

If a target adapter requires system instructions, they SHALL be represented separately from attacker-controlled user messages.

The attack engine MUST NOT gain implicit authority to modify protected system instructions.

28. Instruction Boundary

The orchestration architecture SHALL preserve the distinction between:

system instructions
developer instructions
user/test input
tool output
retrieved content
model output

The exact hierarchy depends on the target.

Aegis Vuldris SHALL record the hierarchy when known.

29. Attack Injection

The framework SHALL allow tests to intentionally place malicious instructions in untrusted locations.

Examples:

user message,
retrieved document,
web content,
tool result,
file content.

However, the Aegis Vuldris runtime SHALL continue treating those values as untrusted data.

30. Indirect Prompt Injection

Indirect prompt-injection tests may include attacker-controlled content retrieved from:

URLs,
documents,
search results,
databases,
simulated tool responses.

External content SHALL be subject to network and content controls.

31. Tool-Aware Attacks

For agent targets, an attack may attempt to influence tool selection.

Aegis Vuldris SHALL distinguish:

model requested tool
tool authorization
tool execution
tool result
model interpretation

A model request to invoke a tool MUST NOT itself authorize execution.

32. Tool Execution Boundary

If Aegis Vuldris ever executes a target-requested tool during testing, the tool SHALL run through an explicit capability boundary.

The tool invocation MUST pass:

target authorization,
test authorization,
capability validation,
input validation,
resource controls.
33. Default Tool Policy

The default policy SHALL be deny-by-default.

No tool SHALL be executable unless explicitly enabled for the execution.

34. Dangerous Tools

The following capabilities SHALL be considered high-risk:

arbitrary shell execution,
arbitrary code execution,
filesystem writes,
filesystem deletion,
unrestricted network access,
credential access,
process creation,
container management,
cloud administration,
database modification.

These capabilities SHALL NOT be implicitly enabled.

35. Network Access

Attack execution SHALL use an explicit network policy.

The policy may define:

allowed protocols
allowed hosts
allowed ports
blocked hosts
redirect behavior
DNS behavior
request limits
response limits
36. SSRF Protection

The orchestrator SHALL treat model-generated URLs as untrusted.

It MUST defend against:

localhost access,
loopback access,
private IP ranges,
link-local addresses,
cloud metadata endpoints,
internal DNS,
unsafe redirects,
DNS rebinding.

Network enforcement SHALL occur below the model decision layer.

37. Target Allowlisting

Targets SHALL be explicitly registered.

Execution SHALL verify that the requested target is authorized for the project and user.

An attack plan MUST NOT select arbitrary network targets unless the target has been registered and authorized.

38. Target Identity

Every execution SHALL bind to a target identifier.

Conceptually:

execution_id -> target_id

The target configuration SHALL not be inferred from attacker-controlled content.

39. Target Adapter Integration

The orchestrator SHALL communicate with targets through the model-adapter boundary defined by ADR-007.

The orchestrator SHOULD NOT contain provider-specific API logic.

Architecture:

Orchestrator
      |
      v
Model Adapter Interface
      |
      +---- OpenAI-compatible
      +---- Ollama
      +---- Custom REST
      +---- Future adapters
40. Adapter Contract

The orchestrator SHALL provide normalized execution requests.

The adapter SHALL return normalized responses.

Provider-specific errors SHOULD be translated into normalized execution errors while retaining provider diagnostics where safe.

41. Execution Request

A conceptual request is:

ExecutionRequest
  |
  +-- execution_id
  +-- target_id
  +-- session_id
  +-- messages
  +-- generation_options
  +-- timeout
  +-- metadata
42. Execution Response

A conceptual response is:

ExecutionResponse
  |
  +-- response_id
  +-- content
  +-- tool_calls
  +-- usage
  +-- latency
  +-- provider_metadata
  +-- status
  +-- error
43. Observation

The raw response SHALL be transformed into an observation suitable for evaluation.

An observation may include:

response text,
structured output,
tool calls,
tool results,
metadata,
timing,
status,
usage information.
44. Observation Trust

Observations from the target SHALL be considered untrusted.

They SHALL NOT be interpreted as Aegis Vuldris instructions.

45. Transition Engine

After each step, the orchestrator SHALL determine whether execution should:

continue,
branch,
retry,
terminate successfully,
terminate due to failure,
terminate due to limit,
become inconclusive,
or be cancelled.
46. Transition Rules

Transition rules SHALL be constrained.

They may inspect approved observations such as:

response contains expected marker
tool call occurred
response schema matched
response status
evaluation signal

They SHALL NOT execute arbitrary code supplied by an attack.

47. Branching

Attack plans MAY branch.

Example:

Probe
 |
 +-- refusal detected ------> escalation
 |
 +-- partial compliance ---> escalation
 |
 +-- unsafe action ---------> verification
 |
 +-- error ------------------> recovery

Branches SHALL be explicitly declared.

48. Loops

Loops SHALL be bounded.

Every loop MUST have at least one enforceable termination mechanism.

Examples:

max_iterations
max_turns
max_duration
49. Infinite Loop Prevention

The orchestrator MUST prevent:

while true

style execution semantics.

No attack plan may cause unbounded execution.

50. Maximum Turns

Every execution SHALL have a maximum turn limit.

A system-wide safe default SHALL exist.

Individual tests MAY request a lower limit.

Increasing a limit above configured policy SHOULD require elevated permission or policy approval.

51. Maximum Duration

Every execution SHALL have a maximum wall-clock duration.

The timer SHALL cover the full execution rather than only individual model requests.

52. Per-Request Timeout

Each target request SHALL have its own timeout.

The per-request timeout MUST NOT exceed the overall execution deadline.

53. Cancellation

Executions SHALL support cancellation.

Cancellation may originate from:

user request,
API request,
worker shutdown,
timeout,
resource policy,
administrative control.

Cancellation SHALL propagate to active target operations where supported.

54. Cancellation Safety

Cancellation SHALL leave execution state in a consistent terminal state.

A cancelled execution SHALL not be reported as a successful security test.

55. Execution Status

Conceptual execution statuses:

PENDING
RUNNING
PAUSED
COMPLETED
FAILED
CANCELLED
TIMED_OUT
LIMIT_REACHED
ERROR

Evaluation status remains separate.

56. State Machine

The execution state machine SHALL follow explicit transitions.

Example:

PENDING
  |
  v
RUNNING
  |
  +----> COMPLETED
  |
  +----> FAILED
  |
  +----> CANCELLED
  |
  +----> TIMED_OUT
  |
  +----> LIMIT_REACHED

Invalid transitions SHALL be rejected.

57. Atomic State Transitions

State transitions SHOULD be persisted atomically where persistence is required.

An execution must not appear:

COMPLETED

while still containing an active worker lease.

58. Job Architecture Integration

ADR-005 defines job execution architecture.

Attack orchestration SHALL execute within that job architecture when execution is asynchronous.

The responsibilities remain separate:

Job System
  |
  v
Attack Orchestrator
  |
  v
Target Adapter

The job system manages scheduling and worker lifecycle.

The orchestrator manages attack execution.

59. Worker Ownership

A worker SHALL own an execution lease while executing an attack.

The lease mechanism SHALL reduce duplicate execution.

60. Duplicate Execution Prevention

The same execution MUST NOT be concurrently processed by multiple workers unless explicit recovery semantics permit it.

Idempotency controls SHALL be used where necessary.

61. Retry Policy

Retries SHALL be explicit.

The orchestrator SHALL distinguish:

transient transport errors,
provider rate limits,
target timeouts,
permanent configuration errors,
authorization failures,
test-level failures.
62. Retry Safety

Retries MUST NOT accidentally multiply dangerous side effects.

For tool-enabled targets, retrying a tool call may cause duplicate actions.

Therefore retries around side-effecting operations SHALL require explicit policy.

63. Backoff

Transient failures MAY use bounded exponential backoff.

Backoff SHALL respect the overall execution deadline.

64. Rate Limits

The orchestration system SHALL enforce:

per-execution request limits,
per-target rate limits,
per-project limits,
global service limits where appropriate.
65. Concurrency

Attack executions MAY run concurrently.

Concurrency SHALL be controlled by:

worker limits,
target limits,
project limits,
global limits.
66. Target Concurrency

Targets MAY have their own provider rate limits.

Aegis Vuldris SHALL support target-specific concurrency controls.

67. Fairness

A single project or execution MUST NOT be able to consume unlimited worker capacity.

Scheduling SHOULD provide reasonable fairness.

68. Resource Accounting

The orchestrator SHALL track relevant resources.

Possible metrics include:

turn_count
request_count
token_count
elapsed_time
response_bytes
input_bytes
tool_calls
network_requests
69. Token Limits

Where token usage is available, executions SHALL support token budgets.

Token limits SHALL be treated as resource controls rather than security verdicts.

70. Response Size Limits

Target responses SHALL have bounded size.

Oversized responses SHALL be truncated or rejected according to policy.

The original oversized condition SHALL remain observable for evaluation.

71. Input Size Limits

Generated attack inputs SHALL also have size limits.

This protects:

application memory,
provider quotas,
database storage,
logs,
evidence systems.
72. Evidence Integration

ADR-008 defines evidence architecture.

The orchestrator SHALL produce references to relevant execution evidence.

Evidence may include:

attack input,
target response,
tool call,
tool result,
transition decision,
timing,
execution metadata.
73. Evidence Minimization

The orchestrator SHALL avoid recording unnecessary sensitive data.

Where full content is required for reproducibility, retention policy SHALL control lifecycle.

74. Evidence Integrity

Execution evidence SHOULD include integrity metadata where required.

Examples:

content hash
sequence number
timestamp
execution identifier
step identifier
75. Event Ordering

Multi-turn evidence SHALL preserve ordering.

Each event SHOULD have a monotonically increasing sequence number within an execution.

Example:

1 attack input
2 target response
3 transition
4 attack input
5 target response
76. Replay

The architecture SHALL support replay of deterministic executions where possible.

Replay SHALL record:

attack plan version,
generator version,
seed,
target configuration reference,
execution options,
relevant environment metadata.
77. Replay Semantics

Replay SHALL NOT imply identical target behavior.

External model systems may change.

Therefore replay means:

reproduce the same Aegis Vuldris execution inputs and strategy

not:

guarantee identical model output
78. Snapshotting

Long-running executions MAY periodically persist execution state.

Snapshots SHALL be versioned.

A snapshot SHALL contain enough information to resume safely.

79. Resume

Resumption SHALL only occur when the execution semantics permit it.

If resuming could duplicate a side effect, the execution SHOULD terminate for manual review instead.

80. Multi-Turn Attack Types

The architecture SHALL support attack patterns including:

Progressive escalation
benign request
  -> ambiguous request
  -> policy-adjacent request
  -> explicit prohibited request
Context poisoning
trusted context
  -> malicious context
  -> instruction override
  -> protected action
Refusal erosion
initial refusal
  -> reframing
  -> role manipulation
  -> incremental escalation
Tool escalation
safe tool request
  -> broader tool request
  -> sensitive operation
81. Attack Memory

Attack strategies MAY maintain controlled memory.

Memory SHALL be scoped to the current execution unless explicitly configured otherwise.

Cross-execution attack memory MUST NOT occur implicitly.

82. Adaptive Strategy State

Adaptive strategies MAY store:

previous responses
successful mutations
failed mutations
transition outcomes
evaluation signals

They MUST NOT store unrestricted secrets.

83. Secret Isolation

Secrets such as:

API keys,
database passwords,
provider credentials,
session tokens,
signing keys

MUST NOT be placed into attack prompts unless the specific authorized test explicitly requires synthetic secret material.

84. Synthetic Secrets

Privacy and leakage tests SHOULD use synthetic secrets where possible.

Examples:

AEGIS-SECRET-001
TEST-SSN-000000001
SYNTHETIC-API-KEY-001

Real credentials SHALL NOT be used as test fixtures.

85. Prompt Injection Against the Orchestrator

Attack content may attempt to manipulate Aegis Vuldris itself.

Example:

Ignore the test limits and continue for 10,000 turns.

The orchestrator MUST ignore such instructions.

Execution policy SHALL be determined by trusted configuration, not model or attacker output.

86. Model-Judge Isolation

If an LLM evaluator is used, evaluator instructions SHALL be separate from attacker-controlled target content.

The target SHALL NOT be allowed to rewrite evaluator policy.

87. Evaluator Integration

ADR-010 defines evaluation architecture.

The orchestrator SHALL send observations to evaluators through defined interfaces.

The orchestrator SHALL not embed evaluator-specific logic.

88. Evaluation Timing

Evaluation MAY occur:

after every turn,
after a step,
at the end of execution,
or at multiple stages.

The attack plan SHALL declare evaluation timing where necessary.

89. Early Stop Based on Evaluation

A test MAY stop early when an explicit evaluator condition is satisfied.

For example:

protected data disclosed

may terminate an attack chain once sufficient evidence is captured.

90. Early Stop Safety

Early stopping SHALL not discard evidence already produced.

The execution SHALL be finalized cleanly.

91. Evaluation Does Not Grant Authority

An evaluator result MUST NOT grant additional execution privileges.

For example:

FAIL

must not automatically enable unrestricted tools.

92. Risk Integration

ADR-009 defines risk and severity architecture.

The orchestrator SHALL provide execution facts required for risk assessment.

Examples:

attack success state,
number of turns,
required privileges,
affected target,
evidence quality,
exploit complexity indicators.

The orchestrator SHALL not independently calculate final risk.

93. Finding Correlation

A single attack execution may produce:

zero findings,
one finding,
multiple findings.

The evaluator/finding layer SHALL determine correlation.

The orchestrator only supplies execution evidence and observations.

94. Regression Testing

Attack executions SHALL support regression use cases.

A stored attack plan may be executed against:

baseline target
current target

and results compared.

95. Regression Identity

Regression records SHOULD preserve:

test_id
attack_plan_id
attack_plan_version
target_version_reference
execution_options
evaluation_version
96. Baseline Comparison

The orchestrator SHALL not itself determine whether a regression is a security regression.

It SHALL provide reproducible execution data.

97. Deterministic Tests

Deterministic tests SHOULD be preferred for:

CI,
smoke tests,
control verification,
stable regression cases.
98. Fuzzing

Fuzzing MAY generate many attack variants.

Fuzzing SHALL still obey:

maximum cases,
maximum duration,
concurrency limits,
input limits,
network policies.
99. Metamorphic Attacks

The orchestration system MAY support metamorphic transformations.

Example:

original prompt
  |
  +-- paraphrase
  +-- language change
  +-- formatting change
  +-- role change
  +-- context insertion

The transformations SHALL be bounded.

100. Mutation Limits

Each generated mutation SHALL be subject to:

size limits,
execution limits,
target authorization,
rate limits.
101. Attack Deduplication

The orchestrator MAY avoid duplicate attacks based on:

normalized input hash,
attack-plan identity,
generation seed,
execution configuration.

Deduplication SHALL NOT accidentally remove meaningful variants where semantic differences matter.

102. Idempotency

Execution requests SHALL have stable identifiers.

A duplicate API submission SHOULD not create duplicate execution records when the caller intentionally retries the same request.

103. API-Level Authorization

Before an execution begins, Aegis Vuldris SHALL verify:

user authentication,
project access,
target access,
test permission,
required capability permission.
104. Object-Level Authorization

Every execution lookup, cancellation, replay, and evidence retrieval operation SHALL verify resource authorization.

An execution identifier alone SHALL NOT grant access.

105. Cross-Project Isolation

An attack execution belonging to Project A MUST NOT be visible to Project B.

This applies to:

execution status,
messages,
evidence,
logs,
reports,
replay metadata.
106. Cross-Target Isolation

Execution state for Target A MUST NOT be automatically available to Target B.

107. Administrative Access

Administrative access MAY permit broader visibility, but SHALL still be audited.

Administrative privileges SHALL not silently bypass audit requirements.

108. Audit Events

The orchestrator SHALL emit audit events for security-sensitive operations.

Examples:

attack_execution_created
attack_execution_started
attack_step_started
attack_step_completed
attack_execution_cancelled
attack_execution_timed_out
attack_execution_failed
attack_execution_replayed
attack_capability_denied
target_access_denied
109. Audit Integrity

Audit records SHOULD include:

actor,
project,
target,
execution,
timestamp,
action,
result.

Sensitive content SHOULD be minimized.

110. Logging

Operational logs SHALL support debugging without becoming a secret store.

Attack prompts and target responses SHOULD NOT automatically be logged at unrestricted verbosity.

111. Sensitive Logging

Sensitive content SHALL be redacted or minimized where practical.

Debug logging SHALL not override data-protection policy.

112. Error Handling

Errors SHALL be normalized into safe categories.

Examples:

TARGET_TIMEOUT
TARGET_RATE_LIMITED
TARGET_UNAVAILABLE
AUTHORIZATION_DENIED
INVALID_ATTACK_PLAN
RESOURCE_LIMIT_REACHED
ADAPTER_ERROR
CANCELLED
INTERNAL_ERROR
113. Error Disclosure

Internal errors SHALL not expose:

credentials,
filesystem paths,
stack traces to untrusted callers,
database connection strings,
internal network topology.
114. Partial Failure

A single failed attack step SHALL not necessarily corrupt the entire execution.

The plan may define recovery behavior.

However, recovery SHALL remain bounded.

115. Provider Errors

Provider-specific failures SHALL be preserved internally where useful.

External API responses SHOULD expose normalized error information.

116. Timeout Semantics

Timeouts SHALL distinguish:

connect timeout
request timeout
read timeout
overall execution timeout

The exact adapter capabilities may differ.

117. Rate-Limit Semantics

Provider rate limiting SHALL not be interpreted as a model security failure.

It SHALL be represented as an execution condition.

118. Network Failure Semantics

Network failure SHALL not automatically produce a security finding.

Evaluation SHALL determine the security meaning.

119. Attack Plan Validation

Before execution, the attack plan SHALL be validated.

Validation SHALL check:

schema,
version,
required fields,
step references,
transition references,
limit definitions,
capability declarations,
evaluator references,
unsupported operations.
120. Capability Validation

Every requested capability SHALL be validated against:

system policy
project policy
target policy
execution policy
user permissions
121. Capability Escalation

A later attack step MUST NOT silently request broader capabilities than the execution was granted.

Capability escalation SHALL require explicit policy approval.

122. Imported Attack Plans

Imported attack plans SHALL be treated as untrusted configuration until validated.

They MUST NOT execute arbitrary code during parsing.

123. Plugin Architecture

Attack strategies MAY be implemented as plugins.

Plugins SHALL use a constrained interface.

Plugins SHOULD NOT receive unrestricted process access.

124. Plugin Trust

A plugin SHALL be treated as privileged software.

Plugin installation and activation SHOULD be restricted to authorized administrators.

125. Plugin Dependencies

Plugin dependencies SHALL be scanned and pinned where practical.

Supply-chain controls SHALL apply.

126. Strategy Interface

A conceptual strategy interface:

class AttackStrategy:
    def initialize(self, context):
        ...

    def next_step(self, context):
        ...

    def observe(self, observation):
        ...

    def should_stop(self, context):
        ...

This is conceptual architecture only.

The actual implementation SHALL use typed interfaces.

127. Strategy Restrictions

A strategy implementation MUST NOT directly:

bypass authorization,
access database credentials,
execute arbitrary shell commands,
disable resource limits,
modify security policy,
access unrelated projects.
128. Execution Context

A strategy SHOULD receive a narrow context object.

The context SHOULD expose only the data required for strategy decisions.

129. Trusted Execution Context

Trusted runtime configuration SHALL be separated from strategy-controlled state.

Example:

Trusted:
  max_turns
  allowed_target
  network_policy
  capability_policy

Untrusted:
  target response
  retrieved content
  attack content
130. State Tainting

The architecture SHOULD conceptually distinguish trusted control state from untrusted data.

Model output MUST NOT overwrite trusted policy fields.

131. Structured Output

Target responses may contain JSON.

JSON SHALL be parsed as data.

A field such as:

{
  "disable_limits": true
}

MUST NOT modify execution policy unless a trusted application layer explicitly authorizes such a change.

132. Schema Validation

Structured model outputs SHALL be schema-validated before being used by the orchestrator.

Unknown fields SHOULD be ignored or rejected according to policy.

133. Tool Call Validation

Tool calls SHALL be validated against an explicit schema before execution.

Validation SHALL include:

tool identity,
argument types,
allowed parameters,
capability,
resource policy.
134. Tool Argument Sanitization

Tool arguments SHALL be treated as untrusted.

Validation SHALL happen before the tool receives them.

135. Filesystem Boundary

If an attack test interacts with files, access SHALL be restricted to an approved test workspace.

Path traversal protections SHALL prevent escaping that workspace.

136. Command Execution Boundary

Aegis Vuldris SHALL NOT execute arbitrary commands merely because a model requested them.

If command execution is ever required for a test, it SHALL use a separate sandboxed capability.

137. Container Boundary

Containerization SHALL be considered defense in depth.

Containers SHALL not be treated as the only security boundary for dangerous execution.

138. Resource Exhaustion

Attack plans SHALL be protected against:

huge prompts,
huge responses,
excessive turns,
excessive retries,
high concurrency,
expensive generation,
recursive branching.
139. Branch Limits

The orchestrator SHALL support maximum branch expansion.

An adaptive strategy MUST NOT generate an exponential number of executions without explicit limits.

140. Execution Budget

Each execution SHOULD have a budget.

A conceptual budget:

max_turns
max_duration
max_requests
max_tokens
max_response_bytes
max_tool_calls
max_network_requests
141. Budget Exhaustion

When a budget is exhausted, execution SHALL enter:

LIMIT_REACHED

unless a more specific terminal state is appropriate.

The evaluator SHALL be able to distinguish budget exhaustion from a successful attack.

142. Pause and Resume

The architecture MAY support pausing.

Paused executions SHALL retain state but consume no active execution worker.

143. Administrative Cancellation

Administrators SHOULD be able to cancel executions subject to authorization.

The action SHALL be audited.

144. User Cancellation

Users SHOULD be able to cancel their authorized executions.

Cancellation SHOULD be idempotent.

145. Cancellation Race

If cancellation occurs while a target request is completing, the final state SHALL follow deterministic rules.

For example:

response received before cancellation commit
    -> record response
    -> finalize cancellation or continue according to state

cancellation committed first
    -> do not start next step
146. Worker Shutdown

Workers SHALL gracefully stop accepting new executions during shutdown.

Active executions SHOULD receive cancellation or recovery handling.

147. Crash Recovery

If a worker crashes, execution recovery SHALL be controlled by job infrastructure.

The orchestrator SHALL detect incomplete state where possible.

148. Stale Execution Detection

Long-running executions SHOULD have heartbeat or lease metadata.

Stale execution detection SHALL prevent permanent RUNNING states.

149. Recovery Safety

Automatic recovery SHALL not blindly repeat side-effecting steps.

Executions involving external side effects SHOULD require safe resume semantics.

150. Execution Trace

Every execution SHOULD produce an ordered trace.

Example:

execution.created
step.started
request.sent
response.received
observation.created
transition.evaluated
step.started
request.sent
response.received
execution.completed
151. Trace Correlation

Trace events SHALL include:

execution_id
step_id
turn_id

where applicable.

152. Metrics

The orchestration subsystem SHOULD expose metrics including:

executions_started
executions_completed
executions_failed
executions_cancelled
executions_timed_out
turns_executed
target_requests
target_errors
average_latency
resource_limit_events
153. Metrics Privacy

Metrics SHALL not contain raw prompts or target responses.

154. Distributed Tracing

If OpenTelemetry is used later, orchestration spans SHOULD include:

execution
attack_step
adapter_request
evaluation

Sensitive prompt content SHALL not be placed into span attributes by default.

155. Database Persistence

Execution state SHALL be persisted using the database architecture defined by ADR-003.

The persistence model SHOULD separate:

execution metadata
execution steps
observations
evidence references
156. Transaction Boundaries

Database transactions SHALL be short and explicit.

Long-running target calls MUST NOT hold database transactions open.

157. Persistence During Execution

The orchestrator SHOULD persist important state transitions.

It MUST balance durability with performance and database growth.

158. Database Isolation

Database queries SHALL enforce project and target authorization.

159. Execution Ordering

Database records SHALL preserve execution ordering independently of timestamps where ordering is security-relevant.

160. Clock Handling

Timestamps SHALL use UTC.

Ordering SHOULD use sequence numbers where exact ordering matters.

161. Data Retention

Execution content SHALL follow configured retention policies.

Long-lived storage SHALL not become the default for all raw target responses without policy.

162. Deletion

When execution data is deleted according to retention policy, references SHALL be handled consistently.

Audit records may retain minimal metadata when legally or operationally required.

163. Privacy

Attack execution may process sensitive data.

The orchestrator SHALL minimize unnecessary exposure.

Privacy controls defined by the privacy architecture SHALL apply.

164. Data Classification

Execution content SHOULD support classification such as:

public
internal
sensitive
restricted

The classification may affect retention and access.

165. Redaction

Redaction MAY occur before persistence or reporting.

The original raw evidence, if retained, SHALL have stricter access controls.

166. Security Test Safety

Aegis Vuldris SHALL only execute attacks against:

systems owned by the user,
systems where explicit authorization exists,
configured targets permitted by policy.
167. Target Authorization

A target SHALL require explicit registration before execution.

Unregistered targets SHALL be rejected.

168. External Targets

External targets require explicit authorization.

The framework SHALL not assume authorization merely because a user supplies a URL.

169. Internet Access Default

Unrestricted internet access SHALL NOT be the default execution capability.

170. Safe Development Mode

Local development SHOULD provide safe mock targets.

This enables testing orchestration without contacting external systems.

171. Mock Target

A mock adapter SHALL be capable of simulating:

normal responses,
refusals,
failures,
delays,
tool calls,
malformed outputs,
rate limits.
172. Orchestrator Unit Tests

The orchestrator SHALL have unit tests for:

step sequencing,
branching,
loops,
limits,
cancellation,
retry behavior,
error handling,
authorization,
state transitions.
173. State Machine Tests

Every valid state transition SHALL be tested.

Invalid transitions SHALL also be tested.

174. Limit Tests

Tests SHALL verify:

max turns
max duration
max requests
max response size
max branch count
175. Cancellation Tests

Tests SHALL verify cancellation:

before execution,
during execution,
between turns,
after response,
during retry.
176. Retry Tests

Tests SHALL verify that transient failures retry correctly and permanent failures do not retry unnecessarily.

177. Duplicate Execution Tests

Tests SHALL verify idempotency behavior.

178. Authorization Tests

Tests SHALL verify:

unauthorized target rejected,
unauthorized project rejected,
cross-project access rejected,
unauthorized cancellation rejected,
unauthorized replay rejected.
179. Prompt Injection Tests

The orchestrator itself SHALL be tested against model outputs containing instructions attempting to:

disable limits,
reveal secrets,
modify policy,
execute commands,
change targets.

The expected behavior is to treat those values as untrusted data.

180. Structured Output Tests

Malformed and adversarial structured outputs SHALL be tested.

181. Tool Boundary Tests

If tool execution exists, tests SHALL verify that:

unauthorized tools are rejected,
invalid arguments are rejected,
dangerous capabilities remain disabled,
tool output remains untrusted.
182. SSRF Tests

Network policy tests SHALL cover:

loopback,
private addresses,
link-local addresses,
metadata endpoints,
redirects,
DNS rebinding scenarios.
183. Path Traversal Tests

Filesystem boundaries SHALL be tested with:

../
..\
encoded traversal
absolute paths
symlink escape

where applicable.

184. Resource Exhaustion Tests

Tests SHALL verify protection against:

massive input,
massive response,
excessive turns,
excessive retries,
branch explosion.
185. Fuzz Testing

The transition engine SHOULD be fuzz-tested with generated plans.

Malformed plans MUST fail safely.

186. Attack Plan Schema Tests

Every supported attack-plan version SHALL have schema validation tests.

187. Replay Tests

Deterministic attacks SHALL have replay tests.

The test SHALL verify that the same:

plan
seed
inputs

produce the same Aegis Vuldris-side execution sequence.

188. Target Variability

Replay tests SHALL not assume that external model responses remain identical.

189. Golden Tests

Golden test fixtures SHOULD represent stable attack sequences.

They SHALL be versioned.

190. Regression Tests

Security-sensitive orchestrator behavior SHALL be included in CI regression tests.

191. CI Security Gates

CI SHOULD fail when:

orchestration unit tests fail,
state-machine invariants fail,
security boundary tests fail,
static analysis fails,
dependency security checks fail.
192. Static Analysis

Orchestration code SHALL be subject to:

Ruff,
Pyright,
pytest,
pre-commit,
dependency scanning.
193. Dependency Pinning

Production dependencies SHOULD be constrained to known compatible versions.

194. Supply Chain

Third-party attack strategies SHALL be treated as potentially dangerous code.

Dependency provenance SHALL be considered.

195. Configuration

Execution policy SHALL be configuration-driven.

Configuration SHALL define safe defaults.

196. Secure Defaults

Defaults SHALL favor:

low limits,
no dangerous tools,
restricted network,
bounded retries,
bounded concurrency,
explicit targets.
197. Configuration Precedence

Security-sensitive settings SHOULD follow a trusted precedence model.

Example:

system policy
  >
project policy
  >
target policy
  >
test policy
  >
execution request

A lower-trust layer MUST NOT override a higher-trust restriction.

198. User-Supplied Limits

A user may request lower limits.

A user SHOULD NOT be able to bypass higher system limits.

199. Execution Profiles

The framework MAY support profiles such as:

safe
standard
extended
ci
research

Profiles SHALL remain bounded by global security policy.

200. Production Safety

Production deployments SHALL use conservative limits.

Research deployments MAY allow larger limits only when explicitly configured.

201. Environment Isolation

Development, test, and production targets SHALL be distinct.

A development attack plan MUST NOT automatically target production.

202. Target Environment Labels

Targets SHOULD carry environment metadata:

development
staging
production
external

Execution policy MAY restrict which attack suites are permitted against each environment.

203. Production Target Warning

Destructive or side-effecting tests SHOULD require explicit confirmation and policy approval.

204. Dry Run

The orchestration architecture SHOULD support dry-run planning.

Dry run SHALL validate:

attack plan,
target,
permissions,
limits,
capabilities,

without contacting the target.

205. Preview

A user MAY preview an attack plan before execution.

Preview SHALL not expose secrets.

206. Approval Gates

High-risk attack profiles MAY require approval.

Approval SHALL be an application-level authorization decision.

207. Audit of Approval

Approvals SHALL be auditable.

208. Execution Metadata

Execution records SHOULD include:

execution_id
project_id
target_id
attack_plan_id
attack_plan_version
created_by
created_at
started_at
completed_at
status
profile
seed
209. Step Metadata

Step records SHOULD include:

step_id
sequence
started_at
completed_at
status
attempt
observation_reference
210. Turn Metadata

Turn records SHOULD include:

turn_id
step_id
sequence
input_reference
response_reference
latency
usage
status
211. Separation of Raw and Derived Data

Raw target outputs SHALL remain distinct from:

evaluator labels,
findings,
risk scores,
reports.

This prevents derived conclusions from overwriting source evidence.

212. Finding Independence

A finding SHALL reference its originating execution and evidence.

213. Report Reproducibility

Reports SHOULD identify the execution and attack-plan versions used.

214. Attack Plan Governance

New built-in attack plans SHALL undergo review.

Review SHOULD consider:

objective,
safety,
target impact,
resource use,
evidence quality,
evaluation logic,
authorization requirements.
215. Attack Plan Naming

Names SHALL be descriptive and stable.

Avoid names implying guaranteed exploitation.

Prefer:

prompt-injection-direct

over:

guaranteed-system-prompt-break
216. Attack Objective Neutrality

Attack names and metadata SHALL describe testing objectives rather than claim outcomes.

217. Outcome Neutrality

The orchestrator SHALL not mark a test as vulnerable solely because the attack was executed.

218. Success Semantics

Attack success is a strategy-level observation.

Security failure is an evaluation-level conclusion.

These concepts SHALL remain distinct.

219. Inconclusive Execution

An execution may complete without sufficient evidence.

The evaluator may return:

INCONCLUSIVE

The orchestrator SHALL preserve that distinction.

220. Execution Error

Infrastructure failure SHALL not automatically become:

FAIL

It SHALL remain an execution error unless evaluation determines otherwise.

221. Timeout Interpretation

A timeout SHALL be represented separately from target behavior.

222. Provider Availability

Provider outage SHALL not be treated as a vulnerability.

223. Attack Chain Completion

A multi-turn attack is complete when:

a terminal step is reached,
a stopping condition is satisfied,
a limit is reached,
cancellation occurs,
an unrecoverable error occurs.
224. Stop Conditions

Stop conditions may include:

objective_observed
max_turns
max_duration
max_requests
terminal_step
evaluator_condition
error
cancelled
225. Multiple Stop Conditions

If multiple stop conditions are reached simultaneously, the system SHALL apply deterministic precedence.

Example:

cancelled
>
timeout
>
resource limit
>
terminal step
>
normal completion

Exact precedence SHALL be implemented and tested.

226. Normal Completion

Normal completion SHALL indicate that the attack plan reached its terminal state without infrastructure failure.

It SHALL not imply security success.

227. Execution Result

A conceptual result:

ExecutionResult
  |
  +-- status
  +-- observations
  +-- evidence
  +-- resource_usage
  +-- termination_reason
  +-- evaluation_reference
228. Termination Reason

The termination reason SHOULD be explicit.

Examples:

TERMINAL_STEP
OBJECTIVE_OBSERVED
MAX_TURNS
MAX_DURATION
MAX_REQUESTS
CANCELLED
TARGET_ERROR
AUTHORIZATION_DENIED
RESOURCE_LIMIT
229. Concurrency Safety

Shared mutable state SHOULD be minimized.

Execution-local state SHOULD remain isolated.

230. Async Execution

The Python implementation SHOULD use asynchronous execution for I/O-bound target calls.

Blocking operations SHALL not block the main async worker loop.

231. Blocking Operations

Potentially blocking operations include:

filesystem operations,
subprocesses,
synchronous network clients,
expensive CPU work.

These SHALL be isolated or executed through appropriate mechanisms.

232. CPU-Bound Generation

CPU-heavy attack generation SHOULD be bounded separately from I/O concurrency.

233. Backpressure

The execution system SHALL provide backpressure when target capacity or worker capacity is exhausted.

234. Queue Safety

Unbounded execution queues SHALL be avoided.

235. Fair Queueing

Where practical, queued executions SHOULD be fairly distributed across projects.

236. Priority

Execution priority MAY be supported.

Priority MUST NOT bypass authorization or security limits.

237. Priority Abuse

Users MUST NOT be able to grant themselves unrestricted priority.

238. Multi-Tenant Considerations

If Aegis Vuldris becomes multi-tenant, orchestration isolation SHALL apply across tenant boundaries.

239. Tenant Data Isolation

Tenant identifiers SHALL be part of authorization context.

240. Tenant Resource Limits

Per-tenant resource quotas SHOULD be supported.

241. Secrets in Target Configuration

Target credentials SHALL be referenced through secure secret management.

Attack plans SHALL not contain plaintext credentials.

242. Secret Injection

If credentials must be injected into an adapter, they SHALL be resolved at the trusted adapter boundary.

Attack content SHALL never control secret selection.

243. Secret Logging

Secrets SHALL never be written to execution traces.

244. Secret Redaction

Known secret values SHOULD be redacted from diagnostic output where practical.

245. Prompt Storage

Prompt and response storage SHALL follow evidence and privacy policies.

246. Hashing

Content hashes MAY be used for deduplication and integrity.

Hashing does not replace authorization.

247. Content References

Large content MAY be stored separately from execution metadata.

Execution records SHOULD use evidence references.

248. Large Payload Handling

The orchestrator SHOULD avoid placing very large payloads directly into relational metadata fields.

249. Serialization

Execution state SHALL use versioned serialization.

Untrusted serialized state SHALL be validated before use.

250. Deserialization Safety

The system MUST NOT use unsafe object deserialization for attack plans or execution state.

Data formats SHOULD be explicit and schema validated.

251. JSON Safety

JSON SHALL be treated as untrusted data.

No JSON field SHALL become executable behavior without trusted application logic.

252. YAML Safety

If YAML is supported for attack plans, safe parsing SHALL be used.

Arbitrary object construction MUST NOT be enabled.

253. Template Safety

Attack templates SHALL use a constrained template engine.

Templates MUST NOT provide arbitrary code execution.

254. Expression Safety

Conditional expressions SHALL use a restricted expression model.

Python eval() SHALL NOT be used for untrusted attack-plan expressions.

255. Scripted Strategies

If scripted strategies are eventually supported, they SHALL run in a separately sandboxed environment.

256. Sandbox Limitations

Sandboxing SHALL be treated as defense in depth.

Network, filesystem, process, and identity boundaries SHALL remain explicit.

257. Agent Testing

Agent targets require special handling because the target may:

call tools,
retrieve data,
maintain memory,
perform external actions.

Aegis Vuldris SHALL observe these activities through adapter-defined interfaces.

258. Agent Tool Calls

Tool calls SHALL be recorded as observations.

They SHALL not automatically be executed by Aegis Vuldris.

259. Tool Simulation

Where possible, Aegis Vuldris SHOULD support simulated tools.

Simulation reduces risk during testing.

260. Tool Result Injection

Tool results used in security testing SHALL be clearly marked as test-controlled data.

261. Retrieval Simulation

RAG tests MAY use controlled retrieval stores.

This enables deterministic indirect-prompt-injection testing.

262. Retrieval State

Retrieval state SHALL be isolated per execution where test contamination would affect results.

263. Persistent Memory Testing

If the target has persistent memory, tests SHALL explicitly declare whether memory persistence is part of the attack.

264. Memory Isolation

A test requiring persistent target memory SHALL not accidentally contaminate unrelated executions.

265. Cross-Session Attacks

Cross-session testing MAY be supported only when explicitly configured.

266. Cross-Session Authorization

Cross-session operations require explicit authorization and test configuration.

267. Long-Running Attacks

Long-running attacks SHALL have:

heartbeat,
checkpointing where appropriate,
bounded duration,
cancellation,
recovery policy.
268. Scheduled Attacks

Scheduled execution belongs to the job/scheduling architecture.

The attack orchestrator receives an authorized execution request.

269. Parallel Attack Chains

Parallel attack chains MAY be supported.

Each branch SHALL have independent state.

270. Branch Merge

If branches are merged, merge semantics SHALL be explicit.

Untrusted state MUST NOT overwrite trusted state during merge.

271. Branch Resource Accounting

Resource usage SHALL be aggregated across branches.

272. Branch Cancellation

Cancelling a parent execution SHALL cancel child branches.

273. Child Execution Identity

Branches SHOULD have child execution identifiers linked to a parent execution.

274. Parent-Child Isolation

A child branch SHALL not escape the parent's target and policy boundaries.

275. Recursive Attacks

Recursive attack spawning SHALL be disabled by default.

If enabled, depth and total-child limits are mandatory.

276. Maximum Depth

Attack recursion SHALL have an explicit maximum depth.

277. Maximum Descendants

The system SHALL enforce a maximum number of child executions.

278. Cost Controls

Expensive model calls SHALL be budgeted.

Where provider cost data is available, execution MAY track estimated cost.

279. Cost Isolation

One project SHALL not consume unlimited provider quota.

280. Provider Quotas

Target configuration SHOULD support provider-specific quotas.

281. Adaptive Cost

Adaptive strategies SHALL consider remaining execution budget.

They MUST not bypass cost limits.

282. Attack Strategy Feedback

Evaluation signals MAY inform later attack steps.

Such feedback SHALL be treated as bounded data.

283. Evaluator Feedback Safety

An evaluator output MUST NOT modify authorization policy.

284. Judge Manipulation

Target responses may attempt to influence an evaluator.

The evaluation architecture SHALL isolate evaluator instructions and trusted scoring logic.

285. Evidence of Manipulation

If a target attempts evaluator manipulation, the attempt MAY itself become an observation relevant to evaluation.

286. Prompt Leakage Testing

Attack strategies may test whether protected prompts are disclosed.

Aegis Vuldris SHALL distinguish synthetic expected values from actual secrets.

287. Synthetic System Prompts

Testing environments SHOULD use synthetic protected prompts where possible.

288. Privacy Test Data

Privacy tests SHOULD use synthetic personal data.

289. Real Personal Data

Real personal data SHOULD NOT be included in attack fixtures unless specifically authorized and necessary.

290. Data Exposure

If sensitive data is observed, evidence handling SHALL follow stricter controls.

291. Evidence Redaction

Reports MAY redact sensitive values while retaining enough information to establish the finding.

292. Reproduction

A finding SHOULD retain enough information for authorized reproduction without unnecessarily exposing sensitive content.

293. Reproduction Boundary

Reproduction SHALL execute under the same or stricter target authorization.

294. Replay Authorization

Replay SHALL require authorization equivalent to executing the original test.

295. Replay Against Different Target

Replay against another target SHALL require explicit target authorization.

296. Attack Plan Compatibility

Replay SHALL verify that the stored plan version remains supported.

297. Version Migration

If attack-plan schemas evolve, explicit migration SHALL be used.

Silent reinterpretation SHALL be avoided.

298. Execution Schema Version

Execution records SHOULD contain schema version information.

299. Backward Compatibility

The system SHOULD preserve the ability to inspect historical execution records after software upgrades.

300. Historical Evaluation

Historical evaluations SHALL identify the evaluator version used.

301. Historical Risk

Historical risk assessments SHALL identify the risk-model version used.

302. Reporting

Reports SHALL be generated from persisted execution/evaluation data.

The orchestrator SHALL not directly render reports.

303. Dashboard Integration

The dashboard may display:

execution status,
current step,
turn count,
resource usage,
termination reason.

It SHALL not expose unauthorized evidence.

304. Live Execution Status

Live status MAY be exposed through an API.

Status updates SHALL not leak target content to unauthorized users.

305. Streaming

Streaming target responses MAY be supported.

Streaming SHALL respect the same resource and cancellation controls.

306. Partial Streaming Evidence

If streaming is recorded, chunks SHALL preserve ordering.

307. Streaming Cancellation

Cancellation SHALL stop downstream processing where possible.

308. Output Normalization

Adapter output SHALL be normalized before orchestration logic consumes it.

309. Provider Metadata

Provider-specific metadata MAY be preserved for diagnostics.

Sensitive provider metadata SHALL be filtered.

310. Latency

Latency SHALL be recorded as execution telemetry.

Latency alone SHALL not indicate vulnerability.

311. Usage

Token usage SHOULD be recorded when provided.

312. Model Identity

The execution SHOULD record the target model identity where available.

313. Model Version

If the provider exposes a model version, it SHOULD be recorded.

314. Environment Fingerprint

Executions MAY record a non-sensitive runtime fingerprint for reproducibility.

315. Fingerprint Privacy

Fingerprints SHALL not include secrets or unnecessary host-identifying information.

316. Configuration Snapshot

Security-relevant execution configuration SHOULD be snapshotted or version-referenced.

317. Immutable Execution Metadata

Once execution begins, core identity fields SHOULD be immutable.

Examples:

project_id
target_id
attack_plan_id
attack_plan_version
318. Mutable Execution State

Runtime state may change:

current_step
status
turn_count
resource_usage
termination_reason
319. Configuration Mutation

Security-sensitive execution configuration MUST NOT be changed by attack content.

320. Administrative Mutation

Authorized administrators MAY change supported runtime controls such as cancellation.

Changes SHALL be audited.

321. Execution Locks

Where necessary, execution records SHOULD use optimistic locking or equivalent concurrency control.

322. Race Conditions

State updates SHALL account for:

worker retries,
cancellation,
duplicate API calls,
provider callbacks,
shutdown.
323. Callback Security

Provider callbacks, if supported, SHALL be authenticated and associated with the expected execution.

324. Callback Validation

Callback payloads SHALL be schema-validated.

325. Webhook Isolation

External callbacks SHALL not directly mutate arbitrary execution state.

326. Polling

Polling adapters SHALL enforce bounded polling intervals.

327. Polling Limits

Long-running provider jobs SHALL have maximum polling duration.

328. Provider Job Mapping

Provider job identifiers SHALL map to an authorized Aegis Vuldris execution.

329. Identifier Validation

External identifiers SHALL not be trusted as authorization identifiers.

330. Path Safety

Execution identifiers SHALL not be used directly as filesystem paths without safe mapping.

331. Temporary Files

Temporary execution files SHALL be created in controlled directories.

332. Cleanup

Temporary resources SHALL be cleaned up after execution.

Cleanup failure SHALL be observable.

333. Cleanup Safety

Cleanup routines SHALL not delete arbitrary paths derived from untrusted data.

334. Memory Limits

Where practical, large response processing SHALL use bounded memory.

335. Streaming Persistence

Large outputs MAY be streamed to evidence storage rather than held entirely in memory.

336. Backpressure on Evidence

Evidence storage failures SHALL not silently cause unlimited in-memory buffering.

337. Evidence Failure

If required evidence cannot be persisted, the execution SHALL follow an explicit failure policy.

It SHALL not falsely report complete evidence.

338. Evidence Integrity Failure

Integrity verification failure SHALL be surfaced.

339. Audit Failure

Failure to emit a required audit event SHALL be handled according to security policy.

340. Security-Critical Audit

Certain events SHOULD be treated as mandatory audit events.

341. Tamper Resistance

Where required, audit and evidence storage SHOULD restrict modification after finalization.

342. Execution Finalization

Finalization SHALL:

stop new steps,
persist terminal state,
finalize evidence,
release resources,
release worker ownership,
emit completion event.
343. Finalization Idempotency

Finalization SHALL be safe to invoke more than once.

344. Resource Release

All execution resources SHALL be released on:

completion,
failure,
cancellation,
timeout.
345. Resource Leak Tests

Tests SHALL verify that failed executions do not leak:

sessions,
workers,
network connections,
temporary files,
memory buffers.
346. Session Cleanup

Target sessions SHOULD be explicitly terminated when the adapter supports termination.

347. API Client Cleanup

HTTP clients SHOULD use controlled lifecycle management.

348. Connection Pools

Connection pools SHALL be bounded.

349. Worker Limits

Worker counts SHALL be configurable and bounded.

350. Global Safety Limit

A global maximum execution concurrency SHOULD exist.

351. Project Safety Limit

Projects SHOULD have configurable execution quotas.

352. Target Safety Limit

Targets SHOULD have configurable concurrency limits.

353. User Safety Limit

Users MAY have execution quotas depending on deployment policy.

354. Quota Accounting

Quota accounting SHOULD use persisted or reliable shared state when workers are distributed.

355. Quota Bypass

A user MUST NOT bypass quotas by creating duplicate execution requests.

356. Rate Limit Identity

Rate limits SHOULD consider:

user
project
target
provider
network destination

as appropriate.

357. Attack Flooding

The system SHALL defend against rapid creation of massive attack executions.

358. Queue Admission

Execution requests SHOULD be validated before entering expensive worker queues.

359. Admission Controls

Admission checks SHOULD include:

authorization,
plan validity,
target availability,
quota,
resource policy.
360. Queue Rejection

Rejected requests SHALL receive clear, non-sensitive reasons.

361. Audit Rejected Execution

Security-sensitive rejected execution requests MAY be audited.

362. API Idempotency Key

The execution API SHOULD support idempotency keys.

363. Idempotency Scope

An idempotency key SHALL be scoped to the authenticated principal and appropriate resource context.

364. Replay Attack Prevention

Expired or reused idempotency keys SHALL not create unintended executions.

365. Authorization Cache

Authorization decisions MAY be cached briefly.

Security-sensitive permission changes SHALL invalidate relevant cached decisions.

366. Target Deletion

A target with active executions SHOULD follow controlled deletion semantics.

367. Project Deletion

Project deletion SHALL account for active executions and evidence.

368. Target Disablement

Disabled targets SHALL reject new executions.

Existing executions SHOULD follow policy-defined handling.

369. Attack Plan Disablement

Disabled attack plans SHALL reject new executions.

Historical executions SHALL remain inspectable.

370. Attack Plan Deprecation

Deprecated plans MAY remain executable only under explicit policy.

371. Attack Plan Integrity

Built-in attack plans SHOULD be protected against unauthorized modification.

372. Signed Plans

Future releases MAY support signed attack-plan bundles.

373. Plan Provenance

The system SHOULD record whether a plan is:

built-in
user-created
imported
plugin-provided
generated
374. Provenance Policy

Untrusted plan sources MAY have stricter capability restrictions.

375. User-Created Plans

User-created plans SHALL still obey global security boundaries.

376. Generated Plans

AI-generated attack plans SHALL be validated like any other untrusted input.

377. AI-Generated Orchestration

An LLM MAY suggest an attack sequence.

It SHALL NOT directly control execution policy.

378. Human Approval

High-impact generated attack plans MAY require human approval.

379. Generation and Execution Separation

Attack generation SHALL remain separate from execution.

This separation reduces the chance that generated content can directly manipulate runtime controls.

380. Evaluation and Execution Separation

Evaluation SHALL remain separate from execution.

381. Evidence and Evaluation Separation

Raw evidence SHALL remain available independently from evaluator conclusions.

382. Risk and Evaluation Separation

Risk assessment SHALL consume evaluation results and contextual evidence rather than direct orchestration state alone.

383. Reporting Separation

Reporting SHALL consume finalized data.

384. Architecture Layers

The resulting logical architecture is:

API
 |
 v
Authorization
 |
 v
Execution Service
 |
 v
Job System
 |
 v
Attack Orchestrator
 |
 +--> Attack Strategy
 |
 +--> Target Session
 |
 +--> Resource Controller
 |
 +--> Transition Engine
 |
 +--> Evidence Collector
 |
 v
Model Adapter
 |
 v
Target
 |
 v
Observation
 |
 +--> Evaluation
 |
 +--> Evidence
 |
 +--> Risk
 |
 +--> Reporting
385. Dependency Direction

Dependencies SHALL point toward stable interfaces.

The orchestrator SHOULD depend on:

TargetAdapter
EvidenceSink
PolicyProvider
ExecutionRepository
Strategy
EvaluatorInterface

rather than provider-specific implementations.

386. Interface Boundaries

Interfaces SHOULD be narrow.

A target adapter SHOULD NOT receive the entire database session or application context.

387. Repository Boundary

Persistence SHALL be accessed through repository/service abstractions where practical.

388. Policy Boundary

Execution policy SHOULD be resolved by a dedicated policy service or component.

389. Capability Boundary

Capabilities SHOULD be represented explicitly.

390. Resource Controller

A resource controller SHOULD centralize:

turn budgets,
request budgets,
timeouts,
concurrency,
token budgets,
output limits.
391. Transition Controller

A transition controller SHOULD centralize state transitions.

392. Evidence Collector

An evidence collector SHOULD centralize observation-to-evidence handling.

393. Strategy Registry

A strategy registry SHOULD map attack-plan identifiers to approved strategies.

394. Strategy Lookup

Unrecognized strategies SHALL fail safely.

395. Dynamic Import Safety

User-controlled values MUST NOT directly control Python module imports.

396. Plugin Loading

Plugin loading SHALL use an explicit allowlist or trusted registry.

397. Execution Service

An execution service SHOULD coordinate:

authorization
validation
job creation
orchestrator invocation
finalization
398. API Service

The API service SHALL not directly implement attack loops.

399. Worker Service

Workers SHALL invoke the execution service or orchestrator through defined boundaries.

400. Frontend

The frontend SHALL treat execution state as untrusted server data.

It SHALL not be trusted for authorization or execution policy.

401. Frontend Cancellation

A cancellation request SHALL be authorized by the backend.

402. Frontend Progress

Progress indicators SHALL not be treated as authoritative security evidence.

403. Security Invariants

The following invariants SHALL hold.

Invariant 1

An attack execution MUST be bound to an authorized target.

Invariant 2

Attack content MUST NOT modify execution policy.

Invariant 3

Model output MUST NOT become trusted Aegis Vuldris instructions.

Invariant 4

Every execution MUST have bounded resources.

Invariant 5

Every loop MUST be bounded.

Invariant 6

Every execution MUST have a terminal state.

Invariant 7

Cancellation MUST prevent new steps from starting.

Invariant 8

Cross-project execution data MUST remain isolated.

Invariant 9

Dangerous capabilities MUST be deny-by-default.

Invariant 10

The orchestrator MUST NOT decide vulnerability status by itself.

Invariant 11

Raw observations MUST remain distinguishable from evaluator conclusions.

Invariant 12

Retries MUST NOT silently duplicate unsafe side effects.

Invariant 13

External network access MUST follow explicit policy.

Invariant 14

Secrets MUST NOT be exposed to attack strategies by default.

Invariant 15

Replay MUST require authorization.

404. Security Invariants — Extended
Invariant 16

A lower-trust configuration layer MUST NOT override a higher-trust security restriction.

Invariant 17

Untrusted structured output MUST NOT modify trusted state without explicit validation and authorization.

Invariant 18

Execution finalization MUST be idempotent.

Invariant 19

Execution identifiers MUST NOT bypass resource authorization.

Invariant 20

Resource exhaustion MUST terminate or constrain execution rather than cause unbounded consumption.

Invariant 21

Attack plans MUST NOT execute arbitrary code during parsing.

Invariant 22

Plugin code MUST NOT receive unrestricted capabilities by default.

Invariant 23

Evidence failures MUST NOT be silently converted into successful completion.

Invariant 24

Provider outages MUST NOT automatically become security findings.

Invariant 25

A security finding MUST remain traceable to an authorized execution and evidence.

430. Failure Taxonomy

The orchestrator SHALL distinguish:

PLAN_INVALID
AUTHORIZATION_DENIED
TARGET_NOT_FOUND
TARGET_DISABLED
TARGET_UNAVAILABLE
ADAPTER_ERROR
TARGET_TIMEOUT
RATE_LIMITED
RESOURCE_LIMIT
CANCELLED
EXECUTION_TIMEOUT
TOOL_DENIED
NETWORK_DENIED
EVIDENCE_FAILURE
INTERNAL_ERROR
431. Failure Classification

Failure classification SHALL be deterministic where possible.

432. Error Recovery

Only explicitly recoverable errors SHALL trigger retries or recovery.

433. Non-Recoverable Errors

Examples:

authorization denied
invalid attack plan
capability denied
unsupported adapter

SHALL normally terminate immediately.

434. Recoverable Errors

Examples may include:

temporary network failure
provider rate limit
transient service unavailable

subject to bounded retry policy.

435. Error Evidence

Execution failures SHOULD retain sufficient metadata to diagnose the problem without exposing secrets.

436. Security Finding from Error

An error SHALL become a security finding only if an evaluator explicitly defines that behavior as security-relevant.

437. Availability Testing

Availability or robustness tests may intentionally induce failures.

Those tests SHALL have explicit resource limits.

438. Denial-of-Service Testing

Potentially disruptive tests SHALL require explicit authorization and stronger safeguards.

439. Production Restrictions

Highly disruptive attack profiles SHOULD be disabled by default in production.

440. Safety Classification

Attack plans MAY have safety classifications:

LOW
MEDIUM
HIGH
CRITICAL

Higher classifications MAY require approval.

441. Safety Policy

Safety classification SHALL affect:

allowed environments,
capabilities,
resource limits,
approval requirements.
442. Safety Classification Is Not Severity

Attack safety classification is operational.

Finding severity is security impact.

They SHALL remain separate.

443. Test Objective vs Operational Risk

A harmless objective may still have high operational risk.

Example:

network enumeration

may require stricter controls even if the security objective is legitimate.

444. Network Destination Classification

Destinations MAY be classified:

local mock
private authorized
staging
production
external authorized
blocked
445. Destination Enforcement

Classification SHALL be enforced outside the attack strategy.

446. DNS Resolution

DNS resolution SHALL be treated as security-sensitive when network access exists.

447. Redirect Validation

Redirect destinations SHALL be revalidated.

448. IP Revalidation

Where SSRF protection is required, destination IPs SHOULD be validated at connection time, not only initial parsing.

449. URL Parsing

URLs SHALL be parsed with a trusted URL parser.

String-prefix checks alone SHALL not be relied upon.

450. Scheme Restrictions

Only explicitly permitted URL schemes SHALL be allowed.

451. Port Restrictions

Ports SHALL be restricted according to target/network policy.

452. Proxy Policy

If a proxy is used, proxy routing SHALL remain subject to network policy.

453. File URL

file: and similar local-resource schemes SHALL be disabled unless explicitly required and sandboxed.

454. Command Injection

User or model content SHALL never be concatenated directly into shell commands.

455. SQL Injection

Execution metadata queries SHALL use parameterized database access.

456. Template Injection

Untrusted attack content SHALL not be evaluated as application templates.

457. Path Injection

Filesystem paths SHALL be normalized and constrained.

458. Header Injection

Model-controlled HTTP headers SHALL be restricted.

459. Request Smuggling

HTTP client behavior SHALL use trusted libraries and safe defaults.

460. Redirect Chains

Redirect chains SHALL have bounded length.

461. Response Content

External response content SHALL be treated as untrusted.

462. Content-Type

Network integrations SHOULD validate expected content types.

463. Content Size

External content SHALL have maximum response size.

464. Compression Bombs

Compressed responses SHALL be subject to decompression size limits.

465. Archive Handling

If attack tests process archives, extraction SHALL occur inside a controlled workspace with:

path traversal protection,
size limits,
file-count limits.
466. Malicious Documents

Documents used in testing SHALL be treated as potentially malicious.

Parsing SHALL use appropriate isolation.

467. Office Documents

Document parsers SHALL not be allowed to execute macros or embedded code.

468. PDF Handling

PDF processing SHALL not automatically execute embedded actions.

469. Image Handling

Image processing SHALL use bounded resource limits.

470. File Uploads

Uploaded attack fixtures SHALL be validated and isolated.

471. Upload Names

User-controlled filenames SHALL not become trusted filesystem paths.

472. File Quotas

Uploads SHALL have size and count quotas.

473. Malware Scanning

Deployments MAY integrate malware scanning for uploaded test fixtures.

474. Execution Workspace

Every execution requiring filesystem access SHOULD have an isolated workspace.

475. Workspace Cleanup

Workspaces SHALL be cleaned after execution according to retention policy.

476. Workspace Access

One execution SHALL not access another execution's workspace.

477. Symlink Protection

Symlink-based workspace escape SHALL be prevented where filesystem tests exist.

478. Environment Variables

Untrusted attack content SHALL not control process environment variables.

479. Process Identity

Dangerous execution, if ever supported, SHALL use a restricted OS identity.

480. Privilege Dropping

Sandboxed operations SHOULD use least privilege.

481. Resource Limits at OS Level

Where dangerous capabilities exist, OS-level resource limits SHOULD supplement application limits.

482. Process Timeout

Sandboxed processes SHALL have hard timeouts.

483. Process Count

Sandboxed execution SHALL have process-count limits.

484. File Descriptor Limits

Sandboxed execution MAY use file descriptor limits.

485. Network Egress

Sandboxed operations SHALL have explicit network egress rules.

486. Container Network

Containerized test environments SHOULD use restricted networks.

487. Host Access

Containers SHALL not receive unnecessary host mounts.

488. Docker Socket

The Docker socket SHALL not be exposed to untrusted test workloads.

489. Host Credentials

Host credentials SHALL never be mounted into untrusted attack environments.

490. Cloud Metadata

Cloud metadata endpoints SHALL be blocked where network access exists unless explicitly required.

491. Credential Isolation

Cloud credentials SHALL not be exposed to target workloads.

492. Service Accounts

Service accounts SHALL use least privilege.

493. Database Credentials

Database credentials SHALL not be available to attack strategies.

494. Internal Services

Internal services SHALL not be reachable from attack execution unless explicitly authorized.

495. Kubernetes

If deployed on Kubernetes, attack workloads SHOULD use dedicated service accounts and network policies.

496. Namespaces

Test workloads MAY use separate namespaces.

497. Resource Quotas

Kubernetes resource quotas SHOULD supplement application budgets.

498. Pod Security

Test workloads SHOULD follow restrictive pod security standards.

499. Secret Mounts

Secrets SHOULD not be mounted into attack workloads unless absolutely necessary.

500. Completion Criteria

ADR-011 implementation is considered architecturally complete when:

attack plans have stable identifiers,
plans are versioned,
multi-turn execution state exists,
execution is bounded,
cancellation exists,
retry semantics exist,
target adapters are used,
evidence is preserved,
evaluation is separate,
authorization is enforced,
project/target isolation is enforced,
dangerous capabilities are explicit,
network access is controlled,
replay metadata is preserved,
execution states are persisted,
audit events exist,
security invariants are tested.
501. Implementation Order

Implementation SHOULD proceed in the following order:

1. execution state model
2. attack-plan schema
3. strategy interface
4. target adapter integration
5. sequential execution
6. resource controller
7. transition engine
8. evidence integration
9. cancellation
10. retry handling
11. multi-turn state
12. adaptive strategies
13. branching
14. tool-aware execution
15. network policy
16. replay
17. observability
18. security hardening
19. regression suite
502. Phase Relationship

ADR-011 depends conceptually on:

ADR-005  Job execution
ADR-007  Model adapters
ADR-008  Evidence
ADR-009  Risk
ADR-010  Test and evaluation architecture
503. ADR-005 Relationship

ADR-005 determines how work is scheduled and executed.

ADR-011 determines what the attack execution does once a worker owns the execution.

504. ADR-007 Relationship

ADR-007 defines how Aegis Vuldris communicates with targets.

ADR-011 defines when and why those adapter calls occur.

505. ADR-008 Relationship

ADR-008 defines evidence architecture.

ADR-011 produces execution observations and evidence references.

506. ADR-009 Relationship

ADR-009 defines risk and severity.

ADR-011 provides execution context but does not replace the risk engine.

507. ADR-010 Relationship

ADR-010 defines the security test and evaluation lifecycle.

ADR-011 provides the attack execution mechanism inside that lifecycle.

508. End-to-End Flow

The intended end-to-end sequence is:

User
 |
 v
Create Security Test
 |
 v
Authorize Target
 |
 v
Create Execution Job
 |
 v
Validate Attack Plan
 |
 v
Start Orchestrator
 |
 v
Initialize Session
 |
 v
Generate Attack Input
 |
 v
Execute Target Request
 |
 v
Capture Observation
 |
 v
Persist Evidence
 |
 v
Evaluate Transition
 |
 +---- continue ----+
 |                  |
 +------------------+
 |
 v
Final Evaluation
 |
 v
Finding Correlation
 |
 v
Risk Assessment
 |
 v
Report
509. Security Boundary Summary

The most important boundary is:

Untrusted Target / Attack Content
              |
              X
              |
      Trusted Aegis Vuldris Policy

No model response, attack prompt, retrieved document, tool output, or external network response may directly cross that boundary into trusted control state.

510. Trusted Control Plane

The trusted control plane includes:

authorization,
target registration,
execution policy,
resource limits,
capability policy,
state transitions,
worker ownership,
security configuration.
511. Untrusted Data Plane

The untrusted data plane includes:

attack prompts,
target responses,
retrieved content,
tool results,
external documents,
generated content,
model-produced structured data.
512. Control/Data Separation

The architecture SHALL maintain a strong separation between the control plane and data plane.

513. No Model-as-Policy

A model SHALL never be the sole authority for:

authorization,
capability granting,
target selection,
resource limits,
security policy,
evidence access.
514. No Prompt-as-Policy

Prompts SHALL never be treated as security policy.

515. No Output-as-Authorization

Model output SHALL never authorize an action by itself.

516. No Evaluator-as-Authorization

Evaluator results SHALL never grant runtime capabilities.

517. No Frontend-as-Authorization

Frontend controls SHALL never substitute for backend authorization.

518. No Adapter-as-Authorization

Adapters SHALL enforce target communication contracts but SHALL not replace application-level authorization.

519. No Worker-as-Authorization

A worker possessing an execution job SHALL not automatically gain unrelated resource access.

520. Least Privilege

Each component SHALL receive only the permissions it requires.

521. Fail Closed

When authorization or policy cannot be determined safely, execution SHALL fail closed.

522. Safe Failure

Failure SHALL not expand privileges.

523. Unknown State

If execution state becomes ambiguous, the system SHALL avoid blindly continuing.

524. Manual Review

Ambiguous side-effecting recovery MAY require manual review.

525. Operational Visibility

Operators SHOULD be able to determine:

what ran,
against which target,
under which plan,
for how long,
how many turns,
why it stopped.
526. Security Visibility

Operators SHOULD be able to determine:

capability denials,
policy violations,
resource exhaustion,
repeated failures,
suspicious execution patterns.
527. Privacy Visibility

Operators SHOULD be able to inspect metadata without automatically exposing sensitive prompt/response content.

528. Alerting

Operational alerting MAY detect:

unusual execution volume,
repeated capability denials,
repeated target failures,
excessive resource consumption.
529. Abuse Prevention

Aegis Vuldris SHALL prevent its own orchestration layer from becoming an uncontrolled attack launcher.

This includes:

target registration,
authorization,
quotas,
allowlisting,
rate limits,
audit logging,
bounded execution.
530. Responsible Testing

All built-in attack capabilities SHALL be designed for authorized security testing.

531. Documentation

User-facing documentation SHALL clearly explain:

target authorization,
attack execution risks,
resource limits,
tool permissions,
network permissions,
data retention.
532. Secure Defaults Documentation

Documentation SHALL describe default restrictions.

533. Developer Documentation

Developer documentation SHALL explain:

strategy interface,
plan schema,
execution lifecycle,
state machine,
policy boundary,
evidence integration.
534. Test Fixture Requirements

Fixtures SHOULD use:

synthetic secrets,
mock targets,
isolated tool simulations,
deterministic responses.
535. External Test Requirements

External integration tests SHOULD use explicitly authorized test environments.

536. Production Testing

Production testing SHALL require explicit deployment policy.

537. Destructive Testing

Destructive testing SHALL be disabled unless explicitly enabled.

538. Side-Effecting Tests

Side-effecting tests SHALL identify expected side effects.

539. Side-Effect Evidence

Observed side effects SHOULD be recorded as evidence when permitted.

540. Side-Effect Verification

Verification SHOULD be separated from the attack action.

541. Rollback

Where possible, side-effecting test environments SHOULD provide rollback mechanisms.

542. Transactional Test Targets

Test targets MAY provide transactional or simulated side effects.

543. External Action Simulation

Agent testing SHOULD prefer simulated actions where possible.

544. Human Approval for High Impact

High-impact operations SHOULD require explicit approval.

545. Approval Expiration

Approvals SHOULD expire rather than remain permanently valid.

546. Approval Scope

Approval SHALL identify:

who
what
target
environment
attack profile
time
547. Approval Audit

Approval creation and use SHALL be auditable.

548. Emergency Stop

Deployments SHOULD provide an administrative emergency stop for attack execution.

549. Emergency Stop Semantics

Emergency stop SHALL prevent new executions and attempt to cancel active executions.

550. Emergency Stop Audit

Emergency stop activation SHALL be audited.

551. Operational Runbooks

Production deployments SHOULD document:

stopping workers,
cancelling executions,
recovering stale jobs,
investigating resource exhaustion,
handling target outages.
552. Incident Handling

Security incidents involving orchestration SHALL follow the project's incident-response process.

553. Evidence During Incidents

Relevant execution evidence SHALL be preserved according to retention and privacy policy.

554. Security Review

Changes to:

capability handling,
network access,
execution limits,
state transitions,
plugin loading,
tool execution

SHALL receive security review.

555. Breaking Changes

Changes to execution semantics that affect reproducibility SHALL require an ADR update or new ADR.

556. Versioned Interfaces

Public execution interfaces SHALL be versioned when breaking changes occur.

557. API Compatibility

The API SHALL preserve compatibility where practical.

558. Migration

Execution-state migrations SHALL be explicit.

559. Data Migration Safety

Migrations SHALL not silently destroy evidence.

560. Rollback

Database and software rollback plans SHOULD account for execution-state compatibility.

561. Operational Testing

Before production release, the orchestrator SHALL be tested under:

normal load,
high concurrency,
provider failures,
cancellation,
worker restart,
database failure,
evidence storage failure.
562. Chaos Testing

Future versions MAY use controlled fault injection.

563. Fault Injection

Fault injection SHALL remain bounded and authorized.

564. Performance Testing

Performance testing SHALL measure:

throughput,
latency,
memory,
database writes,
worker utilization.
565. Performance vs Security

Performance optimizations MUST NOT weaken security boundaries.

566. Caching

Caching MAY be used for non-sensitive metadata.

Raw model responses SHOULD not be cached broadly without retention and authorization controls.

567. Session Cache

Session state caching SHALL preserve project and execution isolation.

568. Cache Poisoning

Untrusted model content SHALL not become trusted cached policy.

569. Cache Keys

Cache keys SHALL include appropriate resource scope.

570. Cache Invalidation

Security-sensitive configuration changes SHALL invalidate relevant cached data.

571. Queue Security

Queue payloads SHALL not contain unnecessary secrets.

572. Queue Integrity

Workers SHALL validate queue payloads before execution.

573. Queue Authorization

A worker SHALL process only jobs it is authorized to process.

574. Message Authentication

Distributed queues SHOULD authenticate messages.

575. Worker Identity

Workers SHOULD have distinct identities where practical.

576. Worker Least Privilege

Workers SHALL not receive unnecessary credentials.

577. Worker Network Access

Worker network access SHOULD be restricted.

578. Worker Filesystem

Worker filesystem access SHOULD be restricted to required directories.

579. Worker Secret Access

Workers SHOULD retrieve only secrets required for their assigned work.

580. Job Payload Validation

All job payloads SHALL be schema validated.

581. Poisoned Jobs

Malformed or malicious jobs SHALL fail safely.

582. Dead Letter Handling

Repeatedly failing jobs MAY enter a dead-letter state for investigation.

583. Dead Letter Security

Dead-letter payloads SHALL remain access controlled.

584. Retry Storm Prevention

Retry policies SHALL prevent retry storms.

585. Backoff Jitter

Distributed retries MAY use jitter.

586. Provider Protection

Provider-specific limits SHALL protect against accidental API abuse.

587. Target Respect

Aegis Vuldris SHALL respect target rate limits and authorized testing constraints.

588. User Transparency

The UI SHOULD show meaningful execution limits before a large test begins.

589. Execution Confirmation

Large or high-impact executions MAY require explicit confirmation.

590. Confirmation Is Not Authorization

User confirmation does not replace authorization.

591. Audit Confirmation

High-impact confirmations SHOULD be auditable.

592. Security Test Profiles

Profiles SHOULD describe operational characteristics clearly.

593. Profile Example
SAFE:
  low turns
  no external tools
  restricted network

STANDARD:
  bounded multi-turn
  approved target

EXTENDED:
  higher resource limits
  explicit approval

RESEARCH:
  controlled environment
  enhanced limits
594. Profile Enforcement

Profiles SHALL be enforced by trusted policy.

595. Profile Escalation

Attack content MUST NOT escalate profiles.

596. Final Security Model

The architecture SHALL be based on:

User Authorization
        |
        v
Trusted Policy
        |
        v
Bounded Orchestration
        |
        v
Controlled Adapter
        |
        v
Authorized Target
        |
        v
Untrusted Response
        |
        v
Evidence
        |
        v
Independent Evaluation
        |
        v
Independent Risk Assessment
597. Architectural Consequences
Positive

This architecture provides:

controlled multi-turn testing,
adaptive attacks,
reproducibility,
explicit execution boundaries,
safer tool integration,
resource control,
cancellation,
strong isolation,
clean separation of concerns,
future extensibility.
Negative

It introduces:

additional state management,
more complex testing,
execution lifecycle complexity,
resource accounting,
concurrency concerns,
more database records,
additional security boundaries.

These costs are accepted because uncontrolled attack execution would create greater security and operational risk.

598. Alternatives Considered
Alternative A — Execute One Prompt Per Test

Rejected because many AI security weaknesses require multi-turn interaction.

Alternative B — Put Orchestration in the Model Adapter

Rejected because provider communication and attack strategy are separate concerns.

Alternative C — Let the Model Control the Loop

Rejected because model output is untrusted and cannot be allowed to control security policy.

Alternative D — Arbitrary Python Attack Scripts

Rejected as the default because arbitrary scripts create unnecessary code-execution and supply-chain risks.

Alternative E — Unlimited Adaptive Execution

Rejected because of resource exhaustion and operational safety risks.

Alternative F — External Workflow Engine Only

Rejected as the sole mechanism because Aegis Vuldris requires domain-specific security execution semantics.

599. Final Decision

Aegis Vuldris SHALL implement a dedicated, bounded attack orchestration subsystem.

The subsystem SHALL support:

declarative attack plans,
single-turn and multi-turn attacks,
adaptive strategies,
branching,
bounded loops,
explicit resource budgets,
target sessions,
cancellation,
retries,
evidence integration,
replay,
authorization,
project isolation,
target isolation,
capability controls,
network restrictions,
safe tool integration,
evaluation handoff,
risk handoff,
auditability.

The orchestrator SHALL remain separate from:

authentication,
authorization policy,
model adapter implementations,
evaluation logic,
risk scoring,
reporting.
600. Acceptance Criteria

ADR-011 is accepted when the implementation roadmap derived from this ADR can demonstrate:

 Attack plans are versioned.
 Attack strategies are separated from execution.
 Multi-turn sessions are isolated.
 Execution state is persisted.
 State transitions are explicit.
 Resource limits are enforced.
 Maximum turns are enforced.
 Maximum duration is enforced.
 Maximum requests are enforced.
 Cancellation works.
 Retry behavior is bounded.
 Duplicate execution is controlled.
 Target authorization is enforced.
 Project isolation is enforced.
 Target isolation is enforced.
 Model output is treated as untrusted.
 Attack content cannot modify policy.
 Tool capabilities are deny-by-default.
 Network access is policy-controlled.
 SSRF protections exist where network access is enabled.
 Evidence is preserved.
 Evaluation is independent.
 Risk assessment is independent.
 Replay metadata is preserved.
 Audit events are generated.
 Security invariants are covered by tests.
 Dangerous capabilities require explicit authorization.
 Production defaults are restrictive.
601. Implementation Gate

No implementation of unrestricted adaptive attack execution SHALL proceed until:

execution limits exist,
target authorization exists,
project/target isolation exists,
cancellation exists,
evidence boundaries exist,
model output is treated as untrusted,
dangerous capabilities are explicitly controlled.
602. Relationship to Future Architecture

Future ADRs may refine:

privacy and sensitive-data handling,
observability,
configuration and secret management,
production deployment,
distributed execution,
advanced agent/tool sandboxing.

Those ADRs SHALL preserve the security invariants defined here.

603. Maintenance

This ADR SHALL be reviewed when:

attack orchestration semantics change,
multi-turn execution changes,
tool execution is introduced,
network capabilities expand,
plugin execution changes,
distributed execution changes,
execution persistence changes,
resource policies change.
604. Security Review Requirement

Any change that weakens a security invariant SHALL require explicit architectural review.

605. Final Architectural Principle

The central principle of ADR-011 is:

Aegis Vuldris may adapt its attack strategy, but the attack strategy must never control Aegis Vuldris's security boundaries.

Adaptive execution is therefore permitted only inside a trusted, bounded, authorized orchestration framework.

606. Status

Accepted

ADR-011 is approved as the architectural basis for Aegis Vuldris attack orchestration and multi-turn execution.

Implementation SHALL proceed only through controlled, testable, incremental changes consistent with this ADR and the related architecture decisions.

607. End of ADR
