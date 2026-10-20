"""External scan API and runner-token tests for AegisAI."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app.db.session import create_session_factory
from app.main import app
from app.models.external_scan import ExternalScan, ExternalScanStatus
from app.models.project import Project
from app.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)

PASSWORD = "a-very-strong-password-123"
RUNNER_TOKEN = "test-runner-token"


@pytest.fixture
def runner_settings(monkeypatch) -> SimpleNamespace:
    """Configure a runner token for the internal endpoints."""

    settings = SimpleNamespace(
        runner_service_token=RUNNER_TOKEN,
        runner_claim_lease_seconds=60,
    )
    monkeypatch.setattr("app.security.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.internal_scans.get_settings", lambda: settings)
    return settings


def _register(email: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 201


def _login(email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_project(token: str) -> UUID:
    response = client.post(
        "/api/v1/projects",
        headers=_headers(token),
        json={"name": f"Scan API Project {uuid4()}"},
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


def _create_target(token: str, project_id: UUID) -> UUID:
    response = client.post(
        "/api/v1/targets",
        headers=_headers(token),
        json={
            "project_id": str(project_id),
            "name": f"Scan API Target {uuid4()}",
            "provider": "openai_compatible",
            "endpoint": "https://model.example.com/v1",
            "model": "test-model",
            "capabilities": ["chat"],
            "authorization_attestation": True,
        },
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


def _create_scan(token: str, project_id: UUID, target_id: UUID) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/scans",
        headers=_headers(token),
        json={
            "target_id": str(target_id),
            "tool": "garak",
            "config": {"probes": ["prompt_injection"]},
        },
    )
    assert response.status_code == 202
    return response.json()


def _require_clean_queue() -> None:
    """Skip claim-dependent tests if another test left work behind."""

    session = create_session_factory()()
    try:
        pending = session.scalar(
            select(ExternalScan).where(
                ExternalScan.status.in_([ExternalScanStatus.QUEUED, ExternalScanStatus.RUNNING])
            )
        )
        if pending is not None:
            pytest.skip("queue already contains work from another test")
    finally:
        session.close()


def _cleanup(*emails: str, project_id: UUID | None = None) -> None:
    session = create_session_factory()()
    try:
        if project_id is not None:
            project = session.get(Project, project_id)
            if project is not None:
                session.delete(project)

        for email in emails:
            user = session.scalar(select(User).where(User.email == email.lower()))
            if user is not None:
                session.delete(user)

        session.commit()
    finally:
        session.close()


def _setup_scan(email: str) -> tuple[UUID, UUID, dict]:
    _register(email)
    token = _login(email)
    project_id = _create_project(token)
    target_id = _create_target(token, project_id)
    scan = _create_scan(token, project_id, target_id)
    return project_id, UUID(scan["id"]), scan


def test_create_scan_queues_it_and_lists_it() -> None:
    email = f"scan-api-{uuid4()}@example.com"
    project_id = None

    try:
        project_id, scan_id, scan = _setup_scan(email)
        token = _login(email)

        assert scan["status"] == "queued"
        assert scan["tool"] == "garak"
        assert scan["attempt_count"] == 0

        fetched = client.get(f"/api/v1/scans/{scan_id}", headers=_headers(token))
        assert fetched.status_code == 200
        assert fetched.json()["id"] == str(scan_id)

        listed = client.get(
            f"/api/v1/projects/{project_id}/scans",
            headers=_headers(token),
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [str(scan_id)]
    finally:
        _cleanup(email, project_id=project_id)


def test_scan_endpoints_require_authentication() -> None:
    response = client.get(f"/api/v1/scans/{uuid4()}")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    response = client.post(
        f"/api/v1/projects/{uuid4()}/scans",
        json={"target_id": str(uuid4()), "tool": "garak"},
    )
    assert response.status_code == 401


def test_scan_is_not_visible_to_another_user() -> None:
    owner_email = f"scan-owner-{uuid4()}@example.com"
    stranger_email = f"scan-stranger-{uuid4()}@example.com"
    project_id = None

    try:
        project_id, scan_id, _scan = _setup_scan(owner_email)
        _register(stranger_email)
        stranger_token = _login(stranger_email)

        response = client.get(
            f"/api/v1/scans/{scan_id}",
            headers=_headers(stranger_token),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    finally:
        _cleanup(owner_email, stranger_email, project_id=project_id)


def test_cancel_scan_via_api_and_reject_a_second_cancel() -> None:
    email = f"scan-cancel-{uuid4()}@example.com"
    project_id = None

    try:
        project_id, scan_id, _scan = _setup_scan(email)
        token = _login(email)

        cancelled = client.post(
            f"/api/v1/scans/{scan_id}/cancel",
            headers=_headers(token),
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"

        again = client.post(
            f"/api/v1/scans/{scan_id}/cancel",
            headers=_headers(token),
        )
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "SCAN_STATE_CONFLICT"
    finally:
        _cleanup(email, project_id=project_id)


def test_internal_endpoints_require_the_service_token(runner_settings) -> None:
    missing = client.post("/api/v1/internal/scans/claim")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "SERVICE_AUTHENTICATION_REQUIRED"

    wrong = client.post(
        "/api/v1/internal/scans/claim",
        headers=_headers("not-the-runner-token"),
    )
    assert wrong.status_code == 401


def test_internal_endpoints_are_disabled_when_no_token_is_configured(monkeypatch) -> None:
    settings = SimpleNamespace(
        runner_service_token="",
        runner_claim_lease_seconds=60,
    )
    monkeypatch.setattr("app.security.dependencies.get_settings", lambda: settings)

    response = client.post(
        "/api/v1/internal/scans/claim",
        headers=_headers("anything"),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SERVICE_AUTHENTICATION_REQUIRED"


def test_runner_claims_and_completes_a_scan_exactly_once(runner_settings) -> None:
    email = f"scan-runner-{uuid4()}@example.com"
    project_id = None

    try:
        _require_clean_queue()
        project_id, scan_id, _scan = _setup_scan(email)
        runner_headers = _headers(RUNNER_TOKEN)

        claim = client.post("/api/v1/internal/scans/claim", headers=runner_headers)
        assert claim.status_code == 200
        claimed = claim.json()["scan"]
        assert claimed is not None
        assert claimed["id"] == str(scan_id)
        assert claimed["status"] == "running"
        assert claimed["attempt_count"] == 1

        completed = client.post(
            f"/api/v1/internal/scans/{scan_id}/complete",
            headers=runner_headers,
            json={
                "status": "completed",
                "tool_version": "0.17.1",
                "external_run_id": "noop-run",
            },
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        assert completed.json()["tool_version"] == "0.17.1"

        duplicate = client.post(
            f"/api/v1/internal/scans/{scan_id}/complete",
            headers=runner_headers,
            json={"status": "failed", "error": "second report"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "SCAN_STATE_CONFLICT"

        session = create_session_factory()()
        try:
            stored = session.get(ExternalScan, scan_id)
            assert stored is not None
            assert stored.status == ExternalScanStatus.COMPLETED
            assert stored.external_run_id == "noop-run"
        finally:
            session.close()
    finally:
        _cleanup(email, project_id=project_id)
