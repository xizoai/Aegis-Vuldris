"""Remediation plan route: authorization and audit.

A plan is a read of an assessment artifact, so it must be authorized like
any other finding read and every view must be audit-recorded. The endpoint
is deliberately read-only: there is no route that applies, approves, or
marks a fix, so generating a suggestion can never change a finding's state.
"""

from uuid import UUID, uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.audit_log import AuditLog
from app.models.project import Project
from app.models.user import User, UserRole
from app.schemas import (
    ExecutionCreate,
    FindingCreate,
    ProjectCreate,
    ProjectMembershipCreate,
    SecurityTestCreate,
)
from app.services.assessments import create_execution, create_finding, create_security_test
from app.services.memberships import create_project_membership
from app.services.projects import create_project
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)
PASSWORD = "a-very-strong-password"

DEFAULT_CONFIG = {
    "category": "jailbreak",
    "attack": {"id": "builtin/jailbreak/01-classic-dan-jailbreak", "version": "1.0.0"},
}


def _register(email: str) -> tuple[str, dict[str, str]]:
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return email, {"Authorization": f"Bearer {token}"}


def _seed_finding(
    config: dict | None = None,
) -> tuple[str, str, str, str]:
    """Create an owner, project, test, execution, and finding. Return ids.

    Returns ``(project_id, finding_id, owner_email, owner_id)``.
    """

    email, auth = _register(f"remediation-owner-{uuid4()}@example.com")
    session = create_session_factory()()
    try:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        project_id = client.post(
            "/api/v1/projects", headers=auth, json={"name": f"Remediation {uuid4()}"}
        ).json()["id"]

        test = create_security_test(
            session,
            UUID(project_id),
            SecurityTestCreate(
                name=f"Case {uuid4()}",
                provider="openai_compatible",
                config=config if config is not None else dict(DEFAULT_CONFIG),
            ),
            user,
        )
        execution = create_execution(
            session, UUID(project_id), ExecutionCreate(test_id=test.id), user
        )
        finding = create_finding(
            session,
            FindingCreate(execution_id=execution.id, title="Jailbreak bypass"),
            user,
        )
        return project_id, str(finding.id), email, str(user.id)
    finally:
        session.close()


def _cleanup(project_id: str, *emails: str) -> None:
    session = create_session_factory()()
    try:
        project = session.get(Project, UUID(project_id))
        if project is not None:
            session.delete(project)
        for email in emails:
            user = session.scalar(select(User).where(User.email == email))
            if user is not None:
                session.delete(user)
        session.commit()
    finally:
        session.close()


def _path(project_id: str, finding_id: str) -> str:
    return f"/api/v1/projects/{project_id}/assessments/findings/{finding_id}/remediation"


def test_owner_receives_the_review_only_plan() -> None:
    project_id, finding_id, owner_email, _owner_id = _seed_finding()
    _, owner_auth = _register(owner_email)
    try:
        response = client.get(_path(project_id, finding_id), headers=owner_auth)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["finding_id"] == finding_id
        assert body["category"] == "jailbreak"
        assert body["kind"] == "llm_behavior"
        assert body["root_cause_hypothesis"]
        assert body["recommendations"]
        assert body["verification_steps"]
        assert body["limitations"]
        assert body["attack_id"] == "builtin/jailbreak/01-classic-dan-jailbreak"
        assert body["attack_version"] == "1.0.0"
        # The honest-state contract: a suggestion is never a patch or a fix.
        assert body["status"] == "suggested"
        assert body["autonomy"] == "suggest"
        assert body["patch_available"] is False
        assert body["requires_human_approval"] is True
    finally:
        _cleanup(project_id, owner_email)


def test_viewing_a_plan_is_audited() -> None:
    project_id, finding_id, owner_email, owner_id = _seed_finding()
    _, owner_auth = _register(owner_email)
    try:
        assert client.get(_path(project_id, finding_id), headers=owner_auth).status_code == 200

        session = create_session_factory()()
        try:
            audit = session.scalar(
                select(AuditLog).where(
                    AuditLog.action == "remediation.viewed",
                    AuditLog.resource_id == finding_id,
                )
            )
            assert audit is not None, "remediation view was not audited"
            assert str(audit.actor_id) == owner_id
            assert audit.event_metadata is not None
            assert audit.event_metadata["project_id"] == project_id
            assert audit.event_metadata["kind"] == "llm_behavior"
        finally:
            session.close()
    finally:
        _cleanup(project_id, owner_email)


def test_viewer_member_can_read_the_plan() -> None:
    """Reading a suggestion is a read; a VIEWER must not be locked out."""

    project_id, finding_id, owner_email, owner_id = _seed_finding()
    viewer_email, viewer_auth = _register(f"remediation-viewer-{uuid4()}@example.com")

    session = create_session_factory()()
    try:
        owner = session.get(User, UUID(owner_id))
        viewer = session.scalar(select(User).where(User.email == viewer_email))
        assert owner is not None
        assert viewer is not None
        create_project_membership(
            session,
            UUID(project_id),
            ProjectMembershipCreate(user_id=viewer.id, role=UserRole.VIEWER),
            owner,
        )

        response = client.get(_path(project_id, finding_id), headers=viewer_auth)
        assert response.status_code == 200, response.text
    finally:
        session.close()
        _cleanup(project_id, owner_email, viewer_email)


def test_stranger_is_denied() -> None:
    project_id, finding_id, owner_email, _owner_id = _seed_finding()
    _, stranger_auth = _register(f"remediation-stranger-{uuid4()}@example.com")
    try:
        response = client.get(_path(project_id, finding_id), headers=stranger_auth)
        assert response.status_code in {403, 404}, response.status_code
    finally:
        _cleanup(project_id, owner_email)


def test_finding_paired_with_the_wrong_project_is_rejected() -> None:
    """The same owner of two projects must not mix a finding across them.

    The finding is authorized, but the path names the wrong project, so the
    answer is not-found rather than the plan.
    """

    project_a, finding_a, owner_email, owner_id = _seed_finding()
    session = create_session_factory()()
    try:
        owner = session.get(User, UUID(owner_id))
        assert owner is not None
        project_b = create_project(
            session, ProjectCreate(name=f"Other {uuid4()}"), owner_id=owner.id
        )
        project_b_id = str(project_b.id)
    finally:
        session.close()

    _, owner_auth = _register(owner_email)
    try:
        response = client.get(_path(project_b_id, finding_a), headers=owner_auth)
        assert response.status_code == 404, response.status_code
    finally:
        _cleanup(project_a, owner_email)
        _cleanup(project_b_id)


def test_missing_finding_is_rejected() -> None:
    project_id, _finding_id, owner_email, _owner_id = _seed_finding()
    _, owner_auth = _register(owner_email)
    try:
        response = client.get(_path(project_id, str(uuid4())), headers=owner_auth)
        assert response.status_code == 404
    finally:
        _cleanup(project_id, owner_email)


def test_unauthenticated_requests_are_rejected() -> None:
    project_id, finding_id, owner_email, _owner_id = _seed_finding()
    try:
        response = client.get(_path(project_id, finding_id))
        assert response.status_code == 401
    finally:
        _cleanup(project_id, owner_email)
