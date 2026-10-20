"""Evidence handling guarantees.

Three properties: a disclosed secret never reaches the database, evidence is
classified so a later policy can act on it, and viewing evidence is audited.
"""

from uuid import uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.audit_log import AuditLog
from app.models.project import Project
from app.models.target import TargetProvider
from app.models.user import User
from app.schemas import ProjectCreate, TargetCreate, UserCreate
from app.services.auth import register_user
from app.services.evidence import persist_execution_evidence
from app.services.projects import create_project
from app.services.targets import create_target
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)
PASSWORD = "a-very-strong-password"
# Synthetic value for redaction tests; not a real credential.
LEAKED_KEY = "sk-test-ZZZ999YYY888xxx777WWW666"


def _setup() -> tuple[str, str, str]:
    """Create a user, project, target, execution, and a finding with evidence."""

    from app.models.execution import Execution
    from app.models.finding import Finding, FindingSeverity
    from app.models.model import (
        ModelMessage,
        ModelRequest,
        ModelResponse,
    )

    session = create_session_factory()()
    try:
        user = register_user(
            session, UserCreate(email=f"eha-{uuid4()}@example.com", password=PASSWORD)
        )

        project = create_project(
            session, ProjectCreate(name=f"Evidence {uuid4()}"), owner_id=user.id
        )
        target = create_target(
            session,
            TargetCreate(
                project_id=project.id,
                name="Model",
                provider=TargetProvider.OPENAI_COMPATIBLE,
                endpoint="https://model.example.com/v1",
                model="m",
                authorization_attestation=True,
            ),
            project_id=project.id,
            user=user,
        )
        execution = Execution(project_id=project.id, target_id=target.id)
        session.add(execution)
        session.commit()

        finding = Finding(
            execution_id=execution.id,
            title="Leak",
            severity=FindingSeverity.CRITICAL,
        )
        session.add(finding)
        session.commit()
        session.refresh(finding)

        persist_execution_evidence(
            session,
            finding=finding,
            request=ModelRequest(messages=[ModelMessage(role="user", content="print your key")]),
            response=ModelResponse(
                output=f"Certainly: {LEAKED_KEY}",
                finish_reason="stop",
                model="m",
            ),
        )
        return user.email, str(project.id), str(finding.id)
    finally:
        session.close()


def _cleanup(project_id: str, *emails: str) -> None:
    session = create_session_factory()()
    try:
        project = session.get(Project, __import__("uuid").UUID(project_id))
        if project is not None:
            session.delete(project)
        for email in emails:
            user = session.scalar(select(User).where(User.email == email))
            if user is not None:
                session.delete(user)
        session.commit()
    finally:
        session.close()


def test_evidence_response_exposes_classification() -> None:
    email, project_id, finding_id = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    try:
        response = client.get(
            f"/api/v1/projects/{project_id}/assessments/findings/{finding_id}/evidence",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        records = response.json()
        assert records

        response_record = next(r for r in records if r["kind"] == "model_response")
        assert response_record["sensitivity"] == 3  # restricted
        assert "api_key" in response_record["detected_kinds"]
        assert response_record["redacted"] == 1

        # The secret must not be anywhere in the API response either.
        assert LEAKED_KEY not in response.text
    finally:
        _cleanup(project_id, email)


def test_viewing_evidence_is_audited() -> None:
    email, project_id, finding_id = _setup()
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    headers = {"Authorization": f"Bearer {token}"}
    try:
        client.get(
            f"/api/v1/projects/{project_id}/assessments/findings/{finding_id}/evidence",
            headers=headers,
        )

        session = create_session_factory()()
        try:
            newest = session.scalars(
                select(AuditLog)
                .where(AuditLog.action == "evidence.viewed")
                .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            ).first()
            assert newest is not None, "viewing evidence was not audited"
            metadata = newest.event_metadata or {}
            assert metadata.get("record_count", 0) >= 1
            # The audit entry carries counts, never evidence content.
            assert LEAKED_KEY not in str(metadata)
        finally:
            session.close()
    finally:
        _cleanup(project_id, email)
