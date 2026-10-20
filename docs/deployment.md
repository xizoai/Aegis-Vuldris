# Aegis Vuldris Deployment Guide

Deploying Aegis Vuldris to a Linux VPS with Docker Compose, per
[`ADR-015`](adr/ADR-015-production-deployment-operational-architecture.md).

## Architecture

```text
                        Internet
                            |
                    :443 (HTTPS)
                            |
                  +-----------------+
                  |  Reverse proxy  |  Caddy / nginx / Traefik
                  |  TLS termination|
                  +--------+--------+
                           |
              +------------+-------------+
              |                          |
              v                          v
    +-------------------+     +-------------------+
    | Frontend          |     | Backend API       |
    | nginx, static SPA |     | FastAPI, :8000    |
    | proxies /api      |     | (not public)      |
    +-------------------+     +---------+---------+
                                       |
                        +--------------+--------------+
                        |                             |
                        v                             v
              +-------------------+         +-------------------+
              | PostgreSQL        |         | Outbound to        |
              | (internal only)   |         | model providers   |
              +-------------------+         +-------------------+
```

The reverse proxy is the only Internet-facing component. Neither the backend nor
the database publishes a port.

## Requirements

- Linux VPS with Docker Engine and Docker Compose v2
- A domain with DNS pointed at the host
- Persistent disk for the database and generated reports

Recommended minimum: 2 vCPU, 2 GB RAM, 20 GB disk. The backend has a 1 GB memory
limit in the production Compose file; executions are I/O-bound waiting on model
providers, so CPU is rarely the constraint.

## 1. Provision the host

```bash
# Create a deploy user with sudo
adduser --disabled-password --gecos "" aegis
usermod -aG sudo aegis

# Hardened SSH: disable password auth and root login
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# UFW: only SSH and HTTPS
sudo ufw allow OpenSSH
sudo ufw allow 443/tcp
sudo ufw allow 80/tcp      # only if needed for certificate issuance/redirect
sudo ufw enable
```

PostgreSQL is intentionally **not** opened in the firewall. It is reachable only
on the internal Docker network.

## 2. Fetch the deployment files

The release workflow rsyncs `docker-compose.production.yml`. For a manual
setup, copy the file and the deploy script onto the host:

```bash
sudo mkdir -p /opt/aegis && sudo chown aegis:aegis /opt/aegis
```

## 3. Configure secrets

Create an environment file readable only by the deploy user:

```bash
sudo install -m 600 /dev/null /opt/aegis/.env
sudo chown aegis:aegis /opt/aegis/.env
```

Populate it from your secrets manager (see
[`docs/secrets-management.md`](secrets-management.md)):

```dotenv
POSTGRES_USER=aegis
POSTGRES_PASSWORD=<high-entropy>
POSTGRES_DB=aegis
SECRET_KEY=<64 hex chars from secrets.token_hex(32)>
ACCESS_TOKEN_EXPIRE_MINUTES=30
LOG_LEVEL=INFO
AEGIS_BACKEND_IMAGE=ghcr.io/<org>/aegis-backend:v0.1.0
AEGIS_FRONTEND_IMAGE=ghcr.io/<org>/aegis-frontend:v0.1.0
RUNNER_SERVICE_TOKEN=<high-entropy>
```

`RUNNER_SERVICE_TOKEN` is optional. It is the shared secret the external scan
runner presents on the internal claim/report endpoints; leave it unset and those
endpoints are disabled. It is not needed until the garak/PyRIT runner is
deployed (see [`docs/integration-plan-garak-pyrit.md`](integration-plan-garak-pyrit.md)).

Compose reads `.env` automatically from the project directory. The file is
git-ignored and excluded from the Docker build context.

> `SECRET_KEY` is the root of trust for credential encryption. Losing it makes
> every stored target credential permanently undecryptable. Back it up in your
> secrets manager, separately from the database.

## 4. Start the stack

```bash
cd /opt/aegis
docker compose --env-file .env -f docker-compose.production.yml pull
docker compose --env-file .env -f docker-compose.production.yml \
  run --rm migrate
docker compose --env-file .env -f docker-compose.production.yml up -d
docker compose --env-file .env -f docker-compose.production.yml ps
```

Migrations run as a separate step **before** the new version receives traffic.

## 5. Reverse proxy and TLS

Example Caddy configuration — it provisions and renews certificates
automatically:

```caddyfile
aegis.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:8080
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
}
```

To publish the frontend to the host for the proxy, bind to loopback in
`docker-compose.production.yml`:

```yaml
  frontend:
    ports:
      - "127.0.0.1:8080:8080"
```

Binding `0.0.0.0:8080` would expose the app without TLS. Do not do it.

## 6. Verify the deployment

```bash
# From the host
curl -fsS http://127.0.0.1:8080/api/v1/system/ready     # {"status":"ok","database":"ok"}

# From outside, over TLS
curl -fsS https://aegis.example.com/api/v1/system/ready
```

Both should report `"status":"ok"`. Then walk the real user path: sign up, create
a project, add a target, run a test, generate a report.

## Operations

### Logs

```bash
docker compose -f docker-compose.production.yml logs -f backend
docker compose -f docker-compose.production.yml logs -f frontend
```

Logs are JSON with a request ID per line. Log rotation is configured in the
Compose file (`max-size: 10m`, `max-file: 5`) so logs cannot fill the disk.

### Updating

```bash
export AEGIS_BACKEND_IMAGE=ghcr.io/<org>/aegis-backend:v0.1.1
export AEGIS_FRONTEND_IMAGE=ghcr.io/<org>/aegis-frontend:v0.1.1
docker compose -f docker-compose.production.yml run --rm migrate
docker compose -f docker-compose.production.yml up -d
```

### Rollback

```bash
export AEGIS_BACKEND_IMAGE=ghcr.io/<org>/aegis-backend:v0.1.0
export AEGIS_FRONTEND_IMAGE=ghcr.io/<org>/aegis-frontend:v0.1.0
docker compose -f docker-compose.production.yml up -d
```

Application rollback is safe while the schema is backwards-compatible. Do not
roll back the schema without a tested restore — see `docs/backup-restore.md`.

### Backups

The database holds encrypted target credentials, findings, evidence, and audit
logs. Back it up and **test the restore**:

```bash
docker compose -f docker-compose.production.yml exec -T db \
  pg_dump -U aegis -Fc aegis > backup-$(date +%F).dump
```

See `docs/backup-restore.md` for the full procedure and restore drill.

### Evidence retention

Evidence is purged only when the retention CLI runs; nothing schedules it for
you. Add a daily host cron entry so old evidence does not accumulate:

```cron
# /etc/cron.d/aegis-retention
15 3 * * * root cd /opt/aegis && docker compose -f docker-compose.production.yml \
  exec -T backend python -m app.cli.retention --json >> /var/log/aegis-retention.log 2>&1
```

Retention windows are per project (`projects.evidence_retention_days`, default
90 days; `0` keeps indefinitely). Run `--dry-run` first. See
`docs/data-retention.md` for what the window covers and what it does not.

## Troubleshooting

App-level failures (install, accounts, targets, executions, reports, CLI) are
collected in [`troubleshooting.md`](troubleshooting.md). Host-level symptoms —
container restart loops, unreachable Postgres, missing volumes — are covered
there too, under install and startup.
