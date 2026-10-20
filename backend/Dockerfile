# syntax=docker/dockerfile:1
#
# Aegis Vuldris backend API image.
#
# Design notes (see docs/adr/ADR-015-production-deployment-operational-architecture.md):
#   - Multi-stage build so build-time tooling (pip, compilers) never ships in the
#     runtime image, keeping the attack surface and image size down.
#   - Runs as a non-root user. Nothing in the application requires root.
#   - No secrets are baked into the image. All configuration is injected at
#     runtime via environment variables (see docs/secrets-management.md).
#   - The image does not run migrations on start. Migrations are an operational
#     step, run deliberately before the new version receives traffic (the
#     compose file does this with a one-shot `migrate` service that the backend
#     waits for; staging follows docs/deployment.md).

# ---------------------------------------------------------------- build stage
FROM python:3.14-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# No compiler toolchain is installed. Every dependency ships manylinux wheels for
# CPython 3.12 (psycopg[binary], cryptography, argon2-cffi, pydantic-core), so
# pip resolves from wheels and no build-essential layer is needed. If a future
# dependency requires a source build, add a compiler here rather than
# installing it in the runtime stage.
WORKDIR /build

# Copy only dependency metadata first so the dependency layer is cached and
# does not invalidate on every source change.
COPY pyproject.toml README.md ./
COPY backend/ ./backend/

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --only-binary=:all: .

# -------------------------------------------------------------- runtime stage
FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Report artifacts are written outside /tmp so they can be mounted on a
    # persistent volume. Losing them would mean losing generated reports.
    AEGIS_REPORT_DIR=/var/lib/aegis/reports

# curl is used by the container healthcheck below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged runtime user with a fixed uid/gid so host volume permissions are
# predictable across hosts.
RUN groupadd --system --gid 10001 aegis \
    && useradd --system --uid 10001 --gid aegis --create-home aegis

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Application source and migrations. No .env file is ever copied: configuration
# comes from the environment.
COPY --chown=aegis:aegis backend/ /app/backend/
COPY --chown=aegis:aegis alembic/ /app/alembic/
COPY --chown=aegis:aegis alembic.ini pyproject.toml README.md /app/

# Mount point for report artifacts; declared so the directory exists and is
# owned by the runtime user even when backed by an empty volume.
RUN mkdir -p /var/lib/aegis/reports \
    && chown -R aegis:aegis /var/lib/aegis

USER aegis

EXPOSE 8000

# Liveness only. Orchestrators should additionally gate traffic on
# /api/v1/system/ready, which reports real database connectivity.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8000/health || exit 1

# exec form: uvicorn handles signals directly, so SIGTERM reaches the server
# and in-flight requests drain instead of being killed.
CMD ["uvicorn", "app.main:app", \
     "--app-dir", "/app/backend", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*", \
     "--no-server-header"]
