# Garak and PyRIT runtime integration — plan

**Status:** phases 0-2 implemented (durable scan queue, claim minting, Aegis LLM shim, garak ingestion); the runner image and phases 3-5 are pending
**Date:** 2026-10-18
**Scope:** running [garak](https://github.com/NVIDIA/garak) and [PyRIT](https://github.com/microsoft/PyRIT)
against AegisAI targets at run time, and surfacing their results as Aegis findings.

This document is the plan of record for the decision to move past the current
*static corpus* reuse (see `docs/attack-library-attribution.md`) to *live*
execution of both tools.

---

## 1. Summary

Today AegisAI reuses garak and PyRIT **content, not code**: prompt text, adversarial
suffixes, and encoding techniques were extracted offline into bundled YAML
(`backend/app/test_cases/`) and 16 native converters (`backend/app/services/converters.py`).
There is no `garak` or `pyrit` dependency and no runtime call to either tool.

This plan adds live execution behind four architecture decisions:

| Decision | Choice |
|---|---|
| Where tools run | A **separate runner** container/process, not the API process |
| How tools reach a target | An **Aegis LLM shim** that injects credentials and enforces the network policy |
| Build order | garak and PyRIT **together**, sharing one ingestion framework |
| Credential handling | Credentials and SSRF policy stay inside Aegis; the runner never sees a key |

The shim is the security keystone. Everything else is plumbing around it.

---

## 2. Why this is not just "another adapter"

AegisAI's execution model is **one execution per `(test, target)`**: `ExecutionEngine`
schedules an asyncio task, sends one request (or one scripted multi-turn), grades the
response with `finding_classifier`, and writes a `Finding`
(`backend/app/services/execution_engine.py`).

Neither tool fits that shape:

- **garak** is a *batch scanner*. One invocation runs hundreds of probes, each probe
  issuing one or more attempts and each attempt carrying its own detector verdict.
- **PyRIT** is an *orchestrator*. One run executes a multi-turn attack strategy across
  converters and scorers, producing many scored turns.

So this is a new abstraction — an **external scan** that wraps a tool run and *emits* N
Aegis findings — not a new entry in `backend/app/adapters/registry.py`.

---

## 3. Goals and non-goals

**Goals**

- Launch a garak scan or PyRIT orchestrator against an existing Aegis target from the API/UI.
- Keep credentials, the SSRF/network policy, and all database writes inside Aegis.
- Normalize tool verdicts into Aegis findings with severity and OWASP LLM Top 10 mapping.
- Preserve the tool's raw report as retention-managed evidence.
- Pin tool versions so a scan is reproducible in principle and attributable in practice.

**Non-goals**

- Replacing the native YAML corpus or the native converters. They stay.
- Running torch/GPU-heavy garak extras (`gcg`, `dra`, `audio`) in the default runner.
- A general-purpose job scheduler. This adds one queue for external scans.

---

## 4. Architecture

```
        ┌────────────┐   POST /projects/{id}/scans    ┌──────────────┐
        │  Frontend  │ ─────────────────────────────▶ │   API        │
        └────────────┘                                │ (owns DB,    │
                                                      │  creds, policy)│
        ┌────────────┐   claim / report (service tok) │              │
        │  Runner    │ ◀─────────────────────────────▶│              │
        │ garak|pyrit│                                └──────┬───────┘
        │            │   ▸ HTTP (no creds, scoped token)     │
        │            │ ──────────────▶ GET /external/llm/{scan}/v1/chat/completions
        └────────────┘                        │
                                              ▼
                                    Aegis LLM shim → adapter → target endpoint
                                    (resolves credentials, enforces SSRF, rate-limits)
```

### 4.1 Runner (separate container)

A dedicated `runner` image with garak and PyRIT pinned. Rationale:

- **Blast radius.** These tools execute model output-driven attack logic and pull very
  large dependency trees. They do not belong in the API process.
- **Concurrency.** Both tools spawn their own pools; the API already runs sync DB work
  on the event loop and its executions are non-durable (see the audit's F3).
- **Dependency isolation.** PyRIT 1.1.0's *core* requirements include `transformers`,
  `numpy`, `scipy`, `datasets`, `fastapi`, and `uvicorn`; the image will be large no
  matter what, and we do not want that in the API image.

The runner **holds no database credentials and no target credentials.** It claims jobs
and reports results through an internal, service-token-authenticated API, so the API
remains the single writer and policy point.

### 4.2 Durable job state

External scans can run for minutes. State must survive a restart. Two tables (§4.6) plus
a Postgres claim using `SELECT ... FOR UPDATE SKIP LOCKED` give at-most-once claiming.

This overlaps with the deferred durable-execution work. The queue built here
should be reusable for native executions, so both should be scheduled as one
workstream.

### 4.3 Aegis LLM shim — implemented (phase 1)

An OpenAI-compatible endpoint, `POST /api/v1/external/llm/{scan_id}/v1/chat/completions`,
scoped to a single scan. Implemented in `backend/app/api/routes/external_llm.py` with the
conversion layer in `backend/app/services/shim_mapping.py`.

- **Authentication:** `backend/app/security/scan_tokens.py` signs a short-lived JWT at
  claim time (`create_scan_token`) and the shim verifies it on every call
  (`decode_scan_token`). The token binds `{scan_id, target_id, project_id}` plus the claim
  nonce minted for that attempt, so it grants exactly one scan against exactly one target
  and dies the moment the scan is requeued or reaches a terminal state — no heartbeat and
  no TTL grace needed for correctness, and the TTL (`external_scan_token_expire_minutes`,
  default 240) is only a backstop. Minted per claim in the internal claim endpoint
  (`llm_token` in the claim response); the runner never sees anything wider.
- **Target binding:** the request body schema is `extra="forbid"` — a body cannot carry a
  URL, host, or target id. The caller's `model` is accepted for client compatibility and
  then dropped: the bound target's configured model is authoritative, and honoring a
  caller-supplied model name would let a tool address a different deployment on the same
  endpoint. Streaming is refused (422) because a streamed reply cannot be rebuilt into
  the hardening-checked flat shape.
- **Credential injection:** credentials are resolved server-side with
  `create_credential_resolver` and injected into the outbound headers by the adapter.
  The response is rebuilt from the normalized `ModelResponse`, so the credential value
  never appears in anything the runner receives.
- **Policy:** forwarding goes through the existing adapter path (`create_model_adapter`),
  so `resolve_target` still applies DNS pinning and the private-address policy. A policy
  rejection surfaces as `403 NETWORK_POLICY_REJECTED`; an unusable target (invalid
  endpoint shape, missing model, negative DNS) as `502 TARGET_NOT_USABLE`; provider
  errors as `502 TARGET_UPSTREAM_ERROR`. `ALLOW_LOCAL_TARGETS` is honoured exactly as for
  native runs.
- **Limits:** a per-scan sliding-window rate limit (60 requests per minute per scan,
  `SlidingWindowRateLimiter` keyed by scan id) returns the shared 429 shape. Request
  shape bounds mirror the native path (message count, message size, `max_tokens`).
  Durable per-scan request/token/wall-clock budgets are phase 5.
- **Audit:** each successful forward increments `external_scans.forwarded_requests`
  (counted rather than audited per call; one UPDATE per request instead of an audit row
  per probe attempt). No prompt or response body is ever logged (ADR-013).

From the exit criteria: the claim → token → shim round trip is covered by
`tests/api/test_scan_shim.py` (mock adapter captures the bound target, provider, and
converted request); cross-scan and stale-token rejections by
`tests/api/test_scan_shim.py` plus the binding tests in `tests/services/test_scan_shim.py`.

Sketch (illustrative, not final):

```python
@router.post("/external/llm/{scan_id}/v1/chat/completions")
async def shim(scan_id: UUID, body: ChatCompletionRequest, claim=Depends(require_scan_token)):
    target = claim.target  # bound at mint time, never from `body`
    request = to_model_request(body)  # OpenAI shape -> ModelRequest
    adapter = create_model_adapter(target.provider, credential_resolver=...)
    response = await adapter.generate(target, request)
    return to_chat_completion(response)  # ModelResponse -> OpenAI shape
```

`to_model_request` / `to_chat_completion` are pure functions and are the bulk of the
shim's testable surface.

### 4.4 Garak adapter — implemented (phase 2)

Implemented in `backend/app/cli/garak.py` (invocation and report parsing) and
dispatched from `backend/app/cli/runner.py`.

- **Invocation:** garak's `rest` generator is pointed at the scan's shim URL and
  authenticated with the claim's `llm_token`. The token is written into a
  generator config file with owner-only permissions inside a private temporary
  directory, then deleted after the run; it never appears on the command line or
  in the process list. `config["generator_option_file"]` lets a deployment supply
  a hand-verified generator file instead of the generated one.
- **Probe selection:** an allow-list (`ALLOWED_PROBE_FAMILIES`) of content-only
  families, bounded at 20 probes. `atkgen`, `gcg`, `dra`, and audio probes are
  excluded: they are expensive or GPU-bound, so enabling one is a deliberate
  capacity decision rather than a config value. A selection outside the list
  fails the scan instead of running whatever the API was asked for.
- **Version:** `garak --version` is recorded on the scan (`tool_version`), so a
  result is attributable to a tool version.
- **Report:** garak writes `{report_prefix}.report.jsonl` under
  `AEGIS_SCAN_REPORT_DIR`; the path is recorded on the scan. The parser reads
  `entry_type == "attempt"` records, maps `passed` to pass/fail, and maps a
  missing verdict to `inconclusive` (never to a pass). Purging scan reports is
  phase 5: point the runner's report directory at a volume you are prepared to
  age out, because today's retention job clears generated report artifacts and
  evidence, not scan reports.

**Not verified yet:** garak is not installed in the development environment, so
the generated generator-config nesting and the attempt-record keys are pinned by
a stub that speaks the documented 0.17.1 shape, not by a live run. Both are
called out in the module docstring and must be confirmed against the pinned garak
in the runner image. That image (Dockerfile, pinned dependencies, compose wiring)
is the remaining phase 2 work; the code path above it is implemented and tested.

### 4.5 PyRIT adapter

- Build a PyRIT `OpenAIChatTarget` pointing at the shim URL with the scan token.
- Choose an orchestrator and scorers from config.
- Map objective/scorer outcomes (§4.6).

### 4.6 Result ingestion and mapping — implemented (phase 2)

One ingestion framework, two producers (`backend/app/services/scan_ingestion.py`).
Each external result becomes a `Finding` whose `details` carry the tool, version,
probe/orchestrator id, category, OWASP mapping, trigger count, and a pointer to
the raw record.

| External verdict | Aegis result | Severity | Notes |
|---|---|---|---|
| garak attempt `passed: false` | `FAIL` + finding | from `severity_scorer` | trigger count and detector go into `details` |
| garak attempt `passed: true` | `PASS` | — | counted, no finding |
| PyRIT objective met | `FAIL` + finding | from `severity_scorer` | scorer name and score in `details` |
| PyRIT objective not met | `PASS` | — | |
| tool error / no verdict | `INCONCLUSIVE` | — | never reported as PASS |

Category → OWASP mapping reuses `OWASP_LLM_TOP_10` in `backend/app/services/risk_scoring.py`,
extended with a probe-family → category table (`PROBE_FAMILIES`), so garak/PyRIT results
appear alongside native findings in reports. Severity is the shared scorer applied to the
category label, not a per-tool table, so the same weakness scores the same way whichever
path found it.

**Transport.** The runner sends its normalized verdicts in the same call that reports the
terminal state (`POST /internal/scans/{id}/complete`, `results`), so the terminal
transition and its findings are one transaction: a completed scan is never left without
the findings its report holds, and a lost reply is a `409` retry rather than a duplicate
ingest. A failed run still ingests the verdicts it produced before dying. Re-ingesting a
scan replaces its findings, so a manual re-run is well defined.

**What is not stored.** Prompts, model output, and the detector's triggering strings stay
in the raw `report.jsonl` under the report volume. They are attack content and, when a
probe works, the leaked data itself; the finding keeps `trigger_count` and the record
index instead. Raw content as Aegis evidence remains open question 3; no `Evidence` rows
are created for scan findings yet.

The raw `report.jsonl` is stored under the report volume. It is not yet purged by
`backend/app/cli/retention.py`, which today clears generated report artifacts and
evidence; extending it to scan reports is part of phase 5 ("retention of artifacts").
Until then the runner's report directory is the operator's responsibility.

### 4.7 Data model

```
external_scans
  id, project_id, target_id
  tool               -- 'garak' | 'pyrit'
  tool_version
  config             -- JSONB: probe/orchestrator selection, limits, seed
  status             -- queued | running | completed | failed | cancelled
  external_run_id
  report_path
  created_by, created_at, started_at, finished_at, error
  claimed_at         -- lease marker, cleared on a terminal transition
  claim_id           -- per-claim nonce the scan token is bound to
  attempt_count      -- claims of this row, so a scan that keeps losing its
                     -- runner is visible instead of looping silently
  forwarded_requests -- model calls the shim forwarded (counted, not logged)

findings
  execution_id        -- now nullable: a finding has one origin, not two
  + external_scan_id  (nullable FK; NULL for native executions)
  + ck_findings_single_origin  -- exactly one of the two is set
```

Migrations: `a1b2c3d4e5f6` adds `external_scans`, `b2c8e4f5d1a7` adds the claim nonce and
the forwarded-request counter, and `c4d9e1f2a3b5` makes `findings.execution_id` nullable,
adds `findings.external_scan_id`, and the single-origin check constraint. Native
`Execution` rows are unchanged; scan-derived findings link through `external_scan_id`
rather than a synthetic execution.

`target_id` is `ON DELETE SET NULL` and `project_id` is `ON DELETE CASCADE`, matching the
existing execution/target relationship: deleting a project discards its scans, deleting a
target keeps the scan for history.

### 4.8 API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/projects/{id}/scans` | create a scan (`tool`, `target_id`, `config`) → `202` ✅ phase 0 |
| `GET` | `/api/v1/projects/{id}/scans` | list a project's scans ✅ phase 0 |
| `GET` | `/api/v1/scans/{id}` | status, progress, tool version ✅ phase 0 |
| `GET` | `/api/v1/scans/{id}/findings` | findings produced, most severe first ✅ phase 2 |
| `POST` | `/api/v1/scans/{id}/cancel` | cancel ✅ phase 0 |
| `POST` | `/api/v1/internal/scans/claim` | runner claim (service token) ✅ phase 0 |
| `POST` | `/api/v1/internal/scans/{id}/complete` | runner report (service token); carries normalized verdicts ✅ phase 2 |

Scanner endpoints enforce project membership/authorization, matching the existing
target and execution authorization in `backend/app/services/assessments.py`.

### 4.9 UI

A **Scans** surface (list + detail) alongside projects: pick a target, pick a tool and a
probe/orchestrator profile, watch progress, and read findings that render through the
same finding/report components as native runs.

---

## 5. Security model

| Threat | Control |
|---|---|
| Key leakage into the runner or its logs | Runner gets only a scoped token; credentials resolved only inside the API |
| SSRF via the shim | Target is bound at token-mint time; request body cannot name a URL/host; forwarding goes through `resolve_target` |
| Shim as open proxy | Token scoped to one `(scan, target)`, short TTL, rate-limited, audited |
| Resource abuse / runaway cost | Per-scan request, token, and wall-clock budgets; cancellable |
| Runner compromise | No DB creds, no target creds; only the scoped shim token; runs in its own container |
| Sensitive content in artifacts | Raw reports stored under the retention-managed report volume; prompt/response bodies not logged |
| Attribution/licensing | §6; NOTICE + SBOM |

---

## 6. Dependencies and licensing

| Tool | Version (pinned) | Python | License | Notes |
|---|---|---|---|---|
| garak | 0.17.1 | `>=3.11` | Apache-2.0 | fits Aegis's `>=3.11,<3.13`; extras `audio`, `calibration`, `dra`, `lint`, `tests` |
| pyrit | 1.1.0 | `>=3.10,<3.15` | MIT | heavy core deps (`transformers`, `scipy`, `numpy`, `datasets`) |

- Install `garak` and `pyrit` **only in the runner image**, pinned to exact versions.
- Extend `docs/attack-library-attribution.md` (or a new NOTICE entry) to cover
  *runtime* use, not just extracted content.
- The release workflow already emits provenance and an SBOM for published images
  (`.github/workflows/release.yml`); include the runner image in that set.

---

## 7. Phased delivery

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0 | Durable scan queue + runner scaffold ✅ | a no-op job survives an API restart and completes exactly once |
| 1 | LLM shim ✅ | OpenAI-shaped request/response round-trips against a mock target; SSRF and cross-scan token reuse are rejected by tests |
| 2 | garak integration ✅ (runner image pending) | a small probe set scans a live target end to end; findings and raw report persisted |
| 3 | PyRIT integration | one orchestrator scans a live target end to end; scorer outcomes mapped |
| 4 | API + UI + reports | scan findings appear in a generated report with OWASP mapping |
| 5 | Hardening | budgets, cancellation, retention of artifacts, attribution/NOTICE, CI smoke test |

Phases 2 and 3 proceed in parallel once phase 1 lands; they share the ingestion
framework from §4.6.

### Phase 0 — implemented

- `external_scans` table (`alembic/versions/a1b2c3d4e5f6_create_external_scan_queue.py`),
  with a `(status, created_at)` index serving the claim query.
- `backend/app/services/scans.py`: create/read/list/cancel plus the runner
  `claim_next_scan` / `complete_scan`. Claiming is `SELECT ... FOR UPDATE SKIP LOCKED`, so
  two runners never receive the same row. Completion is accepted only from `running`, so a
  duplicate report is a `409` rather than a second terminal transition.
- Internal runner API (`backend/app/api/routes/internal_scans.py`) authenticated with a
  shared `RUNNER_SERVICE_TOKEN` compared in constant time. The token is unset by default,
  which disables the internal endpoints entirely.
- Runner scaffold `backend/app/cli/runner.py` (`python -m app.cli.runner --once`). It
  imports no settings or database code and holds only the service token; `run_scan` is the
  seam where garak and PyRIT execution lands in phases 2 and 3.
- Lease recovery: a `running` scan whose claim is older than
  `RUNNER_CLAIM_LEASE_SECONDS` returns to `queued` on the next claim, so a runner that dies
  mid-scan does not strand work. Phase 5 adds heartbeats so long scans extend the lease
  instead of relying on a generous default. Execution is at-least-once across a runner
  crash; the completion guard keeps the terminal transition itself exactly-once.

Exit criterion "a no-op job survives an API restart and completes exactly once" is covered
by `tests/services/test_scans.py` (a queued scan survives a new session) and
`tests/api/test_scans.py` (claim → complete, then a duplicate report is rejected).

### Phase 2 — implemented (runner image pending)

- Garak invocation and report parsing: `backend/app/cli/garak.py`. The generator config is
  written with owner-only permissions and deleted after the run, the probe selection is an
  allow-list bounded at 20, and the report parser refuses a malformed line instead of
  guessing past it.
- Runner dispatch: `backend/app/cli/runner.py` sends a `garak` scan through the shim and a
  not-yet-implemented tool fails the scan with a clear error rather than silently
  no-op'ing. The claim's `llm_token` is threaded into the generator config.
- Ingestion: `backend/app/services/scan_ingestion.py`, called from `complete_scan` so the
  terminal transition and the findings are one transaction. `GET /scans/{id}/findings`
  serves them.
- Data model: `findings.execution_id` is nullable, `findings.external_scan_id` is added,
  and a check constraint requires exactly one origin (`c4d9e1f2a3b5`).

What the exit criterion covers today: the claim → shim → verdicts → findings path is
exercised end to end by `tests/api/test_scan_results.py`, with a stub garak
(`tests/cli/test_garak.py`) that accepts the same argv and emits the same JSONL entry types
as the real tool. What is not covered yet: the runner image (Dockerfile with garak pinned,
compose wiring, shared report volume) and therefore a scan of a live target. Those are the
remaining phase 2 items; the generated generator-config shape and the attempt-record keys
are the two details that must be confirmed against the pinned garak there.

---

## 8. Testing strategy

- **Unit:** `to_model_request` / `to_chat_completion`; probe-family → category mapping;
  verdict → finding mapping; the SSRF rejection path in the shim.
- **Integration:** shim against a stub OpenAI-compatible server; token scoping (a token
  for scan A cannot address scan B or a different target).
- **End-to-end:** a docker-compose run against a local target, asserting findings are
  produced and the raw report is written; assert no credential value ever reaches the
  runner (check the runner's environment and logs).
- **CI:** pin tool versions; a bounded smoke scan (1–3 probes) to keep runtime low.

---

## 9. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Large, brittle dependency trees | Separate image; exact version pins; SBOM |
| Tool version drift changes results | Record `tool_version` per scan; pin in CI |
| Non-deterministic scans | Record the seed/limits in `config`; state reproducibility limits in the doc |
| Provider coverage (non-OpenAI targets) | Shim normalizes to the existing adapter set (`openai_compatible`, `ollama`, `custom_rest`) |
| Long scans outliving the API process | Durable queue (phase 0) |
| Artifact growth | Reuse evidence retention; store reports under the purged report volume |

---

## 10. Open questions

1. **Scope:** are scans project-scoped (recommended, matches targets) or target-scoped?
2. **Granularity:** one `Finding` per garak attempt, or one per (probe, family) aggregate?
3. **Exposure:** do we surface raw garak prompts/outputs as evidence, given they can be
   sensitive? (Affects retention and redaction.)
4. **Profiles:** do we ship curated probe/orchestrator profiles, or expose raw tool flags?
5. **Budget defaults:** what are the default request/token/wall-clock caps per scan?
6. **Runner transport:** internal HTTP (recommended) vs direct DB access.

---

## Appendix A — shim request/response sketch

Request (OpenAI-compatible, no target or URL fields accepted):

```json
{
  "model": "ignored-or-validated",
  "messages": [{"role": "user", "content": "..."}],
  "temperature": 0.7,
  "max_tokens": 256
}
```

Response: the standard `chat.completions` shape, with usage and model echoed from
`ModelResponse`. Streaming is a later enhancement; garak and PyRIT both work without it.
