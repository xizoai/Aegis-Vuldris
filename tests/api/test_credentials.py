"""Target credential API integration tests for Aegis Vuldris."""

from uuid import UUID, uuid4

from app.db.session import create_session_factory
from app.main import app
from app.models.target import Target
from app.models.user import User, UserRole
from fastapi.testclient import TestClient

client = TestClient(app)


def _cleanup_user(email: str) -> None:
    session = create_session_factory()()
    try:
        user = session.query(User).filter(User.email == email.lower()).first()
        if user is not None:
            session.delete(user)
            session.commit()
    finally:
        session.close()


def _cleanup_project(project_id: UUID) -> None:
    from app.models.project import Project

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
        json={"email": email, "password": "a-very-strong-password-123"},
    )
    assert response.status_code == 201
    session = create_session_factory()()
    try:
        user = session.query(User).filter(User.email == email.lower()).first()
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
        json={"email": email, "password": "a-very-strong-password-123"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_project(email: str, name: str) -> UUID:
    response = client.post(
        "/api/v1/projects",
        headers=_auth_headers(_login(email)),
        json={"name": name, "description": "API credential project test"},
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


def _create_target(email: str, project_id: UUID, name: str = "Cred Target") -> UUID:
    response = client.post(
        "/api/v1/targets",
        headers=_auth_headers(_login(email)),
        json={
            "project_id": str(project_id),
            "name": name,
            "description": "API credential target test",
            "provider": "openai_compatible",
            "endpoint": "https://model.example.com/v1",
            "model": "test-model",
            "capabilities": ["chat"],
            "timeout_seconds": 45.0,
            "rate_limit_per_minute": 120,
            "status": "active",
            "authorization_attestation": True,
        },
    )
    assert response.status_code == 201
    return UUID(response.json()["id"])


def test_credential_crud_and_secret_redaction() -> None:
    email = f"api-cred-{uuid4()}@example.com"
    project_id = None
    target_id = None

    try:
        _register_user(email)
        project_id = _create_project(email, f"Cred Project {uuid4()}")
        target_id = _create_target(email, project_id)
        headers = _auth_headers(_login(email))

        create_response = client.post(
            f"/api/v1/targets/{target_id}/credentials",
            headers=headers,
            json={"credential_type": "api_key", "value": "sk-test-0123"},
        )
        assert create_response.status_code == 201
        credential_id = UUID(create_response.json()["id"])
        body = create_response.json()
        assert body["credential_type"] == "api_key"
        assert body["version"] == 1
        assert body["revoked"] is False
        assert "encrypted_value" not in body

        # There is no HTTP path that returns the stored value: plaintext is
        # resolved in-process by the execution engine only.
        resolve_response = client.post(
            f"/api/v1/targets/{target_id}/credentials/{credential_id}/resolve",
            headers=headers,
        )
        assert resolve_response.status_code in {404, 405}
        assert "sk-test-0123" not in resolve_response.text

        rotate_response = client.post(
            f"/api/v1/targets/{target_id}/credentials/{credential_id}/rotate",
            headers=headers,
            json={"credential_type": "api_key", "value": "sk-test-rotated"},
        )
        assert rotate_response.status_code == 200
        assert rotate_response.json()["version"] == 2

        list_response = client.get(
            f"/api/v1/targets/{target_id}/credentials",
            headers=headers,
        )
        assert list_response.status_code == 200
        assert len(list_response.json()) == 2

        revoke_response = client.post(
            f"/api/v1/targets/{target_id}/credentials/{credential_id}/revoke",
            headers=headers,
        )
        assert revoke_response.status_code == 200
        assert revoke_response.json()["revoked"] is True

        delete_response = client.delete(
            f"/api/v1/targets/{target_id}/credentials/{credential_id}",
            headers=headers,
        )
        assert delete_response.status_code == 204
    finally:
        if target_id is not None and project_id is not None:
            session = create_session_factory()()
            try:
                session.delete(session.get(Target, target_id))
                session.commit()
            finally:
                session.close()
        if project_id is not None:
            _cleanup_project(project_id)
        _cleanup_user(email)
