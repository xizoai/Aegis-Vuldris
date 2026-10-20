# Changelog

All notable changes to Aegis Vuldris are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-10-20

Initial functional release. The platform can register users, manage projects and
targets, run security tests against AI model endpoints, and produce scored,
evidence-backed reports through a web UI.

### Added

#### Security foundation

- JWT + Argon2id authentication with project-scoped RBAC and audit logging.
- Fernet-encrypted target credentials at rest, with a PBKDF2-derived key that is
  never persisted, credential versioning, and revocation.
- Outbound network policy blocking loopback, link-local, and private CIDRs, cloud
  metadata hosts, DNS rebinding, and unsafe redirects.
- Per-IP rate limiting on `/auth/login` and `/auth/register`.
- RBAC guards preventing a project from losing its last admin, including
  self-demotion and self-removal cases.
- Structured JSON logging with request-ID correlation on every log line.

#### Execution engine

- In-process async execution engine running security tests against
  `openai_compatible`, `ollama`, and `custom_rest` adapters.
- Full lifecycle: `PENDING → RUNNING → SUCCEEDED/FAILED/CANCELLED` with retries,
  exponential backoff, per-execution timeouts, and cancellation.
- Multi-turn conversation execution that preserves full conversation history.
- Rule-based finding classification with keyword and regex grading, plus optional
  judge-model grading.
- Automatic request/response evidence capture linked to each finding.

#### Attack content library

- 224 seeded test cases across prompt injection (67, including 42 encoded
  variants), jailbreak (108, including 88 adversarial-suffix cases), privacy and
  data leakage (20), RAG attacks (14), and agent/tool-use (15).
- Typed YAML/JSON test-case schema with validation and documentation.

#### Risk scoring and reporting

- Custom severity and risk rubric, with content-based automatic severity
  derivation and an explicit MEDIUM fallback.
- Report generation in JSON and Markdown, with OWASP GenAI LLM Top 10:2026 compliance
  mapping surfaced per finding.
- Report versioning, machine-readable data snapshots, and run-to-run comparison
  producing new / resolved / regressed / improved findings.
- Report download endpoint.

#### Web frontend

- React 19 + TypeScript single-page application covering sign-up, projects,
  targets, credentials, test execution, findings, evidence, and reports.
- Typed API client with bearer-token injection and structured error handling.
- Session-scoped token storage that never writes to `localStorage` and refuses
  to send an expired token.
- Credential values are write-only in the UI: the API client deliberately omits
  the backend's credential-resolve endpoint.
- One-click loading of the 224-case attack library from the project page, backed by
  an idempotent seeding endpoint; live execution status polling that stops when no
  run is in flight.

#### Deployment and CI

- Multi-stage backend Dockerfile running as a non-root user with a healthcheck.
- Frontend Dockerfile building the SPA and serving it from unprivileged nginx
  with SPA history fallback and an internal `/api` proxy.
- Local development and hardened production Compose stacks; the production stack
  publishes no public ports, drops all Linux capabilities, and uses read-only
  root filesystems.
- GitHub Actions gates for Ruff lint and format, Pyright, pytest against a real
  PostgreSQL service, `alembic check`, `pip-audit`, and the frontend quality
  suite, plus a container build-and-smoke workflow.
- Tagged-release workflow that publishes provenance-attested images with SBOMs and
  supports an optional staging deployment.

### Fixed

- **Cross-tenant authorization bypass in bulk test seeding.** Loading the bundled attack
  library authorized each individual test create but ran no check when there was nothing
  left to create, so an unrelated user could read another project's test count from the
  summary. Seeding now authorizes up front and requires mutation rights, so viewers are
  denied too.
- Judge-model grading returned `PASS` when the judge was unavailable, reporting a
  target as safe purely because grading could not run. It now returns
  `INCONCLUSIVE`, which avoids a false negative on a security test.
- Multi-turn execution dropped the user's earlier turns from conversation
  history, weakening multi-turn attack sequences. Prior turns are now preserved.
- Report comparison read live database state, making two historical runs
  indistinguishable. Comparison now reads persisted per-run data snapshots.
- `Execution.result` declared an index that no migration created; `alembic check`
  now reports no drift.

### Security notes

- Only authorized systems should be tested with Aegis Vuldris. Creating a target
  represents an attestation of authorization.
- Credential plaintexts are never returned by the API and are never displayed in
  the UI.


### Model assurance, calibration, and release polish

#### Added

- Model assurance foundation (P0 slice — reproducibility). Targets now carry an
  optional model profile: declared `model_version`, target-level `system_prompt`,
  and generation defaults (`temperature`, `top_p`, `max_tokens`, `seed`). Test
  cases remain the more specific instruction and override target defaults. Every
  execution snapshots the effective profile and a digest of the test definition
  in `run_manifest`, exposed through the execution API, JSON/Markdown reports,
  and a **Model profile** viewer in the workspace. The target form and detail
  page can create and edit the profile. A **Model comparison** matrix shows the
  latest successful result per target and test, so the same suite can be used
  for procurement bake-offs and fine-tune deltas. Findings now map to the
  official OWASP GenAI LLM Top 10:2026 categories, with an informative NIST AI
  RMF / EU AI Act / ISO 42001 crosswalk and version recorded in reports.
  Migration `a3f4b5c6d7e8` adds the profile columns and `run_manifest`.
  Repositioning docs now state the model-endpoint scope and mark the bundled RAG
  and agent cases as experimental prompt-level probes.

- Judge calibration harness (P0 slice — evidence). `aegis judge-calibration`
  measures the confirmation judge against labeled transcripts instead of assuming
  that strict JSON means accuracy. It reports stage-one (lexical) recall, judge
  accuracy, exploited precision and recall, refusal recall, and Cohen's κ, and
  lists every mismatch and abstention; the two-stage contract is preserved
  throughout (an abstention is never agreement, and a stage-one match on a
  refusal is a candidate, not a false positive). The bundled corpus holds 25 safe,
  hand-written transcripts — 13 known exploits, 12 known refusals — including two
  instructions aimed at the judge itself and one base64-encoded leak the lexical
  stage cannot see (measured stage-one recall: 92.3%, 12/13). Labeled benchmark
  subsets import from `.jsonl`, `.json`, or `.csv` with tolerant
  AdvBench/JailbreakBench/StrongREJECT-style column names; items without grading
  rules still calibrate the judge. Live runs use the real adapter stack, name the
  judge target and model, and `--record` saves raw outputs so `--judge-outputs`
  can replay them with no model; `--min-detector-recall`, `--min-judge-accuracy`,
  and `--min-judge-recall` make it a CI gate. A recorded live run against
  `deepseek-ai/DeepSeek-V4-Flash-0731` is committed under `docs/calibration/`:
  25/25 decided, 96.0% accuracy, κ 0.92, with the judge-injection transcript as
  the one miss. Docs: `docs/judge-calibration.md`.

- Two-stage grading with human triage (roadmap step 1 — trust). A deterministic
  pattern match is now a **candidate**, not a verdict: the project's judge target
  resolves it (`exploited` → confirmed, `refused` → dismissed, anything unusable
  leaves it unresolved), a reviewer can confirm / dismiss / re-open it with a
  recorded reason, and tests that are decisive by construction opt out with
  `grading.confirm: false`. Only confirmed findings produce `fail`; unresolved
  matches produce the new `needs_review` execution result, which is never a pass.
  New endpoints: `POST /findings/{id}/triage`, `GET /executions/{id}/steps`
  (transcript, redacted on read), `POST /executions/{id}/replay`, and
  `GET /tests/triage-stats`. The workspace gains confirmation badges, triage
  controls, a transcript viewer, a replay action, and a Detection quality card.
  The CLI prints `[NEEDS REVIEW]`, counts candidates as `(unconfirmed candidate)`,
  exits 2 from `aegis verify` on unconfirmed results, and ships
  `aegis grading-accuracy` (currently 0 false positives across 2240 evaluations)
  as an offline CI precision gate. Reports and risk scoring exclude dismissed
  findings and count confirmed / candidate / dismissed; migration
  `d7e8f9a0b1c2` adds the confirmation columns.

- `docs/architecture.md` is no longer a stub: it now documents the system as
  implemented — the component map (frontend, API, services, adapters, data,
  CLI), the execution pipeline with its grading and verification semantics,
  the security boundaries, deployment topologies, the quality gates, and the
  extension points — with every statement checkable against the code. The
  stub's future-tense component list is gone; capability limits stay in
  OVERVIEW sections 8–9 and the decision records moved to the ADRs.

- Five architecture decision records completing the P3 register:
  [ADR-016](docs/adr/ADR-016-open-core-edition-boundary.md) — open-core
  edition boundary (one repository, one wheel, edition as a defaults switch,
  billing isolated behind an import-tested boundary, verdict parity);
  [ADR-017](docs/adr/ADR-017-organizations-tenancy-model.md) — organizations
  and tenancy (nullable-org migration path M1→M1b, backfill and
  `aegis org adopt-orphans`, 404-never-403 cross-tenant semantics,
  denormalized `executions.organization_id`);
  [ADR-018](docs/adr/ADR-018-durable-jobs-postgres-dispatcher.md) — durable
  jobs on Postgres with a dispatcher interface (`JOB_DISPATCHER=inline|db`),
  not Redis/Celery, for the pilot;
  [ADR-019](docs/adr/ADR-019-third-party-plugin-execution-policy.md) —
  third-party plugin execution policy (allowed in community, disabled in the
  cloud pilot, sandboxing explicitly deferred);
  [ADR-020](docs/adr/ADR-020-contribution-licensing-policy.md) — Apache-2.0
  stays, DCO over CLA, private security reporting, dependency review.
  ADR-016/019/020 record decisions already shipped; ADR-017/018 carry
  explicit implementation-pending status for the SaaS workstream.

- Documentation pass for adoption. New `docs/faq.md` answers the questions
  that decide whether to try the tool (is it a pentest? does it phone home?
  which providers? what does `inconclusive` mean? license? Windows?), and
  `docs/troubleshooting.md` is now the single troubleshooting reference —
  install and startup, accounts, targets and credentials, executions and
  grading (including all four judge `inconclusive` causes), reports, the CLI
  exit-code contract, plugins, and the demo — superseding the tables
  previously duplicated in the Manual and the deployment guide. The README
  gains a supported-targets table (verified against
  `app/adapters/registry.py`), a first-real-assessment CLI line, and a "what a
  finding looks like" sample taken verbatim from the recorded demo fixture.

- Judge-model grading, wired end to end. A project now names a **judge target**
  — a target that belongs to the project — whose model grades
  `method: judge_model` test cases; set it in the project workspace or via
  `PATCH /projects/{id}` with `judge_target_id` (nullable, `ON DELETE SET
  NULL`, migration `c9d0e1f2a3b4`). The engine resolves the judge through the
  same adapter registry, credential store, and network policy as any target,
  and `ModelRequest` gained an optional `model` override (honored by all three
  adapters) so a case can pin a different model on the judge endpoint via
  `grading.judge.model` — now optional, because which strong model exists is
  an operator choice. A model never judges its own answers (ADR-005): if the
  judge target is the target under test with the same effective model, judging
  is refused. Every unavailability path — no judge target configured, inactive
  judge target, refused self-judging, failed judge call — yields
  `INCONCLUSIVE`, never `PASS`.

- Versioned extension contracts with entry-point discovery
  (`docs/extension-points.md`). Four groups load through one shared loader
  (`app/services/extensions.py`): `aegis.graders` (ResponseGrader
  implementations — the engine already accepts any grader through its
  constructor seam), `aegis.report_exporters` (new report formats; the
  generator now dispatches unknown formats to discovered exporters and
  raises a clear error instead of silently rendering JSON),
  `aegis.attack_plugins` (directories of YAML cases — attacks stay data,
  never imported code), and `aegis.adapters` (adapter overrides for a
  provider value, consulted by `AdapterRegistry` before the static
  registrations). Every loaded object must match `PLUGIN_API_VERSION`;
  mismatches, import failures, and contract violations are rejected with
  clear reasons and auditable `plugin.rejected` / `plugin.loaded` entries
  rather than being skipped silently. `ALLOW_THIRD_PARTY_PLUGINS` (default:
  allowed, a self-hosted responsibility) disables all discovery when
  false — the switch a hosted pilot will set. `aegis doctor` prints a
  plugin summary. `tests/fixtures/plugins/` is the working reference plugin,
  discovered through the real `importlib.metadata` machinery by
  `tests/services/test_extension_registry.py` (hand-crafted dist-info, no
  fake registries); `report_exporters.py` ships the JSON and Markdown
  reference implementations.

- Release publishing. Tagging now produces a GitHub Release automatically:
  the new `github-release` job in `release.yml` runs after the images are
  built and staging serves, extracts the changelog section for the tag with
  `scripts/extract_release_notes.py`, appends an **Upgrade notes** block
  (migration head at the release, breaking-changes pointer, rollback rules),
  and publishes it via `gh release create`. A tag without a changelog section
  fails the workflow instead of shipping silently. The application version is
  now single-sourced: `/`, `/system/info`, and the FastAPI metadata read
  `APP_VERSION` from the installed package metadata (`app/core/version.py`),
  so bumping `pyproject.toml` is the only edit a release needs — pinned by a
  test that fails on a stale install. `docs/release-process.md` documents the
  pre-tag `alembic check` gate and the version bump step.

- Contribution and reporting infrastructure. `CONTRIBUTING.md` documents the
  clone-to-merged-PR path, the definition of done, the module-boundary and
  security-semantics rules reviews enforce, and the DCO sign-off
  (`Signed-off-by:`, checked at merge time). `CODE_OF_CONDUCT.md` is the
  Contributor Covenant 2.1. `SECURITY.md` defines private vulnerability
  reporting, scope, and disclosure commitments — security issues never go
  through public issues, and the issue templates say so (`.github/config.yml`
  redirects them). Bug reports ask the quick-start question and request
  `aegis doctor` output; feature requests carry the authorized-testing
  reminder. The PR template carries the quality gates plus a security
  checklist ("does this weaken an existing security test?", fix-state rules,
  exit-code/API contracts). Dependabot covers pip, npm, actions, and docker;
  a new `dependency-review.yml` fails PRs on high-severity CVEs or copyleft
  licenses in changed lockfiles and manifests.

- CI integration. `integration/github-action/action.yml` is a composite
  action that runs `aegis run` in a container against your deployment,
  writes a job summary (per-test results, totals, matched reasons), and
  propagates the exit-code contract unchanged: exit 2 is reported as a
  configured regression, exit 4 as a scanner error, and neither is remapped.
  `--baseline` accepts a report id or a workspace-relative artifact path
  (the workspace is mounted read-only). `docs/ci-integration.md` documents
  the action, every input, the raw-CLI variant for non-GitHub CI, and the
  security notes; `tests/test_github_action.py` guards the contract. The
  `image` input is required and documented as such — no official image is
  published until the first tagged release.

- Regression gate as a service. `backend/app/services/regression.py` owns the
  single finding-set diff (new / resolved / regressed / improved / unchanged,
  matched by category and title) behind both the API's report comparison and
  the CLI's `--baseline` gate, plus the verdict rules: exit 2 only on
  configured regressions, never on resolved or improved findings, and never on
  inconclusive runs unless `--fail-on-inconclusive` is set.
  `aegis run --baseline` now also accepts a **file**: the saved JSON report
  artifact from a previous run (`aegis export --output`), so a CI job can
  commit its last good baseline and gate every later run against it without
  database reports. Report artifacts can embed the same comparison:
  `POST .../reports/{id}/generate` with `baseline_report_id` (or
  `aegis export --baseline`) writes a "changes since baseline" section into
  the JSON and Markdown exports, with project-scoped authorization on the
  baseline. Covered by `tests/services/test_regression_gate.py`,
  end-to-end CLI and API tests, and the existing comparison suite.

- Zero-credential demo. `aegis demo --email <account>` seeds a synthetic
  project — a recorded execution with transcript steps, a high-severity
  finding, and evidence — from the bundled fixture
  (`backend/app/fixtures/demo/demo_run.json`), so every page is explorable
  with no provider credentials. Honesty rules, pinned by
  `tests/cli/test_demo.py`: every seeded row is `[DEMO]`-marked, findings
  land in their default triage state (never `fixed`, never `verified`), the
  demo target uses the reserved `demo.invalid` domain so nothing can
  accidentally run against it, and seeding is idempotent per account.
  `aegis doctor` now reports whether demo data is seeded, `aegis demo --prune`
  removes it, and the Beginner-Guide gains the zero-credential tour plus the
  full detect → fix → verify walkthrough.

- The `aegis` CLI: one console script, installed with the package. `aegis
  doctor` checks versions, `SECRET_KEY`, database connectivity, the Alembic
  revision, and each active target's network policy; `aegis run` runs a
  project's tests against one target through the same service layer and engine
  the API uses; `aegis verify` re-runs the exact attack behind a finding and
  reports the verdict; `aegis export` generates report artifacts and can copy
  them; `aegis seed-tests`, `aegis retention prune`, and `aegis clear-history`
  wrap the existing module commands unchanged. Exit codes are a documented
  contract — 0 success, 1 usage/configuration, 2 a configured condition
  matched (`--fail-on`, `--baseline REPORT_ID`, `--fail-on-inconclusive`), 4
  operational error — so a CI job can fail on a threshold without treating a
  broken scanner as a finding. `--json` prints the full machine-readable
  summary. The CLI adds no business logic; `tests/cli/test_main.py` pins every
  exit code against the real engine, and `docs/Manual.md` documents the
  surface.

- One-command quick start. `docker compose up --build` now reaches a migrated
  database with no manual Alembic step: a one-shot `migrate` service runs
  `alembic upgrade head` in the same image and configuration as the backend,
  which only starts after it exits 0 (`service_completed_successfully`), so a
  failed migration stops the stack instead of serving a stale schema. The
  container smoke job walks the documented first-run API path — register,
  sign in, create a project, seed the attack library, list it back — and
  asserts the live schema matches the models with `alembic check` instead of
  mutating it. `.env.example` now documents `ALLOW_LOCAL_TARGETS`.

- `docs/configuration.md`, generated from `app/core/config.py` and
  `.env.example` by `scripts/generate_configuration_docs.py`, with a test that
  fails when the reference drifts or a setting is missing from the template.
  The packaging test now also builds the wheel, asserts the `aegis` console
  script is exported, installs the wheel into a throwaway venv, and runs it.

- The isolated validation loop, end to end. `docs/patch-workflow.md` documents
  the full detect → propose → apply → verify path: draft a candidate patch,
  review it, apply it yourself in a staging copy, point a same-project
  `target_id` at the staging deployment, and re-run the exact attack. The
  honesty rule is unchanged — only a passed rerun moves a finding to
  `verified`; a failed rerun keeps it `fixed` and says so in the audit trail.
  `examples/quickstart-vulnerable-app/` is the loop's reference app: a
  scripted (not ML) vulnerable demo model carrying a fictional escalation
  code, and its remediated `fixed/` variant, both loopback-only and offline.
  `tests/integration/test_quickstart_demo.py` (marked `slow`) executes the
  documented loop against both variants over real HTTP in CI, so the guide
  cannot drift from the code.

- Candidate patch drafting (AutoFix Level 1, draft stage). A finding can now
  produce a review-only candidate patch via
  `POST /projects/{id}/assessments/findings/{id}/patches`, listed via `GET` on
  the same path. By default the draft is deterministic: it records the
  remediation intent and writes **no diff on purpose**, because a diff without
  comprehension of the target code would be a fabricated fix. Pass
  `drafting_target_id` — an active `openai_compatible` or `ollama` target in
  the same project — plus `file_path` and `file_content`, and that model drafts
  a unified diff from exactly the supplied file, together with the finding
  summary and evidence metadata; stored credentials and raw evidence content
  are never sent, the prompt hash is recorded, and the response is validated as
  a unified diff before anything is stored (a `NO_DIFF` refusal is recorded as
  an honest no-diff draft; prose or unsafe paths are rejected). A proposal
  never changes code and never changes the finding's state: applying it is
  manual, `fixed` stays a human claim, and only a passed verification rerun
  marks a finding `verified`. Drafting is a write, audited as `patch.proposed`,
  and a migration adds `patch_proposals`. The workspace gains a **View
  candidate patch** panel with a diff viewer and `.diff` download — and no
  apply button.

- Bulk execution. Select any number of security tests with a select-all
  checkbox and run them against one target in a single action.
  `POST /executions/bulk` creates every execution up front, so an invalid
  selection is rejected before anything runs, then returns `202` with the
  execution ids. The browser reads progress from the executions it already
  polls, keyed by `test_id`, so the bulk panel and the executions table can
  never disagree. Concurrency is bounded at 2 rather than one task per
  execution, which would exhaust a local model's queue and turn the suite
  into timeouts that read as failures.
- Judge-model grading now runs against a dedicated, project-scoped judge target.
  A test sets `grading.judge.target_id`; the judge uses its own provider,
  endpoint, model, and encrypted credential, and is subject to the same outbound
  network policy as any other model call. The old behaviour — grading with the
  target under test and no credential — is gone. A missing, foreign, or inactive
  judge target fails the execution with a configuration error instead of
  silently returning `inconclusive`.
- The Aegis LLM shim, the outbound leg of the garak/PyRIT pipeline. A scan
  claimed by the runner now mints a scan-scoped token binding one target for
  one attempt (with a per-claim nonce, so a scan that is requeued or
  terminates invalidates its old token immediately).
  `POST /api/v1/external/llm/{scan_id}/v1/chat/completions` accepts an
  OpenAI-shaped request whose body cannot name a destination — URLs, hosts, and
  target ids are rejected, and the caller's `model` is dropped in favour of the
  bound target's — and forwards it through the same adapter path as a native
  run, so SSRF policy, DNS pinning, encrypted credentials, and response limits
  all apply. Streaming is refused; a per-scan rate limit guards the target; and
  the only volume signal is a counted per-scan request counter, never logged
  bodies.

- A durable external scan queue, the foundation for running garak and PyRIT at
  run time. `POST /projects/{id}/scans` queues a scan; a separate runner claims
  work through `POST /internal/scans/claim` and reports a terminal state through
  `POST /internal/scans/{id}/complete`. State lives in the `external_scans` table,
  so a queued scan survives an API restart, and claiming uses
  `FOR UPDATE SKIP LOCKED` so two runners never receive the same job. A duplicate
  report is a `409`, so a job completes at most once. The runner endpoints are
  authenticated with a shared `RUNNER_SERVICE_TOKEN` and stay disabled while it is
  unset. `python -m app.cli.runner` dispatches a claimed scan to its tool (garak
  today; PyRIT lands in a later phase).

- The garak integration, the first external scan that produces findings. A
  claimed garak scan runs against the Aegis LLM shim, so the tool reaches the
  target through Aegis and never holds a target credential or URL. Probe
  selection is an allow-list (`dan`, `promptinject`, `encoding`, and other
  content-only families) bounded at 20 probes, and the runner refuses a
  selection outside it rather than running whatever was asked for.
  - The runner reports normalized verdicts alongside its terminal state, so a
    scan completes and its findings land in one call: there is no window where a
    scan is finished but its results are missing, and a retry after a lost reply
    is a `409` rather than a duplicate ingest.
  - Ingestion maps failures to findings, counts passes, and treats an unjudged
    attempt as `inconclusive` — never as a pass. Severity comes from the shared
    `severity_scorer` and OWASP classification from the shared
    `OWASP_LLM_TOP_10` table, extended with a probe-family mapping, so scan
    findings sort alongside native ones.
  - Findings carry the probe, detector, category, OWASP mapping, a trigger
    count, and a pointer to the raw record. Prompts, model output, and the
    triggering strings stay in the raw report under the report volume; they are
    attack content, and when a probe works they are the leaked data itself, so
    they never enter the database or the API.
  - `GET /api/v1/scans/{id}/findings` returns a scan's findings, most severe
    first, to the project's members.
  - Findings may now come from either a native execution or an external scan.
    `findings.execution_id` is nullable, `findings.external_scan_id` is added,
    and a check constraint keeps it to exactly one origin.

#### Fixed

- Executions left `pending` or `running` by a process restart are now failed at
  startup, with the previous status recorded in an `execution.reconciled` audit
  event, instead of remaining stuck forever. Execution steps need no repair
  because they are only written after a turn succeeds.

- Review-only remediation plans (AutoFix Level 1). Every finding can be turned
  into a deterministic plan — likely root cause, recommended controls,
  verification steps, and explicit limitations — via
  `GET /projects/{id}/assessments/findings/{id}/remediation`. The plan names the
  remediation strategy (`application`, `llm_behavior`, `hybrid`, or
  `manual_review`), carries the finding's attack id and version for a
  reproducible verification rerun, and is audited as `remediation.viewed`.
  Nothing is applied: `status` is `suggested`, `patch_available` is `false`, and
  human approval is required. The project workspace renders the plan per finding
  behind a **View suggested fix** button.

- Verified fixes: the finding lifecycle now separates a human claim from
  deterministic evidence. `POST /…/findings/{id}/verifications` queues a rerun of
  the exact attack that produced a finding — same `test_id`, original target by
  default with a same-project override — and `GET` on the same path lists past
  runs. Only a rerun that no longer reproduces the finding moves it to the new
  `verified` state; a rerun that still reproduces it, or ends inconclusive,
  leaves it `fixed`. `verified` is rejected by the findings API as an editable
  status, every verdict is audited (`finding.verification_passed` /
  `finding.verification_failed` / `finding.verification_inconclusive`), and the
  workspace adds a fix-state control, a **Verify fix (re-run attack)** button,
  and a `verification` badge on rerun rows in the executions table. A migration
  adds the `finding_status.verified` enum value and
  `executions.verifies_finding_id`.

- Declarative attack plugins with stable `attack_id`/`version` identity. Test
  cases carry that identity into the seeded config, so a finding names the exact
  attack that produced it. Grading is pluggable through a `ResponseGrader`
  protocol whose implementations carry their own id and version.

- Report comparison in the project workspace: pick a baseline and a current
  snapshot to surface new, resolved, regressed, and improved findings from each
  run's persisted data snapshot.

- `aegis doctor` now checks the PostgreSQL server encoding and names the fix
  when it is not UTF8. A `WIN1252` cluster (the default of some Windows
  installers) silently transcodes non-ASCII JSONB payloads — the bundled attack
  library contains some — and every later read died in a byte-level
  `UnicodeDecodeError` that never mentioned the database. The Compose files
  now pass `--encoding=UTF8` to `initdb`, `.env.example` states the
  requirement, and
  [`troubleshooting.md`](docs/troubleshooting.md#database-encoding) documents
  the recreate-and-migrate fix.

- `docs/OVERVIEW.md`'s attack-library composition table and
  `docs/Manual.md`'s prompt-injection encoding count now match the shipped
  library — 67 prompt-injection cases (42 garak-derived encodings) and 108
  jailbreak cases (88 garak-derived suffixes), as
  [`attack-library-attribution.md`](docs/attack-library-attribution.md) and the
  seed tests already documented. The stale table read "20/20"; a live seed on
  this machine produced all 224 cases and pinned the real counts per category.

- Confirmation-verdict parsing now reads every complete JSON object in the
  judge's answer: repeated *agreeing* verdicts are collapsed, while conflicting
  verdicts are rejected as ambiguous. A live calibration run found that a judge
  emitting the same verdict object twice (`{...}{...}`) was scored as an
  abstention, because the parser sliced from the first `{` to the last `}`; six
  of 25 answers were lost that way. A conflict still leaves the candidate
  unresolved rather than letting position decide.

- `aegis judge-calibration --record` now creates missing parent directories.
  Previously a path typo discarded a completed live run after the judge calls
  had already been made.

- Execution timestamps in a project's executions table now wrap inside the
  fixed Started column instead of painting over the status badge at common
  viewport widths.

- Changelog compare and release links now point at `xizoai/Aegis-Vuldris`
  instead of a non-existent `aegis-vuldris/aegis` repository.

#### Changed

- The Docker Compose quick start no longer requires a manual
  `docker compose exec backend alembic upgrade head` (or the equivalent seed
  step): the `migrate` service applies the schema during `up`, and the README
  and Manual now use `aegis seed-tests` instead of the module invocation.
- A grading rule whose regex cannot compile now yields `INCONCLUSIVE` instead of
  a false `PASS`, so a broken rule can never read as a clean result.
- The target dropdown lists only this project's active targets. Previously
  another project's target could be selected and the run submitted silently
  without it.
- The README is now a public-facing project page: a centered brand header,
  CI and license badges, product screenshots, a two-stage grading diagram, a
  curated documentation index, and explicit authorized-use and scope
  statements. Internal strategy and audit notes are no longer linked from it.
- Packaging metadata now declares the real repository URLs, keywords,
  classifiers, and a `CITATION.cff` for GitHub's citation support.
- Repository cleanup for a public release: internal strategy, audit, and
  readiness working notes are not part of the public tree, and the remaining
  docs no longer link to them. Documentation and templates
  that still pointed at a previous repository location now use
  `xizoai/Aegis-Vuldris`, the volatile project-facts table no longer carries
  stale line and test counts, and ADR references no longer point at internal
  planning documents. Added `docs/public-release-checklist.md` with the
  history, secret, GitHub-setting, and clean-clone checks to run before the
  repository becomes public.

[Unreleased]: https://github.com/xizoai/Aegis-Vuldris/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/xizoai/Aegis-Vuldris/releases/tag/v0.1.0
