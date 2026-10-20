"""The API must expose why an execution failed.

Without `error` in the response, the UI can only report "failed", which looks
identical for a misconfigured target, an unreadable credential, and a provider
outage. Users cannot act on that.

A run can also complete with result `fail` -- the attack landed, so there is no
`error` at all; the reason then lives in the finding the grader produced.
"""

from uuid import uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.finding import Finding, FindingSeverity
from fastapi.testclient import TestClient

client = TestClient(app)
PASSWORD = "a-very-strong-password"


def _auth(email: str) -> dict[str, str]:
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _seed_failed_execution(project_id: str, error: str | None) -> str:
    session = create_session_factory()()
    try:
        execution = Execution(
            project_id=project_id,
            status=ExecutionStatus.FAILED,
            result=ExecutionResult.INCONCLUSIVE,
            error=error,
        )
        session.add(execution)
        session.commit()
        session.refresh(execution)
        return str(execution.id)
    finally:
        session.close()


def _seed_failed_result_with_finding(project_id: str) -> tuple[str, str]:
    """A run that succeeded because the attack landed: one finding, no error."""

    session = create_session_factory()()
    try:
        execution = Execution(
            project_id=project_id,
            status=ExecutionStatus.SUCCEEDED,
            result=ExecutionResult.FAIL,
        )
        session.add(execution)
        session.flush()
        finding = Finding(
            execution_id=execution.id,
            title="Document structure probing",
            description="Response matched 2 pattern(s): steal, charity",
            severity=FindingSeverity.HIGH,
            details={"matched_patterns": ["steal", "charity"]},
        )
        session.add(finding)
        session.commit()
        session.refresh(execution)
        session.refresh(finding)
        return str(execution.id), str(finding.id)
    finally:
        session.close()


def test_failed_execution_exposes_its_error() -> None:
    email = f"exec-error-{uuid4()}@example.com"
    auth = _auth(email)
    project_id = client.post(
        "/api/v1/projects", headers=auth, json={"name": "Error surfacing"}
    ).json()["id"]

    execution_id = _seed_failed_execution(project_id, "credential could not be decrypted")

    try:
        response = client.get(
            f"/api/v1/projects/{project_id}/assessments/executions/{execution_id}",
            headers=auth,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "failed"
        assert body["result"] == "inconclusive"
        assert body["error"] == "credential could not be decrypted"
    finally:
        session = create_session_factory()()
        try:
            row = session.get(Execution, execution_id)
            if row is not None:
                session.delete(row)
            session.commit()
        finally:
            session.close()


def test_successful_execution_exposes_run_manifest() -> None:
    email = f"exec-manifest-{uuid4()}@example.com"
    auth = _auth(email)
    project_id = client.post(
        "/api/v1/projects", headers=auth, json={"name": "Run manifest"}
    ).json()["id"]

    manifest = {
        "manifest_version": 1,
        "target": {"model": "candidate-v1", "model_version": "2026-08-01"},
        "test": {"name": "Prompt injection case"},
        "effective_generation": {"temperature": 0.2, "top_p": 0.9},
    }
    session = create_session_factory()()
    try:
        execution = Execution(
            project_id=project_id,
            status=ExecutionStatus.SUCCEEDED,
            result=ExecutionResult.PASS,
            run_manifest=manifest,
        )
        session.add(execution)
        session.commit()
        execution_id = str(execution.id)
    finally:
        session.close()

    try:
        response = client.get(
            f"/api/v1/projects/{project_id}/assessments/executions/{execution_id}",
            headers=auth,
        )
        assert response.status_code == 200, response.text
        assert response.json()["run_manifest"] == manifest
    finally:
        session = create_session_factory()()
        try:
            row = session.get(Execution, execution_id)
            if row is not None:
                session.delete(row)
            session.commit()
        finally:
            session.close()


def test_successful_execution_has_null_error() -> None:
    email = f"exec-noerror-{uuid4()}@example.com"
    auth = _auth(email)
    project_id = client.post("/api/v1/projects", headers=auth, json={"name": "No error"}).json()[
        "id"
    ]

    execution_id = _seed_failed_execution(project_id, None)

    try:
        response = client.get(
            f"/api/v1/projects/{project_id}/assessments/executions/{execution_id}",
            headers=auth,
        )
        assert response.status_code == 200
        assert response.json()["error"] is None
    finally:
        session = create_session_factory()()
        try:
            row = session.get(Execution, execution_id)
            if row is not None:
                session.delete(row)
            session.commit()
        finally:
            session.close()


def test_execution_list_includes_error() -> None:
    """The table view the UI renders must carry the reason too."""

    email = f"exec-list-{uuid4()}@example.com"
    auth = _auth(email)
    project_id = client.post("/api/v1/projects", headers=auth, json={"name": "List errors"}).json()[
        "id"
    ]

    execution_id = _seed_failed_execution(project_id, "model provider returned HTTP 404")

    try:
        response = client.get(f"/api/v1/projects/{project_id}/assessments/executions", headers=auth)
        assert response.status_code == 200
        match = [row for row in response.json() if row["id"] == execution_id]
        assert match, "seeded execution missing from list"
        assert match[0]["error"] == "model provider returned HTTP 404"
    finally:
        session = create_session_factory()()
        try:
            row = session.get(Execution, execution_id)
            if row is not None:
                session.delete(row)
            session.commit()
        finally:
            session.close()


def test_failed_result_exposes_the_finding_that_explains_it() -> None:
    """A landed attack has no `error`; the reason is the finding itself."""

    email = f"exec-finding-{uuid4()}@example.com"
    auth = _auth(email)
    project_id = client.post(
        "/api/v1/projects", headers=auth, json={"name": "Finding reasons"}
    ).json()["id"]

    execution_id, finding_id = _seed_failed_result_with_finding(project_id)

    try:
        response = client.get(f"/api/v1/projects/{project_id}/assessments/executions", headers=auth)
        assert response.status_code == 200, response.text
        match = [row for row in response.json() if row["id"] == execution_id]
        assert match, "seeded execution missing from list"
        summary = match[0]["finding_summary"]
        assert summary["id"] == finding_id
        assert summary["title"] == "Document structure probing"
        assert summary["description"] == "Response matched 2 pattern(s): steal, charity"
        assert summary["severity"] == "high"

        single = client.get(
            f"/api/v1/projects/{project_id}/assessments/executions/{execution_id}",
            headers=auth,
        )
        assert single.status_code == 200, single.text
        assert single.json()["finding_summary"]["id"] == finding_id
    finally:
        session = create_session_factory()()
        try:
            row = session.get(Execution, execution_id)
            if row is not None:
                session.delete(row)
            session.commit()
        finally:
            session.close()


def test_execution_without_findings_has_null_finding_summary() -> None:
    email = f"exec-nofinding-{uuid4()}@example.com"
    auth = _auth(email)
    project_id = client.post("/api/v1/projects", headers=auth, json={"name": "No finding"}).json()[
        "id"
    ]

    execution_id = _seed_failed_execution(project_id, None)

    try:
        response = client.get(f"/api/v1/projects/{project_id}/assessments/executions", headers=auth)
        assert response.status_code == 200
        match = [row for row in response.json() if row["id"] == execution_id]
        assert match, "seeded execution missing from list"
        assert match[0]["finding_summary"] is None
    finally:
        session = create_session_factory()()
        try:
            row = session.get(Execution, execution_id)
            if row is not None:
                session.delete(row)
            session.commit()
        finally:
            session.close()
