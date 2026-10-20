<p align="center">
  <img src="docs/assets/logo.svg" width="76" alt="Aegis Vuldris shield logo">
</p>

<h1 align="center">Aegis Vuldris</h1>

<p align="center">
  <strong>Security assurance for AI model endpoints — with evidence, not guesswork.</strong><br>
  Self-hosted adversarial testing for OpenAI-compatible, Ollama, and custom REST inference APIs.
</p>

<p align="center">
  <a href="https://github.com/xizoai/Aegis-Vuldris/actions/workflows/backend.yml"><img alt="Backend quality" src="https://github.com/xizoai/Aegis-Vuldris/actions/workflows/backend.yml/badge.svg?branch=main"></a>
  <a href="https://github.com/xizoai/Aegis-Vuldris/actions/workflows/frontend.yml"><img alt="Frontend quality" src="https://github.com/xizoai/Aegis-Vuldris/actions/workflows/frontend.yml/badge.svg?branch=main"></a>
  <a href="LICENSE"><img alt="License: Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-blue.svg"></a>
  <a href="https://www.python.org/downloads/"><img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB.svg?logo=python&logoColor=white"></a>
  <a href="CONTRIBUTING.md"><img alt="PRs welcome" src="https://img.shields.io/badge/PRs-welcome-brightgreen.svg"></a>
</p>

Aegis Vuldris is an open-source, self-hosted **model security assurance** platform. It helps AI teams and authorized security testers assess the security, safety, privacy, and robustness of LLM inference endpoints — and keep evidence that holds up when the model, prompt, or provider changes.

> [!WARNING]
> **Authorized testing only.** Aegis Vuldris sends adversarial prompts to systems you configure. Only assess systems you own or have explicit written authorization to test. Creating a target is an attestation that you hold that authorization.

> [!NOTE]
> **Scope: model endpoints.** Aegis Vuldris tests inference behavior. It does not execute agent tools, connect to MCP servers, inspect model weights, or prove that a RAG pipeline is safe. The bundled agent and RAG cases are static prompt probes; see [Scope](#scope).

## Why teams use it

- **Ship model changes without guessing.** Run the same suite before and after a model upgrade, fine-tune, prompt change, or provider migration. Report snapshots separate new, resolved, regressed, and improved findings.
- **Compare models on an identical corpus.** The comparison matrix shows the latest result per test and target, so procurement bake-offs and fine-tune deltas use the same attacks.
- **Answer "show me".** Every finding stores the exact request and response. Every run stores a manifest with the model version, effective generation settings, system-prompt digest, and a SHA-256 of the test definition.
- **Meet reviewers where they are.** Severity scoring, OWASP GenAI LLM Top 10:2026 mapping, and a NIST AI RMF / EU AI Act / ISO 42001 crosswalk in JSON and Markdown reports.

Built for AI/ML engineers, application security teams, consultancies and MSSPs, and compliance teams evaluating model risk.

## See it

[![Aegis Vuldris project workspace](docs/assets/screenshots/workspace.png)](docs/assets/screenshots/workspace.png)

*The project workspace (demo data): coverage, active targets, confirmed findings, and the project judge target.*

## How it works

```mermaid
flowchart LR
  T["Target<br/>endpoint + model profile"] --> S["Test library<br/>224 attack cases"]
  S --> R["Execution<br/>request + response recorded"]
  R --> D{"Stage 1<br/>deterministic rules"}
  D -- "no match" --> P["Pass"]
  D -- "match" --> C["Candidate<br/>not a finding yet"]
  C --> J{"Stage 2<br/>judge or reviewer"}
  J -- "exploited" --> F["Confirmed finding"]
  J -- "refused" --> X["Dismissed"]
  J -- "unclear / no judge" --> N["Needs review"]
  F --> E["Evidence + severity<br/>OWASP mapping + report"]
  E --> V["Re-run after the fix"]
  V --> R
```

Two rules keep the output trustworthy:

1. **A pattern match is a candidate, not a verdict.** Only a confirmed finding produces a `fail`. Unresolved candidates produce `needs_review`, which is never reported as a pass.
2. **A human can always decide.** Reviewers confirm, dismiss, or reopen a candidate with a recorded reason, and the action is audited. Applying a fix is a human action, and only a re-run that no longer reproduces the issue marks a finding `verified`.

## Evidence you can replay

[![Exact request and response behind a finding](docs/assets/screenshots/finding-evidence.png)](docs/assets/screenshots/finding-evidence.png)

*The transcript behind a failing run (demo data). The execution records what was sent, what came back, and why it matched — no summary, no paraphrase.*

The confirmation judge is measured, not assumed. `aegis judge-calibration` runs a labeled corpus through the real judge stack and reports stage-one recall, judge accuracy, exploited precision and recall, refusal recall, and Cohen's κ. This repository includes a recorded live run against `deepseek-ai/DeepSeek-V4-Flash-0731`, with the raw judge outputs committed so the result can be replayed without a model:

| Metric | Recorded live run |
|---|---|
| Decided | 25 / 25 |
| Judge accuracy | 96.0% |
| Cohen's κ | 0.92 |
| Exploited precision / recall | 92.9% / 100% |
| Refusal recall | 91.7% |
| Stage-one detector recall | 92.3% (12 / 13) |

Replay it with `aegis judge-calibration --judge-outputs docs/calibration/judge-run-2026-10-19.jsonl`. The single miss is a judge-injection trap; see [judge calibration](docs/judge-calibration.md). Run the same harness against any judge model before trusting its verdicts.

## What's included

| Area | Details |
|---|---|
| **Attack library** | 224 cases: 195 core model-security cases (67 prompt injection, 108 jailbreak, 20 privacy leakage), plus 14 RAG and 15 agent-oriented probes marked experimental. Single-turn and multi-turn attacks, including encoded variants. |
| **Targets** | OpenAI-compatible, Ollama, and custom REST endpoints. Automatic model discovery after the endpoint is entered, with manual model entry always available. Per-target model profile: version, system prompt, temperature, top-p, max tokens, and seed. |
| **Grading** | Deterministic rules produce candidates; a project judge target or a human reviewer resolves them. Confirmation, dismissal, triage reasons, and verification re-runs are recorded. |
| **Evidence** | Exact request/response transcripts, redacted on read. Run manifests capture model version, effective generation config, system-prompt digest, and test-definition SHA-256. |
| **Comparison** | The same corpus across multiple targets with a latest-result matrix — useful for procurement, model upgrades, and fine-tune deltas. |
| **Reporting** | Severity scoring, OWASP GenAI LLM Top 10:2026 classification, NIST AI RMF / EU AI Act / ISO 42001 crosswalk, JSON and Markdown reports, and snapshot comparison. |
| **Operations** | Self-hosted deployment, encrypted target credentials, audit events, retention pruning, PostgreSQL, Docker Compose, and nginx. |
| **CI** | A GitHub Action and a documented exit-code contract: gate a pipeline with `--fail-on high`. |

## Quick start

### Docker Compose (recommended)

Requires Docker with the Compose plugin. A one-shot `migrate` service applies the schema before the backend starts, so there is no manual Alembic step.

```bash
git clone https://github.com/xizoai/Aegis-Vuldris.git
cd Aegis-Vuldris
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
docker compose up --build -d
```

Then open <http://127.0.0.1:8080> and register an account.

> PowerShell: `$env:SECRET_KEY = python -c "import secrets; print(secrets.token_hex(32))"`.

### Explore with demo data

No model or credentials needed — the demo seeds a synthetic project with a recorded execution, finding, and evidence:

```bash
docker compose exec backend aegis demo --email you@example.com
```

Remove it later with `--prune`.

### Run your first assessment

```bash
# Import the bundled attack library into a project (find its UUID in the URL).
docker compose exec backend aegis seed-tests --project <project-uuid> --email you@example.com

# Run the suite against a target, and exit 2 if a high-severity finding appears.
docker compose exec backend aegis run --project <project-uuid> --target <target-uuid> --email you@example.com --fail-on high
```

In the UI, use **Load attack library** on the project page, then **Run test**. Seeding is idempotent, so re-running is safe.

<details>
<summary><strong>Run without Docker</strong></summary>

Requires Python 3.11+, Node 22+, and PostgreSQL 16+.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install .
cp .env.example .env                   # set DATABASE_URL and SECRET_KEY
alembic upgrade head
uvicorn app.main:app --reload --app-dir backend --port 8000
```

In a second terminal, start the UI:

```bash
cd frontend
npm install
npm run dev                            # http://localhost:5173
```

`aegis doctor` checks configuration, database connectivity, and migration state before you start. Full setup is in [development](docs/development.md) and [configuration](docs/configuration.md).

</details>

## Supported targets

| Provider | Speaks to | Notes |
|---|---|---|
| `openai_compatible` | Any OpenAI-style chat API | Store a **base** URL (`https://host/v1`); `/chat/completions` is appended. Model required. |
| `ollama` | An Ollama server | `/api/chat` is appended; streaming is disabled. Model required. |
| `custom_rest` | A configured JSON REST endpoint | Method, path, response mapping, and auth header are set per target. Accepts a base URL or a full inference URL. Model optional. |

The registry in [`backend/app/adapters/registry.py`](backend/app/adapters/registry.py) is the source of truth, and third parties can register more through [extension points](docs/extension-points.md).

## CLI

Everything the UI does is scriptable through `aegis`. Every command calls the same service layer as the API.

| Command | What it does |
|---|---|
| `aegis doctor` | Check environment, database, migrations, secret key, and targets. |
| `aegis demo` | Seed an offline, synthetic demo project. |
| `aegis seed-tests` | Import the bundled 224-case attack library. |
| `aegis run` | Run a project's tests against one target. |
| `aegis verify` | Re-run the exact attack behind a finding and report the verdict. |
| `aegis export` | Generate a JSON or Markdown report artifact. |
| `aegis grading-accuracy` | Measure grader false positives against known-safe responses. |
| `aegis judge-calibration` | Measure the confirmation judge against labeled transcripts. |
| `aegis retention` / `clear-history` | Prune expired evidence or clear a project's execution history. |

Exit codes: `0` success; `1` usage or configuration error; `2` a configured condition matched (`--fail-on`, baseline, or inconclusive); `4` operational error. See [CI integration](docs/ci-integration.md) for the gate contract.

## Scope

**In scope:** the security, safety, privacy, and robustness behavior of a model inference endpoint for a given prompt, system prompt, and generation profile; regression testing across model versions and fine-tunes; evidence packs and reports for security review and compliance work.

**Out of scope today:** agent/tool execution, MCP servers, runtime guardrails, RAG retrieval quality, model-weight or artifact scanning, and autonomous exploitation. The 15 agent and 14 RAG cases are static prompt-level probes and are marked experimental. [The overview](docs/OVERVIEW.md) documents the limitations in full.

Aegis Vuldris is pre-1.0 (`0.1.0`). The core assessment workflow is implemented and tested, but interfaces and the database schema may still change before 1.0.

## Documentation

- **Start here:** [Overview](docs/OVERVIEW.md) · [Beginner guide](docs/Beginner-Guide.md) · [User manual](docs/Manual.md) · [FAQ](docs/faq.md)
- **Architecture & security:** [Architecture](docs/architecture.md) · [Threat model](docs/threat-model.md) · [Security boundaries](docs/security-boundaries.md)
- **Operations:** [Configuration](docs/configuration.md) · [Deployment](docs/deployment.md) · [Secrets management](docs/secrets-management.md) · [CI integration](docs/ci-integration.md) · [Release process](docs/release-process.md)
- **Quality:** [Grading accuracy](docs/grading-accuracy.md) · [Judge calibration](docs/judge-calibration.md) · [Risk scoring](docs/risk-scoring.md)
- **Extending:** [Extension points](docs/extension-points.md) · [Attack plugin guide](docs/Attack-Plugin-Guide.md) · [Test-case schema](docs/test-cases.md) · [ADRs](docs/adr/)
- **Help:** [Troubleshooting](docs/troubleshooting.md) · [Changelog](CHANGELOG.md)

## Development

The quality gates are the same ones CI runs on every push and pull request. They assume the local setup in [development](docs/development.md), including `DATABASE_URL`, `SECRET_KEY`, and `APP_ENV=testing` for the test suite:

```bash
# Backend — Python 3.11+ and PostgreSQL 16+
pip install .
ruff check backend tests scripts examples
ruff format --check backend tests scripts examples
pyright
pytest -q
alembic check

# Frontend — Node 22+
cd frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Backend tests need a PostgreSQL database; [CONTRIBUTING.md](CONTRIBUTING.md) has the full definition of done for a pull request.

## Security

- **Report vulnerabilities privately.** Follow [SECURITY.md](SECURITY.md); never open a public issue for a vulnerability.
- **Credentials are encrypted at rest** with a key derived from `SECRET_KEY`. Transcripts are redacted on read, and security-relevant actions are written to the audit log. See [secrets management](docs/secrets-management.md).
- **A test harness, not a guardrail.** Aegis Vuldris does not protect an endpoint at runtime. It finds behavior that needs a control, a prompt change, or a model change.
- **Stay inside your authorization.** Creating a target attests that you own the system or have written permission to test it.

## Contributing

Contributions are welcome. Branch from `main`, keep `CHANGELOG.md` current under `[Unreleased]`, sign off your commits (DCO), make the quality gates pass, and open a pull request. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and review expectations; [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) applies to every project space.

## License and attribution

Apache License 2.0 — see [LICENSE](LICENSE). The bundled attack library includes Garak-derived cases and other upstream material; attributions are recorded in [attack-library-attribution.md](docs/attack-library-attribution.md).
