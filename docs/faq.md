# FAQ

Short answers, each pointing at the document that backs it. The honest
limitations live in [`OVERVIEW.md`](OVERVIEW.md) — read that before relying on
anything here.

### Is Aegis Vuldris a pentest?

No. It sends adversarial prompts to model endpoints you authorize and records
what came back. It does not scan infrastructure, dependencies, or network
posture, and its output is a signal to investigate, not a verdict. See
OVERVIEW sections 8–9.

### Does it phone home or collect telemetry?

No. There is no analytics, no phone-home, and no crash reporting. The only
outbound traffic is to the model endpoints you register, through the
SSRF-validated network policy ([`ssrf-protection.md`](ssrf-protection.md)).

### Which model providers can I test?

| `provider` | Speaks to |
|---|---|
| `openai_compatible` | Any OpenAI-style `/chat/completions` API (OpenAI, Azure-style gateways, vLLM, LM Studio, hosted routers) |
| `ollama` | An Ollama server (`/api/chat`) |
| `custom_rest` | A configurable JSON REST shape |

The registry is the source of truth (`app/adapters/registry.py`). Third
parties can add adapters through the extension contract documented in
[`extension-points.md`](extension-points.md).

### Can I test a model on localhost or inside my network?

The SSRF guard blocks loopback, private, link-local, and cloud-metadata
addresses by default. For local development, `ALLOW_LOCAL_TARGETS=true`
permits them — never enable it in a shared or production deployment
([`ssrf-protection.md`](ssrf-protection.md)).

### Why did a well-behaved model produce findings?

Default grading is lexical (keyword/regex): a model that casually mentions
"system prompt" can match. Expect false positives — treat every finding as a
prompt to investigate, and read [`grading-accuracy.md`](grading-accuracy.md).

### What does `inconclusive` mean?

Grading could not complete, and Aegis Vuldris refuses to guess: the result is
`inconclusive`, never `pass`. For judge-model tests there are four causes: no
judge target configured, inactive judge target, the judge would be the target
under test with the same model, or the judge call failed
([`troubleshooting.md`](troubleshooting.md#executions-and-grading)).

### Can the judge be a different model than the one under test?

Yes — that is the point. Register a separate target (any provider) and select
it as the project's judge target; the judge model grades `judge_model` cases
semantically. A case can optionally pin a specific model on the judge endpoint
with `grading.judge.model`. A model never judges its own answers: the same
target with the same model is refused (ADR-005).

### How long is evidence kept?

Evidence is the prompts and responses behind findings. Every project has an
evidence retention window (`DEFAULT_EVIDENCE_RETENTION_DAYS`, 90 days by
default); prune it explicitly with `aegis retention prune`. See
[`data-retention.md`](data-retention.md).

### Is it free? Is there a hosted version?

Apache License 2.0 — self-host freely. A hosted pilot is planned, but **no
hosted service exists today**, and the core contains no billing, entitlement,
or telemetry code.

### Can I run it on Windows or macOS?

The supported deployment path is a Linux host with Docker Compose
([`deployment.md`](deployment.md)). Running from source also works on Windows
(this repository's own test suite runs there) — see
[`development.md`](development.md). macOS is untested; Docker Compose is the
safest path.

### How do I try it with zero credentials?

`aegis demo --email you@example.com` seeds a synthetic, clearly-marked `[DEMO]`
project from a recorded fixture. Nothing was produced by a real model run, and
the demo target cannot be reached by design. Remove it with `--prune`, then
point the tool at a target you are authorized to test.

### How do I gate CI on regressions?

Use the `aegis` CLI or the composite GitHub Action; the exit-code contract is
0 (success), 2 (a configured gate fired), 4 (operational error), 1 (usage).
See [`ci-integration.md`](ci-integration.md).

### Something is broken. Where do I look?

[`troubleshooting.md`](troubleshooting.md), then `aegis doctor` — it checks
configuration, database, migrations, and plugins, and names the fix.

### How do I contribute, or report a vulnerability?

Contributions: [`CONTRIBUTING.md`](../CONTRIBUTING.md) (DCO sign-off, quality
gates) and the [attack plugin guide](Attack-Plugin-Guide.md) for new test
cases. Vulnerabilities: [`SECURITY.md`](../SECURITY.md) — never a public
issue.
