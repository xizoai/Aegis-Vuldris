# Aegis Vuldris Development Standards

## Local setup

### Prerequisites

- Python 3.11 or 3.12
- PostgreSQL 16 (the app requires Postgres; it uses JSONB and native enums)
- Node.js 20+ and npm (for the frontend)
- Docker with Compose v2 (for the containerised stack)

#### Verified working versions

Last full green run from a clean environment — database recreated from
scratch, `node_modules` deleted and reinstalled with `npm ci`:

| Tool | Version used | Declared support |
|---|---|---|
| Python | 3.11.7 | 3.11–3.12 |
| Node.js | v26.10.0 | 20+ |
| npm | 11.19.1 | bundled with Node |
| PostgreSQL | 16.15 | 16+ |
| Docker Engine | 29.6.1 | current, with Compose v2 |

Result: 305 backend tests, 52 frontend tests, 0 npm vulnerabilities, and
`alembic check` reporting no model/migration drift.

### Database

The backend needs `DATABASE_URL` and `SECRET_KEY` in a `.env` file at the
repository root. See `.env.example`.

Point `DATABASE_URL` at your Postgres instance, then apply migrations:

```powershell
alembic upgrade head
```

`alembic check` should report "No new upgrade operations detected". If it does
not, the models and migrations have drifted and the CI gate will fail.

### Backend

```powershell
# From the repository root
uvicorn app.main:app --reload --app-dir backend --port 8000
```

Note the `--app-dir backend` flag. The app reads `.env` from the current
working directory, so running from the repository root ensures the settings
are picked up.

Interactive API docs are at `http://127.0.0.1:8000/docs`.

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The dev server proxies `/api` to `http://127.0.0.1:8000`, so the browser only
ever talks to one origin and the backend needs no CORS configuration. Start the
backend first. To reach the dev server from another device, pass `--host`.

### Running with Docker Compose (recommended)

The Compose stack runs the same code in containers and is closer to how it is
deployed.

```powershell
# Generate a local development key
python -c "import secrets; print(secrets.token_hex(32))"

# Set it, then start everything
$env:SECRET_KEY = "<paste the generated key>"
docker compose up --build -d
docker compose ps          # db/backend/frontend healthy; migrate shows exited (0)
```

Services:

| Service   | URL                     | Notes                                       |
| --------- | ----------------------- | ------------------------------------------- |
| Frontend  | http://127.0.0.1:8080   | nginx serving the SPA, proxies `/api`        |
| Backend   | http://127.0.0.1:8000   | Interactive API docs at `/docs`             |
| Database  | `127.0.0.1:5432`        | Loopback only; never exposed publicly       |

Migrations run automatically: a one-shot `migrate` service applies
`alembic upgrade head` during `up`, and the backend only starts after it exits
0. If the stack does not come up, `docker compose logs migrate` shows why.

Useful checks:

```powershell
# Health
Invoke-WebRequest http://127.0.0.1:8080/api/v1/system/ready

# Frontend serves the SPA shell
Invoke-WebRequest http://127.0.0.1:8080
```

Tear down, including volumes:

```powershell
docker compose down -v
```

For a production-shaped stack with no published ports, read-only root
filesystems, and dropped capabilities, see `docs/deployment.md` and
`docker-compose.production.yml`.

### Tests

```powershell
pytest                      # backend
cd frontend; npm test       # frontend
```

### Loading the attack library

The 224 bundled YAML test cases in `backend/app/test_cases/` are static files.
Nothing imports them automatically, so a **new project has no tests and the
execution engine cannot be used** until you seed it.

```powershell
# List what would be created, without writing
docker compose exec backend python -m app.cli.seed_tests `
  --project <project-uuid> --email you@example.com --dry-run

# Seed the full library
docker compose exec backend python -m app.cli.seed_tests `
  --project <project-uuid> --email you@example.com

# Seed one category, capped (handy for a quick demo)
docker compose exec backend python -m app.cli.seed_tests `
  --project <project-uuid> --email you@example.com `
  --category prompt_injection --limit 5
```

| Flag | Purpose |
|---|---|
| `--project` | Project UUID (required) |
| `--email` | Owner account the tests are attributed to (required) |
| `--category` | Limit to one category; repeatable |
| `--limit N` | Consider at most N cases. Re-running with the same limit is a no-op |
| `--dir PATH` | Seed from a custom directory instead of the bundled library |
| `--dry-run` | Report what would change without writing |
| `--prune` | Delete every test in the project |

Seeding is **idempotent by name** — re-running skips tests that already exist,
so it is safe to run after adding new YAML files. Find the project UUID in the
URL when you open the project in the UI.

## Python

Aegis Vuldris uses Python 3.11 as its primary Python version.

Supported Python versions are:

- Python 3.11
- Python 3.12

Python dependencies are managed through `pyproject.toml` and `uv.lock`.

## Frontend

The frontend is a React + TypeScript application in `frontend/`, built with
Vite. See `docs/adr/ADR-002-frontend-framework.md` for the stack decision and
`docs/security-boundaries.md` for what the client must never be trusted to do.

Frontend quality gates:

```powershell
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## Code Quality

All Python code should pass:

- Ruff linting
- Ruff formatting
- Pyright type checking

Run:

```powershell
ruff check .
ruff format --check .
pyright
