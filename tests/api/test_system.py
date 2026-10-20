"""System endpoint tests for Aegis Vuldris."""

import tomllib
from pathlib import Path

from app.core.version import APP_VERSION
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_root_endpoint_returns_service_metadata() -> None:
    """The root endpoint should report service identity and status."""

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Aegis Vuldris",
        "version": APP_VERSION,
        "status": "ok",
    }


def test_health_endpoint_reports_ok() -> None:
    """The liveness endpoint should report ok whenever the process is running."""

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_endpoint_reports_database_status() -> None:
    """The readiness endpoint should report the database connectivity status."""

    response = client.get("/api/v1/system/ready")

    assert response.status_code in (200, 503)

    body = response.json()

    assert body["database"] in ("ok", "error")
    assert body["status"] in ("ok", "degraded")

    if body["database"] == "ok":
        assert response.status_code == 200
        assert body["status"] == "ok"
    else:
        assert response.status_code == 503
        assert body["status"] == "degraded"


def test_system_info_endpoint_reports_application_metadata() -> None:
    """The system info endpoint should report application name/version/status."""

    response = client.get("/api/v1/system/info")

    assert response.status_code == 200

    body = response.json()

    assert body["name"] == "Aegis Vuldris"
    assert body["version"] == APP_VERSION
    assert body["status"] == "ok"


def test_reported_version_is_single_sourced_from_pyproject() -> None:
    """The running version must come from the installed package, not a copy.

    The release process promises that tagging produces a matching reported
    version with no code edit. That only holds if there is exactly one
    source of truth: pyproject.toml, read through the installed distribution
    metadata.
    """

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert APP_VERSION == config["project"]["version"], (
        "APP_VERSION comes from the installed package; if this fails, the "
        "environment is running a stale install — reinstall with `pip install .`"
    )
    assert app.version == APP_VERSION
