# Troubleshooting

One reference for the failures that actually happen. Every session should
start with:

```bash
aegis doctor
```

It checks configuration, database connectivity, migration state, and discovered
plugins — and names the fix when one of them is wrong.

## Install and startup

| Symptom | Cause and fix |
|---|---|
| `The aegis-vuldris package is not installed in this environment` | The app refuses to start uninstalled, by design: the version is read from package metadata, not a hardcoded copy. Run `pip install .` (see [`development.md`](development.md)). |
| Backend exits at startup | `SECRET_KEY` missing or empty. Required outside development. Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| Port 8080 already in use | Another app is on it. `docker compose ps`, then stop that app or change the published port. |
| `relation "users" does not exist` | Migrations did not run. On Compose, check `docker compose logs migrate`; the backend only starts after the one-shot `migrate` service exits 0. From source, run `alembic upgrade head`. |
| Backend exits immediately in Compose | The `migrate` service failed first. Read `docker compose logs migrate` and fix the database URL or the failing migration. |
| Frontend container restarts in a loop | tmpfs ownership on the VPS. See the `uid=101,gid=101` entries in the production Compose file ([`deployment.md`](deployment.md)). |
| `alembic check` reports drift | A model changed without a migration. Generate one, review it, commit it. |
| `aegis doctor` says the schema is not at the migration head | Run `alembic upgrade head` (or `docker compose run --rm migrate`). |
| Cannot reach the database from the host | Postgres sits on the Compose `internal` network only. Reach it from a container (for example `docker compose exec postgres psql ...`), not from the host. |

## Database encoding

Aegis Vuldris stores test payloads, model replies, and findings as JSONB, so the
database must use the **UTF8** encoding. Some Windows PostgreSQL installers
create a cluster whose default encoding is `WIN1252`; writes of non-ASCII
payloads (the bundled attack library contains some) are then transcoded into
bytes the read path cannot decode.

| Symptom | Cause and fix |
|---|---|
| `UnicodeDecodeError: 'utf-8' codec can't decode byte ...` during `aegis seed-tests`, `aegis run`, or loading tests in the UI | The database is not UTF8. `aegis doctor` prints a `database encoding:` line and names this problem; `psql` shows it as `SHOW server_encoding`. The encoding is fixed at database creation and cannot be changed in place. Create a new database — `CREATE DATABASE aegis ENCODING 'UTF8' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0;` — point `DATABASE_URL` at it, run `alembic upgrade head`, and re-seed. For a fresh cluster use `initdb -E UTF8`. |

## Accounts and sessions

| Symptom | Cause and fix |
|---|---|
| 401 right after logging in | Token expired (30 minutes default). Sign in again. |
| 429 while testing registration or login | Per-IP rate limits: 10 requests/60 s to login, 5/60 s to register. |
| `EMAIL_ALREADY_REGISTERED` | The address (case-insensitive) exists. Sign in, or use another address. |

## Targets and credentials

| Symptom | Cause and fix |
|---|---|
| "local and private target addresses are not permitted" | The SSRF guard blocks loopback, private, link-local, and cloud-metadata addresses, with DNS-rebinding protection. For local development only, set `ALLOW_LOCAL_TARGETS=true` ([`ssrf-protection.md`](ssrf-protection.md)). |
| Opaque provider 404 on every run | The endpoint is not a base URL. Aegis Vuldris appends the provider path (`/chat/completions`, `/api/chat`) itself, so `https://host/v1/chat/completions` becomes a doubled path. Store `https://host/v1`. |
| `model is required for openai_compatible targets` | Set the target's `model` field. Required for `openai_compatible` and `ollama`; optional for `custom_rest`. |
| "target is not active" / run refuses to start | Executions re-check the target's status at run time. Reactivate the target, or pick another one. |
| Credential saved but the provider rejects it | Credential values are write-only and cannot be read back. Rotate the credential (increments its version) rather than recreating it ([`secrets-management.md`](secrets-management.md)). |

## Executions and grading

| Symptom | Cause and fix |
|---|---|
| "No security tests in this project" / **Run test** disabled | Seed the library (project page button, or `aegis seed-tests`) and make sure the project has at least one target. |
| Execution stays `running` | The model is slow or hanging. Lower the test's `timeout_seconds`. |
| Execution `failed` | The provider or target errored — **not necessarily a security issue**. Read the execution's error column. |
| Judge-based test returns `inconclusive` | Judging could not run. There are exactly four causes: no judge target is configured on the project; the judge target is inactive; the judge would be the target under test with the same model (a model must not judge its own answers); or the judge call failed. Fix the judge target in the project workspace (or `PATCH /projects/{id}` with `judge_target_id`). |
| Test result is `needs_review` | A pattern matched and nothing confirmed it. Either configure a judge target (the confirmation judge resolves matches to confirmed/dismissed) or triage the finding yourself: **Confirm attack landed** re-grades the run as a failure; **Dismiss as false positive** (reason required) re-grades it as a pass. A no-judge project shows this state for every deterministic match — that is the intended, honest verdict, not an error. |
| A finding looks wrong on a well-behaved model | Keyword/regex grading is lexical, which is why matches start as `candidate` findings. Dismiss it with a reason, and check the per-test dismissed rate in **Detection quality** — a noisy test's patterns need tightening ([`grading-accuracy.md`](grading-accuracy.md)). |

## Reports

| Symptom | Cause and fix |
|---|---|
| Report download returns 404 | Press **Generate** first — a created report has no artifact until generated. |
| Production download 404s while local works | The report volume is not mounted, or `AEGIS_REPORT_DIR` does not match the mount path. |

## CLI and CI

Exit codes are a contract (`docs/ci-integration.md`): **0** success, **2** a
configured gate fired, **4** operational error, **1** usage/configuration.

| Symptom | Cause and fix |
|---|---|
| `aegis run` exits 2 | A configured gate fired: `--fail-on` crossed, a `--baseline` regression, or `--fail-on-inconclusive`. Without those flags, inconclusive results exit 0. |
| `aegis` exits 4 | Operational error (target unreachable, scanner problem). The gate did not evaluate — this is not a regression verdict. |
| `aegis` exits 1 | Usage or configuration error. No scan ran. |
| GitHub Action fails before scanning | The composite action requires the `image` input; see [`ci-integration.md`](ci-integration.md). |

## Plugins and extensions

| Symptom | Cause and fix |
|---|---|
| An installed plugin does not load | `aegis doctor` lists rejected plugins with reasons: wrong `PLUGIN_API_VERSION` (current: `1`), import failure, or contract mismatch. Rejected loads are also audited as `plugin.rejected`. |
| All plugin discovery stopped | `ALLOW_THIRD_PARTY_PLUGINS=false` disables discovery deliberately. Set it to `true` (the default) or leave it unset. |
| Unknown report format raises an error | Third-party export formats need a discovered `aegis.report_exporters` plugin. Unknown formats fail loudly instead of silently rendering JSON. |

## Demo

| Symptom | Cause and fix |
|---|---|
| Running anything against the demo target fails | By design. The demo target uses the reserved `.invalid` domain and cannot be reached; the demo is a recording, marked `[DEMO]` everywhere. |
| Removing demo data | `aegis demo --email you@example.com --prune`. |
