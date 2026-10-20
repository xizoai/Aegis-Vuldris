"""Fix verification route: authorization, states, and audit.

Queuing a verification run re-executes an attack, so it is a write scoped to
the project and only allowed once a human has marked the finding fixed. The
route never sets ``verified`` itself; that happens only when the run passes.
The engine is stubbed out here -- these tests cover the API contract, while
the rerun itself is covered by the service and engine tests.
"""

from uuid import UUID, uuid4

import pytest
from app.db.session import create_session_factory
from app.main import app
from app.models.audit_log import AuditLog
from app.models.project import Project
from app.models.target import Target, TargetProvider
from app.models.user import User, UserRole
from app.schemas import (
    ExecutionCreate,
    FindingCreate,
    ProjectCreate,
    ProjectMembershipCreate,
    SecurityTestCreate,
    TargetCreate,
)
from app.services.assessments import create_execution, create_finding, create_security_test
from app.services.memberships import create_project_membership
from app.services.projects import create_project
from app.services.targets import create_target
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)
PASSWORD = "a-very-strong-password"

ATTACK = {
    "id": "builtin/prompt-injection/01-direct-instruction-override",
    "version": "2.0.0",
}


@pytest.fixture(autouse=True)
def _stub_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep queued runs PENDING: starting the real engine would hit the network."""

    monkeypatch.setattr(
        "app.api.routes.assessments.start_execution",
        lambda execution_id: None,
    )


def _register(email: str) -> tuple[str, dict[str, str]]:
    client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()[
        "access_token"
    ]
    return email, {"Authorization": f"Bearer {token}"}


def _create_target(session, project_id: UUID, owner: User) -> Target:
    return create_target(
        session,
        TargetCreate(
            project_id=project_id,
            name=f"Target {uuid4()}",
            provider=TargetProvider.OPENAI_COMPATIBLE,
            endpoint="https://model.example.com/v1",
            model="test-model",
            capabilities=["chat"],
            timeout_seconds=30.0,
            authorization_attestation=True,
        ),
        project_id,
        owner,
    )


def _seed() -> tuple[str, str, str, str, str, str]:
    """Create an owner, project, target, test, execution, and finding.

    Returns ``(project_id, finding_id, target_id, test_id, owner_email,
    owner_id)``.
    """

    email, auth = _register(f"verification-owner-{uuid4()}@example.com")
    session = create_session_factory()()
    try:
        user = session.scalar(select(User).where(User.email == email))
        assert user is not None
        project_id = client.post(
            "/api/v1/projects", headers=auth, json={"name": f"Verification {uuid4()}"}
        ).json()["id"]

        target = _create_target(session, UUID(project_id), user)
        test = create_security_test(
            session,
            UUID(project_id),
            SecurityTestCreate(
                name=f"Case {uuid4()}",
                provider="openai_compatible",
                config={"category": "prompt_injection", "attack": dict(ATTACK)},
            ),
            user,
        )
        execution = create_execution(
            session,
            UUID(project_id),
            ExecutionCreate(test_id=test.id, target_id=target.id),
            user,
        )
        finding = create_finding(
            session,
            FindingCreate(execution_id=execution.id, title="Instruction override"),
            user,
        )
        return (
            project_id,
            str(finding.id),
            str(target.id),
            str(test.id),
            email,
            str(user.id),
        )
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
    return f"/api/v1/projects/{project_id}/assessments/findings/{finding_id}/verifications"


def _mark_fixed(project_id: str, finding_id: str, auth: dict[str, str]) -> None:
    response = client.patch(
        f"/api/v1/projects/{project_id}/assessments/findings/{finding_id}",
        headers=auth,
        json={"status": "fixed"},
    )
    assert response.status_code == 200, response.text


def test_owner_queues_a_run_and_it_is_listed_and_audited() -> None:
    project_id, finding_id, target_id, test_id, owner_email, owner_id = _seed()
    _, owner_auth = _register(owner_email)
    try:
        _mark_fixed(project_id, finding_id, owner_auth)

        response = client.post(_path(project_id, finding_id), headers=owner_auth)

        assert response.status_code == 202, response.text
        body = response.json()
        assert body["verifies_finding_id"] == finding_id
        assert body["test_id"] == test_id
        assert body["target_id"] == target_id
        assert body["status"] == "pending"
        assert body["result"] != "pass"  # PENDING has no verdict yet.

        listed = client.get(_path(project_id, finding_id), headers=owner_auth)
        assert listed.status_code == 200, listed.text
        runs = listed.json()
        assert [run["id"] for run in runs] == [body["id"]]

        session = create_session_factory()()
        try:
            audit = session.scalar(
                select(AuditLog).where(
                    AuditLog.action == "verification.requested",
                    AuditLog.resource_id == finding_id,
                )
            )
            assert audit is not None, "verification request was not audited"
            assert str(audit.actor_id) == owner_id
            assert audit.event_metadata is not None
            assert audit.event_metadata["attack_id"] == ATTACK["id"]
        finally:
            session.close()
    finally:
        _cleanup(project_id, owner_email)


def test_verification_requires_a_fixed_finding() -> None:
    project_id, finding_id, _target_id, _test_id, owner_email, _owner_id = _seed()
    _, owner_auth = _register(owner_email)
    try:
        response = client.post(_path(project_id, finding_id), headers=owner_auth)

        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "EXECUTION_BINDING_INVALID"
    finally:
        _cleanup(project_id, owner_email)


def test_target_override_is_honored() -> None:
    project_id, finding_id, _target_id, _test_id, owner_email, owner_id = _seed()
    _, owner_auth = _register(owner_email)

    session = create_session_factory()()
    try:
        owner = session.get(User, UUID(owner_id))
        assert owner is not None
        staging = _create_target(session, UUID(project_id), owner)
        staging_id = str(staging.id)
    finally:
        session.close()

    try:
        _mark_fixed(project_id, finding_id, owner_auth)

        response = client.post(
            _path(project_id, finding_id),
            headers=owner_auth,
            json={"target_id": staging_id},
        )

        assert response.status_code == 202, response.text
        assert response.json()["target_id"] == staging_id
    finally:
        _cleanup(project_id, owner_email)


def test_a_target_from_another_project_is_rejected() -> None:
    project_id, finding_id, _target_id, _test_id, owner_email, owner_id = _seed()
    _, owner_auth = _register(owner_email)

    session = create_session_factory()()
    try:
        owner = session.get(User, UUID(owner_id))
        assert owner is not None
        other = create_project(session, ProjectCreate(name=f"Other {uuid4()}"), owner_id=owner.id)
        other_target = _create_target(session, other.id, owner)
        other_target_id = str(other_target.id)
        other_project_id = str(other.id)
    finally:
        session.close()

    try:
        _mark_fixed(project_id, finding_id, owner_auth)

        response = client.post(
            _path(project_id, finding_id),
            headers=owner_auth,
            json={"target_id": other_target_id},
        )

        assert response.status_code == 404, response.text
    finally:
        _cleanup(other_project_id)
        _cleanup(project_id, owner_email)


def test_viewer_can_read_history_but_not_queue() -> None:
    project_id, finding_id, _target_id, _test_id, owner_email, owner_id = _seed()
    _, owner_auth = _register(owner_email)
    viewer_email, viewer_auth = _register(f"verification-viewer-{uuid4()}@example.com")

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
    finally:
        session.close()

    try:
        _mark_fixed(project_id, finding_id, owner_auth)

        denied = client.post(_path(project_id, finding_id), headers=viewer_auth)
        assert denied.status_code == 403, denied.text

        allowed = client.get(_path(project_id, finding_id), headers=viewer_auth)
        assert allowed.status_code == 200, allowed.text
    finally:
        _cleanup(project_id, owner_email, viewer_email)


def test_stranger_is_denied() -> None:
    project_id, finding_id, _target_id, _test_id, owner_email, _owner_id = _seed()
    _, stranger_auth = _register(f"verification-stranger-{uuid4()}@example.com")
    try:
        response = client.post(_path(project_id, finding_id), headers=stranger_auth)
        assert response.status_code in {403, 404}, response.status_code
    finally:
        _cleanup(project_id, owner_email)


def test_finding_paired_with_the_wrong_project_is_rejected() -> None:
    project_id, finding_id, _target_id, _test_id, owner_email, owner_id = _seed()
    _, owner_auth = _register(owner_email)

    session = create_session_factory()()
    try:
        owner = session.get(User, UUID(owner_id))
        assert owner is not None
        other = create_project(session, ProjectCreate(name=f"Other {uuid4()}"), owner_id=owner.id)
        other_project_id = str(other.id)
    finally:
        session.close()

    try:
        response = client.post(_path(other_project_id, finding_id), headers=owner_auth)
        assert response.status_code == 404, response.text
    finally:
        _cleanup(other_project_id)
        _cleanup(project_id, owner_email)


def test_missing_finding_is_rejected() -> None:
    project_id, _finding_id, _target_id, _test_id, owner_email, _owner_id = _seed()
    _, owner_auth = _register(owner_email)
    try:
        response = client.post(_path(project_id, str(uuid4())), headers=owner_auth)
        assert response.status_code == 404, response.text
    finally:
        _cleanup(project_id, owner_email)


def test_unauthenticated_requests_are_rejected() -> None:
    project_id, finding_id, _target_id, _test_id, owner_email, _owner_id = _seed()
    try:
        assert client.post(_path(project_id, finding_id)).status_code == 401
        assert client.get(_path(project_id, finding_id)).status_code == 401
    finally:
        _cleanup(project_id, owner_email)


def test_verified_cannot_be_patched_in() -> None:
    """The API must reject the one status that is supposed to be earned."""

    project_id, finding_id, _target_id, _test_id, owner_email, _owner_id = _seed()
    _, owner_auth = _register(owner_email)
    try:
        response = client.patch(
            f"/api/v1/projects/{project_id}/assessments/findings/{finding_id}",
            headers=owner_auth,
            json={"status": "verified"},
        )

        assert response.status_code == 422, response.text
    finally:
        _cleanup(project_id, owner_email)
