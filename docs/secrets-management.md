# Aegis Vuldris Secrets Management

How Aegis Vuldris handles secrets in development, CI, and production.

## Principle

**Secrets are never committed and never baked into an image.** Every secret
reaches the running process through an environment variable injected at runtime.

## What counts as a secret

| Secret | Purpose | Exposure if leaked |
|---|---|---|
| `SECRET_KEY` | Derives the Fernet key for target credentials; signs JWTs | Decrypt every stored target credential; forge tokens |
| `POSTGRES_PASSWORD` | Database authentication | Full read/write to all data, including encrypted credentials |
| `STAGING_SSH_KEY` | Deploy access to the staging host | Lateral movement to the deploy target |
| Target credentials | Stored per target via the API | Direct access to the model provider account |
| TLS private keys | HTTPS termination | Traffic interception, credential theft |

`SECRET_KEY` is the highest-impact value. It is the root of trust for
credential encryption: `docs/security-boundaries.md` describes how it is used to
derive the Fernet key, and it is never persisted to disk.

Rotating it invalidates every stored target credential and every issued JWT.
Plan that rotation as a deliberate operation (see below), not a routine one.

## Development

`.env` at the repository root holds local values and is git-ignored.
`.env.example` documents the required keys with empty values.

```powershell
Copy-Item .env.example .env
# then fill in DATABASE_URL and SECRET_KEY
```

Generate a local development key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Local keys are throwaway. Never reuse a development key outside your machine.

## CI

CI uses a fixed, clearly-labelled, non-production key defined in the workflow
file:

```yaml
SECRET_KEY: ci_test_secret_key_not_used_outside_ci_000000
```

This is safe because CI runs against a throwaway database that is destroyed
with the runner, and the value protects nothing real. The convention — a name
that says where it is valid — prevents it being copy-pasted into a real
environment.

`permissions:` in every workflow is scoped to the minimum needed, and
`packages: write` is granted only to the job that pushes images.

## Production

Secrets come from the host environment, populated by a secrets manager. Compose
references them with `${VAR:?message}`, which **fails fast with a clear message**
if a secret is missing rather than starting the service with an empty value:

```yaml
SECRET_KEY: ${SECRET_KEY:?SECRET_KEY is required}
```

The application adds a second layer: `Settings.validate_production_secrets`
raises if `APP_ENV` is `staging` or `production` and `SECRET_KEY` is empty. A
misconfigured deployment cannot start.

### Container build safety

`.dockerignore` excludes `.env` and `.env.*` from the build context, so a secret
file cannot reach the daemon or end up in a layer even by accident. The
Dockerfiles contain no `ENV` with a secret value and no `ARG` used for one.

### Suggested managers

Any of these work; pick based on the hosting platform:

- **Docker Compose secrets** (Swarm) — files mounted at `/run/secrets`.
- **SOPS + age** — encrypted files in the repo, decrypted at deploy time.
- **AWS Secrets Manager / SSM Parameter Store**
- **GCP Secret Manager**
- **Azure Key Vault**
- **HashiCorp Vault**

Whichever is used, the deploy workflow references the values as
`${{ secrets.* }}` and never writes them to a file in the repository.

## Rotation procedure

### Rotating `SECRET_KEY` (breaking)

This invalidates all stored target credentials and all issued tokens. Every
target must have its credential re-entered. Schedule a maintenance window.

1. Announce the window; notify users to re-save target credentials afterwards.
2. Take a database backup and **verify the restore works** first.
3. Record the current credential inventory per target so you can confirm what
   needs re-entering.
4. Generate a new key and update the secrets manager.
5. Restart the backend so it picks up the new key.
6. Existing JWTs are now invalid; users are signed out and must log in again.
7. Stored credentials will fail to decrypt. For each target, re-enter the
   provider credential via the API or UI.
8. Confirm decrypt failures are visible in the audit log, and confirm no
   plaintext was written to logs during the failure.
9. Keep the previous key available (but not active) until every credential has
   been re-entered, in case a rollback is needed.

### Rotating `POSTGRES_PASSWORD` (non-breaking)

1. Update the value in the secrets manager.
2. `ALTER USER aegis WITH PASSWORD '<new>';` in the database.
3. Restart the backend.
4. Verify readiness: `GET /api/v1/system/ready` reports `"database":"ok"`.

### Rotating TLS certificates

Automated via the reverse proxy (Let's Encrypt with a certbot timer, or the
platform's managed certificates). Alert on expiry at 14 days and 7 days. Never
commit certificate or key files. See `docs/deployment.md`.

### Rotating target credentials

Per-target, no global procedure required. Creating a new credential revokes the
previous version automatically and increments the version. A rotation is audited
as `target_credential.created` with `rotated_from` set.

## Auditing

Credential lifecycle events are recorded in the audit log:

- `target_credential.created`
- `target_credential.rotated` (recorded as `created` with `rotated_from`)
- `target_credential.revoked`
- `target_credential.deleted`

Audit entries record credential **metadata only** — id, type, version, target.
Never the value. See `docs/adr/ADR-013-observability-audit-logging-telemetry.md`.
