"""Project API authorization tests for Aegis Vuldris."""

from uuid import UUID, uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.audit_log import AuditLog
from app.models.project import Project
from app.models.user import User, UserRole
from fastapi.testclient import TestClient
from sqlalchemy import select

client = TestClient(app)


def _cleanup_user(email: str) -> None:
    session = create_session_factory()()

    try:
        user = session.scalar(select(User).where(User.email == email.lower()))

        if user is not None:
            session.delete(user)
            session.commit()
    finally:
        session.close()


def _cleanup_project(project_id: UUID) -> None:
    session = create_session_factory()()

    try:
        project = session.get(Project, project_id)

        if project is not None:
            session.delete(project)
            session.commit()
    finally:
        session.close()


def _register_user(email: str, role: UserRole = UserRole.USER) -> UUID:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "a-very-strong-password-123",
        },
    )

    assert response.status_code == 201

    session = create_session_factory()()

    try:
        user = session.scalar(select(User).where(User.email == email.lower()))

        assert user is not None
        user_id = user.id

        if role != UserRole.USER:
            user.role = role
            session.commit()
            session.refresh(user)

        return user_id
    finally:
        session.close()


def _login(email: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "a-very-strong-password-123",
        },
    )

    assert response.status_code == 200

    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_project(email: str, name: str) -> tuple[UUID, str]:
    response = client.post(
        "/api/v1/projects",
        headers=_auth_headers(_login(email)),
        json={"name": name, "description": "API project test"},
    )

    assert response.status_code == 201

    body = response.json()

    return UUID(body["id"]), body["owner_id"]


def test_project_list_requires_authentication() -> None:
    """Project listing is rejected when no bearer token is supplied."""

    response = client.get("/api/v1/projects")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_project_create_assigns_owner_and_records_audit() -> None:
    """Project creation assigns the authenticated user as owner and creates an audit event."""

    email = f"api-project-create-{uuid4()}@example.com"
    project_id = None
    owner_id = None

    try:
        user_id = _register_user(email)
        owner_id = str(user_id)

        project_id, response_owner_id = _create_project(email, f"Create Project {uuid4()}")

        assert response_owner_id == owner_id

        session = create_session_factory()()

        try:
            project = session.get(Project, project_id)

            assert project is not None
            assert project.owner_id == user_id

            audit = session.scalar(
                select(AuditLog).where(
                    AuditLog.resource_id == str(project.id),
                    AuditLog.action == "project.created",
                ),
            )

            assert audit is not None
            assert audit.actor_id == user_id
            assert audit.resource_type == "project"
        finally:
            session.close()
    finally:
        if project_id is not None:
            _cleanup_project(project_id)

        _cleanup_user(email)


def test_project_get_rejects_other_users_project() -> None:
    """A user cannot retrieve another user's private project."""

    owner_email = f"api-project-get-owner-{uuid4()}@example.com"
    other_email = f"api-project-get-other-{uuid4()}@example.com"
    project_id = None

    try:
        _register_user(owner_email)
        other_id = _register_user(other_email)
        project_id, _ = _create_project(owner_email, f"Get Project {uuid4()}")

        response = client.get(
            f"/api/v1/projects/{project_id}",
            headers=_auth_headers(_login(other_email)),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

        session = create_session_factory()()

        try:
            audit = session.scalar(
                select(AuditLog).where(
                    AuditLog.resource_id == str(project_id),
                    AuditLog.action == "project.access_denied",
                ),
            )

            assert audit is not None
            assert audit.actor_id == other_id
        finally:
            session.close()
    finally:
        if project_id is not None:
            _cleanup_project(project_id)

        _cleanup_user(owner_email)
        _cleanup_user(other_email)


def test_viewer_can_read_own_project_but_not_mutate() -> None:
    """Viewers can read their own projects but cannot update or delete them."""

    email = f"api-project-viewer-{uuid4()}@example.com"
    project_id = None

    try:
        viewer_id = _register_user(email, role=UserRole.VIEWER)
        project_id, _ = _create_project(email, f"Viewer Project {uuid4()}")

        token = _login(email)
        headers = _auth_headers(token)

        response = client.get(f"/api/v1/projects/{project_id}", headers=headers)

        response_body = response.json()
        assert response.status_code == 200
        assert response_body["owner_id"] == str(viewer_id)

        response = client.patch(
            f"/api/v1/projects/{project_id}",
            headers=headers,
            json={"name": "Viewer Update"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

        response = client.delete(f"/api/v1/projects/{project_id}", headers=headers)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"

        session = create_session_factory()()

        try:
            project = session.get(Project, project_id)

            assert project is not None
        finally:
            session.close()
    finally:
        if project_id is not None:
            _cleanup_project(project_id)

        _cleanup_user(email)


def test_admin_and_super_admin_can_manage_other_users_project() -> None:
    """Administrators can manage projects outside their own ownership."""

    owner_email = f"api-project-admin-owner-{uuid4()}@example.com"
    admin_email = f"api-project-admin-{uuid4()}@example.com"
    super_admin_email = f"api-project-super-admin-{uuid4()}@example.com"
    project_id = None

    try:
        _register_user(owner_email)
        _register_user(admin_email, role=UserRole.ADMIN)
        _register_user(super_admin_email, role=UserRole.SUPER_ADMIN)
        project_id, _ = _create_project(owner_email, f"Admin Project {uuid4()}")

        admin_token = _login(admin_email)
        super_admin_token = _login(super_admin_email)

        response = client.patch(
            f"/api/v1/projects/{project_id}",
            headers=_auth_headers(admin_token),
            json={"description": "Admin managed"},
        )

        assert response.status_code == 200
        assert response.json()["description"] == "Admin managed"

        response = client.delete(
            f"/api/v1/projects/{project_id}",
            headers=_auth_headers(super_admin_token),
        )

        assert response.status_code == 204

        session = create_session_factory()()

        try:
            assert session.get(Project, project_id) is None
        finally:
            session.close()
    finally:
        if project_id is not None:
            _cleanup_project(project_id)

        _cleanup_user(owner_email)
        _cleanup_user(admin_email)
        _cleanup_user(super_admin_email)


def test_project_not_found_still_returns_project_not_found() -> None:
    """Missing projects still return the existing PROJECT_NOT_FOUND error."""

    email = f"api-project-not-found-{uuid4()}@example.com"
    missing_id = uuid4()

    try:
        _register_user(email)

        response = client.get(
            f"/api/v1/projects/{missing_id}",
            headers=_auth_headers(_login(email)),
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    finally:
        _cleanup_user(email)


def _create_target(email: str, project_id: UUID) -> UUID:
    """Create a target on a project and return its ID."""

    response = client.post(
        "/api/v1/targets",
        headers=_auth_headers(_login(email)),
        json={
            "project_id": str(project_id),
            "name": f"Judge candidate {uuid4()}",
            "provider": "openai_compatible",
            "endpoint": "https://judge.example.com/v1",
            "model": "judge-model",
            "capabilities": ["chat"],
            "authorization_attestation": True,
        },
    )

    assert response.status_code == 201

    return UUID(response.json()["id"])


def test_project_judge_target_can_be_set_and_cleared() -> None:
    """A project's judge target is settable, visible, audited, and clearable."""

    email = f"api-project-judge-{uuid4()}@example.com"
    project_id = None

    try:
        _register_user(email)
        project_id, _ = _create_project(email, f"Judge Project {uuid4()}")
        target_id = _create_target(email, project_id)
        token = _login(email)

        # A fresh project judges with nothing until a judge target is chosen.
        response = client.get(f"/api/v1/projects/{project_id}", headers=_auth_headers(token))
        assert response.status_code == 200
        assert response.json()["judge_target_id"] is None

        response = client.patch(
            f"/api/v1/projects/{project_id}",
            headers=_auth_headers(token),
            json={"judge_target_id": str(target_id)},
        )
        assert response.status_code == 200
        assert response.json()["judge_target_id"] == str(target_id)

        # The change is visible on read and recorded in the update audit event.
        session = create_session_factory()()

        try:
            project = session.get(Project, project_id)
            assert project is not None
            assert project.judge_target_id == target_id

            entry = session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.resource_id == str(project_id),
                    AuditLog.action == "project.updated",
                )
                .order_by(AuditLog.created_at.desc())
            ).first()
            assert entry is not None
            changed_fields = (entry.event_metadata or {}).get("changed_fields", [])
            assert "judge_target_id" in changed_fields
        finally:
            session.close()

        # Sending null clears the judge target.
        response = client.patch(
            f"/api/v1/projects/{project_id}",
            headers=_auth_headers(token),
            json={"judge_target_id": None},
        )
        assert response.status_code == 200
        assert response.json()["judge_target_id"] is None
    finally:
        if project_id is not None:
            _cleanup_project(project_id)

        _cleanup_user(email)


def test_project_judge_target_must_belong_to_the_project() -> None:
    """A foreign or missing target is rejected as TARGET_NOT_FOUND, unchanged."""

    email = f"api-project-judge-scope-{uuid4()}@example.com"
    project_id = None
    other_project_id = None

    try:
        _register_user(email)
        project_id, _ = _create_project(email, f"Judge Scope {uuid4()}")
        other_project_id, _ = _create_project(email, f"Judge Scope Other {uuid4()}")
        other_target_id = _create_target(email, other_project_id)
        token = _login(email)

        # A target belonging to another project is treated as absent rather
        # than reported as existing, so the error cannot probe other projects.
        response = client.patch(
            f"/api/v1/projects/{project_id}",
            headers=_auth_headers(token),
            json={"judge_target_id": str(other_target_id)},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TARGET_NOT_FOUND"

        response = client.patch(
            f"/api/v1/projects/{project_id}",
            headers=_auth_headers(token),
            json={"judge_target_id": str(uuid4())},
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TARGET_NOT_FOUND"

        response = client.get(f"/api/v1/projects/{project_id}", headers=_auth_headers(token))
        assert response.json()["judge_target_id"] is None
    finally:
        for pid in (project_id, other_project_id):
            if pid is not None:
                _cleanup_project(pid)

        _cleanup_user(email)
