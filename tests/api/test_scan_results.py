"""End-to-end external scan results: claim, complete with verdicts, read findings.

This is the phase 2 exit criterion at the API boundary -- a tool's normalized
verdicts travel with the terminal report and become findings the project can
read -- with the tool itself stubbed to its recorded output.
"""

from collections.abc import Iterator
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from app.db.session import create_session_factory
from app.main import app
from app.models.external_scan import ExternalScan, ExternalScanStatus
from app.models.finding import Finding, FindingSeverity
from app.models.project import Project
from app.models.user import User
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)

PASSWORD = "a-very-strong-password-123"
RUNNER_TOKEN = "test-runner-token"

# Drained by the autouse fixture. Deleting the project cascades to its targets,
# scans, and findings, so a failing test cannot leave a queued scan behind that
# steals a later test's claim.
_CREATED_PROJECTS: list[str] = []
_CREATED_EMAILS: list[str] = []


@pytest.fixture(autouse=True)
def _scan_isolation() -> Iterator[None]:
    """Refuse to start with foreign queue work; always drain our own."""

    session = create_session_factory()()
    try:
        leftover = session.scalar(
            select(ExternalScan).where(
                ExternalScan.status.in_([ExternalScanStatus.QUEUED, ExternalScanStatus.RUNNING])
            )
        )
        if leftover is not None:
            pytest.skip("queue already contains work from another test")
    finally:
        session.close()

    yield

    session = create_session_factory()()
    try:
        for project_id in _CREATED_PROJECTS:
            project = session.get(Project, UUID(project_id))
            if project is not None:
                session.delete(project)
        for email in _CREATED_EMAILS:
            user = session.scalar(select(User).where(User.email == email.lower()))
            if user is not None:
                session.delete(user)
        session.commit()
    finally:
        session.close()
        _CREATED_PROJECTS.clear()
        _CREATED_EMAILS.clear()


@pytest.fixture
def runner_settings(monkeypatch):
    settings = SimpleNamespace(
        runner_service_token=RUNNER_TOKEN,
        runner_claim_lease_seconds=60,
    )
    monkeypatch.setattr("app.security.dependencies.get_settings", lambda: settings)
    monkeypatch.setattr("app.api.routes.internal_scans.get_settings", lambda: settings)
    return settings


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login(email: str) -> str:
    _CREATED_EMAILS.append(email)
    registered = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": PASSWORD},
    )
    assert registered.status_code == 201, registered.text
    login = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _queue_scan(token: str) -> str:
    project = client.post(
        "/api/v1/projects",
        headers=_headers(token),
        json={"name": f"Results Project {uuid4()}"},
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    _CREATED_PROJECTS.append(project_id)

    target = client.post(
        "/api/v1/targets",
        headers=_headers(token),
        json={
            "project_id": project_id,
            "name": f"Results Target {uuid4()}",
            "provider": "openai_compatible",
            "endpoint": "https://model.example.com/v1",
            "model": "results-model",
            "capabilities": ["chat"],
            "authorization_attestation": True,
        },
    )
    assert target.status_code == 201, target.text

    scan = client.post(
        f"/api/v1/projects/{project_id}/scans",
        headers=_headers(token),
        json={"target_id": target.json()["id"], "tool": "garak", "config": {}},
    )
    assert scan.status_code == 202, scan.text
    return scan.json()["id"]


def _claim() -> str:
    claim = client.post("/api/v1/internal/scans/claim", headers=_headers(RUNNER_TOKEN))
    assert claim.status_code == 200, claim.text
    scan = claim.json()["scan"]
    assert scan is not None, "claim race: another test's scan won"
    assert scan["status"] == "running"
    assert claim.json()["llm_token"]
    return scan["id"]


_RESULTS = [
    {
        "probe": "dan.Dan_11_0",
        "detector": "dan.DAN",
        "verdict": "fail",
        "trigger_count": 2,
        "record_index": 1,
    },
    {
        "probe": "promptinject.HijackHateHumans",
        "detector": "promptinject.AttackRogueString",
        "verdict": "pass",
        "trigger_count": 0,
        "record_index": 2,
    },
    {
        "probe": "encoding.InjectBase64",
        "detector": "encoding.DecodeMatch",
        "verdict": "inconclusive",
        "trigger_count": 0,
        "record_index": 3,
    },
]


def test_completed_scan_ingests_findings_and_serves_them(runner_settings) -> None:
    email = f"results-ok-{uuid4()}@example.com"
    token = _register_and_login(email)
    scan_id = _queue_scan(token)
    assert _claim() == scan_id

    completed = client.post(
        f"/api/v1/internal/scans/{scan_id}/complete",
        headers=_headers(RUNNER_TOKEN),
        json={
            "status": "completed",
            "tool_version": "0.17.1",
            "external_run_id": f"garak-{scan_id}",
            "report_path": "/reports/scan.report.jsonl",
            "results": _RESULTS,
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"

    findings = client.get(f"/api/v1/scans/{scan_id}/findings", headers=_headers(token))
    assert findings.status_code == 200, findings.text
    body = findings.json()

    # Only the failure became a finding; the pass and the inconclusive did not.
    assert len(body) == 1
    finding = body[0]
    assert finding["execution_id"] is None
    assert finding["external_scan_id"] == scan_id
    assert "Dan_11_0" in finding["title"]
    assert finding["severity"] == FindingSeverity.HIGH.value
    assert finding["details"]["source"] == "external_scan"
    assert finding["details"]["tool"] == "garak"
    assert finding["details"]["tool_version"] == "0.17.1"
    assert finding["details"]["probe"] == "dan.Dan_11_0"
    assert finding["details"]["category"] == "jailbreak"
    assert finding["details"]["owasp"] == "LLM01:2026 – Prompt Injection"
    assert finding["details"]["trigger_count"] == 2
    assert finding["details"]["report_path"] == "/reports/scan.report.jsonl"
    # No prompt or model output travels through the API.
    assert "prompt" not in finding["details"]
    assert "outputs" not in finding["details"]

    session = create_session_factory()()
    try:
        stored = session.scalar(select(Finding).where(Finding.external_scan_id == UUID(scan_id)))
        assert stored is not None
        assert stored.execution_id is None
        scan_row = session.get(ExternalScan, UUID(scan_id))
        assert scan_row is not None
        assert scan_row.report_path == "/reports/scan.report.jsonl"
    finally:
        session.close()


def test_scan_findings_are_not_visible_to_a_stranger(runner_settings) -> None:
    owner_email = f"results-owner-{uuid4()}@example.com"
    stranger_email = f"results-stranger-{uuid4()}@example.com"
    token = _register_and_login(owner_email)
    scan_id = _queue_scan(token)
    _claim()
    stranger_token = _register_and_login(stranger_email)

    response = client.get(
        f"/api/v1/scans/{scan_id}/findings",
        headers=_headers(stranger_token),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


def test_scan_findings_require_authentication() -> None:
    response = client.get(f"/api/v1/scans/{uuid4()}/findings")
    assert response.status_code == 401


def test_a_failed_scan_still_ingests_what_it_produced(runner_settings) -> None:
    """A tool that dies mid-run keeps the verdicts it already reported."""

    email = f"results-partial-{uuid4()}@example.com"
    token = _register_and_login(email)
    scan_id = _queue_scan(token)
    _claim()

    completed = client.post(
        f"/api/v1/internal/scans/{scan_id}/complete",
        headers=_headers(RUNNER_TOKEN),
        json={
            "status": "failed",
            "error": "garak exited with 3: probe family exploded",
            "results": [
                {
                    "probe": "xss.MarkdownImage",
                    "detector": "xss.MarkdownExfil",
                    "verdict": "fail",
                    "trigger_count": 1,
                }
            ],
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "failed"
    assert completed.json()["error"].startswith("garak exited with 3")

    findings = client.get(f"/api/v1/scans/{scan_id}/findings", headers=_headers(token))
    assert findings.status_code == 200
    assert [item["details"]["probe"] for item in findings.json()] == ["xss.MarkdownImage"]


def test_an_invalid_result_record_is_refused_without_touching_the_scan(
    runner_settings,
) -> None:
    email = f"results-invalid-{uuid4()}@example.com"
    token = _register_and_login(email)
    scan_id = _queue_scan(token)
    _claim()

    rejected = client.post(
        f"/api/v1/internal/scans/{scan_id}/complete",
        headers=_headers(RUNNER_TOKEN),
        json={
            "status": "completed",
            "results": [{"probe": "dan.Dan_11_0", "verdict": "maybe"}],
        },
    )
    assert rejected.status_code == 422

    session = create_session_factory()()
    try:
        scan_row = session.get(ExternalScan, UUID(scan_id))
        assert scan_row is not None
        # Validation happens before any state change, so the runner can retry a
        # corrected report.
        assert scan_row.status is ExternalScanStatus.RUNNING
    finally:
        session.close()

    findings = client.get(f"/api/v1/scans/{scan_id}/findings", headers=_headers(token))
    assert findings.status_code == 200
    assert findings.json() == []


def test_a_result_record_may_not_smuggle_extra_fields(runner_settings) -> None:
    email = f"results-extra-{uuid4()}@example.com"
    token = _register_and_login(email)
    scan_id = _queue_scan(token)
    _claim()

    rejected = client.post(
        f"/api/v1/internal/scans/{scan_id}/complete",
        headers=_headers(RUNNER_TOKEN),
        json={
            "status": "completed",
            "results": [
                {
                    "probe": "dan.Dan_11_0",
                    "verdict": "fail",
                    "outputs": ["raw model output"],
                }
            ],
        },
    )

    assert rejected.status_code == 422
