"""API tests for the DELETE /executions/history endpoint."""

from uuid import uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.execution import Execution, ExecutionResult, ExecutionStatus
from app.models.execution_step import ExecutionStep
from app.models.finding import Finding, FindingSeverity
from app.models.project import Project as ProjectModel
from app.models.report import Report as ReportModel
from app.models.test import SecurityTest as SecurityTestModel
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

client = TestClient(app)
PASSWORD = "a-very-strong-password"


def _auth(email: str) -> dict[str, str]:
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return {"Authorization": f"Bearer {token}"}


def _seed_execution_with_data(project_id: str) -> tuple[str, str, str]:
    session = create_session_factory()()
    try:
        test = SecurityTestModel(
            project_id=project_id,
            name=f"Test {uuid4()}",
            provider="openai_compatible",
            required_capabilities=["chat"],
            config={},
        )
        session.add(test)
        session.flush()

        report = ReportModel(
            project_id=project_id,
            title=f"Report {uuid4()}",
            format="json",
            path="/tmp/report.json",
        )
        session.add(report)
        session.flush()

        execution = Execution(
            project_id=project_id,
            test_id=test.id,
            status=ExecutionStatus.SUCCEEDED,
            result=ExecutionResult.FAIL,
        )
        session.add(execution)
        session.flush()

        step = ExecutionStep(
            execution_id=execution.id,
            turn_number=0,
            request_content={},
            status="completed",
        )
        session.add(step)

        finding = Finding(
            execution_id=execution.id,
            title="Injection finding",
            severity=FindingSeverity.HIGH,
        )
        session.add(finding)
        session.flush()

        session.commit()
        return str(execution.id), str(test.id), str(report.id)
    finally:
        session.close()


def _cleanup_project(project_id: str) -> None:
    session = create_session_factory()()
    try:
        session.execute(
            delete(Finding).where(
                Finding.execution_id.in_(
                    select(Execution.id).where(Execution.project_id == project_id)
                )
            )
        )
        session.execute(
            delete(ExecutionStep).where(
                ExecutionStep.execution_id.in_(
                    select(Execution.id).where(Execution.project_id == project_id)
                )
            )
        )
        session.execute(delete(Execution).where(Execution.project_id == project_id))
        session.execute(delete(ReportModel).where(ReportModel.project_id == project_id))
        session.execute(delete(SecurityTestModel).where(SecurityTestModel.project_id == project_id))
        session.execute(delete(ProjectModel).where(ProjectModel.id == project_id))
        session.commit()
    finally:
        session.close()


def test_delete_execution_history_endpoint() -> None:
    email = f"clear-history-{uuid4()}@example.com"
    auth = _auth(email)
    project_id = client.post(
        "/api/v1/projects", headers=auth, json={"name": "Clear History"}
    ).json()["id"]

    execution_id, test_id, report_id = _seed_execution_with_data(project_id)
    try:
        response = client.delete(
            f"/api/v1/projects/{project_id}/assessments/executions/history",
            headers=auth,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["deleted"] == 1

        session = create_session_factory()()
        try:
            assert session.get(Execution, execution_id) is None
            assert (
                session.scalar(select(Finding).where(Finding.execution_id == execution_id)) is None
            )
            assert (
                session.scalar(
                    select(ExecutionStep).where(ExecutionStep.execution_id == execution_id)
                )
                is None
            )
            assert session.get(ReportModel, report_id) is not None
            assert session.get(SecurityTestModel, test_id) is not None
        finally:
            session.close()
    finally:
        _cleanup_project(project_id)


def test_delete_execution_history_requires_write_access() -> None:
    owner_email = f"owner-{uuid4()}@example.com"
    owner_auth = _auth(owner_email)
    project_id = client.post("/api/v1/projects", headers=owner_auth, json={"name": "RBAC"}).json()[
        "id"
    ]

    stranger_email = f"stranger-{uuid4()}@example.com"
    stranger_auth = _auth(stranger_email)

    try:
        response = client.delete(
            f"/api/v1/projects/{project_id}/assessments/executions/history",
            headers=stranger_auth,
        )
        assert response.status_code == 403
    finally:
        _cleanup_project(project_id)


def test_delete_single_execution_endpoint() -> None:
    email = f"del-exec-{uuid4()}@example.com"
    auth = _auth(email)
    project_id = client.post(
        "/api/v1/projects", headers=auth, json={"name": "Single Delete"}
    ).json()["id"]

    execution_id, test_id, report_id = _seed_execution_with_data(project_id)
    try:
        response = client.delete(
            f"/api/v1/projects/{project_id}/assessments/executions/{execution_id}",
            headers=auth,
        )
        assert response.status_code == 204, response.text

        session = create_session_factory()()
        try:
            assert session.get(Execution, execution_id) is None
            assert (
                session.scalar(select(Finding).where(Finding.execution_id == execution_id)) is None
            )
            assert session.get(ReportModel, report_id) is not None
            assert session.get(SecurityTestModel, test_id) is not None
        finally:
            session.close()
    finally:
        _cleanup_project(project_id)


def test_delete_single_execution_requires_write_access() -> None:
    owner_email = f"owner-{uuid4()}@example.com"
    owner_auth = _auth(owner_email)
    project_id = client.post(
        "/api/v1/projects", headers=owner_auth, json={"name": "Single RBAC"}
    ).json()["id"]

    execution_id, _, _ = _seed_execution_with_data(project_id)

    stranger_email = f"stranger-{uuid4()}@example.com"
    stranger_auth = _auth(stranger_email)

    try:
        response = client.delete(
            f"/api/v1/projects/{project_id}/assessments/executions/{execution_id}",
            headers=stranger_auth,
        )
        assert response.status_code == 403
    finally:
        _cleanup_project(project_id)
